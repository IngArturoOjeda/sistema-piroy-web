// 1. CAPTURA DE ELEMENTOS DE LA PANTALLA (UI)
const listaCategoriasUI = document.getElementById("lista-categorias");
const menuLateralUI = document.getElementById("menu-lateral");
const btnToggleCategoriasUI = document.getElementById("btn-toggle-categorias");

// Celular: abre o cierra el desplegable de categorías
if (btnToggleCategoriasUI && menuLateralUI) {
    btnToggleCategoriasUI.addEventListener("click", () => {
        const abierto = menuLateralUI.classList.toggle("abierto");
        btnToggleCategoriasUI.setAttribute("aria-expanded", String(abierto));
    });
}

// Lleva la vista al inicio de una sección (catálogo, promos o combos)
function irAlInicioDeLaVista(elemento) {
    if (elemento && typeof elemento.scrollIntoView === "function") {
        elemento.scrollIntoView({ behavior: "smooth", block: "start" });
    }
}
const contenedorCardsUI = document.getElementById("contenedor-cards");
const txtBuscarUI = document.getElementById("txt-buscar"); 
const contadorCarritoUI = document.getElementById("contador-carrito"); 
const vistaCatalogoUI = document.getElementById("vista-catalogo");
const tituloCatalogoUI = document.getElementById("titulo-catalogo");
// Promoción vigente: carrusel de la portada y página /promociones
const vistaPromocionesUI = document.getElementById("vista-promociones");
const contenedorCardsPromosUI = document.getElementById("contenedor-cards-promos");
const btnMasPromosUI = document.getElementById("btn-mas-promos");
const mensajeSinPromosUI = document.getElementById("mensaje-sin-promos");
const seccionPromoUI = document.getElementById("seccion-promo");
const carruselPromoUI = document.getElementById("carrusel-promo");
const enlaceVerPromocionUI = document.getElementById("enlace-ver-promocion");
const promoAnteriorUI = document.getElementById("promo-anterior");
const promoSiguienteUI = document.getElementById("promo-siguiente");
// Capturas de la Ventana Emergente (Modal)
const btnVerCarritoUI = document.getElementById("btn-ver-carrito");
const modalCarritoUI = document.getElementById("modal-carrito");
const btnCerrarModalUI = document.getElementById("btn-cerrar-modal");

// Capturas internas de la Modal del Carrito
const listaProductosCarritoUI = document.getElementById("lista-productos-carrito");
const totalCarritoUI = document.getElementById("total-carrito");

// Capturas del Formulario de Envío
const formPedidoUI = document.getElementById("form-pedido");
const txtClienteNombreUI = document.getElementById("txt-cliente-nombre");
const txtClienteDireccionUI = document.getElementById("txt-cliente-direccion");
const txtClienteTelefonoUI = document.getElementById("txt-cliente-telefono");
const btnEnviarPedidoUI = document.getElementById("btn-enviar-pedido");
// Capturas del modal de confirmacion al agregar al carrito
const modalAgregadoUI = document.getElementById("modal-agregado");
const txtAgregadoDefinirUI = document.getElementById("texto-agregado-definir");
const btnAgregadoSeguirUI = document.getElementById("btn-agregado-seguir");
const btnAgregadoVerCarritoUI = document.getElementById("btn-agregado-ver-carrito");
const btnAgregadoDefinirUI = document.getElementById("btn-agregado-definir");
// Capturas de la sección COMBOS
const btnVerCombosUI = document.getElementById("btn-ver-combos");
const vistaCombosUI = document.getElementById("vista-combos");
const contenedorCardsCombosUI = document.getElementById("contenedor-cards-combos");
const btnMasCombosUI = document.getElementById("btn-mas-combos");
// Capturas de la Modal de Éxito
const modalExitoUI = document.getElementById("modal-exito");
const txtOrdenConfirmadaUI = document.getElementById("txt-orden-confirmada");
const btnEntendidoExitoUI = document.getElementById("btn-entendido-exito");


// Capturas de la página propia de un producto (/producto/{id}-{nombre})
const vistaProductoUI = document.getElementById("vista-producto");
const detalleProductoUI = document.getElementById("detalle-producto");

// Contacto por WhatsApp. Número definitivo de la tienda.
// Va con código de país y sin "+" ni espacios (formato de https://wa.me/).
const WHATSAPP_NUMERO = "595981100099";
const NOMBRE_TIENDA = "AGRO-VETZO";
const TITULO_PAGINA_ORIGINAL = document.title;

// Variables globales para la memoria de la aplicación
let articulosGlobales = [];
let categoriasGlobales = [];
let carrito = [];
// 🌟 NUEVAS VARIABLES PARA EL SCROLL INFINITO
let paginaActual = 1;       // Empezamos siempre mostrando el primer lote (Página 1)
let categoriasPorPrecargar = null; // se vacía al empezar la precarga de formas de compra
let cargandoProductos = false; // Nos avisa si el sistema está ocupado hablando con FastAPI
let finDeStock = false;     // Se volverá true cuando Python nos devuelva una lista vacía []
let categoriaSeleccionadaActual = "Todos"; // 🌟 NUEVO: Sabe qué botón lateral está activo
let vistaActual = "CATALOGO"; // "CATALOGO" | "PROMOCIONES" | "COMBOS" | "PRODUCTO"
// Página de un producto: desde dónde se entró y qué artículo se está viendo
let vistaAntesDeProducto = "CATALOGO";
let scrollAntesDeProducto = 0;
let articuloDetalleActual = null;
// Numera las elecciones de categoría o forma de compra: una carga de artículos que empezó antes de la
// última elección ya no corresponde a lo que el cliente está mirando, y se descarta al llegar.
let turnoCarga = 0;
let turnoVista = 0; // numera los cambios de vista para descartar respuestas viejas (ver mostrarVista)
// Promoción vigente: las primeras para el carrusel de la portada, y la lista paginada de /promociones
let promosPortada = [];
let promosPagina = [];
let paginaPromos = 1;
// Combos: sección independiente, cargada al iniciar para saber si mostrar la entrada
let combosGlobales = [];
let paginaCombos = 1;
// Presentacion (forma de compra) seleccionada para la categoria actual
let presentacionesDisponibles = [];
let presentacionSeleccionadaActual = null;

// 2. CARGAR DATOS DESDE FASTAPI (SQL SERVER)
async function cargarDatosDeLaAPI() {
    // Si ya estamos cargando o si llegamos al final de la base de datos, frenamos por seguridad

    if (cargandoProductos || finDeStock) return;
    cargandoProductos = true; // Encendemos el semáforo en rojo: "Ocupado"
    const turno = turnoCarga;
    const vigente = () => turno === turnoCarga;
    
    try {
        // Sección Categorías
        // 1. SECCIÓN CATEGORÍAS: Se cargan una sola vez al inicio
        if (categoriasGlobales.length === 0) {
            const respuestaCategorias = await fetch("/api/categorias/");
            if (!respuestaCategorias.ok) {
                const errorData = await respuestaCategorias.json();
                alert(`Error ${respuestaCategorias.status}: ${errorData.detail || 'No se pudieron cargar las categorías'}`);
                cargandoProductos = false;
                return; 
            }
            const datosCategoriasDelBackend = await respuestaCategorias.json(); 
            categoriasGlobales = [{ id: 0, nombre: "Todos" }, ...datosCategoriasDelBackend];
            dibujarCategorias(categoriasGlobales);
            categoriasPorPrecargar = categoriasGlobales;
        }    
        // 2. SECCIÓN ARTÍCULOS PAGINADOS: Le pasamos el número de página dinámico a FastAPI
        let urlArticulos = `/api/articulos/?pagina=${paginaActual}&categoria=${categoriaSeleccionadaActual}`;
        // En "Todos" las promociones no se repiten: tienen su propia sección ("Promoción vigente").
        // Las categorías específicas sí las muestran junto al resto de sus artículos.
        if (categoriaSeleccionadaActual === "Todos") {
            await promesaPromosPortada; // hay que saber si las promociones cargaron antes de excluirlas
            if (debeExcluirPromocionesDeTodos()) {
                urlArticulos += "&sin_promocion=true";
            }
            if (!vigente()) return; // mientras esperaba, el cliente eligió otra categoría
        }
        if (presentacionSeleccionadaActual) {
            urlArticulos += `&presentacion=${presentacionSeleccionadaActual.codigo}`;
            if (presentacionSeleccionadaActual.codigo === "NORMAL" && presentacionSeleccionadaActual.unidad) {
                urlArticulos += `&unidad=${encodeURIComponent(presentacionSeleccionadaActual.unidad)}`;
            }
        }
        const respuestaArticulos = await fetch(urlArticulos);
        if (!vigente()) return; // descartada: ya se eligió otra categoría (la nueva carga maneja el semáforo)
        
        if (!respuestaArticulos.ok) {
            const errorData = await respuestaArticulos.json();
            alert(`Error ${respuestaArticulos.status}: ${errorData.detail || 'No se pudieron cargar los artículos'}`);
            cargandoProductos = false;
            return; 
               /* if (respuestaArticulos.status === 404){
                alert('No hay datos');
                return;*/
        }

        const nuevosArticulos = await respuestaArticulos.json();
        if (!vigente()) return;

            // 🌟 VALIDACIÓN CLAVE: Si Python nos devuelve una lista vacía [], significa que no hay más stock
        if (nuevosArticulos.length === 0) {
                finDeStock = true; // Apagamos el motor del scroll infinito para siempre
                cargandoProductos = false;
                // Si no había ningún artículo en pantalla, el aviso "Cargando..." tiene que dar paso a un mensaje
                if (paginaActual === 1 && articulosGlobales.length === 0) mostrarCategoriaSinArticulos();
                console.log("¡Llegamos al final de la base de datos de SQL Server!");
                return;
        }

            // 🌟 ACUMULACIÓN: Sumamos los 50 artículos nuevos al final de la lista maestra
            articulosGlobales = [...articulosGlobales, ...nuevosArticulos];

             // Mandamos a dibujar la lista completa acumulada en la cuadrícula (o, si el cliente ya
             // estaba buscando, solo los resultados de su búsqueda)
            if (txtBuscarUI.value.trim() !== "") {
                aplicarBusquedaActual();
            } else {
                dibujarArticulos(articulosGlobales);
            }

             // Apagamos el semáforo: El sistema ya está libre para la siguiente página
            cargandoProductos = false;

            // Primer lote ya dibujado: ahora sí, en segundo plano, las formas de compra de cada categoría
            if (categoriasPorPrecargar) {
                const pendientes = categoriasPorPrecargar;
                categoriasPorPrecargar = null;
                precargarPresentaciones(pendientes);
            }
    } catch (error) {
        if (!vigente()) return;
        console.error("Error crítico al conectar con la API:", error);
        contenedorCardsUI.innerHTML = "<p>Error al conectar con el servidor. Intente más tarde.</p>";
        cargandoProductos = false;
    }
}

// 3. DIBUJAR MENÚ DE CATEGORÍAS
function dibujarCategorias(listacategorias) {
    listaCategoriasUI.innerHTML = "";

    listacategorias.forEach(categoria => {
        const li = document.createElement("li");
        li.innerHTML = `<button class="btn-categoria">${categoria.nombre}</button>`;
        const boton = li.querySelector(".btn-categoria");

        if (categoria.nombre === "Todos") {
            boton.classList.add("activo");
        }
  
        boton.addEventListener("click", () => {
            // 🌟 NUEVO: Si el usuario hace clic en una categoría, lo regresamos al catálogo regular
            mostrarVista("CATALOGO");

            // Regresamos la URL estéticamente al inicio sin recargar
            window.history.pushState({}, "", "/");

            const todosLosBotones = document.querySelectorAll(".btn-categoria");
            todosLosBotones.forEach(btn => btn.classList.remove("activo"));
            boton.classList.add("activo");

            // Celular: el desplegable se cierra y el botón muestra la categoría elegida
            if (menuLateralUI && btnToggleCategoriasUI) {
                menuLateralUI.classList.remove("abierto");
                btnToggleCategoriasUI.setAttribute("aria-expanded", "false");
                btnToggleCategoriasUI.textContent = `Categorías: ${categoria.nombre} ▾`;
            }

            // Subimos a la grilla para ver los artículos de la categoría desde el inicio
            // El título de la sección muestra la categoría elegida
            tituloCatalogoUI.textContent = categoria.nombre === "Todos" ? "Nuestros Artículos" : categoria.nombre;

            irAlInicioDeLaVista(document.getElementById("vista-catalogo"));

            // 🌟 PASO A: Guardamos la categoría seleccionada
            categoriaSeleccionadaActual = categoria.nombre;
            actualizarSeccionPromo(); // la promoción vigente solo se ve con "Todos"
            // 🌟 PASO B: REINICIAMOS LOS CONTROLES DEL MOTOR DE SCROLL
            turnoCarga++;              // cualquier carga anterior que siga en camino queda descartada
            cargandoProductos = false; // y no puede bloquear la carga de esta categoría
            paginaActual = 1;          // Volvemos al primer lote de 30
            finDeStock = false;        // Encendemos el motor por si estaba apagado
            articulosGlobales = [];    // Vaciamos la lista vieja para que no se mezclen los artículos
            // Regla: nunca reutilizar la presentacion elegida en otra categoria
            presentacionesDisponibles = [];
            presentacionSeleccionadaActual = null;

            // Aviso inmediato: sin esto las tarjetas de la categoría anterior se quedaban a la vista
            // mientras el servidor respondía (1 a 3 segundos).
            mostrarCargandoCatalogo();

            // 🌟 PASO C: "Todos" no tiene una sola forma de compra -> comportamiento actual sin cambios.
            // Una categoria especifica primero pregunta que formas de compra existen.
            if (categoriaSeleccionadaActual === "Todos") {
                cargarDatosDeLaAPI();
            } else {
                cargarPresentacionesDeLaCategoria(categoriaSeleccionadaActual);
            }
            /*
            if (categoria.nombre === "Todos") {
                dibujarArticulos(articulosGlobales);
            } else {
                const articulosFiltrados = articulosGlobales.filter(articulo => articulo.tipo === categoria.nombre);
                dibujarArticulos(articulosFiltrados);
            }*/
        });
        
        listaCategoriasUI.appendChild(li);
    });
}

// Mensaje cuando la categoría elegida no tiene ningún artículo para mostrar
function mostrarCategoriaSinArticulos() {
    contenedorCardsUI.innerHTML = `
        <div class="mensaje-sin-resultados">
            <div class="icono-vacio">🔍❌</div>
            <h3>No hay productos disponibles en esta categoría</h3>
        </div>
    `;
}

// Limpia la grilla y muestra "Cargando..." mientras llegan los artículos de la categoría elegida
function mostrarCargandoCatalogo() {
    const aviso = document.createElement("p");
    aviso.className = "mensaje-cargando";
    aviso.setAttribute("role", "status");
    const rueda = document.createElement("span");
    rueda.className = "rueda-cargando";
    rueda.setAttribute("aria-hidden", "true");
    aviso.append(rueda, "Cargando artículos...");
    contenedorCardsUI.replaceChildren(aviso);
}

// Formas de compra por categoría: se guardan la promesa (así dos pedidos simultáneos comparten la
// misma respuesta) y el momento en que se pidió. Vencen a los 5 minutos: si el negocio publica
// artículos con otra unidad o presentación, el cliente los ve sin tener que recargar la página.
// Si el pedido falla, no se guarda el fallo.
const VIGENCIA_PRESENTACIONES_MS = 5 * 60 * 1000;
const presentacionesPorCategoria = new Map();

function pedirPresentaciones(categoria) {
    const guardada = presentacionesPorCategoria.get(categoria);
    if (guardada && Date.now() - guardada.pedidaEn < VIGENCIA_PRESENTACIONES_MS) {
        return guardada.promesa;
    }

    const olvidarSiSigueSiendoEsta = () => {
        const actual = presentacionesPorCategoria.get(categoria);
        if (actual && actual.promesa === promesa) presentacionesPorCategoria.delete(categoria);
    };
    const promesa = fetch(`/api/articulos/presentaciones?categoria=${encodeURIComponent(categoria)}`)
        .then(async (respuesta) => ({
            ok: respuesta.ok,
            status: respuesta.status,
            cuerpo: await respuesta.json().catch(() => null),
        }))
        .then((resultado) => {
            if (!resultado.ok) olvidarSiSigueSiendoEsta();
            return resultado;
        })
        .catch((error) => {
            olvidarSiSigueSiendoEsta();
            throw error;
        });
    presentacionesPorCategoria.set(categoria, { promesa, pedidaEn: Date.now() });
    return promesa;
}

// Con la portada ya lista, pide en segundo plano (de a una) las formas de compra de cada categoría:
// al elegirla, el cliente solo espera los artículos y no también las formas de compra.
async function precargarPresentaciones(categorias) {
    for (const categoria of categorias) {
        if (categoria.nombre === "Todos") continue;
        try {
            await pedirPresentaciones(categoria.nombre);
        } catch (error) {
            // es solo una precarga: si falla, se pedirá de nuevo cuando el cliente elija la categoría
        }
    }
}

// Consulta las formas de compra disponibles para una categoria especifica
// y decide si carga directo, muestra un selector minimo, o no hay nada que mostrar.
async function cargarPresentacionesDeLaCategoria(categoria) {
    try {
        const resultado = await pedirPresentaciones(categoria);

        // 🌟 PROTECCIÓN: si el usuario ya cambió de categoría mientras esta
        // respuesta viajaba por la red, la descartamos (incluso si vino con error).
        if (categoria !== categoriaSeleccionadaActual) {
            return;
        }

        if (!resultado.ok) {
            const errorData = resultado.cuerpo || {};
            alert(`Error ${resultado.status}: ${errorData.detail || 'No se pudieron cargar las formas de compra'}`);
            return;
        }

        const datos = resultado.cuerpo;

        presentacionesDisponibles = datos;

        if (datos.length === 0) {
            contenedorCardsUI.innerHTML = `
                <div class="mensaje-sin-resultados">
                    <div class="icono-vacio">🔍❌</div>
                    <h3>No hay productos disponibles en esta categoría</h3>
                </div>
            `;
            return;
        }

        if (datos.length === 1) {
            presentacionSeleccionadaActual = datos[0];
            cargarDatosDeLaAPI();
            return;
        }

        dibujarSelectorDePresentaciones(datos);
    } catch (error) {
        console.error("Error crítico al conectar con la API de presentaciones:", error);
        contenedorCardsUI.innerHTML = "<p>Error al conectar con el servidor. Intente más tarde.</p>";
    }
}

// Deriva icono + subtitulo puramente visuales a partir de codigo/unidad.
// No participa de ninguna decision de negocio: eso ya quedo resuelto por el backend.
function obtenerVisualPresentacion(presentacion) {
    if (presentacion.codigo === "KIT") {
        return { icono: "📦", subtitulo: "Elegí una presentación disponible" };
    }
    if (presentacion.unidad === "KG") {
        return { icono: "⚖️", subtitulo: "Elegí cuántos kilos necesitás" };
    }
    if (presentacion.unidad === "UNIDAD") {
        return { icono: "🛍️", subtitulo: "Elegí las unidades que necesitás" };
    }
    return { icono: "🧺", subtitulo: "Elegí la cantidad que necesitás" };
}

// UI del selector de formas de compra
function dibujarSelectorDePresentaciones(lista) {
    contenedorCardsUI.innerHTML = "";

    const contenedor = document.createElement("div");
    contenedor.className = "selector-presentaciones";
    contenedor.innerHTML = `<h3 class="selector-presentaciones-titulo">¿Cómo querés comprar?</h3>`;

    const grilla = document.createElement("div");
    grilla.className = "grilla-presentaciones";

    lista.forEach(presentacion => {
        const { icono, subtitulo } = obtenerVisualPresentacion(presentacion);

        const boton = document.createElement("button");
        boton.className = "tarjeta-presentacion";
        boton.innerHTML = `
            <span class="tarjeta-presentacion-icono">${icono}</span>
            <span class="tarjeta-presentacion-titulo">${presentacion.descripcion}</span>
            <span class="tarjeta-presentacion-subtitulo">${subtitulo}</span>
        `;
        boton.addEventListener("click", () => {
            presentacionSeleccionadaActual = presentacion;
            turnoCarga++;
            cargandoProductos = false;
            paginaActual = 1;
            finDeStock = false;
            articulosGlobales = [];
            cargarDatosDeLaAPI();
        });
        grilla.appendChild(boton);
    });

    contenedor.appendChild(grilla);
    contenedorCardsUI.appendChild(contenedor);
}

// Politica de venta web: estas unidades se venden solo en cantidades enteras.
// Es una regla de venta; no cambia unidad_medida.fraccionable en la base.
const UNIDADES_WEB_ENTERAS = new Set(["KG", "LITROS", "METROS"]);

function esUnidadWebEntera(articulo) {
    return UNIDADES_WEB_ENTERAS.has(articulo.unidad_venta);
}

// Maximo vendible por la web: el stock decimal se trunca hacia abajo.
function maximoVendibleWeb(articulo) {
    return typeof articulo.stock_disponible === "number"
        ? Math.floor(articulo.stock_disponible)
        : null;
}

// Umbral de disponibilidad segun el tipo de venta del articulo
function estaSinStock(articulo) {
    if (typeof articulo.stock_disponible !== "number") return false;
    if (esUnidadWebEntera(articulo)) {
        return maximoVendibleWeb(articulo) < 1;
    }
    const stockMinimo = articulo.fraccionable === true ? 0.001 : 1;
    return articulo.stock_disponible < stockMinimo;
}

// Interpreta el valor crudo del input de cantidad fraccionable.
// Si no es interpretable, conserva la cantidad anterior (no rompe el carrito).
function normalizarCantidadFraccionable(valorCrudo, stockDisponible, cantidadAnterior) {
    const numero = parseFloat(valorCrudo);
    if (typeof valorCrudo !== "string" || valorCrudo.trim() === "" || Number.isNaN(numero)) {
        return cantidadAnterior;
    }
    let cantidadFinal = Math.round(numero * 1000) / 1000; // maximo 3 decimales, sin arrastre de floats
    if (cantidadFinal < 0.001) cantidadFinal = 0.001;
    if (typeof stockDisponible === "number" && cantidadFinal > stockDisponible) {
        cantidadFinal = stockDisponible;
    }
    return cantidadFinal;
}

// Unica fuente de verdad sobre si un item del carrito (fraccionable o no) tiene
// una cantidad numerica, finita, del tipo correcto y dentro del stock disponible.
function cantidadItemValida(item) {
    if (typeof item.cantidad !== "number" || !Number.isFinite(item.cantidad)) {
        return false;
    }

    if (esUnidadWebEntera(item)) {
        const maximo = maximoVendibleWeb(item);
        if (!Number.isInteger(item.cantidad) || item.cantidad < 1) return false;
        return maximo === null || item.cantidad <= maximo;
    }

    if (item.fraccionable === true) {
        if (item.cantidad < 0.001) return false;
    } else {
        if (!Number.isInteger(item.cantidad) || item.cantidad < 1) return false;
    }

    if (typeof item.stock_disponible === "number" && item.cantidad > item.stock_disponible) {
        return false;
    }

    return true;
}

// Etiqueta de unidad de venta para la tarjeta del catalogo (solo texto visual, no afecta la venta)
const ETIQUETAS_UNIDAD_VENTA = { KG: "Por KG", LITROS: "Por litro", METROS: "Por metro" };
function etiquetaUnidadVenta(articulo) {
    if (!articulo.unidad_venta || articulo.unidad_venta === "UNIDAD") return null;
    return ETIQUETAS_UNIDAD_VENTA[articulo.unidad_venta] || `Por ${articulo.unidad_venta}`;
}

// Escapa texto del servidor antes de ponerlo dentro de HTML ("<b>" se ve como texto, no como etiqueta)
function escaparHtml(texto) {
    return String(texto)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}

// 80000 -> "80.000"
function formatoPrecio(valor) {
    return valor.toLocaleString("es-ES", { maximumFractionDigits: 0 });
}

// 4. DIBUJAR TARJETAS DE PRODUCTOS
function dibujarArticulos(listaArticulos, contenedor = contenedorCardsUI) {
    contenedor.innerHTML = "";

    if (listaArticulos.length === 0) {
        contenedor.innerHTML = `
            <div class="mensaje-sin-resultados">
                <div class="icono-vacio">🔍❌</div>
                <h3>No encontramos productos coincidentes</h3>
                <p>Prueba escribiendo otra palabra o revisa la ortografía.</p>
            </div>
        `;
        return; // Frenamos la función aquí para que no intente hacer el forEach de abajo
    }

    listaArticulos.forEach(articulo => {
        const divCard = document.createElement("div");
        divCard.className = "card-producto";

        const sinStock = estaSinStock(articulo);
        const bloqueado = sinStock;
        let textoBoton = "🛒 AGREGAR AL CARRITO ";
        if (sinStock) textoBoton = "Sin stock";

        const etiquetaUnidad = etiquetaUnidadVenta(articulo);

        // El enlace es real (href): sirve con clic derecho, "abrir en pestaña nueva" y teclado
        const hrefProducto = urlProducto(articulo);

        // Con promoción vigente: precio original tachado + precio promocional + insignia "-X %".
        // (los números del servidor son enteros; ningún texto del servidor va en estos fragmentos)
        const enPromo = articulo.precio_original != null;
        const insigniaHtml = (enPromo && articulo.descuento_porcentaje)
            ? `<span class="insignia-descuento">-${articulo.descuento_porcentaje}%<span class="solo-lectores"> de descuento</span></span>`
            : "";
        const precioHtml = enPromo
            ? `<p class="precio precio-con-promo">
                    <s class="precio-original"><span class="solo-lectores">Precio anterior: </span>PYG ${formatoPrecio(articulo.precio_original)}</s>
                    <span class="precio-vigente"><span class="solo-lectores">Precio promocional: </span><span class="precio-moneda">PYG</span> ${formatoPrecio(articulo.precio)}</span>
               </p>`
            : `<p class="precio"><span class="precio-moneda">PYG</span> ${formatoPrecio(articulo.precio)}</p>`;

        divCard.innerHTML = `
            <div class="imagen-producto">
                ${insigniaHtml}
                <a class="enlace-producto" href="${hrefProducto}" tabindex="-1" aria-hidden="true">
                    <img src="${escaparHtml(articulo.imagen)}" alt="${escaparHtml(articulo.nombre)}" loading="lazy">
                </a>
            </div>
            <div class="info-producto">
                <h3><a class="enlace-producto" href="${hrefProducto}">${escaparHtml(articulo.nombre)}</a></h3>
                ${precioHtml}
                <div class="etiquetas-producto">
                    <span class="stock-info ${sinStock ? 'agotado' : 'disponible'}">
                        ${sinStock ? 'Sin stock' : `Stock: ${esUnidadWebEntera(articulo) ? maximoVendibleWeb(articulo) : articulo.stock_disponible}`}
                    </span>
                    ${etiquetaUnidad ? `<span class="unidad-producto">${escaparHtml(etiquetaUnidad)}</span>` : ''}
                </div>
            </div>
            <button class="btn-comprar" ${bloqueado ? "disabled" : ""}>${textoBoton}</button>
        `;

        const botonComprar = divCard.querySelector(".btn-comprar");
        if (!bloqueado) {
            botonComprar.addEventListener("click", () => {
                comprarArticulo(articulo.id, articulo);
            });
        }

        divCard.querySelectorAll(".enlace-producto").forEach(enlace => {
            enlace.addEventListener("click", evento => {
                // Con Ctrl/Cmd/Mayús o botón del medio, el navegador abre el enlace normalmente
                if (evento.button !== 0 || evento.ctrlKey || evento.metaKey || evento.shiftKey || evento.altKey) return;
                evento.preventDefault();
                abrirProducto(articulo);
            });
        });

        contenedor.appendChild(divCard);
    });
}

// 5. SELECCIONAR Y AGRUPAR ARTÍCULO EN EL CARRITO
// articuloOrigen: el artículo tal como lo muestra la tarjeta que se tocó. Es la fuente preferida:
// lo que el cliente ve (precio, stock) es lo que entra al carrito, aunque otra lista cargada antes
// (por ejemplo el catálogo) tenga una copia más vieja del mismo artículo.
function comprarArticulo(idArticulo, articuloOrigen = null) {
    // Buscamos si el artículo ya existía en la canasta
    const articuloEnCarrito = carrito.find(art => art.id === idArticulo);
    let agregado = false;
    let definirCantidad = false;

    if (articuloEnCarrito) {
        if (esUnidadWebEntera(articuloEnCarrito)) {
            // Unidades web enteras: +1 por clic, sin pasar el maximo vendible
            const maximo = maximoVendibleWeb(articuloEnCarrito);
            if (maximo !== null && articuloEnCarrito.cantidad + 1 > maximo) {
                return;
            }
            articuloEnCarrito.cantidad++;
            agregado = true;
        } else {
            // Un fraccionable ya en el carrito no se incrementa: reabrimos el carrito para editar
            // la cantidad. No es una incorporacion, asi que no hay modal de exito.
            if (articuloEnCarrito.fraccionable === true) {
                abrirCarrito();
                return;
            }
            // 🌟 Tope de stock: evaluamos la PROXIMA cantidad (cantidad + 1), no la actual.
            // Cubre defensivamente stock_disponible fraccionario (ej. 3.500) en un articulo
            // no fraccionable. Se aplica solo si el dato existe (ver promociones abajo).
            const hayLimite = typeof articuloEnCarrito.stock_disponible === "number";
            if (hayLimite && (articuloEnCarrito.cantidad + 1) > articuloEnCarrito.stock_disponible) {
                return; // sumar una unidad mas superaria el stock disponible
            }
            articuloEnCarrito.cantidad++; // Si ya existía, simplemente aumentamos su cantidad
            agregado = true;
        }
    } else {
        // 2. BÚSQUEDA del artículo en lo que la web ya tiene cargado. Todas las listas
        // (catálogo, combos, promociones) traen el mismo formato, con el precio efectivo
        // (promocional si hay promo vigente). Si se está viendo la página de este
        // producto, sus datos (recién traídos del servidor) mandan sobre las copias de
        // las listas: precio y stock coinciden con lo que el cliente ve en pantalla.
        const articuloBaseDeDatos =
            (articuloOrigen && articuloOrigen.id === idArticulo ? articuloOrigen : null)
            || (articuloDetalleActual && articuloDetalleActual.id === idArticulo ? articuloDetalleActual : null)
            || articulosGlobales.find(art => art.id === idArticulo)
            || combosGlobales.find(art => art.id === idArticulo)
            || promosPagina.find(art => art.id === idArticulo)
            || promosPortada.find(art => art.id === idArticulo);

        if (articuloBaseDeDatos) {
            const esFraccionable = articuloBaseDeDatos.fraccionable === true;
            if (estaSinStock(articuloBaseDeDatos)) {
                return;
            }
            // Fraccionable: no asumimos ninguna cantidad (ni 0.001 ni 1 KG); queda en null
            // hasta que el cliente la defina explicitamente en el input del carrito.
            // Unidades web enteras arrancan en 1; otros fraccionables quedan pendientes
            const enteraWeb = esUnidadWebEntera(articuloBaseDeDatos);
            const cantidadInicial = (esFraccionable && !enteraWeb) ? null : 1;
            const nuevoItem = { ...articuloBaseDeDatos, cantidad: cantidadInicial };
            carrito.push(nuevoItem);
            agregado = true;
            definirCantidad = esFraccionable && !enteraWeb;
        }
    }

    // Actualizamos la burbuja roja sumando todas las unidades acumuladas en tiempo real
    actualizarBurbujaCabecera();

    if (agregado) {
        // Redibuja aunque el carrito este cerrado: mantiene al dia el estado del boton CONFIRMAR
        dibujarCarrito();
        abrirModalAgregado({ definirCantidad });
    }
}

// Modal independiente de exito: para el cliente, cada agregado exitoso es el mismo mensaje
function abrirModalAgregado({ definirCantidad = false } = {}) {
    txtAgregadoDefinirUI.style.display = definirCantidad ? "block" : "none";
    btnAgregadoDefinirUI.style.display = definirCantidad ? "inline-block" : "none";
    btnAgregadoVerCarritoUI.style.display = definirCantidad ? "none" : "inline-block";
    modalAgregadoUI.style.display = "flex";
}

function cerrarModalAgregado() {
    modalAgregadoUI.style.display = "none";
}

function abrirCarrito() {
    dibujarCarrito();
    modalCarritoUI.style.display = "flex";
}

function cerrarCarrito() {
    modalCarritoUI.style.display = "none";
}

// 6. DIBUJAR LISTADO DENTRO DE LA VENTANA EMERGENTE (CON INTERACTIVIDAD EN + Y -)
function dibujarCarrito() {
    listaProductosCarritoUI.innerHTML = "";
    let sumaTotal = 0;

    carrito.forEach((articulo) => {
        const cantidadValida = cantidadItemValida(articulo);
        const subtotalRenglon = cantidadValida ? articulo.precio * articulo.cantidad : 0;
        sumaTotal += subtotalRenglon;

        const li = document.createElement("li");
        li.className = "renglon-carrito";

        const esFraccionable = articulo.fraccionable === true;
        const enteraWebItem = esUnidadWebEntera(articulo);
        const maximoItem = maximoVendibleWeb(articulo);

        const controlCantidadHtml = enteraWebItem
            ? `
                <div class="control-cantidad">
                    <button class="btn-cantidad-menos" ${articulo.cantidad <= 1 ? "disabled" : ""}>-</button>
                    <span class="cantidad-numero">${articulo.cantidad} ${articulo.unidad_venta}</span>
                    <button class="btn-cantidad-mas" ${maximoItem !== null && articulo.cantidad + 1 > maximoItem ? "disabled" : ""}>+</button>
                </div>
            `
            : esFraccionable
            ? `
                <div class="control-cantidad control-cantidad-fraccionable">
                    <input
                        type="number"
                        class="input-cantidad-fraccionable"
                        step="0.001"
                        min="0.001"
                        max="${articulo.stock_disponible}"
                        value="${cantidadValida ? articulo.cantidad : ""}"
                        placeholder="Ej: 0.500"
                    >
                    <span class="unidad-venta">${articulo.unidad_venta || ""}</span>
                </div>
            `
            : `
                <div class="control-cantidad">
                    <button class="btn-cantidad-menos">-</button>
                    <span class="cantidad-numero">${articulo.cantidad}</span>
                    <button class="btn-cantidad-mas" ${
                        typeof articulo.stock_disponible === "number" && (articulo.cantidad + 1) > articulo.stock_disponible
                            ? "disabled"
                            : ""
                    }>+</button>
                </div>
            `;

        const precioRenglonHtml = cantidadValida
            ? `PYG ${subtotalRenglon.toLocaleString('es-ES', { maximumFractionDigits: 0 })}`
            : `<span class="pendiente-cantidad">Definí la cantidad</span>`;

        li.innerHTML = `
            <div class="carrito-bloque-izq">
                <img src="${articulo.imagen}" alt="${articulo.nombre}" class="miniatura-carrito">
                <div class="carrito-detalles">
                    <h4>${articulo.nombre}</h4>
                    <span class="codigo-articulo">Art. ${articulo.id}</span>
                </div>
            </div>

            <div class="carrito-bloque-der">
                ${controlCantidadHtml}
                <p class="precio-renglon">${precioRenglonHtml}</p>
                <button class="btn-eliminar-item">🗑️</button>
            </div>
        `;

        const btnEliminar = li.querySelector(".btn-eliminar-item");
        btnEliminar.addEventListener("click", () => {
            eliminarArticuloDelCarrito(articulo.id);
        });

        if (enteraWebItem) {
            li.querySelector(".btn-cantidad-menos").addEventListener("click", () => {
                if (articulo.cantidad > 1) articulo.cantidad--;
                actualizarBurbujaCabecera();
                dibujarCarrito();
            });
            li.querySelector(".btn-cantidad-mas").addEventListener("click", () => {
                const maximo = maximoVendibleWeb(articulo);
                if (maximo === null || articulo.cantidad + 1 <= maximo) articulo.cantidad++;
                actualizarBurbujaCabecera();
                dibujarCarrito();
            });
        } else if (esFraccionable) {
            const inputCantidad = li.querySelector(".input-cantidad-fraccionable");
            inputCantidad.addEventListener("change", () => {
                articulo.cantidad = normalizarCantidadFraccionable(
                    inputCantidad.value,
                    articulo.stock_disponible,
                    articulo.cantidad
                );
                actualizarBurbujaCabecera();
                dibujarCarrito();
            });
        } else {
            const btnMenos = li.querySelector(".btn-cantidad-menos");
            const btnMas = li.querySelector(".btn-cantidad-mas");

            // 🌟 EVENTO BOTÓN MENOS (-): Resta una unidad. Si llega a 0, elimina el producto.
            btnMenos.addEventListener("click", () => {
                articulo.cantidad--;
                if (articulo.cantidad <= 0) {
                    eliminarArticuloDelCarrito(articulo.id);
                } else {
                    actualizarBurbujaCabecera();
                    dibujarCarrito(); // Redibujamos para refrescar subtotales y números
                }
            });

            // 🌟 EVENTO BOTÓN MÁS (+): Suma una unidad de forma directa
            btnMas.addEventListener("click", () => {
                const hayLimite = typeof articulo.stock_disponible === "number";
                if (hayLimite && (articulo.cantidad + 1) > articulo.stock_disponible) {
                    return; // el boton deberia estar deshabilitado, esto es solo defensivo
                }
                articulo.cantidad++;
                actualizarBurbujaCabecera();
                dibujarCarrito();
            });
        }

        listaProductosCarritoUI.appendChild(li);
    });

    totalCarritoUI.textContent = `PYG ${sumaTotal.toLocaleString('es-ES', { maximumFractionDigits: 0 })}`;

    // Mientras exista un fraccionable sin cantidad valida, no se puede confirmar el pedido.
    btnEnviarPedidoUI.disabled = carrito.some(
        item => item.fraccionable === true && !cantidadItemValida(item)
    );
}

// 7. ELIMINAR COMPLETAMENTE UN RENGLÓN DEL CARRITO
function eliminarArticuloDelCarrito(idArticulo) {
    carrito = carrito.filter(art => art.id !== idArticulo);
    actualizarBurbujaCabecera();
    dibujarCarrito(); // Redibujamos la lista de la modal
}

// 🌟 FUNCIÓN AUXILIAR: Cuenta los renglones (productos distintos) del carrito y refresca la burbuja roja
function actualizarBurbujaCabecera() {
    contadorCarritoUI.textContent = carrito.length;
}

// ----------------------------------------------------
// ESCUCHADORES DE EVENTOS PRINCIPALES
// ----------------------------------------------------

// Evento para la barra de búsqueda por texto
txtBuscarUI.addEventListener("input", (evento) => {
    // Si el cliente estaba en otra vista (combos, promociones, un producto), la búsqueda
    // vuelve al catálogo para mostrar resultados
    if (vistaActual !== "CATALOGO") {
        if (window.location.pathname !== "/") window.history.pushState({}, "", "/");
        mostrarVista("CATALOGO");
    }

    aplicarBusquedaActual();
    actualizarSeccionPromo(); // con texto en el buscador, la portada muestra solo los resultados
});

// Filtra por el texto del buscador y dibuja los resultados. En "Todos" los artículos en promoción no están
// en la lista (tienen su propia sección), pero una búsqueda tiene que poder encontrarlos. Con el buscador
// vacío se vuelve a la lista sin promociones.
function aplicarBusquedaActual() {
    const textoUsuario = txtBuscarUI.value.toLowerCase();

    let universo = articulosGlobales;
    if (categoriaSeleccionadaActual === "Todos" && textoUsuario !== "") {
        const vistos = new Set(articulosGlobales.map(articulo => articulo.id));
        const promociones = [...promosPortada, ...promosPagina].filter(articulo => {
            if (vistos.has(articulo.id)) return false;
            vistos.add(articulo.id);
            return true;
        });
        universo = [...articulosGlobales, ...promociones];
    }
    const articulosFiltrados = universo.filter(articulo => {
        return articulo.nombre.toLowerCase().includes(textoUsuario);
    });
    dibujarArticulos(articulosFiltrados);
}

// Enter en la búsqueda: cierra el teclado (celular) y sube a los resultados
txtBuscarUI.addEventListener("keydown", (evento) => {
    if (evento.key === "Enter") {
        evento.preventDefault();
        txtBuscarUI.blur();
        irAlInicioDeLaVista(vistaCatalogoUI);
    }
});

// Evento para abrir la ventana del carrito
btnVerCarritoUI.addEventListener("click", () => {
    if (carrito.length>0){
        abrirCarrito(); // Apertura manual: sin confirmacion
    }else{
        alert('No existe articulos en el carrito')
    }
});

// Eventos para cerrar la ventana del carrito
btnCerrarModalUI.addEventListener("click", () => {
    cerrarCarrito();
});

window.addEventListener("click", (evento) => {
    if (evento.target === modalCarritoUI) {
        cerrarCarrito();
    }
});

// Modal de exito: "Seguir comprando" solo lo cierra; "Ver carrito" y "Definir cantidad" abren el carrito
btnAgregadoSeguirUI.addEventListener("click", () => {
    cerrarModalAgregado();
});

btnAgregadoVerCarritoUI.addEventListener("click", () => {
    cerrarModalAgregado();
    abrirCarrito();
});

btnAgregadoDefinirUI.addEventListener("click", () => {
    cerrarModalAgregado();
    abrirCarrito();
});

window.addEventListener("click", (evento) => {
    if (evento.target === modalAgregadoUI) {
        cerrarModalAgregado();
    }
});

// 🌟 NUEVO: Limpia el texto del teléfono en tiempo real dejando solo números y el signo +
txtClienteTelefonoUI.addEventListener("input", (evento) => {
    // Reemplaza cualquier carácter que no sea un número o un signo más (+)
    evento.target.value = evento.target.value.replace(/[^0-9+]/g, "");
});


// Aplica al carrito los precios vigentes que informó el servidor (respuesta 409).
// Solo toca los artículos que siguen en el carrito; el servidor es la fuente del precio.
function actualizarPreciosDelCarrito(precios) {
    if (!Array.isArray(precios)) return;
    precios.forEach(vigente => {
        const itemCarrito = carrito.find(item => item.id === vigente.id);
        if (!itemCarrito) return;
        itemCarrito.precio = vigente.precio;
        itemCarrito.precio_original = vigente.precio_original;
        itemCarrito.descuento_porcentaje = vigente.descuento_porcentaje;
    });
}

// 🌟 ESCUCHADOR PARA ENVIAR EL PEDIDO COMPLETO
formPedidoUI.addEventListener("submit", async (evento) => {
    // 1. FRENAR EL COMPORTAMIENTO POR DEFECTO:
    // Evita que la página web se recargue por completo al presionar el botón
    evento.preventDefault();

    // 2. VALIDACIÓN EXTRA: Si el carrito está completamente vacío, frenamos el envío
    if (carrito.length === 0) {
        alert("Tu carrito está vacío. Agrega algún producto antes de confirmar el pedido.");
        return;
    }

    // 2b. VALIDACIÓN EXTRA: ningún fraccionable puede viajar sin una cantidad válida
    const hayFraccionableSinCantidad = carrito.some(
        item => item.fraccionable === true && !cantidadItemValida(item)
    );
    if (hayFraccionableSinCantidad) {
        alert("Definí la cantidad de los artículos fraccionables antes de confirmar el pedido.");
        return;
    }

    // 3. CONSTRUCCIÓN DEL PAQUETE:
    // Estructuramos el objeto JSON idéntico a lo que pide 'PedidoEntrada' en Python
    const paquetePedido = {
        cliente_nombre: txtClienteNombreUI.value.values || txtClienteNombreUI.value,
        cliente_direccion: txtClienteDireccionUI.value,
        cliente_telefono: txtClienteTelefonoUI.value,
        // Limpiamos los productos enviando solo los datos básicos necesarios para SQL Server
        productos: carrito.map(item => ({
            id: item.id,
            nombre: item.nombre,
            precio: item.precio,
            cantidad: item.cantidad
        }))
    };

    try {
        // 🚀 ENVIAMOS POR RED: Llamamos al endpoint de FastAPI usando el método POST
        // Asegúrate de revisar si tu ruta quedó como '/api/confirmar-pedido' o '/api/articulos/confirmar-pedido'
        const respuestaServer = await fetch("/api/articulos/confirmar-pedido", {
            method: "POST",
            headers: {
                "Content-Type": "application/json" // Le avisamos a Python que le mandamos un JSON
            },
            body: JSON.stringify(paquetePedido) // Convertimos el objeto de JS a texto plano para el viaje
        });

        // Validamos si la Base de Datos aceptó e insertó el registro correctamente
        if (respuestaServer.ok) {
            const resultado = await respuestaServer.json();
            
            // ¡ÉXITO TOTAL!
           // alert(`🎉 ${resultado.mensaje}\nTu número de orden es la N°: ${resultado.id_pedido}`);
            // 🌟 NUEVO: En vez del alert, inyectamos el número de orden en la modal de éxito
            txtOrdenConfirmadaUI.textContent = resultado.id_pedido;

             // 🌟 NUEVO: Encendemos la ventana flotante de éxito en la pantalla
            modalExitoUI.style.display = "flex";

            // LIMPIEZA DEL SISTEMA: 
            carrito = [];                           // Vaciamos la canasta en memoria
            contadorCarritoUI.textContent = 0;      // Regresamos la burbuja roja a cero
            formPedidoUI.reset();                   // Limpiamos las cajas de texto del cliente
            cerrarCarrito();                        // Cerramos la ventana flotante

        } else {
            const datosError = await respuestaServer.json().catch(() => ({}));
            const detalle = datosError.detail;

            // 409: el precio de algún artículo cambió (una promoción empezó o terminó) desde que
            // el cliente lo agregó. No se guardó nada: se actualiza el carrito y se pide revisar.
            if (respuestaServer.status === 409 && detalle && detalle.codigo === "PRECIOS_CAMBIARON") {
                actualizarPreciosDelCarrito(detalle.precios);
                dibujarCarrito();
                alert(`⚠️ ${detalle.mensaje}\n\nYa actualizamos los precios en tu carrito. Revisá el total y volvé a confirmar el pedido.`);
                return;
            }

            const motivo = typeof detalle === "string" ? detalle : "Error desconocido";
            alert(`❌ No se pudo guardar el pedido: ${motivo}`);
        }

    } catch (error) {
        console.error("Error en la petición de red:", error);
        alert("Ocurrió un error de red al intentar conectar con el servidor.");
    }
    // 4. PROBAMOS EN CONSOLA:
    // Imprimimos el paquete en la consola para revisar que esté perfecto
   // console.log("¡Paquete armado con éxito para FastAPI!", paquetePedido);
   //alert(`Paquete listo para el cliente: ${paquetePedido.cliente_nombre}.\nLleva ${paquetePedido.productos.length} tipo(s) de artículos.`);
});

// 🌟 ESCUCHADOR PARA CERRAR LA VENTANA DE ÉXITO
btnEntendidoExitoUI.addEventListener("click", () => {
    modalExitoUI.style.display = "none";
});

// 🌟 ESCUCHADOR DINÁMICO: Detecta el scroll del mouse en tiempo real
window.addEventListener("scroll", () => {
    // Las vistas de promociones y combos no paginan el catálogo
    if (vistaActual !== "CATALOGO") {
        return;
    }

    // En una categoría específica no hay nada que paginar hasta que el cliente elija cómo comprar
    // (selector de formas de compra a la vista, o todavía consultándose): sin esto, el scroll que
    // provoca elegir la categoría pedía la "página 2" sin forma de compra y pisaba el selector.
    if (categoriaSeleccionadaActual !== "Todos" && !presentacionSeleccionadaActual) {
        return;
    }

    // Medimos el estado del navegador del cliente
    const alturaTotalPagina = document.documentElement.scrollHeight; // El alto completo de tu catálogo
    const alturaBordeSuperior = window.scrollY;                       // Cuánto bajó el usuario con la ruedita
    const alturaVentanaVisible = window.innerHeight;                 // El tamaño físico de tu monitor

    // 🔬 MATEMÁTICA DEL SCROLL:
    // Si lo que bajó el usuario + el tamaño de su pantalla es casi igual al fondo de la página (dejamós un margen de 100 píxeles)...
    if (alturaBordeSuperior + alturaVentanaVisible >= alturaTotalPagina - 100) {
        
        // ... Y si el sistema no está cargando nada en este instante y queda stock disponible ...
        if (!cargandoProductos && !finDeStock) {
            paginaActual++; // Avanzamos a la siguiente página (Ej: de página 1 a página 2)
            console.log(`Cargando lote de 30 artículos de la Página N°: ${paginaActual}`);
            
            cargarDatosDeLaAPI(); // Llamamos a la API de forma invisible
        }
    }
});

// 🌟 CARRUSEL DE BANNERS (se arma con GET /api/banners/)
// Los banners son imágenes completas con el texto incluido, cargadas desde el
// panel de administración. Sin banners activos, el carrusel no se muestra.
document.addEventListener("DOMContentLoaded", iniciarCarruselBanners);

async function iniciarCarruselBanners() {
    const contenedor = document.getElementById("contenedor-banner");
    const carrusel = document.getElementById("carrusel-imagenes");
    const indicadores = document.getElementById("carrusel-indicadores");
    if (!contenedor || !carrusel || !indicadores) return;

    let banners;
    try {
        const respuesta = await fetch("/api/banners/");
        if (!respuesta.ok) return;
        banners = await respuesta.json();
    } catch (error) {
        console.error("No se pudieron cargar los banners:", error);
        return; // el carrusel queda oculto: la tienda funciona igual
    }
    if (!Array.isArray(banners) || banners.length === 0) return;

    const slides = [];
    const puntos = [];
    let slideActual = 0;

    // Cambio automático: solo con 2 o más banners y si el cliente no pidió
    // "menos movimiento". Se declara antes de crear los puntitos porque sus
    // clics llaman a reiniciarTemporizador().
    const sinMovimiento = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const cambioAutomatico = banners.length > 1 && !sinMovimiento;
    const tiempoCambio = 5000; // 5 segundos
    let intervalo = null;
    let apuntando = false; // el mouse está sobre el carrusel
    let enfocado = false;  // el foco del teclado está dentro del carrusel

    function detenerTemporizador() {
        if (intervalo !== null) {
            clearInterval(intervalo);
            intervalo = null;
        }
    }
    // Solo corre mientras el cliente no apunta ni enfoca el carrusel
    function iniciarTemporizador() {
        detenerTemporizador();
        if (!cambioAutomatico || apuntando || enfocado) return;
        intervalo = setInterval(() => cambiarSlide((slideActual + 1) % slides.length), tiempoCambio);
    }

    banners.forEach((banner, i) => {
        const slide = document.createElement("div");
        slide.className = "banner-slide" + (i === 0 ? " activo" : "");
        slide.setAttribute("aria-hidden", i === 0 ? "false" : "true");

        const img = document.createElement("img");
        img.src = banner.imagen_url;
        img.alt = banner.alt;
        img.decoding = "async";
        if (i === 0) img.setAttribute("fetchpriority", "high"); // el primero es el que se ve al entrar

        slide.appendChild(img);
        carrusel.appendChild(slide);
        slides.push(slide);

        if (banners.length > 1) {
            const punto = document.createElement("button");
            punto.type = "button";
            punto.className = "punto" + (i === 0 ? " activo" : "");
            punto.setAttribute("aria-label", `Ir al banner ${i + 1} de ${banners.length}`);
            if (i === 0) punto.setAttribute("aria-current", "true");
            punto.addEventListener("click", () => {
                cambiarSlide(i);
                iniciarTemporizador(); // reinicia la cuenta para que no cambie de golpe
            });
            indicadores.appendChild(punto);
            puntos.push(punto);
        }
    });

    function cambiarSlide(indice) {
        slides.forEach((slide, i) => {
            slide.classList.toggle("activo", i === indice);
            slide.setAttribute("aria-hidden", i === indice ? "false" : "true");
        });
        puntos.forEach((punto, i) => {
            punto.classList.toggle("activo", i === indice);
            if (i === indice) punto.setAttribute("aria-current", "true");
            else punto.removeAttribute("aria-current");
        });
        slideActual = indice;
    }

    contenedor.hidden = false;

    if (!cambioAutomatico) return;

    // Se pausa mientras el cliente apunta o enfoca el carrusel
    contenedor.addEventListener("mouseenter", () => { apuntando = true; iniciarTemporizador(); });
    contenedor.addEventListener("mouseleave", () => { apuntando = false; iniciarTemporizador(); });
    contenedor.addEventListener("focusin", () => { enfocado = true; iniciarTemporizador(); });
    contenedor.addEventListener("focusout", evento => {
        // Si el foco pasa a otro elemento del mismo carrusel, sigue enfocado
        enfocado = contenedor.contains(evento.relatedTarget);
        iniciarTemporizador();
    });

    iniciarTemporizador();
}

// ----------------------------------------------------
// VISTAS Y RUTAS
// Cada "página" de la tienda es una vista de esta misma página (index.html) con su propia URL:
// "/" (portada), "/promociones", "/combos" y "/producto/{id}-{nombre}". El carrito vive en memoria
// y no se debe perder al navegar, por eso no son archivos aparte. main.py sirve index.html en todas
// esas direcciones, así que funcionan al recargar y al compartirlas.
// ----------------------------------------------------

const VISTAS = {
    CATALOGO: vistaCatalogoUI,
    PROMOCIONES: vistaPromocionesUI,
    COMBOS: vistaCombosUI,
    PRODUCTO: vistaProductoUI,
};

// Muestra UNA vista y oculta las demás. No toca la URL.
function mostrarVista(nombre) {
    turnoVista++; // cualquier carga en curso de otra vista queda descartada
    Object.entries(VISTAS).forEach(([clave, elemento]) => {
        elemento.style.display = clave === nombre ? "block" : "none";
    });
    vistaActual = nombre;
    document.body.classList.toggle("en-producto", nombre === "PRODUCTO");
    document.body.classList.toggle("en-promociones", nombre === "PROMOCIONES");
    if (nombre !== "PRODUCTO") articuloDetalleActual = null;
    document.title = TITULO_PAGINA_ORIGINAL; // la página del producto y la de promociones lo cambian después
    actualizarSeccionPromo();
}

// "/producto/1000-botina" -> { vista: "PRODUCTO", id: "1000" }
function resolverRuta(ruta) {
    const idProducto = idDesdeRutaProducto(ruta);
    if (idProducto !== null) return { vista: "PRODUCTO", id: idProducto };
    if (ruta === "/promociones") return { vista: "PROMOCIONES" };
    if (ruta === "/combos") return { vista: "COMBOS" };
    return { vista: "CATALOGO" };
}

// Muestra la vista que corresponde a la URL actual, sin cambiarla. Se usa al cargar la página y con
// Atrás/Adelante: el destino es el de la URL, no el de donde se entró (por ejemplo "/" tras elegir
// una categoría estando en un producto).
async function mostrarRutaActual() {
    const destino = resolverRuta(window.location.pathname);
    const veniaDeProducto = vistaActual === "PRODUCTO";

    if (destino.vista === "PRODUCTO") {
        await mostrarProducto(destino.id);
        return;
    }

    if (destino.vista === "PROMOCIONES") {
        await mostrarPaginaPromociones({ conservar: veniaDeProducto });
    } else if (destino.vista === "COMBOS") {
        await mostrarPaginaCombos();
    } else {
        mostrarVista("CATALOGO");
    }

    // Al volver de un producto a la misma vista de la que se salió, recupera la posición
    if (veniaDeProducto) {
        window.scrollTo(0, vistaActual === vistaAntesDeProducto ? scrollAntesDeProducto : 0);
    }
}

// Navegación interna (botones y enlaces de la tienda): cambia la URL sin recargar y muestra la vista
async function irA(ruta) {
    const veniaDeProducto = vistaActual === "PRODUCTO";
    if (window.location.pathname !== ruta) {
        window.history.pushState({ desdeTienda: true }, "", ruta);
    }
    await mostrarRutaActual();
    if (!veniaDeProducto) irAlInicioDeLaVista(VISTAS[vistaActual]);
}

// Clic "normal" (sin Ctrl/Cmd/Mayús/Alt ni botón del medio): el navegador abre los demás en pestaña nueva
function esClicNormal(evento) {
    return evento.button === 0 && !evento.ctrlKey && !evento.metaKey && !evento.shiftKey && !evento.altKey;
}

// "← Volver a la tienda": si se entró desde la tienda es un "Atrás"; si se llegó directo por
// la URL, lleva a la portada
function volverALaTienda(evento) {
    if (!esClicNormal(evento)) return;
    evento.preventDefault();
    if (window.history.state && window.history.state.desdeTienda) {
        window.history.back(); // popstate muestra la vista anterior
    } else {
        window.history.pushState({}, "", "/");
        mostrarRutaActual();
    }
}
document.querySelectorAll(".enlace-volver").forEach(enlace => enlace.addEventListener("click", volverALaTienda));

// Botones Atrás/Adelante del navegador
window.addEventListener("popstate", () => {
    mostrarRutaActual();
});

// ----------------------------------------------------
// CARRUSEL DE TARJETAS (flechas anterior/siguiente). Lo usa "Promoción vigente".
// Es una fila con desplazamiento nativo (también con el dedo en el celular); las flechas
// mueven casi un ancho completo y se deshabilitan en los extremos.
// ----------------------------------------------------
function enlazarCarrusel(pista, btnAnterior, btnSiguiente) {
    const paso = () => Math.max(pista.clientWidth * 0.9, 220);
    const sinMovimiento = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    const actualizar = () => {
        const maximo = pista.scrollWidth - pista.clientWidth;
        btnAnterior.disabled = pista.scrollLeft <= 1;
        btnSiguiente.disabled = pista.scrollLeft >= maximo - 1;
    };
    const mover = direccion => {
        const cantidad = direccion * paso();
        if (typeof pista.scrollBy === "function") {
            pista.scrollBy({ left: cantidad, behavior: sinMovimiento() ? "auto" : "smooth" });
        } else {
            pista.scrollLeft += cantidad;
        }
    };

    btnAnterior.addEventListener("click", () => mover(-1));
    btnSiguiente.addEventListener("click", () => mover(1));
    pista.addEventListener("scroll", actualizar, { passive: true });
    window.addEventListener("resize", actualizar);
    return actualizar;
}

// ----------------------------------------------------
// PROMOCIÓN VIGENTE: carrusel de la portada y página /promociones
// Los artículos vienen de GET /api/articulos/promociones, con el precio ya rebajado
// (precio), el original (precio_original) y el porcentaje (descuento_porcentaje).
// ----------------------------------------------------
const LIMITE_PROMO_PORTADA = 12;     // tarjetas que dibuja el carrusel de la portada
const LIMITE_PROMOS_BUSQUEDA = 100;  // las que se traen para que el buscador las encuentre (máximo del servidor)
const LIMITE_PROMOS_PAGINA = 30;
const TEXTO_SIN_PROMOS = "Por el momento no hay promociones vigentes. ¡Volvé pronto!";

const actualizarFlechasPromo = enlazarCarrusel(carruselPromoUI, promoAnteriorUI, promoSiguienteUI);

// "Todos" solo excluye las promociones cuando están seguras: cargaron bien y entraron todas en la lista
// que usa el buscador. Si la carga falló, o hay tantas que se llegó al tope de lo que se trae (100) y alguna
// quedaría sin poder encontrarse, "Todos" las sigue mostrando (repetidas, pero ninguna se pierde).
function debeExcluirPromocionesDeTodos() {
    return promosPortada.length > 0 && promosPortada.length < LIMITE_PROMOS_BUSQUEDA;
}

// La sección solo se ve en la portada (categoría "Todos", sin búsqueda) y si hay promociones
function actualizarSeccionPromo() {
    const visible =
        promosPortada.length > 0
        && vistaActual === "CATALOGO"
        && categoriaSeleccionadaActual === "Todos"
        && txtBuscarUI.value.trim() === "";
    seccionPromoUI.hidden = !visible;
    if (visible) actualizarFlechasPromo();
}

// Se llama al iniciar. Si falla o no hay promociones, la sección queda oculta y la tienda funciona igual.
async function cargarPromosPortada() {
    try {
        const respuesta = await fetch(`/api/articulos/promociones?pagina=1&limite=${LIMITE_PROMOS_BUSQUEDA}`);
        if (!respuesta.ok) throw new Error(`Error ${respuesta.status} al cargar las promociones`);
        promosPortada = await respuesta.json();
    } catch (error) {
        console.error("No se pudieron cargar las promociones de la portada:", error);
        promosPortada = [];
    }
    mostrarEnlacePie("pie-item-promos", promosPortada.length > 0);
    if (promosPortada.length > 0) {
        dibujarArticulos(promosPortada.slice(0, LIMITE_PROMO_PORTADA), carruselPromoUI);
    }
    actualizarSeccionPromo();
    // Si el cliente ya estaba buscando cuando llegaron las promociones, se vuelve a buscar con ellas
    if (txtBuscarUI.value.trim() !== "" && vistaActual === "CATALOGO") {
        aplicarBusquedaActual();
    }
}

enlaceVerPromocionUI.addEventListener("click", evento => {
    if (!esClicNormal(evento)) return;
    evento.preventDefault();
    irA("/promociones");
});

// Página /promociones: TODOS los artículos con promoción vigente, de a 30
async function mostrarPaginaPromociones({ conservar = false } = {}) {
    mostrarVista("PROMOCIONES");
    document.title = `Promoción vigente | ${NOMBRE_TIENDA}`;
    window.scrollTo(0, 0);
    // Al volver desde un producto se conserva la lista ya cargada (y la posición)
    if (conservar && promosPagina.length > 0) return;
    await cargarPromosPagina(1);
}

async function cargarPromosPagina(pagina) {
    const turno = turnoVista;
    try {
        const respuesta = await fetch(`/api/articulos/promociones?pagina=${pagina}&limite=${LIMITE_PROMOS_PAGINA}`);
        if (!respuesta.ok) throw new Error(`Error ${respuesta.status} al cargar las promociones`);
        const nuevos = await respuesta.json();
        if (turno !== turnoVista) return;

        promosPagina = pagina === 1 ? nuevos : [...promosPagina, ...nuevos];
        paginaPromos = pagina;

        mensajeSinPromosUI.textContent = TEXTO_SIN_PROMOS;
        mensajeSinPromosUI.hidden = promosPagina.length > 0;
        if (promosPagina.length > 0) {
            dibujarArticulos(promosPagina, contenedorCardsPromosUI);
        } else {
            contenedorCardsPromosUI.replaceChildren();
        }
        btnMasPromosUI.style.display = nuevos.length === LIMITE_PROMOS_PAGINA ? "inline-block" : "none";
    } catch (error) {
        if (turno !== turnoVista) return;
        console.error("No se pudieron cargar las promociones:", error);
        mensajeSinPromosUI.textContent = "No pudimos cargar las promociones. Intentá de nuevo en unos minutos.";
        mensajeSinPromosUI.hidden = false;
        btnMasPromosUI.style.display = "none";
    }
}

// Un solo pedido a la vez: dos toques seguidos no deben pedir (y agregar) la misma página dos veces
let cargandoMasPromos = false;
btnMasPromosUI.addEventListener("click", async () => {
    if (cargandoMasPromos) return;
    cargandoMasPromos = true;
    btnMasPromosUI.disabled = true;
    try {
        await cargarPromosPagina(paginaPromos + 1);
    } finally {
        cargandoMasPromos = false;
        btnMasPromosUI.disabled = false;
    }
});

// ----------------------------------------------------
// SECCIÓN COMBOS (independiente de categorías y presentaciones)
// ----------------------------------------------------

const LIMITE_COMBOS = 30;

// Se llama al iniciar: solo muestra la entrada "Combos" si hay alguno publicado
async function cargarCombosDeLaAPI(pagina = 1) {
    try {
        const respuesta = await fetch(`/api/articulos/combos?pagina=${pagina}&limite=${LIMITE_COMBOS}`);
        if (!respuesta.ok) throw new Error(`Error ${respuesta.status} al cargar combos`);

        const nuevos = await respuesta.json();
        combosGlobales = pagina === 1 ? nuevos : [...combosGlobales, ...nuevos];
        paginaCombos = pagina;

        btnVerCombosUI.style.display = combosGlobales.length > 0 ? "inline-flex" : "none";
        mostrarEnlacePie("pie-item-combos", combosGlobales.length > 0);
        btnMasCombosUI.style.display = nuevos.length === LIMITE_COMBOS ? "inline-block" : "none";
    } catch (error) {
        console.error("No se pudieron cargar los combos:", error);
        btnVerCombosUI.style.display = "none";
        mostrarEnlacePie("pie-item-combos", false);
        btnMasCombosUI.style.display = "none";
    }
}

// Página /combos. Si se entra directo por la URL hay que esperar a que terminen de cargar.
async function mostrarPaginaCombos() {
    mostrarVista("COMBOS");
    const turno = turnoVista;
    await promesaCombosInicial;
    if (turno !== turnoVista) return;

    if (combosGlobales.length === 0) {
        // No hay combos publicados: no hay nada que mostrar, se vuelve a la portada
        window.history.replaceState({}, "", "/");
        mostrarVista("CATALOGO");
        return;
    }
    dibujarArticulos(combosGlobales, contenedorCardsCombosUI);
}

btnVerCombosUI.addEventListener("click", () => {
    irA("/combos");
});

let cargandoMasCombos = false;
btnMasCombosUI.addEventListener("click", async () => {
    if (cargandoMasCombos) return;
    cargandoMasCombos = true;
    btnMasCombosUI.disabled = true;
    try {
        await cargarCombosDeLaAPI(paginaCombos + 1);
        dibujarArticulos(combosGlobales, contenedorCardsCombosUI);
    } finally {
        cargandoMasCombos = false;
        btnMasCombosUI.disabled = false;
    }
});

// ----------------------------------------------------
// PÁGINA PROPIA DE UN PRODUCTO: /producto/{id}-{nombre}
// ----------------------------------------------------

// "Botina en cuero Nº 38" -> "botina-en-cuero-n-38" (solo para que la URL sea legible)
function slugArticulo(nombre) {
    return String(nombre)
        .normalize("NFD").replace(/[̀-ͯ]/g, "")
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-+|-+$/g, "")
        .slice(0, 60)
        .replace(/-+$/g, "");
}

function urlProducto(articulo) {
    const slug = slugArticulo(articulo.nombre);
    return `/producto/${articulo.id}${slug ? "-" + slug : ""}`;
}

// "/producto/1000-botina" -> "1000". Lo que sigue al código es decorativo.
function idDesdeRutaProducto(ruta) {
    const coincidencia = /^\/producto\/(\d+)(?:-[^/]*)?\/?$/.exec(ruta);
    return coincidencia ? coincidencia[1] : null;
}

// Mensaje de WhatsApp: "Hola AGRO-VETZO, estoy interesado en este artículo: ..."
// (el precio es el vigente: el promocional si hay promoción)
function urlWhatsApp(articulo) {
    const precio = formatoPrecio(articulo.precio);
    const enlace = `${window.location.origin}${urlProducto(articulo)}`;
    const mensaje =
        `Hola ${NOMBRE_TIENDA}, estoy interesado en este artículo: ${articulo.nombre} - Gs. ${precio}\n${enlace}`;
    return `https://wa.me/${WHATSAPP_NUMERO}?text=${encodeURIComponent(mensaje)}`;
}

// Entrada desde una tarjeta: cambia la URL sin recargar
function abrirProducto(articulo) {
    if (vistaActual !== "PRODUCTO") {
        vistaAntesDeProducto = vistaActual;
        scrollAntesDeProducto = window.scrollY;
    }
    window.history.pushState({ desdeTienda: true }, "", urlProducto(articulo));
    mostrarRutaActual();
}

function mostrarMensajeProducto(texto) {
    const caja = document.createElement("div");
    caja.className = "detalle-mensaje";
    const parrafo = document.createElement("p");
    parrafo.textContent = texto;
    caja.appendChild(parrafo);
    detalleProductoUI.replaceChildren(caja);
}

async function mostrarProducto(idTexto) {
    mostrarVista("PRODUCTO");
    const turno = turnoVista;
    window.scrollTo(0, 0);
    mostrarMensajeProducto("Cargando producto...");

    try {
        const respuesta = await fetch(`/api/articulos/${idTexto}`);
        if (turno !== turnoVista) return;

        if (respuesta.status === 404) {
            mostrarMensajeProducto("Este producto no está disponible.");
            document.title = `Producto no disponible | ${NOMBRE_TIENDA}`;
            return;
        }
        if (!respuesta.ok) throw new Error(`Error ${respuesta.status} al cargar el producto`);

        const articulo = await respuesta.json();
        if (turno !== turnoVista) return;

        articuloDetalleActual = articulo;
        dibujarDetalleProducto(articulo);
        document.title = `${articulo.nombre} | ${NOMBRE_TIENDA}`;
    } catch (error) {
        if (turno !== turnoVista) return;
        console.error("No se pudo cargar el producto:", error);
        mostrarMensajeProducto("No pudimos cargar el producto. Intentá de nuevo en unos minutos.");
    }
}

// Texto que solo leen los lectores de pantalla ("Precio anterior: ")
function crearTextoLector(texto) {
    const span = document.createElement("span");
    span.className = "solo-lectores";
    span.textContent = texto;
    return span;
}

// Todo dato del servidor se escribe con textContent/propiedades (nunca innerHTML)
function dibujarDetalleProducto(articulo) {
    const sinStock = estaSinStock(articulo);
    const etiquetaUnidad = etiquetaUnidadVenta(articulo);

    const contenedor = document.createElement("article");
    contenedor.className = "detalle-producto";

    // Imagen
    const marcoImagen = document.createElement("div");
    marcoImagen.className = "detalle-imagen";
    const imagen = document.createElement("img");
    imagen.src = articulo.imagen;
    imagen.alt = articulo.nombre;
    marcoImagen.appendChild(imagen);

    // Datos
    const datos = document.createElement("div");
    datos.className = "detalle-datos";

    const categoria = document.createElement("p");
    categoria.className = "detalle-categoria";
    categoria.textContent = articulo.tipo;

    const nombre = document.createElement("h1");
    nombre.className = "detalle-nombre";
    nombre.textContent = articulo.nombre;

    // Precio: con promoción vigente, original tachado + promocional + insignia "-X %"
    const precio = document.createElement("p");
    precio.className = "detalle-precio";
    const moneda = document.createElement("span");
    moneda.className = "precio-moneda";
    moneda.textContent = "PYG";
    if (articulo.precio_original != null) {
        precio.classList.add("precio-con-promo");
        const original = document.createElement("s");
        original.className = "precio-original";
        original.append(crearTextoLector("Precio anterior: "), `PYG ${formatoPrecio(articulo.precio_original)}`);
        const vigente = document.createElement("span");
        vigente.className = "precio-vigente";
        vigente.append(crearTextoLector("Precio promocional: "), moneda, ` ${formatoPrecio(articulo.precio)}`);
        precio.append(original, vigente);
        if (articulo.descuento_porcentaje) {
            const insignia = document.createElement("span");
            insignia.className = "insignia-descuento";
            insignia.append(`-${articulo.descuento_porcentaje}%`, crearTextoLector(" de descuento"));
            precio.appendChild(insignia);
        }
    } else {
        precio.append(moneda, ` ${formatoPrecio(articulo.precio)}`);
    }

    const etiquetas = document.createElement("div");
    etiquetas.className = "etiquetas-producto";
    const stock = document.createElement("span");
    stock.className = `stock-info ${sinStock ? "agotado" : "disponible"}`;
    stock.textContent = sinStock
        ? "Sin stock"
        : `Stock: ${esUnidadWebEntera(articulo) ? maximoVendibleWeb(articulo) : articulo.stock_disponible}`;
    etiquetas.appendChild(stock);
    if (etiquetaUnidad) {
        const unidad = document.createElement("span");
        unidad.className = "unidad-producto";
        unidad.textContent = etiquetaUnidad;
        etiquetas.appendChild(unidad);
    }

    datos.append(categoria, nombre, precio, etiquetas);

    // Descripción (solo si el artículo la tiene cargada)
    if (articulo.descripcion) {
        const bloque = document.createElement("div");
        bloque.className = "detalle-descripcion";
        const titulo = document.createElement("h2");
        titulo.textContent = "Descripción";
        const texto = document.createElement("p");
        texto.textContent = articulo.descripcion;
        bloque.append(titulo, texto);
        datos.appendChild(bloque);
    }

    // Acciones: agregar al carrito y consultar por WhatsApp
    const acciones = document.createElement("div");
    acciones.className = "detalle-acciones";

    const btnAgregar = document.createElement("button");
    btnAgregar.type = "button";
    btnAgregar.className = "btn-comprar";
    btnAgregar.textContent = sinStock ? "Sin stock" : "🛒 AGREGAR AL CARRITO";
    btnAgregar.disabled = sinStock;
    if (!sinStock) {
        btnAgregar.addEventListener("click", () => comprarArticulo(articulo.id));
    }

    const btnWhatsApp = document.createElement("a");
    btnWhatsApp.className = "btn-whatsapp";
    btnWhatsApp.href = urlWhatsApp(articulo);
    btnWhatsApp.target = "_blank";
    btnWhatsApp.rel = "noopener noreferrer";
    btnWhatsApp.textContent = "💬 Consultar por WhatsApp";

    acciones.append(btnAgregar, btnWhatsApp);
    datos.appendChild(acciones);

    contenedor.append(marcoImagen, datos);
    detalleProductoUI.replaceChildren(contenedor);
}

// ----------------------------------------------------
// CABECERA FIJA Y PIE DE PÁGINA
// ----------------------------------------------------
// La cabecera queda fija arriba (CSS). Se publica su alto real en --alto-cabecera: lo usan el menú lateral
// (queda justo debajo) y el desplazamiento a cada vista (scroll-padding-top), para que nada quede tapado.
const cabeceraUI = document.querySelector("header");

function publicarAltoDeCabecera() {
    document.documentElement.style.setProperty("--alto-cabecera", `${cabeceraUI.offsetHeight}px`);
}

publicarAltoDeCabecera();
if (typeof ResizeObserver === "function") {
    new ResizeObserver(publicarAltoDeCabecera).observe(cabeceraUI);
}
window.addEventListener("resize", publicarAltoDeCabecera);

// Pie de página: el número de WhatsApp sale de la constante de arriba (un solo lugar)
document.getElementById("pie-whatsapp").href =
    `https://wa.me/${WHATSAPP_NUMERO}?text=${encodeURIComponent(`Hola ${NOMBRE_TIENDA}, quisiera hacer una consulta.`)}`;
document.getElementById("pie-anio").textContent = String(new Date().getFullYear());

// "Promociones" y "Combos" del pie solo aparecen si hay algo que mostrar (lo avisan las funciones que los cargan)
function mostrarEnlacePie(idItem, visible) {
    document.getElementById(idItem).hidden = !visible;
}

// Los enlaces internos del pie navegan sin recargar la página, así no se pierde el carrito
document.getElementById("pie-pagina").addEventListener("click", (evento) => {
    const enlace = evento.target.closest("a[data-ruta-interna]");
    if (!enlace || !esClicNormal(evento)) return;
    evento.preventDefault();
    irA(enlace.getAttribute("href"));
});

// ----------------------------------------------------
// ARRANQUE: se leen los datos y se muestra la vista de la URL actual (recarga o enlace compartido)
// ----------------------------------------------------
const promesaPromosPortada = cargarPromosPortada();
cargarDatosDeLaAPI(); // el catálogo de "Todos" espera a promesaPromosPortada para saber si excluye las promociones
const promesaCombosInicial = cargarCombosDeLaAPI();
mostrarRutaActual();
