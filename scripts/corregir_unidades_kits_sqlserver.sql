-- Corrige la unidad de compra y de venta de 12 kits PRESENTACION en el SISTEMA LOCAL (SQL Server).
-- Correr en tu SQL Server (la base de la agroveterinaria), NO en la base de la web.
--
-- Por que hace falta: la web recibe estas unidades del sincronizador y las pisa en cada
-- sincronizacion. La web ya esta corregida (2026-10-12); sin esto, la proxima sincronizacion
-- volveria a dejar los valores viejos.
--
--   BOLSA (UNI_COD 5): kits de bolsa de 25 kg que estaban como KG o UNIDAD
--   ROLLO (UNI_COD 6): kits PIOLIN X ROLLO que estaban como CAJA o UNIDAD
--
-- Los codigos 5 = BOLSA y 6 = ROLLO son los de la tabla de unidades copiada a la web. ANTES DE CORRER,
-- verifica en tu sistema que esos codigos sean BOLSA y ROLLO (si no coinciden, ajusta @BOLSA y @ROLLO).
-- Las tablas y columnas usadas (ARTICULOS, ART_COD, TIPO_KIT, UNI_COD_COM, UNI_COD_VEN) son las que
-- ya lee el sincronizador. Todo corre en una transaccion: si no se actualizan exactamente 12
-- articulos, se deshace y no cambia nada.

DECLARE @BOLSA int = 5;
DECLARE @ROLLO int = 6;

-- 1) Vista previa: lo que hay hoy en esos articulos
SELECT ART_COD, ART_NOMBRE, TIPO_KIT, UNI_COD_COM, UNI_COD_VEN
FROM ARTICULOS
WHERE ART_COD IN (251188, 251192, 251198, 251208, 251210, 441247, 441249,
                  631441, 631442, 631443, 631452, 661529)
ORDER BY ART_COD;

BEGIN TRANSACTION;

-- 2) Bolsas de 25 kg
UPDATE ARTICULOS
SET UNI_COD_COM = @BOLSA, UNI_COD_VEN = @BOLSA
WHERE ART_COD IN (
    251188,  -- PRONTO DOG X25KG
    251192,  -- AVES TERMINADOR X25KG
    251198,  -- CERDO TERMINADOR X25KG
    251208,  -- CONEJO X25KG
    251210,  -- SAL MINERAL GUAYAKI X25KG
    441247,  -- PORCINO BERGTHAL ENGORDE DE 25K
    441249   -- PONEDORA AVES BERGTHAL DE 25K
)
AND TIPO_KIT = 'PRESENTACION';
DECLARE @bolsas int = @@ROWCOUNT;

-- 3) Rollos de piolin
UPDATE ARTICULOS
SET UNI_COD_COM = @ROLLO, UNI_COD_VEN = @ROLLO
WHERE ART_COD IN (
    631441,  -- PIOLIN VERDE X ROLLO
    631442,  -- PIOLIN AMARILLO X ROLLO
    631443,  -- PIOLIN AZUL X ROLLO
    631452,  -- PIOLIN NEGRO X ROLLO
    661529   -- PIOLIN ROJO X ROLLO 213 MTS
)
AND TIPO_KIT = 'PRESENTACION';
DECLARE @rollos int = @@ROWCOUNT;

IF @bolsas = 7 AND @rollos = 5
BEGIN
    COMMIT TRANSACTION;
    PRINT 'Listo: 7 kits a BOLSA y 5 kits a ROLLO.';
END
ELSE
BEGIN
    ROLLBACK TRANSACTION;
    PRINT 'NO se cambio nada: se esperaban 7 y 5 articulos y fueron ' + CAST(@bolsas AS varchar(10)) + ' y ' + CAST(@rollos AS varchar(10)) + '.';
END;

-- 4) Resultado
SELECT ART_COD, ART_NOMBRE, TIPO_KIT, UNI_COD_COM, UNI_COD_VEN
FROM ARTICULOS
WHERE ART_COD IN (251188, 251192, 251198, 251208, 251210, 441247, 441249,
                  631441, 631442, 631443, 631452, 661529)
ORDER BY ART_COD;
