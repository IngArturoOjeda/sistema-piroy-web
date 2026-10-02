# Guía de puesta en producción — Sincronización SQL Server ↔ PostgreSQL

## 1. Arquitectura general

```text
Visual FoxPro 9 (Caja 1 / Caja 2)
        |
        v
     SQL Server (fuente operativa local)
        |
        v (lee pendientes, HTTPS)
  Sincronizador Python (corre en la agroveterinaria)
        |
        v (POST con X-API-Key)
     FastAPI (Render)
        |
        v
     PostgreSQL (Render, fuente del ecommerce)
```

Reglas fijas del proyecto (`AGENTS.md`):
- El backend web (`backend/app`) **no** debe consultar SQL Server para los endpoints públicos.
- SQL Server nunca se expone a Internet ni se abre el puerto 1433 públicamente.
- Una venta local nunca depende de Internet.
- Ningún trigger de SQL Server ejecuta HTTP ni Python directamente — solo marca "pendiente" en tablas `CAMBIOS_*`. El sincronizador es el único que habla por HTTPS.

## 2. Tablas de control de pendientes (`CAMBIOS_*`)

Las tres siguen el mismo patrón: `version_actual > version_enviada` significa "pendiente de sincronizar".

### `CAMBIOS_ARTICULOS`
Ya existía antes de este trabajo (documentada en `ARCHITECTURE.md`), con trigger sobre `ARTICULOS`. No se modificó su estructura en este proceso.

### `CAMBIOS_ARTICULOS_KIT`
```sql
CREATE TABLE CAMBIOS_ARTICULOS_KIT (
    art_codkit           INT      NOT NULL,
    version_actual        INT      NOT NULL DEFAULT 1,
    version_enviada       INT      NOT NULL DEFAULT 0,
    fecha_cambio          DATETIME NOT NULL DEFAULT GETDATE(),
    fecha_sincronizacion  DATETIME NULL,
    CONSTRAINT PK_CAMBIOS_ARTICULOS_KIT PRIMARY KEY (art_codkit)
);
```
Un solo registro por `art_codkit` (el kit completo, no por línea de componente).

### `CAMBIOS_STOCK`
Ya existía antes de este trabajo (`art_cod` PK, `version_actual`, `version_enviada`, `fecha_cambio`, `fecha_sincronizacion`). No se modificó su estructura.

## 3. Triggers

### Trigger sobre `ARTICULOS` (preexistente)
Detecta cambios en la fila del artículo y mantiene `CAMBIOS_ARTICULOS`. No se modificó en este trabajo; su definición exacta no se documenta acá porque no se revisó su código fuente durante este proceso.

### `TRG_ARTICULOS_KIT_CAMBIOS` (nuevo, sobre `ARTICULOS_KIT`)
- Dispara con `AFTER INSERT, UPDATE, DELETE`.
- Junta los `ART_CODKIT` afectados de `inserted` y `deleted` con `UNION` (deduplica automáticamente) en una tabla variable con `PRIMARY KEY(art_codkit)`.
- Filtra explícitamente `ART_CODKIT IS NOT NULL` en ambos lados (defensivo; se confirmó que hoy no hay filas con `ART_CODKIT` nulo).
- Si el kit modificado cambia `ART_CODKIT` (un componente se mueve de un kit a otro), **ambos** códigos de kit quedan marcados como pendientes.
- Incrementa `version_actual` una sola vez por `art_codkit` por sentencia, sin importar cuántas líneas de ese kit se hayan tocado.
- Validado en SQL Server con pruebas de `INSERT`, `UPDATE` (una línea y varias líneas del mismo kit) y `DELETE`, todas dentro de `BEGIN TRANSACTION`/`ROLLBACK`. Confirmado por el usuario como funcionando.

### `TR_STOCK_CAMBIO` (modificado, sobre `STOCK`)
El trigger **ya existía** antes de este trabajo, disparando con `AFTER INSERT, UPDATE`. **No es correcto decir que se agregó `INSERT`** en este proceso — ya estaba. La modificación realizada fue:
- agregar `DELETE` a los eventos que dispara el trigger;
- mantener `INSERT` y `UPDATE` tal como ya estaban;
- hacer la lógica defensiva ante un cambio manual de `art_cod` en una fila de `STOCK` (si alguien reasigna manualmente una fila a otro artículo, marca **ambos** artículos como pendientes);
- deduplicar por `art_cod` con la misma tabla variable + `UNION` que ya usa el trigger de kits (un incremento por `art_cod` por sentencia);
- comparar `sto_cantidad` y `art_cod` con `ISNULL(..., 0)` en ambos lados (evita el resultado `UNKNOWN` de SQL Server ante un cambio `NULL → valor` o `valor → NULL`).

Clasifica cada fila de `STOCK` por su `sto_id`: solo en `inserted` (INSERT), en ambas (UPDATE), solo en `deleted` (DELETE, el evento nuevo agregado).

Validado en SQL Server por el usuario con los tres casos (`UPDATE` sin cambio de cantidad, `UPDATE` con cambio de cantidad, `DELETE`), confirmado como funcionando ("ya validamos en SQL Server el trigger TR_STOCK_CAMBIO con INSERT/UPDATE/DELETE").

## 4. `unidad_medida`

```sql
CREATE TABLE unidad_medida (
    uni_cod      INTEGER NOT NULL,
    uni_nombre   TEXT    NOT NULL,
    fraccionable BOOLEAN NOT NULL,
    CONSTRAINT pk_unidad_medida PRIMARY KEY (uni_cod)
);
```

`uni_cod` conserva exactamente el código de SQL Server (`UNIDADMEDIDA.UNI_COD`), sin generar IDs nuevos.

Códigos cargados manualmente en PostgreSQL (una sola vez, sin sincronización automática, igual que `tipo_articulo`):

| uni_cod | uni_nombre | fraccionable |
|---|---|---|
| 1 | UNIDAD | false |
| 2 | CAJA | false |
| 3 | KG | true |
| 5 | BOLSA | false |
| 6 | ROLLO | false |
| 7 | METROS | true |
| 8 | LITROS | true |

## 5. `art_kit`, `uni_cod_com`, `uni_cod_ven` en `articulos`

```sql
ALTER TABLE articulos
    ADD COLUMN art_kit     BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN uni_cod_com INTEGER NULL,
    ADD COLUMN uni_cod_ven INTEGER NULL;

ALTER TABLE articulos
    ADD CONSTRAINT fk_articulos_unidad_com
        FOREIGN KEY (uni_cod_com) REFERENCES unidad_medida (uni_cod);

ALTER TABLE articulos
    ADD CONSTRAINT fk_articulos_unidad_ven
        FOREIGN KEY (uni_cod_ven) REFERENCES unidad_medida (uni_cod);
```

- `art_kit`: `0` = artículo normal/base, `1` = kit/combo. Hoy no existen kits dentro de kits.
- `uni_cod_com` / `uni_cod_ven`: unidad de compra y de venta. Nacen `NULL` en artículos ya sincronizados antes de este cambio, hasta que se resincronicen.
- Se sincronizan desde `ARTICULOS.art_kit`, `ARTICULOS.UNI_COD_COM`, `ARTICULOS.UNI_COD_VEN`.

> **Nota**: `art_kit=true` engloba dos conceptos distintos, `PRESENTACION` y `COMBO`, distinguidos por la columna `tipo_kit` (`ARTICULOS.TIPO_KIT` en SQL Server, `articulos.tipo_kit` en PostgreSQL con `CHECK` propio). La columna ya existe en ambas bases y la sincronización de artículos ya la propaga (`sincronizador.py` → `POST /api/sync/articulos`). Ver la sección "Modelo de artículos compuestos: PRESENTACION vs COMBO" en `ARCHITECTURE.md` para la regla completa, y `ROADMAP.md` (Fase 16) para lo que todavía falta (clasificar los kits existentes, resincronizar, y adaptar catálogo/frontend). Esta guía (secciones 5-6) sigue describiendo el flujo tal como se diseñó antes de `tipo_kit`; no se reescribe hasta completar la Fase 16.

## 6. `articulos_kit`

```sql
CREATE TABLE articulos_kit (
    idkit        INTEGER      NOT NULL,
    art_codkit   BIGINT       NOT NULL,
    art_cod      BIGINT       NOT NULL,
    art_cantidad NUMERIC(9,3) NOT NULL,
    CONSTRAINT pk_articulos_kit PRIMARY KEY (idkit),
    CONSTRAINT fk_articulos_kit_kit
        FOREIGN KEY (art_codkit) REFERENCES articulos (art_cod),
    CONSTRAINT fk_articulos_kit_componente
        FOREIGN KEY (art_cod) REFERENCES articulos (art_cod),
    CONSTRAINT uq_articulos_kit_kit_componente
        UNIQUE (art_codkit, art_cod)
);
```

- `idkit` es el mismo identificador de fila que trae `ARTICULOS_KIT.idkit` en SQL Server (no autoincremental en PostgreSQL, no se generan IDs nuevos).
- `art_codkit` es directamente el `art_cod` del artículo kit (no existe una tabla de cabecera de kit separada); se repite una fila por cada componente.
- `art_cod` es el componente; ambas columnas (`art_codkit` y `art_cod`) apuntan a la misma tabla `articulos`.
- `art_cantidad` indica cuánto consume 1 unidad del kit de ese componente (ej. vender 1 "BOLSA MAIZ 5 KG" consume 5 KG de "MAIZ A GRANEL").
- `UNIQUE(art_codkit, art_cod)`: un componente no puede repetirse dentro del mismo kit. Se verificó en SQL Server que hoy existen 0 filas duplicadas de `(ART_CODKIT, ART_COD)` antes de aprobar esta restricción.

## 7. Reglas `llevar_web` / `mostrar_web` / `art_estado`

- `llevar_web` (SQL Server, `BIT`): `0` = no participa del ecommerce; `1` = puede sincronizarse a PostgreSQL. Todo artículo nuevo debería nacer con `llevar_web = 0`. Se controla exclusivamente desde el sistema local (VFP/SQL Server).
- `mostrar_web` (PostgreSQL, `BOOLEAN`, nace en `FALSE`): controla si un artículo **ya sincronizado** se muestra públicamente en la web ahora mismo. Se controla desde el panel administrativo (`frontend/admin-imagenes.html`, switch "Mostrar en web" → `PATCH /api/admin/articulos/{art_cod}/mostrar-web`).
- `art_estado` (`'S'` = vigente, `'N'` = inactivo).
- **Regla final de visibilidad pública** (usada en `GET /api/articulos`):
  ```sql
  art_estado = 'S' AND llevar_web = TRUE AND mostrar_web = TRUE
  ```
  Las tres condiciones deben cumplirse a la vez.
- El panel administrativo **nunca** modifica `llevar_web` ni `art_estado` — esos siguen siendo controlados desde SQL Server/VFP.

## 8. Orden de sincronización: artículos → kits → stock

El sincronizador (`sincronizador/sincronizador.py`, función `main()`) sigue este orden estricto en cada ejecución:

1. **Artículos** (`CAMBIOS_ARTICULOS` → `POST /api/sync/articulos`).
   - Si terminó con errores o se abortó, **no se procesan ni kits ni stock**, y el proceso termina con código de salida `1`. Motivo: tanto kits como stock dependen de que los artículos ya existan en PostgreSQL.
2. **Kits** (`CAMBIOS_ARTICULOS_KIT` → `POST /api/sync/articulos-kit`), solo si el paso 1 no tuvo errores.
3. **Stock** (`CAMBIOS_STOCK` → `POST /api/sync/stock`), también solo si el paso 1 no tuvo errores.
   - Los errores de kits **no** bloquean el procesamiento de stock (el stock físico no depende de la composición de un kit).
   - Código de salida final: `0` solo si kits **y** stock terminaron sin errores; `1` si cualquiera de los dos tuvo errores (aunque ambos se hayan intentado igual).

## 9. `version_actual` / `version_enviada`

Mismo patrón en las tres tablas `CAMBIOS_*`:
- El trigger correspondiente incrementa `version_actual` cuando detecta un cambio real.
- El sincronizador lee todo lo que cumple `version_actual > version_enviada`.
- Recién **después** de una respuesta `200 {"status": "ok", ...}` de FastAPI, confirma en SQL Server:
  ```sql
  UPDATE CAMBIOS_X
  SET version_enviada = ?,
      fecha_sincronizacion = GETDATE()
  WHERE <clave> = ?
    AND version_enviada < ?;
  ```
  El `AND version_enviada < ?` es defensivo: si `version_actual` volvió a subir mientras el envío estaba en curso (otro cambio concurrente), esa versión más nueva queda pendiente para la próxima ejecución, sin perderse.

## 10. Consultas de verificación previas (ya ejecutadas)

- Antes de aprobar `UNIQUE(art_codkit, art_cod)` en `articulos_kit`: se verificó en SQL Server que no existen componentes duplicados por kit (0 filas).
- Antes de definir `StockSync.cantidad` con `ge=0`: se verificó en SQL Server que no existe ningún `sto_cantidad < 0` actualmente.
- Antes de escribir los mensajes de error por violación de FK en `sync.py`: se verificaron (solo lectura, vía `pg_constraint`) los nombres reales de las restricciones en PostgreSQL: `fk_articulos_tipo_articulo`, `fk_articulos_unidad_com`, `fk_articulos_unidad_ven`, `fk_articulos_kit_componente`, `fk_stock_articulos`.

## 11. Validación de unidades inexistentes (`uni_cod_com` / `uni_cod_ven`)

Si el sincronizador envía un código de unidad que no está cargado en `unidad_medida`, el `INSERT`/`UPDATE` de `POST /api/sync/articulos` falla por violación de FK. El backend identifica cuál de las dos restricciones falló (`e.diag.constraint_name`) y responde `422` con un mensaje específico: `"uni_cod_com X no existe en unidad_medida"` o `"uni_cod_ven X no existe en unidad_medida"`.

### Incidente real: unidad `4 = GRAMOS`

Durante las pruebas reales se encontraron **20 artículos** que todavía referenciaban el código `4 = GRAMOS` en SQL Server, una unidad que ya había sido eliminada de `UNIDADMEDIDA`. Esto provocó realmente el error:

```
HTTP 422: "uni_cod_com 4 no existe en unidad_medida"
```

Esos 20 artículos se corrigieron en SQL Server a `3 = KG`.

**Verificación obligatoria antes de producción**: correr esta consulta en SQL Server para detectar unidades inexistentes antes de sincronizar artículos:

```sql
SELECT
    A.art_cod,
    A.art_nombre,
    A.UNI_COD_COM,
    A.UNI_COD_VEN
FROM ARTICULOS A
LEFT JOIN UNIDADMEDIDA UC
    ON UC.UNI_COD = A.UNI_COD_COM
LEFT JOIN UNIDADMEDIDA UV
    ON UV.UNI_COD = A.UNI_COD_VEN
WHERE
    (A.UNI_COD_COM IS NOT NULL AND UC.UNI_COD IS NULL)
    OR
    (A.UNI_COD_VEN IS NOT NULL AND UV.UNI_COD IS NULL)
ORDER BY A.art_cod;
```

Si devuelve filas, hay que corregir el código de unidad en SQL Server (o cargar la unidad faltante en `unidad_medida` en PostgreSQL, si corresponde) antes de sincronizar esos artículos.

## 12. Validación de duplicados de kits

Dos capas:
1. **Pydantic** (`ArticulosKitSync`): un validador rechaza con `422`, antes de tocar la base, si el payload trae dos componentes con el mismo `art_cod` para el mismo kit.
2. **PostgreSQL**: `UNIQUE(art_codkit, art_cod)` es la barrera final si algo se colara igual.

## 13. Validación de `ART_CODKIT` `NULL`

`TRG_ARTICULOS_KIT_CAMBIOS` filtra explícitamente `ART_CODKIT IS NOT NULL` al construir la lista de kits afectados, tanto en `inserted` como en `deleted`. Es una protección defensiva: se confirmó que hoy no existen filas con `ART_CODKIT` nulo en `ARTICULOS_KIT`.

## 14. Validación de `ART_CANTIDAD <= 0`

- **Regla de negocio confirmada**: `ART_CANTIDAD` nunca se guarda en `0` en el sistema local; si un kit queda sin componentes, ese kit se elimina directamente del sistema local.
- **Backend** (`ComponenteKit.art_cantidad`): usa `Field(gt=0, max_digits=9, decimal_places=3)` — rechaza con `422` cualquier cantidad `<= 0` que llegara de todos modos.

## 15. Validación de `STOCK` huérfano (`art_cod` que no existe en `ARTICULOS`/`articulos`)

`POST /api/sync/stock` primero consulta `SELECT art_kit FROM articulos WHERE art_cod = %s`. Si no hay fila, responde `404` ("no existe en articulos") **sin insertar nada** — no se inventan artículos nuevos a partir de una fila de stock. El artículo debe sincronizarse primero por `POST /api/sync/articulos`; mientras tanto, ese stock queda pendiente (no se confirma `version_enviada`) y se reintenta en la próxima ejecución.

### Incidente real: filas de `STOCK` huérfanas

Antes de la carga inicial de stock se encontraron **8 filas en `STOCK`** cuyo `art_cod` ya no existía en `ARTICULOS`. Eran datos viejos de pruebas, y se decidió eliminarlas antes de la carga inicial.

**Control obligatorio** antes de sincronizar stock, en SQL Server:

```sql
SELECT
    S.art_cod,
    S.dep_cod,
    S.sto_cantidad,
    S.sto_id
FROM STOCK S
LEFT JOIN ARTICULOS A
    ON A.art_cod = S.art_cod
WHERE A.art_cod IS NULL
ORDER BY S.art_cod;
```

- Si devuelve **0 filas**: correcto, se puede continuar.
- Si devuelve filas: revisar el origen de cada una antes de decidir qué hacer. **No borrarlas automáticamente en producción sin analizar por qué existen** — en este proyecto se confirmó que eran datos viejos de prueba antes de eliminarlas, pero eso no debe asumirse sin revisar caso por caso.

## 16. Validación de stock negativo

- Se verificó en SQL Server que **no existe** ningún `sto_cantidad < 0` hoy.
- `StockSync.cantidad` usa `Field(ge=0, max_digits=9, decimal_places=3)` — rechaza con `422` cualquier valor negativo que llegara igual.

## 17. Tratamiento de kits inactivos / no web

- La consulta de pendientes de stock filtra `A.art_kit = 0`: el stock de un kit **nunca** se sincroniza, porque el kit no tiene stock físico propio — el stock pertenece a sus componentes.
- `POST /api/sync/stock` repite esa validación del lado del backend: si `articulos.art_kit = TRUE` para ese `art_cod`, responde `422` ("es un kit, no tiene stock fisico propio") y no escribe nada.
- El cálculo de disponibilidad de un kit a partir del stock de sus componentes **no está implementado todavía** — queda para una etapa posterior.

## 18. Tratamiento de `llevar_web = 0`

- La consulta de pendientes de stock también filtra `A.llevar_web = 1`. Si `llevar_web = 0`, ese stock **no se sincroniza** y **no se marca artificialmente como enviado** — el pendiente queda tal cual (`version_actual > version_enviada`) indefinidamente, sin necesidad de limpieza.
- Si más adelante `llevar_web` pasa de `0` a `1`: primero se sincroniza el artículo, y en la siguiente corrida el stock vuelve a entrar solo en la consulta de pendientes (porque ahora cumple la condición), enviando el stock **actual** en ese momento. No hace falta ningún proceso especial de limpieza ni de recuperación de historial.

## 19. Tratamiento defensivo de `DELETE` en `STOCK` como cantidad `0`

La consulta de pendientes de stock usa:
```sql
LEFT JOIN STOCK S ON S.art_cod = C.art_cod
...
ISNULL(S.sto_cantidad, 0) AS sto_cantidad
```
Si la fila de `STOCK` fue eliminada (el sistema local normalmente nunca borra filas de `STOCK`, pero `TR_STOCK_CAMBIO` lo contempla defensivamente), el payload enviado a PostgreSQL lleva `"cantidad": "0.000"`.

## 20. Variables de entorno

| Variable | Uso | Notas |
|---|---|---|
| `SYNC_API_URL` | URL del endpoint de artículos (`.../api/sync/articulos`) | Obligatoria en cada ejecución |
| `SYNC_API_URL_KITS` | URL del endpoint de kits (`.../api/sync/articulos-kit`) | Se lee de forma diferida, solo si hay kits pendientes |
| `SYNC_API_URL_STOCK` | URL del endpoint de stock (`.../api/sync/stock`) | Se lee de forma diferida, solo si hay stock pendiente |
| `SYNC_API_KEY` | Clave compartida, enviada como header `X-API-Key` en los tres endpoints | Misma clave para artículos, kits y stock |

Sin `SYNC_API_KEY` configurada en el backend, los tres endpoints responden `503`. Con una clave incorrecta, responden `401`.

Estas variables se agregan al `.env` local del sincronizador y a las variables de entorno de Render (para el backend). También son necesarias, previamente: `DB_DRIVER`, `DB_SERVER`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` (SQL Server, lado sincronizador) y `DATABASE_URL` (PostgreSQL, lado backend) — ya documentadas en `.env.example`.

## 21. Pruebas controladas realizadas

**Importante**: distingo abajo qué se probó contra datos/servicios reales, y qué solo se verificó con mocks o directamente en SQL Server, para no dar por sentado algo que no se confirmó de punta a punta.

### Artículos
- **Prueba real de producción**: se limitó temporalmente la consulta de pendientes a `TOP 5` (commit `test: limita sincronizacion a cinco articulos`), se ejecutó el sincronizador real contra SQL Server y PostgreSQL de Render, y el resultado confirmado por el usuario fue: 5 artículos procesados, 5 sincronizados correctamente en PostgreSQL, `version_enviada` y `fecha_sincronizacion` actualizadas en SQL Server, 0 errores.
- Se quitó después el límite temporal (commit `test: quita limite temporal de sincronizacion`) para dejar el sincronizador procesando el catálogo completo.

### Kits
- El trigger `TRG_ARTICULOS_KIT_CAMBIOS` y la tabla `CAMBIOS_ARTICULOS_KIT` se probaron directamente en SQL Server (`INSERT`, `UPDATE` de una y de varias líneas del mismo kit, `DELETE`, todo dentro de `BEGIN TRANSACTION`/`ROLLBACK`), confirmado por el usuario como funcionando.
- El código de `POST /api/sync/articulos-kit` y la lógica de `procesar_pendientes_kits` en el sincronizador se verificaron con pruebas unitarias usando mocks (sin tocar SQL Server ni PostgreSQL reales): validación de schema, deduplicación, y la compuerta que impide procesar kits si artículos tuvo errores.
- **Prueba real de producción**: se sincronizó realmente el kit `art_codkit = 21038` ("BALA CALIBRE 22 X CAJA"), con un componente (`idkit = 5016`, `art_cod = 321220`, `art_cantidad = 50.000`). Resultado del sincronizador:
  ```
  [1/1] art_codkit=21038 version=1 OK
  ```
  Se verificó después:
  - En SQL Server: `version_actual = version_enviada` para ese kit.
  - En PostgreSQL, `articulos_kit`: `idkit=5016`, `art_codkit=21038`, `art_cod=321220`, `art_cantidad=50.000`.
- Posteriormente se realizó la carga inicial de los kits válidos (ver sección 22).

### Stock
- El trigger `TR_STOCK_CAMBIO` se probó directamente en SQL Server (`UPDATE` sin cambiar cantidad, `UPDATE` cambiando cantidad, `DELETE`, dentro de `BEGIN TRANSACTION`/`ROLLBACK`), confirmado por el usuario como funcionando.
- El código de `POST /api/sync/stock` y `procesar_pendientes_stock` se verificaron con pruebas unitarias usando mocks: validación de schema (`cantidad >= 0`, precisión decimal), y la compuerta de `main()` (errores de kits no bloquean stock; errores de artículos bloquean todo).
- **Prueba real de producción**: se sincronizó realmente el stock del artículo `art_cod = 1000` ("BOTINA EN CUERO PARA TRABAJO Nº 38", `art_kit=0`, `llevar_web=1`, stock en SQL Server = `3.000`). Resultado del sincronizador:
  ```
  [1/2] art_cod=1000 version=1 OK
  [2/2] art_cod=731998 version=2 OK

  Pendientes encontrados: 2
  Sincronizados OK: 2
  Con error: 0
  ```
  Se verificó después:
  - En SQL Server: `version_actual = version_enviada` para ambos artículos.
  - En PostgreSQL: las cantidades coincidían con SQL Server.
- La carga inicial masiva de stock **todavía está en proceso**, no se da por completada (ver sección 22).

## 22. Procedimiento de carga inicial

Receta repetible, en este orden:

1. Validar datos en SQL Server (unidades inexistentes, duplicados, etc.).
2. Limpiar las inconsistencias encontradas.
3. Verificar que `unidad_medida` esté cargada correctamente en PostgreSQL (tabla de la sección 4).
4. Sembrar `CAMBIOS_ARTICULOS`.
5. Probar con pocos artículos.
6. Sincronizar los artículos completos.
7. Sembrar `CAMBIOS_ARTICULOS_KIT`.
8. Probar un solo kit.
9. Sincronizar los kits.
10. Validar que no haya `STOCK` huérfano (sección 15).
11. Sembrar `CAMBIOS_STOCK`.
12. Probar un solo artículo de stock.
13. Sincronizar el stock completo.
14. Verificar pendientes restantes (sección 23), distinguiendo pendientes procesables de pendientes excluidos por reglas de negocio.
15. Comparar muestras entre SQL Server y PostgreSQL para confirmar coherencia.

### Configuración común (artículos, kits y stock)

- Confirmar que `tipo_articulo` (42 registros) y `unidad_medida` (7 registros, tabla de la sección 4) ya están cargados manualmente en PostgreSQL — ambos ya se hicieron.
- Configurar en Render (backend): `DATABASE_URL`, `SYNC_API_KEY`, `ADMIN_API_KEY`, `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET`.
- Configurar en la máquina del sincronizador (local, SQL Server): `DB_DRIVER`, `DB_SERVER`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `SYNC_API_KEY` (mismo valor que en Render), `SYNC_API_URL`, `SYNC_API_URL_KITS`, `SYNC_API_URL_STOCK`.
- Hacer `git pull` en esa máquina para tener la última versión de `sincronizador/`.
- Ejecutar `python -m sincronizador.sincronizador` desde la raíz del proyecto.
- Antes de dejarlo correr sobre todo el catálogo, acotar temporalmente la consulta de pendientes (por ejemplo, a un solo `art_codkit` o `art_cod` de prueba) y confirmar el resultado antes de quitar el límite — así se hizo para artículos (`TOP 5`), kits y stock (ver sección 21).
- Repetir la ejecución del sincronizador de forma periódica. **Todavía no existe un servicio de Windows** que lo automatice (queda pendiente, `ROADMAP.md` Fase 14); por ahora se ejecuta manualmente.

### Carga inicial de artículos

Una vez sincronizados, revisar en PostgreSQL cuáles quedaron con `mostrar_web = FALSE` (nacen así por defecto) y habilitar manualmente (o desde el panel administrativo) los que deban publicarse.

### Carga inicial de kits

Datos reales observados durante la carga:
- **63 kits únicos** en `ARTICULOS_KIT`.
- **1** ya existía previamente en `CAMBIOS_ARTICULOS_KIT`.
- Los **62 restantes** se sembraron con `version_actual = 1`, `version_enviada = 0`.
- Se detectó un caso problemático: `art_codkit = 621424`, con `art_estado = 'N'` y `llevar_web = 0` — ese artículo cabecera **no existía en PostgreSQL** (porque nunca se sincroniza un artículo con `llevar_web = 0`), y al intentar sincronizar su composición de kit, el backend respondió `404`.

**Decisión final**: no sincronizar la composición de un kit cuyo artículo cabecera no participa del ecommerce. Para la carga inicial, solo se consideran kits cuyo artículo cabecera cumple:
```sql
art_estado = 'S' AND llevar_web = 1
```
Los pendientes de kits inactivos o no-web se marcaron como atendidos en `CAMBIOS_ARTICULOS_KIT` (`version_enviada = version_actual`) para que no siguieran bloqueando al sincronizador con reintentos que iban a fallar siempre por la misma razón.

### Carga inicial de stock

**Todavía en proceso — no completada.** Reglas ya cerradas para cuando se haga:

- Consulta de pendientes: `INNER JOIN ARTICULOS` + `LEFT JOIN STOCK` + `ISNULL(S.sto_cantidad, 0)`, filtrando `A.art_kit = 0` y `A.llevar_web = 1` (secciones 8, 17-19).
- Los kits no sincronizan stock físico propio.
- `llevar_web = 0` no se sincroniza y no se marca artificialmente como enviado; si más adelante cambia a `1`, el pendiente vuelve a entrar automáticamente y se envía el stock **actual** en ese momento.
- Un `DELETE` defensivo en `STOCK` se interpreta como cantidad `0`.
- Se verificó que actualmente no existen valores de `sto_cantidad < 0`; `StockSync` exige `cantidad >= 0`.

No se documenta acá una carga masiva de stock como completada porque, al momento de escribir esta guía, todavía no se terminó.

## 23. Verificaciones finales

### Consultas de pendientes en SQL Server

```sql
-- CAMBIOS_ARTICULOS
SELECT * FROM CAMBIOS_ARTICULOS WHERE version_actual > version_enviada ORDER BY art_cod;

-- CAMBIOS_ARTICULOS_KIT
SELECT * FROM CAMBIOS_ARTICULOS_KIT WHERE version_actual > version_enviada ORDER BY art_codkit;

-- CAMBIOS_STOCK
SELECT * FROM CAMBIOS_STOCK WHERE version_actual > version_enviada ORDER BY art_cod;
```

**Importante**: estas consultas pueden devolver filas aunque el sincronizador esté funcionando correctamente. Un pendiente puede ser:
- **procesable**: el sincronizador debería tomarlo en la próxima ejecución;
- **excluido por regla de negocio**, y por lo tanto va a quedar "pendiente" indefinidamente a propósito, especialmente:
  - artículos/kits/stock con `llevar_web = 0` (no se sincronizan ni se marcan como enviados, sección 18);
  - stock de artículos con `art_kit = 1` (los kits no tienen stock físico propio, sección 17).

No basta con afirmar "0 pendientes" o "hay pendientes" sin distinguir estos dos casos — conviene cruzar cada pendiente con `ARTICULOS.art_estado`, `ARTICULOS.llevar_web` y `ARTICULOS.art_kit` antes de decidir si es un problema real.

### Otras verificaciones

- `GET /api/categorias` y `GET /api/articulos` devuelven datos coherentes con lo recién sincronizado.
- Las imágenes se ven correctamente (Cloudinary o el placeholder `sin-imagen.svg` cuando corresponde).
- El panel administrativo (`/frontend/admin-imagenes.html`) permite buscar un artículo, ver su imagen actual, subir una nueva, y cambiar el switch "Mostrar en web".
- Cambiar `mostrar_web` desde el panel se refleja correctamente en el catálogo público (`GET /api/articulos`).
- SQL Server sigue funcionando de forma completamente local: las ventas y la facturación no dependen de que el sincronizador ni Internet estén disponibles.
- SQL Server no está expuesto públicamente; el puerto 1433 no está abierto hacia Internet.
