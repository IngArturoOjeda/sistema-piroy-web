"""
Paginas de la tienda: todas sirven frontend/index.html y main.js elige la vista segun la URL.
Tambien comprueba que el backend publicado ya no depende de SQL Server.
"""
import asyncio
import os
import subprocess
import sys

import pytest

from backend.app import main


def ruta_index(respuesta):
    return str(respuesta.path).replace("\\", "/")


@pytest.mark.parametrize("funcion, argumentos", [
    (main.read_index, ()),
    (main.read_producto, ("1000-botina-en-cuero",)),
    (main.read_promociones, ()),
    (main.read_combos, ()),
    (main.read_catalogo, ()),
])
def test_cada_pagina_sirve_el_index(funcion, argumentos):
    assert ruta_index(asyncio.run(funcion(*argumentos))).endswith("frontend/index.html")


def test_las_paginas_de_la_tienda_estan_registradas_como_get():
    rutas = {r.path: r.methods for r in main.app.routes if hasattr(r, "methods") and r.methods}
    for ruta in ("/", "/producto/{ref}", "/promociones", "/combos", "/catalogo"):
        assert "GET" in rutas[ruta], ruta
    assert "/promos" not in rutas                      # la pagina vieja ya no existe


def test_el_index_existe_en_el_frontend():
    assert (main.RUTA_FRONTEND / "index.html").is_file()


def test_el_backend_ya_no_importa_sql_server_ni_pyodbc():
    # En un proceso limpio: importar la app no debe cargar el modulo de SQL Server ni pyodbc.
    codigo = (
        f"import sys; sys.path.insert(0, {str(main.RUTA_PROYECTO)!r});"
        "import os; os.environ.setdefault('DATABASE_URL', 'postgresql://x:y@127.0.0.1:1/z');"
        "import backend.app.main;"
        "print('backend.app.database' in sys.modules,"
        " 'pyodbc' in sys.modules, 'backend.app.routers.promos' in sys.modules)"
    )
    entorno = {**os.environ, "DATABASE_URL": "postgresql://x:y@127.0.0.1:1/z"}
    salida = subprocess.run([sys.executable, "-I", "-c", codigo], capture_output=True, text=True,
                            cwd=str(main.RUTA_PROYECTO), env=entorno)
    assert salida.returncode == 0, salida.stderr[-400:]
    assert salida.stdout.split() == ["False", "False", "False"]


def test_los_archivos_viejos_de_promociones_fueron_retirados():
    for ruta in ("backend/app/routers/promos.py", "backend/app/database.py", "frontend/promos-Exclusivos.html"):
        assert not (main.RUTA_PROYECTO / ruta).exists(), ruta
