import os
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, status
from psycopg.errors import ForeignKeyViolation

from backend.app.database_postgres import obtener_conexion_postgres
from backend.app.schemas import ArticuloSync, ArticulosKitSync

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


SQL_VERIFICAR_KIT = "SELECT 1 FROM articulos WHERE art_cod = %s"

SQL_BORRAR_COMPONENTES_KIT = "DELETE FROM articulos_kit WHERE art_codkit = %s"

SQL_INSERTAR_COMPONENTE_KIT = """
    INSERT INTO articulos_kit (idkit, art_codkit, art_cod, art_cantidad)
    VALUES (%s, %s, %s, %s)
"""


@router.post("/articulos-kit", dependencies=[Depends(verificar_sincronizador)])
def sincronizar_articulos_kit(datos: ArticulosKitSync):
    conn = None
    cursor = None
    try:
        conn = obtener_conexion_postgres()
        cursor = conn.cursor()

        cursor.execute(SQL_VERIFICAR_KIT, (datos.art_codkit,))
        if cursor.fetchone() is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"art_codkit {datos.art_codkit} no existe en articulos",
            )

        cursor.execute(SQL_BORRAR_COMPONENTES_KIT, (datos.art_codkit,))

        for componente in datos.componentes:
            cursor.execute(SQL_INSERTAR_COMPONENTE_KIT, (
                componente.idkit,
                datos.art_codkit,
                componente.art_cod,
                componente.art_cantidad,
            ))

        conn.commit()

        return {
            "status": "ok",
            "art_codkit": datos.art_codkit,
            "version_actual": datos.version_actual,
            "componentes": len(datos.componentes),
        }

    except HTTPException:
        if conn:
            conn.rollback()
        raise
    except ForeignKeyViolation as e:
        if conn:
            conn.rollback()
        if getattr(e.diag, "constraint_name", None) == "fk_articulos_kit_componente":
            detalle = "Uno de los componentes no existe todavia en articulos"
        else:
            detalle = "Referencia relacionada al kit no existe"
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detalle)
    except Exception as e:
        if conn:
            conn.rollback()
        print("Error sincronizando articulos_kit:", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo sincronizar la composicion del kit",
        )
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
