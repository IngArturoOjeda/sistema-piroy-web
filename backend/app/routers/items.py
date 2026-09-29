from pathlib import Path

from backend.app.database_postgres import obtener_conexion_postgres
from fastapi import HTTPException, status, APIRouter, Query
# Subimos un nivel para buscar en la app global e importar el esquema
from backend.app.schemas import PedidoEntrada


# Creamos el router para agrupar las rutas de categorías
router = APIRouter(prefix="/articulos", tags=["Articulos"])

RUTA_FRONTEND = Path(__file__).resolve().parents[3] / "frontend"
IMAGEN_SIN_FOTO = "/frontend/assets/images/sin-imagen.svg"


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
    categoria: str = Query("Todos", description="Categoría seleccionada por el usuario") # 🌟 NUEVO PARÁMETRO
):
    conn = None
    cursor = None
    try:
        conn = obtener_conexion_postgres()
        cursor = conn.cursor()

        registros_a_saltear = (pagina - 1) * limite

        filtro_categoria = ""
        parametros = []
        if categoria != "Todos":
            filtro_categoria = "AND t.tipoart_desc = %s"
            parametros.append(categoria)
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

        sql_articulos = """
            SELECT
                a.art_cod,
                a.art_nombre,
                a.art_preciobase,
                a.art_kit,
                COALESCE(um.fraccionable, FALSE) AS fraccionable,
                CASE
                    WHEN a.art_kit THEN COALESCE(kit.stock_disponible, 0)
                    ELSE COALESCE(s.cantidad, 0)
                END AS stock_disponible
            FROM articulos a
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
                "stock_disponible": stock_disponible,
            }
            for art_cod, art_nombre, art_preciobase, art_kit, fraccionable, stock_disponible in cursor.fetchall()
        }

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

            if item.cantidad > articulo["stock_disponible"]:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Stock insuficiente para el artículo '{articulo['art_nombre']}'"
                )

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
            



    