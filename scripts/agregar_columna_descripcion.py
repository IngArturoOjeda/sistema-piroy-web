"""Agrega la columna `descripcion` a `articulos` en la base indicada por DATABASE_URL.

Uso (desde la raiz del proyecto):
    .venv\\Scripts\\python.exe scripts/agregar_columna_descripcion.py

No imprime la cadena de conexion. No modifica filas existentes: la columna
queda en NULL hasta que se cargue desde el panel de administracion.
"""
import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv

load_dotenv()

RUTA_SQL = Path(__file__).with_name("agregar_columna_descripcion.sql")

SQL_EXISTE = (
    "SELECT 1 FROM information_schema.columns "
    "WHERE table_schema = 'public' AND table_name = 'articulos' "
    "AND column_name = 'descripcion'"
)


def main():
    url = os.getenv("DATABASE_URL")
    if not url:
        raise SystemExit("Falta configurar la variable de entorno: DATABASE_URL")

    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM articulos")
            filas_antes = cur.fetchone()[0]

            cur.execute(SQL_EXISTE)
            existia = cur.fetchone() is not None
            print("La columna descripcion", "YA existia." if existia else "no existia; se crea.")

            cur.execute(RUTA_SQL.read_text(encoding="utf-8"))

            cur.execute(SQL_EXISTE)
            assert cur.fetchone() is not None, "la columna no quedo creada"
            cur.execute("SELECT count(*) FROM articulos")
            filas_despues = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM articulos WHERE descripcion IS NOT NULL")
            con_descripcion = cur.fetchone()[0]
        conn.commit()

    print(f"Articulos: {filas_antes} antes, {filas_despues} despues. Con descripcion: {con_descripcion}.")
    print("Listo.")


if __name__ == "__main__":
    main()
