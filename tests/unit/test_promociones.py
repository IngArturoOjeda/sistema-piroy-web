"""
Promociones: precio promocional vigente, porcentaje de descuento y listado.

Cursor y conexion simulados: no toca ninguna base. El SQL se verifica como texto
(las condiciones de vigencia viven en SQL); la evaluacion real contra PostgreSQL se
comprueba aparte, dentro de una transaccion con rollback.
"""
import inspect
from decimal import Decimal

import pytest

from backend.app.routers import items
from backend.app.sql_catalogo import SQL_TIPO_VISIBLE

PALABRAS_DE_ESCRITURA = ("INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "ALTER", "TRUNCATE")


def normalizar(sql):
    return " ".join(sql.split())


class FakeCursor:
    def __init__(self, filas):
        self.filas = filas
        self.ejecuciones = []

    def execute(self, sql, params=()):
        q = normalizar(sql)
        assert q.split(" ", 1)[0].upper() not in PALABRAS_DE_ESCRITURA, "escritura en test mock"
        self.ejecuciones.append((q, tuple(params)))

    def fetchall(self):
        return self.filas

    def fetchone(self):
        return self.filas[0] if self.filas else None

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
    def armar(filas):
        cursor = FakeCursor(filas)
        monkeypatch.setattr(items, "obtener_conexion_postgres", lambda: FakeConn(cursor))
        return cursor
    return armar


# art_cod, nombre, precio_base, tipo, foto, stock, unidad, fraccionable, precio_promo
def fila(precio_base, precio_promo, art_cod=1000):
    return (art_cod, "BOTINA", Decimal(precio_base), "CALZADOS", None, Decimal("3"), "UNIDAD", False,
            None if precio_promo is None else Decimal(precio_promo))


# ---------- calcular_descuento ----------

@pytest.mark.parametrize("base_, promo, esperado", [
    (80000, 68000, 15),          # 15 % exacto
    (100000, 90000, 10),
    (3, 2, 33),                  # 33,33 -> 33
    (3, 1, 67),                  # 66,67 -> 67
    (200, 199, 1),               # 0,5 % -> mitad hacia arriba -> 1
    (1000, 996, None),           # 0,4 % -> 0 -> sin insignia
    (1000, 1000, None),          # no rebaja
    (1000, 1200, None),          # sube de precio: no es promo
    (1000, None, None),          # sin promo
    (0, 0, None),                # precio base invalido
    (None, 500, None),
])
def test_calcular_descuento(base_, promo, esperado):
    b = None if base_ is None else Decimal(base_)
    p = None if promo is None else Decimal(promo)
    assert items.calcular_descuento(b, p) == esperado


def test_calcular_descuento_acepta_enteros_y_decimal():
    assert items.calcular_descuento(80000, 68000) == 15
    assert items.calcular_descuento(Decimal("80000"), Decimal("68000")) == 15


# ---------- formato de respuesta ----------

def test_sin_promo_precio_es_el_base_y_no_hay_precio_original():
    r = items.formatear_articulo_catalogo(fila(80000, None))
    assert r["precio"] == 80000
    assert r["precio_original"] is None and r["descuento_porcentaje"] is None


def test_con_promo_precio_es_el_promocional_y_se_conserva_el_original():
    r = items.formatear_articulo_catalogo(fila(80000, 68000))
    assert r["precio"] == 68000
    assert r["precio_original"] == 80000
    assert r["descuento_porcentaje"] == 15
    assert isinstance(r["precio"], int) and isinstance(r["precio_original"], int)


@pytest.mark.parametrize("promo", [80000, 90000])
def test_promo_que_no_rebaja_se_ignora(promo):
    r = items.formatear_articulo_catalogo(fila(80000, promo))
    assert r["precio"] == 80000
    assert r["precio_original"] is None and r["descuento_porcentaje"] is None


def test_descuento_menor_a_1_porciento_rebaja_el_precio_pero_sin_insignia():
    r = items.formatear_articulo_catalogo(fila(1000, 996))
    assert r["precio"] == 996 and r["precio_original"] == 1000
    assert r["descuento_porcentaje"] is None


# ---------- el SQL de vigencia ----------

def test_sql_promo_vigencia_hora_de_paraguay_fechas_inclusivas_y_precio_menor():
    q = normalizar(items.SQL_PROMO_LATERAL)
    assert "(NOW() AT TIME ZONE 'America/Asuncion')::date BETWEEN p.fec_desde AND p.fec_hasta" in q
    assert "p.art_valor < a.art_preciobase" in q
    assert "MIN(p.art_valor)" in q            # varias promos: gana el precio mas bajo
    assert "p.art_cod = a.art_cod" in q
    assert q.rstrip().endswith("promo ON TRUE")


@pytest.mark.parametrize("funcion, argumentos", [
    (items.trae_articulos, (1, 30, "Todos", None, None)),
    (items.trae_combos, (1, 30)),
    (items.trae_promociones, (1, 30)),
])
def test_todas_las_consultas_de_catalogo_usan_la_promo(base, funcion, argumentos):
    cursor = base([])
    funcion(*argumentos)
    q = cursor.ejecuciones[0][0]
    assert normalizar(items.SQL_PROMO_LATERAL) in q
    assert "promo.precio_promo" in q
    assert normalizar(items.SQL_STOCK_KIT_LATERAL) in q


def test_el_detalle_tambien_usa_la_promo(base):
    cursor = base([fila(80000, 68000) + ("Descripcion",)])
    r = items.trae_detalle_articulo(1000)
    q = cursor.ejecuciones[0][0]
    assert normalizar(items.SQL_PROMO_LATERAL) in q and "promo.precio_promo" in q
    assert r["precio"] == 68000 and r["precio_original"] == 80000 and r["descuento_porcentaje"] == 15
    assert r["descripcion"] == "Descripcion"


# ---------- GET /api/articulos/promociones ----------

def test_promociones_solo_publicados_con_promo_vigente_y_mayor_descuento_primero(base):
    cursor = base([])
    items.trae_promociones(1, 30)
    q, params = cursor.ejecuciones[0]
    for condicion in ("a.art_estado = 'S'", "a.llevar_web = TRUE", "a.mostrar_web = TRUE",
                      "promo.precio_promo IS NOT NULL"):
        assert condicion in q
    assert "ORDER BY (a.art_preciobase - promo.precio_promo) / a.art_preciobase DESC, a.art_cod" in q
    assert params == (30, 0)


def test_promociones_incluye_combos_y_kits(base):
    cursor = base([])
    items.trae_promociones(1, 30)
    q = cursor.ejecuciones[0][0]
    # no excluye ningun tipo de kit: entran normales, PRESENTACION y COMBO
    assert "IS DISTINCT FROM 'COMBO'" not in q
    assert "a.tipo_kit = 'COMBO'" not in q.replace(normalizar(SQL_TIPO_VISIBLE), "")


@pytest.mark.parametrize("pagina, limite, esperado", [(1, 30, (30, 0)), (3, 30, (30, 60)), (2, 10, (10, 10))])
def test_promociones_paginacion(base, pagina, limite, esperado):
    cursor = base([])
    items.trae_promociones(pagina, limite)
    assert cursor.ejecuciones[0][1] == esperado


def test_promociones_devuelve_el_formato_del_catalogo(base):
    base([fila(80000, 68000, 1000), fila(50000, 45000, 1001)])
    lote = items.trae_promociones(1, 30)
    assert [a["id"] for a in lote] == [1000, 1001]
    assert lote[0]["precio"] == 68000 and lote[0]["descuento_porcentaje"] == 15
    assert lote[1]["descuento_porcentaje"] == 10


def test_promociones_limites_de_los_parametros():
    params = inspect.signature(items.trae_promociones).parameters
    pagina = {type(m).__name__: m for m in params["pagina"].default.metadata}
    limite = {type(m).__name__: m for m in params["limite"].default.metadata}
    assert pagina["Ge"].ge == 1
    assert limite["Ge"].ge == 1 and limite["Le"].le == 100


def test_promociones_se_declara_antes_que_la_ruta_de_codigo():
    rutas = [r.path for r in items.router.routes if "GET" in r.methods]
    assert rutas.index("/articulos/promociones") < rutas.index("/articulos/{art_cod}")


def test_error_de_base_en_promociones_es_500(monkeypatch):
    from fastapi import HTTPException

    class Roto(FakeCursor):
        def execute(self, *a, **k):
            raise RuntimeError("fallo simulado")

    monkeypatch.setattr(items, "obtener_conexion_postgres", lambda: FakeConn(Roto([])))
    with pytest.raises(HTTPException) as e:
        items.trae_promociones(1, 30)
    assert e.value.status_code == 500


# ---------- GET /api/articulos/?sin_promocion=true (la portada "Todos" no repite las promociones) ----------

def test_catalogo_sin_promocion_excluye_los_articulos_con_promo_vigente(base):
    cursor = base([])
    items.trae_articulos(1, 30, "Todos", None, None, True)
    q, params = cursor.ejecuciones[0]
    assert "AND promo.precio_promo IS NULL" in q
    assert params == (30, 0)                       # el filtro no agrega parametros
    assert normalizar(items.SQL_PROMO_LATERAL) in q


@pytest.mark.parametrize("valor", [False, None])
def test_catalogo_por_defecto_incluye_los_articulos_en_promocion(base, valor):
    cursor = base([])
    items.trae_articulos(1, 30, "Todos", None, None, valor)
    assert "promo.precio_promo IS NULL" not in cursor.ejecuciones[0][0]


def test_llamar_sin_el_parametro_no_activa_el_filtro(base):
    # Sin FastAPI el valor por defecto es un objeto Query (truthy): no debe contarse como True
    cursor = base([])
    items.trae_articulos(1, 30, "Todos", None, None)
    assert "promo.precio_promo IS NULL" not in cursor.ejecuciones[0][0]


def test_sin_promocion_se_combina_con_la_categoria_y_la_paginacion(base):
    cursor = base([])
    items.trae_articulos(3, 30, "MERCERIAS", None, None, True)
    q, params = cursor.ejecuciones[0]
    assert "AND t.tipoart_desc = %s" in q and "AND promo.precio_promo IS NULL" in q
    assert params == ("MERCERIAS", 30, 60)


def test_el_parametro_sin_promocion_es_booleano_con_false_por_defecto():
    parametro = inspect.signature(items.trae_articulos).parameters["sin_promocion"]
    assert parametro.default.default is False
