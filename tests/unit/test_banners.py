"""
Banners del carrusel: endpoints publicos y de administracion.

Todo simulado: cursor/conexion falsos y Cloudinary falso. No toca ninguna base
ni sube imagenes reales.
"""
import asyncio
from datetime import datetime, timezone
from io import BytesIO

import pytest
from fastapi import HTTPException, Response
from pydantic import ValidationError
from starlette.datastructures import Headers, UploadFile

from backend.app.routers import admin, banners
from backend.app.schemas import BannerActualizar

JPEG = b"\xff\xd8\xff" + b"0" * 100
FECHA = datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc)


class FakeCursor:
    def __init__(self, filas=None, fallar_en=None):
        self.filas = list(filas or [])
        self.fallar_en = fallar_en
        self.consultas = []

    def execute(self, sql, params=None):
        q = " ".join(sql.split())
        self.consultas.append((q, params))
        if self.fallar_en and self.fallar_en in q:
            raise RuntimeError("fallo simulado de base")

    def fetchone(self):
        return self.filas.pop(0) if self.filas else None

    def fetchall(self):
        return self.filas

    def close(self):
        pass


class FakeConn:
    def __init__(self, cursor, commit_falla=False, rollback_falla=False):
        self._cursor = cursor
        self.commit_falla = commit_falla
        self.rollback_falla = rollback_falla
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return self._cursor

    def commit(self):
        if self.commit_falla:
            raise RuntimeError("se perdio la respuesta del COMMIT")
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1
        if self.rollback_falla:
            raise RuntimeError("fallo el rollback")

    def close(self):
        pass


class FakeCloudinary:
    def __init__(self, upload_falla=False, destroy_resultado=None, destroy_falla=False):
        self.upload_falla = upload_falla
        self.destroy_resultado = destroy_resultado or {"result": "ok"}
        self.destroy_falla = destroy_falla
        self.uploads = []
        self.destroys = []

    def upload(self, archivo, **kwargs):
        if self.upload_falla:
            raise RuntimeError("cloudinary caido")
        self.uploads.append(kwargs)
        return {
            "public_id": kwargs["public_id"],
            "secure_url": "https://res.cloudinary.com/demo/image/upload/v1/" + kwargs["public_id"],
        }

    def destroy(self, public_id, **kwargs):
        self.destroys.append((public_id, kwargs))
        if self.destroy_falla:
            raise RuntimeError("cloudinary caido")
        return self.destroy_resultado


@pytest.fixture
def escenario(monkeypatch):
    """Devuelve una funcion para armar cursor/conexion/cloudinary falsos."""
    def armar(filas=None, fallar_en=None, commit_falla=False, rollback_falla=False,
              **opciones_cloudinary):
        cursor = FakeCursor(filas, fallar_en)
        conn = FakeConn(cursor, commit_falla, rollback_falla)
        nube = FakeCloudinary(**opciones_cloudinary)
        monkeypatch.setattr(admin, "obtener_conexion_postgres", lambda: conn)
        monkeypatch.setattr(banners, "obtener_conexion_postgres", lambda: conn)
        monkeypatch.setattr(admin, "configurar_cloudinary", lambda: None)
        monkeypatch.setattr(admin.cloudinary.uploader, "upload", nube.upload)
        monkeypatch.setattr(admin.cloudinary.uploader, "destroy", nube.destroy)
        return cursor, conn, nube
    return armar


def archivo(contenido=JPEG, tipo="image/jpeg", nombre="b.jpg"):
    return UploadFile(
        file=BytesIO(contenido), filename=nombre, headers=Headers({"content-type": tipo})
    )


def subir(**kwargs):
    kwargs.setdefault("archivo", archivo())
    kwargs.setdefault("alt", "Envio sin costo")
    kwargs.setdefault("orden", 0)
    return asyncio.run(admin.subir_banner(**kwargs))


# --- Esquema BannerActualizar ---------------------------------------------

def test_actualizar_rechaza_cuerpo_vacio():
    with pytest.raises(ValidationError):
        BannerActualizar()


def test_actualizar_rechaza_null_y_campos_extra():
    with pytest.raises(ValidationError):
        BannerActualizar(activo=None)
    with pytest.raises(ValidationError):
        BannerActualizar(activo=True, public_id="otro")


def test_actualizar_rechaza_alt_vacio_u_orden_negativo():
    with pytest.raises(ValidationError):
        BannerActualizar(alt="   ")
    with pytest.raises(ValidationError):
        BannerActualizar(orden=-1)
    with pytest.raises(ValidationError):
        BannerActualizar(orden=2147483648)
    assert BannerActualizar(orden=2147483647).orden == 2147483647


# --- Lista publica --------------------------------------------------------

def test_publico_solo_activos_sin_cache(escenario):
    cursor, conn, _ = escenario(filas=[(1, "https://x/1.jpg", "Uno"), (2, "https://x/2.jpg", "Dos")])
    respuesta = Response()
    datos = banners.listar_banners(respuesta)
    assert datos == [
        {"id": 1, "imagen_url": "https://x/1.jpg", "alt": "Uno"},
        {"id": 2, "imagen_url": "https://x/2.jpg", "alt": "Dos"},
    ]
    sql = cursor.consultas[0][0]
    assert "WHERE activo" in sql and "ORDER BY orden, id" in sql
    assert respuesta.headers["Cache-Control"] == "no-store"


def test_publico_sin_banners_devuelve_lista_vacia(escenario):
    escenario(filas=[])
    assert banners.listar_banners(Response()) == []


def test_publico_error_de_base_es_500(escenario):
    escenario(fallar_en="FROM banners")
    with pytest.raises(HTTPException) as e:
        banners.listar_banners(Response())
    assert e.value.status_code == 500


# --- Subir ----------------------------------------------------------------

def test_subir_crea_inactivo_con_id_generado(escenario):
    fila = (7, "https://x", "agrovetzo/banners/banner_abc", "Envio sin costo", 3, False, FECHA)
    cursor, conn, nube = escenario(filas=[fila])

    r = subir(alt="  Envio sin costo  ", orden=3)

    assert r["status"] == "ok" and r["id"] == 7 and r["activo"] is False
    subida = nube.uploads[0]
    assert subida["public_id"].startswith("agrovetzo/banners/banner_")
    assert subida["overwrite"] is False
    consulta, params = cursor.consultas[0]
    assert "INSERT INTO banners" in consulta and "FALSE" in consulta
    assert params[2] == "Envio sin costo" and params[3] == 3
    assert conn.commits == 1


def test_subir_dos_veces_usa_ids_distintos(escenario):
    fila = (1, "u", "p", "a", 0, False, FECHA)
    _, _, nube = escenario(filas=[fila, fila])
    subir()
    subir()
    assert nube.uploads[0]["public_id"] != nube.uploads[1]["public_id"]


@pytest.mark.parametrize("alt", ["", "   "])
def test_subir_alt_vacio_es_422(escenario, alt):
    _, _, nube = escenario()
    with pytest.raises(HTTPException) as e:
        subir(alt=alt)
    assert e.value.status_code == 422 and nube.uploads == []


def test_subir_formato_no_permitido_es_415(escenario):
    _, _, nube = escenario()
    with pytest.raises(HTTPException) as e:
        subir(archivo=archivo(b"GIF89a", "image/gif", "b.gif"))
    assert e.value.status_code == 415 and nube.uploads == []


def test_subir_archivo_falso_es_415(escenario):
    _, _, nube = escenario()
    with pytest.raises(HTTPException) as e:
        subir(archivo=archivo(b"esto no es una imagen", "image/jpeg"))
    assert e.value.status_code == 415 and nube.uploads == []


def test_subir_demasiado_grande_es_413(escenario):
    _, _, nube = escenario()
    grande = b"\xff\xd8\xff" + b"0" * admin.TAMANO_MAXIMO_BYTES
    with pytest.raises(HTTPException) as e:
        subir(archivo=archivo(grande))
    assert e.value.status_code == 413 and nube.uploads == []


def test_subir_cloudinary_cae_es_502_y_no_inserta(escenario):
    cursor, _, nube = escenario(upload_falla=True)
    with pytest.raises(HTTPException) as e:
        subir()
    assert e.value.status_code == 502
    assert cursor.consultas == []


def test_subir_si_falla_el_insert_limpia_cloudinary(escenario):
    cursor, conn, nube = escenario(fallar_en="INSERT INTO banners")
    with pytest.raises(HTTPException) as e:
        subir()
    assert e.value.status_code == 500
    assert conn.rollbacks == 1 and conn.commits == 0
    assert len(nube.destroys) == 1
    assert nube.destroys[0][0] == nube.uploads[0]["public_id"]


def test_subir_si_falla_insert_y_rollback_igual_limpia_cloudinary(escenario):
    _, conn, nube = escenario(fallar_en="INSERT INTO banners", rollback_falla=True)
    with pytest.raises(HTTPException) as e:
        subir()
    assert e.value.status_code == 500
    assert conn.rollbacks == 1
    assert len(nube.destroys) == 1


def test_subir_con_commit_incierto_no_destruye_la_imagen(escenario):
    fila = (1, "u", "p", "a", 0, False, FECHA)
    _, conn, nube = escenario(filas=[fila], commit_falla=True)
    with pytest.raises(HTTPException) as e:
        subir()
    assert e.value.status_code == 500
    assert nube.destroys == []


def test_subir_orden_fuera_del_rango_de_integer_se_rechaza_en_la_ruta():
    from fastapi.params import Form as FormParam
    import inspect

    por_defecto = inspect.signature(admin.subir_banner).parameters["orden"].default
    assert isinstance(por_defecto, FormParam)
    limites = {type(m).__name__: m for m in por_defecto.metadata}
    assert limites["Le"].le == 2147483647


def test_subir_si_falla_insert_y_limpieza_igual_responde_500(escenario):
    _, _, nube = escenario(fallar_en="INSERT INTO banners", destroy_falla=True)
    with pytest.raises(HTTPException) as e:
        subir()
    assert e.value.status_code == 500


# --- Actualizar -----------------------------------------------------------

def test_actualizar_solo_toca_campos_enviados(escenario):
    fila = (4, "u", "p", "a", 2, True, FECHA)
    cursor, conn, _ = escenario(filas=[fila])
    r = admin.actualizar_banner(4, BannerActualizar(activo=True, orden=2))
    consulta, params = cursor.consultas[0]
    assert "SET orden = %s, activo = %s" in consulta and "alt" not in consulta.split("WHERE")[0]
    assert params == (2, True, 4)
    assert r["status"] == "ok" and r["activo"] is True
    assert conn.commits == 1


def test_actualizar_banner_inexistente_es_404(escenario):
    _, conn, _ = escenario(filas=[])
    with pytest.raises(HTTPException) as e:
        admin.actualizar_banner(99, BannerActualizar(activo=False))
    assert e.value.status_code == 404 and conn.commits == 0


# --- Eliminar -------------------------------------------------------------

def test_eliminar_borra_en_cloudinary_y_luego_la_fila(escenario):
    cursor, conn, nube = escenario(filas=[("agrovetzo/banners/banner_x",)])
    r = admin.eliminar_banner(5)
    assert r == {"status": "ok", "id": 5}
    assert nube.destroys == [("agrovetzo/banners/banner_x", {"invalidate": True})]
    assert "DELETE FROM banners" in cursor.consultas[-1][0]
    assert conn.commits == 1


def test_eliminar_si_cloudinary_falla_conserva_la_fila(escenario):
    cursor, conn, _ = escenario(filas=[("agrovetzo/banners/banner_x",)], destroy_falla=True)
    with pytest.raises(HTTPException) as e:
        admin.eliminar_banner(5)
    assert e.value.status_code == 502
    assert not any("DELETE FROM banners" in c[0] for c in cursor.consultas)
    assert conn.commits == 0


def test_eliminar_si_la_imagen_ya_no_existe_igual_borra_la_fila(escenario):
    cursor, conn, _ = escenario(
        filas=[("agrovetzo/banners/banner_x",)], destroy_resultado={"result": "not found"}
    )
    assert admin.eliminar_banner(5)["status"] == "ok"
    assert conn.commits == 1


def test_eliminar_respuesta_rara_de_cloudinary_es_502(escenario):
    cursor, conn, _ = escenario(
        filas=[("agrovetzo/banners/banner_x",)], destroy_resultado={"result": "error"}
    )
    with pytest.raises(HTTPException) as e:
        admin.eliminar_banner(5)
    assert e.value.status_code == 502 and conn.commits == 0


def test_eliminar_inexistente_es_404(escenario):
    _, _, nube = escenario(filas=[])
    with pytest.raises(HTTPException) as e:
        admin.eliminar_banner(5)
    assert e.value.status_code == 404 and nube.destroys == []
