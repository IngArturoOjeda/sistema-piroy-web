"""
Regla web: KG, LITROS y METROS se venden en cantidades enteras.

Ejercita confirmar_pedido() real con un cursor simulado. No escribe en ninguna base.
Se retiro la parte que hacia POST y DELETE contra Render: la cobertura queda aca.
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
        self.cabecera = False
        self.detalle = 0

    def execute(self, sql, params=None):
        q = " ".join(sql.split())
        if q.split(" ", 1)[0].upper() in ("UPDATE", "DELETE", "DROP", "CREATE", "ALTER", "TRUNCATE"):
            raise AssertionError("escritura inesperada en test unit")
        if "INSERT INTO pedido_cabecera" in q:
            self.cabecera = True
            self._resultado = None
        elif "INSERT INTO pedido_detalle_componentes" in q:
            self._resultado = None
        elif "INSERT INTO pedido_detalle " in q:
            self.detalle += 1
            self._resultado = None
        elif "FROM articulos_kit" in q:
            self._resultado = []
        elif "LEFT JOIN stock s" in q and "FROM articulos a" in q:
            self._resultado = self.escenario.get("stock_fisico", [])
        elif "unidad_medida" in q:
            self._resultado = self.escenario["articulos"]
        else:
            raise AssertionError(q[:80])

    def executemany(self, sql, filas):
        pass

    def fetchall(self):
        return self._resultado or []

    def fetchone(self):
        return (999,)

    def close(self):
        pass


class FakeConn:
    def __init__(self, cursor):
        self._cursor = cursor
        self.commit_hecho = False

    def cursor(self):
        return self._cursor

    def commit(self):
        self.commit_hecho = True

    def rollback(self):
        pass

    def close(self):
        pass


def correr_mock(monkeypatch, unidad, fraccionable, cantidad, stock):
    escenario = {
        "articulos": [(700001, "ARTICULO TEST", Decimal("1000"), False, fraccionable, unidad)],
        "stock_fisico": [(700001, "ARTICULO TEST", False, Decimal(stock))],
    }
    cursor = FakeCursor(escenario)
    conn = FakeConn(cursor)
    monkeypatch.setattr(items, "obtener_conexion_postgres", lambda: conn)
    pedido = PedidoEntrada(
        cliente_nombre="T", cliente_direccion="T", cliente_telefono="0981000000",
        productos=[{"id": 700001, "nombre": "x", "precio": 1, "cantidad": cantidad}],
    )
    try:
        items.confirmar_pedido(pedido)
        return {"ok": True, "cabecera": cursor.cabecera, "commit": conn.commit_hecho}
    except HTTPException as e:
        return {"ok": False, "status": e.status_code, "cabecera": cursor.cabecera, "commit": conn.commit_hecho}


@pytest.mark.parametrize(
    "unidad, fraccionable, cantidad, stock, valido",
    [
        ("KG", True, "2.000", "10", True),
        ("KG", True, "1", "10", True),
        ("KG", True, "0.500", "10", False),
        ("KG", True, "1.250", "10", False),
        ("LITROS", True, "3", "10", True),
        ("LITROS", True, "2.5", "10", False),
        ("METROS", True, "1.5", "10", False),
        ("UNIDAD", False, "2.5", "10", False),  # regla existente, no web-entera
    ],
)
def test_cantidad_web_entera(monkeypatch, unidad, fraccionable, cantidad, stock, valido):
    r = correr_mock(monkeypatch, unidad, fraccionable, Decimal(cantidad), stock)
    if valido:
        assert r["ok"] and r["commit"]
    else:
        assert r["ok"] is False and r["status"] == 400
        assert r["commit"] is False and r["cabecera"] is False


def test_stock_decimal_3_700_permite_3_kg(monkeypatch):
    r = correr_mock(monkeypatch, "KG", True, Decimal("3"), "3.700")
    assert r["ok"] is True


def test_stock_decimal_3_700_no_permite_4_kg(monkeypatch):
    r = correr_mock(monkeypatch, "KG", True, Decimal("4"), "3.700")
    assert r["ok"] is False and r["status"] == 400
    assert r["cabecera"] is False
