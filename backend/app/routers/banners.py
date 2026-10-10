from fastapi import APIRouter, HTTPException, Response, status

from backend.app.database_postgres import obtener_conexion_postgres

router = APIRouter(prefix="/banners", tags=["Banners"])


@router.get("/")
def listar_banners(response: Response):
    conn = None
    cursor = None
    try:
        conn = obtener_conexion_postgres()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, imagen_url, alt FROM banners WHERE activo ORDER BY orden, id"
        )
        # Sin cache: un banner desactivado debe dejar de verse enseguida.
        response.headers["Cache-Control"] = "no-store"
        return [{"id": f[0], "imagen_url": f[1], "alt": f[2]} for f in cursor.fetchall()]
    except Exception as e:
        print("Error listando banners:", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudieron cargar los banners",
        )
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
