// Panel de banners del carrusel.
// Usa /api/admin/banners (protegido con X-Admin-Key). Todo texto que viene del
// servidor se escribe con textContent / propiedades del DOM, nunca con innerHTML.

// 1. CAPTURA DE ELEMENTOS
const formBannerUI = document.getElementById("form-banner");
const inputArchivoUI = document.getElementById("banner-archivo");
const previewUI = document.getElementById("banner-preview");
const inputAltUI = document.getElementById("banner-alt");
const inputOrdenUI = document.getElementById("banner-orden");
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
}

function actualizarContador() {
    const total = listaBannersUI.children.length;
    estadoListaUI.textContent = total === 0
        ? "Todavía no hay banners cargados."
        : `${total} banner(s). Solo los activos se ven en la tienda.`;
}

// Agrega un banner recién subido en su lugar (por orden, luego por id) sin
// redibujar la lista: así no se pierden ediciones sin guardar en otras filas.
function insertarFilaBanner(banner) {
    const fila = crearFilaBanner(banner);
    const siguiente = [...listaBannersUI.children].find(
        li => Number(li.dataset.orden) > banner.orden
    );
    listaBannersUI.insertBefore(fila, siguiente || null);
    actualizarContador();
}

function crearFilaBanner(banner) {
    const li = document.createElement("li");
    li.className = "banner-item";
    li.dataset.orden = banner.orden; // último orden guardado en el servidor

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

    const campoOrden = document.createElement("label");
    campoOrden.className = "campo-banner campo-orden";
    const tituloOrden = document.createElement("span");
    tituloOrden.textContent = "Orden";
    const inputOrden = document.createElement("input");
    inputOrden.type = "number";
    inputOrden.min = "0";
    inputOrden.max = "2147483647";
    inputOrden.value = banner.orden;
    campoOrden.append(tituloOrden, inputOrden);

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
    btnGuardar.textContent = "Guardar texto y orden";
    const btnBorrar = document.createElement("button");
    btnBorrar.type = "button";
    btnBorrar.className = "btn-borrar-banner";
    btnBorrar.textContent = "Borrar";
    botones.append(btnGuardar, btnBorrar);

    const estado = document.createElement("p");
    estado.className = "estado-subida";
    estado.setAttribute("role", "status");

    cuerpo.append(campoAlt, campoOrden, filaSwitch, botones, estado);
    li.append(img, cuerpo);

    btnGuardar.addEventListener("click", () =>
        guardarCambios(banner.id, { alt: inputAlt.value.trim(), orden: Number(inputOrden.value) }, [btnGuardar, btnBorrar], estado, li));
    checkActivo.addEventListener("change", () =>
        alternarActivo(banner.id, checkActivo, estado));
    btnBorrar.addEventListener("click", () =>
        borrarBanner(banner.id, [btnGuardar, btnBorrar, checkActivo], estado, li));

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

async function guardarCambios(id, datos, controles, estado, fila) {
    if (!datos.alt) {
        mostrarEstado(estado, "estado-error", "El texto alternativo no puede estar vacío.");
        return;
    }
    if (!Number.isInteger(datos.orden) || datos.orden < 0) {
        mostrarEstado(estado, "estado-error", "El orden debe ser un número entero, 0 o mayor.");
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
        fila.dataset.orden = datos.orden;
        mostrarEstado(estado, "estado-exito", "Guardado. El nuevo orden se aplica al recargar la lista.");
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
    const orden = Number(inputOrdenUI.value);

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
    if (!Number.isInteger(orden) || orden < 0) {
        mostrarEstado(estadoSubidaUI, "estado-error", "El orden debe ser un número entero, 0 o mayor.");
        return;
    }

    btnSubirUI.disabled = true;
    mostrarEstado(estadoSubidaUI, "estado-subiendo", "Subiendo banner...");

    const formData = new FormData();
    formData.append("archivo", archivo);
    formData.append("alt", alt);
    formData.append("orden", String(orden));

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
