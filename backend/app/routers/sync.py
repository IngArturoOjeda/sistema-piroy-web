import os
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, status
from psycopg.errors import ForeignKeyViolation

from backend.app.database_postgres import obtener_conexion_postgres
from backend.app.schemas import ArticuloSync

router = APIRouter(prefix="/sync", tags=["Sincronizacion"])


def verificar_sincronizador(x_api_key: str = Header(default="")):
    esperada = os.getenv("SYNC_API_KEY")
    if not esperada:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Sincronizacion no configurada",
        )
    if not secrets.compare_digest(x_api_key.encode(), esperada.encode()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No autorizado",
        )


SQL_UPSERT_ARTICULO = """
    INSERT INTO articulos
        (art_cod, art_nombre, art_preciobase, tipoart_cod, art_foto, art_estado, llevar_web)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (art_cod) DO UPDATE SET
        art_nombre     = EXCLUDED.art_nombre,
        art_preciobase = EXCLUDED.art_preciobase,
        tipoart_cod    = EXCLUDED.tipoart_cod,
        art_foto       = EXCLUDED.art_foto,
        art_estado     = EXCLUDED.art_estado,
        llevar_web     = EXCLUDED.llevar_web
    RETURNING art_cod
"""


@router.post("/articulos", dependencies=[Depends(verificar_sincronizador)])
def sincronizar_articulo(articulo: ArticuloSync):
    conn = None
    cursor = None
    try:
        conn = obtener_conexion_postgres()
        cursor = conn.cursor()

        cursor.execute(SQL_UPSERT_ARTICULO, (
            articulo.art_cod,
            articulo.art_nombre,
            articulo.art_preciobase,
            articulo.tipoart_cod,
            articulo.art_foto,
            articulo.art_estado,
            articulo.llevar_web,
        ))
        art_cod_guardado = cursor.fetchone()[0]
        conn.commit()

        return {
            "status": "ok",
            "art_cod": art_cod_guardado,
            "version_actual": articulo.version_actual,
        }

    except ForeignKeyViolation:
        if conn:
            conn.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"tipoart_cod {articulo.tipoart_cod} no existe en tipo_articulo",
        )
    except Exception as e:
        if conn:
            conn.rollback()
        print("Error sincronizando articulo:", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo sincronizar el articulo",
        )
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
