from backend.app.database import obtener_conexion
from fastapi import HTTPException, status, APIRouter, Query
# Subimos un nivel para buscar en la app global e importar el esquema
from backend.app.schemas import PedidoEntrada


# Creamos el router para agrupar las rutas de categorías
router = APIRouter(prefix="/articulos", tags=["Articulos"])
@router.get("/")
def trae_articulos(
    pagina: int = Query(1, description="Número de página (empieza en 1)"),
    limite: int = Query(30, description="Cantidad de productos por lote"),
    categoria: str = Query("Todos", description="Categoría seleccionada por el usuario") # 🌟 NUEVO PARÁMETRO
):
    conn = None
    cursor = None
    try:
        conn = obtener_conexion()
        cursor = conn.cursor()

        # MATEMÁTICA DE SQL: Calculamos cuántos registros debemos saltearnos
        #  Ejemplo: Si estamos en la página 2 con límite 50, nos salteamos (2-1)*50 = 50 registros.
        registros_a_saltear = (pagina - 1) * limite

        if categoria == "Todos":
            sql = """select a.art_cod as id, a.art_nombre as nombre, a.art_preciobase as precio, t.TIPOART_DESC as tipo, a.art_foto as imagen
                from articulos a inner join TIPOARTICULO t
                on a.tipoart_cod = t.tipoart_cod
                where a.art_estado<>'N'
                ORDER BY a.art_cod -- Es indispensable ordenar por un campo para que la paginación sea exacta
                OFFSET ? ROWS
                FETCH NEXT ? ROWS ONLY """
            
            cursor.execute(sql, (int(registros_a_saltear), int(limite)))
        else:
            sql = """
                SELECT a.art_cod as id, a.art_nombre as nombre, a.art_preciobase as precio, t.TIPOART_DESC as tipo, a.art_foto as imagen
                FROM articulos a 
                INNER JOIN TIPOARTICULO t ON a.tipoart_cod = t.tipoart_cod
                WHERE t.TIPOART_DESC = ? -- 🌟 FILTRO DE BASE DE DATOS STRICTO
                and a.art_estado<>'N'
                ORDER BY a.art_cod 
                OFFSET ? ROWS
                FETCH NEXT ? ROWS ONLY
            """
            cursor.execute(sql, (categoria, registros_a_saltear, limite))
            
        articulos = cursor.fetchall()
        if not articulos:
            return []
       # if not articulos:
       #     raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Articulos no encontrado")
        
        lista_articulos = []
        for row in articulos:
            url_imagen = ""
            if row.imagen:
                # 1. Borramos los espacios en blanco invisibles que FoxPro deja al final
                ruta_limpia = row.imagen.strip()

                # 2. Convertimos las barras de Windows (\) a barras de red (/)
                ruta_limpia = ruta_limpia.replace("\\", "/")

                # 3. Buscamos la palabra 'frontend/' para recortar la ruta local del disco C
                if "frontend/" in ruta_limpia.lower():
                    posicion = ruta_limpia.lower().find("frontend/")
                    parte_relativa = ruta_limpia[posicion:]
                    # Queda armado como: /frontend/assets/images/ladrillo.jpg
                    url_imagen = f"/{parte_relativa}"
                else:
                    # Si tiene un texto raro que no incluye 'frontend/', ponemos una de prueba
                    url_imagen = f"https://picsum.photos{row.id}"
            else:
                # 🌟 TRUCO DE IMAGEN: Si en la BD la imagen viene vacía o rota, le ponemos una de internet
                url_imagen =  f"https://picsum.photos{row.id}"

            lista_articulos.append({
                "id": row.id,
                "nombre": row.nombre,
                "precio": row.precio,  
                "tipo": row.tipo,
                "imagen": url_imagen
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
        conn = obtener_conexion()
        cursor = conn.cursor()

        # 🌟 PASO A: Insertar la Cabecera única del Cliente
        sql_cabecera = """
            INSERT INTO pedido_cabecera (cliente_nombre, cliente_direccion, cliente_telefono)
            OUTPUT INSERTED.id_pedido
            VALUES (?, ?, ?)
        """
        cursor.execute(sql_cabecera, (pedido.cliente_nombre, pedido.cliente_direccion, pedido.cliente_telefono))
        
        # Guardamos el número de ID único que autogeneró SQL Server (El primer elemento de la fila)
        id_pedido_nuevo = cursor.fetchone()[0]

        # 🌟 PASO B: Insertar cada renglón acumulado en el Detalle
        sql_detalle = """
            INSERT INTO pedido_detalle (id_pedido, art_cod, cantidad, precio_unitario)
            VALUES (?, ?, ?, ?)
        """
        for item in pedido.productos:
            cursor.execute(sql_detalle, (id_pedido_nuevo, item.id, item.cantidad, item.precio))

        # Si todo marchó impecable en las dos tablas, guardamos en firme en SQL Server
        conn.commit()
        
        return {"status": "ok", "mensaje": "Pedido guardado con éxito", "id_pedido": id_pedido_nuevo}

    except Exception as e:
        if conn:
            conn.rollback() # Si falló a mitad de camino, deshace todo para no dejar basura
        print("Error en terminal SQL:", e)
        raise HTTPException(status_code=500, detail=f"Error en la base de datos: {str(e)}")
    
    finally:
        if conn:
            cursor.close()
            conn.close()

    