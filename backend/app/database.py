import pyodbc

# Configuración con tus credenciales de SQL Server
DRIVER = "{ODBC Driver 18 for SQL Server}"
SERVER = "localhost"  # O el nombre de tu instancia si no es localhost
DATABASE = "piroy"  # ¡Recuerda cambiar esto por el nombre real de tu BD!
USER = "sa"
PASSWORD = "manager123*"

def obtener_conexion():
    str_conexion = (
        f"DRIVER={DRIVER};"
        f"SERVER={SERVER};"
        f"DATABASE={DATABASE};"
        f"UID={USER};"
        f"PWD={PASSWORD};"
        f"TrustServerCertificate=yes;"
    )
    conexion = pyodbc.connect(str_conexion)
    return conexion
