"""
Panel de imagenes: lista de articulos con filtro por tipo, busqueda por texto y paginacion.
Cursor y conexion simulados: no toca ninguna base.
"""
import inspect

import pytest

from backend.app import sql_catalogo
from backend.app.routers import admin, admin_auth


def normalizar(sql):
    return " ".join(sql.split())


class Cursor:
    def __init__(self, filas=()):
        self.filas = list(filas)
        self.consultas = []

    def execute(self, sql, params=()):
        self.consultas.append((normalizar(sql), tuple(params)))

    def fetchall(self):
        return self.filas

    def close(self):
        pass


class Conn:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor

    def close(self):
        pass


@pytest.fixture
def base(monkeypatch):
    def armar(filas=()):
        cursor = Cursor(filas)
        monkeypatch.setattr(admin, "obtener_conexion_postgres", lambda: Conn(cursor))
        return cursor
    return armar


def consulta(base, **kwargs):
    cursor = base()
    admin.buscar_articulos_admin(**kwargs)
    return cursor.consultas[0]


def test_sin_filtros_lista_todos_los_articulos_de_a_30(base):
    sql, params = consulta(base)
    assert params == (30, 0)
    assert "a.tipoart_cod = " not in sql and "ILIKE" not in sql      # sin filtro de tipo ni de texto
    assert "ORDER BY a.art_cod LIMIT %s OFFSET %s" in sql
    assert "a.art_estado = 'S'" not in sql                           # el panel muestra tambien los no publicados


def test_llamarla_sin_argumentos_usa_los_valores_por_defecto():
    # los valores por defecto son reales (no objetos Query), asi que se puede llamar a la funcion directamente
    firma = inspect.signature(admin.buscar_articulos_admin).parameters
    assert firma["buscar"].default == "" and firma["tipo"].default is None
    assert firma["pagina"].default == 1 and firma["limite"].default == 30


def test_filtrar_por_tipo_usa_el_tipo_efectivo(base):
    sql, params = consulta(base, tipo=1)
    assert normalizar(sql_catalogo.SQL_TIPO_EFECTIVO) in sql        # un kit cuenta en el tipo de su componente
    assert "AND t.tipoart_cod = %s" in sql
    assert params == (1, 30, 0)


def test_la_busqueda_por_texto_actua_dentro_del_tipo_elegido(base):
    sql, params = consulta(base, buscar="  pronto ", tipo=1)
    assert "AND t.tipoart_cod = %s" in sql and "AND a.art_nombre ILIKE %s" in sql
    assert params == (1, "%pronto%", 30, 0)


def test_buscar_un_numero_busca_por_nombre_o_por_codigo_agrupado(base):
    sql, params = consulta(base, buscar="1000", tipo=5)
    assert "AND (a.art_nombre ILIKE %s OR a.art_cod = %s)" in sql   # los parentesis protegen al filtro de tipo
    assert params == (5, "%1000%", 1000, 30, 0)


def test_un_numero_demasiado_grande_no_se_busca_como_codigo(base):
    sql, params = consulta(base, buscar="9" * 30)
    assert "a.art_cod = %s" not in sql                              # no cabe en un bigint: se busca solo por nombre
    assert params == ("%" + "9" * 30 + "%", 30, 0)


@pytest.mark.parametrize("pagina, limite, esperado", [(1, 30, (30, 0)), (3, 30, (30, 60)), (2, 10, (10, 10))])
def test_paginacion(base, pagina, limite, esperado):
    _, params = consulta(base, pagina=pagina, limite=limite)
    assert params == esperado


def test_la_respuesta_trae_el_tipo_efectivo_y_los_datos_del_panel(base):
    fila = (251188, "PRONTO DOG X25KG", 160000, "BALANCEADOS", None, "S", True, True, "Texto")
    base([fila])
    r = admin.buscar_articulos_admin()
    assert r == [{"art_cod": 251188, "art_nombre": "PRONTO DOG X25KG", "art_preciobase": 160000,
                  "tipoart_desc": "BALANCEADOS", "art_foto": None, "art_estado": "S", "llevar_web": True,
                  "mostrar_web": True, "descripcion": "Texto"}]


def test_los_limites_de_los_parametros_se_validan_en_la_ruta():
    firma = inspect.signature(admin.buscar_articulos_admin).parameters

    def limites(nombre):
        meta = firma[nombre].annotation.__metadata__[0].metadata
        return {type(m).__name__: m for m in meta}

    assert limites("pagina")["Ge"].ge == 1
    assert limites("limite")["Ge"].ge == 1 and limites("limite")["Le"].le == 100
    assert limites("tipo")["Gt"].gt == 0 and limites("tipo")["Lt"].lt == 2**31


def test_la_ruta_sigue_exigiendo_sesion():
    ruta = next(r for r in admin.router.routes if r.path == "/admin/articulos" and "GET" in r.methods)
    assert any(d.call is admin_auth.verificar_admin for d in ruta.dependant.dependencies)
