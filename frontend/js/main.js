// 1. CAPTURA DE ELEMENTOS DE LA PANTALLA (UI)
const listaCategoriasUI = document.getElementById("lista-categorias");
const contenedorCardsUI = document.getElementById("contenedor-cards");
const txtBuscarUI = document.getElementById("txt-buscar"); 
const contadorCarritoUI = document.getElementById("contador-carrito"); 

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

// 2. CARGAR DATOS DESDE FASTAPI (SQL SERVER)
async function cargarDatosDeLaAPI() {
    // Si ya estamos cargando o si llegamos al final de la base de datos, frenamos por seguridad

    if (cargandoProductos || finDeStock) return;
    cargandoProductos = true; // Encendemos el semáforo en rojo: "Ocupado"
    
    try {
        // Sección Categorías
        // 1. SECCIÓN CATEGORÍAS: Se cargan una sola vez al inicio
        if (categoriasGlobales.length === 0) {
            const respuestaCategorias = await fetch("/api/categorias");
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
        const respuestaArticulos = await fetch(`/api/articulos?pagina=${paginaActual}&categoria=${categoriaSeleccionadaActual}`);
        
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
            const todosLosBotones = document.querySelectorAll(".btn-categoria");
            todosLosBotones.forEach(btn => btn.classList.remove("activo"));
            boton.classList.add("activo");  

            // 🌟 PASO A: Guardamos la categoría seleccionada
            categoriaSeleccionadaActual = categoria.nombre;
            // 🌟 PASO B: REINICIAMOS LOS CONTROLES DEL MOTOR DE SCROLL
            paginaActual = 1;          // Volvemos al primer lote de 30
            finDeStock = false;        // Encendemos el motor por si estaba apagado
            articulosGlobales = [];    // Vaciamos la lista vieja para que no se mezclen los artículos

            // 🌟 PASO C: Vamos a buscar el lote N°1 de esta categoría a SQL Server
            cargarDatosDeLaAPI();
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

// 4. DIBUJAR TARJETAS DE PRODUCTOS
function dibujarArticulos(listaArticulos) {
    contenedorCardsUI.innerHTML = "";

    if (listaArticulos.length === 0) {
        contenedorCardsUI.innerHTML = `
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

        divCard.innerHTML = `
            <img src="${articulo.imagen}" alt="${articulo.nombre}">
            <h3>${articulo.nombre}</h3>
            <p class="precio">PYG ${articulo.precio.toLocaleString('es-ES', { maximumFractionDigits: 0 })}</p>
            <button class="btn-comprar">🛒 AGREGAR AL CARRITO </button>
        `;
        
        const botonComprar = divCard.querySelector(".btn-comprar");
        botonComprar.addEventListener("click", () => {
            comprarArticulo(articulo.id); 
        });

        contenedorCardsUI.appendChild(divCard);
    });
}

// 5. SELECCIONAR Y AGRUPAR ARTÍCULO EN EL CARRITO
function comprarArticulo(idArticulo) {
    // Buscamos si el artículo ya existía en la canasta
    const articuloEnCarrito = carrito.find(art => art.id === idArticulo);

    if (articuloEnCarrito) {
        articuloEnCarrito.cantidad++; // Si ya existía, simplemente aumentamos su cantidad
    } else {
        // Si es nuevo, lo buscamos en el catálogo maestro que vino de SQL Server
        const articuloBaseDeDatos = articulosGlobales.find(art => art.id === idArticulo);
        if (articuloBaseDeDatos) {
            // Creamos una copia del producto inyectándole la cantidad inicial en 1
            const nuevoItem = { ...articuloBaseDeDatos, cantidad: 1 };
            carrito.push(nuevoItem);
        }
    }

    // Actualizamos la burbuja roja sumando todas las unidades acumuladas en tiempo real
    actualizarBurbujaCabecera();
}

// 6. DIBUJAR LISTADO DENTRO DE LA VENTANA EMERGENTE (CON INTERACTIVIDAD EN + Y -)
function dibujarCarrito() {
    listaProductosCarritoUI.innerHTML = "";
    let sumaTotal = 0;

    carrito.forEach((articulo) => {
        const subtotalRenglon = articulo.precio * articulo.cantidad;
        sumaTotal += subtotalRenglon;   

        const li = document.createElement("li");
        li.className = "renglon-carrito"; 

        li.innerHTML = `
            <div class="carrito-bloque-izq">
                <img src="${articulo.imagen}" alt="${articulo.nombre}" class="miniatura-carrito">
                <div class="carrito-detalles">
                    <h4>${articulo.nombre}</h4>
                    <span class="codigo-articulo">Art. ${articulo.id}</span>
                </div>
            </div>
            
            <div class="carrito-bloque-der">
                <div class="control-cantidad">
                    <button class="btn-cantidad-menos">-</button>
                    <span class="cantidad-numero">${articulo.cantidad}</span>
                    <button class="btn-cantidad-mas">+</button>
                </div>
                <p class="precio-renglon">PYG ${subtotalRenglon.toLocaleString('es-ES', { maximumFractionDigits: 0 })}</p>
                <button class="btn-eliminar-item">🗑️</button>
            </div>
        `;

        // 🌟 CAPTURAMOS LOS CONTROLES INTERNOS DEL RENGLÓN RECIÉN CREADO
        const btnMenos = li.querySelector(".btn-cantidad-menos");
        const btnMas = li.querySelector(".btn-cantidad-mas");
        const btnEliminar = li.querySelector(".btn-eliminar-item");

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
            articulo.cantidad++;
            actualizarBurbujaCabecera();
            dibujarCarrito();
        });

        // Evento para el tacho de basura
        btnEliminar.addEventListener("click", () => {
            eliminarArticuloDelCarrito(articulo.id);
        });

        listaProductosCarritoUI.appendChild(li);
    });

    totalCarritoUI.textContent = `PYG ${sumaTotal.toLocaleString('es-ES', { maximumFractionDigits: 0 })}`;
}

// 7. ELIMINAR COMPLETAMENTE UN RENGLÓN DEL CARRITO
function eliminarArticuloDelCarrito(idArticulo) {
    carrito = carrito.filter(art => art.id !== idArticulo);
    actualizarBurbujaCabecera();
    dibujarCarrito(); // Redibujamos la lista de la modal
}

// 🌟 FUNCIÓN AUXILIAR: Cuenta todas las unidades del carrito y refresca la burbuja roja
function actualizarBurbujaCabecera() {
    const totalUnidades = carrito.reduce((suma, art) => suma + art.cantidad, 0);
    contadorCarritoUI.textContent = totalUnidades;
}

// ----------------------------------------------------
// ESCUCHADORES DE EVENTOS PRINCIPALES
// ----------------------------------------------------

// Evento para la barra de búsqueda por texto
txtBuscarUI.addEventListener("input", (evento) => {
    const textoUsuario = evento.target.value.toLowerCase();
    const articulosFiltrados = articulosGlobales.filter(articulo => {
        return articulo.nombre.toLowerCase().includes(textoUsuario);
    });
    dibujarArticulos(articulosFiltrados);
});

// Evento para abrir la ventana del carrito
btnVerCarritoUI.addEventListener("click", () => {
    if (carrito.length>0){
        dibujarCarrito(); // Construye los renglones antes de abrir
        modalCarritoUI.style.display = "flex";
    }else{
        alert('No existe articulos en el carrito')
    }    
});

// Eventos para cerrar la ventana del carrito
btnCerrarModalUI.addEventListener("click", () => {
    modalCarritoUI.style.display = "none";
});

window.addEventListener("click", (evento) => {
    if (evento.target === modalCarritoUI) {
        modalCarritoUI.style.display = "none";
    }
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
            modalCarritoUI.style.display = "none";  // Cerramos la ventana flotante

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


// Arrancamos la aplicación leyendo la API
cargarDatosDeLaAPI();
