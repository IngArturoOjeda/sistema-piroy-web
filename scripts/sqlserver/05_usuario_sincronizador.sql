/*
  AGRO-VETZO - Usuario de SQL Server para el sincronizador, con permisos minimos (base Piroy)

  El sincronizador NO debe usar 'sa'. Este usuario solo puede:
    - LEER:        ARTICULOS, STOCK, ARTICULOS_KIT, TIPOARTICULO, UNIDADMEDIDA
    - LEER y ACTUALIZAR: CAMBIOS_ARTICULOS, CAMBIOS_STOCK, CAMBIOS_ARTICULOS_KIT
  No puede borrar ni modificar articulos, stock ni ventas.

  ANTES DE CORRER: reemplazar CAMBIAR_ESTA_CLAVE por una clave larga y propia, que se usa una sola vez aqui y despues
  en el archivo .env del servidor. NO guardes este script con la clave puesta, y no la pegues en ningun chat ni en Git.
  Si el servidor no acepta usuarios de SQL (solo Windows), hay que activar "modo mixto" en las propiedades del servidor.

  Se puede repetir: si el usuario ya existe, solo se vuelven a dar los permisos.
*/
IF DB_NAME() NOT LIKE N'Piroy%'
BEGIN
    RAISERROR('Este script es para la base Piroy. Elige Piroy en la barra de SSMS. No se ejecuta nada.', 16, 1);
    SET NOEXEC ON;
END
GO

DECLARE @clave nvarchar(128) = N'CAMBIAR_ESTA_CLAVE';
IF @clave = N'CAMBIAR_ESTA_CLAVE'
   AND NOT EXISTS (SELECT 1 FROM sys.server_principals WHERE name = N'agrovetzo_sync')
BEGIN
    RAISERROR('Cambia CAMBIAR_ESTA_CLAVE por una clave propia antes de correr. No se ejecuta nada.', 16, 1);
    SET NOEXEC ON;
END
ELSE IF NOT EXISTS (SELECT 1 FROM sys.server_principals WHERE name = N'agrovetzo_sync')
BEGIN
    DECLARE @sql nvarchar(max) =
        N'CREATE LOGIN [agrovetzo_sync] WITH PASSWORD = N''' + REPLACE(@clave, '''', '''''') +
        N''', CHECK_POLICY = ON, CHECK_EXPIRATION = OFF, DEFAULT_DATABASE = [' + DB_NAME() + N']';
    EXEC (@sql);
    PRINT 'Login agrovetzo_sync creado';
END
GO

IF USER_ID(N'agrovetzo_sync') IS NULL
BEGIN
    CREATE USER [agrovetzo_sync] FOR LOGIN [agrovetzo_sync];
    PRINT 'Usuario agrovetzo_sync creado en la base';
END
GO

GRANT SELECT ON dbo.ARTICULOS     TO [agrovetzo_sync];
GRANT SELECT ON dbo.STOCK         TO [agrovetzo_sync];
GRANT SELECT ON dbo.ARTICULOS_KIT TO [agrovetzo_sync];
GRANT SELECT ON dbo.TIPOARTICULO  TO [agrovetzo_sync];
GRANT SELECT ON dbo.UNIDADMEDIDA  TO [agrovetzo_sync];
GRANT SELECT, UPDATE ON dbo.CAMBIOS_ARTICULOS     TO [agrovetzo_sync];
GRANT SELECT, UPDATE ON dbo.CAMBIOS_STOCK         TO [agrovetzo_sync];
GRANT SELECT, UPDATE ON dbo.CAMBIOS_ARTICULOS_KIT TO [agrovetzo_sync];
GO

SET NOEXEC OFF;
GO
PRINT 'Listo: usuario agrovetzo_sync con permisos minimos.';
