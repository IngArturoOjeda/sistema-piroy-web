"""Inicio y cierre de sesion del panel de administracion."""
from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status

from backend.app import seguridad_admin as seg
from backend.app.database_postgres import obtener_conexion_postgres
from backend.app.schemas import LoginEntrada

router = APIRouter(prefix="/admin", tags=["Administracion"])

# La cookie solo viaja hacia /api/admin: ni la tienda ni los archivos estaticos la reciben.
RUTA_COOKIE = "/api/admin"
MENSAJE_CREDENCIALES = "Usuario o contraseña incorrectos"


def verificar_admin(token: str = Cookie(default="", alias=seg.NOMBRE_COOKIE)):
    """Dependencia de las rutas del panel: exige una sesion vigente. Devuelve el usuario."""
    no_autorizado = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No autorizado")
    if not token:
        raise no_autorizado
    conn = None
    cursor = None
    try:
        conn = obtener_conexion_postgres()
        cursor = conn.cursor()
        usuario = seg.usuario_de_sesion(cursor, token)
    except Exception as e:
        print("Error verificando la sesion de administracion:", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo verificar la sesion",
        )
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
    if usuario is None:
        raise no_autorizado
    return usuario


@router.post("/login")
def iniciar_sesion(datos: LoginEntrada, respuesta: Response):
    conn = None
    cursor = None
    try:
        conn = obtener_conexion_postgres()
        cursor = conn.cursor()
        fila = seg.buscar_usuario(cursor, datos.usuario)

        if fila is None or not fila[2]:
            # Usuario inexistente o dado de baja: mismo tiempo y mismo mensaje que una clave mala
            seg.verificar_password(datos.password, seg.HASH_FICTICIO)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=MENSAJE_CREDENCIALES)

        usuario_id, password_hash, _, bloqueado = fila
        if bloqueado:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Demasiados intentos fallidos. Probá de nuevo en {seg.BLOQUEO_MINUTOS} minutos.",
            )

        if not seg.verificar_password(datos.password, password_hash):
            seg.registrar_fallo(cursor, usuario_id)
            conn.commit()
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=MENSAJE_CREDENCIALES)

        token = seg.crear_sesion(cursor, usuario_id)
        conn.commit()
    except HTTPException:
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        print("Error iniciando sesion de administracion:", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo iniciar sesion",
        )
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    respuesta.set_cookie(
        key=seg.NOMBRE_COOKIE,
        value=token,
        max_age=seg.DURACION_SESION_HORAS * 3600,
        path=RUTA_COOKIE,
        httponly=True,
        secure=True,
        samesite="strict",
    )
    return {"usuario": datos.usuario}


@router.post("/logout")
def cerrar_sesion(respuesta: Response, token: str = Cookie(default="", alias=seg.NOMBRE_COOKIE)):
    if token:
        conn = None
        cursor = None
        try:
            conn = obtener_conexion_postgres()
            cursor = conn.cursor()
            seg.cerrar_sesion(cursor, token)
            conn.commit()
        except Exception as e:
            if conn:
                conn.rollback()
            print("Error cerrando sesion de administracion:", e)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="No se pudo cerrar la sesion",
            )
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()
    respuesta.delete_cookie(key=seg.NOMBRE_COOKIE, path=RUTA_COOKIE)
    return {"ok": True}


@router.get("/sesion")
def sesion_actual(usuario: str = Depends(verificar_admin)):
    return {"usuario": usuario}
