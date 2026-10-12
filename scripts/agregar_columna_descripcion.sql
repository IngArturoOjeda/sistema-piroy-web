-- Descripcion comercial de cada articulo para la pagina de detalle (PostgreSQL).
-- Es un dato propio del e-commerce: NO viene de SQL Server y el sincronizador
-- no la toca (su upsert actualiza una lista fija de columnas que no la incluye).
-- Idempotente: se puede ejecutar mas de una vez sin efectos.
-- Ejecutar con: python scripts/agregar_columna_descripcion.py

ALTER TABLE public.articulos
    ADD COLUMN IF NOT EXISTS descripcion text
        CHECK (descripcion IS NULL OR char_length(descripcion) <= 2000);
