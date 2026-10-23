"""
Pedidos de la web que el sincronizador baja al sistema local (Render -> SQL Server), lado servidor.
Conexiones y cursores simulados: no toca ninguna base ni la red.

Reglas: solo se entregan los PENDIENTE; se marcan RECIBIDO a pedido del sincronizador y marcar dos veces no hace dano.
"""
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi import HTTPException

from backend.app.routers import sync


def normalizar(sql):
    return " ".join(sql.split())


class Cursor:
    def __init__(self, respuestas=(), falla=False):
        self.respuestas = list(respuestas)
        self.falla = falla
        self.consultas = []

    def execute(self, sql, params=()):
        if self.falla:
            raise RuntimeError("falla simulada")
        self.consultas.append((normalizar(sql), tuple(params)))

    def fetchall(self):
        return self.respuestas.pop(0)

    def fetchone(self):
        return self.respuestas.pop(0)

    def close(self):
        pass


class Conn:
    def __init__(self, cursor):
        self._cursor = cursor
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return self._cursor

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        pass


FECHA = datetime(2026, 10, 23, 14, 30, tzinfo=timezone.utc)


def rutas(sufijo, metodo):
    return [r for r in sync.router.routes if r.path.endswith(sufijo) and metodo in r.methods]


@pytest.mark.parametrize("sufijo, metodo", [("/pedidos-pendientes", "GET"), ("/pedidos/{id_pedido}/recibido", "POST")])
def test_las_rutas_estan_protegidas_con_la_clave_del_sincronizador(sufijo, metodo):
    encontradas = rutas(sufijo, metodo)
    assert len(encontradas) == 1
    assert any(d.call is sync.verificar_sincronizador for d in encontradas[0].dependant.dependencies)


def test_solo_se_piden_los_pendientes_en_orden():
    sql = normalizar(sync.SQL_PEDIDOS_PENDIENTES)
    assert "estado_sync = 'PENDIENTE' AND id_pedido > %s" in sql and "ORDER BY id_pedido" in sql and "LIMIT %s" in sql


def test_entrega_cabecera_y_detalle_de_cada_pedido(monkeypatch):
    cur = Cursor([
        [(7, "Ana Perez", "Calle 1", "0981", FECHA), (8, "Luis", "Ruta 2", "0982", FECHA)],
        [(7, 10, Decimal("2"), Decimal("15000")), (7, 11, Decimal("1.5"), Decimal("8000")), (8, 10, Decimal("1"), Decimal("15000"))],
    ])
    conn = Conn(cur)
    monkeypatch.setattr(sync, "obtener_conexion_postgres", lambda: conn)
    resp = sync.listar_pedidos_pendientes(limite=50, despues_de=0)
    assert resp["status"] == "ok" and [p["id_pedido"] for p in resp["pedidos"]] == [7, 8]
    primero = resp["pedidos"][0]
    assert primero["cliente_nombre"] == "Ana Perez" and primero["fecha_pedido"] == FECHA.isoformat()
    assert primero["detalle"] == [
        {"art_cod": 10, "cantidad": 2.0, "precio_unitario": 15000.0},
        {"art_cod": 11, "cantidad": 1.5, "precio_unitario": 8000.0},
    ]
    assert len(resp["pedidos"][1]["detalle"]) == 1
    assert cur.consultas[0][1] == (0, 50) and cur.consultas[1][1] == ([7, 8],)
    assert conn.commits == 0                      # solo lectura


def test_sin_pedidos_no_consulta_el_detalle(monkeypatch):
    cur = Cursor([[]])
    monkeypatch.setattr(sync, "obtener_conexion_postgres", lambda: Conn(cur))
    assert sync.listar_pedidos_pendientes(limite=50, despues_de=0) == {"status": "ok", "pedidos": []}
    assert len(cur.consultas) == 1


def test_marca_recibido_y_confirma(monkeypatch):
    cur = Cursor([(7,)])
    conn = Conn(cur)
    monkeypatch.setattr(sync, "obtener_conexion_postgres", lambda: conn)
    assert sync.marcar_pedido_recibido(7) == {"status": "ok", "id_pedido": 7}
    assert conn.commits == 1 and cur.consultas[0][1] == (7,)


def test_marcar_dos_veces_no_pisa_la_fecha_original():
    sql = normalizar(sync.SQL_MARCAR_PEDIDO_RECIBIDO)
    assert "COALESCE(fecha_sincronizacion, now())" in sql and "DELETE" not in sql.upper()


def test_pedido_inexistente_responde_404(monkeypatch):
    conn = Conn(Cursor([None]))
    monkeypatch.setattr(sync, "obtener_conexion_postgres", lambda: conn)
    with pytest.raises(HTTPException) as e:
        sync.marcar_pedido_recibido(999)
    assert e.value.status_code == 404 and conn.commits == 0


@pytest.mark.parametrize("llamada", [
    lambda: sync.listar_pedidos_pendientes(limite=50, despues_de=0),
    lambda: sync.marcar_pedido_recibido(7),
])
def test_si_la_base_falla_responde_500_sin_confirmar(monkeypatch, llamada):
    conn = Conn(Cursor(falla=True))
    monkeypatch.setattr(sync, "obtener_conexion_postgres", lambda: conn)
    with pytest.raises(HTTPException) as e:
        llamada()
    assert e.value.status_code == 500 and conn.commits == 0
