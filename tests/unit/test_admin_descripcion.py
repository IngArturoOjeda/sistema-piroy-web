"""
Descripcion comercial de un articulo desde el panel de administracion:
PATCH /api/admin/articulos/{art_cod}/descripcion y la busqueda del panel.

Cursor y conexion simulados: no toca ninguna base.
"""
import inspect

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from backend.app.routers import admin
from backend.app.schemas import DescripcionEntrada


class FakeCursor:
    def __init__(self, filas=None, rowcount=1, falla=False):
        self.filas = filas or []
        self.rowcount = rowcount
        self.falla = falla
        self.consultas = []

    def execute(self, sql, params=None):
        if self.falla:
            raise RuntimeError("fallo simulado")
        self.consultas.append((" ".join(sql.split()), params))

    def fetchall(self):
        return self.filas

    def close(self):
        pass


class FakeConn:
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
    def armar(**opciones):
        cursor = FakeCursor(**opciones)
        conn = FakeConn(cursor)
        monkeypatch.setattr(admin, "obtener_conexion_postgres", lambda: conn)
        return cursor, conn
    return armar


# --- Esquema --------------------------------------------------------------

def test_esquema_recorta_espacios_y_guarda_el_texto():
    assert DescripcionEntrada(descripcion="  Botina de trabajo.\nSuela.  ").descripcion == "Botina de trabajo.\nSuela."


@pytest.mark.parametrize("valor", ["", "   ", "\n\t "])
def test_esquema_texto_vacio_es_nulo(valor):
    assert DescripcionEntrada(descripcion=valor).descripcion is None


def test_esquema_acepta_null_explicito():
    assert DescripcionEntrada(descripcion=None).descripcion is None


def test_esquema_exige_el_campo_y_rechaza_extras():
    with pytest.raises(ValidationError):
        DescripcionEntrada()
    with pytest.raises(ValidationError):
        DescripcionEntrada(descripcion="x", art_cod=5)


def test_esquema_limite_de_2000_caracteres():
    assert len(DescripcionEntrada(descripcion="a" * 2000).descripcion) == 2000
    with pytest.raises(ValidationError):
        DescripcionEntrada(descripcion="a" * 2001)


# --- Ruta -----------------------------------------------------------------

def test_guarda_la_descripcion_con_parametros(base):
    cursor, conn = base()
    r = admin.actualizar_descripcion(DescripcionEntrada(descripcion="Texto"), 1000)
    assert r == {"status": "ok", "art_cod": 1000, "descripcion": "Texto"}
    sql, params = cursor.consultas[0]
    assert sql == "UPDATE articulos SET descripcion = %s WHERE art_cod = %s"
    assert params == ("Texto", 1000)
    assert conn.commits == 1


def test_un_texto_vacio_limpia_la_descripcion(base):
    cursor, _ = base()
    r = admin.actualizar_descripcion(DescripcionEntrada(descripcion="   "), 1000)
    assert r["descripcion"] is None
    assert cursor.consultas[0][1] == (None, 1000)


def test_texto_con_comillas_y_sql_viaja_como_parametro(base):
    cursor, _ = base()
    peligro = "'); DROP TABLE articulos; --"
    admin.actualizar_descripcion(DescripcionEntrada(descripcion=peligro), 1000)
    sql, params = cursor.consultas[0]
    assert "DROP" not in sql and params[0] == peligro


def test_articulo_inexistente_es_404_y_no_confirma(base):
    _, conn = base(rowcount=0)
    with pytest.raises(HTTPException) as e:
        admin.actualizar_descripcion(DescripcionEntrada(descripcion="x"), 999999)
    assert e.value.status_code == 404
    assert conn.commits == 0 and conn.rollbacks == 1


def test_error_de_base_es_500_con_rollback(base):
    _, conn = base(falla=True)
    with pytest.raises(HTTPException) as e:
        admin.actualizar_descripcion(DescripcionEntrada(descripcion="x"), 1000)
    assert e.value.status_code == 500
    assert conn.commits == 0 and conn.rollbacks == 1


def test_codigo_fuera_de_rango_se_rechaza_en_la_ruta():
    por_defecto = inspect.signature(admin.actualizar_descripcion).parameters["art_cod"].default
    limites = {type(m).__name__: m for m in por_defecto.metadata}
    assert limites["Gt"].gt == 0 and limites["Lt"].lt == 10**18


def test_la_ruta_exige_la_clave_de_administrador():
    ruta = next(r for r in admin.router.routes if r.path == "/admin/articulos/{art_cod}/descripcion")
    assert "PATCH" in ruta.methods
    assert any(d.call is admin.verificar_admin for d in ruta.dependant.dependencies)


# --- La busqueda del panel trae la descripcion actual ---------------------

def test_la_busqueda_del_panel_devuelve_la_descripcion(base):
    filas = [
        (1000, "BOTINA", 80000, "CALZADOS", "https://x/1.jpg", "S", True, True, "Texto cargado"),
        (1001, "OTRA", 5000, "CALZADOS", None, "S", True, False, None),
    ]
    cursor, _ = base(filas=filas)
    r = admin.buscar_articulos_admin("bot")
    assert "a.descripcion" in cursor.consultas[0][0]
    assert r[0]["descripcion"] == "Texto cargado"
    assert r[1]["descripcion"] is None
