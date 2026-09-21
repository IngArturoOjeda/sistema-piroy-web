# ARCHITECTURE.md

# Arquitectura del e-commerce de la agroveterinaria

## Objetivo

Integrar el sistema local Visual FoxPro 9 + SQL Server con un e-commerce moderno sin exponer directamente SQL Server a Internet.

## Arquitectura general

```text
Cliente Web
    |
    v
Frontend HTML/CSS/JS
    |
    v
FastAPI en Render
    |
    v
PostgreSQL en Render
    ^
    |
   HTTPS
    |
Sincronizador Python local
    |
    v
SQL Server
    ^
    |
Visual FoxPro
Caja 1 / Caja 2
```

## Render

La plataforma cloud elegida es Render.

Se prevé usar Render para:
- FastAPI/Uvicorn;
- aplicación web;
- PostgreSQL administrado.

SQL Server local NO debe exponerse públicamente.

## Cuando el negocio pierde Internet

### Local
Siguen funcionando:
- ventas;
- facturación;
- Visual FoxPro;
- SQL Server;
- cambios de stock.

### Web
Sigue funcionando:
- navegación;
- datos con el último estado sincronizado;
- recepción de pedidos.

Los pedidos web son solicitudes, no ventas confirmadas.

Cuando vuelve Internet:
1. se actualizan stocks pendientes;
2. se descargan pedidos pendientes;
3. se insertan en SQL Server;
4. se marcan como recibidos en PostgreSQL.

## Flujo de pedidos

### PostgreSQL
Estado técnico de sincronización:

```text
PENDIENTE
RECIBIDO
```

### SQL Server
Estado comercial:

```text
PENDIENTE
CONFIRMADO
PREPARADO
ENTREGADO
CANCELADO
```

Versión 2: enviar esos estados de vuelta a PostgreSQL para seguimiento web.

## Prevención de duplicados

Cada pedido web debe conservar en SQL Server:

```text
id_pedido_web
```

Debe existir una restricción:

```text
UNIQUE(id_pedido_web)
```

Cabecera y detalle deben insertarse dentro de una transacción.

## Stock local

Tabla confirmada:

```text
STOCK
```

Columnas conocidas:

```text
art_cod       NUMERIC(18,0)
dep_cod       INT
sto_cantidad  NUMERIC(9,3)
sto_id        NUMERIC(18,0)
```

Por ahora se trabaja con un solo depósito.

## CAMBIOS_STOCK

Estructura diseñada:

```sql
CREATE TABLE CAMBIOS_STOCK (
    art_cod NUMERIC(18,0) NOT NULL,
    version_actual INT NOT NULL DEFAULT 1,
    version_enviada INT NOT NULL DEFAULT 0,
    fecha_cambio DATETIME NOT NULL DEFAULT GETDATE(),
    fecha_sincronizacion DATETIME NULL,
    CONSTRAINT PK_CAMBIOS_STOCK PRIMARY KEY (art_cod)
);
```

Regla:

```text
version_actual > version_enviada
```

significa pendiente de sincronización.

El sincronizador envía stock actual + versión actual.

## Concurrencia de stock

Si Python lee versión 5 y durante el envío otra venta incrementa a 6, al confirmar la 5 queda:

```text
version_actual = 6
version_enviada = 5
```

Por lo tanto el artículo sigue pendiente.

Actualización defensiva:

```sql
UPDATE CAMBIOS_STOCK
SET version_enviada = @version,
    fecha_sincronizacion = GETDATE()
WHERE art_cod = @art_cod
  AND version_enviada < @version;
```

## Trigger de STOCK

El trigger:
- detecta cambios reales de `sto_cantidad`;
- inserta en `CAMBIOS_STOCK` si no existe;
- incrementa `version_actual` si ya existe;
- no llama APIs;
- no ejecuta Python;
- no accede a Internet.

Ya fue probado manualmente.

## Consulta de pendientes

```sql
SELECT
    C.art_cod,
    C.version_actual,
    C.version_enviada,
    S.sto_cantidad
FROM CAMBIOS_STOCK C
INNER JOIN STOCK S
    ON S.art_cod = C.art_cod
WHERE C.version_actual > C.version_enviada;
```

## Backend actual vs arquitectura objetivo

Actualmente el proyecto nació consultando SQL Server desde FastAPI en localhost.

Estado actual:

```text
frontend
  -> FastAPI
  -> SQL Server
```

Arquitectura objetivo:

```text
frontend
  -> FastAPI
  -> PostgreSQL
```

y por separado:

```text
SQL Server
  -> sincronizador local
  -> FastAPI/PostgreSQL
```

## Conexiones actuales confirmadas

```text
backend/app/database.py
-> pyodbc
-> SQL Server

backend/app/database_postgres.py
-> psycopg
-> PostgreSQL en Render
```

Objetivo final:

```text
backend/app
-> PostgreSQL

sincronizador/
-> SQL Server
```

## Endpoint actual de categorías

Actualmente consulta:

```sql
SELECT tipoart_cod, tipoart_desc
FROM tipoarticulo;
```

Esto confirma que PostgreSQL necesita como mínimo:

```text
tipoart_cod
tipoart_desc
```

## Endpoint actual de artículos

Actualmente `GET /api/articulos/` usa:

```text
ARTICULOS.art_cod
ARTICULOS.art_nombre
ARTICULOS.art_preciobase
ARTICULOS.tipoart_cod
ARTICULOS.art_foto
ARTICULOS.art_estado

TIPOARTICULO.tipoart_cod
TIPOARTICULO.tipoart_desc
```

Devuelve:

```text
id
nombre
precio
tipo
imagen
```

Soporta:
- paginación;
- filtro por categoría.

## Endpoint actual de pedidos

Actualmente `POST /api/articulos/confirmar-pedido`:
1. recibe `PedidoEntrada`;
2. inserta cabecera directamente en SQL Server;
3. obtiene `id_pedido`;
4. inserta detalles;
5. hace COMMIT;
6. hace ROLLBACK si falla.

Arquitectura objetivo:

```text
Cliente
  -> FastAPI en Render
  -> PostgreSQL
  -> pedido PENDIENTE
  -> sincronizador
  -> SQL Server
```

## Schemas actuales

```text
ItemCarrito:
- id
- nombre
- precio
- cantidad

PedidoEntrada:
- cliente_nombre
- cliente_direccion
- cliente_telefono
- productos[]
```

Validaciones actuales:
- `id > 0`;
- `cantidad > 0`;
- `cantidad <= 100`.

Regla de seguridad:
- usar `id/art_cod` y `cantidad`;
- no confiar en `nombre` ni `precio`;
- consultar PostgreSQL para obtener los valores oficiales.

## Artículos para ecommerce

SQL Server debe manejar un indicador:

```text
llevar_web
```

Sugerencia: `BIT`.

- `0`: no se sincroniza.
- `1`: pertenece al ecommerce.

Todo artículo nuevo debería iniciar con `llevar_web = 0`.

## Publicación web

PostgreSQL debe manejar:

```text
mostrar_web
```

Esto es distinto de `llevar_web`.

- `llevar_web`: participa del ecommerce.
- `mostrar_web`: se muestra públicamente ahora.

Esto permite preparar:
- imagen;
- nombre comercial;
- descripción web;
- destacados;
- promociones;
- otros datos exclusivos web.

## Tablas mínimas conceptuales en PostgreSQL

La web necesitará al menos estructuras equivalentes a:

```text
tipo_articulo
articulos
stock
pedido_cabecera
pedido_detalle
```

No se pretende clonar toda la base SQL Server.

## Imágenes

Actualmente `art_foto` parece contener rutas locales de Windows y el endpoint intenta convertirlas a `/frontend/...`.

Eso no es suficiente para producción en Render si la imagen depende del disco local de la veterinaria.

Debe definirse más adelante una estrategia de imágenes accesibles desde la nube.

## Promociones

El router actual de promociones usa:

```text
ARTICULOS
TIPOARTICULO
PROMOCION
```

con campos como:
- `fec_desde`;
- `fec_hasta`;
- `art_valor`.

Debe definirse si las promociones se sincronizan desde SQL Server o si serán administradas desde el futuro administrador web.

## Administrador web

Debe administrar datos propios del ecommerce, por ejemplo:
- mostrar/ocultar artículo;
- imagen;
- descripción comercial;
- destacado;
- promoción;
- contenido web.

No debe reemplazar VFP ni administrar directamente SQL Server.

## Seguridad

No:
- SQL Server público;
- puerto 1433 público;
- credenciales en código;
- llamadas HTTP desde triggers;
- dependencia de Internet para vender localmente.

Sí:
- HTTPS;
- autenticación privada del sincronizador;
- secretos en variables de entorno;
- reintentos;
- logs;
- operaciones idempotentes.
