# ROADMAP.md

# Plan de implementación

Trabajar una etapa por vez.

## Fase 0 — Entender y separar arquitectura
Estado: EN PROGRESO

Ya confirmado:
- el proyecto actual usa SQL Server desde FastAPI;
- existe conexión PostgreSQL preparada con `psycopg`;
- Render es la plataforma cloud prevista;
- la arquitectura objetivo separa backend web y SQL Server local.

### Fase 0.1 — Revisar routers actuales
Estado: REVISADO

Confirmado:
- `categories.py` usa SQL Server;
- `items.py` usa SQL Server;
- `promos.py` usa SQL Server;
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
Estado: PENDIENTE

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

Antes de mover archivos:
1. buscar todos los imports de `backend.app.database`;
2. migrar routers uno por uno;
3. validar funcionamiento;
4. recién después retirar SQL Server del backend web.

## Fase 1 — Diseñar tablas mínimas en PostgreSQL
Estado: PENDIENTE

Diseñar, revisar y aprobar antes de crear:
- `tipo_articulo`;
- `articulos`;
- `stock`;
- `pedido_cabecera`;
- `pedido_detalle`.

No copiar columnas innecesarias de SQL Server.

## Fase 2 — Migrar categorías a PostgreSQL
Estado: PENDIENTE

- crear datos necesarios en PostgreSQL;
- adaptar `categories.py`;
- mantener mismo contrato JSON para el frontend;
- probar antes de seguir.

## Fase 3 — Migrar artículos a PostgreSQL
Estado: PENDIENTE

- mantener paginación;
- mantener filtro por categoría;
- usar `mostrar_web`;
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
Estado: PENDIENTE

Sincronizar catálogo necesario hacia PostgreSQL.

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
Estado: PENDIENTE

Validar:
- FastAPI en Render;
- variables de entorno;
- PostgreSQL de Render;
- HTTPS;
- autenticación del sincronizador;
- logs;
- backups.

## Versión 2

Sincronizar estados comerciales:

```text
SQL Server/VFP
  -> Sincronizador
  -> PostgreSQL
  -> Cliente consulta estado
```
