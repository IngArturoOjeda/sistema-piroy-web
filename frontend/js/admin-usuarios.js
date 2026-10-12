// Pantalla de usuarios del panel.
// - Cualquier usuario: cambiar su propia contraseña.
// - Administrador: crear usuarios, activar/desactivar, dar o quitar el rol de administrador
//   y restablecer contraseñas. El servidor vuelve a verificar todo (esto es solo la interfaz).
// Todo texto que viene del servidor se escribe con textContent, nunca con innerHTML.

const seccionGestionUI = document.getElementById("seccion-gestion");
const listaUsuariosUI = document.getElementById("lista-usuarios");
const estadoUsuariosUI = document.getElementById("estado-usuarios");
const formRestablecerUI = document.getElementById("form-restablecer");
const tituloRestablecerUI = document.getElementById("titulo-restablecer");

let usuarioActual = null;         // {usuario, es_admin} de la sesión
let usuarioAReestablecer = null;  // fila elegida para cambiarle la contraseña

function mostrarEstado(elemento, clase, texto) {
    elemento.className = `estado-subida visible ${clase}`;
    elemento.textContent = texto;
}

function ocultarEstado(elemento) {
    elemento.className = "estado-subida";
    elemento.textContent = "";
}

// FastAPI devuelve "detail" como texto o como lista (errores 422 de validación)
async function mensajeDeError(respuesta, porDefecto) {
    const cuerpo = await respuesta.json().catch(() => ({}));
    if (typeof cuerpo.detail === "string") return cuerpo.detail;
    if (Array.isArray(cuerpo.detail)) return "Revisá los datos ingresados.";
    return porDefecto;
}

function enviarJson(url, metodo, cuerpo) {
    return fetchAdmin(url, {
        method: metodo,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(cuerpo),
    });
}

function formatearFecha(iso) {
    if (!iso) return "Nunca";
    return new Date(iso).toLocaleString("es-PY", { dateStyle: "short", timeStyle: "short" });
}

// ---------- Mi contraseña ----------

document.getElementById("form-mi-password").addEventListener("submit", async (evento) => {
    evento.preventDefault();
    const estado = document.getElementById("estado-mi-password");
    const actual = document.getElementById("mi-actual");
    const nueva = document.getElementById("mi-nueva");
    const repetir = document.getElementById("mi-repetir");
    const boton = document.getElementById("btn-mi-password");

    if (nueva.value !== repetir.value) {
        mostrarEstado(estado, "estado-error", "La contraseña nueva y su repetición no coinciden.");
        return;
    }
    boton.disabled = true;
    mostrarEstado(estado, "estado-subiendo", "Guardando...");
    try {
        const respuesta = await enviarJson("/api/admin/mi-password", "POST",
            { actual: actual.value, nueva: nueva.value });
        if (!respuesta.ok) {
            mostrarEstado(estado, "estado-error", await mensajeDeError(respuesta, "No se pudo cambiar la contraseña."));
            return;
        }
        actual.value = nueva.value = repetir.value = "";
        mostrarEstado(estado, "estado-exito", "Contraseña cambiada.");
    } catch (error) {
        mostrarEstado(estado, "estado-error", error.message);
    } finally {
        boton.disabled = false;
    }
});

// ---------- Lista de usuarios (administrador) ----------

function crearBoton(texto, alHacerClick, deshabilitado = false) {
    const boton = document.createElement("button");
    boton.type = "button";
    boton.className = "btn-secundario btn-accion";
    boton.textContent = texto;
    boton.disabled = deshabilitado;
    boton.addEventListener("click", alHacerClick);
    return boton;
}

function crearCelda(texto, etiqueta) {
    const celda = document.createElement("td");
    celda.dataset.etiqueta = etiqueta;
    celda.textContent = texto;
    return celda;
}

function dibujarUsuarios(usuarios) {
    listaUsuariosUI.replaceChildren();
    for (const u of usuarios) {
        const soyYo = u.usuario === usuarioActual.usuario;
        const fila = document.createElement("tr");
        if (!u.activo) fila.className = "usuario-inactivo";

        const estado = u.activo ? (u.bloqueado ? "Activo (bloqueado por intentos)" : "Activo") : "Inactivo";
        fila.append(
            crearCelda(u.usuario + (soyYo ? " (vos)" : ""), "Usuario"),
            crearCelda(u.es_admin ? "Administrador" : "Común", "Rol"),
            crearCelda(estado, "Estado"),
            crearCelda(formatearFecha(u.ultimo_acceso), "Último acceso"),
        );

        const acciones = document.createElement("td");
        acciones.className = "celda-acciones";
        acciones.append(
            crearBoton(u.activo ? "Desactivar" : "Activar",
                () => cambiarUsuario(u, { activo: !u.activo }), soyYo && u.activo),
            crearBoton(u.es_admin ? "Quitar administrador" : "Hacer administrador",
                () => cambiarUsuario(u, { es_admin: !u.es_admin }), soyYo && u.es_admin),
        );
        if (!soyYo) acciones.append(crearBoton("Nueva contraseña", () => abrirRestablecer(u)));
        fila.append(acciones);
        listaUsuariosUI.append(fila);
    }
}

async function cargarUsuarios() {
    mostrarEstado(estadoUsuariosUI, "estado-subiendo", "Cargando usuarios...");
    try {
        const respuesta = await fetchAdmin("/api/admin/usuarios");
        if (!respuesta.ok) {
            mostrarEstado(estadoUsuariosUI, "estado-error", await mensajeDeError(respuesta, "No se pudo cargar la lista."));
            return false;
        }
        dibujarUsuarios(await respuesta.json());
        ocultarEstado(estadoUsuariosUI);
        return true;
    } catch (error) {
        mostrarEstado(estadoUsuariosUI, "estado-error", error.message);
        return false;
    }
}

async function cambiarUsuario(usuario, cambio) {
    if (cambio.activo === false &&
        !confirm(`¿Desactivar a "${usuario.usuario}"? Se cierran sus sesiones y ya no podrá entrar.`)) {
        return;
    }
    try {
        const respuesta = await enviarJson(`/api/admin/usuarios/${usuario.id}`, "PATCH", cambio);
        if (!respuesta.ok) {
            mostrarEstado(estadoUsuariosUI, "estado-error", await mensajeDeError(respuesta, "No se pudo guardar el cambio."));
            return;
        }
        await cargarUsuarios();
    } catch (error) {
        mostrarEstado(estadoUsuariosUI, "estado-error", error.message);
    }
}

// ---------- Crear usuario ----------

document.getElementById("form-usuario-nuevo").addEventListener("submit", async (evento) => {
    evento.preventDefault();
    const estado = document.getElementById("estado-usuario-nuevo");
    const nombre = document.getElementById("nuevo-usuario");
    const clave = document.getElementById("nuevo-password");
    const esAdmin = document.getElementById("nuevo-es-admin");
    const boton = document.getElementById("btn-crear-usuario");

    boton.disabled = true;
    mostrarEstado(estado, "estado-subiendo", "Creando...");
    try {
        const respuesta = await enviarJson("/api/admin/usuarios", "POST",
            { usuario: nombre.value, password: clave.value, es_admin: esAdmin.checked });
        if (!respuesta.ok) {
            mostrarEstado(estado, "estado-error", await mensajeDeError(respuesta, "No se pudo crear el usuario."));
            return;
        }
        const creado = await respuesta.json();
        nombre.value = clave.value = "";
        esAdmin.checked = false;
        mostrarEstado(estado, "estado-exito", `Usuario "${creado.usuario}" creado.`);
        await cargarUsuarios();
    } catch (error) {
        mostrarEstado(estado, "estado-error", error.message);
    } finally {
        boton.disabled = false;
    }
});

// ---------- Restablecer la contraseña de otro usuario ----------

function abrirRestablecer(usuario) {
    usuarioAReestablecer = usuario;
    tituloRestablecerUI.textContent = `Nueva contraseña para "${usuario.usuario}"`;
    ocultarEstado(document.getElementById("estado-restablecer"));
    formRestablecerUI.hidden = false;
    const campo = document.getElementById("restablecer-password");
    campo.value = "";
    campo.focus();
    formRestablecerUI.scrollIntoView({ behavior: "smooth", block: "center" });
}

function cerrarRestablecer() {
    usuarioAReestablecer = null;
    document.getElementById("restablecer-password").value = "";
    formRestablecerUI.hidden = true;
}

document.getElementById("btn-cancelar-restablecer").addEventListener("click", cerrarRestablecer);

formRestablecerUI.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    if (!usuarioAReestablecer) return;
    const estado = document.getElementById("estado-restablecer");
    const boton = document.getElementById("btn-restablecer");
    boton.disabled = true;
    mostrarEstado(estado, "estado-subiendo", "Guardando...");
    try {
        const respuesta = await enviarJson(`/api/admin/usuarios/${usuarioAReestablecer.id}/password`, "POST",
            { password: document.getElementById("restablecer-password").value });
        if (!respuesta.ok) {
            mostrarEstado(estado, "estado-error", await mensajeDeError(respuesta, "No se pudo cambiar la contraseña."));
            return;
        }
        const nombre = usuarioAReestablecer.usuario;
        cerrarRestablecer();
        if (await cargarUsuarios()) {
            mostrarEstado(estadoUsuariosUI, "estado-exito",
                `Contraseña de "${nombre}" cambiada; sus sesiones se cerraron.`);
        }
    } catch (error) {
        mostrarEstado(estado, "estado-error", error.message);
    } finally {
        boton.disabled = false;
    }
});

document.getElementById("btn-recargar-usuarios").addEventListener("click", cargarUsuarios);

// ---------- Arranque ----------

promesaSesionAdmin.then((sesion) => {
    usuarioActual = sesion;
    if (sesion && sesion.es_admin) {
        seccionGestionUI.hidden = false;
        cargarUsuarios();
    }
});
