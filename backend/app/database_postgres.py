import os

import psycopg
from dotenv import load_dotenv


load_dotenv()


DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "Falta configurar la variable de entorno: DATABASE_URL"
    )


def obtener_conexion_postgres():
    return psycopg.connect(DATABASE_URL)