"""
Pedidos de la web que el sincronizador guarda en SQL Server (PEDIDOS_WEB / PEDIDOS_WEB_DETALLE), lado sincronizador.
Sin tocar ninguna base ni la red.

Reglas: cabecera + detalle en una transaccion; recien despues se marca RECIBIDO en la web; si ya estaba guardado
(corte entre una cosa y otra) no se duplica y solo se marca; un error de un pedido no frena a los demas.
"""
from datetime import datetime, timezone
from decimal import Decimal

import pyodbc
import pytest

from sincronizador import sincronizador


def pedido(id_pedido=7, detalle=None, nombre="Ana Perez"):
    return {
        "id_pedido": id_pedido,
        "cliente_nombre": nombre,
        "cliente_direccion": "Calle 1",
        "cliente_telefono": "0981",
        "fecha_pedido": "2026-10-23T14:30:00+00:00",
        "detalle": detalle if detalle is not None else [
            {"art_cod": 10, "cantidad": 2.0, "precio_unitario": 15000.0},
            {"art_cod": 11, "cantidad": 1.5, "precio_unitario": 8000.0},
        ],
    }


class Cursor:
    def __init__(self, existentes=(), falla_en=None):
        self.existentes, self.falla_en = set(existentes), falla_en
        self.ejecutados, self._ultimo = [], None

    def execute(self, sql, params=()):
        if self.falla_en and self.falla_en in sql:
            raise pyodbc.Error("falla simulada")
        self.ejecutados.append((" ".join(sql.split()), tuple(params)))
        self._ultimo = (sql, tuple(params))

    def fetchone(self):
        sql, params = self._ultimo
        return (1,) if "SELECT 1" in sql and params[0] in self.existentes else None


class Conn:
    def __init__(self):
        self.commits = self.rollbacks = 0

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


# ---------- armado y validacion ----------

def test_arma_cabecera_y_detalle_con_el_total_por_linea():
    cabecera, filas = sincronizador.construir_filas_pedido(pedido())
    assert cabecera[:4] == (7, "Ana Perez", "Calle 1", "0981")
    assert isinstance(cabecera[4], datetime) and cabecera[4].tzinfo is None
    assert filas == [
        (7, 10, Decimal("2.0"), Decimal("15000.0"), Decimal("30000.00")),
        (7, 11, Decimal("1.5"), Decimal("8000.0"), Decimal("12000.00")),
    ]


def test_la_fecha_se_pasa_a_la_hora_local_sin_zona():
    esperado = datetime(2026, 10, 23, 14, 30, tzinfo=timezone.utc).astimezone().replace(tzinfo=None)
    assert sincronizador.fecha_local("2026-10-23T14:30:00+00:00") == esperado


@pytest.mark.parametrize("malo", [
    pedido(detalle=[]),
    pedido(id_pedido=0),
    pedido(detalle=[{"art_cod": 10, "cantidad": 0, "precio_unitario": 100}]),
    pedido(detalle=[{"art_cod": 10, "cantidad": 1, "precio_unitario": -5}]),
    pedido(detalle=[{"art_cod": 10, "cantidad": 1}]),
    {"id_pedido": 1},
])
def test_pedidos_invalidos_se_rechazan(malo):
    with pytest.raises(sincronizador.ErrorSincronizacion):
        sincronizador.construir_filas_pedido(malo)


def test_nombre_vacio_y_textos_largos_no_traban_el_pedido():
    cabecera, _ = sincronizador.construir_filas_pedido(
        {**pedido(nombre="   "), "cliente_direccion": "x" * 500, "cliente_telefono": None})
    assert cabecera[1] == "SIN NOMBRE" and len(cabecera[2]) == 300 and cabecera[3] is None
    cabecera, _ = sincronizador.construir_filas_pedido(pedido(nombre="N" * 200))
    assert len(cabecera[1]) == 150


def test_el_codigo_de_articulo_admite_el_rango_completo():
    _, filas = sincronizador.construir_filas_pedido(
        pedido(detalle=[{"art_cod": 10**17 + 5, "cantidad": 1, "precio_unitario": 100}]))
    assert filas[0][1] == 10**17 + 5


# ---------- guardado ----------

def test_guarda_cabecera_y_detalle_en_una_transaccion():
    cur, conn = Cursor(), Conn()
    cabecera, filas = sincronizador.construir_filas_pedido(pedido())
    assert sincronizador.guardar_pedido(conn, cur, cabecera, filas) is True
    sqls = [s for s, _ in cur.ejecutados]
    assert "INSERT INTO PEDIDOS_WEB (" in sqls[1] and sum("PEDIDOS_WEB_DETALLE" in s for s in sqls) == 2
    assert conn.commits == 1 and conn.rollbacks == 0


def test_si_ya_estaba_guardado_no_inserta_nada():
    cur, conn = Cursor(existentes=[7]), Conn()
    cabecera, filas = sincronizador.construir_filas_pedido(pedido())
    assert sincronizador.guardar_pedido(conn, cur, cabecera, filas) is False
    assert len(cur.ejecutados) == 1 and conn.commits == 0


def test_si_falla_un_insert_deshace_todo():
    cur, conn = Cursor(falla_en="PEDIDOS_WEB_DETALLE"), Conn()
    cabecera, filas = sincronizador.construir_filas_pedido(pedido())
    with pytest.raises(sincronizador.ErrorSincronizacion):
        sincronizador.guardar_pedido(conn, cur, cabecera, filas)
    assert conn.commits == 0 and conn.rollbacks == 1


def test_el_pedido_web_no_toca_stock():
    for sql in (sincronizador.SQL_INSERTAR_PEDIDO, sincronizador.SQL_INSERTAR_PEDIDO_DETALLE, sincronizador.SQL_PEDIDO_EXISTE):
        assert "STOCK" not in sql.upper() and "UPDATE" not in sql.upper() and "DELETE" not in sql.upper()


# ---------- proceso completo ----------

def preparar(monkeypatch, falla_marcar=()):
    marcados = []

    def enviar(url, api_key, payload, metodo="POST"):
        id_pedido = int(url.split("/")[-2])
        if id_pedido in falla_marcar:
            raise sincronizador.ErrorConexion("sin red")
        marcados.append(id_pedido)
        return {"status": "ok", "id_pedido": id_pedido}

    monkeypatch.setattr(sincronizador, "enviar_articulo", enviar)
    return marcados


def test_marca_recibido_solo_despues_de_guardar(monkeypatch):
    marcados = preparar(monkeypatch)
    cur, conn = Cursor(falla_en="INSERT INTO PEDIDOS_WEB ("), Conn()
    resumen = sincronizador.procesar_pedidos(conn, cur, [pedido(7)], "http://x/pedidos", "k")
    assert marcados == [] and resumen["errores"] == [7] and resumen["ok"] == 0


def test_guarda_y_marca_cada_pedido(monkeypatch):
    marcados = preparar(monkeypatch)
    resumen = sincronizador.procesar_pedidos(Conn(), Cursor(), [pedido(7), pedido(8)], "http://x/pedidos", "k")
    assert marcados == [7, 8] and resumen["ok"] == 2 and resumen["errores"] == []


def test_si_se_corto_antes_de_marcar_el_reintento_no_duplica(monkeypatch):
    marcados = preparar(monkeypatch)
    cur = Cursor(existentes=[7])
    resumen = sincronizador.procesar_pedidos(Conn(), cur, [pedido(7)], "http://x/pedidos", "k")
    assert marcados == [7] and resumen["ya_estaban"] == 1 and resumen["errores"] == []
    assert not any("INSERT" in s for s, _ in cur.ejecutados)


def test_un_pedido_con_error_no_frena_a_los_demas(monkeypatch):
    marcados = preparar(monkeypatch)
    resumen = sincronizador.procesar_pedidos(Conn(), Cursor(), [pedido(7, detalle=[]), pedido(8)], "http://x/pedidos", "k")
    assert marcados == [8] and resumen["errores"] == [7] and resumen["ok"] == 1


def test_tres_fallos_de_conexion_seguidos_detienen_el_proceso(monkeypatch):
    preparar(monkeypatch, falla_marcar={1, 2, 3, 4})
    resumen = sincronizador.procesar_pedidos(Conn(), Cursor(), [pedido(i) for i in (1, 2, 3, 4)], "http://x/pedidos", "k")
    assert resumen["motivo_aborto"] and resumen["sin_procesar"] == 1 and len(resumen["errores"]) == 3


def test_respuesta_distinta_al_pedido_no_cuenta_como_recibido(monkeypatch):
    monkeypatch.setattr(sincronizador, "enviar_articulo", lambda *a, **k: {"status": "ok", "id_pedido": 99})
    resumen = sincronizador.procesar_pedidos(Conn(), Cursor(), [pedido(7)], "http://x/pedidos", "k")
    assert resumen["errores"] == [7] and resumen["ok"] == 0


# ---------- paso dentro de main ----------

def test_la_lectura_usa_get_y_valida_la_respuesta(monkeypatch):
    llamadas = []

    def enviar(url, api_key, payload, metodo="POST"):
        llamadas.append((url, payload, metodo))
        return {"status": "ok", "pedidos": [pedido(7)]}

    monkeypatch.setattr(sincronizador, "enviar_articulo", enviar)
    assert sincronizador.leer_pedidos_pendientes_web("http://x/p", "k") == [pedido(7)]
    assert llamadas == [("http://x/p?limite=50&despues_de=0", None, "GET")]
    monkeypatch.setattr(sincronizador, "enviar_articulo", lambda *a, **k: {"status": "ok"})
    with pytest.raises(sincronizador.ErrorSincronizacion):
        sincronizador.leer_pedidos_pendientes_web("http://x/p", "k")


def test_un_error_en_pedidos_se_informa_pero_no_lanza(monkeypatch, capsys):
    monkeypatch.setattr(sincronizador, "obtener_variable", lambda n: (_ for _ in ()).throw(RuntimeError("falta " + n)))
    assert sincronizador.sincronizar_pedidos(Conn(), Cursor(), "k") is True
    assert "Error en los pedidos web" in capsys.readouterr().out


def test_main_procesa_articulos_aunque_fallen_los_pedidos(monkeypatch):
    etapas = []
    monkeypatch.setattr(sincronizador, "obtener_variable", lambda n: "v")
    monkeypatch.setattr(sincronizador, "obtener_conexion", lambda: type("C", (), {"cursor": lambda s: None, "close": lambda s: None})())
    monkeypatch.setattr(sincronizador, "sincronizar_pedidos", lambda c, cur, k: True)
    monkeypatch.setattr(sincronizador, "leer_pendientes", lambda c: [])
    monkeypatch.setattr(sincronizador, "leer_pendientes_kits", lambda c: etapas.append("kits") or [])
    monkeypatch.setattr(sincronizador, "leer_pendientes_stock", lambda c: etapas.append("stock") or [])
    with pytest.raises(SystemExit) as e:
        sincronizador.main()
    assert etapas == ["kits", "stock"] and e.value.code == 1


def test_un_pedido_que_falla_no_traba_a_los_mas_nuevos(monkeypatch):
    """Primera pagina llena: 50 pedidos, el primero con error. La segunda pagina se pide desde el ultimo id."""
    paginas = {0: [pedido(i, detalle=[] if i == 1 else None) for i in range(1, 51)], 50: [pedido(51)]}
    pedidas = []

    def leer(url, api_key, despues_de=0):
        pedidas.append(despues_de)
        return paginas[despues_de]

    marcados = []
    monkeypatch.setattr(sincronizador, "obtener_variable", lambda n: "http://x/" + n)
    monkeypatch.setattr(sincronizador, "leer_pedidos_pendientes_web", leer)
    monkeypatch.setattr(sincronizador, "marcar_pedido_recibido", lambda u, k, i: marcados.append(i))
    assert sincronizador.sincronizar_pedidos(Conn(), Cursor(), "k") is True
    assert pedidas == [0, 50] and 51 in marcados and 1 not in marcados and len(marcados) == 50
