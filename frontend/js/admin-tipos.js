// Pantalla de tipos de artículos: el administrador decide cuáles se ven en la tienda.
// El servidor decide y vuelve a verificar todo; esto es solo la interfaz.
// Todo texto que viene del servidor se escribe con textContent, nunca con innerHTML.

const listaTiposUI = document.getElementById("lista-tipos");
const estadoTiposUI = document.getElementById("estado-tipos");
const filtroTipoUI = document.getElementById("filtro-tipo-lista");

let tipos = [];

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

function crearCelda(etiqueta) {
    const celda = document.createElement("td");
    celda.dataset.etiqueta = etiqueta;
    return celda;
}

// Qué ve el cliente de este tipo
function estadoDelTipo(tipo) {
    if (!tipo.mostrar_web) return { texto: "Oculto", clase: "etiqueta-oculto" };
    if (tipo.en_menu) return { texto: "Visible en el menú", clase: "etiqueta-visible" };
    return { texto: "Visible, pero sin artículos (no aparece en el menú)", clase: "etiqueta-vacio" };
}

// Rellena la lista desplegable con todos los tipos (así no hay que escribir el nombre) y conserva el elegido
function llenarFiltro() {
    const elegido = filtroTipoUI.value;
    filtroTipoUI.replaceChildren(filtroTipoUI.options[0]);
    for (const tipo of tipos) {
        const opcion = document.createElement("option");
        opcion.value = String(tipo.tipoart_cod);
        opcion.textContent = tipo.tipoart_desc;
        filtroTipoUI.append(opcion);
    }
    filtroTipoUI.value = tipos.some((t) => String(t.tipoart_cod) === elegido) ? elegido : "";
}

function dibujarTipos() {
    const elegido = filtroTipoUI.value;
    listaTiposUI.replaceChildren();
    const visibles = tipos.filter((t) => !elegido || String(t.tipoart_cod) === elegido);

    for (const tipo of visibles) {
        const fila = document.createElement("tr");
        if (!tipo.mostrar_web) fila.className = "usuario-inactivo";

        const celdaNombre = crearCelda("Tipo");
        celdaNombre.textContent = tipo.tipoart_desc;

        const celdaCantidad = crearCelda("Artículos publicados");
        celdaCantidad.textContent = `${tipo.articulos_total_publicados} de ${tipo.articulos_total}`;

        const celdaEstado = crearCelda("En la tienda");
        const estado = estadoDelTipo(tipo);
        const etiqueta = document.createElement("span");
        etiqueta.className = `etiqueta-estado ${estado.clase}`;
        etiqueta.textContent = estado.texto;
        celdaEstado.append(etiqueta);

        const celdaAccion = document.createElement("td");
        celdaAccion.className = "celda-acciones";
        const boton = document.createElement("button");
        boton.type = "button";
        boton.className = "btn-secundario btn-accion";
        boton.textContent = tipo.mostrar_web ? "Ocultar" : "Mostrar";
        boton.addEventListener("click", () => cambiarTipo(tipo, boton));
        celdaAccion.append(boton);

        fila.append(celdaNombre, celdaCantidad, celdaEstado, celdaAccion);
        listaTiposUI.append(fila);
    }

    if (tipos.length === 0) {
        mostrarEstado(estadoTiposUI, "estado-subiendo", "No hay tipos de artículos.");
    } else if (estadoTiposUI.textContent === "No hay tipos de artículos.") {
        ocultarEstado(estadoTiposUI);
    }
}

async function cargarTipos() {
    mostrarEstado(estadoTiposUI, "estado-subiendo", "Cargando tipos...");
    try {
        const respuesta = await fetchAdmin("/api/admin/tipos");
        if (!respuesta.ok) {
            mostrarEstado(estadoTiposUI, "estado-error", await mensajeDeError(respuesta, "No se pudo cargar la lista."));
            return false;
        }
        tipos = await respuesta.json();
        ocultarEstado(estadoTiposUI);
        llenarFiltro();
        dibujarTipos();
        return true;
    } catch (error) {
        mostrarEstado(estadoTiposUI, "estado-error", error.message);
        return false;
    }
}

async function cambiarTipo(tipo, boton) {
    const ocultar = tipo.mostrar_web;
    if (ocultar) {
        const n = tipo.articulos_publicados;
        const aviso = n > 0
            ? `¿Ocultar "${tipo.tipoart_desc}"? ${n === 1 ? "Su artículo publicado deja" : `Sus ${n} artículos publicados dejan`} de verse en toda la tienda y no se podrán comprar.`
            : `¿Ocultar "${tipo.tipoart_desc}"?`;
        if (!confirm(aviso)) return;
    }
    boton.disabled = true;
    try {
        const respuesta = await fetchAdmin(`/api/admin/tipos/${tipo.tipoart_cod}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ mostrar_web: !tipo.mostrar_web }),
        });
        if (!respuesta.ok) {
            mostrarEstado(estadoTiposUI, "estado-error", await mensajeDeError(respuesta, "No se pudo guardar el cambio."));
            boton.disabled = false;
            return;
        }
        if (await cargarTipos()) {
            mostrarEstado(estadoTiposUI, "estado-exito",
                `"${tipo.tipoart_desc}" ahora está ${ocultar ? "oculto" : "visible"} en la tienda.`);
        }
    } catch (error) {
        mostrarEstado(estadoTiposUI, "estado-error", error.message);
        boton.disabled = false;
    }
}

filtroTipoUI.addEventListener("change", dibujarTipos);
document.getElementById("btn-recargar-tipos").addEventListener("click", cargarTipos);

promesaSesionAdmin.then((sesion) => {
    if (sesion) cargarTipos();
});
