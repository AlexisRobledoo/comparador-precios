// =========================================================
// Comparador de Precios Rosario — la web habla con NUESTRA API
// =========================================================

const $ = (id) => document.getElementById(id);
const pesos = new Intl.NumberFormat("es-AR", { style: "currency", currency: "ARS", maximumFractionDigits: 0 });

// Crea un elemento HTML con texto. Usamos textContent (no innerHTML) porque los
// nombres vienen de los datos y así evitamos que se ejecute código raro.
function crear(tag, clase, texto) {
  const el = document.createElement(tag);
  if (clase) el.className = clase;
  if (texto !== undefined) el.textContent = texto;
  return el;
}

function aviso(texto) {
  const t = $("toast");
  t.textContent = texto;
  t.classList.add("show");
  clearTimeout(aviso.timer);
  aviso.timer = setTimeout(() => t.classList.remove("show"), 2000);
}

// ---------------------------------------------------------------------------
// 1) RESUMEN (fecha de los datos)
// ---------------------------------------------------------------------------
async function cargarResumen() {
  try {
    const r = await (await fetch("/api/resumen")).json();
    const fecha = new Date(r.fecha_datos + "T12:00:00").toLocaleDateString("es-AR");
    const cadenas = r.cadenas.map((c) => c.nombre).join(", ");
    $("resumen").textContent =
      `${r.productos.toLocaleString("es-AR")} productos en ${r.sucursales} sucursales de Gran Rosario · ${cadenas} · Precios del ${fecha}`;
  } catch {
    $("resumen").textContent = "No se pudieron cargar los datos.";
  }
}

// ---------------------------------------------------------------------------
// 2) BÚSQUEDA (espera que dejes de escribir 300 ms antes de buscar)
// ---------------------------------------------------------------------------
let temporizador;
$("buscador").addEventListener("input", (e) => {
  clearTimeout(temporizador);
  temporizador = setTimeout(() => buscar(e.target.value), 300);
});
$("formBuscar").addEventListener("submit", (e) => { e.preventDefault(); buscar($("buscador").value); });

$("sugerencias").addEventListener("click", (e) => {
  if (e.target.tagName !== "BUTTON") return;
  $("buscador").value = e.target.textContent;
  buscar(e.target.textContent);
});

async function buscar(texto) {
  texto = texto.trim();
  const lista = $("resultados");
  if (texto.length < 2) { lista.replaceChildren(); $("estado").textContent = ""; return; }

  $("estado").textContent = "Buscando…";
  const r = await fetch(`/api/buscar?q=${encodeURIComponent(texto)}&limite=40`);
  const productos = await r.json();

  $("estado").textContent = productos.length
    ? `${productos.length} resultado${productos.length > 1 ? "s" : ""} para "${texto}"`
    : `No encontré nada para "${texto}". Probá con menos palabras.`;

  lista.replaceChildren(...productos.map(tarjeta));
}

function tarjeta(p) {
  const card = crear("button", "card");
  card.type = "button";
  card.append(crear("span", "card__brand", p.marca || " "));
  card.append(crear("span", "card__name", p.descripcion));
  card.append(crear("span", "card__meta", `${p.presentacion} · en ${p.cadenas} cadena${p.cadenas > 1 ? "s" : ""}`));

  const precio = crear("span", "card__price");
  precio.append(crear("span", "card__from", "desde"), crear("span", "card__min", pesos.format(p.precio_min)));
  if (p.precio_max > p.precio_min) {
    const dif = Math.round((1 - p.precio_min / p.precio_max) * 100);
    precio.append(crear("span", "pill", `hasta ${dif}% menos`));
  }
  card.append(precio);
  card.addEventListener("click", () => abrirProducto(p.ean));
  return card;
}

// ---------------------------------------------------------------------------
// 3) DETALLE DE UN PRODUCTO
// ---------------------------------------------------------------------------
let productoActual = null;

async function abrirProducto(ean) {
  const p = await (await fetch(`/api/productos/${ean}`)).json();
  productoActual = p;

  $("modalMarca").textContent = p.marca || "";
  $("modalTitulo").textContent = p.descripcion;
  $("modalMeta").textContent = `${p.presentacion} · Código ${p.ean}`;

  const mas_barato = p.precios[0];
  $("modalAhorro").textContent = p.ahorro_maximo > 0
    ? `💡 Comprándolo en ${mas_barato.cadena} ahorrás hasta ${pesos.format(p.ahorro_maximo)} contra el más caro.`
    : "El precio es el mismo en todas las sucursales.";

  const minimo = mas_barato.precio_final;
  $("modalPrecios").replaceChildren(...p.precios.map((s) => {
    const li = crear("li", "store" + (s.precio_final === minimo ? " best" : ""));
    li.append(crear("span", "store__chain", s.cadena));
    const precio = crear("span", "store__price", pesos.format(s.precio_final));
    if (s.precio_promo) precio.append(crear("span", "store__old", pesos.format(s.precio)));
    li.append(precio);
    li.append(crear("span", "store__addr", `${s.sucursal} · ${s.direccion}, ${s.localidad}`));
    if (s.promo) li.append(crear("span", "store__promo", "🏷️ " + s.promo.split(" - ")[0]));
    return li;
  }));

  $("modal").showModal();
}

$("cerrarModal").addEventListener("click", () => $("modal").close());
$("modal").addEventListener("click", (e) => { if (e.target === $("modal")) $("modal").close(); });

$("agregar").addEventListener("click", () => {
  if (!productoActual) return;
  agregarAlCarrito(productoActual.ean, productoActual.descripcion);
  $("modal").close();
});

// ---------------------------------------------------------------------------
// 4) CHANGUITO (se guarda en el navegador para no perderlo al recargar)
// ---------------------------------------------------------------------------
let carrito = [];
try { carrito = JSON.parse(localStorage.getItem("changuito") || "[]"); } catch { carrito = []; }

function guardar() {
  try { localStorage.setItem("changuito", JSON.stringify(carrito)); } catch { /* sin problema */ }
}

function agregarAlCarrito(ean, nombre) {
  const item = carrito.find((i) => i.ean === ean);
  if (item) item.cantidad++;
  else carrito.push({ ean, nombre, cantidad: 1 });
  aviso("✓ Agregado al changuito");
  actualizarCarrito();
}

function cambiarCantidad(ean, delta) {
  const item = carrito.find((i) => i.ean === ean);
  if (!item) return;
  item.cantidad += delta;
  if (item.cantidad <= 0) carrito = carrito.filter((i) => i.ean !== ean);
  actualizarCarrito();
}

async function actualizarCarrito() {
  guardar();
  const total = carrito.reduce((s, i) => s + i.cantidad, 0);
  $("contador").textContent = total;
  $("carritoVacio").hidden = carrito.length > 0;
  $("vaciar").hidden = carrito.length === 0;

  $("itemsCarrito").replaceChildren(...carrito.map((i) => {
    const li = crear("li", "cart__item");
    li.append(crear("span", "cart__item-name", i.nombre));
    const qty = crear("span", "qty");
    const menos = crear("button", "", "−"); menos.type = "button"; menos.setAttribute("aria-label", "Quitar uno");
    const mas = crear("button", "", "+"); mas.type = "button"; mas.setAttribute("aria-label", "Agregar uno");
    menos.addEventListener("click", () => cambiarCantidad(i.ean, -1));
    mas.addEventListener("click", () => cambiarCantidad(i.ean, +1));
    qty.append(menos, crear("span", "", i.cantidad), mas);
    li.append(qty);
    return li;
  }));

  await compararCarrito();
}

async function compararCarrito() {
  const caja = $("comparacion");
  if (!carrito.length) { caja.replaceChildren(); return; }

  // Le mandamos a la API la lista y nos devuelve el total en cada cadena
  const r = await fetch("/api/changuito", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ items: carrito.map(({ ean, cantidad }) => ({ ean, cantidad })) }),
  });
  const datos = await r.json();

  const lista = crear("ol", "rank");
  datos.cadenas.forEach((c, i) => {
    const li = crear("li", i === 0 && c.faltantes === 0 ? "best" : "");
    const nombre = crear("span", "", (i === 0 && c.faltantes === 0 ? "🏆 " : "") + c.cadena);
    if (c.faltantes) nombre.append(crear("span", "falta", `No tiene ${c.faltantes} producto${c.faltantes > 1 ? "s" : ""}`));
    li.append(nombre, crear("span", "total", pesos.format(c.total)));
    lista.append(li);
  });

  const completas = datos.cadenas.filter((c) => c.faltantes === 0);
  const elementos = [crear("h3", "", "¿Dónde conviene comprar todo?"), lista];
  if (completas.length > 1) {
    const ahorro = completas[completas.length - 1].total - completas[0].total;
    elementos.push(crear("p", "save-note", `Ahorrás ${pesos.format(ahorro)} comprando en ${completas[0].cadena} en vez de ${completas[completas.length - 1].cadena}.`));
  }
  caja.replaceChildren(...elementos);
}

$("vaciar").addEventListener("click", () => { carrito = []; actualizarCarrito(); });

// En el celular, el changuito es un panel que se abre y se cierra
$("abrirCarrito").addEventListener("click", () => $("carrito").classList.add("open"));
$("cerrarCarrito").addEventListener("click", () => $("carrito").classList.remove("open"));

// ---------------------------------------------------------------------------
// ARRANQUE
// ---------------------------------------------------------------------------
cargarResumen();
actualizarCarrito();
