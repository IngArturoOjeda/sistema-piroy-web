/*
  AGRO-VETZO - Pedidos de la web en SQL Server (SQL Server 2012, base Piroy)

  Crea dos tablas NUEVAS (no toca ninguna tabla existente) donde el sincronizador guarda los pedidos que los clientes
  hacen en la web:
    - PEDIDOS_WEB          : una fila por pedido (equivale a CabPresupuesto). Su numero (id_pedido_web) es el mismo
                             numero de pedido que genera la web, asi no hay duplicados ni dos numeraciones.
    - PEDIDOS_WEB_DETALLE  : una fila por articulo (equivale a detalllepresupuesto).
  Un pedido web NO descuenta stock: el stock baja cuando el negocio vende o entrega, como siempre.
  valor_descuento queda en 0 (la web solo guarda el precio que se cobro, que ya incluye la promocion vigente).
  estado es el estado comercial que maneja el asesor; el pedido llega como PENDIENTE.

  Tambien da al usuario agrovetzo_sync permiso de LEER e INSERTAR en estas dos tablas (nada mas: no puede modificar
  ni borrar pedidos; el estado lo cambia el sistema local con su propio usuario).

  Antes de correr: respaldo de Piroy. Se puede repetir sin problema: solo crea lo que falta.
  Esto no envia nada: quien baja los pedidos es el sincronizador.
*/
IF DB_NAME() NOT LIKE N'Piroy%'
BEGIN
    RAISERROR('Este script es para la base Piroy (o una copia de prueba llamada Piroy_algo). Elige Piroy en la barra de SSMS. No se ejecuta nada.', 16, 1);
    SET NOEXEC ON;
END
GO

IF OBJECT_ID('dbo.PEDIDOS_WEB', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.PEDIDOS_WEB (
        id_pedido_web     bigint        NOT NULL,
        cliente_nombre    varchar(150)  NOT NULL,
        cliente_direccion varchar(300)  NULL,
        cliente_telefono  varchar(50)   NULL,
        fecha_pedido      datetime      NOT NULL,
        fecha_recibido    datetime      NOT NULL CONSTRAINT DF_PEDIDOS_WEB_fecha_recibido DEFAULT (GETDATE()),
        estado            varchar(20)   NOT NULL CONSTRAINT DF_PEDIDOS_WEB_estado DEFAULT ('PENDIENTE'),
        CONSTRAINT PK_PEDIDOS_WEB PRIMARY KEY (id_pedido_web),
        CONSTRAINT CK_PEDIDOS_WEB_estado CHECK (estado IN ('PENDIENTE', 'CONFIRMADO', 'PREPARADO', 'ENTREGADO', 'CANCELADO'))
    );
    PRINT 'Tabla PEDIDOS_WEB creada';
END
ELSE PRINT 'Tabla PEDIDOS_WEB ya existia: no se toca';
GO

-- Correccion: una version anterior de este script creo art_cod como int. ARTICULOS.ART_COD es numeric(18,0), asi que
-- se vuelve a crear con el tipo correcto, pero SOLO si la tabla esta vacia (no se borra ningun pedido).
IF OBJECT_ID('dbo.PEDIDOS_WEB_DETALLE', 'U') IS NOT NULL
   AND EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.PEDIDOS_WEB_DETALLE') AND name = 'art_cod'
               AND system_type_id = TYPE_ID('int'))
   AND NOT EXISTS (SELECT 1 FROM dbo.PEDIDOS_WEB_DETALLE)
BEGIN
    DROP TABLE dbo.PEDIDOS_WEB_DETALLE;
    PRINT 'PEDIDOS_WEB_DETALLE estaba vacia con art_cod int: se vuelve a crear con numeric(18,0)';
END
GO

IF OBJECT_ID('dbo.PEDIDOS_WEB_DETALLE', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.PEDIDOS_WEB_DETALLE (
        id_pedido_web   bigint         NOT NULL,
        art_cod         numeric(18, 0) NOT NULL,
        cantidad        decimal(18, 3) NOT NULL,
        precio_unitario decimal(18, 2) NOT NULL,
        valor_descuento decimal(18, 2) NOT NULL CONSTRAINT DF_PEDIDOS_WEB_DETALLE_descuento DEFAULT (0),
        valor_pagar     decimal(18, 2) NOT NULL,
        CONSTRAINT PK_PEDIDOS_WEB_DETALLE PRIMARY KEY (id_pedido_web, art_cod),
        CONSTRAINT FK_PEDIDOS_WEB_DETALLE_cabecera FOREIGN KEY (id_pedido_web) REFERENCES dbo.PEDIDOS_WEB (id_pedido_web),
        CONSTRAINT CK_PEDIDOS_WEB_DETALLE_cantidad CHECK (cantidad > 0)
    );
    PRINT 'Tabla PEDIDOS_WEB_DETALLE creada';
END
ELSE PRINT 'Tabla PEDIDOS_WEB_DETALLE ya existia: no se toca';
GO

IF USER_ID(N'agrovetzo_sync') IS NOT NULL
BEGIN
    GRANT SELECT, INSERT ON dbo.PEDIDOS_WEB         TO [agrovetzo_sync];
    GRANT SELECT, INSERT ON dbo.PEDIDOS_WEB_DETALLE TO [agrovetzo_sync];
    PRINT 'Permisos dados a agrovetzo_sync (leer e insertar)';
END
ELSE PRINT 'AVISO: no existe el usuario agrovetzo_sync (paso 05). Los permisos se dan al correr este script de nuevo.';
GO

SET NOEXEC OFF;
GO
PRINT 'Paso 6 terminado.';
