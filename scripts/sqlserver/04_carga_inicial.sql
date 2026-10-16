/*
  AGRO-VETZO - Paso 4 de 4: carga inicial (SQL Server 2012, base Piroy)

  Marca TODO como pendiente de enviar, para que la primera corrida del sincronizador deje la web igual al negocio:
    - CAMBIOS_ARTICULOS      : todos los articulos
    - CAMBIOS_STOCK          : todos los articulos que no son kit (tengan o no fila en STOCK: sin fila se envia stock 0,
                               asi no queda en la web una cantidad vieja)
    - CAMBIOS_ARTICULOS_KIT  : todos los kits, tengan o no componentes (un kit sin componentes borra los viejos de la web)
  Solo agrega lo que falta (no toca filas existentes), asi que se puede repetir sin problema.

  Correr JUSTO ANTES de la primera sincronizacion, y despues de:
    - los pasos 1, 2 y 3,
    - tener en la web los tipos y unidades del negocio (el servidor rechaza articulos con tipo o unidad inexistente).
  Esto no envia nada por si mismo: solo deja la lista de pendientes. Quien envia es el sincronizador.
*/
IF DB_NAME() NOT LIKE N'Piroy%'
BEGIN
    RAISERROR('Este script es para la base Piroy (o una copia de prueba llamada Piroy_algo). Elige Piroy en la barra de SSMS. No se ejecuta nada.', 16, 1);
    SET NOEXEC ON;
END
GO

IF OBJECT_ID('dbo.CAMBIOS_ARTICULOS', 'U') IS NULL OR OBJECT_ID('dbo.CAMBIOS_STOCK', 'U') IS NULL
   OR OBJECT_ID('dbo.CAMBIOS_ARTICULOS_KIT', 'U') IS NULL
BEGIN
    RAISERROR('Falta correr el paso 1. No se ejecuta nada.', 16, 1);
    SET NOEXEC ON;
END
GO

SET NOCOUNT ON;
SET XACT_ABORT ON;
BEGIN TRANSACTION;

DECLARE @n int;

INSERT INTO CAMBIOS_ARTICULOS (art_cod, version_actual, version_enviada, fecha_cambio)
SELECT a.ART_COD, 1, 0, GETDATE()
FROM ARTICULOS a
WHERE NOT EXISTS (SELECT 1 FROM CAMBIOS_ARTICULOS c WHERE c.art_cod = a.ART_COD);
SET @n = @@ROWCOUNT;
PRINT 'CAMBIOS_ARTICULOS: ' + CAST(@n AS varchar(10)) + ' articulos agregados como pendientes';

INSERT INTO CAMBIOS_STOCK (art_cod, version_actual, version_enviada, fecha_cambio)
SELECT s.ART_COD, 1, 0, GETDATE()
FROM (SELECT ART_COD FROM ARTICULOS WHERE ISNULL(ART_KIT, 0) = 0
      UNION
      SELECT ART_COD FROM STOCK WHERE ART_COD IS NOT NULL) s
WHERE NOT EXISTS (SELECT 1 FROM CAMBIOS_STOCK c WHERE c.art_cod = s.ART_COD);
SET @n = @@ROWCOUNT;
PRINT 'CAMBIOS_STOCK: ' + CAST(@n AS varchar(10)) + ' articulos agregados como pendientes';

INSERT INTO CAMBIOS_ARTICULOS_KIT (art_codkit, version_actual, version_enviada, fecha_cambio)
SELECT k.ART_COD, 1, 0, GETDATE()
FROM (SELECT ART_COD FROM ARTICULOS WHERE ART_KIT = 1
      UNION
      SELECT DISTINCT ak.ART_CODKIT FROM ARTICULOS_KIT ak
      INNER JOIN ARTICULOS a ON a.ART_COD = ak.ART_CODKIT) k
WHERE NOT EXISTS (SELECT 1 FROM CAMBIOS_ARTICULOS_KIT c WHERE c.art_codkit = k.ART_COD);
SET @n = @@ROWCOUNT;
PRINT 'CAMBIOS_ARTICULOS_KIT: ' + CAST(@n AS varchar(10)) + ' kits agregados como pendientes';

COMMIT TRANSACTION;
GO
SET NOEXEC OFF;
GO
PRINT 'Paso 4 terminado.';
