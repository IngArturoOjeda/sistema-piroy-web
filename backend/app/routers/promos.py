from backend.app.database import obtener_conexion
from fastapi import HTTPException, status, APIRouter, Query

router = APIRouter(prefix="/promos", tags=["Promos"])

@router.get("/")
def trae_promos():
    conn = None
    cursor = None

    try:
        conn = obtener_conexion()
        cursor = conn.cursor()

        sql = """
            SELECT a.art_cod as id, a.art_nombre as nombre, p.art_valor as precio, t.TIPOART_DESC as tipo, a.art_foto as imagen
                FROM articulos a 
                INNER JOIN TIPOARTICULO t ON a.tipoart_cod = t.tipoart_cod
                INNER JOIN PROMOCION p ON a.art_cod = p.art_cod
                where cast(getdate() as date) > = p.fec_desde and cast(GETDATE() as date) < = p.fec_hasta
                ORDER BY a.art_cod
        """

        cursor.execute(sql)
        promociones = cursor.fetchall()
        if not promociones:
            return []
        
        lista_promos = []
        for row in promociones:
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
                    url_imagen = f"/{parte_relativa}"
                else:
                    # Si tiene un texto raro que no incluye 'frontend/', ponemos una de prueba
                    url_imagen = f"https://picsum.photos{row.id}"
            else:
                # 🌟 TABULACIÓN CORREGIDA: Este else ahora está perfectamente alineado con el 'if row.imagen'
                url_imagen = f"https://picsum.photos{row.id}"

            lista_promos.append({
               "id": row.id,
               "nombre": row.nombre,
               "precio": row.precio,
               "tipo": row.tipo,
               "imagen": url_imagen     
            })
        return lista_promos
    except HTTPException:
        raise
    except Exception as e:
        print(e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error al obtener articulos")
    finally:
        if conn:
            cursor.close()
            conn.close()
