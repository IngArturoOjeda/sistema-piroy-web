"""
Login del panel de administracion: hash de contrasena, sesion por cookie, bloqueo y rutas protegidas.

Cursor y conexion simulados: no toca ninguna base.
"""
import inspect

import pytest
from fastapi import HTTPException, Response

from backend.app import seguridad_admin as seg
from backend.app.routers import admin, admin_auth
from backend.app.schemas import LoginEntrada

PASSWORD = "una-clave-larga-123"


class Cursor:
    """Responde a cada consulta segun su texto; guarda lo ejecutado."""

    def __init__(self, usuario=None, sesion=None):
        self.usuario = usuario      # (id, hash, activo, bloqueado) o None
        self.sesion = sesion        # (id, usuario, es_admin) o None
        self.consultas = []
        self._ultima = ""

    def execute(self, sql, params=()):
        self._ultima = " ".join(sql.split())
        self.consultas.append((self._ultima, tuple(params)))

    def fetchone(self):
        if "FROM admin_usuarios WHERE usuario" in self._ultima:
            return self.usuario
        if "FROM admin_sesiones s" in self._ultima:
            return self.sesion
        return None

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
        monkeypatch.setattr(admin_auth, "obtener_conexion_postgres", lambda: conn)
        return cursor, conn
    return armar


@pytest.fixture(scope="module")
def hash_valido():
    return seg.hashear_password(PASSWORD)


# ---------- contrasenas ----------

def test_el_hash_no_contiene_la_contrasena_y_lleva_sal_propia(hash_valido):
    otro = seg.hashear_password(PASSWORD)
    assert PASSWORD not in hash_valido
    assert hash_valido.startswith("scrypt$") and hash_valido != otro


def test_verificar_password(hash_valido):
    assert seg.verificar_password(PASSWORD, hash_valido) is True
    assert seg.verificar_password(PASSWORD + "x", hash_valido) is False
    assert seg.verificar_password("", hash_valido) is False


@pytest.mark.parametrize("guardado", ["", "basura", "bcrypt$1$2$3$a$b", "scrypt$x$8$1$aa$bb"])
def test_hash_guardado_invalido_no_verifica_ni_revienta(guardado):
    assert seg.verificar_password(PASSWORD, guardado) is False


def test_politica_de_contrasena_nueva():
    assert seg.validar_password_nueva("corta") is not None
    assert seg.validar_password_nueva("x" * 201) is not None
    assert seg.validar_password_nueva("x" * seg.LARGO_MINIMO_PASSWORD) is None


def test_el_token_se_guarda_solo_como_hash():
    token = seg.nuevo_token()
    assert seg.hash_de_token(token) != token and len(seg.hash_de_token(token)) == 64
    assert seg.nuevo_token() != token


# ---------- entrada ----------

def test_el_usuario_se_normaliza_a_minusculas_sin_espacios():
    assert LoginEntrada(usuario="  Admin ", password="x").usuario == "admin"


# ---------- login ----------

def test_login_correcto_crea_sesion_y_cookie_segura(base, hash_valido):
    cursor, conn = base(usuario=(7, hash_valido, True, False))
    r = Response()
    resultado = admin_auth.iniciar_sesion(LoginEntrada(usuario="Admin", password=PASSWORD), r)
    assert resultado == {"usuario": "admin"}
    assert conn.commits == 1
    cookie = r.headers["set-cookie"].lower()
    assert seg.NOMBRE_COOKIE in cookie
    for marca in ("httponly", "secure", "samesite=strict", "path=/api/admin", "max-age=28800"):
        assert marca in cookie
    assert any(s.startswith("INSERT INTO admin_sesiones") for s in cursor.sql())
    # lo que se guarda es el hash del token de la cookie, no el token
    token = r.headers["set-cookie"].split("=", 1)[1].split(";", 1)[0]
    insert = next(c for c in cursor.consultas if c[0].startswith("INSERT INTO admin_sesiones"))
    assert insert[1][1] == seg.hash_de_token(token) and insert[1][1] != token


def test_la_busqueda_del_usuario_bloquea_su_fila_hasta_terminar_el_ingreso(base, hash_valido):
    # evita pruebas de clave en paralelo y sesiones nuevas tras un cambio de contrasena
    cursor, _ = base(usuario=(7, hash_valido, True, False))
    admin_auth.iniciar_sesion(LoginEntrada(usuario="admin", password=PASSWORD), Response())
    assert cursor.consultas[0][0].endswith("WHERE usuario = %s FOR UPDATE")


def test_login_correcto_reinicia_el_contador_de_fallos(base, hash_valido):
    cursor, _ = base(usuario=(7, hash_valido, True, False))
    admin_auth.iniciar_sesion(LoginEntrada(usuario="admin", password=PASSWORD), Response())
    assert any("intentos_fallidos = 0" in s and "bloqueado_hasta = NULL" in s for s in cursor.sql())


def test_contrasena_incorrecta_es_401_y_cuenta_el_fallo(base, hash_valido):
    cursor, conn = base(usuario=(7, hash_valido, True, False))
    r = Response()
    with pytest.raises(HTTPException) as e:
        admin_auth.iniciar_sesion(LoginEntrada(usuario="admin", password="mala"), r)
    assert e.value.status_code == 401 and e.value.detail == admin_auth.MENSAJE_CREDENCIALES
    assert "set-cookie" not in r.headers
    assert conn.commits == 1                      # el fallo queda registrado
    assert any(s.startswith("UPDATE admin_usuarios SET intentos_fallidos") for s in cursor.sql())
    assert not any(s.startswith("INSERT INTO admin_sesiones") for s in cursor.sql())


def test_usuario_inexistente_y_clave_mala_dan_el_mismo_mensaje(base, hash_valido):
    base(usuario=None)
    with pytest.raises(HTTPException) as inexistente:
        admin_auth.iniciar_sesion(LoginEntrada(usuario="nadie", password="x"), Response())
    base(usuario=(7, hash_valido, True, False))
    with pytest.raises(HTTPException) as mala:
        admin_auth.iniciar_sesion(LoginEntrada(usuario="admin", password="x"), Response())
    assert inexistente.value.status_code == mala.value.status_code == 401
    assert inexistente.value.detail == mala.value.detail


def test_usuario_dado_de_baja_no_entra_ni_con_la_clave_correcta(base, hash_valido):
    cursor, _ = base(usuario=(7, hash_valido, False, False))
    with pytest.raises(HTTPException) as e:
        admin_auth.iniciar_sesion(LoginEntrada(usuario="admin", password=PASSWORD), Response())
    assert e.value.status_code == 401
    assert not any(s.startswith("INSERT INTO admin_sesiones") for s in cursor.sql())


def test_usuario_bloqueado_es_429_aunque_la_clave_sea_correcta(base, hash_valido):
    cursor, _ = base(usuario=(7, hash_valido, True, True))
    r = Response()
    with pytest.raises(HTTPException) as e:
        admin_auth.iniciar_sesion(LoginEntrada(usuario="admin", password=PASSWORD), r)
    assert e.value.status_code == 429
    assert "set-cookie" not in r.headers
    assert not any(s.startswith("INSERT INTO admin_sesiones") for s in cursor.sql())


def test_el_bloqueo_se_decide_en_el_sql_con_el_reloj_de_la_base():
    cursor = Cursor()
    seg.registrar_fallo(cursor, 7)
    sql, params = cursor.consultas[0]
    assert "THEN 0 ELSE intentos_fallidos + 1" in sql
    assert "now() + make_interval(mins => %s)" in sql
    assert params == (seg.INTENTOS_MAXIMOS, seg.INTENTOS_MAXIMOS, seg.BLOQUEO_MINUTOS, 7)
    assert seg.INTENTOS_MAXIMOS == 5 and seg.BLOQUEO_MINUTOS == 15


def test_error_de_base_en_el_login_es_500_con_rollback(monkeypatch):
    class Roto(Cursor):
        def execute(self, *a, **k):
            raise RuntimeError("falla simulada")

    conn = Conn(Roto())
    monkeypatch.setattr(admin_auth, "obtener_conexion_postgres", lambda: conn)
    with pytest.raises(HTTPException) as e:
        admin_auth.iniciar_sesion(LoginEntrada(usuario="admin", password="x"), Response())
    assert e.value.status_code == 500 and conn.rollbacks == 1


# ---------- sesion vigente ----------

def test_sin_cookie_es_401_sin_consultar_la_base(base):
    cursor, _ = base()
    with pytest.raises(HTTPException) as e:
        admin_auth.verificar_admin("")
    assert e.value.status_code == 401 and cursor.consultas == []


def test_sesion_invalida_o_vencida_es_401(base):
    base(sesion=None)
    with pytest.raises(HTTPException) as e:
        admin_auth.verificar_admin("token-viejo")
    assert e.value.status_code == 401


def test_sesion_vigente_devuelve_el_usuario(base):
    cursor, _ = base(sesion=(7, "admin", True))
    assert admin_auth.verificar_admin("token-bueno") == {"id": 7, "usuario": "admin", "es_admin": True}
    sql, params = cursor.consultas[0]
    assert "s.vence_en > now()" in sql and "u.activo" in sql
    assert params == (seg.hash_de_token("token-bueno"),)


def test_error_de_base_al_verificar_es_500_no_deja_pasar(monkeypatch):
    class Roto(Cursor):
        def execute(self, *a, **k):
            raise RuntimeError("falla simulada")

    monkeypatch.setattr(admin_auth, "obtener_conexion_postgres", lambda: Conn(Roto()))
    with pytest.raises(HTTPException) as e:
        admin_auth.verificar_admin("token")
    assert e.value.status_code == 500


# ---------- logout ----------

def test_logout_borra_la_sesion_y_la_cookie(base):
    cursor, conn = base()
    r = Response()
    assert admin_auth.cerrar_sesion(r, "mi-token") == {"ok": True}
    assert conn.commits == 1
    assert cursor.consultas[0] == (
        "DELETE FROM admin_sesiones WHERE token_hash = %s", (seg.hash_de_token("mi-token"),))
    assert seg.NOMBRE_COOKIE in r.headers["set-cookie"] and "Max-Age=0" in r.headers["set-cookie"]


def test_logout_sin_sesion_no_falla(base):
    cursor, _ = base()
    assert admin_auth.cerrar_sesion(Response(), "") == {"ok": True}
    assert cursor.consultas == []


# ---------- todas las rutas del panel exigen sesion ----------

def test_todas_las_rutas_del_panel_exigen_la_sesion():
    rutas = list(admin.router.routes)
    assert rutas, "el router de administracion no tiene rutas"
    for ruta in rutas:
        assert any(d.call is admin_auth.verificar_admin for d in ruta.dependant.dependencies), ruta.path


def test_solo_login_y_logout_son_publicos_en_el_router_de_autenticacion():
    publicas = {r.path for r in admin_auth.router.routes
                if not any(d.call is admin_auth.verificar_admin for d in r.dependant.dependencies)}
    assert publicas == {"/admin/login", "/admin/logout"}


def test_la_clave_vieja_de_cabecera_ya_no_abre_el_panel():
    assert "x_admin_key" not in inspect.getsource(admin_auth).lower()
    assert "ADMIN_API_KEY" not in inspect.getsource(admin)
