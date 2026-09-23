# ROADMAP.md

# Plan de implementación

Trabajar una etapa por vez.

## Fase 0 — Entender y separar arquitectura
Estado: EN PROGRESO

Ya confirmado:
- el proyecto actual nació usando SQL Server desde FastAPI;
- existe conexión PostgreSQL preparada con `psycopg`;
- Render es la plataforma cloud prevista;
- la arquitectura objetivo separa backend web y SQL Server local.

### Fase 0.1 — Revisar routers actuales
Estado: REVISADO

Confirmado:
- `categories.py` ya fue migrado a PostgreSQL;
- `items.py` todavía usa SQL Server;
- `promos.py` todavía usa SQL Server;
- `main.py` sirve frontend y monta routers;
- `models.py` está vacío;
- `frontend/js/api.js` está vacío.

### Fase 0.2 — Revisar schemas
Estado: REVISADO

Confirmado:
- `ItemCarrito`: id, nombre, precio, cantidad;
- `PedidoEntrada`: cliente_nombre, cliente_direccion, cliente_telefono, productos;
- no confiar en nombre/precio recibidos desde el navegador.

### Fase 0.3 — Separar conexiones
Estado: EN PROGRESO

Actualmente:

```text
backend/app/database.py
-> SQL Server

backend/app/database_postgres.py
-> PostgreSQL
```

Objetivo:

```text
backend/app
-> PostgreSQL

sincronizador/
-> SQL Server
```

Avance:
- `categories.py` ya usa `database_postgres.py`;
- `items.py` y `promos.py` siguen usando `database.py`.

Antes de mover/eliminar archivos:
1. migrar routers uno por uno;
2. validar funcionamiento después de cada migración;
3. recién después retirar SQL Server del backend web.

## Fase 1 — Diseñar tablas mínimas en PostgreSQL
Estado: COMPLETADA

PostgreSQL fue creado en Render y ya existen en el esquema `public`:
- `tipo_articulo`;
- `articulos`;
- `stock`;
- `pedido_cabecera`;
- `pedido_detalle`.

Decisiones aplicadas:
- `tipoart_cod` conserva el valor de SQL Server y no es autoincremental en PostgreSQL;
- `art_estado` acepta `S` (vigente) y `N` (inactivo);
- `mostrar_web` pertenece a PostgreSQL;
- precios definidos como `NUMERIC(14,0)`;
- pedidos usan `BIGSERIAL`;
- `estado_sync` admite `PENDIENTE` y `RECIBIDO`;
- `fecha_sincronizacion` incluida en `pedido_cabecera`;
- `pedido_detalle.cantidad` valida valores entre 1 y 100.

## Fase 2 — Migrar categorías a PostgreSQL
Estado: COMPLETADA

Realizado:
- tabla `tipo_articulo` creada en PostgreSQL de Render;
- 42 tipos de artículos cargados manualmente desde SQL Server;
- `backend/app/routers/categories.py` migrado de SQL Server a PostgreSQL;
- se mantiene el mismo contrato JSON del frontend: `[{"id": ..., "nombre": ...}]`;
- endpoint `GET /api/categorias/` probado localmente contra PostgreSQL de Render con resultado correcto;
- cambio commiteado y enviado a `main`.

## Fase 3 — Migrar artículos a PostgreSQL
Estado: PENDIENTE

Siguiente etapa.

Objetivos:
- cargar/sincronizar artículos necesarios en PostgreSQL;
- mantener paginación;
- mantener filtro por categoría;
- usar `mostrar_web`;
- respetar `art_estado`;
- definir estrategia de imagen;
- mantener contrato actual del frontend cuando sea posible.

## Fase 4 — Migrar pedidos a PostgreSQL
Estado: PENDIENTE

- `POST /api/articulos/confirmar-pedido` debe guardar primero en PostgreSQL;
- `estado_sync = PENDIENTE`;
- obtener precio oficial desde PostgreSQL;
- no confiar en precio enviado por JavaScript;
- usar transacción cabecera/detalle.

## Fase 5 — Stock local
Estado: PARCIALMENTE COMPLETADO

Ya realizado y probado en SQL Server:
- tabla `CAMBIOS_STOCK`;
- trigger de stock;
- incremento de `version_actual`;
- un solo registro por artículo;
- consulta de pendientes;
- lógica `version_actual > version_enviada`.

Siguiente:
- crear `sincronizador/sincronizador.py`;
- conectar a SQL Server;
- leer pendientes;
- imprimir resultados;
- todavía no enviar nada a la nube.

## Fase 6 — Endpoint privado de stock
Estado: PENDIENTE

FastAPI debe recibir algo equivalente a:

```json
{
  "art_cod": 105,
  "stock": 17,
  "version": 4
}
```

Actualizar PostgreSQL y responder confirmación.

## Fase 7 — Confirmación local de stock
Estado: PENDIENTE

Solo después de respuesta exitosa:

```sql
UPDATE CAMBIOS_STOCK
SET version_enviada = @version,
    fecha_sincronizacion = GETDATE()
WHERE art_cod = @art_cod
  AND version_enviada < @version;
```

## Fase 8 — Reintentos y errores
Estado: PENDIENTE

Probar:
- Internet caído;
- API caída;
- timeout;
- datos inválidos;
- reintento automático.

## Fase 9 — Sincronización de artículos
Estado: PENDIENTE

Definir:
- `llevar_web`;
- `CAMBIOS_ARTICULOS`;
- alta inicial;
- cambio de precio;
- cambio de tipo;
- activo/inactivo.

## Fase 10 — Tipos de artículos
Estado: PARCIALMENTE COMPLETADA

Ya realizado:
- carga inicial manual de 42 tipos de artículos en PostgreSQL.

Pendiente:
- automatizar la sincronización futura de tipos desde SQL Server hacia PostgreSQL.

## Fase 11 — Pedidos web hacia SQL Server
Estado: PENDIENTE

Implementar:
- consulta de pedidos `PENDIENTE`;
- inserción cabecera + detalle en transacción;
- `id_pedido_web UNIQUE`;
- marcar `RECIBIDO` solo después del éxito.

## Fase 12 — Formulario VFP
Estado: PENDIENTE

Permitir que el asesor:
- vea pedidos web;
- consulte detalles;
- contacte al cliente;
- cambie estado comercial.

## Fase 13 — Administrador web
Estado: PENDIENTE

Gestionar:
- `mostrar_web`;
- imagen;
- descripción comercial;
- destacados;
- promociones.

## Fase 14 — Servicio Windows
Estado: PENDIENTE

Ejecutar sincronizador automáticamente en el servidor local.

## Fase 15 — Producción en Render
Estado: EN PROGRESO

Ya realizado:
- PostgreSQL creado en Render;
- tablas base creadas en esquema `public`;
- conexión externa probada con `psql`;
- `DATABASE_URL` utilizada localmente para validar categorías contra Render.

Pendiente:
- FastAPI en Render;
- variables de entorno de producción;
- mismo regionamiento entre FastAPI y PostgreSQL;
- HTTPS;
- autenticación del sincronizador;
- logs;
- backups/plan persistente para producción.

## Versión 2

Sincronizar estados comerciales:

```text
SQL Server/VFP
  -> Sincronizador
  -> PostgreSQL
  -> Cliente consulta estado
```
