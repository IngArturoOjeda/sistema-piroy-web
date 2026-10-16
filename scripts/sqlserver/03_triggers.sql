/*
  AGRO-VETZO - Paso 3 de 4: triggers que anotan los cambios (SQL Server 2012, base Piroy)

  Cada trigger solo escribe en las tablas CAMBIOS_*: no usa Internet ni toca otras tablas.
  Se pueden volver a correr (borra y crea de nuevo cada trigger).

    TR_ARTICULOS_CAMBIOS_WEB      sobre ARTICULOS        (articulo nuevo o modificado)
    TR_STOCK_CAMBIO               sobre STOCK            (venta, compra, ajuste)
    TRG_ARTICULOS_KIT_CAMBIOS     sobre ARTICULOS_KIT    (componentes de los kits)

  Cambio respecto de los scripts de prueba: el trigger de ARTICULOS ahora tambien vigila art_kit, TIPO_KIT,
  UNI_COD_COM y UNI_COD_VEN (antes un cambio solo de unidad no llegaba a la web), y si un articulo modificado
  no tiene fila en CAMBIOS_ARTICULOS la crea (antes quedaba sin avisar).

  Requiere el paso 1 (las tablas CAMBIOS_* deben existir: si un trigger existe sin su tabla, las ventas fallan).
  Se recomienda correrlo fuera del horario de ventas, y probar una venta al terminar.
*/
IF DB_NAME() NOT LIKE N'Piroy%'
BEGIN
    RAISERROR('Este script es para la base Piroy (o una copia de prueba llamada Piroy_algo). Elige Piroy en la barra de SSMS. No se ejecuta nada.', 16, 1);
    SET NOEXEC ON;
END
GO

IF OBJECT_ID('dbo.CAMBIOS_ARTICULOS', 'U') IS NULL OR OBJECT_ID('dbo.CAMBIOS_STOCK', 'U') IS NULL
   OR OBJECT_ID('dbo.CAMBIOS_ARTICULOS_KIT', 'U') IS NULL
   OR COL_LENGTH('dbo.ARTICULOS', 'llevar_web') IS NULL OR COL_LENGTH('dbo.ARTICULOS', 'TIPO_KIT') IS NULL
BEGIN
    RAISERROR('Falta correr el paso 1 (tablas CAMBIOS_* y columnas nuevas). No se ejecuta nada.', 16, 1);
    SET NOEXEC ON;
END
GO

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

-- ---------------------------------------------------------------- ARTICULOS
IF OBJECT_ID('dbo.TR_ARTICULOS_CAMBIOS_WEB', 'TR') IS NOT NULL DROP TRIGGER dbo.TR_ARTICULOS_CAMBIOS_WEB;
GO
CREATE TRIGGER dbo.TR_ARTICULOS_CAMBIOS_WEB
ON dbo.ARTICULOS
AFTER INSERT, UPDATE
AS
BEGIN
    SET NOCOUNT ON;

    -- 1. Articulos nuevos: version 1 (pendiente) solo si ya nacen para la web; si no, version 0
    INSERT INTO CAMBIOS_ARTICULOS (art_cod, version_actual, version_enviada, fecha_cambio)
    SELECT i.art_cod,
           CASE WHEN i.llevar_web = 1 THEN 1 ELSE 0 END,
           0,
           GETDATE()
    FROM inserted i
    LEFT JOIN deleted d ON i.art_cod = d.art_cod
    WHERE d.art_cod IS NULL
      AND NOT EXISTS (SELECT 1 FROM CAMBIOS_ARTICULOS c WHERE c.art_cod = i.art_cod);

    -- 2. Articulos modificados en algo que muestra la web
    DECLARE @Modificados TABLE (art_cod NUMERIC(18,0) PRIMARY KEY);

    INSERT INTO @Modificados (art_cod)
    SELECT i.art_cod
    FROM inserted i
    INNER JOIN deleted d ON d.art_cod = i.art_cod
    WHERE ISNULL(i.art_nombre, '')     <> ISNULL(d.art_nombre, '')
       OR ISNULL(i.art_preciobase, 0)  <> ISNULL(d.art_preciobase, 0)
       OR ISNULL(i.tipoart_cod, 0)     <> ISNULL(d.tipoart_cod, 0)
       OR ISNULL(i.art_foto, '')       <> ISNULL(d.art_foto, '')
       OR ISNULL(i.art_estado, '')     <> ISNULL(d.art_estado, '')
       OR ISNULL(i.llevar_web, 0)      <> ISNULL(d.llevar_web, 0)
       OR ISNULL(i.art_kit, -1)        <> ISNULL(d.art_kit, -1)
       OR ISNULL(i.TIPO_KIT, '')       <> ISNULL(d.TIPO_KIT, '')
       OR ISNULL(i.UNI_COD_COM, -1)    <> ISNULL(d.UNI_COD_COM, -1)
       OR ISNULL(i.UNI_COD_VEN, -1)    <> ISNULL(d.UNI_COD_VEN, -1);

    -- los que ya tienen fila: suben de version
    UPDATE c
    SET c.version_actual = c.version_actual + 1,
        c.fecha_cambio = GETDATE()
    FROM CAMBIOS_ARTICULOS c
    INNER JOIN @Modificados m ON m.art_cod = c.art_cod;

    -- los que no tienen fila todavia: se crean como pendientes
    INSERT INTO CAMBIOS_ARTICULOS (art_cod, version_actual, version_enviada, fecha_cambio)
    SELECT m.art_cod, 1, 0, GETDATE()
    FROM @Modificados m
    WHERE NOT EXISTS (SELECT 1 FROM CAMBIOS_ARTICULOS c WHERE c.art_cod = m.art_cod);
END;
GO

-- ---------------------------------------------------------------- STOCK
IF OBJECT_ID('dbo.TR_STOCK_CAMBIO', 'TR') IS NOT NULL DROP TRIGGER dbo.TR_STOCK_CAMBIO;
GO
CREATE TRIGGER dbo.TR_STOCK_CAMBIO
ON dbo.STOCK
AFTER INSERT, UPDATE, DELETE
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @ArticulosAfectados TABLE (art_cod NUMERIC(18,0) PRIMARY KEY);

    INSERT INTO @ArticulosAfectados (art_cod)
    -- INSERT: fila nueva (esta en inserted, no en deleted)
    SELECT i.art_cod
    FROM inserted i
    WHERE i.art_cod IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM deleted d WHERE d.sto_id = i.sto_id)

    UNION

    -- UPDATE: marca el art_cod NUEVO, si cambio cantidad o si cambio art_cod
    SELECT i.art_cod
    FROM inserted i
    INNER JOIN deleted d ON d.sto_id = i.sto_id
    WHERE i.art_cod IS NOT NULL
      AND (
            ISNULL(i.sto_cantidad, 0) <> ISNULL(d.sto_cantidad, 0)
            OR ISNULL(i.art_cod, 0) <> ISNULL(d.art_cod, 0)
      )

    UNION

    -- UPDATE: marca tambien el art_cod ANTERIOR, si cambio cantidad o si cambio art_cod
    SELECT d.art_cod
    FROM inserted i
    INNER JOIN deleted d ON d.sto_id = i.sto_id
    WHERE d.art_cod IS NOT NULL
      AND (
            ISNULL(i.sto_cantidad, 0) <> ISNULL(d.sto_cantidad, 0)
            OR ISNULL(i.art_cod, 0) <> ISNULL(d.art_cod, 0)
      )

    UNION

    -- DELETE: fila eliminada (esta en deleted, no en inserted)
    SELECT d.art_cod
    FROM deleted d
    WHERE d.art_cod IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM inserted i WHERE i.sto_id = d.sto_id);

    -- Los que ya tienen historial: incrementan version_actual
    UPDATE C
    SET C.version_actual = C.version_actual + 1,
        C.fecha_cambio = GETDATE()
    FROM CAMBIOS_STOCK C
    INNER JOIN @ArticulosAfectados A
        ON A.art_cod = C.art_cod;

    -- Los que todavia no existen: se insertan como version 1
    INSERT INTO CAMBIOS_STOCK (art_cod, version_actual, version_enviada, fecha_cambio)
    SELECT A.art_cod, 1, 0, GETDATE()
    FROM @ArticulosAfectados A
    WHERE NOT EXISTS (
        SELECT 1 FROM CAMBIOS_STOCK C WHERE C.art_cod = A.art_cod
    );
END;
GO

-- ---------------------------------------------------------------- ARTICULOS_KIT
IF OBJECT_ID('dbo.TRG_ARTICULOS_KIT_CAMBIOS', 'TR') IS NOT NULL DROP TRIGGER dbo.TRG_ARTICULOS_KIT_CAMBIOS;
GO
CREATE TRIGGER dbo.TRG_ARTICULOS_KIT_CAMBIOS
ON dbo.ARTICULOS_KIT
AFTER INSERT, UPDATE, DELETE
AS
BEGIN
    SET NOCOUNT ON;

    -- 1. Kits afectados por esta sentencia, sin duplicados y sin NULL
    DECLARE @KitsAfectados TABLE (art_codkit INT PRIMARY KEY);

    INSERT INTO @KitsAfectados (art_codkit)
    SELECT ART_CODKIT
    FROM inserted
    WHERE ART_CODKIT IS NOT NULL

    UNION

    SELECT ART_CODKIT
    FROM deleted
    WHERE ART_CODKIT IS NOT NULL;

    -- 2. Los que ya tienen historial: incrementan version_actual
    UPDATE C
    SET C.version_actual = C.version_actual + 1,
        C.fecha_cambio = GETDATE()
    FROM CAMBIOS_ARTICULOS_KIT C
    INNER JOIN @KitsAfectados K
        ON K.art_codkit = C.art_codkit;

    -- 3. Los que todavia no existen: se insertan como version 1
    INSERT INTO CAMBIOS_ARTICULOS_KIT (art_codkit, version_actual, version_enviada, fecha_cambio)
    SELECT K.art_codkit, 1, 0, GETDATE()
    FROM @KitsAfectados K
    WHERE NOT EXISTS (
        SELECT 1 FROM CAMBIOS_ARTICULOS_KIT C WHERE C.art_codkit = K.art_codkit
    );
END;
GO

SET NOEXEC OFF;
GO
PRINT 'Paso 3 terminado: 3 triggers creados.';
