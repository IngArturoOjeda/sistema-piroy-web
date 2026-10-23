import json
import urllib.error
import urllib.request
from datetime import datetime
from decimal import Decimal

import pyodbc

from sincronizador.database import obtener_conexion, obtener_variable

TIMEOUT_SEGUNDOS = 15
MAX_FALLOS_CONEXION_SEGUIDOS = 3
PEDIDOS_POR_PAGINA = 50
MAX_PAGINAS_PEDIDOS = 20

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
        A.TIPO_KIT,
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


SQL_TIPOS = """
    SELECT TIPOART_COD, TIPOART_DESC
    FROM TIPOARTICULO
    ORDER BY TIPOART_COD
"""

SQL_UNIDADES = """
    SELECT UNI_COD, UNI_NOMBRE
    FROM UNIDADMEDIDA
    ORDER BY UNI_COD
"""


def construir_payload_catalogos(cursor):
    """Lista completa de tipos y unidades del sistema local (son pocos). FastAPI crea los que faltan
    y actualiza el nombre; no borra nada ni toca lo que se decide en el panel."""
    cursor.execute(SQL_TIPOS)
    tipos = [
        {"tipoart_cod": int(fila.TIPOART_COD), "tipoart_desc": str(fila.TIPOART_DESC).strip()}
        for fila in cursor.fetchall()
        if fila.TIPOART_COD is not None and fila.TIPOART_DESC is not None and str(fila.TIPOART_DESC).strip()
    ]
    cursor.execute(SQL_UNIDADES)
    unidades = [
        {"uni_cod": int(fila.UNI_COD), "uni_nombre": str(fila.UNI_NOMBRE).strip()}
        for fila in cursor.fetchall()
        if fila.UNI_COD is not None and fila.UNI_NOMBRE is not None and str(fila.UNI_NOMBRE).strip()
    ]
    return {"tipos": tipos, "unidades": unidades}


def sincronizar_catalogos(cursor, url, api_key):
    """Envia tipos y unidades ANTES de los articulos: cada articulo exige que su tipo y su unidad existan.
    Cualquier error se propaga (los articulos no se envian si esto falla)."""
    payload = construir_payload_catalogos(cursor)
    respuesta = enviar_articulo(url, api_key, payload)
    if (
        not isinstance(respuesta, dict)
        or respuesta.get("status") != "ok"
        or respuesta.get("tipos") != len(payload["tipos"])
        or respuesta.get("unidades") != len(payload["unidades"])
    ):
        raise ErrorSincronizacion(f"FastAPI no confirmó los tipos y unidades: {respuesta}")
    print(f"Tipos y unidades al día: {len(payload['tipos'])} tipos, {len(payload['unidades'])} unidades")


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
        "tipo_kit": fila.TIPO_KIT,
        "uni_cod_com": valor_opcional_entero(fila.UNI_COD_COM),
        "uni_cod_ven": valor_opcional_entero(fila.UNI_COD_VEN),
        "version_actual": int(fila.version_actual),
    }


def enviar_articulo(url, api_key, payload, metodo="POST"):
    solicitud = urllib.request.Request(
        url,
        data=None if payload is None else json.dumps(payload).encode("utf-8"),
        method=metodo,
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


def sin_nombre_y_fuera_de_la_web(fila):
    """Articulo sin nombre que NO va a la web (llevar_web = 0): no hay nada que publicar, y la web rechazaria el
    nombre vacio. Se omite sin tratarlo como error para que no frene kits ni stock. Si llevar_web = 1 si es un
    error real (se quiere publicar algo sin nombre) y se envia para que el servidor lo rechace."""
    return not (fila.art_nombre or "").strip() and not bool(fila.llevar_web)


def omitir_articulo(conn, cursor, fila):
    """Confirma la version localmente sin enviar nada. Si mas adelante le ponen nombre (o llevar_web = 1), el
    trigger vuelve a anotarlo y se envia."""
    return confirmar_version(conn, cursor, {"art_cod": int(fila.art_cod), "version_actual": int(fila.version_actual)})


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
        "omitidos": [],
    }
    fallos_conexion_seguidos = 0

    for indice, fila in enumerate(pendientes, start=1):
        etiqueta = f"[{indice}/{total}] art_cod={fila.art_cod} version={fila.version_actual}"
        try:
            if sin_nombre_y_fuera_de_la_web(fila):
                omitir_articulo(conn, cursor, fila)
                resumen["omitidos"].append(int(fila.art_cod))
                print(f"{etiqueta} OMITIDO (sin nombre y fuera de la web)")
                continue
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
    if resumen.get("omitidos"):
        print(f"Omitidos (sin nombre y fuera de la web): {len(resumen['omitidos'])}")
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


# Pedidos de la web (PostgreSQL en Render -> PEDIDOS_WEB y PEDIDOS_WEB_DETALLE en SQL Server).
# Se guarda cabecera y detalle en UNA transaccion y solo despues se avisa a la web que el pedido fue recibido.
# Si se corta entre una cosa y la otra, la proxima corrida ve que el pedido ya esta guardado y solo lo marca: no se duplica.
# No toca stock: el pedido web solo queda registrado para que lo atienda el asesor.
SQL_PEDIDO_EXISTE = "SELECT 1 FROM PEDIDOS_WEB WHERE id_pedido_web = ?"

SQL_INSERTAR_PEDIDO = """
    INSERT INTO PEDIDOS_WEB (id_pedido_web, cliente_nombre, cliente_direccion, cliente_telefono, fecha_pedido)
    VALUES (?, ?, ?, ?, ?)
"""

SQL_INSERTAR_PEDIDO_DETALLE = """
    INSERT INTO PEDIDOS_WEB_DETALLE (id_pedido_web, art_cod, cantidad, precio_unitario, valor_descuento, valor_pagar)
    VALUES (?, ?, ?, ?, 0, ?)
"""


def fecha_local(texto):
    """La web entrega la fecha con zona horaria (UTC); el negocio la guarda en la hora de este servidor."""
    return datetime.fromisoformat(texto).astimezone().replace(tzinfo=None)


def recortar(texto, largo):
    """Los textos del cliente se ajustan al largo de la columna: un pedido real no debe quedar trabado por eso."""
    return None if texto is None else str(texto).strip()[:largo]


def construir_filas_pedido(pedido):
    """Valida el pedido que llega de la web y arma lo que se inserta. Cualquier dato raro es un error del pedido
    (no se guarda nada y no se marca recibido)."""
    try:
        id_pedido = int(pedido["id_pedido"])
        detalle = pedido["detalle"]
        if id_pedido <= 0 or not detalle:
            raise ValueError("pedido sin numero valido o sin articulos")
        cabecera = (
            id_pedido,
            (str(pedido["cliente_nombre"]).strip() or "SIN NOMBRE")[:150],
            recortar(pedido.get("cliente_direccion"), 300),
            recortar(pedido.get("cliente_telefono"), 50),
            fecha_local(pedido["fecha_pedido"]),
        )
        filas = []
        for linea in detalle:
            art_cod = int(linea["art_cod"])
            cantidad = Decimal(str(linea["cantidad"]))
            precio = Decimal(str(linea["precio_unitario"]))
            if cantidad <= 0 or precio < 0:
                raise ValueError(f"cantidad o precio invalido en art_cod={art_cod}")
            filas.append((id_pedido, art_cod, cantidad, precio, (cantidad * precio).quantize(Decimal("0.01"))))
    except (KeyError, TypeError, ValueError, ArithmeticError) as e:
        raise ErrorSincronizacion(f"Pedido con datos invalidos: {e}")
    return cabecera, filas


def guardar_pedido(conn, cursor, cabecera, filas):
    """Devuelve True si lo guardo ahora, False si ya estaba guardado (reintento)."""
    try:
        cursor.execute(SQL_PEDIDO_EXISTE, (cabecera[0],))
        if cursor.fetchone() is not None:
            return False
        cursor.execute(SQL_INSERTAR_PEDIDO, cabecera)
        for fila in filas:
            cursor.execute(SQL_INSERTAR_PEDIDO_DETALLE, fila)
        conn.commit()
    except pyodbc.Error as e:
        rollback_seguro(conn)
        raise ErrorSincronizacion(f"SQL Server no pudo guardar el pedido {cabecera[0]}: {e}")
    return True


def marcar_pedido_recibido(url_base, api_key, id_pedido):
    respuesta = enviar_articulo(f"{url_base}/{id_pedido}/recibido", api_key, None)
    if not isinstance(respuesta, dict) or respuesta.get("status") != "ok" or respuesta.get("id_pedido") != id_pedido:
        raise ErrorSincronizacion(f"FastAPI no confirmó el pedido {id_pedido}: {respuesta}")


def leer_pedidos_pendientes_web(url, api_key, despues_de=0):
    separador = "&" if "?" in url else "?"
    respuesta = enviar_articulo(f"{url}{separador}limite={PEDIDOS_POR_PAGINA}&despues_de={despues_de}", api_key, None, metodo="GET")
    if not isinstance(respuesta, dict) or respuesta.get("status") != "ok" or not isinstance(respuesta.get("pedidos"), list):
        raise ErrorSincronizacion(f"Respuesta inesperada al pedir los pedidos: {respuesta}")
    return respuesta["pedidos"]


def procesar_pedidos(conn, cursor, pedidos, url_recibido, api_key):
    total = len(pedidos)
    resumen = {"encontrados": total, "ok": 0, "ya_estaban": 0, "errores": [], "sin_procesar": 0, "motivo_aborto": None}
    fallos_conexion_seguidos = 0

    for indice, pedido in enumerate(pedidos, start=1):
        id_pedido = pedido.get("id_pedido") if isinstance(pedido, dict) else None
        etiqueta = f"[{indice}/{total}] pedido={id_pedido}"
        try:
            cabecera, filas = construir_filas_pedido(pedido)
            guardado = guardar_pedido(conn, cursor, cabecera, filas)
            marcar_pedido_recibido(url_recibido, api_key, cabecera[0])
            resumen["ok"] += 1
            if not guardado:
                resumen["ya_estaban"] += 1
            fallos_conexion_seguidos = 0
            print(f"{etiqueta} OK" + ("" if guardado else " (ya estaba guardado en SQL Server)"))
        except ErrorConfiguracion as e:
            resumen["motivo_aborto"] = str(e)
            resumen["sin_procesar"] = total - indice + 1
            print(f"{etiqueta} ERROR FATAL: {e}")
            break
        except ErrorConexion as e:
            # El pedido ya quedo guardado en SQL Server; la proxima corrida solo lo marca como recibido.
            resumen["errores"].append(id_pedido)
            fallos_conexion_seguidos += 1
            print(f"{etiqueta} ERROR: {e}")
            if fallos_conexion_seguidos >= MAX_FALLOS_CONEXION_SEGUIDOS:
                resumen["motivo_aborto"] = f"{MAX_FALLOS_CONEXION_SEGUIDOS} fallos de conexión seguidos con FastAPI"
                resumen["sin_procesar"] = total - indice
                break
        except ErrorSincronizacion as e:
            resumen["errores"].append(id_pedido)
            fallos_conexion_seguidos = 0
            print(f"{etiqueta} ERROR: {e}")
        except Exception as e:
            rollback_seguro(conn)
            resumen["errores"].append(id_pedido)
            print(f"{etiqueta} ERROR inesperado: {e}")

    return resumen


def sincronizar_pedidos(conn, cursor, api_key):
    """Paso aparte: un error aqui no frena articulos, kits ni stock (y al reves). Devuelve True si hubo error."""
    try:
        url = obtener_variable("SYNC_API_URL_PEDIDOS")
        url_recibido = obtener_variable("SYNC_API_URL_PEDIDOS_RECIBIDO")
        hubo_error = False
        hubo_pedidos = False
        despues_de = 0
        # Se pide por paginas: un pedido que falla sigue pendiente, pero no traba a los mas nuevos.
        for _ in range(MAX_PAGINAS_PEDIDOS):
            pedidos = leer_pedidos_pendientes_web(url, api_key, despues_de)
            if not pedidos:
                break
            hubo_pedidos = True
            resumen = procesar_pedidos(conn, cursor, pedidos, url_recibido.rstrip("/"), api_key)
            print(f"Pedidos web: {resumen['ok']} guardados ({resumen['ya_estaban']} ya estaban), "
                  f"{len(resumen['errores'])} con error, {resumen['sin_procesar']} sin procesar")
            if resumen["motivo_aborto"]:
                print(f"Pedidos web detenidos: {resumen['motivo_aborto']}")
            hubo_error = hubo_error or bool(resumen["errores"] or resumen["motivo_aborto"])
            if resumen["motivo_aborto"] or len(pedidos) < PEDIDOS_POR_PAGINA:
                break
            despues_de = max(int(p["id_pedido"]) for p in pedidos)
        if not hubo_pedidos:
            print("No hay pedidos web pendientes")
        return hubo_error
    except Exception as e:
        print(f"Error en los pedidos web: {e}")
        return True


def main():
    conn = None
    cursor = None
    try:
        url = obtener_variable("SYNC_API_URL")
        api_key = obtener_variable("SYNC_API_KEY")

        conn = obtener_conexion()
        cursor = conn.cursor()

        # Los pedidos de clientes van primero: son lo mas urgente para el negocio y no dependen del catalogo.
        error_pedidos = sincronizar_pedidos(conn, cursor, api_key)

        pendientes = leer_pendientes(cursor)
        if pendientes:
            sincronizar_catalogos(cursor, obtener_variable("SYNC_API_URL_CATALOGOS"), api_key)
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

        if error_kits or error_stock or error_pedidos:
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
