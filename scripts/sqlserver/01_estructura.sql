/*
  AGRO-VETZO - Paso 1 de 4: estructura para el sincronizador (SQL Server 2012, base Piroy)

  Que hace (se puede correr mas de una vez: lo que ya existe se salta):
    - agrega a ARTICULOS la columna llevar_web (bit, NOT NULL, por defecto 0: ningun articulo va a la web)
    - agrega a ARTICULOS la columna TIPO_KIT (varchar(20), acepta NULL)
    - crea las tablas CAMBIOS_ARTICULOS, CAMBIOS_STOCK y CAMBIOS_ARTICULOS_KIT (vacias)

  Que NO hace: no toca datos existentes, no crea triggers (eso es el paso 3), no envia nada a la web.
  Los programas de VFP que hacen INSERT sin nombrar columnas no se rompen: llevar_web tiene valor por defecto.

  ANTES: respaldo completo de la base Piroy. Ejecutar en SSMS conectado a la base Piroy.
*/
IF DB_NAME() NOT LIKE N'Piroy%'
BEGIN
    RAISERROR('Este script es para la base Piroy (o una copia de prueba llamada Piroy_algo). Elige Piroy en la barra de SSMS. No se ejecuta nada.', 16, 1);
    SET NOEXEC ON;
END
GO

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

-- 1. Columnas nuevas de ARTICULOS
IF COL_LENGTH('dbo.ARTICULOS', 'llevar_web') IS NULL
BEGIN
    ALTER TABLE dbo.ARTICULOS
        ADD llevar_web bit NOT NULL CONSTRAINT DF_ARTICULOS_llevar_web DEFAULT (0);
    PRINT 'ARTICULOS.llevar_web creada (todos en 0)';
END
ELSE PRINT 'ARTICULOS.llevar_web ya existia';
GO

IF COL_LENGTH('dbo.ARTICULOS', 'TIPO_KIT') IS NULL
BEGIN
    ALTER TABLE dbo.ARTICULOS ADD TIPO_KIT varchar(20) NULL;
    PRINT 'ARTICULOS.TIPO_KIT creada';
END
ELSE PRINT 'ARTICULOS.TIPO_KIT ya existia';
GO

-- 2. Tablas de cambios (una fila por articulo; version_actual > version_enviada = pendiente de enviar)
IF OBJECT_ID('dbo.CAMBIOS_ARTICULOS', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.CAMBIOS_ARTICULOS (
        art_cod              numeric(18, 0) NOT NULL,
        version_actual       int            NOT NULL CONSTRAINT DF_CAMBIOS_ARTICULOS_vact DEFAULT (1),
        version_enviada      int            NOT NULL CONSTRAINT DF_CAMBIOS_ARTICULOS_venv DEFAULT (0),
        fecha_cambio         datetime       NOT NULL CONSTRAINT DF_CAMBIOS_ARTICULOS_fcam DEFAULT (GETDATE()),
        fecha_sincronizacion datetime       NULL,
        CONSTRAINT PK_CAMBIOS_ARTICULOS PRIMARY KEY CLUSTERED (art_cod)
    );
    PRINT 'CAMBIOS_ARTICULOS creada';
END
ELSE PRINT 'CAMBIOS_ARTICULOS ya existia';
GO

IF OBJECT_ID('dbo.CAMBIOS_STOCK', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.CAMBIOS_STOCK (
        art_cod              numeric(18, 0) NOT NULL,
        version_actual       int            NOT NULL CONSTRAINT DF_CAMBIOS_STOCK_vact DEFAULT (1),
        version_enviada      int            NOT NULL CONSTRAINT DF_CAMBIOS_STOCK_venv DEFAULT (0),
        fecha_cambio         datetime       NOT NULL CONSTRAINT DF_CAMBIOS_STOCK_fcam DEFAULT (GETDATE()),
        fecha_sincronizacion datetime       NULL,
        CONSTRAINT PK_CAMBIOS_STOCK PRIMARY KEY CLUSTERED (art_cod)
    );
    PRINT 'CAMBIOS_STOCK creada';
END
ELSE PRINT 'CAMBIOS_STOCK ya existia';
GO

IF OBJECT_ID('dbo.CAMBIOS_ARTICULOS_KIT', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.CAMBIOS_ARTICULOS_KIT (
        art_codkit           numeric(18, 0) NOT NULL,
        version_actual       int            NOT NULL CONSTRAINT DF_CAMBIOS_ARTICULOS_KIT_vact DEFAULT (1),
        version_enviada      int            NOT NULL CONSTRAINT DF_CAMBIOS_ARTICULOS_KIT_venv DEFAULT (0),
        fecha_cambio         datetime       NOT NULL CONSTRAINT DF_CAMBIOS_ARTICULOS_KIT_fcam DEFAULT (GETDATE()),
        fecha_sincronizacion datetime       NULL,
        CONSTRAINT PK_CAMBIOS_ARTICULOS_KIT PRIMARY KEY CLUSTERED (art_codkit)
    );
    PRINT 'CAMBIOS_ARTICULOS_KIT creada';
END
ELSE PRINT 'CAMBIOS_ARTICULOS_KIT ya existia';
GO

SET NOEXEC OFF;
GO
PRINT 'Paso 1 terminado.';
