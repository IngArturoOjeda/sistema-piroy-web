"""Crea la tabla `banners` en la base indicada por DATABASE_URL.

Uso (desde la raiz del proyecto):
    .venv\\Scripts\\python.exe scripts/crear_tabla_banners.py

No imprime la cadena de conexion. Solo crea objetos nuevos (IF NOT EXISTS).
"""
from pathlib import Path

import psycopg
from dotenv import load_dotenv
import os

load_dotenv()

RUTA_SQL = Path(__file__).with_name("crear_tabla_banners.sql")


def main():
    url = os.getenv("DATABASE_URL")
    if not url:
        raise SystemExit("Falta configurar la variable de entorno: DATABASE_URL")

    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('public.banners')")
            existia = cur.fetchone()[0] is not None
            print("La tabla banners", "YA existia." if existia else "no existia; se crea.")

            cur.execute(RUTA_SQL.read_text(encoding="utf-8"))

            cur.execute(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'banners' "
                "ORDER BY ordinal_position"
            )
            for nombre, tipo in cur.fetchall():
                print(f"  {nombre}: {tipo}")
        conn.commit()
    print("Listo.")


if __name__ == "__main__":
    main()
