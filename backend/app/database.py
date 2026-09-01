
import os
import pyodbc
from dotenv import load_dotenv

# Carga las variables guardadas en el archivo .env
load_dotenv()

def obtener_variable(nombre):
    valor = os.getenv(nombre)

    if not valor:
        raise RuntimeError(
            f"Falta configurar la variable de entorno: {nombre}"
        )

    return valor

# Configuración con tus credenciales de SQL Server
DRIVER = obtener_variable("DB_DRIVER")
SERVER = obtener_variable("DB_SERVER")
DATABASE = obtener_variable("DB_NAME")
USER = obtener_variable("DB_USER")
PASSWORD = obtener_variable("DB_PASSWORD")

def obtener_conexion():
    str_conexion = (
        f"DRIVER={{{DRIVER}}};"
        f"SERVER={SERVER};"
        f"DATABASE={DATABASE};"
        f"UID={USER};"
        f"PWD={PASSWORD};"
        f"TrustServerCertificate=yes;"
    )
    conexion = pyodbc.connect(str_conexion)
    return conexion
