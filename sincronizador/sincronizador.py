import json
import urllib.error
import urllib.request
from decimal import Decimal

from sincronizador.database import obtener_conexion, obtener_variable

TIMEOUT_SEGUNDOS = 15

SQL_UN_PENDIENTE = """
    SELECT TOP 1
        C.art_cod,
        C.version_actual,
        C.version_enviada,
        A.art_nombre,
        A.art_preciobase,
        A.tipoart_cod,
        A.art_foto,
        A.art_estado,
        A.llevar_web
    FROM CAMBIOS_ARTICULOS C
    INNER JOIN ARTICULOS A
        ON A.art_cod = C.art_cod
    WHERE C.version_actual > C.version_enviada
    ORDER BY C.art_cod
"""

SQL_CONFIRMAR_VERSION = """
    UPDATE CAMBIOS_ARTICULOS
    SET version_enviada = ?,
        fecha_sincronizacion = GETDATE()
    WHERE art_cod = ?
      AND version_enviada < ?
"""


class ErrorSincronizacion(Exception):
    pass


def leer_un_pendiente(cursor):
    cursor.execute(SQL_UN_PENDIENTE)
    return cursor.fetchone()


def precio_para_json(precio):
    if isinstance(precio, Decimal) and precio != precio.to_integral_value():
        return str(precio)
    return int(precio)


def construir_payload(fila):
    return {
        "art_cod": int(fila.art_cod),
        "art_nombre": fila.art_nombre,
        "art_preciobase": precio_para_json(fila.art_preciobase),
        "tipoart_cod": int(fila.tipoart_cod),
        "art_foto": fila.art_foto,
        "art_estado": fila.art_estado,
        "llevar_web": bool(fila.llevar_web),
        "version_actual": int(fila.version_actual),
    }


def enviar_articulo(url, api_key, payload):
    solicitud = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-API-Key": api_key,
        },
    )
    try:
        with urllib.request.urlopen(solicitud, timeout=TIMEOUT_SEGUNDOS) as respuesta:
            codigo = respuesta.status
            cuerpo = respuesta.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        detalle = e.read().decode("utf-8", errors="replace")
        raise ErrorSincronizacion(f"FastAPI respondió HTTP {e.code}: {detalle}")
    except urllib.error.URLError as e:
        raise ErrorSincronizacion(f"No se pudo conectar con FastAPI: {e.reason}")

    if codigo != 200:
        raise ErrorSincronizacion(f"FastAPI respondió HTTP {codigo}: {cuerpo}")

    try:
        return json.loads(cuerpo)
    except json.JSONDecodeError:
        raise ErrorSincronizacion(f"Respuesta de FastAPI no es JSON válido: {cuerpo}")


def validar_respuesta(respuesta, payload):
    if not isinstance(respuesta, dict):
        raise ErrorSincronizacion(f"Respuesta inesperada de FastAPI: {respuesta}")
    if respuesta.get("status") != "ok":
        raise ErrorSincronizacion(f"FastAPI no confirmó status ok: {respuesta}")
    if respuesta.get("art_cod") != payload["art_cod"]:
        raise ErrorSincronizacion(
            f"art_cod devuelto ({respuesta.get('art_cod')}) distinto del enviado ({payload['art_cod']})"
        )
    if respuesta.get("version_actual") != payload["version_actual"]:
        raise ErrorSincronizacion(
            f"version_actual devuelta ({respuesta.get('version_actual')}) distinta de la enviada ({payload['version_actual']})"
        )


def main():
    conn = None
    cursor = None
    try:
        url = obtener_variable("SYNC_API_URL")
        api_key = obtener_variable("SYNC_API_KEY")

        conn = obtener_conexion()
        cursor = conn.cursor()

        fila = leer_un_pendiente(cursor)
        if fila is None:
            print("No hay artículos pendientes")
            return

        payload = construir_payload(fila)
        print(
            f"Enviando art_cod={payload['art_cod']} "
            f"version_actual={payload['version_actual']}"
        )

        respuesta = enviar_articulo(url, api_key, payload)
        validar_respuesta(respuesta, payload)

        version = payload["version_actual"]
        cursor.execute(SQL_CONFIRMAR_VERSION, (version, payload["art_cod"], version))
        filas_actualizadas = cursor.rowcount
        conn.commit()

        if filas_actualizadas:
            print(f"OK: version_enviada={version} confirmada en SQL Server")
        else:
            print(
                "Aviso: FastAPI confirmó, pero version_enviada no cambió "
                "(ya estaba en esa versión o en una superior)"
            )
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"Error en el sincronizador (version_enviada NO actualizada): {e}")
        raise SystemExit(1)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


if __name__ == "__main__":
    main()
