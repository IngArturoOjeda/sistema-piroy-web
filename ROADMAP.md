# ROADMAP.md

# Plan de implementación

Trabajar una etapa por vez.

## Fase 0 — Entender y separar arquitectura
Estado: COMPLETADA (2026-10-12): ningún router del backend consulta SQL Server

Ya confirmado:
- el proyecto actual nació usando SQL Server desde FastAPI;
- existe conexión PostgreSQL preparada con `psycopg`;
- Render es la plataforma cloud prevista;
- la arquitectura objetivo separa backend web y SQL Server local;
- todos los routers (`categories.py`, `items.py`, `sync.py`, `admin.py`, `banners.py`) usan
  PostgreSQL. El viejo `promos.py`, que era el último sobre SQL Server, se retiró junto con
  `database.py`: las promociones ahora salen de la tabla `promocion` (Fase 19).

### Fase 0.1 — Revisar routers actuales
Estado: REVISADO (actualizado tras la migración de `items.py`)

Confirmado:
- `categories.py` ya fue migrado a PostgreSQL;
- `items.py` ya fue migrado a PostgreSQL (catálogo, presentaciones, combos
  y confirmar-pedido — ver `ARCHITECTURE.md`, "Backend actual vs
  arquitectura objetivo");
- `promos.py` (SQL Server) se **retiró** con `database.py` y `frontend/promos-Exclusivos.html`; el botón
  "Ver Promos" y la ruta `/promos` ya no existen. Las promociones son la tabla `promocion`, la sección
  "Promoción vigente" de la portada y la página `/promociones` (Fase 19);
- backend desplegado en Render con `render.yaml` + `requirements-render.txt`
  (servicio `agrovetzo-web`, plan free, `https://agrovetzo-web.onrender.com`;
  ver Fase 15);
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
Estado: COMPLETADA

Actualmente:

```text
backend/app/database_postgres.py
-> PostgreSQL
-> usado por todos los routers

sincronizador/database.py
-> SQL Server
-> usado solo por el sincronizador
```

Objetivo:

```text
backend/app
-> PostgreSQL

sincronizador/
-> SQL Server
```

Avance:
- todos los routers usan `database_postgres.py`;
- `backend/app/database.py` y `promos.py` se eliminaron; el backend publicado ya no necesita `pyodbc`
  (`requirements-render.txt`). `backend/requirements.txt` lo conserva solo para el entorno local del
  sincronizador.

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

Ya realizado (`backend/app/routers/admin.py`, protegido con usuario y contraseña; ver
`ARCHITECTURE.md`, "Acceso al panel"):
- login del administrador: usuarios con contraseña hasheada, sesión por cookie HttpOnly de 8 horas,
  bloqueo tras 5 intentos fallidos, pantalla `admin-login.html`, botón "Cerrar sesión" y script
  `scripts/crear_usuario_admin.py`; reemplaza la clave única `ADMIN_API_KEY`;
- pool de conexiones a PostgreSQL y mejoras de velocidad al elegir una categoría (aviso "Cargando" inmediato,
  formas de compra precargadas en segundo plano); ver `ARCHITECTURE.md`, "Pool de conexiones";
- tipo efectivo de los kits: un kit por presentación pertenece al tipo del artículo del que descuenta stock (no al tipo
  `KIT` del sistema local), aparece en esa categoría y su unidad es una forma de compra más; el tipo `KIT` ya no es una
  categoría de la tienda (ver `ARCHITECTURE.md`, "Tipo efectivo de un artículo");
- estado de cada tipo de artículo (`admin-tipos.html`, `tipo_articulo.mostrar_web`): ocultar un tipo oculta el
  tipo y todos sus artículos en la tienda; el menú de categorías solo muestra tipos visibles con artículos;
- panel con direcciones cortas (`/admin`, `/admin/imagenes`, `/admin/banners`, `/admin/tipos`, `/admin/usuarios`) y **app instalable**
  (manifiesto, service worker sin caché, íconos y botón "Instalar app"; Chrome confirma que es instalable); ver `ARCHITECTURE.md`,
  "Direcciones del panel y app instalable";
- gestión de usuarios desde el panel (`admin-usuarios.html`): roles administrador / común, crear,
  activar y desactivar, dar o quitar el rol, restablecer contraseñas, cambiar la propia
  contraseña y "ojito" para ver lo que se escribe;
- listar/buscar artículos, con filtro por tipo y "Ver más" (panel de imágenes);
- togglear `mostrar_web` por artículo (`PATCH /api/admin/articulos/{art_cod}/mostrar-web`);
- subir imagen de un artículo a Cloudinary (`POST /api/admin/articulos/{art_cod}/imagen`);
- backend de banners del carrusel (`/api/admin/banners` y `GET /api/banners/`,
  tabla `banners` ya creada en PostgreSQL; ver `ARCHITECTURE.md`, "Banners del carrusel");
- panel de banners (`frontend/admin-banners.html`): subir, editar texto, reordenar
  con ▲ ▼ (`PUT /api/admin/banners/orden`), activar y borrar (falta probarlo en un
  navegador real);
- página propia de cada producto (`/producto/{id}-{nombre}`, `GET /api/articulos/{art_cod}`)
  con descripción, agregar al carrito y consulta por WhatsApp (ver `ARCHITECTURE.md`,
  "Página de detalle de un producto");
- descripción comercial de cada artículo editable desde el panel de productos
  (`PATCH /api/admin/articulos/{art_cod}/descripcion`, máx. 2000 caracteres);
- carrusel de la tienda alimentado por `GET /api/banners/` (imagen completa, oculto
  si no hay banners activos); se eliminaron `banner1-3.jpg`;
- `/docs`, `/redoc` y `/openapi.json` apagados por defecto (`HABILITAR_DOCS=1` en local).

Pendiente:
- banners: subir el diseño real de AGRO-VETZO (1920 × 660 px) y comprobar en un
  celular que el texto de la imagen se lee; si no, sumar una imagen alterna para
  celular;
- accesibilidad pendiente del carrusel: aún faltan flechas anterior/siguiente;
- cargar las descripciones de los artículos (la columna, el campo del panel y la página
  del producto ya están; falta el trabajo de escribir las descripciones, de a una desde el
  panel; no hay carga masiva);
- página del producto: el número de WhatsApp definitivo (`WHATSAPP_NUMERO` en `main.js`)
  ya está cargado; falta la vista previa al compartir el enlace en
  WhatsApp (etiquetas `og:` generadas en el servidor, porque los rastreadores no
  ejecutan JavaScript); y probarla en un navegador real y en celular;
- destacados;
- administración de promociones desde el panel web (hoy las promociones solo se cargarán desde
  el sistema local con el sincronizador, Fase 19 etapa 5; ver "Promociones" en `ARCHITECTURE.md`).

## Fase 14 — Servicio Windows
Estado: HECHA (2026-10-20), como tarea programada de Windows

El sincronizador corre solo en el servidor del negocio: tarea «AGRO-VETZO Sincronizador» (Programador de tareas, cuenta
`SYSTEM`, cada 5 minutos, sin instancias superpuestas) que ejecuta `C:\agrovetzo-sync\ejecutar_sincronizador.bat` y guarda
el resultado en `sincronizador.log`. Verificado: una venta real llega a la web sola en menos de 5 minutos. No hace falta un
servicio de Windows propio. Pasos de instalación: `docs/GUIA_INSTALACION_SERVIDOR_NEGOCIO.md`.

### Migración al servidor del negocio (en curso desde 2026-10-14)
El SQL Server que se usó hasta ahora era una copia de pruebas; la base real es `Piroy` (SQL Server 2012, instancia
`DESKTOP-8TG4CTH`, sin `llevar_web`, `TIPO_KIT`, tablas `CAMBIOS_*` ni triggers). Los scripts, para correr en SSMS con
respaldo previo, están en `scripts/sqlserver/`:
- `00_diagnostico_solo_lectura.sql` y `99_verificacion_solo_lectura.sql` (no modifican nada);
- `01_estructura.sql` (columnas y tablas), `02_datos_llevar_web_y_tipo_kit.sql` (`llevar_web` copiado de la web; todos los kits como PRESENTACION),
  `03_triggers.sql` (ahora vigila también `art_kit`, `TIPO_KIT` y las unidades) y `04_carga_inicial.sql`
  (deja todo pendiente para la primera sincronización) y `05_usuario_sincronizador.sql` (usuario SQL de permisos mínimos).
Pasos de instalación en el servidor: `docs/GUIA_INSTALACION_SERVIDOR_NEGOCIO.md`.
Nuevo en el código: el sincronizador envía `TIPOARTICULO` y `UNIDADMEDIDA` a `POST /api/sync/catalogos` antes de los
artículos. Las tablas de la web se conservan (no se vacían): el sincronizador las corrige. Hecho el 2026-10-16: scripts ejecutados en `Piroy`, sincronizador instalado en el servidor del negocio
(`C:\agrovetzo-sync`), primera sincronización real completa (1625 artículos, 61 kits y el stock de los artículos de la web;
los artículos sin nombre y fuera de la web se omiten) y cambios de stock de ventas reales verificados en la web. Tarea
programada (cada 5 minutos) y cambio de precio verificados el 2026-10-20.

## Fase 15 — Producción en Render
Estado: EN PROGRESO

Ya realizado:
- PostgreSQL creado en Render;
- tablas base creadas en esquema `public`;
- conexión externa probada con `psql`;
- `DATABASE_URL` utilizada localmente para validar categorías contra Render;
- FastAPI desplegado en Render (2026-10-09) mediante Blueprint (`render.yaml`),
  servicio web `agrovetzo-web` en plan free, con despliegue automático en cada
  push a `main`; verificado en vivo: `/`, `/api/categorias/`, `/api/articulos/` y
  `/api/banners/` responden 200, `/api/promos/` y `/promos` daban 404 (desactivados; luego retirados),
  las rutas de administración y sincronización dan 401 sin clave, y la tienda
  muestra los banners cargados desde el panel;
- variables de entorno de producción cargadas en el panel de Render (`DATABASE_URL`,
  `SYNC_API_KEY`, `CLOUDINARY_*`; nunca en el repo);
- HTTPS (lo provee Render);
- autenticación del sincronizador (`X-API-Key`, 401 sin clave verificado);
- `/docs`, `/redoc` y `/openapi.json` apagados en producción.

Pendiente:
- confirmar que FastAPI y PostgreSQL estén en la misma región de Render;
- (hecho el 2026-10-16) el sincronizador del servidor del negocio apunta a la URL de producción y la sincronización real
  se probó contra el servicio desplegado;
- logs y monitoreo;
- backups y plan de pago/persistente para producción: en el plan free el servicio
  se duerme tras un tiempo sin visitas y la primera carga tarda;
- el servicio quedó fuera del proyecto "AgroVetzo" de Render (aparece en "Ungrouped
  Services"); es solo organización, opcional.

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
- Pendiente de seguridad (misma técnica de escape que las tarjetas): el modal del carrito y la lista de categorías
  todavía arman parte de su HTML con `innerHTML` y datos del servidor.
- Pendiente: reescribir `test_carrito_fraccionable` y `test_carrito_full` con datos controlados (hecho en el scratchpad, sin versionar).

## Fase 19 — Promociones y novedades en la portada
Estado: EN PROGRESO (plan aprobado el 2026-10-11; el usuario pidió **no sincronizar todavía**)

Diseño completo en `ARCHITECTURE.md`, sección "Promociones". Referencia: portada de tiempodemascotas.com.py.
Flujo: portada con sección "Promoción vigente" (carrusel con flechas) → botón "Ver promoción" → `/promociones`
(todos los artículos en promoción) → cada tarjeta lleva a `/producto/{id}-{nombre}`.

1. Etapa 1 — HECHA y desplegada: tabla `promocion` (creada en producción, vacía) y precios en las lecturas
   (`SQL_PROMO_LATERAL`, `precio` efectivo, `precio_original`, `descuento_porcentaje`, `GET /api/articulos/promociones`).
2. Etapa 2 — HECHA: `confirmar_pedido` cobra el precio promocional vigente (se guarda en `pedido_detalle.precio_unitario`) y
   responde 409 con los precios vigentes si el carrito trae otro; la web actualiza el carrito y pide confirmar de nuevo.
3. Etapa 3 — HECHA (código y pruebas; falta verla en un navegador real): precio tachado + insignia "-X %" en tarjetas y
   página del producto, carrusel "Promoción vigente" con flechas en la portada, página `/promociones`, rutas `/promociones` y
   `/combos` servidas al recargar (`/combos` ya no da 404), retiro de `promos.py`, `database.py`, `promos-Exclusivos.html`, el
   botón "Ver Promos" y la API vieja `/api/promos/`, y escape del nombre/imagen en las tarjetas. Ajustes posteriores
   (2026-10-12/13, tras ver la promo de prueba en el celular): (a) la página se desbordaba a los costados en el celular
   —el texto "Precio anterior/promocional" para lectores de pantalla (`.solo-lectores`, `position:absolute`) de las tarjetas
   del carrusel quedaba fuera de pantalla y ensanchaba toda la página (507 px en un teléfono de 375)—; se corrigió con
   `position: relative` en `.card-producto`, y el botón Combos (solo en su fila) se centra a 60 % de ancho para que su
   latido no se corte en los bordes; medido en un Chrome real a 320/360/375/414 px; (b) "Todos" ya no repite los
   artículos en promoción (`sin_promocion=true`); el buscador los sigue encontrando. Falta ver la sección con una
   promoción real: la tabla está vacía y no hay forma de cargarla hasta la etapa 5 (hoy solo insertando a mano en PostgreSQL).
4. Etapa 4 — Novedades con caducidad manual (`articulos.novedad_hasta`), sección "Novedades" en carrusel.
5. Etapa 5 — DIFERIDA: `POST /api/sync/promociones` y lectura de `PROMOCION` en el sincronizador. Requiere que el usuario
   confirme la estructura de `PROMOCION` y si la tabla de artículos guarda la fecha de inserción (para sumar una regla
   automática de Novedades).

## Fase 20 — Portada con secciones, página de catálogo, cabecera fija y pie de página
Estado: COMPLETADA el 2026-10-13 (etapas 1 a 3). Referencia: portada de tiempodemascotas.com.py.

Hoy `/` muestra todo el catálogo con scroll infinito y un menú lateral. Objetivo: portada con una sección por categoría
(≈8 artículos + VER TODOS), página `/catalogo` ("Explorá nuestro catálogo") con el catálogo completo, cabecera fija
(Carrito y Combos siempre visibles, el banner pasa por debajo), barra de categorías fija bajo la cabecera y pie de página
(Cómo llegar, Atención al cliente, Nuestras redes, Nuestra tienda).

1. Etapa 1 — Backend: `GET /api/articulos/portada`, parámetro `buscar` en `GET /api/articulos/` (la búsqueda pasa a ser
   del servidor) y ruta `GET /catalogo`. HECHA (con pruebas y SQL validado en lectura contra la base real).
2. Etapa 2 — Cabecera fija y compacta (una fila en celular) y pie de página. HECHA (probada en Chrome real a 320, 360, 375,
   414, 768 y 1280 px: cabecera fija tras bajar, Carrito y Combos visibles, sin desborde, pie con sus 4 bloques). Datos del pie:
   horario lunes a sábado 07:00 a 19:00, correo `agroranchopiroy@gmail.com`, TikTok `@enzo.duarte326`, ubicación como «Agro-Vetzo»
   en Google Maps. Pendiente: reemplazar la búsqueda de Maps por el enlace "Compartir" del local y agregar más redes si las hay.
3. Etapa 3 — Portada, página de catálogo, barra de categorías (reemplaza el menú lateral) y búsqueda del servidor.
   HECHA (probada en Chrome real a 320-1280 px: portada con una sección por categoría, VER TODOS, `/catalogo` con
   `?categoria=` y `?buscar=`, Atrás/Adelante, recarga directa, búsqueda sobre todo el catálogo, pie con categorías).
   Ajuste posterior (2026-10-13): con muchos tipos de artículos las categorías van en un desplegable
   "Categorías ▾" (en vez de una fila de botones), la portada muestra como máximo las 10 secciones con más artículos
   (`max_categorias`) y el pie lista 8 + "Ver todas"; probado con 42 categorías simuladas de 320 a 1280 px.
   Si el negocio quiere elegir el orden de las secciones, haría falta una columna nueva en `tipo_articulo`.
   Quedan fuera: "Novedades", "Compra por animal", formulario de contacto, medios de pago, página "Nosotros".

## Versión 2

Sincronizar estados comerciales:

```text
SQL Server/VFP
  -> Sincronizador
  -> PostgreSQL
  -> Cliente consulta estado
```
