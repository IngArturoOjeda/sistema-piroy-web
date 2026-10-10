"""
Configuracion compartida de las pruebas.

- tests/unit: mock puro. Se bloquea psycopg.connect para que no pueda
  conectarse a ninguna base, ni por accidente.
- tests/integracion_lectura: solo SELECT y GET contra el servidor local.
  La conexion se marca como solo lectura.

Las credenciales se leen del entorno (.env, que no va a Git). Nada queda escrito aca.
"""
import os
import urllib.request
from pathlib import Path

import psycopg
import pytest
from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parents[1]

load_dotenv(RAIZ / ".env")

# backend/app/database_postgres.py exige DATABASE_URL al importarse.
# Si no hay .env, se usa un valor ficticio: los tests unit nunca se conectan.
os.environ.setdefault("DATABASE_URL", "postgresql://no-usar:no-usar@127.0.0.1:1/no_usar")

API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")


def pytest_collection_modifyitems(config, items):
    for item in items:
        partes = Path(item.path).parts
        if "unit" in partes and "tests" in partes:
            item.add_marker(pytest.mark.unit)
        elif "integracion_lectura" in partes:
            item.add_marker(pytest.mark.integracion_lectura)


@pytest.fixture(autouse=True)
def bloquear_conexiones_en_unit(request, monkeypatch):
    if request.node.get_closest_marker("unit") is None:
        return

    def prohibido(*args, **kwargs):
        raise AssertionError("un test unit intento conectarse a PostgreSQL")

    monkeypatch.setattr(psycopg, "connect", prohibido)


@pytest.fixture
def conexion_solo_lectura():
    url = os.getenv("DATABASE_URL", "")
    if not url or url.startswith("postgresql://no-usar"):
        pytest.skip("DATABASE_URL no configurada: integracion omitida")
    conn = psycopg.connect(url)
    conn.read_only = True
    yield conn
    conn.close()


@pytest.fixture
def api_url():
    try:
        # "/" y no "/docs": la documentacion automatica puede estar apagada.
        urllib.request.urlopen(API_BASE_URL + "/", timeout=3).close()
    except Exception:
        pytest.skip(f"servidor no disponible en {API_BASE_URL}")
    return API_BASE_URL
