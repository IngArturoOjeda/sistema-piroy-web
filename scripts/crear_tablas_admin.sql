-- Usuarios y sesiones del panel de administracion (PostgreSQL).
-- Idempotente: se puede ejecutar mas de una vez sin efectos.
-- Ejecutar con: python scripts/crear_tablas_admin.py   (agregar --probar para validar con rollback)
--
-- La contrasena se guarda con hash (scrypt, con sal propia); nunca en texto plano.
-- Del token de sesion solo se guarda su hash SHA-256: quien lea la base no puede usar las sesiones.

CREATE TABLE IF NOT EXISTS public.admin_usuarios (
    id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    usuario text NOT NULL
        CHECK (usuario = lower(usuario) AND length(usuario) BETWEEN 3 AND 50),
    password_hash text NOT NULL,
    activo boolean NOT NULL DEFAULT TRUE,
    intentos_fallidos integer NOT NULL DEFAULT 0,
    bloqueado_hasta timestamptz NULL,
    creado_en timestamptz NOT NULL DEFAULT now(),
    ultimo_acceso timestamptz NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS admin_usuarios_usuario_uq
    ON public.admin_usuarios (usuario);

CREATE TABLE IF NOT EXISTS public.admin_sesiones (
    id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    usuario_id integer NOT NULL
        REFERENCES public.admin_usuarios (id) ON DELETE CASCADE,
    token_hash text NOT NULL,
    creada_en timestamptz NOT NULL DEFAULT now(),
    vence_en timestamptz NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS admin_sesiones_token_uq
    ON public.admin_sesiones (token_hash);

CREATE INDEX IF NOT EXISTS admin_sesiones_usuario_idx
    ON public.admin_sesiones (usuario_id);
