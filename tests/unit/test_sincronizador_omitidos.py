"""
Articulos del sistema local que no se pueden publicar (sin nombre) y que ademas estan fuera de la web.
No deben frenar el resto de la sincronizacion (kits y stock). Sin tocar ninguna base ni la red.
"""
from collections import namedtuple

import pytest

from sincronizador import sincronizador

Fila = namedtuple(
    "Fila",
    "art_cod version_actual version_enviada art_nombre art_preciobase tipoart_cod art_foto art_estado "
    "llevar_web art_kit TIPO_KIT UNI_COD_COM UNI_COD_VEN",
)


def fila(art_cod, nombre="PRODUCTO", llevar_web=0, estado="S"):
    return Fila(art_cod, 1, 0, nombre, 1000, 1, None, estado, llevar_web, 0, None, 1, 1)


@pytest.mark.parametrize("nombre, llevar_web, esperado", [
    ("", 0, True),
    ("   ", 0, True),
    (None, 0, True),
    ("", 1, False),          # se quiere publicar algo sin nombre: error real, no se oculta
    ("ALAMBRE", 0, False),
    ("ALAMBRE", 1, False),
])
def test_cuando_se_omite_un_articulo(nombre, llevar_web, esperado):
    assert sincronizador.sin_nombre_y_fuera_de_la_web(fila(1, nombre, llevar_web)) is esperado


class Conn:
    def rollback(self):
        pass


def preparar(monkeypatch):
    enviados, confirmados = [], []

    def enviar(url, api_key, payload):
        enviados.append(payload["art_cod"])
        if not payload["art_nombre"].strip():
            raise sincronizador.ErrorSincronizacion("HTTP 422: nombre vacio")
        return {"status": "ok", "art_cod": payload["art_cod"], "version_actual": payload["version_actual"]}

    def confirmar(conn, cursor, payload):
        confirmados.append((payload["art_cod"], payload["version_actual"]))
        return 1

    monkeypatch.setattr(sincronizador, "enviar_articulo", enviar)
    monkeypatch.setattr(sincronizador, "confirmar_version", confirmar)
    return enviados, confirmados


def test_los_omitidos_no_se_envian_no_son_error_y_quedan_confirmados(monkeypatch):
    enviados, confirmados = preparar(monkeypatch)
    pendientes = [fila(10, "ALAMBRE", 1), fila(11, "", 0), fila(12, "   ", 0), fila(13, "CLAVOS", 0)]
    resumen = sincronizador.procesar_pendientes(Conn(), None, pendientes, "http://x", "clave")
    assert enviados == [10, 13]
    assert resumen["omitidos"] == [11, 12]
    assert resumen["ok"] == 2 and resumen["errores"] == [] and resumen["motivo_aborto"] is None
    assert (11, 1) in confirmados and (12, 1) in confirmados      # no vuelven a quedar pendientes


def test_sin_nombre_pero_para_la_web_sigue_siendo_error(monkeypatch):
    enviados, _ = preparar(monkeypatch)
    resumen = sincronizador.procesar_pendientes(Conn(), None, [fila(20, "", 1)], "http://x", "clave")
    assert enviados == [20]
    assert resumen["errores"] == [20] and resumen["omitidos"] == []


def test_el_resumen_informa_los_omitidos(monkeypatch, capsys):
    preparar(monkeypatch)
    resumen = sincronizador.procesar_pendientes(Conn(), None, [fila(11, "", 0), fila(13, "CLAVOS", 0)], "http://x", "k")
    sincronizador.imprimir_resumen(resumen)
    salida = capsys.readouterr().out
    assert "Omitidos (sin nombre y fuera de la web): 1" in salida and "Con error: 0" in salida


def test_los_omitidos_no_frenan_kits_ni_stock(monkeypatch):
    enviados, _ = preparar(monkeypatch)
    etapas = []
    monkeypatch.setattr(sincronizador, "obtener_variable", lambda n: "v")
    monkeypatch.setattr(sincronizador, "obtener_conexion", lambda: type("C", (), {"cursor": lambda s: None, "close": lambda s: None})())
    monkeypatch.setattr(sincronizador, "sincronizar_catalogos", lambda c, u, k: None)
    monkeypatch.setattr(sincronizador, "sincronizar_pedidos", lambda c, cur, k: False)
    monkeypatch.setattr(sincronizador, "leer_pendientes", lambda c: [fila(11, "", 0)])
    monkeypatch.setattr(sincronizador, "leer_pendientes_kits", lambda c: etapas.append("kits") or [])
    monkeypatch.setattr(sincronizador, "leer_pendientes_stock", lambda c: etapas.append("stock") or [])
    sincronizador.main()
    assert etapas == ["kits", "stock"] and enviados == []
