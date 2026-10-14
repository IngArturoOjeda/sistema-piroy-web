import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from backend.app.routers.categories import router as categorias_router
from backend.app.routers.items import router as articulos_router
from backend.app.routers.sync import router as sync_router
from backend.app.routers.admin import router as admin_router
from backend.app.routers.banners import router as banners_router
from backend.app.routers.admin_auth import router as admin_auth_router
from backend.app.routers.admin_usuarios import router as admin_usuarios_router
# La documentacion automatica (/docs, /redoc, /openapi.json) lista todas las
# rutas, incluidas las de administracion. Queda apagada salvo HABILITAR_DOCS=1
# (para desarrollo local; en Render no se define).
DOCS_HABILITADAS = os.getenv("HABILITAR_DOCS") == "1"
app = FastAPI(
    docs_url="/docs" if DOCS_HABILITADAS else None,
    redoc_url="/redoc" if DOCS_HABILITADAS else None,
    openapi_url="/openapi.json" if DOCS_HABILITADAS else None,
)

RUTA_PROYECTO = Path(__file__).resolve().parents[2]  # Ruta del proyecto
RUTA_FRONTEND = RUTA_PROYECTO / "frontend"  # Ruta del frontend
RUTA_ADMIN_APP = RUTA_FRONTEND / "admin-app"  # manifiesto y service worker de la app del panel

# 1. PUENTE DE ARCHIVOS ESTÁTICOS (CSS, JS, IMÁGENES)
app.mount("/frontend", StaticFiles(directory=RUTA_FRONTEND), name="frontend")


# 2. ENLACE DE ROUTERS (todos consultan PostgreSQL)
# Le agregamos el prefijo '/api' aquí de forma global para que coincida con main.js
app.include_router(categorias_router, prefix="/api")
app.include_router(articulos_router, prefix="/api")
app.include_router(sync_router, prefix="/api")
app.include_router(admin_auth_router, prefix="/api")
app.include_router(admin_usuarios_router, prefix="/api")
app.include_router(admin_router, prefix="/api")
app.include_router(banners_router, prefix="/api")


# 3. PÁGINAS DE LA TIENDA
# Todas sirven la misma página principal (frontend/index.html): main.js lee la URL y muestra
# la vista que corresponde. Así cada dirección funciona al recargar o al compartirla, y el
# carrito (que vive en memoria) no se pierde al navegar dentro de la tienda.
def pagina_principal():
    return FileResponse(f"{RUTA_FRONTEND}/index.html")


@app.get("/")
async def read_index():
    return pagina_principal()


# Página propia de un producto: /producto/1000 o /producto/1000-botina-en-cuero
@app.get("/producto/{ref}")
async def read_producto(ref: str):
    return pagina_principal()


# Todos los artículos con una promoción vigente (botón "Ver promoción" de la portada)
@app.get("/promociones")
async def read_promociones():
    return pagina_principal()


# Combos (antes cambiaba la barra de direcciones pero daba 404 al recargar)
@app.get("/combos")
async def read_combos():
    return pagina_principal()


# Catalogo completo ("Explora nuestro catalogo"): acepta /catalogo?categoria=NOMBRE; la query la lee main.js
@app.get("/catalogo")
async def read_catalogo():
    return pagina_principal()


# 4. PANEL DE ADMINISTRACION (app instalable)
# Direcciones cortas bajo /admin/. Todas las paginas del panel viven dentro de ese prefijo porque es el ALCANCE de la
# app instalada (manifest "scope": "/admin/"): lo que queda dentro se abre en la ventana de la app y el navegador
# ofrece "Abrir en aplicacion". Las paginas siguen siendo las mismas (frontend/admin-*.html), y la API es /api/admin.
def pagina_admin(archivo: str):
    return FileResponse(f"{RUTA_FRONTEND}/{archivo}", headers={"Cache-Control": "no-cache"})


# "/admin" y "/admin/" responden las dos (el alcance de la app es "/admin/"): entrada y pantalla de ingreso
@app.get("/admin")
async def read_admin():
    return pagina_admin("admin-login.html")


@app.get("/admin/")
async def read_admin_inicio():
    return pagina_admin("admin-login.html")


@app.get("/admin/imagenes")
async def read_admin_imagenes():
    return pagina_admin("admin-imagenes.html")


@app.get("/admin/banners")
async def read_admin_banners():
    return pagina_admin("admin-banners.html")


@app.get("/admin/tipos")
async def read_admin_tipos():
    return pagina_admin("admin-tipos.html")


@app.get("/admin/usuarios")
async def read_admin_usuarios():
    return pagina_admin("admin-usuarios.html")


@app.get("/admin/manifest.webmanifest")
async def read_admin_manifiesto():
    return FileResponse(RUTA_ADMIN_APP / "manifest.webmanifest", media_type="application/manifest+json")


# El service worker se sirve desde /admin/ para que su alcance sea /admin/; sin caché del navegador, así una
# versión nueva se aplica enseguida.
@app.get("/admin/sw.js")
async def read_admin_service_worker():
    return FileResponse(
        RUTA_ADMIN_APP / "sw.js",
        media_type="text/javascript",
        headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/admin/"},
    )
