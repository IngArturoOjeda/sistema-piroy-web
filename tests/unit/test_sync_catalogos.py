"""
Sincronizacion de tipos de articulo y unidades de medida (SQL Server -> PostgreSQL).
Conexiones y cursores simulados: no toca ninguna base ni la red.

Reglas: el sistema local manda la lista completa; la web crea lo que falta y actualiza el nombre, pero NUNCA
toca tipo_articulo.mostrar_web ni unidad_medida.fraccionable (se deciden en el panel) y nunca borra.
"""
from collections import namedtuple
from decimal import Decimal

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from backend.app.routers import sync
from backend.app.schemas import CatalogosSync
from sincronizador import sincronizador


def normalizar(sql):
    return " ".join(sql.split())


class Cursor:
    def __init__(self, falla=False):
        self.falla = falla
        self.consultas = []

    def execute(self, sql, params=()):
        if self.falla:
            raise RuntimeError("falla simulada")
        self.consultas.append((normalizar(sql), tuple(params)))

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


def datos(tipos=None, unidades=None):
    return CatalogosSync(
        tipos=tipos if tipos is not None else [{"tipoart_cod": 1, "tipoart_desc": "BALANCEADOS"}],
        unidades=unidades if unidades is not None else [{"uni_cod": 1, "uni_nombre": "UNIDAD"}],
    )


# ---------- servidor: validacion ----------

def test_los_nombres_se_limpian_de_espacios():
    d = datos([{"tipoart_cod": 2, "tipoart_desc": "  MEDICAMENTOS   "}], [{"uni_cod": 3, "uni_nombre": "KG   "}])
    assert d.tipos[0].tipoart_desc == "MEDICAMENTOS" and d.unidades[0].uni_nombre == "KG"


@pytest.mark.parametrize("tipos, unidades", [
    ([{"tipoart_cod": 1, "tipoart_desc": "   "}], []),
    ([{"tipoart_cod": 0, "tipoart_desc": "X"}], []),
    ([{"tipoart_cod": 1, "tipoart_desc": "A"}, {"tipoart_cod": 1, "tipoart_desc": "B"}], []),
    ([], [{"uni_cod": 1, "uni_nombre": "A"}, {"uni_cod": 1, "uni_nombre": "B"}]),
    ([], [{"uni_cod": -1, "uni_nombre": "A"}]),
])
def test_datos_invalidos_se_rechazan(tipos, unidades):
    with pytest.raises(ValidationError):
        datos(tipos, unidades)


# ---------- servidor: endpoint ----------

def test_la_ruta_esta_protegida_con_la_clave_del_sincronizador():
    rutas = [r for r in sync.router.routes if r.path.endswith("/catalogos")]
    assert len(rutas) == 1 and "POST" in rutas[0].methods
    assert any(d.call is sync.verificar_sincronizador for d in rutas[0].dependant.dependencies)


def test_crea_y_actualiza_tipos_y_unidades_en_una_transaccion(monkeypatch):
    cur = Cursor()
    conn = Conn(cur)
    monkeypatch.setattr(sync, "obtener_conexion_postgres", lambda: conn)
    d = datos([{"tipoart_cod": 1, "tipoart_desc": "BALANCEADOS"}, {"tipoart_cod": 2, "tipoart_desc": "MEDICAMENTOS"}],
              [{"uni_cod": 4, "uni_nombre": "GRAMOS"}])
    resp = sync.sincronizar_catalogos(d)
    assert resp == {"status": "ok", "tipos": 2, "unidades": 1}
    assert conn.commits == 1 and conn.rollbacks == 0
    assert [p for _, p in cur.consultas] == [(1, "BALANCEADOS"), (2, "MEDICAMENTOS"), (4, "GRAMOS")]


def test_no_toca_lo_que_se_decide_en_el_panel():
    for sql in (sync.SQL_UPSERT_TIPO, sync.SQL_UPSERT_UNIDAD):
        actualiza = normalizar(sql).split("DO UPDATE SET")[1]
        assert "mostrar_web" not in actualiza and "fraccionable" not in actualiza
        assert "DELETE" not in sql.upper()
    # una unidad nueva empieza como no fraccionable
    assert "VALUES (%s, %s, FALSE)" in normalizar(sync.SQL_UPSERT_UNIDAD)


def test_si_la_base_falla_deshace_todo_y_responde_500(monkeypatch):
    conn = Conn(Cursor(falla=True))
    monkeypatch.setattr(sync, "obtener_conexion_postgres", lambda: conn)
    with pytest.raises(HTTPException) as e:
        sync.sincronizar_catalogos(datos())
    assert e.value.status_code == 500
    assert conn.rollbacks == 1 and conn.commits == 0


# ---------- sincronizador ----------

Tipo = namedtuple("Tipo", "TIPOART_COD TIPOART_DESC")
Unidad = namedtuple("Unidad", "UNI_COD UNI_NOMBRE")


class CursorSqlServer:
    def __init__(self, tipos, unidades):
        self.tipos, self.unidades, self.ultima = tipos, unidades, None

    def execute(self, sql):
        self.ultima = sql

    def fetchall(self):
        return self.tipos if "TIPOARTICULO" in self.ultima else self.unidades


def test_el_sincronizador_lee_las_tablas_reales_del_negocio():
    assert "FROM TIPOARTICULO" in sincronizador.SQL_TIPOS and "TIPOART_COD" in sincronizador.SQL_TIPOS
    assert "FROM UNIDADMEDIDA" in sincronizador.SQL_UNIDADES and "UNI_NOMBRE" in sincronizador.SQL_UNIDADES


def test_el_payload_limpia_espacios_y_convierte_codigos():
    cur = CursorSqlServer(
        [Tipo(1, "BALANCEADOS" + " " * 39), Tipo(5003, "KIT   "), Tipo(9, "   "), Tipo(None, "X")],
        [Unidad(Decimal("1"), "UNIDAD "), Unidad(Decimal("3"), "KG"), Unidad(Decimal("8"), None)],
    )
    payload = sincronizador.construir_payload_catalogos(cur)
    assert payload["tipos"] == [{"tipoart_cod": 1, "tipoart_desc": "BALANCEADOS"}, {"tipoart_cod": 5003, "tipoart_desc": "KIT"}]
    assert payload["unidades"] == [{"uni_cod": 1, "uni_nombre": "UNIDAD"}, {"uni_cod": 3, "uni_nombre": "KG"}]
    assert all(type(u["uni_cod"]) is int for u in payload["unidades"])


def test_envia_los_catalogos_y_valida_la_confirmacion(monkeypatch):
    enviados = []

    def falso(url, api_key, payload):
        enviados.append((url, api_key, payload))
        return {"status": "ok", "tipos": len(payload["tipos"]), "unidades": len(payload["unidades"])}

    monkeypatch.setattr(sincronizador, "enviar_articulo", falso)
    cur = CursorSqlServer([Tipo(1, "A")], [Unidad(1, "UNIDAD")])
    sincronizador.sincronizar_catalogos(cur, "http://x/api/sync/catalogos", "clave")
    assert enviados[0][0] == "http://x/api/sync/catalogos" and enviados[0][1] == "clave"


@pytest.mark.parametrize("respuesta", [{"status": "error"}, {"status": "ok", "tipos": 0, "unidades": 1}, "texto"])
def test_si_el_servidor_no_confirma_bien_es_error(monkeypatch, respuesta):
    monkeypatch.setattr(sincronizador, "enviar_articulo", lambda *a: respuesta)
    cur = CursorSqlServer([Tipo(1, "A")], [Unidad(1, "UNIDAD")])
    with pytest.raises(sincronizador.ErrorSincronizacion):
        sincronizador.sincronizar_catalogos(cur, "http://x", "clave")


def preparar_main(monkeypatch, orden, catalogos):
    monkeypatch.setattr(sincronizador, "obtener_variable", lambda n: f"valor-{n}")
    monkeypatch.setattr(sincronizador, "obtener_conexion", lambda: Conn(Cursor()))
    monkeypatch.setattr(sincronizador, "leer_pendientes", lambda c: ["fila"])
    monkeypatch.setattr(sincronizador, "sincronizar_catalogos", catalogos)
    monkeypatch.setattr(sincronizador, "sincronizar_pedidos", lambda c, cur, k: False)
    monkeypatch.setattr(sincronizador, "procesar_pendientes",
                        lambda *a: orden.append("articulos") or {"errores": [], "motivo_aborto": None})
    monkeypatch.setattr(sincronizador, "imprimir_resumen", lambda r: None)
    monkeypatch.setattr(sincronizador, "leer_pendientes_kits", lambda c: [])
    monkeypatch.setattr(sincronizador, "leer_pendientes_stock", lambda c: [])


def test_los_catalogos_se_envian_antes_que_los_articulos(monkeypatch):
    orden = []
    preparar_main(monkeypatch, orden, lambda c, u, k: orden.append(("catalogos", u)))
    sincronizador.main()
    assert orden == [("catalogos", "valor-SYNC_API_URL_CATALOGOS"), "articulos"]


def test_si_fallan_los_catalogos_no_se_envian_articulos(monkeypatch):
    orden = []

    def falla(*a):
        raise sincronizador.ErrorConexion("sin red")

    preparar_main(monkeypatch, orden, falla)
    with pytest.raises(SystemExit):
        sincronizador.main()
    assert orden == []
