/*
  AGRO-VETZO - Verificacion de la estructura del sincronizador (SOLO LECTURA)
  No modifica nada. Correr en la base Piroy con Resultados en texto (Ctrl+T) y pegar el resultado.
*/
SET NOCOUNT ON;

PRINT '=== 1. PIEZAS QUE DEBEN EXISTIR (1 = existe)';
SELECT n.pieza, n.existe FROM (VALUES
  ('columna ARTICULOS.llevar_web',  CASE WHEN COL_LENGTH('dbo.ARTICULOS','llevar_web') IS NULL THEN 0 ELSE 1 END),
  ('columna ARTICULOS.TIPO_KIT',    CASE WHEN COL_LENGTH('dbo.ARTICULOS','TIPO_KIT') IS NULL THEN 0 ELSE 1 END),
  ('tabla CAMBIOS_ARTICULOS',       CASE WHEN OBJECT_ID('dbo.CAMBIOS_ARTICULOS','U') IS NULL THEN 0 ELSE 1 END),
  ('tabla CAMBIOS_STOCK',           CASE WHEN OBJECT_ID('dbo.CAMBIOS_STOCK','U') IS NULL THEN 0 ELSE 1 END),
  ('tabla CAMBIOS_ARTICULOS_KIT',   CASE WHEN OBJECT_ID('dbo.CAMBIOS_ARTICULOS_KIT','U') IS NULL THEN 0 ELSE 1 END),
  ('trigger TR_ARTICULOS_CAMBIOS_WEB',  CASE WHEN OBJECT_ID('dbo.TR_ARTICULOS_CAMBIOS_WEB','TR') IS NULL THEN 0 ELSE 1 END),
  ('trigger TR_STOCK_CAMBIO',           CASE WHEN OBJECT_ID('dbo.TR_STOCK_CAMBIO','TR') IS NULL THEN 0 ELSE 1 END),
  ('trigger TRG_ARTICULOS_KIT_CAMBIOS', CASE WHEN OBJECT_ID('dbo.TRG_ARTICULOS_KIT_CAMBIOS','TR') IS NULL THEN 0 ELSE 1 END)
) AS n(pieza, existe);

PRINT '=== 2. TRIGGERS (deshabilitado debe ser 0)';
SELECT OBJECT_NAME(parent_id) AS tabla, name AS trigger_nombre, is_disabled AS deshabilitado
FROM sys.triggers WHERE parent_class = 1 ORDER BY 1, 2;

IF COL_LENGTH('dbo.ARTICULOS','llevar_web') IS NOT NULL
BEGIN
    PRINT '=== 3. ARTICULOS POR llevar_web';
    EXEC('SELECT llevar_web, COUNT(*) AS articulos FROM dbo.ARTICULOS GROUP BY llevar_web');
    PRINT '=== 4. KITS POR TIPO_KIT (NULL = falta clasificar)';
    EXEC('SELECT TIPO_KIT, COUNT(*) AS kits FROM dbo.ARTICULOS WHERE ART_KIT = 1 GROUP BY TIPO_KIT');
END

IF OBJECT_ID('dbo.CAMBIOS_ARTICULOS','U') IS NOT NULL
BEGIN
    PRINT '=== 5. PENDIENTES DE ENVIAR (version_actual > version_enviada) Y YA ENVIADOS';
    EXEC('SELECT ''articulos'' AS lista, SUM(CASE WHEN version_actual > version_enviada THEN 1 ELSE 0 END) AS pendientes,
                 SUM(CASE WHEN version_actual <= version_enviada THEN 1 ELSE 0 END) AS al_dia, COUNT(*) AS total FROM CAMBIOS_ARTICULOS
          UNION ALL SELECT ''stock'', SUM(CASE WHEN version_actual > version_enviada THEN 1 ELSE 0 END),
                 SUM(CASE WHEN version_actual <= version_enviada THEN 1 ELSE 0 END), COUNT(*) FROM CAMBIOS_STOCK
          UNION ALL SELECT ''kits'', SUM(CASE WHEN version_actual > version_enviada THEN 1 ELSE 0 END),
                 SUM(CASE WHEN version_actual <= version_enviada THEN 1 ELSE 0 END), COUNT(*) FROM CAMBIOS_ARTICULOS_KIT');
    PRINT '=== 6. ARTICULOS SIN FILA EN CAMBIOS_ARTICULOS (deberia ser 0 despues de la carga inicial)';
    EXEC('SELECT COUNT(*) AS sin_fila FROM dbo.ARTICULOS a WHERE NOT EXISTS (SELECT 1 FROM CAMBIOS_ARTICULOS c WHERE c.art_cod = a.ART_COD)');
END
PRINT '=== FIN (no se modifico nada)';
