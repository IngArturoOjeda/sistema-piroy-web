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
const vistaPromocionesUI = document.getElementById("vista-promociones");
const contenedorCardsPromosUI = document.getElementById("contenedor-cards-promos");
const btnVerPromosUI = document.getElementById("btn-ver-promos");
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


// Variables globales para la memoria de la aplicación
let articulosGlobales = [];
let categoriasGlobales = [];
let carrito = [];
// 🌟 NUEVAS VARIABLES PARA EL SCROLL INFINITO
let paginaActual = 1;       // Empezamos siempre mostrando el primer lote (Página 1)
let cargandoProductos = false; // Nos avisa si el sistema está ocupado hablando con FastAPI
let finDeStock = false;     // Se volverá true cuando Python nos devuelva una lista vacía []
let categoriaSeleccionadaActual = "Todos"; // 🌟 NUEVO: Sabe qué botón lateral está activo
let promosGlobales = [];
let vistaActual = "CATALOGO"; // "CATALOGO" | "PROMOCIONES" | "COMBOS"
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
        }    
        // 2. SECCIÓN ARTÍCULOS PAGINADOS: Le pasamos el número de página dinámico a FastAPI
        let urlArticulos = `/api/articulos/?pagina=${paginaActual}&categoria=${categoriaSeleccionadaActual}`;
        if (presentacionSeleccionadaActual) {
            urlArticulos += `&presentacion=${presentacionSeleccionadaActual.codigo}`;
            if (presentacionSeleccionadaActual.codigo === "NORMAL" && presentacionSeleccionadaActual.unidad) {
                urlArticulos += `&unidad=${encodeURIComponent(presentacionSeleccionadaActual.unidad)}`;
            }
        }
        const respuestaArticulos = await fetch(urlArticulos);
        
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

            // 🌟 VALIDACIÓN CLAVE: Si Python nos devuelve una lista vacía [], significa que no hay más stock
        if (nuevosArticulos.length === 0) {
                finDeStock = true; // Apagamos el motor del scroll infinito para siempre
                cargandoProductos = false;
                console.log("¡Llegamos al final de la base de datos de SQL Server!");
                return;
        }

            // 🌟 ACUMULACIÓN: Sumamos los 50 artículos nuevos al final de la lista maestra
            articulosGlobales = [...articulosGlobales, ...nuevosArticulos];

             // Mandamos a dibujar la lista completa acumulada en la cuadrícula
            dibujarArticulos(articulosGlobales);

             // Apagamos el semáforo: El sistema ya está libre para la siguiente página
            cargandoProductos = false;
    } catch (error) {
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
            document.getElementById("vista-catalogo").style.display = "block";
            document.getElementById("vista-promociones").style.display = "none";
            vistaCombosUI.style.display = "none";
            vistaActual = "CATALOGO";

            // Restablecemos el texto del botón enérgico de la cabecera
            const btnVerPromosUI = document.getElementById("btn-ver-promos");
            if (btnVerPromosUI) btnVerPromosUI.innerHTML = "🔥 Ver Promos";

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
            // 🌟 PASO B: REINICIAMOS LOS CONTROLES DEL MOTOR DE SCROLL
            paginaActual = 1;          // Volvemos al primer lote de 30
            finDeStock = false;        // Encendemos el motor por si estaba apagado
            articulosGlobales = [];    // Vaciamos la lista vieja para que no se mezclen los artículos
            // Regla: nunca reutilizar la presentacion elegida en otra categoria
            presentacionesDisponibles = [];
            presentacionSeleccionadaActual = null;

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

// Consulta las formas de compra disponibles para una categoria especifica
// y decide si carga directo, muestra un selector minimo, o no hay nada que mostrar.
async function cargarPresentacionesDeLaCategoria(categoria) {
    try {
        const respuesta = await fetch(
            `/api/articulos/presentaciones?categoria=${encodeURIComponent(categoria)}`
        );

        // 🌟 PROTECCIÓN: si el usuario ya cambió de categoría mientras esta
        // respuesta viajaba por la red, la descartamos (incluso si vino con error).
        if (categoria !== categoriaSeleccionadaActual) {
            return;
        }

        if (!respuesta.ok) {
            const errorData = await respuesta.json();
            alert(`Error ${respuesta.status}: ${errorData.detail || 'No se pudieron cargar las formas de compra'}`);
            return;
        }

        const datos = await respuesta.json();

        // 🌟 misma protección, ahora despues del segundo await (parseo del JSON)
        if (categoria !== categoriaSeleccionadaActual) {
            return;
        }

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

        divCard.innerHTML = `
            <div class="imagen-producto">
                <img src="${articulo.imagen}" alt="${articulo.nombre}" loading="lazy">
            </div>
            <div class="info-producto">
                <h3>${articulo.nombre}</h3>
                <p class="precio"><span class="precio-moneda">PYG</span> ${articulo.precio.toLocaleString('es-ES', { maximumFractionDigits: 0 })}</p>
                <div class="etiquetas-producto">
                    <span class="stock-info ${sinStock ? 'agotado' : 'disponible'}">
                        ${sinStock ? 'Sin stock' : `Stock: ${esUnidadWebEntera(articulo) ? maximoVendibleWeb(articulo) : articulo.stock_disponible}`}
                    </span>
                    ${etiquetaUnidad ? `<span class="unidad-producto">${etiquetaUnidad}</span>` : ''}
                </div>
            </div>
            <button class="btn-comprar" ${bloqueado ? "disabled" : ""}>${textoBoton}</button>
        `;

        const botonComprar = divCard.querySelector(".btn-comprar");
        if (!bloqueado) {
            botonComprar.addEventListener("click", () => {
                comprarArticulo(articulo.id);
            });
        }

        contenedor.appendChild(divCard);
    });
}

// 5. SELECCIONAR Y AGRUPAR ARTÍCULO EN EL CARRITO
function comprarArticulo(idArticulo) {
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
        // 2. 🌟 BUSQUEDA INTELIGENTE: Primero intentamos buscarlo en la lista de Ofertas
        let articuloBaseDeDatos = promosGlobales.find(art => art.id === idArticulo);

        if (articuloBaseDeDatos) {
            // 🌟 Si el mismo articulo tambien esta en el catalogo, completamos su metadata
            // (stock_disponible, unidad_venta, fraccionable), manteniendo el precio promocional.
            const articuloCatalogo =
                articulosGlobales.find(art => art.id === idArticulo)
                || combosGlobales.find(art => art.id === idArticulo);
            if (articuloCatalogo) {
                articuloBaseDeDatos = { ...articuloCatalogo, ...articuloBaseDeDatos };
            }
        } else {
            // Si no estaba en las ofertas, significa que es un producto normal del inicio
            articuloBaseDeDatos = articulosGlobales.find(art => art.id === idArticulo);
        }

        // Fallback: solo si no estaba en promociones ni en el catálogo
        if (!articuloBaseDeDatos) {
            articuloBaseDeDatos = combosGlobales.find(art => art.id === idArticulo);
        }

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

// Función para conectar el Frontend con tu endpoint corregido de FastAPI
async function cargarPromocionesDeLaAPI() {
    try {
        // Conexión directa a tu endpoint con la barra '/' al final para evitar desvíos
        const respuesta = await fetch("/api/promos/");
        if (!respuesta.ok) throw new Error("Error en el servidor de ofertas");
        
        const productosPromos = await respuesta.json();
        // 🌟 LA CLAVE: Guardamos las ofertas en la memoria global antes de vaciar la pantalla
        promosGlobales = productosPromos; 
        contenedorCardsPromosUI.innerHTML = "";

        if (productosPromos.length === 0) {
            contenedorCardsPromosUI.innerHTML = `<h3>⚠️ No hay promociones activas por el momento. ¡Vuelve pronto!</h3>`;
            return;
        }

        // Dibujamos las tarjetas usando exactamente tu misma lógica de tarjetas de inicio
        productosPromos.forEach(articulo => {
            const divCard = document.createElement("div");
            divCard.className = "card-producto"; // Tu misma clase CSS de tarjetas

            divCard.innerHTML = `
                <img src="${articulo.imagen}" alt="${articulo.nombre}">
                <h3>${articulo.nombre}</h3>
                <p class="precio" style="color: #e74c3c;">PYG ${articulo.precio.toLocaleString('es-ES', { maximumFractionDigits: 0 })}</p>
                <button class="btn-comprar">🛒 AGREGAR AL CARRITO </button>
            `;
            
            // Al hacer clic, ejecuta tu función comprarArticulo original (La que ya suma a la burbuja)
            const botonComprar = divCard.querySelector(".btn-comprar");
            botonComprar.addEventListener("click", () => {
                comprarArticulo(articulo.id); 
            });

            contenedorCardsPromosUI.appendChild(divCard);
        });

        promosDescargadas = true; // Bloqueamos para no repetir la consulta si vuelve a hacer clic
    } catch (error) {
        console.error("Error crítico en la sección de promociones:", error);
        contenedorCardsPromosUI.innerHTML = "<p>Error al conectar con el servidor de ofertas.</p>";
    }
}

// ----------------------------------------------------
// ESCUCHADORES DE EVENTOS PRINCIPALES
// ----------------------------------------------------

// Evento para la barra de búsqueda por texto
txtBuscarUI.addEventListener("input", (evento) => {
    // Si el cliente estaba en Promos o Combos, la búsqueda vuelve al catálogo para mostrar resultados
    if (vistaActual !== "CATALOGO") {
        vistaCatalogoUI.style.display = "block";
        vistaPromocionesUI.style.display = "none";
        vistaCombosUI.style.display = "none";
        vistaActual = "CATALOGO";
        btnVerPromosUI.innerHTML = "🔥 Ver Promos";
    }

    const textoUsuario = evento.target.value.toLowerCase();
    const articulosFiltrados = articulosGlobales.filter(articulo => {
        return articulo.nombre.toLowerCase().includes(textoUsuario);
    });
    dibujarArticulos(articulosFiltrados);
});

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
            const datosError = await respuestaServer.json();
            alert(`❌ No se pudo guardar el pedido: ${datosError.detail || 'Error desconocido'}`);
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

// 🌟 LÓGICA DEL BANNER DINÁMICO AUTOMÁTICO
document.addEventListener("DOMContentLoaded", () => {
    const slides = document.querySelectorAll(".banner-slide");
    const puntos = document.querySelectorAll(".punto");
    let slideActual = 0;
    const tiempoCambio = 5000; // 5000 milisegundos = 5 segundos

    function cambiarSlide(indice) {
        // Quitamos la clase activo de todos los slides y puntos
        slides.forEach(slide => slide.classList.remove("activo"));
        puntos.forEach(punto => punto.classList.remove("activo"));

        // Activamos el slide y punto correspondiente
        slides[indice].classList.add("activo");
        puntos[indice].classList.add("activo");
        slideActual = indice;
    }

    function siguienteSlide() {
        let siguiente = slideActual + 1;
        if (siguiente >= slides.length) {
            siguiente = 0; // Si llega al final, vuelve al primero
        }
        cambiarSlide(siguiente);
    }

    // Iniciar el temporizador automático
    let intervaloBanner = setInterval(siguienteSlide, tiempoCambio);

    // Permitir hacer clic en los puntitos para saltar a una imagen
    puntos.forEach((punto, index) => {
        punto.addEventListener("click", () => {
            cambiarSlide(index);
            // Reiniciamos el temporizador para que no cambie de golpe justo después del clic
            clearInterval(intervaloBanner);
            intervaloBanner = setInterval(siguienteSlide, tiempoCambio);
        });
    });
});

// Variable de control para no saturar a SQL Server con llamadas repetidas
let promosDescargadas = false;

// Evento para el botón enérgico de Promociones
btnVerPromosUI.addEventListener("click", async () => {
    // Si la pantalla de ofertas está oculta, la encendemos y apagamos el catálogo normal
    if (vistaPromocionesUI.style.display === "none") {
        vistaCatalogoUI.style.display = "none";
        vistaPromocionesUI.style.display = "block";
        vistaCombosUI.style.display = "none";
        vistaActual = "PROMOCIONES";
        btnVerPromosUI.innerHTML = "⬅️ Ver Catálogo"; // Cambia el texto del botón temporalmente
        irAlInicioDeLaVista(vistaPromocionesUI);

        // Cambiamos la URL estéticamente a nivel profesional sin recargar el navegador
        window.history.pushState({}, "", "/promos");
        
        // Si es la primera vez que hace clic, vamos a buscar los datos a SQL Server
        if (!promosDescargadas) {
            await cargarPromocionesDeLaAPI();
        }
    } else {
        // Si ya estaba visible, el usuario quiere regresar a ver todos los artículos
        vistaPromocionesUI.style.display = "none";
        vistaCatalogoUI.style.display = "block";
        vistaActual = "CATALOGO";
        btnVerPromosUI.innerHTML = "🔥 Ver Promos"; // Restablece el texto original del botón
        irAlInicioDeLaVista(vistaCatalogoUI);

        // Regresamos la URL al inicio estéticamente
        window.history.pushState({}, "", "/");
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
        btnMasCombosUI.style.display = nuevos.length === LIMITE_COMBOS ? "inline-block" : "none";
    } catch (error) {
        console.error("No se pudieron cargar los combos:", error);
        btnVerCombosUI.style.display = "none";
        btnMasCombosUI.style.display = "none";
    }
}

btnVerCombosUI.addEventListener("click", () => {
    vistaCatalogoUI.style.display = "none";
    vistaPromocionesUI.style.display = "none";
    vistaCombosUI.style.display = "block";
    vistaActual = "COMBOS";
    window.history.pushState({}, "", "/combos");
    dibujarArticulos(combosGlobales, contenedorCardsCombosUI);
    irAlInicioDeLaVista(vistaCombosUI);
});

btnMasCombosUI.addEventListener("click", async () => {
    await cargarCombosDeLaAPI(paginaCombos + 1);
    dibujarArticulos(combosGlobales, contenedorCardsCombosUI);
});

// Arrancamos la aplicación leyendo la API
cargarDatosDeLaAPI();
cargarCombosDeLaAPI();
