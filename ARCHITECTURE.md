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
items.py       -> PostgreSQL  (migrado: catálogo, presentaciones, combos, confirmar-pedido)
sync.py        -> PostgreSQL  (siempre fue así: recibe del sincronizador)
admin.py       -> PostgreSQL + Cloudinary (siempre fue así; incluye banners)
banners.py     -> PostgreSQL  (lista pública del carrusel)
promos.py      -> SQL Server  (sin migrar todavía, es el único que queda; NO está
                               registrado en main.py, así que /api/promos/ no se sirve)
```

Arquitectura objetivo (ya alcanzada salvo `promos.py`):

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

Pendiente: migrar `promos.py` a PostgreSQL (requiere antes decidir cómo se
administran las promociones — ver sección "Promociones" más abajo).

## Conexiones actuales confirmadas

```text
backend/app/database.py
-> pyodbc
-> SQL Server
-> usado solo por backend/app/routers/promos.py

backend/app/database_postgres.py
-> psycopg
-> PostgreSQL en Render
-> usado por categories.py, items.py, sync.py y admin.py
```

Objetivo final (pendiente solo para `promos.py`):

```text
backend/app
-> PostgreSQL

sincronizador/
-> SQL Server
```

## Endpoint actual de categorías

`GET /api/categorias/` consulta PostgreSQL:

```sql
SELECT tipoart_cod, tipoart_desc
FROM tipo_articulo;
```

Devuelve una lista de `{"id": tipoart_cod, "nombre": tipoart_desc}`. Si la
tabla está vacía, responde 404.

## Endpoint actual de artículos

`GET /api/articulos/` consulta PostgreSQL (`articulos`, `tipo_articulo`,
`stock`, `unidad_medida`, más la subconsulta de stock de kits). Parámetros:
`pagina`, `limite`, `categoria` (o `"Todos"`), `unidad` (opcional, solo con
`presentacion` NORMAL o ninguna), `presentacion` (`NORMAL` | `KIT`,
opcional). Siempre excluye `tipo_kit='COMBO'`, en todos los modos (ver
"Modelo de artículos compuestos" más abajo). Devuelve, por artículo:

```text
id
nombre
precio
tipo            (nombre de la categoría)
imagen
stock_disponible
unidad_venta
fraccionable
```

`GET /api/articulos/presentaciones?categoria=` y `GET /api/articulos/combos`
comparten el mismo formato de respuesta; están descriptos en la sección
"Modelo de artículos compuestos: PRESENTACION vs COMBO".

## Endpoint actual de pedidos

`POST /api/articulos/confirmar-pedido` ya corre sobre PostgreSQL, dentro de
una única transacción (rollback si cualquier fase falla):

1. valida que el pedido no esté vacío y no tenga artículos repetidos;
2. trae metadatos de los artículos pedidos (precio oficial, si es kit,
   fraccionable, unidad de venta) — nunca confía en lo que mandó el
   navegador;
3. valida reglas de cantidad: enteros para no-fraccionables, y enteros
   también para KG/LITROS/METROS por política web (ver "Política de
   cantidades" más abajo);
4. para los kits del pedido, trae su composición (`articulos_kit`) y la
   expande a consumo físico de sus componentes;
5. valida el stock físico **agregado**: si un artículo directo y un kit
   comparten el mismo componente, se suman antes de comparar contra el
   stock real; detecta también kits anidados (no soportado) y kits sin
   componentes configurados (inconsistencia interna, 500);
6. recién con todo validado, inserta `pedido_cabecera`, `pedido_detalle` y
   un snapshot por componente en `pedido_detalle_componentes`, y hace
   commit.

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

### Despliegue en Render

`render.yaml` (Blueprint) declara solo el servicio web `agrovetzo-web` (plan free, Python 3.13.5, `uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT`, build con `requirements-render.txt`). La base PostgreSQL ya existente no se declara, para no crear otra. Las variables `DATABASE_URL`, `SYNC_API_KEY`, `ADMIN_API_KEY` y `CLOUDINARY_*` están como `sync: false`: se cargan a mano en el panel de Render y nunca van al repo.

`requirements-render.txt` es igual a `backend/requirements.txt` sin `pyodbc`: el backend publicado no consulta SQL Server. Por eso `main.py` no registra el router de promos (importa `database.py`, que exige `pyodbc` y las variables `DB_*`). Estado: archivos creados, **todavía sin desplegar ni verificar en Render**; la versión de Python y el arranque real están por confirmar.

### Banners del carrusel

Los banners son imágenes completas (con el texto ya incluido en la imagen), pensadas en 1920 × 660 px, que se suben desde el administrador y se guardan en Cloudinary (carpeta `agrovetzo/banners`). Solo viven en PostgreSQL; no existen en SQL Server.

Tabla `banners` (definición en `scripts/crear_tabla_banners.sql`, creada con `scripts/crear_tabla_banners.py`): `id`, `imagen_url`, `public_id` (único, empieza con `agrovetzo/banners/`), `alt` (1 a 500 caracteres), `orden` (entero >= 0), `activo` (por defecto `false`) y `creado_en`.

Endpoints:
- `GET /api/banners/` — público; solo activos, ordenados por `orden, id`; responde `Cache-Control: no-store`.
- `GET /api/admin/banners`, `POST /api/admin/banners` (multipart: `archivo`, `alt`, `orden`; se crea inactivo), `PATCH /api/admin/banners/{id}` (`alt`, `orden`, `activo`) y `DELETE /api/admin/banners/{id}` — protegidos con `X-Admin-Key`.

Reglas: el `public_id` lo genera el backend (aleatorio, `overwrite=False`). Al borrar se destruye primero la imagen en Cloudinary (aceptando "not found") y después la fila; si Cloudinary falla, la fila queda y se reintenta. Si el INSERT falla al subir, se intenta borrar la imagen recién subida; si el resultado del COMMIT es incierto, la imagen se conserva.

Estado: backend implementado y probado con mocks (`tests/unit/test_banners.py`). Falta la sección del panel (`admin-imagenes.html`) y que `index.html` lea la API (hoy el carrusel sigue con las 3 imágenes locales y textos de prueba).

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

PRESENTACION — representa una forma de venta cerrada de un único producto base; pertenece funcionalmente a la categoría de su componente, aunque su propio `tipo_articulo` siga siendo `KIT`:

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

### Comportamiento del catálogo

- Si una categoría tiene artículos normales (una sola unidad) **y** presentaciones (`tipo_kit = PRESENTACION`) relacionadas: mostrar selector, ej. `[Por KG] [Presentaciones]`.
- Si una categoría solo tiene artículos normales con una única unidad: no mostrar selector, cargar directo (ej. MERCERIAS / UNIDAD).
- Los kits `tipo_kit = COMBO` **no participan** del selector por categoría. Se muestran en una sección propia de la web (ej. "Combos"), separada del catálogo por categoría.

### Limpieza de datos (responsabilidad del usuario, en SQL Server)

Se detectaron artículos normales con `uni_cod_ven` mal configurado (ej. artículos "X100 UNIDAD" cargados con unidad `CAJA`). La corrección se hace manualmente en SQL Server, antes de continuar con cualquier cambio de código. No se compensan datos incorrectos con lógica en el backend ni se infiere la unidad por el nombre del artículo.

### Stock y pedidos

Hasta que se confirme una regla distinta, tanto `PRESENTACION` como `COMBO` siguen calculando disponibilidad física a partir de sus componentes (`articulos_kit` + `stock`), igual que hoy. `confirmar_pedido()` puede seguir tratando ambos como `art_kit = true` para el cálculo de consumo físico agregado — no se identificó, por ahora, una necesidad de distinguir `PRESENTACION` de `COMBO` en esa validación.

## Frontend: diseño responsivo y marca

El frontend (`frontend/index.html`, `frontend/css/styles.css`, `frontend/js/main.js`) está pensado **móvil primero**, porque la mayoría de los clientes compra desde el celular.

- **Paleta de marca**: tokens en `:root` (`--marron`, `--verde-accion`, `--verde-claro`, `--fondo`, `--texto`), tomados del logo `frontend/assets/images/logo-vete.jpg`. El verde del logo tal cual no alcanza contraste AA con texto blanco, por eso los botones usan `--verde-accion`.
- **Categorías**: en celular (≤ 768 px), un botón "Categorías: <actual> ▾" despliega la lista. En escritorio, el panel es `sticky`. Al elegir categoría se sube a la sección de artículos (`irAlInicioDeLaVista`), y el título de la sección muestra el nombre de la categoría.
- **Cabecera**: en escritorio, una fila con logo, buscador, Promos, Combos y Carrito. En celular, tres filas: logo + Carrito, buscador completo, y Promos + Combos.
- **Búsqueda**: al escribir, si la vista activa no es el catálogo, vuelve a él. Enter cierra el teclado y sube a los resultados.
- **Carrito en celular**: cada renglón se parte en dos filas para que el tacho de basura quede dentro de la pantalla.
- **Desplazamiento horizontal**: en celular, `overflow-x: clip` (con `hidden` como respaldo) evita arrastrar la página hacia los costados.
- **Promos y Combos**: en celular, latido suave (`latidoSuave`, solo escala). En escritorio, el latido con giro (`latidoVibratorio`).
- **Lógica sin cambios**: el rediseño no toca carrito, stock, presentaciones, combos ni paginación. Los IDs que usan las pruebas de frontend se conservaron.

Pendiente: tarjetas, selector de presentaciones y modales (Etapa 3 de `ROADMAP.md`, Fase 17).

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
- secretos en variables de entorno;
- reintentos;
- logs;
- operaciones idempotentes.
