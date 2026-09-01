from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
# Importamos únicamente el router de categorías
from backend.app.routers.categories import router as categorias_router
from backend.app.routers.items import router as articulos_router
from backend.app.routers.promos import router as promos_router
app = FastAPI()

RUTA_PROYECTO = Path(__file__).resolve().parents[2]  # Ruta del proyecto
RUTA_FRONTEND = RUTA_PROYECTO / "frontend"  # Ruta del frontend
# 1. CONFIGURACIÓN DE RUTAS LOCALES 
#RUTA_FRONTEND = "C:/Landing/sistema-piroy-web/frontend" ##"C:/sistema-piroy-web/frontend"

# 2. PUENTE DE ARCHIVOS ESTÁTICOS (CSS, JS, IMÁGENES)
app.mount("/frontend", StaticFiles(directory=RUTA_FRONTEND), name="frontend")


# 3. ENLACE DE ROUTERS (Aquí es donde FastAPI mágicamente activa tus consultas a SQL Server)
# Le agregamos el prefijo '/api' aquí de forma global para que coincida con tu main.js
app.include_router(categorias_router, prefix="/api")
app.include_router(articulos_router, prefix="/api")
app.include_router(promos_router,prefix="/api")

# 4. ENDPOINT PARA MOSTRAR LA PÁGINA WEB PRINCIPAL
@app.get("/")
async def read_index():
    ruta_index = f"{RUTA_FRONTEND}/index.html"
    return FileResponse(ruta_index)

# 5. ENDPOINT PARA MOSTRAR LA PÁGINA DE PROMOCIONES
@app.get("/promos")
async def read_promos():
    ruta_promos = f"{RUTA_FRONTEND}/promos-Exclusivos.html"
    return FileResponse(ruta_promos)
