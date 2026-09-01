
import os
import pyodbc
from dotenv import load_dotenv

# Carga las variables guardadas en el archivo .env
load_dotenv()


# Configuración con tus credenciales de SQL Server
DRIVER = os.getenv("DB_DRIVER")
SERVER = os.getenv("DB_SERVER")
DATABASE = os.getenv("DB_NAME")
USER = os.getenv("DB_USER")
PASSWORD = os.getenv("DB_PASSWORD")

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
