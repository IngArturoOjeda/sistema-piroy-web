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

        if "INSERT INTO pedido_cabecera" in sql_n:
            self.se_inserto_cabecera = True
            self._resultado = None
        elif "INSERT INTO pedido_detalle_componentes" in sql_n:
            self.se_inserto_componentes += 1
            self._resultado = None
        elif "INSERT INTO pedido_detalle " in sql_n:
            self.se_inserto_detalle += 1
            self._resultado = None
        elif "FROM articulos_kit" in sql_n:
            self._resultado = self.escenario.get("componentes", [])
        elif "LEFT JOIN stock s" in sql_n and "FROM articulos a" in sql_n:
            self._resultado = self.escenario.get("stock_fisico", [])
        elif "FROM articulos a" in sql_n and "unidad_medida" in sql_n:
            self._resultado = self.escenario.get("articulos", [])
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


def correr_caso(monkeypatch, escenario, productos):
    cursor = FakeCursor(escenario)
    conn = FakeConn(cursor)
    monkeypatch.setattr(items, "obtener_conexion_postgres", lambda: conn)

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


def item(id_, cantidad):
    return {"id": id_, "nombre": "x", "precio": 1, "cantidad": cantidad}


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
