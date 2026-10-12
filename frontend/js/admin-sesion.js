// Sesión del panel de administración (compartido por admin-imagenes y admin-banners).
// La sesión vive en una cookie HttpOnly que pone el servidor al iniciar sesión: este código
// nunca ve ni guarda la contraseña ni el token.

const URL_LOGIN_ADMIN = "/frontend/admin-login.html";

function irAlLogin() {
    window.location.replace(URL_LOGIN_ADMIN);
}

// fetch con la cookie de sesión; si el servidor dice 401 (sesión vencida) vuelve al login
async function fetchAdmin(url, opciones = {}) {
    const respuesta = await fetch(url, { ...opciones, credentials: "same-origin" });
    if (respuesta.status === 401) {
        irAlLogin();
        throw new Error("Tu sesión venció. Volvé a iniciar sesión.");
    }
    return respuesta;
}

// Solo se sale al login si el servidor confirmó el cierre: si falló, la sesión sigue abierta
// (y el login volvería a entrar solo), así que se avisa para reintentar.
async function cerrarSesionAdmin() {
    try {
        const respuesta = await fetch("/api/admin/logout", { method: "POST", credentials: "same-origin" });
        if (respuesta.ok) {
            irAlLogin();
            return;
        }
    } catch (error) {
        // cae al aviso de abajo
    }
    alert("No se pudo cerrar la sesión. Probá de nuevo.");
}

// Al abrir el panel: sin sesión vigente va directo al login; con sesión muestra quién es.
async function comprobarSesionAdmin() {
    const etiqueta = document.getElementById("admin-usuario");
    const boton = document.getElementById("btn-salir");
    if (boton) boton.addEventListener("click", cerrarSesionAdmin);
    try {
        const respuesta = await fetch("/api/admin/sesion", { credentials: "same-origin" });
        if (respuesta.status === 401) {
            irAlLogin();
            return;
        }
        if (respuesta.ok && etiqueta) {
            const datos = await respuesta.json();
            etiqueta.textContent = datos.usuario;
        }
    } catch (error) {
        // sin conexión: el panel muestra sus propios errores al operar
    }
}

comprobarSesionAdmin();
