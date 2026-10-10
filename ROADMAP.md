# ROADMAP.md

# Plan de implementación

Trabajar una etapa por vez.

## Fase 0 — Entender y separar arquitectura
Estado: CASI COMPLETADA (falta solo `promos.py`)

Ya confirmado:
- el proyecto actual nació usando SQL Server desde FastAPI;
- existe conexión PostgreSQL preparada con `psycopg`;
- Render es la plataforma cloud prevista;
- la arquitectura objetivo separa backend web y SQL Server local;
- `categories.py`, `items.py`, `sync.py` y `admin.py` ya quedaron migrados
  a PostgreSQL. Solo `promos.py` sigue sobre SQL Server.

### Fase 0.1 — Revisar routers actuales
Estado: REVISADO (actualizado tras la migración de `items.py`)

Confirmado:
- `categories.py` ya fue migrado a PostgreSQL;
- `items.py` ya fue migrado a PostgreSQL (catálogo, presentaciones, combos
  y confirmar-pedido — ver `ARCHITECTURE.md`, "Backend actual vs
  arquitectura objetivo");
- `promos.py` todavía usa SQL Server (único router pendiente); mientras
  tanto el botón "Ver Promos" está oculto en `frontend/index.html`
  (`style="display: none;"`), la ruta de página `GET /promos` está comentada
  en `main.py` y el router de promos no se registra (necesario para que el
  backend arranque en Render sin `pyodbc`); reactivar todo al migrar el router;
- `render.yaml` y `requirements-render.txt` creados; falta el primer despliegue
  y verificarlo (crear el Blueprint en Render, cargar las variables secretas);
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
Estado: CASI COMPLETADA (falta solo `promos.py`)

Actualmente:

```text
backend/app/database.py
-> SQL Server
-> usado solo por promos.py

backend/app/database_postgres.py
-> PostgreSQL
-> usado por categories.py, items.py, sync.py y admin.py
```

Objetivo:

```text
backend/app
-> PostgreSQL

sincronizador/
-> SQL Server
```

Avance:
- `categories.py`, `items.py`, `sync.py` y `admin.py` ya usan
  `database_postgres.py`;
- `promos.py` sigue usando `database.py` (único router pendiente).

Antes de mover/eliminar archivos:
1. migrar routers uno por uno — hecho para todos salvo `promos.py`;
2. validar funcionamiento después de cada migración;
3. recién después retirar SQL Server del backend web (pendiente de
   `promos.py`; `backend/app/database.py` no se puede eliminar todavía).

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
Estado: COMPLETADA

Realizado:
- `backend/app/routers/items.py` migrado por completo a PostgreSQL
  (`GET /api/articulos/`, `/presentaciones`, `/combos`);
- paginación y filtro por categoría conservados, y ampliados con filtro
  por unidad y por presentación (`NORMAL`/`KIT`);
- usa `mostrar_web` y respeta `art_estado`;
- estrategia de imagen: Cloudinary para lo nuevo, con fallback a rutas
  locales bajo `frontend/` para lo heredado (`url_imagen_articulo()`);
- se agregaron campos nuevos al contrato del frontend (`stock_disponible`,
  `unidad_venta`, `fraccionable`) — ver `ARCHITECTURE.md`, "Endpoint actual
  de artículos".

## Fase 4 — Migrar pedidos a PostgreSQL
Estado: COMPLETADA

Realizado:
- `POST /api/articulos/confirmar-pedido` guarda en PostgreSQL, dentro de
  una transacción (`pedido_cabecera` con `estado_sync='PENDIENTE'` por
  default, `pedido_detalle`, y snapshot en `pedido_detalle_componentes`);
- el precio oficial se obtiene de PostgreSQL, nunca del valor enviado por
  el navegador;
- además de lo planeado originalmente, valida stock físico agregado
  (incluye expansión de kits) antes de confirmar — ver `ARCHITECTURE.md`,
  "Endpoint actual de pedidos".

## Fase 5 — Stock local
Estado: PARCIALMENTE COMPLETADO

Ya realizado y probado en SQL Server:
- tabla `CAMBIOS_STOCK`;
- trigger de stock;
- incremento de `version_actual`;
- un solo registro por artículo;
- consulta de pendientes;
- lógica `version_actual > version_enviada`.

Realizado (más allá de lo planeado originalmente para esta fase):
- `sincronizador/sincronizador.py` creado, conectado a SQL Server con
  `pyodbc`, lee pendientes y envía a FastAPI por HTTPS — ver Fases 6 a 9,
  completadas junto con esta.

## Fase 6 — Endpoint privado de stock
Estado: COMPLETADA

`POST /api/sync/stock` (`backend/app/routers/sync.py`, protegido con
`X-API-Key`) recibe `{art_cod, cantidad, version_actual}`, valida que el
artículo exista y no sea un kit (un kit no tiene stock físico propio), hace
`UPSERT` en `stock` y responde confirmación.

## Fase 7 — Confirmación local de stock
Estado: COMPLETADA

`sincronizador.py` actualiza `CAMBIOS_STOCK.version_enviada` en SQL Server
solo después de una respuesta exitosa de FastAPI, con la misma defensa de
concurrencia planeada originalmente (`AND version_enviada < @version`). Si
SQL Server no puede registrar la confirmación aunque FastAPI sí la haya
recibido, el sincronizador lo trata como un error aparte (reintenta en la
corrida siguiente en vez de perder el cambio).

## Fase 8 — Reintentos y errores
Estado: COMPLETADA

`sincronizador.py` tolera errores de red/timeout (hasta 3 seguidos), separa
los errores de configuración, de conexión, de confirmación local y de
sincronización en general, y no deja un artículo a medio sincronizar: si
PostgreSQL confirma pero SQL Server no puede registrar `version_enviada`,
ese caso queda identificado para reintentar, no se pierde.

## Fase 9 — Sincronización de artículos
Estado: COMPLETADA

- `llevar_web` viaja desde SQL Server (`ARTICULOS.llevar_web`) hasta
  PostgreSQL (`articulos.llevar_web`);
- tabla `CAMBIOS_ARTICULOS` en SQL Server, con el mismo patrón
  `version_actual > version_enviada` que el stock;
- `POST /api/sync/articulos` hace `UPSERT` (alta y cambios de precio, tipo,
  estado, todo en una sola operación idempotente);
- documentado con incidentes reales de datos en
  `docs/GUIA_PUESTA_EN_PRODUCCION.md`.

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
Estado: PARCIALMENTE COMPLETADA

Ya realizado (`backend/app/routers/admin.py`, protegido con `X-Admin-Key`):
- listar/buscar artículos;
- togglear `mostrar_web` por artículo (`PATCH /api/admin/articulos/{art_cod}/mostrar-web`);
- subir imagen de un artículo a Cloudinary (`POST /api/admin/articulos/{art_cod}/imagen`);
- backend de banners del carrusel (`/api/admin/banners` y `GET /api/banners/`,
  tabla `banners` ya creada en PostgreSQL; ver `ARCHITECTURE.md`, "Banners del carrusel");
- panel de banners (`frontend/admin-banners.html`): subir, editar texto, reordenar
  con ▲ ▼ (`PUT /api/admin/banners/orden`), activar y borrar (falta probarlo en un
  navegador real);
- `/docs`, `/redoc` y `/openapi.json` apagados por defecto (`HABILITAR_DOCS=1` en local).

Pendiente:
- banners, etapa 3: `index.html` lee `GET /api/banners/` (carrusel con imagen
  completa y `aspect-ratio`, oculto si no hay banners) y se borran
  `banner1-3.jpg`; antes, probar el diseño real en celular;
- descripción comercial;
- destacados;
- administración de promociones (hoy `promos.py` sigue sobre SQL Server,
  sin panel propio — ver Fase 0 y la sección "Promociones" de
  `ARCHITECTURE.md`).

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
3. Etapa 3: COMPLETADO para tarjetas de producto (imagen 1:1 con `object-fit:contain` y `loading="lazy"`, nombre a 2 líneas, precio destacado, stock como badge, unidad de venta como badge, botón con `:focus-visible`), aplicado pero **sin confirmación visual del usuario todavía**. PENDIENTE: selector de presentaciones, modales (carrito, "agregado al carrito") y el resto de la accesibilidad (buscador con etiqueta, foco y `Escape` en modales, `role="dialog"` en el carrito);
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
