// 1. CAPTURA DE ELEMENTOS
const txtBuscarAdminUI = document.getElementById("txt-buscar-admin");
const listaResultadosUI = document.getElementById("lista-resultados");
const panelDetalleUI = document.getElementById("panel-detalle");

const ANCHURA_MOVIL = 900;

// 2. CLAVE DE ADMINISTRADOR: solo en memoria, nunca en sessionStorage/localStorage
// Solución temporal hasta implementar login administrativo real.
let claveAdminEnMemoria = null;
let articuloSeleccionado = null;
let temporizadorBusqueda = null;

function esVistaMovil() {
    return window.innerWidth <= ANCHURA_MOVIL;
}

function obtenerClaveAdmin() {
    if (!claveAdminEnMemoria) {
        const ingresada = prompt("Ingresá la clave de administrador:");
        if (ingresada && ingresada.trim()) {
            claveAdminEnMemoria = ingresada.trim();
        }
    }
    return claveAdminEnMemoria;
}

// 3. FETCH CON X-Admin-Key, con manejo de 401
async function fetchAdmin(url, opciones = {}) {
    const clave = obtenerClaveAdmin();
    if (!clave) {
        throw new Error("Se necesita la clave de administrador para continuar.");
    }

    const headers = { ...(opciones.headers || {}), "X-Admin-Key": clave };
    const respuesta = await fetch(url, { ...opciones, headers });

    if (respuesta.status === 401) {
        claveAdminEnMemoria = null; // se borra: la próxima operación la vuelve a pedir
        throw new Error("Clave de administrador incorrecta.");
    }

    return respuesta;
}

// 4. BÚSQUEDA (con una pequeña espera para no disparar una petición por cada letra)
txtBuscarAdminUI.addEventListener("input", () => {
    clearTimeout(temporizadorBusqueda);
    const texto = txtBuscarAdminUI.value.trim();
    if (texto.length === 0) {
        listaResultadosUI.innerHTML = "";
        return;
    }
    temporizadorBusqueda = setTimeout(() => buscarArticulos(texto), 350);
});

async function buscarArticulos(texto) {
    try {
        const respuesta = await fetchAdmin(`/api/admin/articulos?buscar=${encodeURIComponent(texto)}`);
        if (!respuesta.ok) {
            const error = await respuesta.json().catch(() => ({}));
            alert(`Error ${respuesta.status}: ${error.detail || "No se pudo buscar"}`);
            return;
        }
        const articulos = await respuesta.json();
        dibujarResultados(articulos);
    } catch (error) {
        alert(error.message);
    }
}

function dibujarResultados(articulos) {
    listaResultadosUI.innerHTML = "";

    if (articulos.length === 0) {
        listaResultadosUI.innerHTML = "<li class='admin-detalle-vacio'>Sin coincidencias.</li>";
        return;
    }

    articulos.forEach(articulo => {
        const li = document.createElement("li");
        li.className = "resultado-item";
        const publicado = articulo.art_estado === "S" && articulo.llevar_web && articulo.mostrar_web;
        const imagenMiniatura = articulo.art_foto || "/frontend/assets/images/sin-imagen.svg";

        li.innerHTML = `
            <img class="resultado-miniatura" src="${imagenMiniatura}" alt="${articulo.art_nombre}">
            <div class="resultado-textos">
                <div class="resultado-codigo">Art. ${articulo.art_cod}</div>
                <div class="resultado-nombre">${articulo.art_nombre}</div>
                <div class="resultado-precio">PYG ${articulo.art_preciobase.toLocaleString("es-ES")}</div>
                <span class="resultado-estado ${publicado ? "estado-publicado" : "estado-no-publicado"}">
                    ${publicado ? "Publicado" : "No publicado"}
                </span>
            </div>
        `;

        li.addEventListener("click", () => seleccionarArticulo(articulo, li));
        listaResultadosUI.appendChild(li);
    });
}

// 5. SELECCIÓN Y PANEL DE DETALLE
function seleccionarArticulo(articulo, elementoLi) {
    articuloSeleccionado = articulo;

    document.querySelectorAll(".resultado-item").forEach(el => el.classList.remove("seleccionado"));
    elementoLi.classList.add("seleccionado");

    const imagenActual = articulo.art_foto || "/frontend/assets/images/sin-imagen.svg";

    panelDetalleUI.innerHTML = `
        <div class="detalle-info">
            <img class="detalle-imagen-actual" src="${imagenActual}" alt="${articulo.art_nombre}">
            <div class="detalle-texto">
                <p><strong>Código:</strong> ${articulo.art_cod}</p>
                <p><strong>Nombre:</strong> ${articulo.art_nombre}</p>
                <p class="detalle-precio">PYG ${articulo.art_preciobase.toLocaleString("es-ES")}</p>
                <p><strong>Categoría:</strong> ${articulo.tipoart_desc}</p>
            </div>
        </div>

        <div class="fila-badges">
            <span class="badge ${articulo.art_estado === "S" ? "badge-vigente" : "badge-inactivo"}">
                ${articulo.art_estado === "S" ? "Vigente" : "Inactivo"}
            </span>
            <span class="badge ${articulo.llevar_web ? "badge-si" : "badge-no"}">
                llevar_web: ${articulo.llevar_web ? "Sí" : "No"}
            </span>
            <span class="badge ${articulo.mostrar_web ? "badge-si" : "badge-no"}">
                mostrar_web: ${articulo.mostrar_web ? "Sí" : "No"}
            </span>
        </div>

        <form id="form-imagen" class="form-imagen">
            <input type="file" id="input-archivo" accept="image/jpeg,image/png,image/webp" required>
            <img id="img-preview" class="preview-nueva-imagen" alt="Vista previa">
            <button type="submit" class="btn-subir-imagen" id="btn-subir">Subir imagen</button>
            <p id="estado-subida" class="estado-subida"></p>
        </form>
    `;

    document.getElementById("input-archivo").addEventListener("change", mostrarPreviewLocal);
    document.getElementById("form-imagen").addEventListener("submit", subirImagen);

    if (esVistaMovil()) {
        panelDetalleUI.scrollIntoView({ behavior: "smooth", block: "start" });
    }
}

function mostrarPreviewLocal(evento) {
    const archivo = evento.target.files[0];
    const imgPreview = document.getElementById("img-preview");
    if (archivo) {
        imgPreview.src = URL.createObjectURL(archivo);
        imgPreview.classList.add("visible");
    } else {
        imgPreview.classList.remove("visible");
    }
}

// 6. SUBIDA DE LA IMAGEN
async function subirImagen(evento) {
    evento.preventDefault();

    const inputArchivo = document.getElementById("input-archivo");
    const btnSubir = document.getElementById("btn-subir");
    const estadoUI = document.getElementById("estado-subida");
    const archivo = inputArchivo.files[0];

    if (!archivo) return;

    btnSubir.disabled = true;
    estadoUI.className = "estado-subida visible estado-subiendo";
    estadoUI.textContent = "Subiendo imagen...";

    const formData = new FormData();
    formData.append("archivo", archivo);

    try {
        const respuesta = await fetchAdmin(
            `/api/admin/articulos/${articuloSeleccionado.art_cod}/imagen`,
            { method: "POST", body: formData }
        );

        const resultado = await respuesta.json();

        if (!respuesta.ok) {
            estadoUI.className = "estado-subida visible estado-error";
            estadoUI.textContent = resultado.detail || "No se pudo subir la imagen.";
            btnSubir.disabled = false;
            return;
        }

        estadoUI.className = "estado-subida visible estado-exito";
        estadoUI.textContent = "Imagen actualizada con éxito.";
        document.querySelector(".detalle-imagen-actual").src = resultado.art_foto;
        btnSubir.disabled = false;
    } catch (error) {
        estadoUI.className = "estado-subida visible estado-error";
        estadoUI.textContent = error.message;
        btnSubir.disabled = false;
    }
}
