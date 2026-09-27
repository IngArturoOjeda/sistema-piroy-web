import os
from pathlib import Path

import cloudinary
import cloudinary.uploader
from dotenv import load_dotenv

RUTA_PROYECTO = Path(__file__).resolve().parents[1]
IMAGEN_DE_PRUEBA = RUTA_PROYECTO / "frontend" / "assets" / "images" / "ladrillo.jpg"
CARPETA_CLOUDINARY = "agrovetzo/productos"


def obtener_variable_obligatoria(nombre):
    valor = os.getenv(nombre)
    if not valor:
        raise RuntimeError(f"Falta configurar la variable de entorno: {nombre}")
    return valor


def main():
    load_dotenv()

    cloud_name = obtener_variable_obligatoria("CLOUDINARY_CLOUD_NAME")
    api_key = obtener_variable_obligatoria("CLOUDINARY_API_KEY")
    api_secret = obtener_variable_obligatoria("CLOUDINARY_API_SECRET")

    cloudinary.config(
        cloud_name=cloud_name,
        api_key=api_key,
        api_secret=api_secret,
        secure=True,
    )

    if not IMAGEN_DE_PRUEBA.is_file():
        print(f"No se encontró la imagen de prueba: {IMAGEN_DE_PRUEBA}")
        raise SystemExit(1)

    resultado = cloudinary.uploader.upload(
        str(IMAGEN_DE_PRUEBA),
        folder=CARPETA_CLOUDINARY,
    )

    print(f"secure_url: {resultado['secure_url']}")
    print(f"public_id: {resultado['public_id']}")


if __name__ == "__main__":
    main()
