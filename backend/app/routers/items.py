from backend.app.database import obtener_conexion
from backend.app.database_postgres import obtener_conexion_postgres
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
            SELECT a.art_cod, a.art_nombre, a.art_preciobase, t.tipoart_desc, a.art_foto
            FROM articulos a
            INNER JOIN tipo_articulo t ON a.tipoart_cod = t.tipoart_cod
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
        for art_cod, nombre, precio, tipo, foto in articulos:
            url_imagen = ""
            if foto:
                # 1. Borramos los espacios en blanco invisibles que FoxPro deja al final
                ruta_limpia = foto.strip()

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
                    url_imagen = f"https://picsum.photos{art_cod}"
            else:
                # 🌟 TRUCO DE IMAGEN: Si en la BD la imagen viene vacía o rota, le ponemos una de internet
                url_imagen =  f"https://picsum.photos{art_cod}"

            lista_articulos.append({
                "id": art_cod,
                "nombre": nombre,
                "precio": int(precio),
                "tipo": tipo,
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
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo registrar el pedido"
        )

    finally:
        if cursor:
            cursor.close()

        if conn:
            conn.close()
            



    