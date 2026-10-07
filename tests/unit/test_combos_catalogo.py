"""
Suite mock de COMBOS y catalogo general.

Ejecuta las funciones reales trae_combos() y trae_articulos() de
backend/app/routers/items.py con la conexion reemplazada por un cursor simulado:
- el SQL se captura y se verifica que contenga los predicados esperados;
- el cursor simulado respeta LIMIT/OFFSET para probar paginacion;
- cualquier sentencia de escritura falla el test.

Limitacion: los WHERE y el calculo de stock viven en SQL. Esta suite verifica el
texto del SQL y que los valores se propaguen, no que PostgreSQL los evalue.
Esa parte la cubre tests/integracion_lectura (solo lectura).
"""
from decimal import Decimal

import pytest
from fastapi import HTTPException

from backend.app.routers import items

PALABRAS_DE_ESCRITURA = ("INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "ALTER", "TRUNCATE")
CLAVES_ARTICULO = {"id", "nombre", "precio", "tipo", "imagen", "stock_disponible", "unidad_venta", "fraccionable"}
PREDICADO_COMBO_CATALOGO = "AND a.tipo_kit IS DISTINCT FROM 'COMBO'"
PREDICADO_COMBO_SQL = (
    "a.art_kit = TRUE", "a.tipo_kit = 'COMBO'", "a.art_estado = 'S'",
    "a.llevar_web = TRUE", "a.mostrar_web = TRUE",
)


def normalizar(sql):
    return " ".join(sql.split())


class FakeCursor:
    """Devuelve filas simuladas. Si la consulta pagina (LIMIT %s OFFSET %s), recorta segun esos parametros."""

    def __init__(self, filas):
        self.filas = filas
        self.ejecuciones = []
        self._resultado = []

    def execute(self, sql, params=()):
        q = normalizar(sql)
        if q.split(" ", 1)[0].upper() in PALABRAS_DE_ESCRITURA:
            raise AssertionError(f"escritura detectada en test mock: {q[:60]}")
        params = tuple(params)
        self.ejecuciones.append((q, params))
        if "LIMIT %s OFFSET %s" in q:
            limite, offset = params[-2], params[-1]
            self._resultado = self.filas[offset:offset + limite]
        else:
            self._resultado = list(self.filas)

    def fetchall(self):
        return self._resultado

    def close(self):
        pass


class FakeConn:
    def __init__(self, cursor):
        self._cursor = cursor
        self.usada = False

    def cursor(self):
        self.usada = True
        return self._cursor

    def commit(self):
        raise AssertionError("commit inesperado en test mock")

    def close(self):
        pass


def fila(art_cod, tipo, stock, unidad="BOLSA", fraccionable=False, foto=None, precio=Decimal("5000")):
    # Orden de columnas de las consultas: art_cod, nombre, precio, tipo, foto, stock, unidad, fraccionable
    return (art_cod, f"ARTICULO {art_cod}", precio, tipo, foto, stock, unidad, fraccionable)


# Datos de prueba con IDs ficticios (900xxx y 910xxx). No existen en produccion.
COMBOS = [fila(900000 + i, "KIT", Decimal("3.000")) for i in range(1, 36)]
ARTICULOS_NORMALES = [fila(910000 + i, "MERCERIAS", Decimal("12.000"), unidad="UNIDAD") for i in range(1, 36)]


@pytest.fixture
def correr(monkeypatch):
    """Ejecuta una funcion del router con filas simuladas. Devuelve (resultado, cursor, conexion)."""
    def _correr(funcion, filas, *args):
        cursor = FakeCursor(filas)
        conn = FakeConn(cursor)
        monkeypatch.setattr(items, "obtener_conexion_postgres", lambda: conn)
        resultado = funcion(*args)
        return resultado, cursor, conn
    return _correr


# ---------- 1. /combos: filtros SQL ----------

def test_combos_sql_contiene_predicados_de_combo_publicado(correr):
    _, cur, _ = correr(items.trae_combos, COMBOS, 1, 30)
    q = cur.ejecuciones[0][0]
    for predicado in PREDICADO_COMBO_SQL:
        assert predicado in q, f"falta {predicado}"


def test_combos_sql_no_menciona_presentaciones_ni_normales(correr):
    _, cur, _ = correr(items.trae_combos, COMBOS, 1, 30)
    q = cur.ejecuciones[0][0]
    assert "'PRESENTACION'" not in q
    assert "a.art_kit = FALSE" not in q


def test_combos_sql_usa_stock_derivado_de_componentes(correr):
    _, cur, _ = correr(items.trae_combos, COMBOS, 1, 30)
    q = cur.ejecuciones[0][0]
    assert normalizar(items.SQL_STOCK_KIT_LATERAL) in q
    assert "WHEN a.art_kit THEN COALESCE(kit.stock_disponible, 0)" in q


# ---------- 2. /combos: paginacion ----------

@pytest.mark.parametrize("pagina, limite, esperado", [(1, 30, (30, 0)), (3, 30, (30, 60)), (2, 10, (10, 10))])
def test_combos_params_de_paginacion(correr, pagina, limite, esperado):
    _, cur, _ = correr(items.trae_combos, COMBOS, pagina, limite)
    assert cur.ejecuciones[0][1] == esperado


def test_combos_paginas_de_30_reparten_todo_sin_repetidos(correr):
    ids, tamanos = [], []
    for pagina in (1, 2, 3):
        lote, _, _ = correr(items.trae_combos, COMBOS, pagina, 30)
        tamanos.append(len(lote))
        ids += [a["id"] for a in lote]
    assert tamanos == [30, 5, 0]
    assert sorted(ids) == sorted(a[0] for a in COMBOS)
    assert len(ids) == len(set(ids))


def test_combos_paginas_de_10(correr):
    tamanos = []
    for pagina in (1, 2, 3, 4):
        lote, _, _ = correr(items.trae_combos, COMBOS, pagina, 10)
        tamanos.append(len(lote))
    assert tamanos == [10, 10, 10, 5]


# ---------- 3. forma de respuesta ----------

def test_combos_forma_de_respuesta(correr):
    lote, _, _ = correr(items.trae_combos, COMBOS, 1, 30)
    assert set(lote[0].keys()) == CLAVES_ARTICULO
    assert isinstance(lote[0]["id"], int)
    assert isinstance(lote[0]["precio"], int)
    assert isinstance(lote[0]["stock_disponible"], float)
    assert isinstance(lote[0]["fraccionable"], bool)
    assert lote[0]["imagen"] == items.IMAGEN_SIN_FOTO


def test_combos_y_catalogo_tienen_las_mismas_claves(correr):
    combos, _, _ = correr(items.trae_combos, COMBOS, 1, 30)
    catalogo, _, _ = correr(items.trae_articulos, ARTICULOS_NORMALES, 1, 30, "MERCERIAS", None, None)
    assert set(combos[0].keys()) == set(catalogo[0].keys())


# ---------- 4. stock_disponible ----------

def test_stock_se_propaga_desde_el_sql(correr):
    filas = [fila(920001, "KIT", Decimal("3.000")), fila(920002, "KIT", Decimal("0"))]
    lote, _, _ = correr(items.trae_combos, filas, 1, 30)
    assert lote[0]["stock_disponible"] == 3.0
    assert lote[1]["stock_disponible"] == 0.0


# ---------- 5. catalogo general ----------

def test_catalogo_todos_excluye_combos_en_sql(correr):
    _, cur, _ = correr(items.trae_articulos, ARTICULOS_NORMALES, 1, 30, "Todos", None, None)
    q, params = cur.ejecuciones[0]
    assert PREDICADO_COMBO_CATALOGO in q
    assert "COMBO" not in str(params)
    assert params == (30, 0)


def test_catalogo_categoria_especifica_excluye_combos(correr):
    _, cur, _ = correr(items.trae_articulos, ARTICULOS_NORMALES, 1, 30, "MERCERIAS", None, None)
    q, params = cur.ejecuciones[0]
    assert PREDICADO_COMBO_CATALOGO in q and "AND t.tipoart_desc = %s" in q
    assert params == ("MERCERIAS", 30, 0)


def test_catalogo_presentacion_normal_excluye_combos_y_filtra_normales(correr):
    _, cur, _ = correr(items.trae_articulos, ARTICULOS_NORMALES, 1, 30, "Todos", None, "NORMAL")
    q = cur.ejecuciones[0][0]
    assert PREDICADO_COMBO_CATALOGO in q
    assert "AND a.art_kit = FALSE" in q


def test_catalogo_sin_presentacion_excluye_combos_sin_filtrar_normales(correr):
    _, cur, _ = correr(items.trae_articulos, ARTICULOS_NORMALES, 1, 30, "Todos", None, None)
    q = cur.ejecuciones[0][0]
    assert PREDICADO_COMBO_CATALOGO in q
    assert "AND a.art_kit = FALSE" not in q


# ---------- 6. presentacion=KIT sin regresion ----------

def test_presentacion_kit_exige_presentacion_y_conserva_exclusion(correr):
    _, cur, _ = correr(items.trae_articulos, COMBOS, 1, 30, "BALANCEADOS", None, "KIT")
    q, params = cur.ejecuciones[0]
    assert "a.tipo_kit = 'PRESENTACION'" in q
    assert PREDICADO_COMBO_CATALOGO in q
    assert params == ("BALANCEADOS", 30, 0)


# ---------- 7. validaciones de KIT ----------

def test_kit_con_categoria_todos_da_400_sin_consultar(monkeypatch):
    cursor = FakeCursor([])
    conn = FakeConn(cursor)
    monkeypatch.setattr(items, "obtener_conexion_postgres", lambda: conn)
    with pytest.raises(HTTPException) as info:
        items.trae_articulos(1, 30, "Todos", None, "KIT")
    assert info.value.status_code == 400
    assert conn.usada is False


def test_kit_con_unidad_da_400_sin_consultar(monkeypatch):
    cursor = FakeCursor([])
    conn = FakeConn(cursor)
    monkeypatch.setattr(items, "obtener_conexion_postgres", lambda: conn)
    with pytest.raises(HTTPException) as info:
        items.trae_articulos(1, 30, "BALANCEADOS", "KG", "KIT")
    assert info.value.status_code == 400
    assert conn.usada is False


# ---------- 8. paginacion del catalogo ----------

def test_catalogo_paginacion(correr):
    tamanos = []
    for pagina in (1, 2):
        lote, _, _ = correr(items.trae_articulos, ARTICULOS_NORMALES, pagina, 30, "Todos", None, None)
        tamanos.append(len(lote))
    assert tamanos == [30, 5]
