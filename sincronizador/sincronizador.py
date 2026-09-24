from sincronizador.database import obtener_conexion

SQL_ARTICULOS_PENDIENTES = """
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


def leer_articulos_pendientes(cursor):
    cursor.execute(SQL_ARTICULOS_PENDIENTES)
    return cursor.fetchall()


def main():
    conn = None
    cursor = None
    try:
        conn = obtener_conexion()
        cursor = conn.cursor()

        pendientes = leer_articulos_pendientes(cursor)
        print(f"Artículos pendientes: {len(pendientes)}")

        for fila in pendientes:
            print(
                f"art_cod={fila.art_cod} | "
                f"version_actual={fila.version_actual} | "
                f"version_enviada={fila.version_enviada} | "
                f"art_nombre={fila.art_nombre!r} | "
                f"art_preciobase={fila.art_preciobase} | "
                f"tipoart_cod={fila.tipoart_cod} | "
                f"art_foto={fila.art_foto!r} | "
                f"art_estado={fila.art_estado!r} | "
                f"llevar_web={fila.llevar_web}"
            )
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
