"""
Seguridad del panel de administracion: usuarios, contrasenas y sesiones.

- Contrasena: se guarda solo su hash (scrypt de la biblioteca estandar, sal propia por usuario).
- Sesion: el navegador recibe un token aleatorio en una cookie HttpOnly; en la base solo queda
  su hash SHA-256 (quien lea la base no puede usar las sesiones).
- Bloqueo: tras INTENTOS_MAXIMOS fallos seguidos el usuario queda bloqueado BLOQUEO_MINUTOS.

Las tablas son `admin_usuarios` y `admin_sesiones` (scripts/crear_tablas_admin.sql).
"""
import base64
import hashlib
import hmac
import secrets

from backend.app.database_postgres import obtener_conexion_postgres

NOMBRE_COOKIE = "agrovetzo_admin"
DURACION_SESION_HORAS = 8
INTENTOS_MAXIMOS = 5
BLOQUEO_MINUTOS = 15
LARGO_MINIMO_PASSWORD = 10

# scrypt: ~16 MB y unas decenas de milisegundos por verificacion
_N, _R, _P, _LARGO = 2**14, 8, 1, 32


def _b64(datos: bytes) -> str:
    return base64.b64encode(datos).decode("ascii")


def _derivar(password: str, sal: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=sal, n=n, r=r, p=p, dklen=_LARGO,
                          maxmem=128 * n * r * 2)


def hashear_password(password: str) -> str:
    """Devuelve 'scrypt$n$r$p$sal$hash' (sal y hash en base64)."""
    sal = secrets.token_bytes(16)
    derivado = _derivar(password, sal, _N, _R, _P)
    return f"scrypt${_N}${_R}${_P}${_b64(sal)}${_b64(derivado)}"


def verificar_password(password: str, guardado: str) -> bool:
    try:
        esquema, n, r, p, sal, esperado = guardado.split("$")
        if esquema != "scrypt":
            return False
        derivado = _derivar(password, base64.b64decode(sal), int(n), int(r), int(p))
        return hmac.compare_digest(derivado, base64.b64decode(esperado))
    except Exception:
        return False


# Hash de una contrasena que nadie conoce: se verifica contra el cuando el usuario no existe,
# para que "usuario inexistente" tarde lo mismo que "contrasena equivocada".
HASH_FICTICIO = hashear_password(secrets.token_urlsafe(16))


def hash_de_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def nuevo_token() -> str:
    return secrets.token_urlsafe(32)


def validar_password_nueva(password: str):
    """Devuelve un texto con el problema, o None si la contrasena sirve."""
    if len(password) < LARGO_MINIMO_PASSWORD:
        return f"La contrasena debe tener al menos {LARGO_MINIMO_PASSWORD} caracteres."
    if len(password) > 200:
        return "La contrasena es demasiado larga (maximo 200 caracteres)."
    return None


# ---------- Acceso a la base ----------

def buscar_usuario(cursor, usuario: str):
    """(id, password_hash, activo, bloqueado) o None. `bloqueado` lo decide la base (reloj unico).

    FOR UPDATE: la fila queda bloqueada hasta el commit/rollback, asi dos ingresos simultaneos del
    mismo usuario (o un ingreso y un cambio de contrasena) se atienden de a uno y ven el estado
    ya actualizado: no se pueden probar mas de INTENTOS_MAXIMOS claves en paralelo.
    """
    cursor.execute(
        "SELECT id, password_hash, activo, "
        "COALESCE(bloqueado_hasta > now(), FALSE) "
        "FROM admin_usuarios WHERE usuario = %s FOR UPDATE",
        (usuario,),
    )
    return cursor.fetchone()


def registrar_fallo(cursor, usuario_id: int):
    """Suma un intento fallido; al llegar al maximo bloquea y reinicia el contador."""
    cursor.execute(
        "UPDATE admin_usuarios SET "
        "intentos_fallidos = CASE WHEN intentos_fallidos + 1 >= %s THEN 0 ELSE intentos_fallidos + 1 END, "
        "bloqueado_hasta = CASE WHEN intentos_fallidos + 1 >= %s "
        "THEN now() + make_interval(mins => %s) ELSE bloqueado_hasta END "
        "WHERE id = %s",
        (INTENTOS_MAXIMOS, INTENTOS_MAXIMOS, BLOQUEO_MINUTOS, usuario_id),
    )


def crear_sesion(cursor, usuario_id: int) -> str:
    """Registra el acceso correcto, limpia sesiones vencidas y devuelve el token nuevo."""
    cursor.execute(
        "UPDATE admin_usuarios SET intentos_fallidos = 0, bloqueado_hasta = NULL, "
        "ultimo_acceso = now() WHERE id = %s",
        (usuario_id,),
    )
    cursor.execute("DELETE FROM admin_sesiones WHERE vence_en < now()")
    token = nuevo_token()
    cursor.execute(
        "INSERT INTO admin_sesiones (usuario_id, token_hash, vence_en) "
        "VALUES (%s, %s, now() + make_interval(hours => %s))",
        (usuario_id, hash_de_token(token), DURACION_SESION_HORAS),
    )
    return token


def usuario_de_sesion(cursor, token: str):
    """(id, usuario, es_admin) del dueno de una sesion vigente y activa, o None."""
    cursor.execute(
        "SELECT u.id, u.usuario, u.es_admin FROM admin_sesiones s "
        "JOIN admin_usuarios u ON u.id = s.usuario_id "
        "WHERE s.token_hash = %s AND s.vence_en > now() AND u.activo",
        (hash_de_token(token),),
    )
    return cursor.fetchone()


def cerrar_sesion(cursor, token: str):
    cursor.execute("DELETE FROM admin_sesiones WHERE token_hash = %s", (hash_de_token(token),))
