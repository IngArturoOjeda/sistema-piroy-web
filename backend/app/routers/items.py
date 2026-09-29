from pathlib import Path
from decimal import Decimal
from typing import Optional, Literal

from backend.app.database_postgres import obtener_conexion_postgres
from fastapi import HTTPException, status, APIRouter, Query
# Subimos un nivel para buscar en la app global e importar el esquema
from backend.app.schemas import PedidoEntrada


# Creamos el router para agrupar las rutas de categorías
router = APIRouter(prefix="/articulos", tags=["Articulos"])

RUTA_FRONTEND = Path(__file__).resolve().parents[3] / "frontend"
IMAGEN_SIN_FOTO = "/frontend/assets/images/sin-imagen.svg"

# Descripciones confirmadas para la unidad de venta de articulos NORMALES.
# Solo se cargan las que ya tienen un texto de negocio confirmado; cualquier
# otra unidad usa un fallback mecanico ("Por {unidad}") hasta que se confirme.
DESCRIPCIONES_UNIDAD_NORMAL = {
    "KG": "Por KG",
    "UNIDAD": "Por unidad",
}


def url_imagen_articulo(foto):
    if not foto or not foto.strip():
        return IMAGEN_SIN_FOTO

    foto = foto.strip()

    if foto.startswith("https://"):
        return foto
    if foto.startswith("http://"):
        return IMAGEN_SIN_FOTO

    ruta_limpia = foto.replace("\\", "/")
    posicion = ruta_limpia.lower().find("frontend/")
    if posicion == -1:
        return IMAGEN_SIN_FOTO

    parte_relativa = ruta_limpia[posicion:]
    archivo = (RUTA_FRONTEND.parent / parte_relativa).resolve()
    if not archivo.is_relative_to(RUTA_FRONTEND) or not archivo.is_file():
        return IMAGEN_SIN_FOTO

    return f"/{parte_relativa}"


@router.get("/")
def trae_articulos(
    pagina: int = Query(1, description="Número de página (empieza en 1)"),
    limite: int = Query(30, description="Cantidad de productos por lote"),
    categoria: str = Query("Todos", description="Categoría seleccionada por el usuario"),
    unidad: Optional[str] = Query(None, description="Filtra por unidad de venta exacta (ej: KG, BOLSA, CAJA)"),
    presentacion: Optional[Literal["NORMAL", "KIT"]] = Query(
        None,
        description="Filtra por forma de compra: NORMAL (articulos propios de la categoria) o KIT (kits relacionados por componente)"
    )
):
    conn = None
    cursor = None
    try:
        if presentacion == "KIT":
            if unidad:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="El filtro unidad no se aplica cuando presentacion=KIT"
                )
            if categoria == "Todos":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Debe indicar una categoría específica cuando presentacion=KIT"
                )

        conn = obtener_conexion_postgres()
        cursor = conn.cursor()

        registros_a_saltear = (pagina - 1) * limite

        filtro_categoria = ""
        filtro_unidad = ""
        filtro_presentacion = ""
        parametros = []

        if presentacion == "KIT":
            # Ya se valido arriba: categoria != "Todos" y unidad no informado
            filtro_presentacion = """
                AND a.art_kit = TRUE
                AND EXISTS (
                    SELECT 1
                    FROM articulos_kit ak
                    JOIN articulos comp ON comp.art_cod = ak.art_cod
                    JOIN tipo_articulo tcomp ON tcomp.tipoart_cod = comp.tipoart_cod
                    WHERE ak.art_codkit = a.art_cod
                      AND tcomp.tipoart_desc = %s
                )
            """
            parametros.append(categoria)
        else:
            if categoria != "Todos":
                filtro_categoria = "AND t.tipoart_desc = %s"
                parametros.append(categoria)
            if presentacion == "NORMAL":
                filtro_presentacion = "AND a.art_kit = FALSE"
            if unidad:
                filtro_unidad = "AND um.uni_nombre = %s"
                parametros.append(unidad)

        parametros.extend([limite, registros_a_saltear])

        sql = f"""
            SELECT
                a.art_cod, a.art_nombre, a.art_preciobase, t.tipoart_desc, a.art_foto,
                CASE
                    WHEN a.art_kit THEN COALESCE(kit.stock_disponible, 0)
                    ELSE COALESCE(s.cantidad, 0)
                END AS stock_disponible,
                um.uni_nombre AS unidad_venta,
                COALESCE(um.fraccionable, FALSE) AS fraccionable
            FROM articulos a
            INNER JOIN tipo_articulo t ON a.tipoart_cod = t.tipoart_cod
            LEFT JOIN stock s ON s.art_cod = a.art_cod
            LEFT JOIN unidad_medida um ON um.uni_cod = a.uni_cod_ven
            LEFT JOIN LATERAL (
                SELECT GREATEST(
                    MIN(
                        CASE
                            WHEN ak.art_cantidad <= 0 THEN 0
                            ELSE FLOOR(COALESCE(sc.cantidad, 0) / ak.art_cantidad)
                        END
                    ),
                    0
                ) AS stock_disponible
                FROM articulos_kit ak
                LEFT JOIN stock sc ON sc.art_cod = ak.art_cod
                WHERE ak.art_codkit = a.art_cod
            ) kit ON a.art_kit = TRUE
            WHERE a.art_estado = 'S'
              AND a.llevar_web = TRUE
              AND a.mostrar_web = TRUE
              {filtro_categoria}
              {filtro_unidad}
              {filtro_presentacion}
            ORDER BY a.art_cod
            LIMIT %s OFFSET %s
        """
        cursor.execute(sql, parametros)
            
        articulos = cursor.fetchall()
        if not articulos:
            return []

        lista_articulos = []
        for art_cod, nombre, precio, tipo, foto, stock_disponible, unidad_venta, fraccionable in articulos:
            lista_articulos.append({
                "id": art_cod,
                "nombre": nombre,
                "precio": int(precio),
                "tipo": tipo,
                "imagen": url_imagen_articulo(foto),
                "stock_disponible": float(stock_disponible),
                "unidad_venta": unidad_venta,
                "fraccionable": bool(fraccionable)
            })
        return lista_articulos

    except HTTPException:
        raise
    except Exception as e:
        print(e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error al obtener articulos")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@router.get("/presentaciones")
def trae_presentaciones(
    categoria: str = Query(..., description="Categoria para la cual se buscan las formas de compra disponibles")
):
    conn = None
    cursor = None
    try:
        conn = obtener_conexion_postgres()
        cursor = conn.cursor()

        sql_normales = """
            SELECT DISTINCT um.uni_nombre
            FROM articulos a
            JOIN tipo_articulo t ON t.tipoart_cod = a.tipoart_cod
            LEFT JOIN unidad_medida um ON um.uni_cod = a.uni_cod_ven
            WHERE t.tipoart_desc = %s
              AND a.art_estado = 'S'
              AND a.llevar_web = TRUE
              AND a.mostrar_web = TRUE
              AND a.art_kit = FALSE
        """
        cursor.execute(sql_normales, (categoria,))
        unidades_normales = [fila[0] for fila in cursor.fetchall()]

        if None in unidades_normales:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=(
                    f"Hay artículos normales sin unidad de venta asignada en "
                    f"la categoría '{categoria}'"
                )
            )

        sql_kit_existe = """
            SELECT EXISTS (
                SELECT 1
                FROM articulos kit
                JOIN articulos_kit ak ON ak.art_codkit = kit.art_cod
                JOIN articulos comp ON comp.art_cod = ak.art_cod
                JOIN tipo_articulo tcomp ON tcomp.tipoart_cod = comp.tipoart_cod
                WHERE kit.art_kit = TRUE
                  AND kit.art_estado = 'S'
                  AND kit.llevar_web = TRUE
                  AND kit.mostrar_web = TRUE
                  AND tcomp.tipoart_desc = %s
            )
        """
        cursor.execute(sql_kit_existe, (categoria,))
        hay_kit = cursor.fetchone()[0]

        presentaciones = []

        for unidad_normal in sorted(unidades_normales):
            presentaciones.append({
                "codigo": "NORMAL",
                "unidad": unidad_normal,
                "descripcion": DESCRIPCIONES_UNIDAD_NORMAL.get(unidad_normal, f"Por {unidad_normal}")
            })

        if hay_kit:
            presentaciones.append({
                "codigo": "KIT",
                "descripcion": "Por presentación"
            })

        return presentaciones

    except HTTPException:
        raise
    except Exception as e:
        print(e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error al obtener presentaciones")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@router.post("/confirmar-pedido")
def confirmar_pedido(pedido: PedidoEntrada):
    conn = None
    cursor = None
    try:
        if not pedido.productos:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El pedido debe contener al menos un artículo"
            )

        ids_pedido = [item.id for item in pedido.productos]
        if len(ids_pedido) != len(set(ids_pedido)):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El pedido contiene artículos duplicados"
            )

        conn = obtener_conexion_postgres()
        cursor = conn.cursor()

        # FASE 1: metadatos de los articulos del pedido (existencia/publicado, precio, tipo)
        sql_articulos = """
            SELECT
                a.art_cod,
                a.art_nombre,
                a.art_preciobase,
                a.art_kit,
                COALESCE(um.fraccionable, FALSE) AS fraccionable
            FROM articulos a
            LEFT JOIN unidad_medida um ON um.uni_cod = a.uni_cod_ven
            WHERE a.art_cod = ANY(%s)
              AND a.art_estado = 'S'
              AND a.llevar_web = TRUE
              AND a.mostrar_web = TRUE
        """
        cursor.execute(sql_articulos, (ids_pedido,))
        articulos_por_id = {
            art_cod: {
                "art_nombre": art_nombre,
                "art_preciobase": art_preciobase,
                "art_kit": art_kit,
                "fraccionable": fraccionable,
            }
            for art_cod, art_nombre, art_preciobase, art_kit, fraccionable in cursor.fetchall()
        }

        # FASE 2: existencia + tipo de cantidad, y consumo fisico directo de los NO-kit
        consumo_fisico = {}
        ids_kit_en_pedido = []

        for item in pedido.productos:
            articulo = articulos_por_id.get(item.id)
            if articulo is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"El artículo {item.id} no está disponible"
                )

            if not articulo["fraccionable"] and (item.cantidad < 1 or item.cantidad % 1 != 0):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"El artículo '{articulo['art_nombre']}' no admite cantidades fraccionarias"
                )

            if articulo["art_kit"]:
                ids_kit_en_pedido.append(item.id)
            else:
                consumo_fisico[item.id] = consumo_fisico.get(item.id, Decimal(0)) + item.cantidad

        # FASE 3: composicion de TODOS los kits del pedido, en una sola consulta batch
        componentes_por_kit = {}
        if ids_kit_en_pedido:
            sql_componentes = """
                SELECT art_codkit, art_cod, art_cantidad
                FROM articulos_kit
                WHERE art_codkit = ANY(%s)
            """
            cursor.execute(sql_componentes, (ids_kit_en_pedido,))
            for art_codkit, art_cod_componente, art_cantidad in cursor.fetchall():
                componentes_por_kit.setdefault(art_codkit, []).append((art_cod_componente, art_cantidad))

        # FASE 4: expandir cada kit pedido a consumo fisico de sus componentes
        for item in pedido.productos:
            articulo = articulos_por_id[item.id]
            if not articulo["art_kit"]:
                continue

            componentes = componentes_por_kit.get(item.id, [])
            if not componentes:
                # Inconsistencia interna: un kit publicado sin composicion configurada
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"El kit '{articulo['art_nombre']}' no tiene componentes configurados"
                )

            for art_cod_componente, art_cantidad in componentes:
                if art_cantidad <= 0:
                    # Inconsistencia interna: composicion de kit mal cargada
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=f"El kit '{articulo['art_nombre']}' tiene una composición inválida"
                    )
                consumo_fisico[art_cod_componente] = (
                    consumo_fisico.get(art_cod_componente, Decimal(0))
                    + item.cantidad * art_cantidad
                )

        # FASE 5: stock fisico real + nombre + deteccion de kit anidado, en una sola consulta batch
        ids_fisicos = list(consumo_fisico.keys())
        sql_stock_fisico = """
            SELECT a.art_cod, a.art_nombre, a.art_kit, COALESCE(s.cantidad, 0)
            FROM articulos a
            LEFT JOIN stock s ON s.art_cod = a.art_cod
            WHERE a.art_cod = ANY(%s)
        """
        cursor.execute(sql_stock_fisico, (ids_fisicos,))
        info_fisicos = {
            art_cod: {"art_nombre": art_nombre, "art_kit": art_kit, "stock": stock}
            for art_cod, art_nombre, art_kit, stock in cursor.fetchall()
        }

        faltantes = set(ids_fisicos) - set(info_fisicos.keys())
        if faltantes:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Configuración inconsistente: los artículos {sorted(faltantes)} no existen"
            )

        for art_cod, consumo in consumo_fisico.items():
            info = info_fisicos[art_cod]
            if info["art_kit"]:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Configuración inválida: el artículo '{info['art_nombre']}' es un kit anidado dentro de otro kit"
                )
            if consumo > info["stock"]:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Stock insuficiente de '{info['art_nombre']}' para completar el pedido"
                )

        # Recien ahora, con TODO validado (fases 1 a 5 completas), se escribe algo

        sql_cabecera = """
            INSERT INTO pedido_cabecera (cliente_nombre, cliente_direccion, cliente_telefono)
            VALUES (%s, %s, %s)
            RETURNING id_pedido
        """
        cursor.execute(sql_cabecera, (pedido.cliente_nombre, pedido.cliente_direccion, pedido.cliente_telefono))
        id_pedido_nuevo = cursor.fetchone()[0]

        sql_detalle = """
            INSERT INTO pedido_detalle (id_pedido, art_cod, cantidad, precio_unitario)
            VALUES (%s, %s, %s, %s)
        """
        for item in pedido.productos:
            articulo = articulos_por_id[item.id]
            cursor.execute(
                sql_detalle,
                (id_pedido_nuevo, item.id, item.cantidad, articulo["art_preciobase"])
            )

        conn.commit()

        return {"status": "ok", "mensaje": "Pedido guardado con éxito", "id_pedido": id_pedido_nuevo}

    except HTTPException:
        if conn:
            conn.rollback()
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        print("Error en terminal SQL:", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo registrar el pedido"
        )

    finally:
        if cursor:
            cursor.close()

        if conn:
            conn.close()
            



    