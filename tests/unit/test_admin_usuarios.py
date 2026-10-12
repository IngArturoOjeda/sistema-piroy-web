"""
Gestion de usuarios del panel: solo administradores, reglas para no quedarse sin acceso,
y cambio de la propia contrasena. Cursor y conexion simulados: no toca ninguna base.
"""
import datetime

import psycopg.errors
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from backend.app import seguridad_admin as seg
from backend.app.routers import admin_auth, admin_usuarios as au
from backend.app.schemas import CambioDePassword, PasswordNueva, UsuarioCambio, UsuarioNuevo

YO = {"id": 1, "usuario": "arturo", "es_admin": True}
COMUN = {"id": 2, "usuario": "juan", "es_admin": False}
PASSWORD_VIEJA = "clave-vieja-1234"


class Cursor:
    """respuestas: lista de (texto_que_debe_contener_la_consulta, filas). rowcount configurable."""

    def __init__(self, respuestas=(), rowcount=1, falla_con=None):
        self.respuestas = list(respuestas)
        self.rowcount = rowcount
        self.falla_con = falla_con
        self.consultas = []
        self._filas = []

    def execute(self, sql, params=()):
        q = " ".join(sql.split())
        self.consultas.append((q, tuple(params)))
        if self.falla_con and q.startswith("INSERT"):
            raise self.falla_con
        self._filas = []
        for clave, filas in self.respuestas:
            if clave in q:
                self._filas = filas
                break

    def fetchone(self):
        return self._filas[0] if self._filas else None

    def fetchall(self):
        return list(self._filas)

    def close(self):
        pass

    def sql(self):
        return [c[0] for c in self.consultas]


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
    def armar(**kwargs):
        cursor = Cursor(**kwargs)
        conn = Conn(cursor)
        monkeypatch.setattr(au, "obtener_conexion_postgres", lambda: conn)
        return cursor, conn
    return armar


# ---------- permisos ----------

def test_un_usuario_comun_no_gestiona_usuarios():
    with pytest.raises(HTTPException) as e:
        au.exigir_administrador(COMUN)
    assert e.value.status_code == 403


def test_un_administrador_si():
    assert au.exigir_administrador(YO) == YO


def test_las_rutas_de_gestion_exigen_administrador_y_mi_password_solo_sesion():
    for ruta in au.router.routes:
        llamadas = [d.call for d in ruta.dependant.dependencies]
        if ruta.path == "/admin/mi-password":
            assert admin_auth.verificar_admin in llamadas
            assert au.exigir_administrador not in llamadas
        else:
            assert au.exigir_administrador in llamadas, ruta.path


# ---------- entradas ----------

def test_usuario_nuevo_se_normaliza_y_valida():
    assert UsuarioNuevo(usuario="  Juan.Perez ", password="x").usuario == "juan.perez"
    for malo in ("ab", "con espacio", "ñandú", "a" * 51, "x/y"):
        with pytest.raises(ValidationError):
            UsuarioNuevo(usuario=malo, password="x")


def test_el_cambio_necesita_algo_que_cambiar():
    with pytest.raises(ValidationError):
        UsuarioCambio()
    assert UsuarioCambio(activo=False).es_admin is None


# ---------- listar ----------

def test_listar_devuelve_los_datos_sin_el_hash(base):
    fecha = datetime.datetime(2026, 10, 12, 10, 0, tzinfo=datetime.timezone.utc)
    cursor, _ = base(respuestas=[("FROM admin_usuarios", [(1, "arturo", True, True, fecha, fecha, False)])])
    r = au.listar_usuarios(YO)
    assert r == [{"id": 1, "usuario": "arturo", "activo": True, "es_admin": True,
                  "ultimo_acceso": fecha.isoformat(), "creado_en": fecha.isoformat(), "bloqueado": False}]
    assert "password_hash" not in cursor.sql()[0]


# ---------- crear ----------

def test_crear_guarda_el_hash_y_nunca_la_contrasena(base):
    cursor, conn = base(respuestas=[("INSERT", [(9,)])])
    r = au.crear_usuario(UsuarioNuevo(usuario="Juan", password="una-clave-larga-1", es_admin=False), YO)
    assert r == {"id": 9, "usuario": "juan", "es_admin": False} and conn.commits == 1
    params = cursor.consultas[0][1]
    assert params[0] == "juan" and params[1].startswith("scrypt$") and "una-clave-larga-1" not in params[1]


def test_crear_con_contrasena_corta_es_400_sin_tocar_la_base(base):
    cursor, _ = base()
    with pytest.raises(HTTPException) as e:
        au.crear_usuario(UsuarioNuevo(usuario="juan", password="corta"), YO)
    assert e.value.status_code == 400 and cursor.consultas == []


def test_crear_un_usuario_repetido_es_409_con_rollback(base):
    _, conn = base(falla_con=psycopg.errors.UniqueViolation("duplicado"))
    with pytest.raises(HTTPException) as e:
        au.crear_usuario(UsuarioNuevo(usuario="juan", password="una-clave-larga-1"), YO)
    assert e.value.status_code == 409 and conn.rollbacks == 1 and conn.commits == 0


# ---------- activar / desactivar / rol ----------

def test_desactivar_a_otro_cierra_sus_sesiones(base):
    cursor, conn = base(respuestas=[("SELECT activo, es_admin", [(True, False)])])
    r = au.cambiar_usuario(UsuarioCambio(activo=False), 2, YO)
    assert r == {"id": 2, "activo": False, "es_admin": False} and conn.commits == 1
    assert any(s.startswith("DELETE FROM admin_sesiones WHERE usuario_id") for s in cursor.sql())


def test_reactivar_no_borra_sesiones(base):
    cursor, _ = base(respuestas=[("SELECT activo, es_admin", [(False, False)])])
    au.cambiar_usuario(UsuarioCambio(activo=True), 2, YO)
    assert not any(s.startswith("DELETE") for s in cursor.sql())


@pytest.mark.parametrize("cambio", [UsuarioCambio(activo=False), UsuarioCambio(es_admin=False)])
def test_nadie_se_desactiva_ni_se_quita_el_rol_a_si_mismo(base, cambio):
    cursor, conn = base(respuestas=[("SELECT activo, es_admin", [(True, True)])])
    with pytest.raises(HTTPException) as e:
        au.cambiar_usuario(cambio, YO["id"], YO)
    assert e.value.status_code == 400 and conn.commits == 0 and conn.rollbacks == 1
    assert not any(s.startswith("UPDATE") for s in cursor.sql())


def test_no_se_puede_dejar_al_sistema_sin_administrador_activo(base):
    # el actor (id 1) intenta desactivar a otro administrador (id 5) y no queda ninguno mas activo
    cursor, conn = base(respuestas=[("SELECT activo, es_admin", [(True, True)]),
                                    ("es_admin AND activo AND id <>", [])])
    with pytest.raises(HTTPException) as e:
        au.cambiar_usuario(UsuarioCambio(activo=False), 5, YO)
    assert e.value.status_code == 400 and conn.commits == 0
    assert not any(s.startswith("UPDATE") for s in cursor.sql())


def test_se_puede_desactivar_a_un_administrador_si_queda_otro(base):
    cursor, conn = base(respuestas=[("SELECT activo, es_admin", [(True, True)]),
                                    ("es_admin AND activo AND id <>", [(1,)])])
    au.cambiar_usuario(UsuarioCambio(activo=False), 5, YO)
    assert conn.commits == 1
    assert any("FOR UPDATE" in s and "es_admin AND activo" in s for s in cursor.sql())


def test_dar_el_rol_de_administrador_a_un_comun(base):
    cursor, _ = base(respuestas=[("SELECT activo, es_admin", [(True, False)])])
    r = au.cambiar_usuario(UsuarioCambio(es_admin=True), 2, YO)
    assert r["es_admin"] is True
    assert cursor.consultas[-1][1] == (True, True, 2)


def test_los_cambios_de_usuarios_se_serializan_con_un_candado_antes_de_bloquear_filas(base):
    # evita el abrazo mortal entre dos cambios simultaneos sobre administradores distintos
    cursor, _ = base(respuestas=[("SELECT activo, es_admin", [(True, False)])])
    au.cambiar_usuario(UsuarioCambio(activo=False), 2, YO)
    assert cursor.consultas[0] == ("SELECT pg_advisory_xact_lock(%s)", (au.CANDADO_CAMBIOS_DE_USUARIOS,))
    assert "FOR UPDATE" in cursor.consultas[1][0]


def test_cambiar_un_usuario_inexistente_es_404(base):
    _, conn = base(respuestas=[])
    with pytest.raises(HTTPException) as e:
        au.cambiar_usuario(UsuarioCambio(activo=False), 99, YO)
    assert e.value.status_code == 404 and conn.commits == 0


# ---------- restablecer contrasena ----------

def test_restablecer_cambia_el_hash_levanta_el_bloqueo_y_cierra_sesiones(base):
    cursor, conn = base()
    au.restablecer_password(PasswordNueva(password="otra-clave-larga-1"), 2, YO)
    assert conn.commits == 1
    update = cursor.consultas[0]
    assert "intentos_fallidos = 0" in update[0] and "bloqueado_hasta = NULL" in update[0]
    assert update[1][0].startswith("scrypt$") and update[1][1] == 2
    assert cursor.consultas[1] == ("DELETE FROM admin_sesiones WHERE usuario_id = %s", (2,))


def test_restablecer_la_propia_contrasena_por_esta_ruta_es_400(base):
    cursor, _ = base()
    with pytest.raises(HTTPException) as e:
        au.restablecer_password(PasswordNueva(password="otra-clave-larga-1"), YO["id"], YO)
    assert e.value.status_code == 400 and cursor.consultas == []


def test_restablecer_con_clave_corta_es_400(base):
    with pytest.raises(HTTPException) as e:
        au.restablecer_password(PasswordNueva(password="corta"), 2, YO)
    assert e.value.status_code == 400


def test_restablecer_a_un_usuario_inexistente_es_404(base):
    _, conn = base(rowcount=0)
    with pytest.raises(HTTPException) as e:
        au.restablecer_password(PasswordNueva(password="otra-clave-larga-1"), 99, YO)
    assert e.value.status_code == 404 and conn.commits == 0


# ---------- mi contrasena ----------

def test_mi_password_correcta_se_cambia_y_se_cierran_las_demas_sesiones(base):
    cursor, conn = base(respuestas=[("SELECT password_hash", [(seg.hashear_password(PASSWORD_VIEJA), False)])])
    r = au.cambiar_mi_password(CambioDePassword(actual=PASSWORD_VIEJA, nueva="clave-nueva-larga-1"), COMUN, "mi-token")
    assert r == {"ok": True} and conn.commits == 1
    borrado = next(c for c in cursor.consultas if c[0].startswith("DELETE FROM admin_sesiones"))
    assert "token_hash <> %s" in borrado[0]
    assert borrado[1] == (COMUN["id"], seg.hash_de_token("mi-token"))


def test_mi_password_con_la_actual_equivocada_es_400_y_cuenta_el_fallo(base):
    cursor, conn = base(respuestas=[("SELECT password_hash", [(seg.hashear_password(PASSWORD_VIEJA), False)])])
    with pytest.raises(HTTPException) as e:
        au.cambiar_mi_password(CambioDePassword(actual="equivocada", nueva="clave-nueva-larga-1"), COMUN, "t")
    assert e.value.status_code == 400
    assert conn.commits == 1                          # el fallo queda registrado
    assert any(s.startswith("UPDATE admin_usuarios SET intentos_fallidos") for s in cursor.sql())
    assert not any("SET password_hash" in s for s in cursor.sql())


def test_mi_password_bloqueado_es_429(base):
    _, _ = base(respuestas=[("SELECT password_hash", [(seg.hashear_password(PASSWORD_VIEJA), True)])])
    with pytest.raises(HTTPException) as e:
        au.cambiar_mi_password(CambioDePassword(actual=PASSWORD_VIEJA, nueva="clave-nueva-larga-1"), COMUN, "t")
    assert e.value.status_code == 429


def test_mi_password_nueva_corta_es_400_sin_tocar_la_base(base):
    cursor, _ = base()
    with pytest.raises(HTTPException) as e:
        au.cambiar_mi_password(CambioDePassword(actual=PASSWORD_VIEJA, nueva="corta"), COMUN, "t")
    assert e.value.status_code == 400 and cursor.consultas == []


# ---------- errores ----------

def test_error_de_base_es_500_con_rollback(monkeypatch):
    class Roto(Cursor):
        def execute(self, *a, **k):
            raise RuntimeError("falla simulada")

    conn = Conn(Roto())
    monkeypatch.setattr(au, "obtener_conexion_postgres", lambda: conn)
    with pytest.raises(HTTPException) as e:
        au.listar_usuarios(YO)
    assert e.value.status_code == 500 and conn.rollbacks == 1


@pytest.mark.parametrize("funcion", [au.cambiar_usuario, au.restablecer_password])
def test_el_id_de_usuario_se_valida_en_la_ruta(funcion):
    import inspect
    limites = {type(m).__name__: m for m in inspect.signature(funcion).parameters["usuario_id"].default.metadata}
    assert limites["Gt"].gt == 0 and limites["Lt"].lt == 2**31
