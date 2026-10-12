r"""Agrega la columna `mostrar_web` a `tipo_articulo` en la base indicada por DATABASE_URL.

Uso (desde la raiz del proyecto):
    .venv\Scripts\python.exe scripts/agregar_columna_mostrar_web_tipo.py            # aplica
    .venv\Scripts\python.exe scripts/agregar_columna_mostrar_web_tipo.py --probar   # valida y deshace

No imprime la cadena de conexion. Todos los tipos existentes quedan con mostrar_web = TRUE.
"""
import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

load_dotenv()

RUTA_SQL = Path(__file__).with_name("agregar_columna_mostrar_web_tipo.sql")

SQL_EXISTE = (
    "SELECT 1 FROM information_schema.columns "
    "WHERE table_schema = 'public' AND table_name = 'tipo_articulo' "
    "AND column_name = 'mostrar_web'"
)


def main():
    probar = "--probar" in sys.argv
    url = os.getenv("DATABASE_URL")
    if not url:
        raise SystemExit("Falta configurar la variable de entorno: DATABASE_URL")

    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM tipo_articulo")
            filas_antes = cur.fetchone()[0]

            cur.execute(SQL_EXISTE)
            existia = cur.fetchone() is not None
            print("La columna mostrar_web", "YA existia." if existia else "no existia; se crea.")

            cur.execute(RUTA_SQL.read_text(encoding="utf-8"))

            cur.execute(SQL_EXISTE)
            assert cur.fetchone() is not None, "la columna no quedo creada"
            cur.execute("SELECT count(*), count(*) FILTER (WHERE mostrar_web) FROM tipo_articulo")
            filas_despues, visibles = cur.fetchone()

        if probar:
            conn.rollback()
            print("MODO PRUEBA: se deshizo todo (rollback); no quedo nada cambiado.")
        else:
            conn.commit()

    print(f"Tipos: {filas_antes} antes, {filas_despues} despues. Visibles: {visibles}.")
    print("Listo.")


if __name__ == "__main__":
    main()
