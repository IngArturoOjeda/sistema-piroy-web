# Instalar el sincronizador en el servidor del negocio

Guía paso a paso para que el sincronizador lea la base real (`Piroy`, SQL Server 2012, instancia `DESKTOP-8TG4CTH`) y
envíe los cambios a `https://www.agrovetzo.com.py`. Se hace **una vez**, en el servidor del negocio.

Reglas que no cambian: SQL Server nunca se abre a Internet (el sincronizador solo *sale* hacia Render por HTTPS), las
ventas locales no dependen de Internet, y las claves se escriben solo en el servidor, nunca en Git ni en un chat.

## 0. Antes de empezar

Ya debe estar hecho (ver `scripts/sqlserver/` y `ROADMAP.md`, Fase 14):

- [ ] respaldo de `Piroy`;
- [ ] scripts `01`, `02`, `03` y `04` corridos, y `99_verificacion_solo_lectura.sql` mostrando `sin_fila = 0`;
- [ ] el código nuevo (`POST /api/sync/catalogos`) desplegado en Render (push a `main`).

## 1. Usuario de SQL Server para el sincronizador

En SSMS, conectado a la base `Piroy`: abrir `scripts/sqlserver/05_usuario_sincronizador.sql`, reemplazar
`CAMBIAR_ESTA_CLAVE` por una clave larga y propia, ejecutar, y **cerrar el archivo sin guardar la clave**.

Crea `agrovetzo_sync`, que solo puede leer `ARTICULOS`, `STOCK`, `ARTICULOS_KIT`, `TIPOARTICULO` y `UNIDADMEDIDA`, y
leer/actualizar las tres tablas `CAMBIOS_*`. Si SQL Server no acepta usuarios de SQL, activar el *modo mixto* en
Propiedades del servidor > Seguridad y reiniciar el servicio.

## 2. Programas en el servidor

1. **Python 3.14** (ya instalado). Probar en una consola: `python --version`.
2. **Driver ODBC**: instalar *ODBC Driver 17 for SQL Server* (descarga gratuita de Microsoft). Anotar el nombre exacto del
   driver (consola: `odbcad32` > pestaña Controladores). El driver viejo llamado `SQL Server` también existe en Windows,
   pero es mejor el 17.
3. **Carpeta de trabajo**: crear `C:\agrovetzo-sync\` y copiar adentro la carpeta `sincronizador\` del proyecto
   (contiene `__init__.py`, `database.py`, `sincronizador.py` y `requirements.txt`). No hace falta copiar nada más.
4. **Entorno de Python** (en una consola, dentro de `C:\agrovetzo-sync`):

```bat
cd /d C:\agrovetzo-sync
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r sincronizador\requirements.txt
```

Si `pip` no encuentra una versión de `pyodbc` compatible con Python 3.14, avisar (se resuelve con otra versión de Python).

## 3. Archivo `.env` (solo en el servidor)

Crear `C:\agrovetzo-sync\.env` con este contenido, reemplazando los valores. **Este archivo no se sube a Git, no se envía
por correo ni por chat.**

```text
DB_DRIVER=ODBC Driver 17 for SQL Server
DB_SERVER=localhost
DB_NAME=Piroy
DB_USER=agrovetzo_sync
DB_PASSWORD=la_clave_del_paso_1

SYNC_API_KEY=la_clave_del_sincronizador_de_render
SYNC_API_URL=https://www.agrovetzo.com.py/api/sync/articulos
SYNC_API_URL_KITS=https://www.agrovetzo.com.py/api/sync/articulos-kit
SYNC_API_URL_STOCK=https://www.agrovetzo.com.py/api/sync/stock
SYNC_API_URL_CATALOGOS=https://www.agrovetzo.com.py/api/sync/catalogos
```

- `DB_SERVER=localhost` sirve si el sincronizador corre en la misma máquina que SQL Server. Si la instancia es con nombre,
  usar `localhost\NOMBREINSTANCIA`.
- `SYNC_API_KEY` es la misma que está en el panel de Render (servicio `agrovetzo-web` > Environment). Cópiala de allí
  directamente al archivo; no la pegues en ningún otro lado.

## 4. Prueba de conexión (no envía nada)

```bat
cd /d C:\agrovetzo-sync
.venv\Scripts\python.exe -c "from sincronizador.database import obtener_conexion as c; k=c(); r=k.cursor(); r.execute('SELECT DB_NAME(), COUNT(*) FROM ARTICULOS'); print(r.fetchone())"
```

Debe imprimir `('Piroy', 1715)` (o la cantidad actual). Si falla: revisar nombre del driver, usuario y clave, y que el
servicio *SQL Server* acepte conexiones locales.

## 5. Primera sincronización (manual y vigilada)

1. **Despertar la web**: abrir `https://www.agrovetzo.com.py` en el navegador y esperar a que cargue. El plan gratuito de
   Render se duerme y la primera respuesta tarda; el sincronizador espera 15 segundos por pedido y se detiene tras 3
   fallos de conexión seguidos.
2. Ejecutar:

```bat
cd /d C:\agrovetzo-sync
.venv\Scripts\python.exe -m sincronizador.sincronizador
```

3. Verá primero `Tipos y unidades al día`, luego los artículos (`[n/1715] ... OK`), los kits y el stock. Son más de mil
   envíos; puede tardar varios minutos. Si se corta, **se vuelve a ejecutar sin riesgo**: continúa con lo pendiente.
4. Al final: correr `99_verificacion_solo_lectura.sql`; los *pendientes* deben ser 0 (salvo cambios nuevos) y revisar la
   tienda en `https://www.agrovetzo.com.py`.

Errores comunes: `401` = `SYNC_API_KEY` distinta de la de Render; `422 ... no existe en tipo_articulo/unidad_medida` =
el paso de tipos y unidades no llegó (revisar `SYNC_API_URL_CATALOGOS`); `Falta configurar la variable de entorno: X` =
falta esa línea en el `.env`.

## 6. Ejecutarlo solo cada pocos minutos

Crear `C:\agrovetzo-sync\ejecutar_sincronizador.bat`:

```bat
@echo off
cd /d C:\agrovetzo-sync
echo ===== %date% %time% >> sincronizador.log
.venv\Scripts\python.exe -m sincronizador.sincronizador >> sincronizador.log 2>&1
```

Programarlo (consola como administrador):

```bat
schtasks /Create /TN "AGRO-VETZO Sincronizador" /TR "C:\agrovetzo-sync\ejecutar_sincronizador.bat" /SC MINUTE /MO 5 /RU SYSTEM /F
```

Luego, en el *Programador de tareas* > propiedades de la tarea > Configuración, verificar que diga **No iniciar una
instancia nueva** si ya se está ejecutando. Revisar `sincronizador.log` los primeros días. Si el servidor se apaga, al
volver a encenderse la tarea retoma lo pendiente: nada se pierde.

## 7. Comprobar que funciona de punta a punta

1. **Stock**: hacer una venta de prueba (o un ajuste) de un artículo; en 5 minutos debe verse el stock nuevo en la web.
2. **Artículo**: cambiar el precio de un artículo de prueba; en 5 minutos debe verse en la web.
3. **Sin Internet**: desconectar la red un momento y hacer una venta: la venta no se ve afectada; al volver la red, el
   cambio llega solo.

## 8. Después de la instalación

- Quitar la copia de pruebas: **no** correr más el sincronizador desde la PC de desarrollo contra Render.
- Cuando el servicio de Render sea de pago (o se duerma menos), conviene subir `TIMEOUT_SEGUNDOS` solo si aparecen
  errores de conexión.
- Borrar `ADMIN_API_KEY` de Render (ya no se usa).
