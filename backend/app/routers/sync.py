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
        (art_cod, art_nombre, art_preciobase, tipoart_cod, art_foto, art_estado, llevar_web,
         art_kit, uni_cod_com, uni_cod_ven)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (art_cod) DO UPDATE SET
        art_nombre     = EXCLUDED.art_nombre,
        art_preciobase = EXCLUDED.art_preciobase,
        tipoart_cod    = EXCLUDED.tipoart_cod,
        art_foto       = EXCLUDED.art_foto,
        art_estado     = EXCLUDED.art_estado,
        llevar_web     = EXCLUDED.llevar_web,
        art_kit        = EXCLUDED.art_kit,
        uni_cod_com    = EXCLUDED.uni_cod_com,
        uni_cod_ven    = EXCLUDED.uni_cod_ven
    RETURNING art_cod
"""

MENSAJES_FK_ARTICULOS = {
    "fk_articulos_tipo_articulo": "tipoart_cod {valor} no existe en tipo_articulo",
    "fk_articulos_unidad_com": "uni_cod_com {valor} no existe en unidad_medida",
    "fk_articulos_unidad_ven": "uni_cod_ven {valor} no existe en unidad_medida",
}


def mensaje_para_violacion_fk(error, articulo):
    valores_por_constraint = {
        "fk_articulos_tipo_articulo": articulo.tipoart_cod,
        "fk_articulos_unidad_com": articulo.uni_cod_com,
        "fk_articulos_unidad_ven": articulo.uni_cod_ven,
    }
    nombre_constraint = getattr(error.diag, "constraint_name", None)
    plantilla = MENSAJES_FK_ARTICULOS.get(nombre_constraint)
    if plantilla is None:
        return "Referencia relacionada al articulo no existe"
    return plantilla.format(valor=valores_por_constraint.get(nombre_constraint))


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
            articulo.art_kit,
            articulo.uni_cod_com,
            articulo.uni_cod_ven,
        ))
        art_cod_guardado = cursor.fetchone()[0]
        conn.commit()

        return {
            "status": "ok",
            "art_cod": art_cod_guardado,
            "version_actual": articulo.version_actual,
        }

    except ForeignKeyViolation as e:
        if conn:
            conn.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=mensaje_para_violacion_fk(e, articulo),
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
