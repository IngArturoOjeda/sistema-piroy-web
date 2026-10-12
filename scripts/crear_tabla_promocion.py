"""Crea la tabla `promocion` en la base indicada por DATABASE_URL.

Uso (desde la raiz del proyecto):
    .venv\\Scripts\\python.exe scripts/crear_tabla_promocion.py

No imprime la cadena de conexion. Solo crea objetos nuevos (IF NOT EXISTS) y no
modifica ninguna fila existente.
"""
import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv

load_dotenv()

RUTA_SQL = Path(__file__).with_name("crear_tabla_promocion.sql")


def main():
    url = os.getenv("DATABASE_URL")
    if not url:
        raise SystemExit("Falta configurar la variable de entorno: DATABASE_URL")

    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('public.promocion')")
            existia = cur.fetchone()[0] is not None
            print("La tabla promocion", "YA existia." if existia else "no existia; se crea.")

            cur.execute(RUTA_SQL.read_text(encoding="utf-8"))

            cur.execute(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'promocion' "
                "ORDER BY ordinal_position"
            )
            for nombre, tipo in cur.fetchall():
                print(f"  {nombre}: {tipo}")

            cur.execute("SELECT count(*) FROM promocion")
            print("Filas en promocion:", cur.fetchone()[0])
        conn.commit()
    print("Listo.")


if __name__ == "__main__":
    main()
