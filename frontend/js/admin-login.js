// Pantalla de ingreso al panel. La contraseña viaja una sola vez por HTTPS al servidor,
// que responde con una cookie de sesión HttpOnly; aquí no se guarda nada.

const formLoginUI = document.getElementById("form-login");
const inputUsuarioUI = document.getElementById("login-usuario");
const inputPasswordUI = document.getElementById("login-password");
const btnIngresarUI = document.getElementById("btn-ingresar");
const errorLoginUI = document.getElementById("login-error");

const PANEL_DESTINO = "/admin/imagenes";

function mostrarErrorLogin(texto) {
    errorLoginUI.textContent = texto;
    errorLoginUI.hidden = false;
}

formLoginUI.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    errorLoginUI.hidden = true;
    btnIngresarUI.disabled = true;
    btnIngresarUI.textContent = "Ingresando...";

    try {
        const respuesta = await fetch("/api/admin/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            credentials: "same-origin",
            body: JSON.stringify({
                usuario: inputUsuarioUI.value,
                password: inputPasswordUI.value,
            }),
        });

        if (respuesta.ok) {
            window.location.replace(PANEL_DESTINO);
            return;
        }

        const cuerpo = await respuesta.json().catch(() => ({}));
        if (typeof cuerpo.detail === "string") {
            mostrarErrorLogin(cuerpo.detail);
        } else if (respuesta.status === 422) {
            mostrarErrorLogin("Completá el usuario y la contraseña.");
        } else {
            mostrarErrorLogin("No se pudo iniciar sesión. Probá de nuevo.");
        }
        inputPasswordUI.value = "";
        inputPasswordUI.focus();
    } catch (error) {
        mostrarErrorLogin("No hay conexión con el servidor. Probá de nuevo.");
    } finally {
        btnIngresarUI.disabled = false;
        btnIngresarUI.textContent = "Ingresar";
    }
});

// Si ya hay una sesión vigente, entra directo al panel
fetch("/api/admin/sesion", { credentials: "same-origin" })
    .then((respuesta) => {
        if (respuesta.ok) window.location.replace(PANEL_DESTINO);
    })
    .catch(() => {});
