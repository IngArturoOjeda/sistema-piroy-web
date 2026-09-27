import os
import secrets
from io import BytesIO

import cloudinary
import cloudinary.uploader
from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, UploadFile, status

from backend.app.database_postgres import obtener_conexion_postgres
from backend.app.schemas import MostrarWebEntrada

router = APIRouter(prefix="/admin", tags=["Administracion"])

CARPETA_CLOUDINARY = "agrovetzo/productos"
TAMANO_MAXIMO_BYTES = 5 * 1024 * 1024  # 5 MB

FIRMAS_PERMITIDAS = {
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/webp": (b"RIFF",),
}


def verificar_admin(x_admin_key: str = Header(default="")):
    esperada = os.getenv("ADMIN_API_KEY")
    if not esperada:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Administracion no configurada",
        )
    if not secrets.compare_digest(x_admin_key.encode(), esperada.encode()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No autorizado",
        )


def validar_imagen(contenido: bytes, content_type: str):
    firmas = FIRMAS_PERMITIDAS.get(content_type)
    if firmas is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Formato no permitido. Use jpg, jpeg, png o webp",
        )
    if not contenido.startswith(firmas):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="El archivo no parece ser una imagen valida",
        )
    if content_type == "image/webp" and contenido[8:12] != b"WEBP":
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="El archivo no parece ser una imagen valida",
        )


def configurar_cloudinary():
    cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME")
    api_key = os.getenv("CLOUDINARY_API_KEY")
    api_secret = os.getenv("CLOUDINARY_API_SECRET")

    if not cloud_name or not api_key or not api_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cloudinary no configurado",
        )

    cloudinary.config(
        cloud_name=cloud_name,
        api_key=api_key,
        api_secret=api_secret,
        secure=True,
    )


@router.get("/articulos", dependencies=[Depends(verificar_admin)])
def buscar_articulos_admin(
    buscar: str = Query(..., min_length=1, description="Texto o codigo a buscar")
):
    conn = None
    cursor = None
    try:
        conn = obtener_conexion_postgres()
        cursor = conn.cursor()

        buscar_limpio = buscar.strip()
        parametros = [f"%{buscar_limpio}%"]

        filtro_codigo = ""
        if buscar_limpio.isdigit():
            filtro_codigo = "OR a.art_cod = %s"
            parametros.append(int(buscar_limpio))

        sql = f"""
            SELECT a.art_cod, a.art_nombre, a.art_preciobase, t.tipoart_desc,
                   a.art_foto, a.art_estado, a.llevar_web, a.mostrar_web
            FROM articulos a
            INNER JOIN tipo_articulo t ON a.tipoart_cod = t.tipoart_cod
            WHERE a.art_nombre ILIKE %s
              {filtro_codigo}
            ORDER BY a.art_cod
            LIMIT 20
        """
        cursor.execute(sql, parametros)
        filas = cursor.fetchall()

        return [
            {
                "art_cod": r[0],
                "art_nombre": r[1],
                "art_preciobase": int(r[2]),
                "tipoart_desc": r[3],
                "art_foto": r[4],
                "art_estado": r[5],
                "llevar_web": r[6],
                "mostrar_web": r[7],
            }
            for r in filas
        ]
    except HTTPException:
        raise
    except Exception as e:
        print("Error buscando articulos (admin):", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo buscar articulos",
        )
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@router.patch("/articulos/{art_cod}/mostrar-web", dependencies=[Depends(verificar_admin)])
def actualizar_mostrar_web(art_cod: int, datos: MostrarWebEntrada):
    conn = None
    cursor = None
    try:
        conn = obtener_conexion_postgres()
        cursor = conn.cursor()

        cursor.execute(
            "UPDATE articulos SET mostrar_web = %s WHERE art_cod = %s",
            (datos.mostrar_web, art_cod),
        )
        if cursor.rowcount == 0:
            conn.rollback()
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"art_cod {art_cod} no existe",
            )
        conn.commit()

        return {"status": "ok", "art_cod": art_cod, "mostrar_web": datos.mostrar_web}

    except HTTPException:
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        print("Error actualizando mostrar_web:", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo actualizar mostrar_web",
        )
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@router.post("/articulos/{art_cod}/imagen", dependencies=[Depends(verificar_admin)])
async def subir_imagen_articulo(art_cod: int, archivo: UploadFile = File(...)):
    conn = None
    cursor = None
    try:
        conn = obtener_conexion_postgres()
        cursor = conn.cursor()

        cursor.execute("SELECT 1 FROM articulos WHERE art_cod = %s", (art_cod,))
        if cursor.fetchone() is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"art_cod {art_cod} no existe",
            )

        contenido = await archivo.read(TAMANO_MAXIMO_BYTES + 1)
        if len(contenido) > TAMANO_MAXIMO_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="La imagen supera el tamano maximo de 5 MB",
            )

        validar_imagen(contenido, archivo.content_type)

        configurar_cloudinary()

        archivo_memoria = BytesIO(contenido)
        archivo_memoria.name = archivo.filename or "imagen"

        public_id = f"{CARPETA_CLOUDINARY}/articulo_{art_cod}"
        try:
            resultado = cloudinary.uploader.upload(
                archivo_memoria,
                public_id=public_id,
                overwrite=True,
            )
        except Exception as e:
            print("Error subiendo a Cloudinary:", e)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="No se pudo subir la imagen a Cloudinary",
            )

        secure_url = resultado["secure_url"]

        cursor.execute(
            "UPDATE articulos SET art_foto = %s WHERE art_cod = %s",
            (secure_url, art_cod),
        )
        conn.commit()

        return {"status": "ok", "art_cod": art_cod, "art_foto": secure_url}

    except HTTPException:
        if conn:
            conn.rollback()
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        print("Error subiendo imagen de articulo:", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo actualizar la imagen del articulo",
        )
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
