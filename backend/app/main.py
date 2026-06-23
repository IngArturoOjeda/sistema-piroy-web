from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
# Importamos únicamente el router de categorías
from backend.app.routers.categories import router as categorias_router
from backend.app.routers.items import router as articulos_router
app = FastAPI()

# 1. CONFIGURACIÓN DE RUTAS LOCALES
RUTA_FRONTEND = "C:/Ferreteria_WEB/frontend"

# 2. PUENTE DE ARCHIVOS ESTÁTICOS (CSS, JS, IMÁGENES)
app.mount("/frontend", StaticFiles(directory=RUTA_FRONTEND), name="frontend")


# 3. ENLACE DE ROUTERS (Aquí es donde FastAPI mágicamente activa tus consultas a SQL Server)
# Le agregamos el prefijo '/api' aquí de forma global para que coincida con tu main.js
app.include_router(categorias_router, prefix="/api")
app.include_router(articulos_router, prefix="/api")

# 4. ENDPOINT PARA MOSTRAR LA PÁGINA WEB PRINCIPAL
@app.get("/")
async def read_index():
    ruta_index = f"{RUTA_FRONTEND}/index.html"
    return FileResponse(ruta_index)
