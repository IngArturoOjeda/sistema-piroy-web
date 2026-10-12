"""
Prueba la funcion REAL confirmar_pedido() de backend/app/routers/items.py con un
cursor simulado. Cubre rutas que no existen en los datos reales de produccion
(kit sin componentes, componente inexistente, kit anidado, art_cantidad <= 0)
y la regla de stock agregado entre articulo directo y kit.

Sin base de datos: la conexion se reemplaza por FakeConn y psycopg.connect esta bloqueado.
"""
from decimal import Decimal

import pytest
from fastapi import HTTPException

from backend.app.routers import items
from backend.app.schemas import PedidoEntrada


class FakeCursor:
    def __init__(self, escenario):
        self.escenario = escenario
        self._resultado = []
        self._id_pedido_generado = escenario.get("id_pedido", 99999)
        self.se_inserto_cabecera = False
        self.se_inserto_detalle = 0
        self.se_inserto_componentes = 0
        self.consultas = []
        self.precios_insertados = []

    def executemany(self, sql, filas):
        sql_n = " ".join(sql.split())
        if "INSERT INTO pedido_detalle_componentes" in sql_n:
            self.se_inserto_componentes += len(filas)
        else:
            raise AssertionError(f"executemany no esperado: {sql_n[:80]}")

    def execute(self, sql, params=None):
        sql_n = " ".join(sql.split())
        if sql_n.split(" ", 1)[0].upper() in ("UPDATE", "DELETE", "DROP", "CREATE", "ALTER", "TRUNCATE"):
            raise AssertionError("escritura inesperada en test unit")
        self.consultas.append(sql_n)

        if "INSERT INTO pedido_cabecera" in sql_n:
            self.se_inserto_cabecera = True
            self._resultado = None
        elif "INSERT INTO pedido_detalle_componentes" in sql_n:
            self.se_inserto_componentes += 1
            self._resultado = None
        elif "INSERT INTO pedido_detalle " in sql_n:
            self.se_inserto_detalle += 1
            self.precios_insertados.append(params[3])   # (id_pedido, art_cod, cantidad, precio_unitario)
            self._resultado = None
        elif "FROM articulos_kit" in sql_n:
            self._resultado = self.escenario.get("componentes", [])
        elif "LEFT JOIN stock s" in sql_n and "FROM articulos a" in sql_n:
            self._resultado = self.escenario.get("stock_fisico", [])
        elif "FROM articulos a" in sql_n and "unidad_medida" in sql_n:
            # Las filas pueden traer 6 columnas (sin promo) o 7 (con precio_promo al final)
            self._resultado = [f + (None,) * (7 - len(f)) for f in self.escenario.get("articulos", [])]
        else:
            raise AssertionError(f"Consulta SQL no reconocida por el test: {sql_n[:80]}")

    def fetchall(self):
        return self._resultado or []

    def fetchone(self):
        return (self._id_pedido_generado,)

    def close(self):
        pass


class FakeConn:
    def __init__(self, cursor):
        self._cursor = cursor
        self.committed = False
        self.rolled_back = False

    def cursor(self):
        return self._cursor

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        pass


def precio_oficial(escenario, id_):
    """Precio que cobra el servidor: el promocional vigente si rebaja, si no el de lista."""
    for fila in escenario.get("articulos", []):
        if fila[0] == id_:
            base = fila[2]
            promo = fila[6] if len(fila) > 6 else None
            return promo if promo is not None and promo < base else base
    return Decimal(1)


def correr_caso(monkeypatch, escenario, productos):
    cursor = FakeCursor(escenario)
    conn = FakeConn(cursor)
    monkeypatch.setattr(items, "obtener_conexion_postgres", lambda: conn)
    productos = [
        {**p, "precio": float(precio_oficial(escenario, p["id"])) if p["precio"] is None else p["precio"]}
        for p in productos
    ]

    pedido = PedidoEntrada(
        cliente_nombre="Test Mock",
        cliente_direccion="Test 123",
        cliente_telefono="0981000000",
        productos=productos,
    )
    try:
        respuesta = items.confirmar_pedido(pedido)
        return {"ok": True, "conn": conn, "cursor": cursor, "respuesta": respuesta}
    except HTTPException as e:
        return {"ok": False, "status": e.status_code, "detail": e.detail, "conn": conn, "cursor": cursor}


def item(id_, cantidad, precio=None):
    # precio=None: el test manda el precio oficial vigente (ver correr_caso)
    return {"id": id_, "nombre": "x", "precio": precio, "cantidad": cantidad}


# Escenario compartido: articulo directo 5000 (stock 100) y kit 5001 que consume 25 del mismo componente.
ESCENARIO_DIRECTO_Y_KIT = {
    "articulos": [
        (5000, "MAIZ A GRANEL", Decimal("3000"), False, True, "KG"),
        (5001, "MAIZ BOLSA 25 KG", Decimal("70000"), True, False, "BOLSA"),
    ],
    "componentes": [(5001, 5000, Decimal("25.000"))],
    "stock_fisico": [(5000, "MAIZ A GRANEL", False, Decimal("100.000"))],
}


def test_directo_mas_kit_que_superan_stock_fisico_se_rechaza(monkeypatch):
    r = correr_caso(monkeypatch, ESCENARIO_DIRECTO_Y_KIT, [item(5000, Decimal("50")), item(5001, 3)])
    assert r["ok"] is False and r["status"] == 400
    assert "MAIZ A GRANEL" in r["detail"], "el mensaje nombra el componente fisico, no el kit"
    assert r["cursor"].se_inserto_cabecera is False
    assert r["conn"].committed is False


def test_directo_mas_kit_dentro_de_stock_fisico_se_confirma(monkeypatch):
    r = correr_caso(monkeypatch, ESCENARIO_DIRECTO_Y_KIT, [item(5000, Decimal("30")), item(5001, 2)])
    assert r["ok"] is True
    assert r["cursor"].se_inserto_cabecera is True
    assert r["cursor"].se_inserto_detalle == 2
    assert r["conn"].committed is True


def test_kit_sin_componentes_configurados_da_500(monkeypatch):
    escenario = {
        "articulos": [(9001, "KIT SIN COMPONENTES", Decimal("1000"), True, False, "UNIDAD")],
        "componentes": [],
        "stock_fisico": [],
    }
    r = correr_caso(monkeypatch, escenario, [item(9001, 1)])
    assert r["ok"] is False and r["status"] == 500
    assert "no tiene componentes" in r["detail"]
    assert r["cursor"].se_inserto_cabecera is False


def test_componente_inexistente_da_500(monkeypatch):
    escenario = {
        "articulos": [(9002, "KIT CON COMPONENTE FANTASMA", Decimal("1000"), True, False, "UNIDAD")],
        "componentes": [(9002, 777777, Decimal("1.000"))],
        "stock_fisico": [],
    }
    r = correr_caso(monkeypatch, escenario, [item(9002, 1)])
    assert r["ok"] is False and r["status"] == 500
    assert "no existen" in r["detail"] and "777777" in r["detail"]
    assert r["cursor"].se_inserto_cabecera is False


def test_kit_anidado_da_500(monkeypatch):
    escenario = {
        "articulos": [(9003, "KIT QUE CONTIENE OTRO KIT", Decimal("1000"), True, False, "UNIDAD")],
        "componentes": [(9003, 9004, Decimal("2.000"))],
        "stock_fisico": [(9004, "SUB-KIT ANIDADO", True, Decimal("50.000"))],
    }
    r = correr_caso(monkeypatch, escenario, [item(9003, 1)])
    assert r["ok"] is False and r["status"] == 500
    assert "kit anidado" in r["detail"]
    assert r["cursor"].se_inserto_cabecera is False


def test_art_cantidad_cero_en_componente_da_500(monkeypatch):
    escenario = {
        "articulos": [(9005, "KIT CON COMPONENTE MAL CARGADO", Decimal("1000"), True, False, "UNIDAD")],
        "componentes": [(9005, 5000, Decimal("0.000"))],
        "stock_fisico": [],
    }
    r = correr_caso(monkeypatch, escenario, [item(9005, 1)])
    assert r["ok"] is False and r["status"] == 500
    assert "composición inválida" in r["detail"]
    assert r["cursor"].se_inserto_cabecera is False


# ---------------------------------------------------------------------------
# Precio del pedido: promocion vigente y proteccion contra cambios de precio
# ---------------------------------------------------------------------------

def escenario_precio(base, promo=None, art_cod=6000, kit=False):
    """Un articulo normal (o kit sin componentes validos no se usa aqui) con stock de sobra."""
    return {
        "articulos": [(art_cod, "ALIMENTO TEST", Decimal(base), False, False, "UNIDAD", None if promo is None else Decimal(promo))],
        "stock_fisico": [(art_cod, "ALIMENTO TEST", False, Decimal("50"))],
    }


def test_con_promo_vigente_se_cobra_el_precio_promocional(monkeypatch):
    escenario = escenario_precio(100000, promo=80000)
    r = correr_caso(monkeypatch, escenario, [item(6000, 2)])    # el navegador manda 80000 (el precio que vio)
    assert r["ok"] is True and r["conn"].committed is True
    assert r["cursor"].precios_insertados == [Decimal("80000")]


def test_sin_promo_se_cobra_el_precio_de_lista(monkeypatch):
    r = correr_caso(monkeypatch, escenario_precio(100000), [item(6000, 1)])
    assert r["ok"] is True
    assert r["cursor"].precios_insertados == [Decimal("100000")]


@pytest.mark.parametrize("promo", [100000, 120000])
def test_promo_que_no_rebaja_se_ignora_y_se_cobra_la_lista(monkeypatch, promo):
    r = correr_caso(monkeypatch, escenario_precio(100000, promo=promo), [item(6000, 1)])
    assert r["ok"] is True
    assert r["cursor"].precios_insertados == [Decimal("100000")]


def test_la_consulta_del_pedido_usa_la_misma_promo_que_el_catalogo(monkeypatch):
    r = correr_caso(monkeypatch, escenario_precio(100000, promo=80000), [item(6000, 1)])
    sql_articulos = next(q for q in r["cursor"].consultas if "unidad_medida" in q and "FROM articulos a" in q)
    assert " ".join(items.SQL_PROMO_LATERAL.split()) in sql_articulos
    assert "promo.precio_promo" in sql_articulos


def test_carrito_con_precio_de_lista_pero_promo_ya_vigente_da_409_y_no_escribe(monkeypatch):
    # El cliente agrego el articulo antes de que empezara la promo: su carrito dice 100000.
    r = correr_caso(monkeypatch, escenario_precio(100000, promo=80000), [item(6000, 1, precio=100000)])
    assert r["ok"] is False and r["status"] == 409
    assert r["detail"]["codigo"] == "PRECIOS_CAMBIARON"
    assert r["detail"]["precios"] == [
        {"id": 6000, "precio": 80000, "precio_original": 100000, "descuento_porcentaje": 20}
    ]
    assert r["cursor"].se_inserto_cabecera is False and r["cursor"].se_inserto_detalle == 0
    assert r["conn"].committed is False and r["conn"].rolled_back is True


def test_carrito_con_precio_promocional_pero_promo_ya_vencida_da_409_con_el_precio_de_lista(monkeypatch):
    # Promo terminada mientras el cliente compraba: su carrito dice 80000, ahora vale 100000.
    r = correr_caso(monkeypatch, escenario_precio(100000), [item(6000, 1, precio=80000)])
    assert r["ok"] is False and r["status"] == 409
    assert r["detail"]["precios"] == [
        {"id": 6000, "precio": 100000, "precio_original": None, "descuento_porcentaje": None}
    ]
    assert r["cursor"].se_inserto_cabecera is False and r["conn"].committed is False


def test_el_409_lista_solo_los_articulos_cuyo_precio_cambio(monkeypatch):
    escenario = {
        "articulos": [
            (6000, "CON PROMO", Decimal("100000"), False, False, "UNIDAD", Decimal("90000")),
            (6001, "SIN CAMBIOS", Decimal("5000"), False, False, "UNIDAD", None),
            (6002, "TAMBIEN CAMBIO", Decimal("3000"), False, False, "UNIDAD", Decimal("2000")),
        ],
        "stock_fisico": [(a, "X", False, Decimal("50")) for a in (6000, 6001, 6002)],
    }
    r = correr_caso(monkeypatch, escenario, [
        item(6000, 1, precio=100000),   # desactualizado
        item(6001, 1),                  # correcto
        item(6002, 1, precio=3000),     # desactualizado
    ])
    assert r["status"] == 409
    assert [p["id"] for p in r["detail"]["precios"]] == [6000, 6002]
    assert r["detail"]["precios"][1]["descuento_porcentaje"] == 33


@pytest.mark.parametrize("enviado, debe_pasar", [
    (80000, True), (80000.0, True), (80000.4, True),     # dentro de la tolerancia de medio guarani
    (80001, False), (79999, False), (100000, False),
])
def test_tolerancia_al_comparar_el_precio_del_carrito(monkeypatch, enviado, debe_pasar):
    r = correr_caso(monkeypatch, escenario_precio(100000, promo=80000), [item(6000, 1, precio=enviado)])
    assert r["ok"] is debe_pasar
    if not debe_pasar:
        assert r["status"] == 409


def test_el_chequeo_de_precio_va_antes_que_el_de_stock(monkeypatch):
    escenario = escenario_precio(100000, promo=80000)
    r = correr_caso(monkeypatch, escenario, [item(6000, 9999, precio=100000)])   # stock insuficiente Y precio viejo
    assert r["status"] == 409


def test_un_articulo_no_disponible_sigue_dando_400_antes_que_el_chequeo_de_precio(monkeypatch):
    r = correr_caso(monkeypatch, escenario_precio(100000), [item(777, 1, precio=5)])
    assert r["status"] == 400 and "no está disponible" in r["detail"]


def test_un_kit_con_promo_cobra_el_precio_promocional_del_kit(monkeypatch):
    escenario = {
        "articulos": [(7000, "KIT CON PROMO", Decimal("70000"), True, False, "BOLSA", Decimal("63000"))],
        "componentes": [(7000, 5000, Decimal("25.000"))],
        "stock_fisico": [(5000, "MAIZ", False, Decimal("100.000"))],
    }
    r = correr_caso(monkeypatch, escenario, [item(7000, 2)])
    assert r["ok"] is True
    assert r["cursor"].precios_insertados == [Decimal("63000")]
    assert r["cursor"].se_inserto_componentes == 1


def test_el_precio_que_manda_el_navegador_nunca_se_usa_para_cobrar(monkeypatch):
    # Aunque mande un precio "dentro de tolerancia", lo que se guarda es el oficial.
    r = correr_caso(monkeypatch, escenario_precio(100000, promo=80000), [item(6000, 1, precio=80000.4)])
    assert r["ok"] is True
    assert r["cursor"].precios_insertados == [Decimal("80000")]
