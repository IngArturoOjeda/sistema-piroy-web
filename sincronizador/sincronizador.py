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
        A.llevar_web,
        A.art_kit,
        A.UNI_COD_COM,
        A.UNI_COD_VEN
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


def valor_opcional_entero(valor):
    if valor is None:
        return None
    return int(valor)


def construir_payload(fila):
    return {
        "art_cod": int(fila.art_cod),
        "art_nombre": fila.art_nombre,
        "art_preciobase": precio_para_json(fila.art_preciobase),
        "tipoart_cod": int(fila.tipoart_cod),
        "art_foto": fila.art_foto,
        "art_estado": fila.art_estado,
        "llevar_web": bool(fila.llevar_web),
        "art_kit": bool(fila.art_kit),
        "uni_cod_com": valor_opcional_entero(fila.UNI_COD_COM),
        "uni_cod_ven": valor_opcional_entero(fila.UNI_COD_VEN),
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


SQL_PENDIENTES_KITS = """
    SELECT
        C.art_codkit,
        C.version_actual,
        C.version_enviada
    FROM CAMBIOS_ARTICULOS_KIT C
    WHERE C.version_actual > C.version_enviada
    ORDER BY C.art_codkit
"""

SQL_COMPONENTES_KIT = """
    SELECT idkit, ART_COD, ART_CANTIDAD
    FROM ARTICULOS_KIT
    WHERE ART_CODKIT = ?
    ORDER BY idkit
"""

SQL_CONFIRMAR_VERSION_KIT = """
    UPDATE CAMBIOS_ARTICULOS_KIT
    SET version_enviada = ?,
        fecha_sincronizacion = GETDATE()
    WHERE art_codkit = ?
      AND version_enviada < ?
"""


def leer_pendientes_kits(cursor):
    cursor.execute(SQL_PENDIENTES_KITS)
    return cursor.fetchall()


def cantidad_para_json(cantidad):
    return str(cantidad)


def construir_payload_kit(cursor, fila_kit):
    cursor.execute(SQL_COMPONENTES_KIT, (fila_kit.art_codkit,))
    componentes = [
        {
            "idkit": int(c.idkit),
            "art_cod": int(c.ART_COD),
            "art_cantidad": cantidad_para_json(c.ART_CANTIDAD),
        }
        for c in cursor.fetchall()
    ]
    return {
        "art_codkit": int(fila_kit.art_codkit),
        "componentes": componentes,
        "version_actual": int(fila_kit.version_actual),
    }


def validar_respuesta_kit(respuesta, payload):
    if not isinstance(respuesta, dict):
        raise ErrorSincronizacion(f"Respuesta inesperada de FastAPI: {respuesta}")
    if respuesta.get("status") != "ok":
        raise ErrorSincronizacion(f"FastAPI no confirmó status ok: {respuesta}")
    if respuesta.get("art_codkit") != payload["art_codkit"]:
        raise ErrorSincronizacion(
            f"art_codkit devuelto ({respuesta.get('art_codkit')}) distinto del enviado ({payload['art_codkit']})"
        )
    if respuesta.get("version_actual") != payload["version_actual"]:
        raise ErrorSincronizacion(
            f"version_actual devuelta ({respuesta.get('version_actual')}) distinta de la enviada ({payload['version_actual']})"
        )


def confirmar_version_kit(conn, cursor, payload):
    version = payload["version_actual"]
    try:
        cursor.execute(SQL_CONFIRMAR_VERSION_KIT, (version, payload["art_codkit"], version))
        filas_actualizadas = cursor.rowcount
        conn.commit()
    except pyodbc.Error as e:
        raise ErrorConfirmacionLocal(
            f"FastAPI confirmó art_codkit={payload['art_codkit']} versión {version}, "
            f"pero SQL Server no pudo registrar version_enviada en CAMBIOS_ARTICULOS_KIT: {e}"
        )
    return filas_actualizadas


def sincronizar_un_kit(conn, cursor, fila_kit, url, api_key):
    payload = construir_payload_kit(cursor, fila_kit)
    respuesta = enviar_articulo(url, api_key, payload)
    validar_respuesta_kit(respuesta, payload)
    return confirmar_version_kit(conn, cursor, payload)


def procesar_pendientes_kits(conn, cursor, pendientes, url, api_key):
    total = len(pendientes)
    resumen = {
        "encontrados": total,
        "ok": 0,
        "errores": [],
        "sin_procesar": 0,
        "motivo_aborto": None,
    }
    fallos_conexion_seguidos = 0

    for indice, fila_kit in enumerate(pendientes, start=1):
        etiqueta = f"[{indice}/{total}] art_codkit={fila_kit.art_codkit} version={fila_kit.version_actual}"
        try:
            filas_actualizadas = sincronizar_un_kit(conn, cursor, fila_kit, url, api_key)
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
            resumen["errores"].append(int(fila_kit.art_codkit))
            resumen["motivo_aborto"] = (
                "SQL Server no puede registrar version_enviada "
                "(no se envían más kits)"
            )
            resumen["sin_procesar"] = total - indice
            print(f"{etiqueta} ERROR FATAL: {e}")
            break
        except ErrorConexion as e:
            rollback_seguro(conn)
            resumen["errores"].append(int(fila_kit.art_codkit))
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
            resumen["errores"].append(int(fila_kit.art_codkit))
            fallos_conexion_seguidos = 0
            print(f"{etiqueta} ERROR: {e}")
        except Exception as e:
            rollback_seguro(conn)
            resumen["errores"].append(int(fila_kit.art_codkit))
            print(f"{etiqueta} ERROR inesperado: {e}")

    return resumen


SQL_PENDIENTES_STOCK = """
    SELECT
        C.art_cod,
        C.version_actual,
        C.version_enviada,
        ISNULL(S.sto_cantidad, 0) AS sto_cantidad
    FROM CAMBIOS_STOCK C
    INNER JOIN ARTICULOS A
        ON A.art_cod = C.art_cod
    LEFT JOIN STOCK S
        ON S.art_cod = C.art_cod
    WHERE C.version_actual > C.version_enviada
      AND A.art_kit = 0
      AND A.llevar_web = 1
    ORDER BY C.art_cod
"""

SQL_CONFIRMAR_VERSION_STOCK = """
    UPDATE CAMBIOS_STOCK
    SET version_enviada = ?,
        fecha_sincronizacion = GETDATE()
    WHERE art_cod = ?
      AND version_enviada < ?
"""


def leer_pendientes_stock(cursor):
    cursor.execute(SQL_PENDIENTES_STOCK)
    return cursor.fetchall()


def construir_payload_stock(fila_stock):
    return {
        "art_cod": int(fila_stock.art_cod),
        "cantidad": cantidad_para_json(fila_stock.sto_cantidad),
        "version_actual": int(fila_stock.version_actual),
    }


def validar_respuesta_stock(respuesta, payload):
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


def confirmar_version_stock(conn, cursor, payload):
    version = payload["version_actual"]
    try:
        cursor.execute(SQL_CONFIRMAR_VERSION_STOCK, (version, payload["art_cod"], version))
        filas_actualizadas = cursor.rowcount
        conn.commit()
    except pyodbc.Error as e:
        raise ErrorConfirmacionLocal(
            f"FastAPI confirmó art_cod={payload['art_cod']} versión {version}, "
            f"pero SQL Server no pudo registrar version_enviada en CAMBIOS_STOCK: {e}"
        )
    return filas_actualizadas


def sincronizar_un_stock(conn, cursor, fila_stock, url, api_key):
    payload = construir_payload_stock(fila_stock)
    respuesta = enviar_articulo(url, api_key, payload)
    validar_respuesta_stock(respuesta, payload)
    return confirmar_version_stock(conn, cursor, payload)


def procesar_pendientes_stock(conn, cursor, pendientes, url, api_key):
    total = len(pendientes)
    resumen = {
        "encontrados": total,
        "ok": 0,
        "errores": [],
        "sin_procesar": 0,
        "motivo_aborto": None,
    }
    fallos_conexion_seguidos = 0

    for indice, fila_stock in enumerate(pendientes, start=1):
        etiqueta = f"[{indice}/{total}] art_cod={fila_stock.art_cod} version={fila_stock.version_actual}"
        try:
            filas_actualizadas = sincronizar_un_stock(conn, cursor, fila_stock, url, api_key)
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
            resumen["errores"].append(int(fila_stock.art_cod))
            resumen["motivo_aborto"] = (
                "SQL Server no puede registrar version_enviada "
                "(no se envía más stock)"
            )
            resumen["sin_procesar"] = total - indice
            print(f"{etiqueta} ERROR FATAL: {e}")
            break
        except ErrorConexion as e:
            rollback_seguro(conn)
            resumen["errores"].append(int(fila_stock.art_cod))
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
            resumen["errores"].append(int(fila_stock.art_cod))
            fallos_conexion_seguidos = 0
            print(f"{etiqueta} ERROR: {e}")
        except Exception as e:
            rollback_seguro(conn)
            resumen["errores"].append(int(fila_stock.art_cod))
            print(f"{etiqueta} ERROR inesperado: {e}")

    return resumen


def main():
    conn = None
    cursor = None
    try:
        url = obtener_variable("SYNC_API_URL")
        api_key = obtener_variable("SYNC_API_KEY")

        conn = obtener_conexion()
        cursor = conn.cursor()

        pendientes = leer_pendientes(cursor)
        if pendientes:
            resumen = procesar_pendientes(conn, cursor, pendientes, url, api_key)
            imprimir_resumen(resumen)
            error_articulos = bool(resumen["errores"] or resumen["motivo_aborto"])
        else:
            print("No hay artículos pendientes")
            error_articulos = False

        if error_articulos:
            # No se procesan kits ni stock: pueden depender de articulos que no llegaron a Postgres.
            raise SystemExit(1)

        pendientes_kits = leer_pendientes_kits(cursor)
        if pendientes_kits:
            url_kits = obtener_variable("SYNC_API_URL_KITS")
            resumen_kits = procesar_pendientes_kits(conn, cursor, pendientes_kits, url_kits, api_key)
            imprimir_resumen(resumen_kits)
            error_kits = bool(resumen_kits["errores"] or resumen_kits["motivo_aborto"])
        else:
            print("No hay kits pendientes")
            error_kits = False

        # Los errores de kits NO impiden procesar stock: el stock fisico
        # no depende de la composicion del kit.
        pendientes_stock = leer_pendientes_stock(cursor)
        if pendientes_stock:
            url_stock = obtener_variable("SYNC_API_URL_STOCK")
            resumen_stock = procesar_pendientes_stock(conn, cursor, pendientes_stock, url_stock, api_key)
            imprimir_resumen(resumen_stock)
            error_stock = bool(resumen_stock["errores"] or resumen_stock["motivo_aborto"])
        else:
            print("No hay stock pendiente")
            error_stock = False

        if error_kits or error_stock:
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
