from fastapi import APIRouter, HTTPException, status
from backend.app.database_postgres import obtener_conexion_postgres
from backend.app.sql_catalogo import SQL_TIPO_CON_ARTICULOS

# Creamos el router para agrupar las rutas de categorías
router = APIRouter(prefix="/categorias", tags=["Categorias"])

# Menú de la tienda: solo tipos que el administrador no ocultó y que tienen algo para mostrar
# (los kits por presentación cuentan en el tipo de su componente: ver sql_catalogo.py).
SQL_CATEGORIAS_VISIBLES = f"""
    SELECT t.tipoart_cod, t.tipoart_desc
    FROM tipo_articulo t
    WHERE t.mostrar_web = TRUE
      AND {SQL_TIPO_CON_ARTICULOS}
    ORDER BY t.tipoart_cod
"""


@router.get("/")
def listar_categorias():
    conn = None
    cursor = None
    try:
         # 1. Abrimos la conexión a PostgreSQL
        conn = obtener_conexion_postgres()
        cursor = conn.cursor()

        # 2. Tipos visibles (no ocultos por el administrador y con artículos para mostrar)
        cursor.execute(SQL_CATEGORIAS_VISIBLES)
        filas = cursor.fetchall()

        # 3. Transformamos los datos en una lista limpia
        categorias = []
        for fila in filas:
            categorias.append({
                "id":fila[0],
                "nombre":fila[1]
            })

        return categorias
    except HTTPException:
        raise
    except Exception as e:
        print(e) # Para que puedas ver el error en la terminal si algo falla
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f"No se pudieron cargar las categorías")
    finally:
        # 4. Cerramos la conexión y devolvemos el resultado
        if cursor:
            cursor.close()

        if conn:
            conn.close()
