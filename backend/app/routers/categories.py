from fastapi import APIRouter, HTTPException, status
from backend.app.database_postgres import obtener_conexion_postgres

# Creamos el router para agrupar las rutas de categorías
router = APIRouter(prefix="/categorias", tags=["Categorias"])

# Un tipo tiene artículos que mostrar cuando su página de categoría no quedaría vacía: o tiene
# artículos normales publicados, o hay kits PRESENTACION publicados con componentes de ese tipo
# (es lo mismo que decide /api/articulos/presentaciones). Los COMBO no cuentan: tienen su propia vista.
# Se usa también en el panel de administración para avisar qué tipos no aparecen en el menú.
SQL_TIPO_CON_ARTICULOS = """
    (
        EXISTS (
            SELECT 1
            FROM articulos a
            WHERE a.tipoart_cod = t.tipoart_cod
              AND a.art_estado = 'S'
              AND a.llevar_web = TRUE
              AND a.mostrar_web = TRUE
              AND a.art_kit = FALSE
        )
        OR EXISTS (
            SELECT 1
            FROM articulos kit
            JOIN tipo_articulo tkit ON tkit.tipoart_cod = kit.tipoart_cod
            JOIN articulos_kit ak ON ak.art_codkit = kit.art_cod
            JOIN articulos comp ON comp.art_cod = ak.art_cod
            WHERE comp.tipoart_cod = t.tipoart_cod
              AND kit.art_kit = TRUE
              AND kit.tipo_kit = 'PRESENTACION'
              AND kit.art_estado = 'S'
              AND kit.llevar_web = TRUE
              AND kit.mostrar_web = TRUE
              AND tkit.mostrar_web = TRUE
        )
    )
"""

# Menú de la tienda: solo tipos que el administrador no ocultó y que tienen algo para mostrar.
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
