r"""Crea un usuario del panel de administracion, o le cambia la contrasena si ya existe.

Uso (desde la raiz del proyecto):
    .venv\Scripts\python.exe scripts/crear_usuario_admin.py USUARIO
    .venv\Scripts\python.exe scripts/crear_usuario_admin.py USUARIO --desactivar

La contrasena se pide por teclado (sin mostrarla) y se guarda solo con hash. No se
imprime ni la contrasena ni la cadena de conexion. Al cambiar la contrasena de un
usuario existente se cierran todas sus sesiones abiertas y se levanta su bloqueo.
"""
import getpass
import os
import re
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # para importar backend.app

from backend.app import seguridad_admin as seg  # noqa: E402  (despues de load_dotenv)

PATRON_USUARIO = re.compile(r"^[a-z0-9._-]{3,50}$")


def pedir_password():
    password = getpass.getpass("Contrasena nueva: ")
    problema = seg.validar_password_nueva(password)
    if problema:
        raise SystemExit(problema)
    if getpass.getpass("Repeti la contrasena: ") != password:
        raise SystemExit("Las contrasenas no coinciden. No se hizo ningun cambio.")
    return password


def main():
    argumentos = [a for a in sys.argv[1:] if not a.startswith("--")]
    desactivar = "--desactivar" in sys.argv
    if len(argumentos) != 1:
        raise SystemExit("Uso: crear_usuario_admin.py USUARIO [--desactivar]")
    usuario = argumentos[0].strip().lower()
    if not PATRON_USUARIO.match(usuario):
        raise SystemExit("El usuario debe tener de 3 a 50 caracteres: letras, numeros, punto, guion o guion bajo.")

    url = os.getenv("DATABASE_URL")
    if not url:
        raise SystemExit("Falta configurar la variable de entorno: DATABASE_URL")

    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM admin_usuarios WHERE usuario = %s", (usuario,))
            fila = cur.fetchone()

            if desactivar:
                if fila is None:
                    raise SystemExit(f"El usuario '{usuario}' no existe.")
                cur.execute("UPDATE admin_usuarios SET activo = FALSE WHERE id = %s", (fila[0],))
                cur.execute("DELETE FROM admin_sesiones WHERE usuario_id = %s", (fila[0],))
                conn.commit()
                print(f"Usuario '{usuario}' dado de baja; sus sesiones se cerraron.")
                return

            hash_nuevo = seg.hashear_password(pedir_password())
            if fila is None:
                cur.execute(
                    "INSERT INTO admin_usuarios (usuario, password_hash) VALUES (%s, %s)",
                    (usuario, hash_nuevo),
                )
                print(f"Usuario '{usuario}' creado.")
            else:
                cur.execute(
                    "UPDATE admin_usuarios SET password_hash = %s, activo = TRUE, "
                    "intentos_fallidos = 0, bloqueado_hasta = NULL WHERE id = %s",
                    (hash_nuevo, fila[0]),
                )
                cur.execute("DELETE FROM admin_sesiones WHERE usuario_id = %s", (fila[0],))
                print(f"Contrasena de '{usuario}' actualizada; sus sesiones anteriores se cerraron.")
        conn.commit()


if __name__ == "__main__":
    main()
