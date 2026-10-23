import os
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, status
from psycopg.errors import ForeignKeyViolation

from backend.app.database_postgres import obtener_conexion_postgres
from backend.app.schemas import ArticuloSync, ArticulosKitSync, CatalogosSync, StockSync

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
         art_kit, tipo_kit, uni_cod_com, uni_cod_ven)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (art_cod) DO UPDATE SET
        art_nombre     = EXCLUDED.art_nombre,
        art_preciobase = EXCLUDED.art_preciobase,
        tipoart_cod    = EXCLUDED.tipoart_cod,
        art_foto       = EXCLUDED.art_foto,
        art_estado     = EXCLUDED.art_estado,
        llevar_web     = EXCLUDED.llevar_web,
        art_kit        = EXCLUDED.art_kit,
        tipo_kit       = EXCLUDED.tipo_kit,
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
            articulo.tipo_kit,
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


SQL_OBTENER_ART_KIT = "SELECT art_kit FROM articulos WHERE art_cod = %s"

SQL_UPSERT_STOCK = """
    INSERT INTO stock (art_cod, cantidad)
    VALUES (%s, %s)
    ON CONFLICT (art_cod) DO UPDATE SET
        cantidad = EXCLUDED.cantidad
    RETURNING art_cod
"""


@router.post("/stock", dependencies=[Depends(verificar_sincronizador)])
def sincronizar_stock(datos: StockSync):
    conn = None
    cursor = None
    try:
        conn = obtener_conexion_postgres()
        cursor = conn.cursor()

        cursor.execute(SQL_OBTENER_ART_KIT, (datos.art_cod,))
        fila = cursor.fetchone()
        if fila is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"art_cod {datos.art_cod} no existe en articulos",
            )
        if fila[0]:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"art_cod {datos.art_cod} es un kit, no tiene stock fisico propio",
            )

        cursor.execute(SQL_UPSERT_STOCK, (datos.art_cod, datos.cantidad))
        art_cod_guardado = cursor.fetchone()[0]
        conn.commit()

        return {
            "status": "ok",
            "art_cod": art_cod_guardado,
            "version_actual": datos.version_actual,
        }

    except HTTPException:
        if conn:
            conn.rollback()
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        print("Error sincronizando stock:", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo sincronizar el stock",
        )
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# Tipos y unidades: el sistema local manda la lista completa; aca solo se crean los que faltan y se
# actualiza el nombre. NO se tocan tipo_articulo.mostrar_web ni unidad_medida.fraccionable (se deciden
# en el panel) y nunca se borra nada. Una unidad nueva empieza como no fraccionable.
SQL_UPSERT_TIPO = """
    INSERT INTO tipo_articulo (tipoart_cod, tipoart_desc)
    VALUES (%s, %s)
    ON CONFLICT (tipoart_cod) DO UPDATE SET
        tipoart_desc = EXCLUDED.tipoart_desc
"""

SQL_UPSERT_UNIDAD = """
    INSERT INTO unidad_medida (uni_cod, uni_nombre, fraccionable)
    VALUES (%s, %s, FALSE)
    ON CONFLICT (uni_cod) DO UPDATE SET
        uni_nombre = EXCLUDED.uni_nombre
"""


@router.post("/catalogos", dependencies=[Depends(verificar_sincronizador)])
def sincronizar_catalogos(datos: CatalogosSync):
    conn = None
    cursor = None
    try:
        conn = obtener_conexion_postgres()
        cursor = conn.cursor()

        for tipo in datos.tipos:
            cursor.execute(SQL_UPSERT_TIPO, (tipo.tipoart_cod, tipo.tipoart_desc))
        for unidad in datos.unidades:
            cursor.execute(SQL_UPSERT_UNIDAD, (unidad.uni_cod, unidad.uni_nombre))
        conn.commit()

        return {
            "status": "ok",
            "tipos": len(datos.tipos),
            "unidades": len(datos.unidades),
        }

    except Exception as e:
        if conn:
            conn.rollback()
        print("Error sincronizando catalogos:", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudieron sincronizar los tipos y unidades",
        )
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# Pedidos de la web que el sincronizador baja al sistema local. Render solo entrega los PENDIENTE y los marca
# RECIBIDO cuando el sincronizador confirma que ya los guardo en SQL Server. Marcar dos veces no hace dano.
SQL_PEDIDOS_PENDIENTES = """
    SELECT id_pedido, cliente_nombre, cliente_direccion, cliente_telefono, fecha_pedido
    FROM pedido_cabecera
    WHERE estado_sync = 'PENDIENTE' AND id_pedido > %s
    ORDER BY id_pedido
    LIMIT %s
"""

SQL_DETALLE_PEDIDOS = """
    SELECT id_pedido, art_cod, cantidad, precio_unitario
    FROM pedido_detalle
    WHERE id_pedido = ANY(%s)
    ORDER BY id_pedido, id_detalle
"""

SQL_MARCAR_PEDIDO_RECIBIDO = """
    UPDATE pedido_cabecera
    SET estado_sync = 'RECIBIDO',
        fecha_sincronizacion = COALESCE(fecha_sincronizacion, now())
    WHERE id_pedido = %s
    RETURNING id_pedido
"""


@router.get("/pedidos-pendientes", dependencies=[Depends(verificar_sincronizador)])
def listar_pedidos_pendientes(
    limite: int = Query(default=50, ge=1, le=200),
    despues_de: int = Query(default=0, ge=0, lt=2**63),
):
    conn = None
    cursor = None
    try:
        conn = obtener_conexion_postgres()
        cursor = conn.cursor()

        cursor.execute(SQL_PEDIDOS_PENDIENTES, (despues_de, limite))
        cabeceras = cursor.fetchall()
        pedidos = {}
        for id_pedido, nombre, direccion, telefono, fecha in cabeceras:
            pedidos[id_pedido] = {
                "id_pedido": id_pedido,
                "cliente_nombre": nombre,
                "cliente_direccion": direccion,
                "cliente_telefono": telefono,
                "fecha_pedido": fecha.isoformat(),
                "detalle": [],
            }

        if pedidos:
            cursor.execute(SQL_DETALLE_PEDIDOS, (list(pedidos),))
            for id_pedido, art_cod, cantidad, precio in cursor.fetchall():
                pedidos[id_pedido]["detalle"].append({
                    "art_cod": art_cod,
                    "cantidad": float(cantidad),
                    "precio_unitario": float(precio),
                })

        return {"status": "ok", "pedidos": list(pedidos.values())}

    except Exception as e:
        print("Error listando pedidos pendientes:", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudieron leer los pedidos pendientes",
        )
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@router.post("/pedidos/{id_pedido}/recibido", dependencies=[Depends(verificar_sincronizador)])
def marcar_pedido_recibido(id_pedido: int = Path(gt=0, lt=2**63)):
    conn = None
    cursor = None
    try:
        conn = obtener_conexion_postgres()
        cursor = conn.cursor()

        cursor.execute(SQL_MARCAR_PEDIDO_RECIBIDO, (id_pedido,))
        if cursor.fetchone() is None:
            conn.rollback()
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"El pedido {id_pedido} no existe",
            )
        conn.commit()

        return {"status": "ok", "id_pedido": id_pedido}

    except HTTPException:
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        print("Error marcando pedido recibido:", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo marcar el pedido como recibido",
        )
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
