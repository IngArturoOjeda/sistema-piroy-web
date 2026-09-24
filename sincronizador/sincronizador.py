import json
import urllib.error
import urllib.request
from decimal import Decimal

import pyodbc

from sincronizador.database import obtener_conexion, obtener_variable

TIMEOUT_SEGUNDOS = 15
MAX_FALLOS_CONEXION_SEGUIDOS = 3

SQL_PENDIENTES = """
    SELECT
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
    """Fallo de un artículo puntual: se registra y se continúa."""


class ErrorConfiguracion(Exception):
    """HTTP 401/503 de FastAPI: afecta a todos los artículos. Aborta de inmediato."""


class ErrorConexion(Exception):
    """No se pudo llegar a FastAPI (red, timeout). Se tolera hasta 3 seguidos."""


class ErrorConfirmacionLocal(Exception):
    """FastAPI confirmó el artículo, pero SQL Server no pudo registrar version_enviada.
    Aborta de inmediato."""


def leer_pendientes(cursor):
    cursor.execute(SQL_PENDIENTES)
    return cursor.fetchall()


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
        if e.code in (401, 503):
            raise ErrorConfiguracion(f"FastAPI respondió HTTP {e.code}: {detalle}")
        raise ErrorSincronizacion(f"FastAPI respondió HTTP {e.code}: {detalle}")
    except OSError as e:
        motivo = getattr(e, "reason", e)
        raise ErrorConexion(f"No se pudo conectar con FastAPI: {motivo}")

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


def confirmar_version(conn, cursor, payload):
    version = payload["version_actual"]
    try:
        cursor.execute(SQL_CONFIRMAR_VERSION, (version, payload["art_cod"], version))
        filas_actualizadas = cursor.rowcount
        conn.commit()
    except pyodbc.Error as e:
        raise ErrorConfirmacionLocal(
            f"FastAPI confirmó art_cod={payload['art_cod']} versión {version}, "
            f"pero SQL Server no pudo registrar version_enviada: {e}"
        )
    return filas_actualizadas


def sincronizar_un_articulo(conn, cursor, fila, url, api_key):
    payload = construir_payload(fila)
    respuesta = enviar_articulo(url, api_key, payload)
    validar_respuesta(respuesta, payload)
    return confirmar_version(conn, cursor, payload)


def rollback_seguro(conn):
    try:
        conn.rollback()
    except Exception:
        pass


def procesar_pendientes(conn, cursor, pendientes, url, api_key):
    total = len(pendientes)
    resumen = {
        "encontrados": total,
        "ok": 0,
        "errores": [],
        "sin_procesar": 0,
        "motivo_aborto": None,
    }
    fallos_conexion_seguidos = 0

    for indice, fila in enumerate(pendientes, start=1):
        etiqueta = f"[{indice}/{total}] art_cod={fila.art_cod} version={fila.version_actual}"
        try:
            filas_actualizadas = sincronizar_un_articulo(conn, cursor, fila, url, api_key)
            resumen["ok"] += 1
            fallos_conexion_seguidos = 0
            aviso = "" if filas_actualizadas else " (version_enviada ya estaba actualizada)"
            print(f"{etiqueta} OK{aviso}")
        except ErrorConfiguracion as e:
            rollback_seguro(conn)
            resumen["motivo_aborto"] = str(e)
            resumen["sin_procesar"] = total - indice + 1
            print(f"{etiqueta} ERROR FATAL: {e}")
            break
        except ErrorConfirmacionLocal as e:
            rollback_seguro(conn)
            resumen["errores"].append(int(fila.art_cod))
            resumen["motivo_aborto"] = (
                "SQL Server no puede registrar version_enviada "
                "(no se envían más artículos)"
            )
            resumen["sin_procesar"] = total - indice
            print(f"{etiqueta} ERROR FATAL: {e}")
            break
        except ErrorConexion as e:
            rollback_seguro(conn)
            resumen["errores"].append(int(fila.art_cod))
            fallos_conexion_seguidos += 1
            print(f"{etiqueta} ERROR: {e}")
            if fallos_conexion_seguidos >= MAX_FALLOS_CONEXION_SEGUIDOS:
                resumen["motivo_aborto"] = (
                    f"{MAX_FALLOS_CONEXION_SEGUIDOS} fallos de conexión seguidos con FastAPI"
                )
                resumen["sin_procesar"] = total - indice
                break
        except ErrorSincronizacion as e:
            rollback_seguro(conn)
            resumen["errores"].append(int(fila.art_cod))
            fallos_conexion_seguidos = 0
            print(f"{etiqueta} ERROR: {e}")
        except Exception as e:
            rollback_seguro(conn)
            resumen["errores"].append(int(fila.art_cod))
            print(f"{etiqueta} ERROR inesperado: {e}")

    return resumen


def imprimir_resumen(resumen):
    print()
    print(f"Pendientes encontrados: {resumen['encontrados']}")
    print(f"Sincronizados OK: {resumen['ok']}")
    print(f"Con error: {len(resumen['errores'])}")
    if resumen["motivo_aborto"]:
        print(f"Ejecución abortada: {resumen['motivo_aborto']}")
        print(f"Sin procesar: {resumen['sin_procesar']}")
    if resumen["errores"]:
        print("art_cod con error: " + ", ".join(str(a) for a in resumen["errores"]))


def main():
    conn = None
    cursor = None
    try:
        url = obtener_variable("SYNC_API_URL")
        api_key = obtener_variable("SYNC_API_KEY")

        conn = obtener_conexion()
        cursor = conn.cursor()

        pendientes = leer_pendientes(cursor)
        if not pendientes:
            print("No hay artículos pendientes")
            return

        resumen = procesar_pendientes(conn, cursor, pendientes, url, api_key)
        imprimir_resumen(resumen)

        if resumen["errores"] or resumen["motivo_aborto"]:
            raise SystemExit(1)
    except Exception as e:
        print(f"Error en el sincronizador: {e}")
        raise SystemExit(1)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


if __name__ == "__main__":
    main()
