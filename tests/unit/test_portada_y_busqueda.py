"""
Portada (GET /api/articulos/portada) y busqueda en el catalogo (parametro `buscar`).
Cursor y conexion simulados: no toca ninguna base; el SQL se verifica como texto y la
evaluacion real contra PostgreSQL se comprueba aparte, en solo lectura.
"""
import inspect
from decimal import Decimal

import pytest
from fastapi import HTTPException

from backend.app import sql_catalogo
from backend.app.routers import items


def normalizar(sql):
    return " ".join(sql.split())


class FakeCursor:
    def __init__(self, filas=()):
        self.filas = list(filas)
        self.ejecuciones = []

    def execute(self, sql, params=()):
        self.ejecuciones.append((normalizar(sql), tuple(params)))

    def fetchall(self):
        return self.filas

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
    def armar(filas=()):
        cursor = FakeCursor(filas)
        monkeypatch.setattr(items, "obtener_conexion_postgres", lambda: FakeConn(cursor))
        return cursor
    return armar


# art_cod, nombre, precio, tipo, foto, stock, unidad, fraccionable, precio_promo, tipo_cod, posicion
def fila(art_cod, tipo, tipo_cod, posicion, foto=None, promo=None):
    return (art_cod, f"ARTICULO {art_cod}", Decimal("5000"), tipo, foto, Decimal("3"), "UNIDAD", False,
            promo, tipo_cod, posicion)


# ---------- portada ----------

def test_la_portada_usa_el_mismo_universo_que_el_catalogo(base):
    cursor = base()
    items.trae_portada()
    q, params = cursor.ejecuciones[0]
    assert params == (8,)
    for fragmento in (sql_catalogo.SQL_TIPO_EFECTIVO, items.SQL_STOCK_KIT_LATERAL, items.SQL_PROMO_LATERAL):
        assert normalizar(fragmento) in q
    for condicion in ("a.art_estado = 'S'", "a.llevar_web = TRUE", "a.mostrar_web = TRUE",
                      f"AND {sql_catalogo.SQL_TIPO_VISIBLE}", "a.tipo_kit IS DISTINCT FROM 'COMBO'"):
        assert condicion in q


def test_la_portada_toma_n_por_categoria_con_los_que_tienen_foto_primero(base):
    cursor = base()
    items.trae_portada(5)
    q, params = cursor.ejecuciones[0]
    assert params == (5,)
    assert "ROW_NUMBER() OVER ( PARTITION BY t.tipoart_cod ORDER BY (NULLIF(a.art_foto, '') IS NULL), a.art_cod )" in q
    assert "WHERE x.posicion <= %s ORDER BY x.tipo_cod, x.posicion" in q


def test_la_portada_agrupa_por_categoria_en_orden_y_con_el_formato_del_catalogo(base):
    base([fila(1, "BALANCEADOS", 1, 1, foto="https://x/1.jpg"), fila(2, "BALANCEADOS", 1, 2),
          fila(10, "PIOLA", 2004, 1, promo=Decimal("4000")), fila(20, "SAL", 2003, 1)])
    r = items.trae_portada()
    assert [c["categoria"] for c in r] == ["BALANCEADOS", "PIOLA", "SAL"]
    assert [[a["id"] for a in c["articulos"]] for c in r] == [[1, 2], [10], [20]]
    assert set(r[0].keys()) == {"categoria", "articulos"}                    # sin campos internos
    assert r[1]["articulos"][0]["precio"] == 4000 and r[1]["articulos"][0]["precio_original"] == 5000
    assert r[0]["articulos"][0]["imagen"] == "https://x/1.jpg"
    assert r[0]["articulos"][1]["imagen"] == items.IMAGEN_SIN_FOTO


def test_la_portada_sin_articulos_es_una_lista_vacia(base):
    base()
    assert items.trae_portada() == []


def test_la_portada_se_declara_antes_que_la_ruta_de_codigo():
    rutas = [r.path for r in items.router.routes if "GET" in r.methods]
    assert rutas.index("/articulos/portada") < rutas.index("/articulos/{art_cod}")


def test_por_categoria_se_valida_en_la_ruta():
    anotacion = inspect.signature(items.trae_portada).parameters["por_categoria"].annotation
    limites = {type(m).__name__: m for m in anotacion.__metadata__[0].metadata}
    assert limites["Ge"].ge == 1 and limites["Le"].le == 24
    assert inspect.signature(items.trae_portada).parameters["por_categoria"].default == 8


def test_error_de_base_en_la_portada_es_500(monkeypatch):
    class Roto(FakeCursor):
        def execute(self, *a, **k):
            raise RuntimeError("falla simulada")

    monkeypatch.setattr(items, "obtener_conexion_postgres", lambda: FakeConn(Roto()))
    with pytest.raises(HTTPException) as e:
        items.trae_portada()
    assert e.value.status_code == 500


# ---------- buscar en el catalogo ----------

def consulta(base, *args):
    cursor = base()
    items.trae_articulos(*args)
    return cursor.ejecuciones[0]


def test_sin_buscar_no_se_filtra_por_texto(base):
    q, params = consulta(base, 1, 30, "Todos", None, None)
    assert "ILIKE" not in q and params == (30, 0)


@pytest.mark.parametrize("texto", ["", "   "])
def test_un_texto_vacio_no_filtra(base, texto):
    q, params = consulta(base, 1, 30, "Todos", None, None, False, texto)
    assert "ILIKE" not in q and params == (30, 0)


def test_buscar_por_nombre(base):
    q, params = consulta(base, 1, 30, "Todos", None, None, False, "  Pronto ")
    assert "AND a.art_nombre ILIKE %s" in q and "a.art_cod = %s" not in q
    assert params == ("%Pronto%", 30, 0)


def test_buscar_un_numero_busca_por_nombre_o_por_codigo_entre_parentesis(base):
    q, params = consulta(base, 1, 30, "Todos", None, None, False, "251188")
    assert "AND (a.art_nombre ILIKE %s OR a.art_cod = %s)" in q
    assert params == ("%251188%", 251188, 30, 0)


def test_un_numero_demasiado_grande_no_se_busca_como_codigo(base):
    q, params = consulta(base, 1, 30, "Todos", None, None, False, "9" * 30)
    assert "a.art_cod = %s" not in q and params == ("%" + "9" * 30 + "%", 30, 0)


@pytest.mark.parametrize("texto", ["²", "①", "12²", "٣"])
def test_caracteres_que_parecen_digitos_pero_no_lo_son_se_buscan_solo_por_nombre(base, texto):
    # str.isdigit() es verdadero para "²" o "①" pero int() falla: antes daba error 500
    q, params = consulta(base, 1, 30, "Todos", None, None, False, texto)
    assert "a.art_cod = %s" not in q and "AND a.art_nombre ILIKE %s" in q
    assert params == (f"%{texto}%", 30, 0)


def test_los_comodines_del_texto_se_escapan(base):
    _, params = consulta(base, 1, 30, "Todos", None, None, False, "100%_x\\")
    assert params[0] == "%100\\%\\_x\\\\%"


def test_buscar_se_combina_con_categoria_unidad_y_paginacion(base):
    q, params = consulta(base, 3, 30, "BALANCEADOS", "BOLSA", None, False, "dog")
    assert "AND t.tipoart_desc = %s" in q and "AND um.uni_nombre = %s" in q and "AND a.art_nombre ILIKE %s" in q
    assert q.index("t.tipoart_desc = %s") < q.index("um.uni_nombre = %s") < q.index("ILIKE %s")   # mismo orden que los parametros
    assert params == ("BALANCEADOS", "BOLSA", "%dog%", 30, 60)


def test_buscar_conserva_las_reglas_de_publicacion(base):
    q, _ = consulta(base, 1, 30, "Todos", None, None, False, "dog")
    for condicion in ("a.art_estado = 'S'", "a.mostrar_web = TRUE", f"AND {sql_catalogo.SQL_TIPO_VISIBLE}",
                      "a.tipo_kit IS DISTINCT FROM 'COMBO'"):
        assert condicion in q


def test_llamar_sin_buscar_no_activa_el_filtro(base):
    # Sin FastAPI el valor por defecto es un objeto Query (truthy): no debe tratarse como texto
    q, _ = consulta(base, 1, 30, "Todos", None, None)
    assert "ILIKE" not in q


def test_buscar_tiene_largo_maximo_en_la_ruta():
    parametro = inspect.signature(items.trae_articulos).parameters["buscar"].default
    limites = {type(m).__name__: m for m in parametro.metadata}
    assert limites["MaxLen"].max_length == 100
