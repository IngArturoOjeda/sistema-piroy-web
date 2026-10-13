// 1. CAPTURA DE ELEMENTOS
const txtBuscarAdminUI = document.getElementById("txt-buscar-admin");
const listaResultadosUI = document.getElementById("lista-resultados");
const panelDetalleUI = document.getElementById("panel-detalle");

const ANCHURA_MOVIL = 900;

// 2. SESIÓN: la maneja admin-sesion.js (fetchAdmin con cookie y vuelta al login si vence)
let articuloSeleccionado = null;
let temporizadorBusqueda = null;

function esVistaMovil() {
    return window.innerWidth <= ANCHURA_MOVIL;
}

// 4. LISTA: filtro por tipo + búsqueda por texto + "Ver más" (de a TAMANO_PAGINA artículos)
const filtroTipoUI = document.getElementById("filtro-tipo");
const estadoListaUI = document.getElementById("estado-lista");

const TAMANO_PAGINA = 30;
let paginaActual = 1;
let articulosMostrados = 0;
let turnoLista = 0; // numera las cargas: una respuesta vieja (se cambió el filtro mientras viajaba) se descarta

function mostrarEstadoLista(texto, esError = false) {
    estadoListaUI.textContent = texto;
    estadoListaUI.classList.toggle("estado-lista-error", esError);
}

// Si falló la carga de la página siguiente, el botón "Ver más" vuelve a estar disponible para reintentar
function reactivarVerMas() {
    const boton = listaResultadosUI.querySelector(".resultado-ver-mas button");
    if (boton) boton.disabled = false;
}

// Rellena el filtro con los tipos que tienen artículos (los vacíos no sirven para filtrar)
async function cargarTipos() {
    try {
        const respuesta = await fetchAdmin("/api/admin/tipos");
        if (!respuesta.ok) return; // sin tipos el filtro queda en "Todos": la lista sigue funcionando
        const tipos = (await respuesta.json()).filter(t => t.articulos_total > 0);
        const total = tipos.reduce((suma, t) => suma + t.articulos_total, 0);
        filtroTipoUI.options[0].textContent = `Todos (${total})`;
        for (const tipo of tipos) {
            const opcion = document.createElement("option");
            opcion.value = String(tipo.tipoart_cod);
            opcion.textContent = `${tipo.tipoart_desc} (${tipo.articulos_total})`;
            filtroTipoUI.append(opcion);
        }
    } catch (error) {
        // el filtro queda en "Todos"
    }
}

// reiniciar = true: vuelve a la primera página (cambió el filtro o el texto); false: agrega la siguiente
async function cargarLista(reiniciar) {
    const turno = ++turnoLista;
    if (reiniciar) {
        paginaActual = 1;
        articulosMostrados = 0;
        listaResultadosUI.replaceChildren();
        mostrarEstadoLista("Cargando...");
    } else {
        paginaActual++;
    }

    const parametros = new URLSearchParams({ pagina: String(paginaActual), limite: String(TAMANO_PAGINA) });
    if (filtroTipoUI.value) parametros.set("tipo", filtroTipoUI.value);
    const texto = txtBuscarAdminUI.value.trim();
    if (texto) parametros.set("buscar", texto);

    try {
        const respuesta = await fetchAdmin(`/api/admin/articulos?${parametros}`);
        if (turno !== turnoLista) return;
        if (!respuesta.ok) {
            const error = await respuesta.json().catch(() => ({}));
            if (!reiniciar) {
                paginaActual--;
                reactivarVerMas();
            }
            mostrarEstadoLista(`No se pudo cargar la lista: ${error.detail || respuesta.status}`, true);
            return;
        }
        const articulos = await respuesta.json();
        if (turno !== turnoLista) return;
        dibujarResultados(articulos, reiniciar);
    } catch (error) {
        if (turno !== turnoLista) return;
        if (!reiniciar) {
            paginaActual--;
            reactivarVerMas();
        }
        mostrarEstadoLista(error.message, true);
    }
}

// El texto se espera un instante para no pedir en cada letra; el tipo se aplica al instante
txtBuscarAdminUI.addEventListener("input", () => {
    clearTimeout(temporizadorBusqueda);
    temporizadorBusqueda = setTimeout(() => cargarLista(true), 350);
});
filtroTipoUI.addEventListener("change", () => {
    clearTimeout(temporizadorBusqueda);
    cargarLista(true);
});

// Todo lo que viene del servidor se escribe con textContent / propiedades del DOM, nunca con innerHTML
function crearItemResultado(articulo) {
    const li = document.createElement("li");
    li.className = "resultado-item";
    li.dataset.artCod = articulo.art_cod;
    const publicado = articulo.art_estado === "S" && articulo.llevar_web && articulo.mostrar_web;

    const imagen = document.createElement("img");
    imagen.className = "resultado-miniatura";
    imagen.src = articulo.art_foto || "/frontend/assets/images/sin-imagen.svg";
    imagen.alt = articulo.art_nombre;

    const textos = document.createElement("div");
    textos.className = "resultado-textos";
    const codigo = document.createElement("div");
    codigo.className = "resultado-codigo";
    codigo.textContent = `Art. ${articulo.art_cod}`;
    const nombre = document.createElement("div");
    nombre.className = "resultado-nombre";
    nombre.textContent = articulo.art_nombre;
    const precio = document.createElement("div");
    precio.className = "resultado-precio";
    precio.textContent = `PYG ${articulo.art_preciobase.toLocaleString("es-ES")}`;
    const estado = document.createElement("span");
    estado.className = `resultado-estado ${publicado ? "estado-publicado" : "estado-no-publicado"}`;
    estado.textContent = publicado ? "Publicado" : "No publicado";
    textos.append(codigo, nombre, precio, estado);

    li.append(imagen, textos);
    li.addEventListener("click", () => seleccionarArticulo(articulo, li));
    return li;
}

function dibujarResultados(articulos, reiniciar) {
    listaResultadosUI.querySelector(".resultado-ver-mas")?.remove();

    articulosMostrados += articulos.length;
    articulos.forEach(articulo => {
        const li = crearItemResultado(articulo);
        if (articuloSeleccionado && articuloSeleccionado.art_cod === articulo.art_cod) {
            li.classList.add("seleccionado"); // se conserva la selección si el artículo sigue en la lista
        }
        listaResultadosUI.appendChild(li);
    });

    if (articulosMostrados === 0) {
        const vacio = document.createElement("li");
        vacio.className = "admin-detalle-vacio";
        vacio.textContent = "Sin coincidencias.";
        listaResultadosUI.appendChild(vacio);
        mostrarEstadoLista("Sin coincidencias.");
        return;
    }

    // una página completa: puede haber más
    const hayMas = articulos.length === TAMANO_PAGINA;
    if (hayMas) {
        const li = document.createElement("li");
        li.className = "resultado-ver-mas";
        const boton = document.createElement("button");
        boton.type = "button";
        boton.className = "btn-secundario";
        boton.textContent = "Ver más";
        boton.addEventListener("click", () => {
            boton.disabled = true;
            cargarLista(false);
        });
        li.appendChild(boton);
        listaResultadosUI.appendChild(li);
    }
    mostrarEstadoLista(`Mostrando ${articulosMostrados} artículo${articulosMostrados === 1 ? "" : "s"}${hayMas ? " (hay más)" : ""}`);
}

function actualizarBadgeListaResultado(articulo) {
    const li = listaResultadosUI.querySelector(`[data-art-cod="${articulo.art_cod}"]`);
    if (!li) return;

    const publicado = articulo.art_estado === "S" && articulo.llevar_web && articulo.mostrar_web;
    const badge = li.querySelector(".resultado-estado");
    if (!badge) return;

    badge.className = `resultado-estado ${publicado ? "estado-publicado" : "estado-no-publicado"}`;
    badge.textContent = publicado ? "Publicado" : "No publicado";
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

        ${!articulo.llevar_web ? '<p class="aviso-advertencia">Este artículo está deshabilitado para ecommerce desde el sistema local.</p>' : ""}
        ${articulo.art_estado === "N" ? '<p class="aviso-advertencia">Este artículo está inactivo.</p>' : ""}

        <div class="control-mostrar-web">
            <label class="fila-switch">
                <span>Mostrar en web</span>
                <span class="switch">
                    <input type="checkbox" id="switch-mostrar-web" ${articulo.mostrar_web ? "checked" : ""}>
                    <span class="switch-slider"></span>
                </span>
            </label>
            <p id="estado-mostrar-web" class="estado-mostrar-web"></p>
        </div>

        <form id="form-descripcion" class="form-descripcion">
            <label for="txt-descripcion">Descripción para la página del producto</label>
            <textarea id="txt-descripcion" rows="6" maxlength="2000"
                      placeholder="Para qué sirve, marca, medidas, modo de uso... Los saltos de línea se respetan."></textarea>
            <div class="descripcion-pie">
                <span id="contador-descripcion" class="contador-descripcion" aria-live="polite"></span>
                <button type="submit" class="btn-subir-imagen" id="btn-guardar-descripcion">Guardar descripción</button>
            </div>
            <p id="estado-descripcion" class="estado-subida" role="status"></p>
        </form>

        <form id="form-imagen" class="form-imagen">
            <input type="file" id="input-archivo" accept="image/jpeg,image/png,image/webp" required>
            <img id="img-preview" class="preview-nueva-imagen" alt="Vista previa">
            <button type="submit" class="btn-subir-imagen" id="btn-subir">Subir imagen</button>
            <p id="estado-subida" class="estado-subida"></p>
        </form>
    `;

    document.getElementById("input-archivo").addEventListener("change", mostrarPreviewLocal);
    document.getElementById("form-imagen").addEventListener("submit", subirImagen);
    document.getElementById("switch-mostrar-web").addEventListener("change", alternarMostrarWeb);

    // Descripción: el texto se asigna como valor (no dentro del HTML) para que ningún
    // contenido cargado pueda inyectar código en el panel
    const txtDescripcion = document.getElementById("txt-descripcion");
    txtDescripcion.value = articulo.descripcion || "";
    actualizarContadorDescripcion();
    txtDescripcion.addEventListener("input", actualizarContadorDescripcion);
    document.getElementById("form-descripcion").addEventListener("submit", guardarDescripcion);

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

// 6b. DESCRIPCIÓN COMERCIAL (se muestra en la página propia del producto)
const MAXIMO_DESCRIPCION = 2000; // igual que el backend y la base

function actualizarContadorDescripcion() {
    const txt = document.getElementById("txt-descripcion");
    const contador = document.getElementById("contador-descripcion");
    if (txt && contador) {
        contador.textContent = `${txt.value.length} / ${MAXIMO_DESCRIPCION}`;
    }
}

async function guardarDescripcion(evento) {
    evento.preventDefault();

    const txt = document.getElementById("txt-descripcion");
    const btn = document.getElementById("btn-guardar-descripcion");
    const estadoUI = document.getElementById("estado-descripcion");
    const articulo = articuloSeleccionado; // por si se elige otro mientras se guarda

    btn.disabled = true;
    estadoUI.className = "estado-subida visible estado-subiendo";
    estadoUI.textContent = "Guardando...";

    try {
        const respuesta = await fetchAdmin(
            `/api/admin/articulos/${articulo.art_cod}/descripcion`,
            {
                method: "PATCH",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ descripcion: txt.value }),
            }
        );
        const resultado = await respuesta.json().catch(() => ({}));

        if (!respuesta.ok) {
            estadoUI.className = "estado-subida visible estado-error";
            estadoUI.textContent = typeof resultado.detail === "string"
                ? resultado.detail
                : "No se pudo guardar. Revisá que no supere los 2000 caracteres.";
            return;
        }

        articulo.descripcion = resultado.descripcion; // null si quedó vacía
        if (articulo === articuloSeleccionado) {
            txt.value = resultado.descripcion || ""; // refleja el texto ya recortado
            actualizarContadorDescripcion();
        }
        estadoUI.className = "estado-subida visible estado-exito";
        estadoUI.textContent = resultado.descripcion ? "Descripción guardada." : "Descripción eliminada.";
    } catch (error) {
        estadoUI.className = "estado-subida visible estado-error";
        estadoUI.textContent = error.message;
    } finally {
        btn.disabled = false;
    }
}

// 7. CAMBIO DE mostrar_web (switch "Mostrar en web")
async function alternarMostrarWeb(evento) {
    const checkbox = evento.target;
    const estadoUI = document.getElementById("estado-mostrar-web");
    const nuevoValor = checkbox.checked; // el navegador ya lo cambio visualmente
    const valorAnterior = !nuevoValor;   // por eso guardamos el opuesto como "anterior"

    checkbox.disabled = true;
    estadoUI.textContent = "Guardando...";
    estadoUI.className = "estado-mostrar-web guardando";

    try {
        const respuesta = await fetchAdmin(
            `/api/admin/articulos/${articuloSeleccionado.art_cod}/mostrar-web`,
            {
                method: "PATCH",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ mostrar_web: nuevoValor }),
            }
        );
        const resultado = await respuesta.json();

        if (!respuesta.ok) {
            checkbox.checked = valorAnterior;
            estadoUI.textContent = resultado.detail || "No se pudo actualizar.";
            estadoUI.className = "estado-mostrar-web error";
            return;
        }

        articuloSeleccionado.mostrar_web = resultado.mostrar_web;
        actualizarBadgeListaResultado(articuloSeleccionado);
        estadoUI.textContent = "";
        estadoUI.className = "estado-mostrar-web";
    } catch (error) {
        checkbox.checked = valorAnterior;
        estadoUI.textContent = error.message;
        estadoUI.className = "estado-mostrar-web error";
    } finally {
        checkbox.disabled = false;
    }
}

// 8. ARRANQUE: con la sesión confirmada, se cargan los tipos del filtro y la primera página de artículos
promesaSesionAdmin.then((sesion) => {
    if (sesion) {
        cargarTipos();
        cargarLista(true);
    }
});
