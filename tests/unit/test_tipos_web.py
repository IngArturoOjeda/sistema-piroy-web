"""
Estado de cada tipo de articulo en la web: el menu de categorias, el ocultamiento total en las
consultas publicas y el panel de administracion. Cursor y conexion simulados: no toca ninguna base.
"""
import inspect

import pytest
from fastapi import HTTPException

from backend.app.routers import admin, admin_auth, categories, items
from backend.app.schemas import MostrarWebEntrada


def normalizar(sql):
    return " ".join(sql.split())


class Cursor:
    def __init__(self, filas=(), rowcount=1, falla=False):
        self.filas = list(filas)
        self.rowcount = rowcount
        self.falla = falla
        self.consultas = []

    def execute(self, sql, params=()):
        if self.falla:
            raise RuntimeError("falla simulada")
        self.consultas.append((normalizar(sql), tuple(params)))

    def fetchall(self):
        return self.filas

    def fetchone(self):
        return self.filas[0] if self.filas else None

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


@pytest.fixture
def base(monkeypatch):
    def armar(modulo, **kwargs):
        cursor = Cursor(**kwargs)
        conn = Conn(cursor)
        monkeypatch.setattr(modulo, "obtener_conexion_postgres", lambda: conn)
        return cursor, conn
    return armar


# ---------- menu de categorias ----------

def test_el_menu_solo_trae_tipos_visibles_y_con_articulos(base):
    cursor, _ = base(categories, filas=[(1, "BALANCEADOS"), (1007, "MERCERIAS")])
    r = categories.listar_categorias()
    assert r == [{"id": 1, "nombre": "BALANCEADOS"}, {"id": 1007, "nombre": "MERCERIAS"}]
    q = cursor.consultas[0][0]
    assert "t.mostrar_web = TRUE" in q
    assert normalizar(categories.SQL_TIPO_CON_ARTICULOS) in q
    assert q.endswith("ORDER BY t.tipoart_cod")


def test_un_tipo_con_articulos_es_el_que_tiene_algo_en_su_pagina_de_categoria():
    q = normalizar(categories.SQL_TIPO_CON_ARTICULOS)
    # articulos normales publicados del tipo
    for condicion in ("a.tipoart_cod = t.tipoart_cod", "a.art_estado = 'S'", "a.llevar_web = TRUE",
                      "a.mostrar_web = TRUE", "a.art_kit = FALSE"):
        assert condicion in q
    # o kits PRESENTACION publicados con componentes del tipo (y de un tipo de kit visible)
    for condicion in ("kit.tipo_kit = 'PRESENTACION'", "comp.tipoart_cod = t.tipoart_cod",
                      "kit.mostrar_web = TRUE", "tkit.mostrar_web = TRUE"):
        assert condicion in q
    assert "COMBO" not in q                      # los combos tienen su propia vista


def test_sin_ningun_tipo_visible_el_menu_es_una_lista_vacia_no_un_error(base):
    base(categories, filas=[])
    assert categories.listar_categorias() == []


def test_error_de_base_en_categorias_es_500(base):
    base(categories, falla=True)
    with pytest.raises(HTTPException) as e:
        categories.listar_categorias()
    assert e.value.status_code == 500


# ---------- un tipo oculto oculta tambien sus articulos ----------

def consulta(funcion, base, modulo, *args):
    cursor, _ = base(modulo, filas=[])
    funcion(*args)
    return cursor.consultas[0][0]


@pytest.mark.parametrize("funcion, argumentos", [
    (items.trae_articulos, (1, 30, "Todos", None, None)),
    (items.trae_combos, (1, 30)),
    (items.trae_promociones, (1, 30)),
])
def test_el_catalogo_no_muestra_articulos_de_un_tipo_oculto(base, funcion, argumentos):
    assert "AND t.mostrar_web = TRUE" in consulta(funcion, base, items, *argumentos)


def test_el_detalle_del_articulo_no_se_ve_si_su_tipo_esta_oculto(base):
    cursor, _ = base(items, filas=[])
    with pytest.raises(HTTPException) as e:        # sin filas: 404 "no disponible"
        items.trae_detalle_articulo(1000)
    assert e.value.status_code == 404
    assert "AND t.mostrar_web = TRUE" in cursor.consultas[0][0]


def test_las_formas_de_compra_respetan_el_tipo_oculto(base):
    cursor, _ = base(items, filas=[("UNIDAD",)])
    items.trae_presentaciones("MERCERIAS")
    normales, kits = cursor.consultas[0][0], cursor.consultas[1][0]
    assert "AND t.mostrar_web = TRUE" in normales
    assert "tkit.mostrar_web = TRUE" in kits and "tcomp.mostrar_web = TRUE" in kits


def test_los_kits_por_presentacion_exigen_el_tipo_del_componente_visible(base):
    cursor, _ = base(items, filas=[])
    items.trae_articulos(1, 30, "MERCERIAS", None, "KIT")
    assert "tcomp.mostrar_web = TRUE" in cursor.consultas[0][0]


def test_el_pedido_rechaza_articulos_de_un_tipo_oculto():
    fuente = inspect.getsource(items.confirmar_pedido)
    assert "INNER JOIN tipo_articulo t ON t.tipoart_cod = a.tipoart_cod" in fuente
    assert "AND t.mostrar_web = TRUE" in fuente


# ---------- panel de administracion ----------

def test_las_rutas_de_tipos_exigen_sesion():
    rutas = {(r.path, tuple(sorted(r.methods))): r for r in admin.router.routes if "/tipos" in r.path}
    assert set(rutas) == {("/admin/tipos", ("GET",)), ("/admin/tipos/{tipoart_cod}", ("PATCH",))}
    for ruta in rutas.values():
        assert any(d.call is admin_auth.verificar_admin for d in ruta.dependant.dependencies)


def test_el_panel_lista_cada_tipo_con_su_estado_y_si_aparece_en_el_menu(base):
    filas = [
        (1, "BALANCEADOS", True, 1, True),     # visible y con articulos: aparece en el menu
        (6028, "CALZADOS", True, 0, False),    # visible pero sin articulos: no aparece
        (1007, "MERCERIAS", False, 5, True),   # con articulos pero oculto por el administrador
    ]
    cursor, _ = base(admin, filas=filas)
    r = admin.listar_tipos_admin()
    assert [(t["tipoart_desc"], t["mostrar_web"], t["articulos_publicados"], t["en_menu"]) for t in r] == [
        ("BALANCEADOS", True, 1, True), ("CALZADOS", True, 0, False), ("MERCERIAS", False, 5, False)]
    q = cursor.consultas[0][0]
    assert normalizar(categories.SQL_TIPO_CON_ARTICULOS) in q and "ORDER BY t.tipoart_desc" in q


def test_ocultar_un_tipo_guarda_y_confirma(base):
    cursor, conn = base(admin, rowcount=1)
    r = admin.actualizar_mostrar_web_tipo(MostrarWebEntrada(mostrar_web=False), 1007)
    assert r == {"status": "ok", "tipoart_cod": 1007, "mostrar_web": False}
    assert cursor.consultas[0] == ("UPDATE tipo_articulo SET mostrar_web = %s WHERE tipoart_cod = %s", (False, 1007))
    assert conn.commits == 1


def test_un_tipo_inexistente_es_404_sin_confirmar(base):
    _, conn = base(admin, rowcount=0)
    with pytest.raises(HTTPException) as e:
        admin.actualizar_mostrar_web_tipo(MostrarWebEntrada(mostrar_web=True), 999999)
    assert e.value.status_code == 404 and conn.commits == 0 and conn.rollbacks == 1


def test_error_de_base_al_cambiar_un_tipo_es_500_con_rollback(base):
    _, conn = base(admin, falla=True)
    with pytest.raises(HTTPException) as e:
        admin.actualizar_mostrar_web_tipo(MostrarWebEntrada(mostrar_web=True), 1)
    assert e.value.status_code == 500 and conn.rollbacks == 1


def test_el_codigo_de_tipo_se_valida_en_la_ruta():
    por_defecto = inspect.signature(admin.actualizar_mostrar_web_tipo).parameters["tipoart_cod"].default
    limites = {type(m).__name__: m for m in por_defecto.metadata}
    assert limites["Gt"].gt == 0 and limites["Lt"].lt == 2**31
