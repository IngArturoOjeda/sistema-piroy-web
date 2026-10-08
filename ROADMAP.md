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

## Fase 16 — Modelo PRESENTACION / COMBO (`tipo_kit`)
Estado: PARCIALMENTE COMPLETADA (pendientes: pasos 1, 3, 6 y la verificación visual del paso 10)

Decisión de modelo ya documentada en `ARCHITECTURE.md` ("Modelo de artículos compuestos: PRESENTACION vs COMBO"). La limpieza de datos maestros en SQL Server la realiza el usuario manualmente.

Orden recomendado:
1. limpieza de unidades/datos maestros en SQL Server — PENDIENTE (responsabilidad del usuario);
2. agregar `tipo_kit` en SQL Server — COMPLETADO (`ARTICULOS.TIPO_KIT`);
3. clasificar los kits actuales como `PRESENTACION` o `COMBO` — PENDIENTE de confirmar sobre los kits reales existentes (`21038`, `251186`);
4. agregar `tipo_kit` en PostgreSQL — COMPLETADO (`articulos.tipo_kit` con `CHECK`);
5. adaptar la sincronización (`CAMBIOS_ARTICULOS`, payload, schema Pydantic, `POST /api/sync/articulos`) — COMPLETADO;
6. resincronizar y verificar los datos — PENDIENTE;
7. adaptar los endpoints de catálogo (`/api/articulos/presentaciones`, `GET /api/articulos?presentacion=`) para distinguir `PRESENTACION` de `COMBO` — COMPLETADO (`GET /api/articulos` excluye `COMBO` en todos sus modos, commit `0306ffe`; `GET /api/articulos/combos` devuelve solo `COMBO`);
8. adaptar el selector del frontend — COMPLETADO (selector de presentaciones por categoría);
9. crear la sección independiente de Combos — COMPLETADO (`#vista-combos` con paginación);
10. pruebas end-to-end — PARCIAL: suites automatizadas en `tests/` (ver Fase 18); pruebas visuales de frontend pendientes de confirmación del usuario.

## Fase 17 — Rediseño del frontend (móvil primero)
Estado: PARCIALMENTE COMPLETADA

Decisiones del usuario: la mayoría compra desde el celular; estilo moderno y vivo; paleta derivada del logo AGRO-VETZO. Detalle en `ARCHITECTURE.md`, sección "Frontend: diseño responsivo y marca".

1. Etapa 1: categorías y scroll — COMPLETADO (desplegable en celular, panel fijo en escritorio, subida automática a la sección al elegir categoría; Combos, Promos y búsqueda también suben a su sección);
2. Etapa 2: sistema visual y marca — COMPLETADO (paleta en `:root`, cabecera en filas en celular, marca AGRO-VETZO en título y logo, carrito en dos filas en celular);
3. Etapa 3: tarjetas, selector de presentaciones y modales, con accesibilidad (buscador con etiqueta, tarjetas usables con teclado, foco y `Escape` en modales, `role="dialog"` en el carrito) — PENDIENTE;
4. conteo de artículos por categoría en el panel — PENDIENTE (requiere que `GET /api/categorias` devuelva el conteo);
5. decisión sobre modo oscuro — PENDIENTE (no incluido hasta que el usuario lo confirme);
6. verificación visual en celular y escritorio — PENDIENTE de confirmación del usuario.

## Fase 18 — Pruebas automatizadas
Estado: COMPLETADA en su primera versión (commit `01e0034`)

- `tests/unit/`: mock puro, sin base ni servidor. `psycopg.connect` queda bloqueado por `tests/conftest.py`.
- `tests/integracion_lectura/`: requiere servidor local y PostgreSQL; solo `SELECT` y `GET`, con conexión de solo lectura.
- Pendiente: versionar las suites de frontend (jsdom), que hoy viven en el scratchpad. Requieren un `package.json` con `jsdom`.
- Pendiente: reescribir `test_carrito_fraccionable` y `test_carrito_full` con datos controlados (hecho en el scratchpad, sin versionar).

## Versión 2

Sincronizar estados comerciales:

```text
SQL Server/VFP
  -> Sincronizador
  -> PostgreSQL
  -> Cliente consulta estado
```
