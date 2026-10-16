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

**Estado: la migración ya se hizo para casi todos los routers.** El proyecto
nació consultando SQL Server desde FastAPI en localhost; hoy la mayoría de
los endpoints públicos ya consultan PostgreSQL.

Estado actual, por router:

```text
categories.py  -> PostgreSQL  (migrado)
items.py       -> PostgreSQL  (catálogo, presentaciones, combos, promociones, detalle de producto, confirmar-pedido)
sync.py        -> PostgreSQL  (siempre fue así: recibe del sincronizador)
admin.py       -> PostgreSQL + Cloudinary (siempre fue así; incluye banners)
banners.py     -> PostgreSQL  (lista pública del carrusel)
```

El viejo `promos.py` (SQL Server) y `database.py` (pyodbc) se **retiraron**: las promociones
ahora salen de la tabla `promocion` de PostgreSQL (ver "Promociones"). Ningún router del backend
consulta SQL Server.

Arquitectura objetivo (**ya alcanzada**):

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
backend/app/database_postgres.py
-> psycopg
-> PostgreSQL en Render
-> usado por todos los routers (categories, items, sync, admin, banners)

sincronizador/database.py
-> pyodbc
-> SQL Server local
-> usado solo por el sincronizador
```

Objetivo final (alcanzado):

```text
backend/app
-> PostgreSQL

sincronizador/
-> SQL Server
```

### Sincronización de tipos y unidades, y servidor del negocio

`POST /api/sync/catalogos` (`sync.py`, con `X-API-Key`) recibe la lista completa de `TIPOARTICULO` y `UNIDADMEDIDA` de SQL
Server y hace upsert en `tipo_articulo` y `unidad_medida`: crea lo que falta y actualiza el nombre, sin tocar
`tipo_articulo.mostrar_web` ni `unidad_medida.fraccionable` (decisiones del panel) y sin borrar. El sincronizador lo llama
antes de los artículos (cada artículo exige que su tipo y unidad existan). Variable: `SYNC_API_URL_CATALOGOS`.

La base real del negocio es `Piroy` (SQL Server 2012). Sus tablas `CAMBIOS_*`, triggers y las columnas `llevar_web` y
`TIPO_KIT` se crean con los scripts numerados de `scripts/sqlserver/` (ver `ROADMAP.md`, Fase 14). El trigger de
`ARTICULOS` vigila nombre, precio, tipo, foto, estado, `llevar_web`, `art_kit`, `TIPO_KIT` y las unidades.

### Pool de conexiones a PostgreSQL

`obtener_conexion_postgres()` (`database_postgres.py`) ya no abre una conexión nueva en cada pedido
(TCP + TLS + autenticación: cerca de 0,5 s con la base en otro servidor): presta una de un pool
(`psycopg_pool.ConnectionPool`, mínimo 1 y máximo 10 conexiones, espera máxima de 20 s por una libre,
cada conexión se renueva a los 30 minutos y se prueba con `check_connection` antes de entregarla, así una
conexión cortada por la base se descarta en vez de fallar el pedido). Los routers siguen usando
`conn = obtener_conexion_postgres()` ... `conn.close()`: `close()` devuelve la conexión al pool (deshaciendo
antes cualquier transacción abierta, como la que deja una lectura). Las dependencias son
`psycopg[binary,pool]` en `backend/requirements.txt` y `requirements-render.txt`. Los scripts de `scripts/`
y el sincronizador no usan el pool: abren su propia conexión.

## Endpoint actual de categorías

`GET /api/categorias/` consulta PostgreSQL y devuelve el menú de la tienda: solo los tipos que
el administrador no ocultó (`tipo_articulo.mostrar_web = TRUE`) **y** que tienen algo para mostrar
(`SQL_TIPO_CON_ARTICULOS`, en `backend/app/sql_catalogo.py`: artículos publicados cuyo **tipo efectivo**
es ese tipo, incluidos los kits por presentación; los COMBO no cuentan porque tienen su propia vista). Es
lo mismo que decide `/api/articulos/presentaciones`, así que un tipo del menú nunca abre una página vacía. Ordenados por `tipoart_cod`. Devuelve una lista de
`{"id": tipoart_cod, "nombre": tipoart_desc}`; si no hay ningún tipo visible responde una lista vacía
(antes devolvía los 42 tipos, casi todos vacíos).

## Endpoint actual de artículos

`GET /api/articulos/` consulta PostgreSQL (`articulos`, `tipo_articulo`,
`stock`, `unidad_medida`, más la subconsulta de stock de kits). Parámetros:
`pagina`, `limite`, `categoria` (o `"Todos"`), `unidad` (opcional: filtra por unidad de venta),
`presentacion` (`NORMAL` | `KIT`; se conserva por compatibilidad y **ya no filtra**), `buscar` (texto opcional, hasta 100 caracteres: filtra por nombre con `ILIKE`, con `%` y `_` escapados, y si es un
número de hasta 18 dígitos también por código exacto; se combina con `categoria` y `unidad`) y `sin_promocion`
(booleano, por defecto `false`: con `true` excluye los artículos con promoción
vigente; la web **ya no lo usa**: el catálogo completo de `/catalogo` muestra todos los artículos, con su precio
rebajado si tienen promoción, y la sección "Promoción vigente" vive solo en la portada). Siempre excluye `tipo_kit='COMBO'`, en todos los modos (ver
"Modelo de artículos compuestos" más abajo). Devuelve, por artículo:

```text
id
nombre
precio                (precio EFECTIVO: el promocional si hay promo vigente, si no el de lista)
precio_original       (precio de lista, solo con promo vigente; si no, null)
descuento_porcentaje  (entero, solo con promo vigente y descuento >= 1 %; si no, null)
tipo                  (nombre de la categoría: el tipo EFECTIVO, ver "Tipo efectivo de un artículo")
imagen
stock_disponible
unidad_venta
fraccionable
```

`GET /api/articulos/portada?por_categoria=8&max_categorias=10` (`por_categoria` de 1 a 24, `max_categorias` de 1 a 50)
devuelve la muestra de la portada en una sola consulta: `[{"categoria": "BALANCEADOS", "articulos": [...]}]`, con los
primeros N artículos (primero los que tienen foto) de las `max_categorias` categorías **con más artículos publicados**
(de más a menos; desempata el código del tipo), con las mismas reglas de publicación y de tipo efectivo que el menú y el
catálogo (`ROW_NUMBER` por tipo y `DENSE_RANK` por cantidad; no incluye COMBO). El tope hace que la portada y su peso no
crezcan con la cantidad de tipos (con 40 categorías serían ~100 KB sin tope).

`GET /api/articulos/presentaciones?categoria=`, `GET /api/articulos/combos`,
`GET /api/articulos/promociones` y `GET /api/articulos/{art_cod}` comparten el
mismo formato de respuesta (el detalle agrega `descripcion`); los dos primeros
están descriptos en la sección "Modelo de artículos compuestos: PRESENTACION vs
COMBO" y los dos últimos en "Promociones" y "Página de detalle de un producto".

## Vistas y rutas de la tienda

La tienda es una sola página (`index.html`) con cinco vistas, cada una con su URL: `/` (portada), `/catalogo`
(catálogo completo), `/promociones`, `/combos` y `/producto/{id}-{nombre}`. `main.py` sirve `index.html` en todas ellas, y
`main.js` decide qué vista mostrar a partir de `location.pathname` y `location.search` (`resolverRuta`,
`mostrarRutaActual`, `mostrarVista`; `irA` para la navegación interna y `popstate` para Atrás/Adelante). Por eso cada
dirección funciona al recargar y al compartirla, y el carrito (que vive en memoria) no se pierde al navegar. Los enlaces
"← Volver a la tienda" hacen "Atrás" si se entró desde la tienda y llevan a la portada si se llegó directo. Una ruta
desconocida muestra la portada; `/combos` sin combos publicados también vuelve a la portada.

**Portada (`/`):** banner, "Promoción vigente" y **una sección por categoría, hasta 10** (las que tienen más artículos;
`MAX_SECCIONES_EN_PORTADA`), de hasta 8 artículos cada una, con un botón
**VER TODOS** hacia `/catalogo?categoria=NOMBRE`), más un botón **VER TODO EL CATÁLOGO**. Las secciones salen de una sola
llamada a `GET /api/articulos/portada` (`cargarPortada`, `dibujarPortada`; se pide una vez y, si falla, muestra un mensaje con
"Reintentar"); cada sección reutiliza `dibujarArticulos(lista, contenedor)`. En escritorio las secciones son una grilla de
4 columnas; en tablet y celular, una fila que se desliza con el dedo. La portada **no** pide el catálogo completo.

**Catálogo (`/catalogo`):** título "EXPLORÁ NUESTRO CATÁLOGO" y la grilla con scroll infinito de siempre (30 por lote,
selector de formas de compra por categoría, aviso "Cargando", precarga de presentaciones). La URL manda:
`/catalogo?categoria=NOMBRE` (un nombre inexistente u oculto cae en el catálogo completo y corrige la URL) y
`/catalogo?buscar=TEXTO`. Si la URL pide la lista que ya está cargada (por ejemplo, Atrás desde un producto) no se vuelve a
pedir; volver a elegir lo que ya se está mirando sí la recarga (útil para regresar al selector de formas de compra).

**Barra de categorías y desplegable:** parte de la cabecera fija (ver más abajo). Lleva siempre tres elementos, sin
importar cuántos tipos haya: `Inicio`, `Todos` y un botón **`Categorías ▾`** que abre un panel con **todas** las
categorías (`GET /api/categorias/`, `cargarCategorias`; si no hay categorías el botón se oculta). El panel tiene
columnas en escritorio (`columns: 4 200px`) y es una lista que se desplaza en celular (`max-height` según la pantalla);
con 42 categorías simuladas entra en pantalla en 320, 375, 768 y 1280 px y la cabecera no cambia de alto. Dentro de una
categoría, el botón muestra su nombre (por ejemplo `BALANCEADOS ▾`, como en la tienda de referencia; si el nombre es
largo se recorta con «…»). Se cierra con Esc (devolviendo el foco al botón), tocando afuera, al salir el foco o al elegir
una categoría; el botón usa `aria-expanded` y `aria-controls`, y la categoría actual lleva `aria-current` en el panel.
Las entradas son enlaces reales (`a[href]`) que navegan sin recargar. Reemplaza al menú lateral y a la fila de botones
(que con decenas de tipos obligaba a desplazarse mucho y escondía las últimas). El contenedor de la barra no tiene
`overflow` propio: un contenedor con desplazamiento recortaría el panel. Todo enlace con `data-ruta-interna` (logo, barra,
panel, VER TODOS, pie) lo atiende un único escuchador que llama a `irA`.

**Búsqueda (del servidor):** escribir en el buscador de la cabecera (espera de 350 ms; Enter inmediato) lleva a
`/catalogo?buscar=TEXTO` (entrada nueva del historial al entrar desde otra página; reemplaza la entrada mientras se escribe
dentro del catálogo) y el catálogo pide `GET /api/articulos/?buscar=...`, que busca sobre **todos** los artículos
publicados, no solo los ya cargados. Ignora categoría y formas de compra, pagina con el mismo scroll infinito y el título
dice `Resultados para «texto»`. Con el texto vacío vuelve al catálogo completo; en la portada el buscador se vacía.

## Página de detalle de un producto

Cada artículo tiene página propia: `/producto/{art_cod}` o `/producto/{art_cod}-{nombre}` (el nombre es solo decorativo; manda el código). Es una **vista de `index.html`**, no un archivo aparte, porque el carrito vive en memoria (`let carrito = []` en `main.js`) y se perdería al cambiar de página. `main.py` sirve `index.html` en esa ruta (`GET /producto/{ref}`) y `main.js` lee la URL: funciona al recargar, con Atrás/Adelante y con el enlace compartido. Las tarjetas del catálogo y de combos llevan enlaces reales (`href`), así que también sirven Ctrl+clic y "abrir en pestaña nueva".

`GET /api/articulos/{art_cod}` (público) devuelve el mismo formato del catálogo (`id`, `nombre`, `precio`, `tipo`, `imagen`, `stock_disponible`, `unidad_venta`, `fraccionable`) más `descripcion` (`null` si está vacía), con el mismo cálculo de stock, incluidos los kits. Acepta artículos normales y kits (PRESENTACION y COMBO) publicados (`art_estado = 'S'`, `llevar_web` y `mostrar_web`); si no existe o no está publicado, 404. Se declara después de `/presentaciones` y `/combos` para no taparlas.

La página muestra imagen, categoría, nombre, precio, stock, unidad de venta y descripción (si la tiene), con dos acciones: **Agregar al carrito** (reutiliza `comprarArticulo()`, con sus reglas de stock y cantidad) y **Consultar por WhatsApp**, un enlace `https://wa.me/{número}?text=...` con el mensaje "Hola AGRO-VETZO, estoy interesado en este artículo: {nombre} - Gs. {precio}" y el enlace al producto. El número está en la constante `WHATSAPP_NUMERO` de `main.js` y es el número definitivo de la tienda. Todo dato del servidor se pinta con `textContent`. En esta vista el carrusel de banners se oculta (`body.en-producto`).

Columna `articulos.descripcion` (`text`, máximo 2000 caracteres, nullable): dato propio del e-commerce, **no viene de SQL Server**; el upsert del sincronizador actualiza una lista fija de columnas que no la incluye, así que no la pisa. Se creó con `scripts/agregar_columna_descripcion.sql` (+ `.py`). Se carga desde el panel de imágenes de productos (`frontend/admin-imagenes.html`): cuadro de texto con contador de caracteres y botón "Guardar descripción", que llama a `PATCH /api/admin/articulos/{art_cod}/descripcion` (cuerpo `{"descripcion": "..."}`, protegido con la sesión del administrador). El texto se recorta; si queda vacío se guarda como `NULL` ("sin descripción"); más de 2000 caracteres da 422 (y la base lo rechaza con un `CHECK`). La búsqueda del panel (`GET /api/admin/articulos`) devuelve la descripción actual.

## Endpoint actual de pedidos

`POST /api/articulos/confirmar-pedido` ya corre sobre PostgreSQL, dentro de
una única transacción (rollback si cualquier fase falla):

1. valida que el pedido no esté vacío y no tenga artículos repetidos;
2. trae metadatos de los artículos pedidos (precio oficial, si es kit,
   fraccionable, unidad de venta) — nunca confía en lo que mandó el
   navegador. El **precio oficial es el promocional vigente** si lo hay
   (mismo `SQL_PROMO_LATERAL` que usa el catálogo) o el de lista;
3. valida reglas de cantidad: enteros para no-fraccionables, y enteros
   también para KG/LITROS/METROS por política web (ver "Política de
   cantidades" más abajo);
3b. **compara el precio que el cliente vio en su carrito con el oficial**
   (tolerancia de medio guaraní). Si alguno difiere —una promoción empezó o
   terminó mientras compraba— responde **409** y no escribe nada:
   `{"detail": {"codigo": "PRECIOS_CAMBIARON", "mensaje": "...", "precios":
   [{"id", "precio", "precio_original", "descuento_porcentaje"}]}}`, con solo
   los artículos cuyo precio cambió. La web actualiza esos precios en el
   carrito, avisa y pide volver a confirmar. El precio del navegador se usa
   **solo para esta comparación, nunca para cobrar**. Se evalúa antes del
   chequeo de stock; un artículo no disponible sigue dando 400 antes;
4. para los kits del pedido, trae su composición (`articulos_kit`) y la
   expande a consumo físico de sus componentes;
5. valida el stock físico **agregado**: si un artículo directo y un kit
   comparten el mismo componente, se suman antes de comparar contra el
   stock real; detecta también kits anidados (no soportado) y kits sin
   componentes configurados (inconsistencia interna, 500);
6. recién con todo validado, inserta `pedido_cabecera`, `pedido_detalle`
   (con `precio_unitario` = el precio oficial vigente en ese momento, es
   decir, el realmente cobrado) y un snapshot por componente en
   `pedido_detalle_componentes`, y hace commit.

Ya no inserta nada en SQL Server directamente. El flujo hacia SQL Server
(sincronizador descargando pedidos desde PostgreSQL) sigue pendiente —
Fase 11 del `ROADMAP.md`:

```text
Cliente
  -> FastAPI en Render
  -> PostgreSQL (pedido_cabecera con estado_sync='PENDIENTE')
  -> sincronizador  [PENDIENTE: todavía no descarga pedidos]
  -> SQL Server
```

## Política de cantidades: unidades web enteras

Regla comercial de la web (no cambia la base de datos ni el sistema local):
**KG, LITROS y METROS se venden en cantidades enteras en la web**, aunque el
artículo sea fraccionable en el sistema local. El tope por artículo es
`floor(stock_disponible)`. La lista de unidades afectadas es una constante
compartida (`UNIDADES_WEB_ENTERAS` en `backend/app/routers/items.py` y en
`frontend/js/main.js`).

Cualquier otro artículo fraccionable (por ejemplo, con unidad `M3`) admite
decimales normalmente: hasta 3 decimales, mínimo 0.001 (`ItemCarrito.cantidad`,
ver "Schemas actuales"). En el frontend, ese tipo de artículo se agrega al
carrito con cantidad pendiente (`null`) hasta que el cliente la define
explícitamente; "Confirmar pedido" queda bloqueado mientras haya algún
pendiente sin definir.

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

### Estado de cada tipo de artículo (`tipo_articulo.mostrar_web`)

La tabla `tipo_articulo` tiene también `mostrar_web boolean NOT NULL DEFAULT TRUE` (script
`scripts/agregar_columna_mostrar_web_tipo.py`, `--probar` valida y deshace). Es un dato propio del
e-commerce, no viene de SQL Server: **si el sincronizador llegara a cargar tipos, su upsert no debe
pisar esta columna**. El administrador la cambia desde `frontend/admin-tipos.html`
(`GET /api/admin/tipos`, con la cantidad de artículos publicados y si el tipo aparece en el menú, y
`PATCH /api/admin/tipos/{tipoart_cod}` con `{"mostrar_web": bool}`).
La pantalla filtra con una lista desplegable de tipos ("Todos los tipos" + cada tipo), sin escribir el nombre.

Un tipo oculto lo oculta todo: ni el tipo ni sus artículos aparecen en el menú, el listado, las
promociones, los combos, la página del producto ni las formas de compra (`AND t.mostrar_web = TRUE` en
cada consulta pública, sobre el tipo efectivo: los kits por presentación se ocultan con el tipo de su
componente, no con `KIT`), y `confirmar_pedido` rechaza sus artículos como no disponibles. Los `COMBO` no se
ocultan con un tipo (`SQL_TIPO_VISIBLE`). Ocultar el tipo `KIT` no afecta a ningún kit por presentación.
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

Implementado en el backend y en la web (etapas 1 a 3 del plan; ver `ROADMAP.md`, Fase 19). Hasta que se cargue la tabla `promocion`, la tienda se ve igual que antes: la sección "Promoción vigente" no aparece si no hay promociones.

**Origen de los datos.** La tabla `PROMOCION` del sistema local (SQL Server) tiene, según el viejo `promos.py`, las columnas `art_cod`, `art_valor` (precio promocional), `fec_desde` y `fec_hasta`; su estructura completa (clave, duplicados por artículo) **está por confirmar**. Se cargará en PostgreSQL con el sincronizador (etapa posterior; todavía no existe `POST /api/sync/promociones`).

**Tabla `promocion` (PostgreSQL)**, definida en `scripts/crear_tabla_promocion.sql` (+ `.py`): `id`, `art_cod` (FK a `articulos`, `ON DELETE CASCADE`), `art_valor` (`numeric(14,0)` > 0), `fec_desde`, `fec_hasta` (`fec_hasta >= fec_desde`) e índice por `(art_cod, fec_desde, fec_hasta)`. Cada fila es el **precio promocional** de un artículo entre dos fechas.

**Reglas de vigencia** (`SQL_PROMO_LATERAL` en `items.py`, usado por el catálogo, los combos, el detalle y el listado de promociones):
- vigente si `fec_desde <= hoy <= fec_hasta` (ambas fechas inclusivas), con "hoy" en hora de Paraguay (`America/Asuncion`). Render corre en UTC: la fecha del servidor puede ir un día adelante de la de Paraguay, y se comprobó que ocurre;
- solo cuenta si el precio promocional es **menor** al precio de lista (si no rebaja, se ignora);
- con varias promos vigentes para el mismo artículo se aplica el **precio más bajo**;
- el porcentaje se calcula a partir del nuevo precio, `(lista − promo) / lista`, redondeado a entero (mitad hacia arriba); si da menos de 1 % no se muestra insignia (el precio rebajado sí se aplica).

**Endpoints**: `GET /api/articulos/promociones?pagina&limite` (limite máx. 100) devuelve los artículos publicados (normales, PRESENTACION y COMBO) con promo vigente, de mayor a menor descuento (el código desempata). Declarado antes de `/{art_cod}`.

**Cobro del precio promocional** (hecho): `confirmar_pedido` cobra el precio promocional vigente y lo guarda en `pedido_detalle.precio_unitario`; si el carrito trae un precio distinto responde 409 (ver "Endpoint actual de pedidos"). Cuando se arme la bajada de pedidos al sistema local, cada renglón ya lleva el precio realmente cobrado.

**En la web** (`index.html`, `main.js`, `styles.css`):
- tarjetas y página del producto: precio original tachado (`<s>`, con texto "Precio anterior" para lectores de pantalla), precio promocional e insignia "-X %" sobre la imagen; el mensaje de WhatsApp usa el precio promocional; el carrito se arma con el precio vigente;
- sección **Promoción vigente** en la portada: carrusel de las primeras 12 (`GET /api/articulos/promociones?limite=12`) con flechas anterior/siguiente (desplazamiento nativo y táctil, flechas deshabilitadas en los extremos, sin animación con "menos movimiento") y el enlace **Ver promoción**. Es parte de la portada (solo se ve en ella) y solo si hay promociones; si no hay o la API falla, queda oculta y la tienda funciona igual;
- **El catálogo completo no excluye las promociones**: `/catalogo` ("Todos") y las categorías muestran todos los artículos, también los que están en promoción, con su precio rebajado. (Antes, con el catálogo en la portada, "Todos" excluía las promociones con `sin_promocion=true` porque ya salían en su sección; el parámetro del servidor se conserva pero la web ya no lo usa.) La búsqueda, al ser del servidor, encuentra las promociones como cualquier artículo;
- página **`/promociones`**: todos los artículos con promoción vigente, de a 30 con "Ver más"; cada tarjeta lleva a `/producto/{id}-{nombre}`. Al volver desde un producto conserva la lista y la posición.

**Sincronización de `PROMOCION`** (etapa posterior, "sincronizar aún no"): `POST /api/sync/promociones` reemplazando la tabla en una transacción, y lectura de `PROMOCION` en el sincronizador. Requiere antes que el usuario confirme la estructura real de `PROMOCION`. Hoy no hay forma de cargar promociones en producción salvo insertarlas a mano en PostgreSQL.

## Administrador web

Debe administrar datos propios del ecommerce, por ejemplo:
- mostrar/ocultar artículo;
- imagen;
- descripción comercial;
- destacado;
- promoción;
- contenido web.

No debe reemplazar VFP ni administrar directamente SQL Server.

### Panel de imágenes: lista de artículos con filtro por tipo

`frontend/admin-imagenes.html` + `js/admin-imagenes.js` listan los artículos (publicados o no) y permiten elegir
uno para ver/cambiar su imagen, su descripción y si se muestra en la web. La lista usa
`GET /api/admin/articulos` con parámetros opcionales: `tipo` (código del tipo), `buscar` (texto o código, dentro
de lo elegido), `pagina` (desde 1) y `limite` (1 a 100, por defecto 30). Sin `tipo` ni `buscar` lista **todos**,
ordenados por código. La respuesta es una lista de artículos; la pantalla pide de a 30 y muestra "Ver más"
mientras la última página venga completa.

- El filtro "Tipo de artículo" ofrece "Todos" más los tipos que tienen artículos, con su cantidad total y cuántos
  están publicados: `ALAMBRE (6 · 1 publicados)` (`articulos_total` y `articulos_total_publicados` de
  `GET /api/admin/tipos`). "Publicado" significa vigente (`art_estado = 'S'`), con `llevar_web` y con `mostrar_web`
  activado: es lo mismo que marca el cartel "Publicado" de cada artículo de la lista. La pantalla de tipos
  (`admin-tipos.html`) muestra la misma cifra como "publicados de total" (`1 de 6`).
- El tipo es el **tipo efectivo** (ver "Tipo efectivo de un artículo"): los kits por presentación se listan en el
  tipo de su componente, igual que en la tienda, y el detalle muestra esa misma categoría.
- Cambiar el tipo o el texto vuelve a la primera página; una respuesta que llega tarde (se cambió el filtro
  mientras viajaba) se descarta. Los datos del servidor se escriben en la lista con `textContent`.

### Acceso al panel (usuario y contraseña)

Todas las rutas `/api/admin/...` exigen una sesión iniciada (dependencia `verificar_admin`, en `backend/app/routers/admin_auth.py`). La antigua clave única `X-Admin-Key` / `ADMIN_API_KEY` **ya no se usa**: la variable puede borrarse del panel de Render.

Tablas (definición en `scripts/crear_tablas_admin.sql`, creadas con `scripts/crear_tablas_admin.py`; `--probar` valida y deshace):
- `admin_usuarios`: `usuario` (único, minúsculas, 3 a 50), `password_hash`, `activo`, `es_admin` (rol; columna agregada con `ALTER TABLE` en el mismo script), `intentos_fallidos`, `bloqueado_hasta`, `creado_en`, `ultimo_acceso`.
- `admin_sesiones`: `usuario_id` (se borra con el usuario), `token_hash` (único), `creada_en`, `vence_en`.

Endpoints:
- `POST /api/admin/login` (`{"usuario","password"}`): si es correcto crea una sesión y responde con la cookie `agrovetzo_admin` (`HttpOnly`, `Secure`, `SameSite=Strict`, `Path=/api/admin`, 8 horas). Usuario inexistente, dado de baja o contraseña mala dan el mismo 401 "Usuario o contraseña incorrectos" y tardan lo mismo.
- `POST /api/admin/logout`: borra la sesión en el servidor y la cookie.
- `GET /api/admin/sesion`: devuelve `{usuario, es_admin}` de la sesión vigente (401 si no hay).

Gestión de usuarios (`backend/app/routers/admin_usuarios.py`; las cinco primeras exigen el rol de administrador, 403 si no lo tiene):
- `GET /api/admin/usuarios` (lista, sin hashes), `POST /api/admin/usuarios` (`usuario`, `password`, `es_admin`; 409 si ya existe), `PATCH /api/admin/usuarios/{id}` (`activo` y/o `es_admin`), `POST /api/admin/usuarios/{id}/password` (restablece la contraseña de otro usuario).
- `POST /api/admin/mi-password` (`actual`, `nueva`): lo puede usar cualquier usuario con sesión; una contraseña actual equivocada cuenta como intento fallido.
- Reglas: nadie puede desactivarse ni quitarse el rol a sí mismo; siempre debe quedar al menos un administrador activo (los cambios de activo/rol se serializan con un candado de transacción `pg_advisory_xact_lock` y se bloquean las filas, para decidirlo sin carreras ni abrazos mortales); desactivar o restablecer la contraseña de un usuario cierra todas sus sesiones; al cambiar la propia contraseña se cierran las demás sesiones propias y se conserva la actual.

Reglas (`backend/app/seguridad_admin.py`):
- la contraseña se guarda solo como hash `scrypt` con sal propia (biblioteca estándar, sin dependencias nuevas); mínimo 10 caracteres;
- del token de sesión solo se guarda su SHA-256: quien lea la base no puede usar las sesiones;
- 5 contraseñas malas seguidas bloquean al usuario 15 minutos (429, aunque después acierte); un acceso correcto reinicia el contador; el reloj es el de la base;
- una sesión vence a las 8 horas, deja de valer si el usuario se da de baja y las vencidas se limpian en cada ingreso.

Usuarios: no hay registro público. El primer administrador se crea con `scripts/crear_usuario_admin.py USUARIO --admin` (pide la contraseña por teclado sin mostrarla; sobre un usuario existente cambia su contraseña, cierra sus sesiones y levanta el bloqueo; `--desactivar` da de baja). Los demás se gestionan desde `frontend/admin-usuarios.html`. Dos roles: **administrador** (gestiona usuarios) y **común** (usa el panel de imágenes y banners y puede cambiar su propia contraseña).

Interfaz (direcciones en "Direcciones del panel y app instalable"): `frontend/admin-login.html` + `js/admin-login.js`; `frontend/admin-usuarios.html` + `js/admin-usuarios.js` (cambiar mi contraseña para todos; crear, activar/desactivar, rol y nueva contraseña solo para administradores); `js/admin-sesion.js` (compartido por todas las pantallas) manda al login si no hay sesión o si vence (401), muestra el usuario y el botón "Cerrar sesión"; `js/admin-ojo.js` es el botón "ojito" que muestra u oculta la contraseña mientras se escribe. Los paneles no guardan contraseña ni token en el navegador (la cookie no es legible desde JavaScript).

Límite conocido: el bloqueo es por usuario, no por dirección IP.

### Direcciones del panel y app instalable

El panel se abre en **`/admin`** (en producción, `https://www.agrovetzo.com.py/admin`). Cada pantalla tiene una dirección
corta bajo `/admin/`, servida por `main.py` con las mismas páginas de `frontend/`:

| Dirección | Página |
|---|---|
| `/admin` y `/admin/` | ingreso (`admin-login.html`); con sesión iniciada lleva directo a `/admin/imagenes` |
| `/admin/imagenes` | `admin-imagenes.html` |
| `/admin/banners` | `admin-banners.html` |
| `/admin/tipos` | `admin-tipos.html` |
| `/admin/usuarios` | `admin-usuarios.html` |
| `/admin/manifest.webmanifest` | manifiesto de la app (`application/manifest+json`) |
| `/admin/sw.js` | service worker (`text/javascript`, `Service-Worker-Allowed: /admin/`, sin caché del navegador) |

Las direcciones viejas `/frontend/admin-*.html` siguen existiendo, pero ya nadie enlaza a ellas. La API del panel no cambia
(`/api/admin/...`). `/admin` y `/admin/` responden las dos porque el alcance de la app es `/admin/`: si `/admin/` redirigiera
a `/admin`, saldría del alcance.

**App instalable (PWA):** el panel se puede instalar como aplicación (en Edge aparece "Abrir en aplicación"; en Chrome, el
icono de instalar). Piezas:
- `frontend/admin-app/manifest.webmanifest`: `start_url` y `scope` en `/admin/` (todas las pantallas del panel están dentro, y
  los enlaces entre ellas también: lo que sale del alcance se abre en el navegador), `display: standalone`, colores de la marca
  e íconos `frontend/assets/images/admin/icono-192.png` y `icono-512.png` (el 512 también como `maskable`; el contenido queda
  en la zona segura). Los íconos se generaron con el emblema del logo y el texto "AGRO-VETZO ADMIN".
- `frontend/admin-app/sw.js`: service worker mínimo. **No guarda nada en caché** (los datos del panel van siempre a la red y no
  queda nada del administrador en el dispositivo); solo atiende las navegaciones y, si no hay internet, muestra una página
  "Sin conexión" con "Reintentar".
- `frontend/js/admin-pwa.js` (incluido en las cinco pantallas): registra el service worker y muestra el botón **"Instalar app"**
  del menú cuando el navegador ofrece instalar (`beforeinstallprompt`); se oculta al instalarse o al usar la app.
- Las cinco páginas llevan `<link rel="manifest">`, `theme-color` y `apple-touch-icon`; "Ver la tienda" (en el menú) se abre
  en otra pestaña.

**Nombre y menú:** la app se llama **AGRO-VETZO** (`name` y `short_name` del manifiesto, títulos de las páginas y
`apple-mobile-web-app-title`). Las cuatro pantallas de trabajo (imágenes, banners, tipos, usuarios) comparten el mismo menú
en celular, app y PC: cabecera con botón ☰, logo y título de la pantalla; el menú es un cajón lateral (`#menu-admin`, máx. 320 px)
con grupos desplegables (Catálogo: imágenes y tipos; Portada: banners; Administración: usuarios), "Ver la tienda" y, abajo,
usuario, "Instalar app" y "Cerrar sesión". Marca la pantalla actual con `aria-current="page"` y abre su grupo; se cierra con ✕,
tocando afuera o con Esc. El contenido del menú está repetido en el HTML de cada pantalla (hay que editar las cuatro al agregar
una opción); `frontend/js/admin-menu.js` solo lo abre y cierra. El ingreso (`admin-login.html`) no lleva menú.
En `admin-imagenes.css` la grilla de la pantalla de imágenes usa `minmax(0, 1fr)` y los textos largos se parten
(`overflow-wrap: anywhere`): un nombre sin espacios no debe estirar la página en el celular.

La sesión es una cookie por dominio: al cambiar de dirección (por ejemplo de `onrender.com` a `www.agrovetzo.com.py`) hay que
iniciar sesión de nuevo.

### Despliegue en Render

`render.yaml` (Blueprint) declara solo el servicio web `agrovetzo-web` (plan free, Python 3.13.5, `uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT`, build con `requirements-render.txt`). La base PostgreSQL ya existente no se declara, para no crear otra. Las variables `DATABASE_URL`, `SYNC_API_KEY` y `CLOUDINARY_*` están como `sync: false`: se cargan a mano en el panel de Render y nunca van al repo.

`requirements-render.txt` es igual a `backend/requirements.txt` sin `pyodbc`: el backend publicado no consulta SQL Server. Por eso `main.py` no registra el router de promos (importa `database.py`, que exige `pyodbc` y las variables `DB_*`). Estado: **desplegado y verificado** (2026-10-09) en `https://agrovetzo-web.onrender.com`; Render aceptó Python 3.13.5 y el servicio arranca con solo estas variables de entorno. Cada push a `main` despliega automáticamente (`autoDeployTrigger: commit`). Detalle de lo verificado y lo pendiente en `ROADMAP.md`, Fase 15.

### Banners del carrusel

Los banners son imágenes completas (con el texto ya incluido en la imagen), pensadas en 1920 × 660 px, que se suben desde el administrador y se guardan en Cloudinary (carpeta `agrovetzo/banners`). Solo viven en PostgreSQL; no existen en SQL Server.

Tabla `banners` (definición en `scripts/crear_tabla_banners.sql`, creada con `scripts/crear_tabla_banners.py`): `id`, `imagen_url`, `public_id` (único, empieza con `agrovetzo/banners/`), `alt` (1 a 500 caracteres), `orden` (entero >= 0), `activo` (por defecto `false`) y `creado_en`.

Endpoints:
- `GET /api/banners/` — público; solo activos, ordenados por `orden, id`; responde `Cache-Control: no-store`.
- `GET /api/admin/banners`, `POST /api/admin/banners` (multipart: `archivo`, `alt` y `orden` opcional; se crea inactivo y, sin `orden`, al final de la lista), `PATCH /api/admin/banners/{id}` (`alt`, `orden`, `activo`), `PUT /api/admin/banners/orden` (cuerpo `{"ids": [...]}`: fija el orden de todos los banners de una vez, en una transacción) y `DELETE /api/admin/banners/{id}` — protegidos con la sesión del administrador.
- `PUT /api/admin/banners/orden` exige exactamente los ids existentes; si la lista cambió (otro banner subido o borrado) responde 409 y no escribe. Asigna `orden` 0, 1, 2... según la posición.

Reglas: el `public_id` lo genera el backend (aleatorio, `overwrite=False`). Al borrar se destruye primero la imagen en Cloudinary (aceptando "not found") y después la fila; si Cloudinary falla, la fila queda y se reintenta. Si el INSERT falla al subir, se intenta borrar la imagen recién subida; si el resultado del COMMIT es incierto, la imagen se conserva.

Panel: `frontend/admin-banners.html` + `frontend/js/admin-banners.js` (estilos en `admin-imagenes.css`), enlazado desde el panel de imágenes de productos. Permite subir (con texto alternativo; el banner nuevo queda al final y oculto), editar el texto, reordenar con botones ▲ Subir / ▼ Bajar, activar o desactivar y borrar. Si el servidor rechaza un reordenamiento, la fila vuelve a su lugar. Pide la clave de administrador y la guarda solo en memoria. Todo dato del servidor se pinta con `textContent`.

Estado: backend probado con mocks (`tests/unit/test_banners.py`) y con el circuito real en producción (crear inactivo, editar, listar, borrar; Cloudinary quedó vacío). Carrusel de la tienda (`index.html` + `main.js`, `iniciarCarruselBanners`): se arma con `GET /api/banners/`. Muestra la imagen entera (`object-fit: contain`, contenedor con `aspect-ratio: 1920 / 660` y `max-height: 500px`), sin textos superpuestos. Sin banners activos, o si la API falla, queda oculto y la tienda funciona igual. Con un solo banner no hay puntitos ni cambio automático; con varios cambia cada 5 s, se pausa al apuntar o enfocar, y no cambia solo si el cliente pidió "menos movimiento". Los puntitos son botones con nombre accesible. Los 3 banners fijos de prueba (`banner1-3.jpg`) se eliminaron. La lógica del panel y del carrusel se probó en un DOM simulado (jsdom, fuera del repo); todavía no en un navegador real, y falta revisar cómo se lee el texto de un banner en un celular (a 360 px de ancho la imagen mide ~124 px de alto).

### Documentación automática de la API

`/docs`, `/redoc` y `/openapi.json` están apagados por defecto (`main.py`) porque listan todas las rutas, incluidas las de administración. Para verlos en local: `HABILITAR_DOCS=1` en el `.env`. En Render no se define.

## Modelo de artículos compuestos: PRESENTACION vs COMBO

Decisión de modelo de dominio, **estable**. El campo `tipo_kit` ya existe como columna en SQL Server (`ARTICULOS.TIPO_KIT`) y en PostgreSQL (`articulos.tipo_kit`, con `CHECK` propio), y la sincronización de artículos ya lo propaga de punta a punta (`sincronizador.py` → `POST /api/sync/articulos` → `articulos.tipo_kit`). La distinción ya está implementada en los endpoints y en el frontend: `GET /api/articulos` excluye `COMBO` en todos sus modos (`AND a.tipo_kit IS DISTINCT FROM 'COMBO'`, commit `0306ffe`), `GET /api/articulos/presentaciones` y `presentacion=KIT` trabajan solo con `PRESENTACION`, y `GET /api/articulos/combos` devuelve solo `COMBO`. Lo pendiente (clasificación de kits reales y resincronización) está en `ROADMAP.md`, Fase 16.

### Problema detectado

`articulos.art_kit = true` hoy engloba dos conceptos comerciales distintos que la web necesita poder distinguir:

1. **PRESENTACION**: una forma de venta cerrada de un único producto base (ej. una bolsa de 25kg de un producto que también se vende a granel).
2. **COMBO**: una combinación comercial de productos, potencialmente de categorías distintas, pensada como oferta propia — no como una forma de venta de una sola categoría.

### Campo nuevo: `tipo_kit`

```text
art_kit = false  ->  tipo_kit = NULL
art_kit = true   ->  tipo_kit = PRESENTACION
art_kit = true   ->  tipo_kit = COMBO
```

No se usa `tipo_kit = "NORMAL"`: un artículo normal se sigue identificando por `art_kit = false` + `tipo_kit NULL`, igual que hoy.

`tipo_kit` es un **dato explícito**, nunca inferido. No son reglas válidas para determinarlo automáticamente:
- cantidad de componentes en `articulos_kit`;
- nombre del artículo;
- categoría del kit o de sus componentes;
- cantidad (`art_cantidad`) de un componente.

### Ejemplos

Artículo normal (sin cambios respecto al modelo actual):

```text
BOVIMAX A GRANEL
tipo_articulo = BALANCEADOS, art_kit = false, tipo_kit = NULL, unidad_venta = KG

BALA CALIBRE 22 POR UNIDAD
tipo_articulo = PROYECTILES, art_kit = false, tipo_kit = NULL, unidad_venta = UNIDAD
```

PRESENTACION — representa una forma de venta cerrada de un único producto base; pertenece a la categoría de su componente (su **tipo efectivo**, ver abajo), aunque su propio `tipo_articulo` en el sistema local siga siendo `KIT`:

```text
BOVIMAX X25KG
tipo_articulo = KIT, art_kit = true, tipo_kit = PRESENTACION
articulos_kit: BOVIMAX X25KG -> BOVIMAX A GRANEL x 25 KG

BALA CALIBRE 22 X CAJA
tipo_articulo = KIT, art_kit = true, tipo_kit = PRESENTACION
articulos_kit: BALA CALIBRE 22 X CAJA -> BALA CALIBRE 22 POR UNIDAD x 50
```

COMBO — técnicamente también un kit, pero comercialmente otro concepto; puede mezclar componentes de categorías distintas y **no** se considera una presentación de ninguna de esas categorías:

```text
COMBO CAZA
tipo_articulo = KIT, art_kit = true, tipo_kit = COMBO
componentes de categorías distintas (ej. PROYECTILES, INFLABLES, ...)
```

### Tipo efectivo de un artículo

El tipo `KIT` es solo un rótulo del sistema local (VFP): la forma de decirle al sistema que un producto debe
descontar el stock de otro artículo. **No es una categoría de la tienda.** Por eso, en la web:

- un kit `PRESENTACION` pertenece al tipo del artículo del que descuenta su stock (su único componente; hoy
  los 48 kits publicados tienen un solo componente): `PRONTO DOG X25KG` aparece en BALANCEADOS;
- el resto de los artículos usa su propio tipo;
- los `COMBO` no pertenecen a ningún tipo de la tienda (se muestran en su sección "Combos") y no dependen de
  que un tipo esté oculto.

Se calcula en SQL (`backend/app/sql_catalogo.py`: `SQL_TIPO_EFECTIVO`, `COALESCE(tipo del componente, tipo
propio)`) y lo usan el catálogo, las promociones, el detalle del producto, las formas de compra, el menú, el
panel de tipos y la validación de `confirmar_pedido`. Si algún día un kit `PRESENTACION` tuviera varios
componentes de tipos distintos, se tomaría el del componente de menor `art_cod`; si no tuviera componentes,
se usaría su propio tipo. Un artículo **normal** cargado con tipo `KIT` (hoy `HONDITA`) sí se trata como tipo
`KIT`: conviene corregir su tipo en el sistema local; mientras `KIT` esté oculto en el panel, ese artículo no se ve.

### Comportamiento del catálogo

- Las formas de compra de una categoría (`GET /api/articulos/presentaciones`) son las **unidades de venta**
  distintas de sus artículos publicados, kits por presentación incluidos: `[Por BOLSA] [Por CAJA] [Por KG]`,
  según la unidad que tenga cada artículo (los kits cuentan con su propia unidad). Ya no existe una forma de
  compra aparte "Por presentación".
- Con una sola unidad no se muestra el selector y se carga directo (ej. MERCERIAS / UNIDAD).
- Los kits `tipo_kit = COMBO` **no participan** del selector por categoría. Se muestran en una sección propia de la web (ej. "Combos"), separada del catálogo por categoría.

### Limpieza de datos (responsabilidad del usuario, en SQL Server)

Se detectaron artículos normales con `uni_cod_ven` mal configurado (ej. artículos "X100 UNIDAD" cargados con unidad `CAJA`). La corrección se hace manualmente en SQL Server, antes de continuar con cualquier cambio de código. No se compensan datos incorrectos con lógica en el backend ni se infiere la unidad por el nombre del artículo.

Corrección del 2026-10-12: 12 kits `PRESENTACION` tenían una unidad que no era la de su presentación (7 bolsas
de 25 kg como `KG` o `UNIDAD`, y 5 `PIOLIN X ROLLO` como `CAJA` o `UNIDAD`). Se corrigieron en la base de la web
(`uni_cod_com` y `uni_cod_ven`: 7 a `BOLSA`, 5 a `ROLLO`) y se dejó `scripts/corregir_unidades_kits_sqlserver.sql`
para aplicar lo mismo en el sistema local. **Mientras ese script no se corra en SQL Server, la próxima
sincronización de esos artículos volvería a dejar los valores viejos** (el upsert de `sync.py` actualiza `uni_cod_com`
y `uni_cod_ven`).

### Stock y pedidos

Hasta que se confirme una regla distinta, tanto `PRESENTACION` como `COMBO` siguen calculando disponibilidad física a partir de sus componentes (`articulos_kit` + `stock`), igual que hoy. `confirmar_pedido()` puede seguir tratando ambos como `art_kit = true` para el cálculo de consumo físico agregado — no se identificó, por ahora, una necesidad de distinguir `PRESENTACION` de `COMBO` en esa validación.

## Frontend: diseño responsivo y marca

El frontend (`frontend/index.html`, `frontend/css/styles.css`, `frontend/js/main.js`) está pensado **móvil primero**, porque la mayoría de los clientes compra desde el celular.

- **Paleta de marca**: tokens en `:root` (`--marron`, `--verde-accion`, `--verde-claro`, `--fondo`, `--texto`), tomados del logo `frontend/assets/images/logo-vete.jpg`. El verde del logo tal cual no alcanza contraste AA con texto blanco, por eso los botones usan `--verde-accion`.
- **Categorías**: barra de enlaces bajo la cabecera fija (en celular se desliza horizontalmente). Al elegir una se va a `/catalogo?categoria=…`, se sube a la sección (`irAlInicioDeLaVista`) y el título muestra el nombre de la categoría. Ya no hay menú lateral.
- **Cabecera**: fija; una fila con logo (enlace a la portada), buscador, Combos y Carrito, y debajo la barra de categorías. En celular la fila es una sola, con los botones solo con iconos. (El botón "Ver Promos" de la cabecera se retiró: las promociones ahora son la sección "Promoción vigente" de la portada.)
- **Búsqueda**: al escribir, lleva al catálogo con el texto en la URL y se busca en el servidor (ver "Vistas y rutas"). Enter busca ya, cierra el teclado y sube a los resultados.
- **Carrito en celular**: cada renglón se parte en dos filas para que el tacho de basura quede dentro de la pantalla.
- **Desplazamiento horizontal**: en celular, `overflow-x: clip` (con `hidden` como respaldo) evita arrastrar la página hacia los costados.
- **Combos**: en celular, latido suave (`latidoSuave`, solo escala). En escritorio, el latido con giro (`latidoVibratorio`).
- **Lógica sin cambios**: el rediseño no toca carrito, stock, presentaciones, combos ni paginación. Los IDs que usan las pruebas de frontend se conservaron.

Pendiente: tarjetas, selector de presentaciones y modales (Etapa 3 de `ROADMAP.md`, Fase 17).

### Cabecera fija y pie de página (Fase 20, etapa 2)

**Cabecera fija:** `header { position: sticky; top: 0; z-index: 100 }`: el logo, el buscador, Combos y Carrito quedan
siempre a la vista y el contenido (banner incluido) pasa por debajo. Tiene un **tamaño constante** (fila del logo: 80 px en escritorio,
58 px en celular): si se achicara al hacer scroll, el contenido daría saltos. En celular es **una sola fila** (logo ~36 px +
buscador + Combos + Carrito, solo con iconos; la burbuja del contador del carrito sigue visible). `main.js` publica el alto
real en la variable CSS `--alto-cabecera` (`publicarAltoDeCabecera`, con `ResizeObserver`); la usan
`html { scroll-padding-top }` (los `scrollIntoView` de `irAlInicioDeLaVista` no quedan tapados). La cabecera incluye la
barra de categorías, así que su alto total es de ~122 px en escritorio y ~100 px en celular. Las reglas de celular de la cabecera están **al final de
`styles.css`** a propósito: las de escritorio tienen la misma especificidad y, si las de celular estuvieran antes, ganarían ellas.
`html, body` usan `overflow-x: clip` (no `hidden`, que rompería `position: sticky`).

**Pie de página** (`<footer id="pie-pagina">`, en todas las vistas, fondo `--marron`; 4 columnas, 2 en tablet, 1 en
celular): *Cómo llegar* (el negocio figura en Google Maps como «Agro-Vetzo»; botón "Navegar" →
`https://www.google.com/maps/search/?api=1&query=Agro-Vetzo`, sin dirección escrita: conviene cambiarlo por el enlace
"Compartir" del local cuando se tenga), *Atención al cliente* (lunes a sábado de 07:00 a 19:00 hs,
`agroranchopiroy@gmail.com` y botón de WhatsApp), *Nuestras redes* (TikTok `@enzo.duarte326`) y *Nuestra tienda*
(enlaces internos: Inicio, Catálogo completo, Promociones y Combos si los hay, las primeras 8 categorías y, si hay más, "Ver todas las categorías"). El enlace de WhatsApp lo arma `main.js` con `WHATSAPP_NUMERO` (único lugar del número); el año del ©
también. Los enlaces internos (`data-ruta-interna`) navegan con `irA` sin recargar, para no perder el carrito;
"Promociones" y "Combos" solo se muestran si hay promociones vigentes o combos publicados (`mostrarEnlacePie`). Los
datos del negocio están en `index.html` (no son secretos).

## Pruebas

- `tests/unit/`: mock puro de `confirmar_pedido()`, unidades enteras y catálogo de combos. No se conecta a ninguna base: `tests/conftest.py` bloquea `psycopg.connect` en esos tests.
- `tests/integracion_lectura/`: requiere el servidor local y `DATABASE_URL`. Solo `SELECT` y `GET`, con conexión de solo lectura (`conn.read_only = True`). No escribe nada en PostgreSQL.
- Ejecución desde la raíz del proyecto, con `pytest` instalado desde `requirements-dev.txt`:

```text
.venv\Scripts\python.exe -m pytest tests/unit
.venv\Scripts\python.exe -m pytest tests/integracion_lectura   (con el servidor levantado en 127.0.0.1:8000)
```

- Las credenciales salen del entorno (`.env`, ignorado por Git). Ningún test versionado contiene secretos ni rutas absolutas.
- Las pruebas de frontend (jsdom) todavía no están en el repo.

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
- panel de administración con usuario y contraseña (hash scrypt), sesión por cookie HttpOnly y bloqueo por intentos;
- secretos en variables de entorno;
- reintentos;
- logs;
- operaciones idempotentes.
