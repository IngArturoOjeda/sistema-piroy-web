import os

import pyodbc
from dotenv import load_dotenv

load_dotenv()


def obtener_variable(nombre):
    valor = os.getenv(nombre)

    if not valor:
        raise RuntimeError(
            f"Falta configurar la variable de entorno: {nombre}"
        )

    return valor


def obtener_conexion():
    str_conexion = (
        f"DRIVER={{{obtener_variable('DB_DRIVER')}}};"
        f"SERVER={obtener_variable('DB_SERVER')};"
        f"DATABASE={obtener_variable('DB_NAME')};"
        f"UID={obtener_variable('DB_USER')};"
        f"PWD={obtener_variable('DB_PASSWORD')};"
        f"TrustServerCertificate=yes;"
    )
    return pyodbc.connect(str_conexion)
