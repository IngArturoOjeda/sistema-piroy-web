-- Estado de cada tipo de articulo en la web (PostgreSQL).
-- TRUE = el tipo se puede mostrar; FALSE = el administrador lo oculto: ni el tipo ni sus
-- articulos aparecen en la tienda. Es un dato propio del e-commerce: NO viene de SQL Server.
-- Los tipos existentes quedan visibles (DEFAULT TRUE): la tienda se ve igual que antes.
-- Idempotente: se puede ejecutar mas de una vez sin efectos.
-- Ejecutar con: python scripts/agregar_columna_mostrar_web_tipo.py   (--probar valida y deshace)

ALTER TABLE public.tipo_articulo
    ADD COLUMN IF NOT EXISTS mostrar_web boolean NOT NULL DEFAULT TRUE;
