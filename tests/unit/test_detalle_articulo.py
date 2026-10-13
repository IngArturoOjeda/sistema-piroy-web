"""
Detalle publico de un articulo: GET /api/articulos/{art_cod} y pagina /producto/{ref}.

Cursor y conexion simulados: no toca ninguna base.
"""
import asyncio
import inspect

import pytest
from fastapi import HTTPException

from backend.app import main
from backend.app.routers import items


class FakeCursor:
    def __init__(self, fila=None, falla=False):
        self.fila = fila
        self.falla = falla
        self.consultas = []

    def execute(self, sql, params=None):
        if self.falla:
            raise RuntimeError("fallo simulado")
        self.consultas.append((" ".join(sql.split()), params))

    def fetchone(self):
        return self.fila

    def close(self):
        pass


class FakeConn:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor

    def close(self):
        pass


@pytest.fixture
def base(monkeypatch):
    def armar(fila=None, falla=False):
        cursor = FakeCursor(fila, falla)
        monkeypatch.setattr(items, "obtener_conexion_postgres", lambda: FakeConn(cursor))
        return cursor
    return armar


# art_cod, nombre, precio, tipo, foto, stock, unidad_venta, fraccionable, precio_promo, descripcion
FILA = (1000, "BOTINA EN CUERO Nº 38", 80000, "CALZADOS",
        "https://res.cloudinary.com/x/1000.jpg", 3, "UNIDAD", False, None, "Botina de trabajo.\nSuela antideslizante.")


def test_devuelve_los_mismos_campos_del_catalogo_mas_la_descripcion(base):
    base(FILA)
    r = items.trae_detalle_articulo(1000)
    assert r == {
        "id": 1000,
        "nombre": "BOTINA EN CUERO Nº 38",
        "precio": 80000,
        "precio_original": None,
        "descuento_porcentaje": None,
        "tipo": "CALZADOS",
        "imagen": "https://res.cloudinary.com/x/1000.jpg",
        "stock_disponible": 3.0,
        "unidad_venta": "UNIDAD",
        "fraccionable": False,
        "descripcion": "Botina de trabajo.\nSuela antideslizante.",
    }


@pytest.mark.parametrize("valor", [None, "", "   \n "])
def test_descripcion_vacia_se_devuelve_como_null(base, valor):
    base(FILA[:9] + (valor,))
    assert items.trae_detalle_articulo(1000)["descripcion"] is None


def test_articulo_inexistente_o_no_publicado_es_404(base):
    base(None)
    with pytest.raises(HTTPException) as e:
        items.trae_detalle_articulo(999999)
    assert e.value.status_code == 404


def test_solo_consulta_articulos_publicados_y_filtra_por_codigo(base):
    cursor = base(FILA)
    items.trae_detalle_articulo(1000)
    sql, params = cursor.consultas[0]
    assert params == (1000,)
    assert "a.art_cod = %s" in sql
    for condicion in ("a.art_estado = 'S'", "a.llevar_web = TRUE", "a.mostrar_web = TRUE"):
        assert condicion in sql
    # a diferencia del catalogo, acepta COMBO (tiene su propia seccion y detalle): no los excluye
    assert "IS DISTINCT FROM 'COMBO'" not in sql
    # el stock de un kit se calcula igual que en el catalogo
    assert "LEFT JOIN LATERAL" in sql and "a.descripcion" in sql


def test_error_de_base_es_500(base):
    base(FILA, falla=True)
    with pytest.raises(HTTPException) as e:
        items.trae_detalle_articulo(1000)
    assert e.value.status_code == 500


def test_codigo_fuera_de_rango_se_rechaza_en_la_ruta():
    por_defecto = inspect.signature(items.trae_detalle_articulo).parameters["art_cod"].default
    limites = {type(m).__name__: m for m in por_defecto.metadata}
    assert limites["Gt"].gt == 0 and limites["Lt"].lt == 10**18


def test_las_rutas_fijas_se_declaran_antes_que_la_de_codigo():
    rutas = [r.path for r in items.router.routes if "GET" in r.methods]
    assert rutas.index("/articulos/presentaciones") < rutas.index("/articulos/{art_cod}")
    assert rutas.index("/articulos/combos") < rutas.index("/articulos/{art_cod}")


def test_pagina_de_producto_sirve_el_index():
    respuesta = asyncio.run(main.read_producto("1000-botina-en-cuero"))
    assert str(respuesta.path).replace("\\", "/").endswith("frontend/index.html")
