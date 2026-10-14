// Menú del panel de administración (cajón lateral con botón de hamburguesa). Es el mismo en celular, app y PC.
// El contenido del menú está en el HTML de cada pantalla; aquí solo se abre y se cierra.

(function () {
    const boton = document.getElementById("btn-menu");
    const menu = document.getElementById("menu-admin");
    const fondo = document.getElementById("menu-fondo");
    const cerrar = document.getElementById("btn-menu-cerrar");
    if (!boton || !menu) return;

    // Con el menú abierto, el resto de la página queda inactiva (sin foco de teclado ni clics): Tab no sale del menú.
    function fondoDeLaPagina() {
        return [...document.body.children].filter((el) => el !== menu && el !== fondo && el.tagName !== "SCRIPT");
    }

    function abrir() {
        fondoDeLaPagina().forEach((el) => { el.inert = true; });
        document.body.classList.add("menu-abierto");
        boton.setAttribute("aria-expanded", "true");
        cerrar.focus();
    }

    function cerrarMenu() {
        if (!document.body.classList.contains("menu-abierto")) return;
        fondoDeLaPagina().forEach((el) => { el.inert = false; });
        document.body.classList.remove("menu-abierto");
        boton.setAttribute("aria-expanded", "false");
        boton.focus();
    }

    boton.addEventListener("click", abrir);
    cerrar.addEventListener("click", cerrarMenu);
    if (fondo) fondo.addEventListener("click", cerrarMenu);
    document.addEventListener("keydown", (evento) => {
        if (evento.key === "Escape") cerrarMenu();
    });
})();
