from fastapi import APIRouter, HTTPException, status
from backend.app.database import obtener_conexion

# Creamos el router para agrupar las rutas de categorías
router = APIRouter(prefix="/categorias", tags=["Categorias"])

@router.get("/")
def listar_categorias():
    conn = None 
    cursor = None
    try:
         # 1. Abrimos la conexión a SQL Server
        conn = obtener_conexion()
        cursor = conn.cursor()

        # 2. Hacemos la consulta a tu tabla (Asegúrate de que se llame TipoArticulo)
        sql =  "select tipoart_cod, tipoart_desc from tipoarticulo"

        cursor.execute(sql)
        filas = cursor.fetchall()

        # 3. Transformamos los datos en una lista limpia
        categorias = []
        for fila in filas:
            categorias.append({
                "id":fila.tipoart_cod,
                "nombre":fila.tipoart_desc
            })

        if not categorias:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No se pudo obtener Tipo de Articulos");
     
        return categorias
    except HTTPException:
        raise     
    except Exception as e:
        print(e) # Para que puedas ver el error en la terminal si algo falla
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f"Error en la base de datos: {str(e)}")
    finally:
        # 4. Cerramos la conexión y devolvemos el resultado
        if cursor:
            cursor.close()

        if conn:     
            conn.close()             
