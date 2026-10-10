// Panel de banners del carrusel.
// Usa /api/admin/banners (protegido con X-Admin-Key). Todo texto que viene del
// servidor se escribe con textContent / propiedades del DOM, nunca con innerHTML.

// 1. CAPTURA DE ELEMENTOS
const formBannerUI = document.getElementById("form-banner");
const inputArchivoUI = document.getElementById("banner-archivo");
const previewUI = document.getElementById("banner-preview");
const inputAltUI = document.getElementById("banner-alt");
const btnSubirUI = document.getElementById("banner-btn-subir");
const estadoSubidaUI = document.getElementById("banner-estado-subida");
const estadoListaUI = document.getElementById("banners-estado-lista");
const listaBannersUI = document.getElementById("lista-banners");

const TAMANO_MAXIMO_BYTES = 5 * 1024 * 1024; // igual que el backend
const TIPOS_PERMITIDOS = ["image/jpeg", "image/png", "image/webp"];

// 2. CLAVE DE ADMINISTRADOR: solo en memoria, nunca en sessionStorage/localStorage
// Misma solución temporal que admin-imagenes.js (hasta tener login real).
let claveAdminEnMemoria = null;

function obtenerClaveAdmin() {
    if (!claveAdminEnMemoria) {
        const ingresada = prompt("Ingresá la clave de administrador:");
        if (ingresada && ingresada.trim()) {
            claveAdminEnMemoria = ingresada.trim();
        }
    }
    return claveAdminEnMemoria;
}

async function fetchAdmin(url, opciones = {}) {
    const clave = obtenerClaveAdmin();
    if (!clave) {
        throw new Error("Se necesita la clave de administrador para continuar.");
    }

    const headers = { ...(opciones.headers || {}), "X-Admin-Key": clave };
    const respuesta = await fetch(url, { ...opciones, headers });

    if (respuesta.status === 401) {
        claveAdminEnMemoria = null; // la próxima operación la vuelve a pedir
        throw new Error("Clave de administrador incorrecta.");
    }
    return respuesta;
}

// FastAPI devuelve "detail" como texto o como lista (errores 422 de validación)
async function mensajeDeError(respuesta, porDefecto) {
    const cuerpo = await respuesta.json().catch(() => ({}));
    if (typeof cuerpo.detail === "string") return cuerpo.detail;
    if (Array.isArray(cuerpo.detail)) return "Revisá los datos ingresados.";
    return porDefecto;
}

function mostrarEstado(elemento, clase, texto) {
    elemento.className = `estado-subida visible ${clase}`;
    elemento.textContent = texto;
}

// 3. LISTA DE BANNERS
async function cargarBanners() {
    estadoListaUI.textContent = "Cargando...";
    try {
        const respuesta = await fetchAdmin("/api/admin/banners");
        if (!respuesta.ok) {
            estadoListaUI.textContent = await mensajeDeError(respuesta, "No se pudieron cargar los banners.");
            return;
        }
        dibujarBanners(await respuesta.json());
    } catch (error) {
        estadoListaUI.textContent = error.message;
    }
}

function dibujarBanners(banners) {
    listaBannersUI.replaceChildren();
    banners.forEach(banner => listaBannersUI.appendChild(crearFilaBanner(banner)));
    actualizarContador();
    actualizarBotonesMover();
}

function actualizarContador() {
    const total = listaBannersUI.children.length;
    estadoListaUI.textContent = total === 0
        ? "Todavía no hay banners cargados."
        : `${total} banner(s). Solo los activos se ven en la tienda.`;
}

// Agrega un banner recién subido al final (el servidor lo creó con el último
// orden) sin redibujar la lista: así no se pierden ediciones sin guardar.
function insertarFilaBanner(banner) {
    listaBannersUI.appendChild(crearFilaBanner(banner));
    actualizarContador();
    actualizarBotonesMover();
}

function crearFilaBanner(banner) {
    const li = document.createElement("li");
    li.className = "banner-item";
    li.dataset.id = banner.id;

    const img = document.createElement("img");
    img.className = "banner-miniatura";
    img.src = banner.imagen_url;
    img.alt = banner.alt;
    img.loading = "lazy";

    const cuerpo = document.createElement("div");
    cuerpo.className = "banner-cuerpo";

    const campoAlt = document.createElement("label");
    campoAlt.className = "campo-banner";
    const tituloAlt = document.createElement("span");
    tituloAlt.textContent = "Texto alternativo";
    const inputAlt = document.createElement("input");
    inputAlt.type = "text";
    inputAlt.maxLength = 500;
    inputAlt.value = banner.alt;
    campoAlt.append(tituloAlt, inputAlt);

    const filaMover = document.createElement("div");
    filaMover.className = "banner-mover";
    const btnSubir = document.createElement("button");
    btnSubir.type = "button";
    btnSubir.className = "btn-secundario btn-mover btn-mover-subir";
    btnSubir.textContent = "▲ Subir";
    const btnBajar = document.createElement("button");
    btnBajar.type = "button";
    btnBajar.className = "btn-secundario btn-mover btn-mover-bajar";
    btnBajar.textContent = "▼ Bajar";
    filaMover.append(btnSubir, btnBajar);

    const filaSwitch = document.createElement("label");
    filaSwitch.className = "fila-switch banner-activo";
    const textoSwitch = document.createElement("span");
    textoSwitch.textContent = "Activo (visible en la tienda)";
    const contenedorSwitch = document.createElement("span");
    contenedorSwitch.className = "switch";
    const checkActivo = document.createElement("input");
    checkActivo.type = "checkbox";
    checkActivo.checked = banner.activo;
    const slider = document.createElement("span");
    slider.className = "switch-slider";
    contenedorSwitch.append(checkActivo, slider);
    filaSwitch.append(textoSwitch, contenedorSwitch);

    const botones = document.createElement("div");
    botones.className = "banner-botones";
    const btnGuardar = document.createElement("button");
    btnGuardar.type = "button";
    btnGuardar.className = "btn-subir-imagen";
    btnGuardar.textContent = "Guardar texto";
    const btnBorrar = document.createElement("button");
    btnBorrar.type = "button";
    btnBorrar.className = "btn-borrar-banner";
    btnBorrar.textContent = "Borrar";
    botones.append(btnGuardar, btnBorrar);

    const estado = document.createElement("p");
    estado.className = "estado-subida";
    estado.setAttribute("role", "status");

    cuerpo.append(campoAlt, filaMover, filaSwitch, botones, estado);
    li.append(img, cuerpo);

    btnGuardar.addEventListener("click", () =>
        guardarCambios(banner.id, { alt: inputAlt.value.trim() }, [btnGuardar, btnBorrar], estado));
    checkActivo.addEventListener("change", () =>
        alternarActivo(banner.id, checkActivo, estado));
    btnBorrar.addEventListener("click", () =>
        borrarBanner(banner.id, [btnGuardar, btnBorrar, checkActivo], estado, li));
    btnSubir.addEventListener("click", () => moverBanner(li, -1, btnSubir));
    btnBajar.addEventListener("click", () => moverBanner(li, 1, btnBajar));

    return li;
}

// 4. CAMBIOS (PATCH)
async function enviarPatch(id, datos) {
    return fetchAdmin(`/api/admin/banners/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(datos),
    });
}

async function guardarCambios(id, datos, controles, estado) {
    if (!datos.alt) {
        mostrarEstado(estado, "estado-error", "El texto alternativo no puede estar vacío.");
        return;
    }

    controles.forEach(c => { c.disabled = true; });
    mostrarEstado(estado, "estado-subiendo", "Guardando...");
    try {
        const respuesta = await enviarPatch(id, datos);
        if (!respuesta.ok) {
            mostrarEstado(estado, "estado-error", await mensajeDeError(respuesta, "No se pudo guardar."));
            return;
        }
        mostrarEstado(estado, "estado-exito", "Guardado.");
    } catch (error) {
        mostrarEstado(estado, "estado-error", error.message);
    } finally {
        controles.forEach(c => { c.disabled = false; });
    }
}

async function alternarActivo(id, checkbox, estado) {
    const nuevoValor = checkbox.checked;
    checkbox.disabled = true;
    mostrarEstado(estado, "estado-subiendo", "Guardando...");
    try {
        const respuesta = await enviarPatch(id, { activo: nuevoValor });
        if (!respuesta.ok) {
            checkbox.checked = !nuevoValor;
            mostrarEstado(estado, "estado-error", await mensajeDeError(respuesta, "No se pudo cambiar el estado."));
            return;
        }
        mostrarEstado(estado, "estado-exito", nuevoValor ? "Banner activo." : "Banner oculto.");
    } catch (error) {
        checkbox.checked = !nuevoValor;
        mostrarEstado(estado, "estado-error", error.message);
    } finally {
        checkbox.disabled = false;
    }
}

// 4b. SUBIR / BAJAR (PUT /api/admin/banners/orden con la lista completa de ids)
let reordenando = false;

// Habilita o deshabilita ▲ ▼ según la posición (el primero no sube, el último no baja)
function actualizarBotonesMover() {
    const filas = [...listaBannersUI.children];
    filas.forEach((fila, i) => {
        fila.querySelector(".btn-mover-subir").disabled = reordenando || i === 0;
        fila.querySelector(".btn-mover-bajar").disabled = reordenando || i === filas.length - 1;
    });
}

// Vuelve al orden anterior sin revivir filas borradas ni perder las agregadas
// mientras se esperaba la respuesta del servidor.
function restaurarOrden(antes) {
    const agregadas = [...listaBannersUI.children].filter(li => !antes.includes(li));
    listaBannersUI.replaceChildren(...antes.filter(li => li.isConnected), ...agregadas);
}

async function moverBanner(fila, delta, boton) {
    if (reordenando) return;

    const antes = [...listaBannersUI.children];
    const destino = antes.indexOf(fila) + delta;
    if (destino < 0 || destino >= antes.length) return;

    // Se mueve la fila en pantalla de inmediato; si el servidor falla, se revierte
    // con los mismos elementos (no se pierden ediciones sin guardar).
    const referencia = delta < 0 ? antes[destino] : antes[destino].nextSibling;
    listaBannersUI.insertBefore(fila, referencia);

    reordenando = true;
    actualizarBotonesMover();
    estadoListaUI.textContent = "Guardando el orden...";

    try {
        const ids = [...listaBannersUI.children].map(li => Number(li.dataset.id));
        const respuesta = await fetchAdmin("/api/admin/banners/orden", {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ ids }),
        });
        if (!respuesta.ok) {
            restaurarOrden(antes);
            estadoListaUI.textContent = await mensajeDeError(respuesta, "No se pudo guardar el orden.");
            return;
        }
        actualizarContador();
    } catch (error) {
        restaurarOrden(antes);
        estadoListaUI.textContent = error.message;
    } finally {
        reordenando = false;
        actualizarBotonesMover();
        // Mantiene el foco en la fila movida (para quien usa el teclado)
        (boton.disabled ? fila.querySelector(".btn-mover:not(:disabled)") : boton)?.focus();
    }
}

// 5. BORRAR (DELETE)
async function borrarBanner(id, controles, estado, fila) {
    if (!confirm("¿Borrar este banner? También se elimina la imagen. No se puede deshacer.")) {
        return;
    }
    controles.forEach(c => { c.disabled = true; });
    mostrarEstado(estado, "estado-subiendo", "Borrando...");
    try {
        const respuesta = await fetchAdmin(`/api/admin/banners/${id}`, { method: "DELETE" });
        if (!respuesta.ok) {
            mostrarEstado(estado, "estado-error", await mensajeDeError(respuesta, "No se pudo borrar."));
            controles.forEach(c => { c.disabled = false; });
            return;
        }
        // Solo se quita esta fila: las demás conservan sus ediciones sin guardar.
        fila.remove();
        actualizarContador();
        actualizarBotonesMover();
    } catch (error) {
        mostrarEstado(estado, "estado-error", error.message);
        controles.forEach(c => { c.disabled = false; });
    }
}

// 6. SUBIR BANNER NUEVO (POST)
inputArchivoUI.addEventListener("change", () => {
    const archivo = inputArchivoUI.files[0];
    if (previewUI.dataset.urlObjeto) {
        URL.revokeObjectURL(previewUI.dataset.urlObjeto);
        delete previewUI.dataset.urlObjeto;
    }
    if (!archivo) {
        previewUI.classList.remove("visible");
        return;
    }
    const url = URL.createObjectURL(archivo);
    previewUI.dataset.urlObjeto = url;
    previewUI.src = url;
    previewUI.classList.add("visible");
});

formBannerUI.addEventListener("submit", async evento => {
    evento.preventDefault();

    const archivo = inputArchivoUI.files[0];
    const alt = inputAltUI.value.trim();

    if (!archivo) return;
    if (!TIPOS_PERMITIDOS.includes(archivo.type)) {
        mostrarEstado(estadoSubidaUI, "estado-error", "Formato no permitido. Usá jpg, png o webp.");
        return;
    }
    if (archivo.size > TAMANO_MAXIMO_BYTES) {
        mostrarEstado(estadoSubidaUI, "estado-error", "La imagen supera el máximo de 5 MB.");
        return;
    }
    if (!alt) {
        mostrarEstado(estadoSubidaUI, "estado-error", "Escribí el texto alternativo.");
        return;
    }

    btnSubirUI.disabled = true;
    mostrarEstado(estadoSubidaUI, "estado-subiendo", "Subiendo banner...");

    const formData = new FormData();
    formData.append("archivo", archivo);
    formData.append("alt", alt); // sin "orden": el servidor lo agrega al final

    try {
        const respuesta = await fetchAdmin("/api/admin/banners", { method: "POST", body: formData });
        if (!respuesta.ok) {
            mostrarEstado(estadoSubidaUI, "estado-error", await mensajeDeError(respuesta, "No se pudo subir el banner."));
            return;
        }
        const creado = await respuesta.json();
        mostrarEstado(estadoSubidaUI, "estado-exito", "Banner subido. Está oculto: activalo en la lista cuando esté listo.");
        formBannerUI.reset();
        previewUI.classList.remove("visible");
        insertarFilaBanner(creado);
    } catch (error) {
        mostrarEstado(estadoSubidaUI, "estado-error", error.message);
    } finally {
        btnSubirUI.disabled = false;
    }
});

document.getElementById("btn-recargar-banners").addEventListener("click", async evento => {
    const boton = evento.currentTarget;
    boton.disabled = true;
    try {
        await cargarBanners(); // vuelve a pedir la clave si hace falta
    } finally {
        boton.disabled = false;
    }
});

cargarBanners();
