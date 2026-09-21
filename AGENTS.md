# AGENTS.md

## Propósito

Reglas de trabajo para cualquier agente de IA que modifique este repositorio.

Antes de escribir código, leer también:
- `ARCHITECTURE.md`
- `ROADMAP.md`

## Forma de trabajo

1. Trabajar paso a paso.
2. No implementar varias etapas grandes al mismo tiempo.
3. Antes de cambiar código, explicar brevemente qué se va a modificar.
4. No inventar nombres de tablas, columnas o endpoints no confirmados.
5. Si falta información del sistema VFP o SQL Server, pedirla primero.
6. Mantener compatibilidad con Visual FoxPro 9 + SQL Server.
7. No reescribir el sistema local.
8. No exponer SQL Server directamente a Internet.
9. No abrir públicamente el puerto 1433.
10. No hacer que una venta local dependa de Internet.
11. No ejecutar llamadas HTTP desde triggers SQL Server.
12. Usar variables de entorno para credenciales y secretos.
13. Nunca subir credenciales reales a Git.
14. Implementar y probar una etapa antes de continuar.
15. Priorizar simplicidad, seguridad, idempotencia y recuperación ante fallos.

## Stack

### Sistema local
- Visual FoxPro 9.0
- SQL Server
- Dos equipos en red local
- Un equipo actúa como SQL Server + punto de venta
- El segundo equipo es punto de venta conectado por LAN

### E-commerce
- Python
- FastAPI
- Uvicorn
- HTML
- CSS
- JavaScript
- PostgreSQL
- Render como plataforma cloud prevista para producción

## Responsabilidades

### SQL Server
Fuente principal de:
- stock real
- artículos operativos
- tipos de artículos
- precios base
- activo/inactivo
- ventas locales
- pedidos web ya recibidos por el negocio

### PostgreSQL
Base utilizada por el e-commerce:
- artículos destinados a web
- categorías/tipos necesarios
- stock web
- datos comerciales web
- promociones web
- pedidos generados por clientes
- publicación web

### Sincronizador Python
Puente entre SQL Server local y FastAPI/PostgreSQL en Render.

Debe:
- leer cambios pendientes de SQL Server;
- enviarlos por HTTPS a FastAPI;
- descargar pedidos pendientes;
- insertarlos en SQL Server;
- manejar reintentos sin perder información.

## Regla final de acceso a bases

El backend actual todavía tiene rutas que consultan SQL Server porque el proyecto nació en localhost.

La arquitectura objetivo es:

```text
backend/app -> PostgreSQL
sincronizador/ -> SQL Server
```

Los endpoints públicos del ecommerce NO deben consultar SQL Server.

## Código actual confirmado

Actualmente existen:
- `backend/app/database.py` -> SQL Server con pyodbc
- `backend/app/database_postgres.py` -> PostgreSQL con psycopg
- `backend/app/routers/categories.py`
- `backend/app/routers/items.py`
- `backend/app/routers/promos.py`
- `backend/app/schemas.py`
- `frontend/js/main.js`

Los routers de categorías, artículos y promociones todavía usan `backend.app.database`, por lo tanto consultan SQL Server.

## Reglas para pedidos

El frontend actual envía:
- id/art_cod
- nombre
- precio
- cantidad

Regla de seguridad:
- confiar en `id/art_cod` y `cantidad` después de validarlos;
- NO confiar en `nombre` ni `precio` enviados por el navegador;
- FastAPI debe consultar PostgreSQL y obtener allí nombre/precio oficiales.

## Artículos web

SQL Server debe tener un indicador equivalente a:

```text
llevar_web
```

- `0`: no participa del ecommerce.
- `1`: puede sincronizarse a PostgreSQL.

Todo artículo nuevo debería comenzar con `llevar_web = 0`.

PostgreSQL debe tener un campo distinto:

```text
mostrar_web
```

Este controla si el artículo ya sincronizado se muestra públicamente.

## Render

La idea es usar Render para:
- FastAPI/Uvicorn;
- aplicación web;
- PostgreSQL administrado.

El sincronizador NO se ejecutará en Render. Correrá dentro de la agroveterinaria y se comunicará hacia Render mediante HTTPS.

## Seguridad de secretos

Nunca copiar secretos reales a:
- archivos Markdown;
- `.env.example`;
- Git;
- logs;
- mensajes públicos.

`.env.example` debe contener solo valores ficticios.

## Estado actual

Ya está probado en SQL Server:
- tabla `CAMBIOS_STOCK`;
- trigger sobre `STOCK`;
- incremento de `version_actual`;
- `version_enviada`;
- consulta de pendientes con `version_actual > version_enviada`.

Antes de continuar con cambios grandes, revisar `ARCHITECTURE.md` y `ROADMAP.md`.
