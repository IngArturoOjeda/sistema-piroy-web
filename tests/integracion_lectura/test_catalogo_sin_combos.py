"""
Integracion de SOLO LECTURA: el catalogo general (GET /api/articulos) no muestra COMBO;
GET /api/articulos/combos si.

Requiere el servidor local (API_BASE_URL, por defecto 127.0.0.1:8000) y DATABASE_URL en el entorno.
Solo ejecuta SELECT (conexion read_only) y GET. Los conjuntos de referencia se leen de la base
en cada corrida: no hay IDs ni nombres fijos.
"""
import json
import urllib.parse
import urllib.request

import pytest


def get(api_url, ruta, params=None):
    url = api_url + "/api/articulos" + ruta
    if params:
        url += "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url) as r:
        return json.loads(r.read().decode("utf-8"))


def ids_de(lista):
    return {a["id"] for a in lista}


def todas_las_paginas(api_url, ruta, params):
    ids, pagina = set(), 1
    while True:
        lote = get(api_url, ruta, {**params, "pagina": pagina, "limite": 30})
        if not lote:
            break
        ids |= ids_de(lote)
        pagina += 1
        if pagina > 500:
            raise RuntimeError("paginacion sin fin")
    return ids


def consultar(conn, sql):
    cur = conn.cursor()
    try:
        cur.execute(sql)
        return cur.fetchall()
    finally:
        cur.close()


FILTRO_PUBLICADO = "a.art_estado = 'S' AND a.llevar_web = TRUE AND a.mostrar_web = TRUE"


@pytest.fixture
def referencia(conexion_solo_lectura):
    """Conjuntos de referencia leidos de la base (solo SELECT)."""
    conn = conexion_solo_lectura
    return {
        "combos": {r[0] for r in consultar(conn, f"""
            SELECT a.art_cod FROM articulos a WHERE a.tipo_kit = 'COMBO' AND {FILTRO_PUBLICADO}""")},
        "presentaciones": {r[0] for r in consultar(conn, f"""
            SELECT a.art_cod FROM articulos a WHERE a.tipo_kit = 'PRESENTACION' AND {FILTRO_PUBLICADO}""")},
        "normales": {r[0] for r in consultar(conn, f"""
            SELECT a.art_cod FROM articulos a WHERE a.art_kit = FALSE AND {FILTRO_PUBLICADO}""")},
        "categorias": [r[0] for r in consultar(conn, f"""
            SELECT DISTINCT t.tipoart_desc FROM articulos a
            JOIN tipo_articulo t ON t.tipoart_cod = a.tipoart_cod
            WHERE {FILTRO_PUBLICADO}""")],
    }


def test_todos_no_devuelve_combos_publicados(api_url, referencia):
    todos = todas_las_paginas(api_url, "/", {"categoria": "Todos"})
    assert not (todos & referencia["combos"])


def test_categorias_especificas_no_devuelven_combos(api_url, referencia):
    culpables = {}
    for cat in referencia["categorias"]:
        ids = todas_las_paginas(api_url, "/", {"categoria": cat})
        if ids & referencia["combos"]:
            culpables[cat] = ids & referencia["combos"]
    assert culpables == {}


def test_sin_parametros_no_devuelve_combos(api_url, referencia):
    ids = todas_las_paginas(api_url, "/", {})
    assert not (ids & referencia["combos"])


def test_presentaciones_publicadas_siguen_en_catalogo_general(api_url, referencia):
    todos = todas_las_paginas(api_url, "/", {"categoria": "Todos"})
    assert referencia["presentaciones"] <= todos


def test_combos_endpoint_devuelve_los_combos_publicados(api_url, referencia):
    if not referencia["combos"]:
        pytest.skip("no hay combos publicados en la base: nada que verificar en /combos")
    ids = todas_las_paginas(api_url, "/combos", {})
    assert referencia["combos"] <= ids


def test_presentacion_kit_solo_devuelve_presentaciones(api_url, referencia):
    for cat in referencia["categorias"]:
        ids = todas_las_paginas(api_url, "/", {"categoria": cat, "presentacion": "KIT"})
        assert ids <= referencia["presentaciones"], f"categoria {cat}: KIT devolvio algo fuera de PRESENTACION"
        assert not (ids & referencia["combos"]), f"categoria {cat}: KIT devolvio un COMBO"


def test_presentacion_normal_solo_devuelve_articulos_normales(api_url, referencia):
    for cat in referencia["categorias"]:
        ids = todas_las_paginas(api_url, "/", {"categoria": cat, "presentacion": "NORMAL"})
        assert ids <= referencia["normales"], f"categoria {cat}: NORMAL devolvio un kit"
