r"""Crea las tablas `admin_usuarios` y `admin_sesiones` en la base indicada por DATABASE_URL.

Uso (desde la raiz del proyecto):
    .venv\Scripts\python.exe scripts/crear_tablas_admin.py            # crea de verdad
    .venv\Scripts\python.exe scripts/crear_tablas_admin.py --probar   # valida y deshace (rollback)

No imprime la cadena de conexion. Solo crea objetos nuevos (IF NOT EXISTS) y no
modifica ninguna fila existente.
"""
import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

load_dotenv()

RUTA_SQL = Path(__file__).with_name("crear_tablas_admin.sql")
TABLAS = ("admin_usuarios", "admin_sesiones")


def main():
    probar = "--probar" in sys.argv
    url = os.getenv("DATABASE_URL")
    if not url:
        raise SystemExit("Falta configurar la variable de entorno: DATABASE_URL")

    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            for tabla in TABLAS:
                cur.execute("SELECT to_regclass(%s)", (f"public.{tabla}",))
                print(f"{tabla}:", "YA existia." if cur.fetchone()[0] is not None else "no existia; se crea.")

            cur.execute(RUTA_SQL.read_text(encoding="utf-8"))

            for tabla in TABLAS:
                print(f"\n{tabla}")
                cur.execute(
                    "SELECT column_name, data_type FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = %s ORDER BY ordinal_position",
                    (tabla,),
                )
                for nombre, tipo in cur.fetchall():
                    print(f"  {nombre}: {tipo}")
                cur.execute(f"SELECT count(*) FROM {tabla}")
                print("  filas:", cur.fetchone()[0])

        if probar:
            conn.rollback()
            print("\nMODO PRUEBA: se deshizo todo (rollback); no quedo nada creado.")
        else:
            conn.commit()
            print("\nListo.")


if __name__ == "__main__":
    main()
