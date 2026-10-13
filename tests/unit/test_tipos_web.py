"""
Tipo efectivo de los articulos, estado de cada tipo en la web (menu, ocultamiento total) y panel de
administracion. Cursor y conexion simulados: no toca ninguna base.

Regla: un kit PRESENTACION (por bolsa, caja...) pertenece al tipo del articulo del que descuenta su stock,
no al tipo "KIT" del sistema local. Un tipo oculto oculta el tipo y sus articulos (salvo los COMBO).
"""
import inspect

import pytest
from fastapi import HTTPException

from backend.app import sql_catalogo
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


# ---------- el tipo efectivo ----------

def test_un_kit_presentacion_toma_el_tipo_de_su_componente():
    q = normalizar(sql_catalogo.SQL_TIPO_EFECTIVO)
    # el componente de un kit PRESENTACION (y solo de esos)
    for parte in ("FROM articulos_kit ak", "JOIN articulos comp ON comp.art_cod = ak.art_cod",
                  "a.art_kit = TRUE", "a.tipo_kit = 'PRESENTACION'", "ak.art_codkit = a.art_cod"):
        assert parte in q
    # el articulo se une al tipo del componente, o al propio si no es un kit PRESENTACION
    assert "INNER JOIN tipo_articulo t ON t.tipoart_cod = COALESCE(tipo_comp.tipoart_cod, a.tipoart_cod)" in q


def test_los_combo_no_dependen_de_la_visibilidad_del_tipo():
    # su tipo ("KIT") es solo un rotulo del sistema local y no una categoria que se pueda ocultar
    assert sql_catalogo.SQL_TIPO_VISIBLE == "(t.mostrar_web = TRUE OR a.tipo_kit = 'COMBO')"


@pytest.mark.parametrize("funcion, argumentos", [
    (items.trae_articulos, (1, 30, "BALANCEADOS", None, None)),
    (items.trae_promociones, (1, 30)),
])
def test_el_catalogo_usa_el_tipo_efectivo_y_oculta_los_tipos_ocultos(base, funcion, argumentos):
    cursor, _ = base(items, filas=[])
    funcion(*argumentos)
    q = cursor.consultas[0][0]
    assert normalizar(sql_catalogo.SQL_TIPO_EFECTIVO) in q
    assert f"AND {sql_catalogo.SQL_TIPO_VISIBLE}" in q


def test_el_detalle_usa_el_tipo_efectivo_y_acepta_combos(base):
    cursor, _ = base(items, filas=[])
    with pytest.raises(HTTPException) as e:        # sin filas: 404 "no disponible"
        items.trae_detalle_articulo(1000)
    assert e.value.status_code == 404
    q = cursor.consultas[0][0]
    assert normalizar(sql_catalogo.SQL_TIPO_EFECTIVO) in q and f"AND {sql_catalogo.SQL_TIPO_VISIBLE}" in q
    assert "IS DISTINCT FROM 'COMBO'" not in q     # el detalle acepta combos


def test_los_combos_no_se_ocultan_con_un_tipo(base):
    cursor, _ = base(items, filas=[])
    items.trae_combos(1, 30)
    q = cursor.consultas[0][0]
    assert "t.mostrar_web" not in q                # el combo no depende de la visibilidad del tipo
    assert "a.tipo_kit = 'COMBO'" in q


def test_el_pedido_rechaza_articulos_de_un_tipo_oculto_usando_el_tipo_efectivo():
    fuente = inspect.getsource(items.confirmar_pedido)
    assert "{SQL_TIPO_EFECTIVO}" in fuente and "AND {SQL_TIPO_VISIBLE}" in fuente


# ---------- formas de compra = unidades de venta (los kits cuentan con su unidad) ----------

def test_las_formas_de_compra_son_las_unidades_de_los_articulos_de_la_categoria(base):
    # BALANCEADOS: articulos normales en KG y BOLSA, mas kits por presentacion en BOLSA y CAJA
    cursor, _ = base(items, filas=[("KG",), ("BOLSA",), ("CAJA",)])
    r = items.trae_presentaciones("BALANCEADOS")
    assert [(p["codigo"], p["unidad"]) for p in r] == [("NORMAL", "BOLSA"), ("NORMAL", "CAJA"), ("NORMAL", "KG")]
    assert [p["descripcion"] for p in r] == ["Por BOLSA", "Por CAJA", "Por KG"]
    assert len(cursor.consultas) == 1               # ya no hay una consulta aparte para "Por presentacion"
    q, params = cursor.consultas[0]
    assert params == ("BALANCEADOS",)
    assert normalizar(sql_catalogo.SQL_TIPO_EFECTIVO) in q and f"AND {sql_catalogo.SQL_TIPO_VISIBLE}" in q
    assert "a.art_kit = FALSE" not in q             # los kits por presentacion entran
    assert "IS DISTINCT FROM 'COMBO'" in q          # los combos no


def test_ya_no_existe_la_forma_de_compra_por_presentacion(base):
    base(items, filas=[("UNIDAD",)])
    r = items.trae_presentaciones("MERCERIAS")
    assert r == [{"codigo": "NORMAL", "unidad": "UNIDAD", "descripcion": "Por unidad"}]


def test_un_articulo_sin_unidad_de_venta_sigue_siendo_un_error(base):
    base(items, filas=[("KG",), (None,)])
    with pytest.raises(HTTPException) as e:
        items.trae_presentaciones("BALANCEADOS")
    assert e.value.status_code == 500


def test_el_filtro_por_unidad_incluye_a_los_kits_de_la_categoria(base):
    cursor, _ = base(items, filas=[])
    items.trae_articulos(1, 30, "BALANCEADOS", "BOLSA", "NORMAL")
    q, params = cursor.consultas[0]
    assert "AND um.uni_nombre = %s" in q and "a.art_kit = FALSE" not in q
    assert params == ("BALANCEADOS", "BOLSA", 30, 0)


# ---------- menu de categorias ----------

def test_el_menu_solo_trae_tipos_visibles_y_con_articulos(base):
    cursor, _ = base(categories, filas=[(1, "BALANCEADOS"), (1007, "MERCERIAS")])
    r = categories.listar_categorias()
    assert r == [{"id": 1, "nombre": "BALANCEADOS"}, {"id": 1007, "nombre": "MERCERIAS"}]
    q = cursor.consultas[0][0]
    assert "t.mostrar_web = TRUE" in q
    assert normalizar(sql_catalogo.SQL_TIPO_CON_ARTICULOS) in q
    assert q.endswith("ORDER BY t.tipoart_cod")


def test_un_tipo_con_articulos_cuenta_los_kits_por_el_tipo_de_su_componente():
    q = normalizar(sql_catalogo.SQL_TIPO_CON_ARTICULOS)
    assert normalizar(sql_catalogo.SQL_TIPO_COMPONENTE_LATERAL) in q
    assert "COALESCE(tipo_comp.tipoart_cod, a.tipoart_cod) = t.tipoart_cod" in q
    for condicion in ("a.art_estado = 'S'", "a.llevar_web = TRUE", "a.mostrar_web = TRUE"):
        assert condicion in q
    assert "a.tipo_kit IS DISTINCT FROM 'COMBO'" in q   # los combos tienen su propia vista


def test_sin_ningun_tipo_visible_el_menu_es_una_lista_vacia_no_un_error(base):
    base(categories, filas=[])
    assert categories.listar_categorias() == []


def test_error_de_base_en_categorias_es_500(base):
    base(categories, falla=True)
    with pytest.raises(HTTPException) as e:
        categories.listar_categorias()
    assert e.value.status_code == 500


# ---------- panel de administracion ----------

def test_las_rutas_de_tipos_exigen_sesion():
    rutas = {(r.path, tuple(sorted(r.methods))): r for r in admin.router.routes if "/tipos" in r.path}
    assert set(rutas) == {("/admin/tipos", ("GET",)), ("/admin/tipos/{tipoart_cod}", ("PATCH",))}
    for ruta in rutas.values():
        assert any(d.call is admin_auth.verificar_admin for d in ruta.dependant.dependencies)


def test_el_panel_lista_cada_tipo_con_su_estado_y_si_aparece_en_el_menu(base):
    # (cod, desc, mostrar_web, publicados, con_articulos, total, total_publicados)
    filas = [
        (1, "BALANCEADOS", True, 33, True, 60, 33),     # visible y con articulos (kits incluidos): aparece en el menu
        (6028, "CALZADOS", True, 0, False, 54, 0),      # visible pero sin articulos publicados: no aparece
        (1007, "MERCERIAS", False, 5, True, 160, 5),    # con articulos pero oculto por el administrador
        (5003, "KIT", True, 1, True, 2, 2),             # el COMBO esta publicado pero no depende del tipo
    ]
    cursor, _ = base(admin, filas=filas)
    r = admin.listar_tipos_admin()
    assert [(t["tipoart_desc"], t["mostrar_web"], t["articulos_publicados"], t["en_menu"]) for t in r] == [
        ("BALANCEADOS", True, 33, True), ("CALZADOS", True, 0, False), ("MERCERIAS", False, 5, False),
        ("KIT", True, 1, True)]
    # "publicados de total" (pantalla de tipos y filtro del panel de imagenes): el total cuenta todos los
    # articulos del tipo y los publicados incluyen los COMBO, igual que el cartel "Publicado" de la lista
    assert [(t["articulos_total_publicados"], t["articulos_total"]) for t in r] == [(33, 60), (0, 54), (5, 160), (2, 2)]
    q_total_publicados = cursor.consultas[0][0]
    assert "AS total_publicados" in q_total_publicados
    q = cursor.consultas[0][0]
    assert normalizar(sql_catalogo.SQL_TIPO_CON_ARTICULOS) in q and "ORDER BY t.tipoart_desc" in q
    # la cantidad de publicados tambien cuenta cada kit en el tipo de su componente
    assert normalizar(sql_catalogo.SQL_TIPO_COMPONENTE_LATERAL) in q


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
