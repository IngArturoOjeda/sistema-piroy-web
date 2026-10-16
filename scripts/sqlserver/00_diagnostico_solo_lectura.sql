/*
  AGRO-VETZO - Diagnostico del SQL Server del negocio (SOLO LECTURA)

  Este script NO modifica nada: no crea, no borra, no actualiza. Solo hace SELECT sobre las vistas del catalogo.
  Sirve para saber que piezas del sincronizador ya existen en esta base y cuales faltan, ANTES de migrar.

  Como usarlo (SSMS, en el servidor del negocio):
    1. Conectarse a la instancia (DESKTOP-8TG4CTH) y elegir en la barra la base del sistema (la que usa el punto de venta).
    2. Menu Consulta > Resultados en texto (Ctrl+T), para poder copiar todo junto.
    3. Ejecutar (F5) y pegar el resultado completo en la conversacion.
*/
SET NOCOUNT ON;

PRINT '=== 1. SERVIDOR Y BASE';
SELECT @@SERVERNAME AS servidor,
       DB_NAME() AS base_actual,
       CONVERT(varchar(50), SERVERPROPERTY('ProductVersion')) AS version,
       CONVERT(varchar(50), SERVERPROPERTY('Edition')) AS edicion,
       CONVERT(varchar(100), SERVERPROPERTY('Collation')) AS collation_servidor,
       CONVERT(varchar(100), DATABASEPROPERTYEX(DB_NAME(), 'Collation')) AS collation_base,
       SUSER_SNAME() AS usuario_actual,
       IS_SRVROLEMEMBER('sysadmin') AS es_sysadmin;

PRINT '=== 2. BASES DE LA INSTANCIA';
SELECT name AS base, state_desc AS estado, recovery_model_desc AS modelo_recuperacion FROM sys.databases ORDER BY name;

PRINT '=== 3. TABLAS QUE USA EL SINCRONIZADOR (1 = existe, 0 = falta)';
SELECT n.nombre,
       CASE WHEN OBJECT_ID('dbo.' + n.nombre, 'U') IS NULL THEN 0 ELSE 1 END AS existe
FROM (VALUES ('ARTICULOS'), ('STOCK'), ('ARTICULOS_KIT'),
             ('CAMBIOS_ARTICULOS'), ('CAMBIOS_STOCK'), ('CAMBIOS_ARTICULOS_KIT')) AS n(nombre);

PRINT '=== 4. COLUMNAS DE ARTICULOS, STOCK Y ARTICULOS_KIT';
SELECT OBJECT_NAME(c.object_id) AS tabla, c.column_id AS n, c.name AS columna, ty.name AS tipo,
       c.max_length, c.precision, c.scale, c.is_nullable AS acepta_null, c.is_identity AS es_identity,
       ISNULL(dc.definition, '') AS valor_por_defecto
FROM sys.columns c
JOIN sys.types ty ON ty.user_type_id = c.user_type_id
LEFT JOIN sys.default_constraints dc ON dc.object_id = c.default_object_id
WHERE c.object_id IN (OBJECT_ID('dbo.ARTICULOS'), OBJECT_ID('dbo.STOCK'), OBJECT_ID('dbo.ARTICULOS_KIT'))
ORDER BY tabla, c.column_id;

PRINT '=== 5. COLUMNAS QUE EL SINCRONIZADOR NECESITA EN ARTICULOS (1 = existe, 0 = falta)';
SELECT n.nombre,
       CASE WHEN COL_LENGTH('dbo.ARTICULOS', n.nombre) IS NULL THEN 0 ELSE 1 END AS existe
FROM (VALUES ('art_cod'), ('art_nombre'), ('art_preciobase'), ('tipoart_cod'), ('art_foto'), ('art_estado'),
             ('llevar_web'), ('art_kit'), ('TIPO_KIT'), ('UNI_COD_COM'), ('UNI_COD_VEN')) AS n(nombre);

PRINT '=== 6. TRIGGERS EXISTENTES EN ARTICULOS, STOCK Y ARTICULOS_KIT';
SELECT OBJECT_NAME(tr.parent_id) AS tabla, tr.name AS trigger_nombre,
       tr.is_disabled AS deshabilitado, tr.is_instead_of_trigger AS instead_of,
       tr.create_date AS creado, tr.modify_date AS modificado
FROM sys.triggers tr
WHERE tr.parent_class = 1
  AND tr.parent_id IN (OBJECT_ID('dbo.ARTICULOS'), OBJECT_ID('dbo.STOCK'), OBJECT_ID('dbo.ARTICULOS_KIT'))
ORDER BY tabla, tr.name;

PRINT '=== 7. CLAVES Y CLAVES UNICAS DE LAS TABLAS';
SELECT OBJECT_NAME(i.object_id) AS tabla, i.name AS indice, i.type_desc, i.is_primary_key AS es_pk, i.is_unique AS es_unico,
       STUFF((SELECT ', ' + col.name FROM sys.index_columns ic
              JOIN sys.columns col ON col.object_id = ic.object_id AND col.column_id = ic.column_id
              WHERE ic.object_id = i.object_id AND ic.index_id = i.index_id ORDER BY ic.key_ordinal
              FOR XML PATH('')), 1, 2, '') AS columnas
FROM sys.indexes i
WHERE i.object_id IN (OBJECT_ID('dbo.ARTICULOS'), OBJECT_ID('dbo.STOCK'), OBJECT_ID('dbo.ARTICULOS_KIT'),
                      OBJECT_ID('dbo.CAMBIOS_ARTICULOS'), OBJECT_ID('dbo.CAMBIOS_STOCK'), OBJECT_ID('dbo.CAMBIOS_ARTICULOS_KIT'))
  AND i.name IS NOT NULL
ORDER BY tabla, i.name;

PRINT '=== 8. CANTIDADES (solo numeros)';
SELECT 'ARTICULOS' AS tabla, COUNT(*) AS filas FROM dbo.ARTICULOS
UNION ALL SELECT 'STOCK', COUNT(*) FROM dbo.STOCK
UNION ALL SELECT 'ARTICULOS_KIT', COUNT(*) FROM dbo.ARTICULOS_KIT;

IF COL_LENGTH('dbo.ARTICULOS', 'llevar_web') IS NOT NULL
    EXEC('SELECT llevar_web, COUNT(*) AS articulos FROM dbo.ARTICULOS GROUP BY llevar_web ORDER BY llevar_web');
ELSE
    PRINT 'ARTICULOS todavia no tiene la columna llevar_web';

IF COL_LENGTH('dbo.ARTICULOS', 'art_kit') IS NOT NULL
    EXEC('SELECT art_kit, COUNT(*) AS articulos FROM dbo.ARTICULOS GROUP BY art_kit ORDER BY art_kit');

PRINT '=== 9. STOCK: DEPOSITOS Y FILAS POR ARTICULO';
IF COL_LENGTH('dbo.STOCK', 'dep_cod') IS NOT NULL
    EXEC('SELECT dep_cod, COUNT(*) AS filas FROM dbo.STOCK GROUP BY dep_cod ORDER BY dep_cod');
IF COL_LENGTH('dbo.STOCK', 'art_cod') IS NOT NULL
    EXEC('SELECT COUNT(*) AS articulos_con_mas_de_una_fila_de_stock FROM (SELECT art_cod FROM dbo.STOCK GROUP BY art_cod HAVING COUNT(*) > 1) x');

PRINT '=== 10. TABLAS DE TIPOS Y UNIDADES (para cargar las categorias y unidades de la web)';
SELECT t.name AS tabla, c.column_id AS n, c.name AS columna, ty.name AS tipo, c.max_length
FROM sys.tables t
JOIN sys.columns c ON c.object_id = t.object_id
JOIN sys.types ty ON ty.user_type_id = c.user_type_id
WHERE t.name LIKE '%TIPO%' OR t.name LIKE '%UNI%'
ORDER BY t.name, c.column_id;

PRINT '=== 11. MUESTRA PARA COMPARAR CON LA WEB (20 articulos al azar)';
SELECT TOP 20 art_cod, LTRIM(RTRIM(art_nombre)) AS nombre, tipoart_cod, UNI_COD_COM, UNI_COD_VEN
FROM dbo.ARTICULOS ORDER BY NEWID();

PRINT '=== FIN (no se modifico nada)';
