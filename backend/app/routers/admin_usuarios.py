"""Gestion de usuarios del panel (solo administradores) y cambio de la propia contrasena."""
import psycopg.errors
from fastapi import APIRouter, Cookie, Depends, HTTPException, Path, status

from backend.app import seguridad_admin as seg
from backend.app.database_postgres import obtener_conexion_postgres
from backend.app.routers.admin_auth import verificar_admin
from backend.app.schemas import CambioDePassword, PasswordNueva, UsuarioCambio, UsuarioNuevo

router = APIRouter(prefix="/admin", tags=["Administracion"])

ID_USUARIO = Path(..., gt=0, lt=2**31)

# Candado de transaccion que serializa los cambios de activo/rol: sin el, dos cambios simultaneos
# sobre administradores distintos se bloquearian mutuamente (cada uno con su fila y esperando la otra).
CANDADO_CAMBIOS_DE_USUARIOS = 730120


def exigir_administrador(actual: dict = Depends(verificar_admin)):
    """Dependencia: ademas de tener sesion, hay que tener el rol de administrador."""
    if not actual["es_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo un administrador puede gestionar usuarios",
        )
    return actual


def error_400(texto):
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=texto)


def con_base(operacion):
    """Ejecuta operacion(cursor) en una transaccion: commit si sale bien, rollback si falla."""
    conn = None
    cursor = None
    try:
        conn = obtener_conexion_postgres()
        cursor = conn.cursor()
        resultado = operacion(cursor)
        conn.commit()
        return resultado
    except HTTPException:
        if conn:
            conn.rollback()
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        print("Error en la gestion de usuarios:", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo completar la operacion",
        )
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# ---------- listar ----------

@router.get("/usuarios")
def listar_usuarios(_: dict = Depends(exigir_administrador)):
    def operacion(cursor):
        cursor.execute(
            "SELECT id, usuario, activo, es_admin, ultimo_acceso, creado_en, "
            "COALESCE(bloqueado_hasta > now(), FALSE) "
            "FROM admin_usuarios ORDER BY usuario"
        )
        return [
            {
                "id": f[0],
                "usuario": f[1],
                "activo": f[2],
                "es_admin": f[3],
                "ultimo_acceso": f[4].isoformat() if f[4] else None,
                "creado_en": f[5].isoformat() if f[5] else None,
                "bloqueado": f[6],
            }
            for f in cursor.fetchall()
        ]
    return con_base(operacion)


# ---------- crear ----------

@router.post("/usuarios", status_code=status.HTTP_201_CREATED)
def crear_usuario(datos: UsuarioNuevo, _: dict = Depends(exigir_administrador)):
    problema = seg.validar_password_nueva(datos.password)
    if problema:
        raise error_400(problema)
    hash_nuevo = seg.hashear_password(datos.password)

    def operacion(cursor):
        try:
            cursor.execute(
                "INSERT INTO admin_usuarios (usuario, password_hash, es_admin) "
                "VALUES (%s, %s, %s) RETURNING id",
                (datos.usuario, hash_nuevo, datos.es_admin),
            )
        except psycopg.errors.UniqueViolation:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Ya existe un usuario con ese nombre",
            )
        return {"id": cursor.fetchone()[0], "usuario": datos.usuario, "es_admin": datos.es_admin}
    return con_base(operacion)


# ---------- activar / desactivar / cambiar rol ----------

@router.patch("/usuarios/{usuario_id}")
def cambiar_usuario(datos: UsuarioCambio, usuario_id: int = ID_USUARIO,
                    actual: dict = Depends(exigir_administrador)):
    def operacion(cursor):
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", (CANDADO_CAMBIOS_DE_USUARIOS,))
        cursor.execute(
            "SELECT activo, es_admin FROM admin_usuarios WHERE id = %s FOR UPDATE", (usuario_id,))
        fila = cursor.fetchone()
        if fila is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")
        activo = fila[0] if datos.activo is None else datos.activo
        es_admin = fila[1] if datos.es_admin is None else datos.es_admin

        quita_acceso = (fila[0] and not activo) or (fila[1] and not es_admin)
        if usuario_id == actual["id"] and quita_acceso:
            raise error_400("No podés desactivarte ni quitarte el rol de administrador a vos mismo")
        if fila[0] and fila[1] and not (activo and es_admin):
            # siempre debe quedar otro administrador activo (se bloquean para decidir sin carreras)
            cursor.execute(
                "SELECT id FROM admin_usuarios WHERE es_admin AND activo AND id <> %s FOR UPDATE",
                (usuario_id,),
            )
            if not cursor.fetchall():
                raise error_400("Tiene que quedar al menos un administrador activo")

        cursor.execute(
            "UPDATE admin_usuarios SET activo = %s, es_admin = %s WHERE id = %s",
            (activo, es_admin, usuario_id),
        )
        if not activo:
            cursor.execute("DELETE FROM admin_sesiones WHERE usuario_id = %s", (usuario_id,))
        return {"id": usuario_id, "activo": activo, "es_admin": es_admin}
    return con_base(operacion)


# ---------- restablecer la contrasena de otro usuario ----------

@router.post("/usuarios/{usuario_id}/password")
def restablecer_password(datos: PasswordNueva, usuario_id: int = ID_USUARIO,
                         actual: dict = Depends(exigir_administrador)):
    if usuario_id == actual["id"]:
        raise error_400("Para cambiar tu propia contraseña usá \"Cambiar mi contraseña\"")
    problema = seg.validar_password_nueva(datos.password)
    if problema:
        raise error_400(problema)
    hash_nuevo = seg.hashear_password(datos.password)

    def operacion(cursor):
        cursor.execute(
            "UPDATE admin_usuarios SET password_hash = %s, intentos_fallidos = 0, "
            "bloqueado_hasta = NULL WHERE id = %s",
            (hash_nuevo, usuario_id),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")
        cursor.execute("DELETE FROM admin_sesiones WHERE usuario_id = %s", (usuario_id,))
        return {"ok": True}
    return con_base(operacion)


# ---------- cambiar la propia contrasena (cualquier usuario con sesion) ----------

@router.post("/mi-password")
def cambiar_mi_password(datos: CambioDePassword, actual: dict = Depends(verificar_admin),
                        token: str = Cookie(default="", alias=seg.NOMBRE_COOKIE)):
    problema = seg.validar_password_nueva(datos.nueva)
    if problema:
        raise error_400(problema)

    def operacion(cursor):
        cursor.execute(
            "SELECT password_hash, COALESCE(bloqueado_hasta > now(), FALSE) "
            "FROM admin_usuarios WHERE id = %s FOR UPDATE",
            (actual["id"],),
        )
        fila = cursor.fetchone()
        if fila is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No autorizado")
        if fila[1]:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Demasiados intentos fallidos. Probá de nuevo en {seg.BLOQUEO_MINUTOS} minutos.",
            )
        if not seg.verificar_password(datos.actual, fila[0]):
            # con una sesion robada tambien se contaria como intento fallido
            seg.registrar_fallo(cursor, actual["id"])
            return False
        cursor.execute(
            "UPDATE admin_usuarios SET password_hash = %s, intentos_fallidos = 0 WHERE id = %s",
            (seg.hashear_password(datos.nueva), actual["id"]),
        )
        # las demas sesiones de este usuario (otros equipos) se cierran; esta sigue abierta
        cursor.execute(
            "DELETE FROM admin_sesiones WHERE usuario_id = %s AND token_hash <> %s",
            (actual["id"], seg.hash_de_token(token)),
        )
        return True

    if not con_base(operacion):
        raise error_400("La contraseña actual no es correcta")
    return {"ok": True}
