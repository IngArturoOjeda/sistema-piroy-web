"""
Panel de administracion como app instalable: direcciones /admin/..., manifiesto, service worker y enlaces.
Sin tocar ninguna base.
"""
import asyncio
import json
import re
import struct

import pytest

from backend.app import main

FRONTEND = main.RUTA_FRONTEND
PAGINAS = [
    ("/admin", main.read_admin, "admin-login.html"),
    ("/admin/", main.read_admin_inicio, "admin-login.html"),
    ("/admin/imagenes", main.read_admin_imagenes, "admin-imagenes.html"),
    ("/admin/banners", main.read_admin_banners, "admin-banners.html"),
    ("/admin/tipos", main.read_admin_tipos, "admin-tipos.html"),
    ("/admin/usuarios", main.read_admin_usuarios, "admin-usuarios.html"),
]
HTML_DEL_PANEL = ["admin-login.html", "admin-imagenes.html", "admin-banners.html", "admin-tipos.html", "admin-usuarios.html"]


def ruta(respuesta):
    return str(respuesta.path).replace("\\", "/")


def manifiesto():
    return json.loads((main.RUTA_ADMIN_APP / "manifest.webmanifest").read_text(encoding="utf-8"))


def medidas_png(archivo):
    datos = archivo.read_bytes()
    assert datos[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", datos[16:24])


# ---------- direcciones ----------

@pytest.mark.parametrize("direccion, funcion, archivo", PAGINAS)
def test_cada_direccion_del_panel_sirve_su_pagina(direccion, funcion, archivo):
    respuesta = asyncio.run(funcion())
    assert ruta(respuesta).endswith(f"frontend/{archivo}")
    assert respuesta.headers["cache-control"] == "no-cache"


def test_las_direcciones_del_panel_estan_registradas_como_get():
    rutas = {r.path: r.methods for r in main.app.routes if hasattr(r, "methods") and r.methods}
    for direccion, _, _ in PAGINAS:
        assert "GET" in rutas[direccion], direccion
    # la API del panel sigue en /api/admin, aparte de las paginas
    assert not any(getattr(r, "path", None) == "/admin/articulos" for r in main.app.routes)


def test_admin_con_y_sin_barra_final_responden_las_dos():
    # el alcance de la app es "/admin/": que /admin/ no redirija a /admin (fuera del alcance)
    rutas = [r.path for r in main.app.routes if hasattr(r, "methods")]
    assert "/admin" in rutas and "/admin/" in rutas


def test_las_paginas_estaticas_viejas_siguen_existiendo():
    for archivo in HTML_DEL_PANEL:
        assert (FRONTEND / archivo).is_file()


# ---------- manifiesto ----------

def test_el_manifiesto_describe_una_app_instalable():
    m = manifiesto()
    assert m["name"] and m["short_name"] and len(m["short_name"]) <= 12
    assert m["display"] == "standalone"
    assert m["start_url"] == "/admin/" and m["scope"] == "/admin/" and m["id"]
    assert m["start_url"].startswith(m["scope"])          # el inicio tiene que estar dentro del alcance
    assert re.fullmatch(r"#[0-9A-Fa-f]{6}", m["theme_color"]) and re.fullmatch(r"#[0-9A-Fa-f]{6}", m["background_color"])
    assert m["lang"].startswith("es")


def test_los_iconos_del_manifiesto_existen_y_miden_lo_que_dicen():
    m = manifiesto()
    medidas_declaradas = set()
    propositos = set()
    for icono in m["icons"]:
        assert icono["src"].startswith("/frontend/")
        archivo = FRONTEND.parent / icono["src"].lstrip("/")
        assert archivo.is_file(), icono["src"]
        ancho, alto = medidas_png(archivo)
        assert f"{ancho}x{alto}" == icono["sizes"] and icono["type"] == "image/png"
        medidas_declaradas.add(icono["sizes"])
        propositos.add(icono["purpose"])
    assert {"192x192", "512x512"} <= medidas_declaradas       # los tamanos que exigen los navegadores
    assert "maskable" in propositos and "any" in propositos


def test_el_manifiesto_se_sirve_con_su_tipo_de_contenido():
    respuesta = asyncio.run(main.read_admin_manifiesto())
    assert respuesta.media_type == "application/manifest+json"
    assert ruta(respuesta).endswith("frontend/admin-app/manifest.webmanifest")


# ---------- service worker ----------

def test_el_service_worker_se_sirve_con_alcance_y_sin_cache():
    respuesta = asyncio.run(main.read_admin_service_worker())
    assert respuesta.media_type == "text/javascript"
    assert respuesta.headers["service-worker-allowed"] == "/admin/"
    assert respuesta.headers["cache-control"] == "no-cache"
    assert ruta(respuesta).endswith("frontend/admin-app/sw.js")


def test_el_service_worker_no_guarda_nada_en_cache():
    codigo = (main.RUTA_ADMIN_APP / "sw.js").read_text(encoding="utf-8")
    assert "caches." not in codigo and "cache.put" not in codigo.lower() and "indexedDB" not in codigo
    assert 'addEventListener("fetch"' in codigo                  # Chrome/Edge lo piden para ofrecer instalar
    assert 'peticion.mode !== "navigate"' in codigo              # solo se ocupa de abrir paginas; lo demas va a la red


# ---------- paginas del panel ----------

@pytest.mark.parametrize("archivo", HTML_DEL_PANEL)
def test_cada_pagina_del_panel_enlaza_la_app(archivo):
    html = (FRONTEND / archivo).read_text(encoding="utf-8")
    assert '<link rel="manifest" href="/admin/manifest.webmanifest">' in html
    assert '<meta name="theme-color" content="#603000">' in html
    assert 'rel="apple-touch-icon"' in html
    assert '<script src="/frontend/js/admin-pwa.js"></script>' in html
    assert 'id="btn-instalar"' in html and "hidden" in html.split('id="btn-instalar"')[1].split(">")[0]
    assert 'content="noindex, nofollow"' in html or archivo != "admin-login.html"


@pytest.mark.parametrize("archivo", HTML_DEL_PANEL)
def test_los_enlaces_del_panel_usan_las_direcciones_dentro_del_alcance(archivo):
    html = (FRONTEND / archivo).read_text(encoding="utf-8")
    sin_recursos = html.replace("/frontend/js/", "").replace("/frontend/css/", "").replace("/frontend/assets/", "")
    assert "/frontend/admin-" not in sin_recursos             # ningun enlace sale del alcance /admin/
    for href in re.findall(r'<a [^>]*href="([^"]+)"', html):
        assert href.startswith("/admin/") or href == "/", href  # "/" (la tienda) se abre aparte, en otra pestana


def test_la_tienda_se_abre_en_otra_pestana_desde_el_panel():
    html = (FRONTEND / "admin-imagenes.html").read_text(encoding="utf-8")
    assert '<a href="/" target="_blank" rel="noopener" class="menu-enlace">Ver la tienda</a>' in html


def test_las_pantallas_redirigen_a_las_direcciones_nuevas():
    assert 'const URL_LOGIN_ADMIN = "/admin/";' in (FRONTEND / "js" / "admin-sesion.js").read_text(encoding="utf-8")
    assert 'const PANEL_DESTINO = "/admin/imagenes";' in (FRONTEND / "js" / "admin-login.js").read_text(encoding="utf-8")


def test_el_script_de_la_app_registra_el_service_worker_en_su_alcance():
    codigo = (FRONTEND / "js" / "admin-pwa.js").read_text(encoding="utf-8")
    assert 'register("/admin/sw.js", { scope: "/admin/" })' in codigo
    assert "beforeinstallprompt" in codigo and "appinstalled" in codigo


# ---------- nombre y menu del panel ----------

PANTALLAS_CON_MENU = ["admin-imagenes.html", "admin-banners.html", "admin-tipos.html", "admin-usuarios.html"]


def test_la_app_se_llama_agro_vetzo():
    m = manifiesto()
    assert m["name"] == "AGRO-VETZO" and m["short_name"] == "AGRO-VETZO"
    for archivo in HTML_DEL_PANEL:
        html = (FRONTEND / archivo).read_text(encoding="utf-8")
        assert "<title>AGRO-VETZO - " in html and "AgroVetzo" not in html
        assert '<meta name="apple-mobile-web-app-title" content="AGRO-VETZO">' in html


@pytest.mark.parametrize("archivo", PANTALLAS_CON_MENU)
def test_cada_pantalla_tiene_el_menu_de_hamburguesa(archivo):
    html = (FRONTEND / archivo).read_text(encoding="utf-8")
    for pieza in ('id="btn-menu"', 'id="menu-admin"', 'id="menu-fondo"', 'id="btn-menu-cerrar"',
                  'id="admin-usuario"', 'id="btn-salir"', 'id="btn-instalar"', '<script src="/frontend/js/admin-menu.js"></script>'):
        assert pieza in html, pieza
    # el menu lleva a las cuatro pantallas y marca solo la actual
    for destino in ("/admin/imagenes", "/admin/banners", "/admin/tipos", "/admin/usuarios"):
        assert f'href="{destino}"' in html
    assert html.count('aria-current="page"') == 1
    assert html.index("admin-menu.js") < html.index("admin-pwa.js") < html.index("admin-sesion.js")
