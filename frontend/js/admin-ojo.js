// Botón "ojito" de los campos de contraseña: muestra u oculta lo que se escribe.
// Uso: un <button class="btn-ojo" data-ojo-para="id-del-input"> con dos <svg>
// (.ojo-abierto y .ojo-tachado). Sirve para campos presentes o agregados después.

document.addEventListener("click", (evento) => {
    const boton = evento.target.closest(".btn-ojo");
    if (!boton) return;
    const campo = document.getElementById(boton.dataset.ojoPara);
    if (!campo) return;

    const mostrar = campo.type === "password";
    campo.type = mostrar ? "text" : "password";
    boton.setAttribute("aria-pressed", String(mostrar));
    boton.setAttribute("aria-label", mostrar ? "Ocultar contraseña" : "Mostrar contraseña");
    boton.querySelector(".ojo-abierto").hidden = mostrar;
    boton.querySelector(".ojo-tachado").hidden = !mostrar;
    campo.focus();
});
