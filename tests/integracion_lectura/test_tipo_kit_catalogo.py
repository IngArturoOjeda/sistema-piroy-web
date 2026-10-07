"""
Integracion de SOLO LECTURA: presentaciones y filtros de presentacion del catalogo.

Requiere el servidor local (API_BASE_URL, por defecto 127.0.0.1:8000) y DATABASE_URL en el entorno.
Solo ejecuta SELECT (conexion read_only) y GET. Las comparaciones son contra conjuntos
leidos de la base en cada corrida, no contra nombres de productos.
"""
import json
import urllib.error
import urllib.parse
import urllib.request

import pytest


def get(api_url, ruta, params=None):
    url = api_url + "/api/articulos" + ruta
    if params:
        url += "?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


def todas_las_paginas(api_url, params):
    ids, pagina = set(), 1
    while True:
        status, lote = get(api_url, "/", {**params, "pagina": pagina, "limite": 30})
        assert status == 200, f"status {status} en pagina {pagina}"
        if not lote:
            break
        ids |= {a["id"] for a in lote}
        pagina += 1
        if pagina > 500:
            raise RuntimeError("paginacion sin fin")
    return ids


FILTRO_PUBLICADO = "a.art_estado = 'S' AND a.llevar_web = TRUE AND a.mostrar_web = TRUE"


@pytest.fixture
def referencia(conexion_solo_lectura):
    cur = conexion_solo_lectura.cursor()
    try:
        cur.execute(f"""SELECT a.art_cod FROM articulos a
                        WHERE a.tipo_kit = 'PRESENTACION' AND {FILTRO_PUBLICADO}""")
        presentaciones = {r[0] for r in cur.fetchall()}
        cur.execute(f"""SELECT a.art_cod FROM articulos a
                        WHERE a.art_kit = FALSE AND {FILTRO_PUBLICADO}""")
        normales = {r[0] for r in cur.fetchall()}
        cur.execute(f"""SELECT DISTINCT t.tipoart_desc FROM articulos a
                        JOIN tipo_articulo t ON t.tipoart_cod = a.tipoart_cod
                        WHERE {FILTRO_PUBLICADO}""")
        categorias = [r[0] for r in cur.fetchall()]
    finally:
        cur.close()
    return {"presentaciones": presentaciones, "normales": normales, "categorias": categorias}


def test_presentaciones_responden_200_para_cada_categoria(api_url, referencia):
    for cat in referencia["categorias"]:
        status, body = get(api_url, "/presentaciones", {"categoria": cat})
        assert status == 200, f"categoria {cat}: status {status}"
        assert isinstance(body, list)


def test_presentacion_kit_solo_devuelve_presentaciones(api_url, referencia):
    for cat in referencia["categorias"]:
        ids = todas_las_paginas(api_url, {"categoria": cat, "presentacion": "KIT"})
        assert ids <= referencia["presentaciones"], f"categoria {cat}: KIT devolvio algo que no es PRESENTACION"


def test_presentacion_normal_solo_devuelve_articulos_no_kit(api_url, referencia):
    for cat in referencia["categorias"]:
        ids = todas_las_paginas(api_url, {"categoria": cat, "presentacion": "NORMAL"})
        assert ids <= referencia["normales"], f"categoria {cat}: NORMAL devolvio un kit"


def test_categoria_todos_con_presentacion_kit_da_400(api_url):
    status, _ = get(api_url, "/", {"categoria": "Todos", "presentacion": "KIT"})
    assert status == 400


def test_catalogo_general_responde_con_articulos(api_url, conexion_solo_lectura):
    cur = conexion_solo_lectura.cursor()
    try:
        cur.execute(f"SELECT COUNT(*) FROM articulos a WHERE {FILTRO_PUBLICADO}")
        hay_publicados = cur.fetchone()[0] > 0
    finally:
        cur.close()
    status, body = get(api_url, "/", {"pagina": 1, "limite": 30})
    assert status == 200
    if hay_publicados:
        assert len(body) > 0
