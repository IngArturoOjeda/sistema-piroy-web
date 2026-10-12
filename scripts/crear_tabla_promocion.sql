-- Promociones vigentes por articulo (PostgreSQL). Misma forma que la tabla PROMOCION
-- del sistema local (art_cod, art_valor, fec_desde, fec_hasta): cada fila es el PRECIO
-- PROMOCIONAL de un articulo entre dos fechas, ambas inclusivas.
-- Idempotente: se puede ejecutar mas de una vez sin efectos.
-- Ejecutar con: python scripts/crear_tabla_promocion.py
--
-- Se cargara desde el sistema local con el sincronizador (etapa posterior). Mientras la
-- tabla este vacia, la tienda se ve exactamente igual que antes.

CREATE TABLE IF NOT EXISTS public.promocion (
    id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    art_cod bigint NOT NULL
        REFERENCES public.articulos (art_cod) ON DELETE CASCADE,
    art_valor numeric(14, 0) NOT NULL
        CHECK (art_valor > 0),
    fec_desde date NOT NULL,
    fec_hasta date NOT NULL,
    CHECK (fec_hasta >= fec_desde)
);

CREATE INDEX IF NOT EXISTS promocion_art_idx
    ON public.promocion (art_cod, fec_desde, fec_hasta);
