"""
Fragmentos SQL compartidos por el catalogo, el menu de categorias y el panel de administracion.

TIPO EFECTIVO de un articulo
----------------------------
En el sistema local, las presentaciones (por bolsa, caja, kg...) de un producto se cargan como kits
de tipo PRESENTACION, y esos kits llevan el tipo de articulo "KIT": es solo la forma de decirle al
sistema que descuenten stock de otro articulo, no una categoria real. En la tienda, un kit
PRESENTACION pertenece al tipo del articulo del que descuenta su stock (su unico componente), igual
que el resto de los articulos de ese producto. El resto de los articulos (incluidos los COMBO) usan
su propio tipo.

Todos los fragmentos esperan el alias "a" para `articulos`.
"""

# Tipo del componente de un kit PRESENTACION (NULL para cualquier otro articulo).
SQL_TIPO_COMPONENTE_LATERAL = """
    LEFT JOIN LATERAL (
        SELECT comp.tipoart_cod AS tipoart_cod
        FROM articulos_kit ak
        JOIN articulos comp ON comp.art_cod = ak.art_cod
        WHERE a.art_kit = TRUE
          AND a.tipo_kit = 'PRESENTACION'
          AND ak.art_codkit = a.art_cod
        ORDER BY ak.art_cod
        LIMIT 1
    ) tipo_comp ON TRUE
"""

# Une `tipo_articulo` (alias "t") con el tipo efectivo del articulo "a".
SQL_TIPO_EFECTIVO = (
    SQL_TIPO_COMPONENTE_LATERAL
    + """
    INNER JOIN tipo_articulo t ON t.tipoart_cod = COALESCE(tipo_comp.tipoart_cod, a.tipoart_cod)
"""
)

# El administrador puede ocultar un tipo (tipo_articulo.mostrar_web = FALSE): se ocultan el tipo y todos
# sus articulos. Los COMBO no dependen de eso: su tipo ("KIT") es solo un rotulo del sistema local y no
# una categoria. Requiere los alias "a" y "t" (de SQL_TIPO_EFECTIVO).
SQL_TIPO_VISIBLE = "(t.mostrar_web = TRUE OR a.tipo_kit = 'COMBO')"

# Condicion sobre la tabla `tipo_articulo` (alias "t"): el tipo tiene articulos publicados para mostrar en
# su categoria (contando, como corresponde, los kits PRESENTACION por el tipo de su componente).
# Los COMBO no cuentan: tienen su propia vista.
SQL_TIPO_CON_ARTICULOS = (
    """
    EXISTS (
        SELECT 1
        FROM articulos a
"""
    + SQL_TIPO_COMPONENTE_LATERAL
    + """
        WHERE COALESCE(tipo_comp.tipoart_cod, a.tipoart_cod) = t.tipoart_cod
          AND a.art_estado = 'S'
          AND a.llevar_web = TRUE
          AND a.mostrar_web = TRUE
          AND a.tipo_kit IS DISTINCT FROM 'COMBO'
    )
"""
)
