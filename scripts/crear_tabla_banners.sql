-- Tabla de banners del carrusel de la tienda (PostgreSQL).
-- Idempotente: se puede ejecutar mas de una vez sin efectos.
-- Ejecutar con: python scripts/crear_tabla_banners.py

CREATE TABLE IF NOT EXISTS public.banners (
    id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    imagen_url text NOT NULL
        CHECK (btrim(imagen_url) <> ''),
    public_id text NOT NULL UNIQUE
        CHECK (public_id LIKE 'agrovetzo/banners/%'),
    alt text NOT NULL
        CHECK (char_length(btrim(alt)) BETWEEN 1 AND 500),
    orden integer NOT NULL DEFAULT 0
        CHECK (orden >= 0),
    activo boolean NOT NULL DEFAULT false,
    creado_en timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS banners_publicos_orden_idx
    ON public.banners (orden, id)
    WHERE activo;
