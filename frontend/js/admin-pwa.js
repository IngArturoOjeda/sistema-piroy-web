// App instalable del panel de administración.
// - Registra el service worker (/admin/sw.js, alcance /admin/): es lo que permite que el navegador ofrezca
//   instalar el panel como una aplicación ("Abrir en aplicación" en Edge, "Instalar" en Chrome).
// - Si el navegador permite instalar, muestra el botón "Instalar app" de la cabecera (#btn-instalar); cuando la
//   app ya está instalada o se está usando como app, el botón queda oculto.

(function () {
    if ("serviceWorker" in navigator) {
        window.addEventListener("load", () => {
            navigator.serviceWorker.register("/admin/sw.js", { scope: "/admin/" }).catch((error) => {
                console.warn("No se pudo registrar el service worker del panel:", error);
            });
        });
    }

    const boton = document.getElementById("btn-instalar");
    let ofertaDeInstalacion = null;

    window.addEventListener("beforeinstallprompt", (evento) => {
        evento.preventDefault(); // en vez del aviso automático del navegador, se usa el botón de la cabecera
        ofertaDeInstalacion = evento;
        if (boton) boton.hidden = false;
    });

    if (boton) {
        boton.addEventListener("click", async () => {
            if (!ofertaDeInstalacion) return;
            ofertaDeInstalacion.prompt();
            try {
                await ofertaDeInstalacion.userChoice;
            } catch (error) {
                // el cliente cerró el cuadro: no pasa nada
            }
            ofertaDeInstalacion = null;
            boton.hidden = true;
        });
    }

    window.addEventListener("appinstalled", () => {
        ofertaDeInstalacion = null;
        if (boton) boton.hidden = true;
    });
})();
