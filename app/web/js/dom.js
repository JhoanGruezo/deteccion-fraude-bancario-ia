/**
 * Ayudas mínimas para construir el DOM sin innerHTML.
 *
 * Todo el texto que pinta la interfaz viene de datos (nombres de comercios, la
 * respuesta del modelo): si se metiera con innerHTML, un comercio llamado
 * "<img onerror=…>" ejecutaría código. Con `el()` todo texto entra como nodo de texto.
 */

/**
 * Crea un elemento. `atributos` admite: clase, texto, dataset, estilo (propiedades CSS
 * personalizadas) y on<Evento>; el resto va como atributo. Los hijos pueden ser nodos,
 * textos, null/false (se ignoran) o listas.
 */
export function el(etiqueta, atributos = {}, ...hijos) {
  const nodo = document.createElement(etiqueta);
  for (const [clave, valor] of Object.entries(atributos || {})) {
    if (valor === null || valor === undefined || valor === false) continue;
    if (clave === "clase") nodo.className = valor;
    else if (clave === "texto") nodo.textContent = valor;
    else if (clave === "dataset") Object.assign(nodo.dataset, valor);
    else if (clave === "estilo") for (const [prop, v] of Object.entries(valor)) nodo.style.setProperty(prop, v);
    else if (clave.startsWith("on") && typeof valor === "function") nodo.addEventListener(clave.slice(2).toLowerCase(), valor);
    else if (valor === true) nodo.setAttribute(clave, "");
    else nodo.setAttribute(clave, String(valor));
  }
  agregar(nodo, hijos);
  return nodo;
}

function agregar(nodo, hijos) {
  for (const hijo of hijos) {
    if (hijo === null || hijo === undefined || hijo === false) continue;
    if (Array.isArray(hijo)) agregar(nodo, hijo);
    else nodo.append(hijo instanceof Node ? hijo : document.createTextNode(String(hijo)));
  }
}

/**
 * Texto del modelo con un formato mínimo y seguro: **negritas** y saltos de línea.
 * Devuelve un DocumentFragment hecho de nodos de texto, <strong> y <br>; nunca
 * interpreta HTML. Un "**" sin cerrar (el texto todavía está llegando) se deja tal cual.
 */
export function textoConFormato(texto) {
  const fragmento = document.createDocumentFragment();
  const lineas = String(texto ?? "").split("\n");
  lineas.forEach((linea, i) => {
    if (i > 0) fragmento.append(document.createElement("br"));
    let ultimo = 0;
    for (const m of linea.matchAll(/\*\*(.+?)\*\*/g)) {
      fragmento.append(linea.slice(ultimo, m.index));
      const fuerte = document.createElement("strong");
      fuerte.textContent = m[1];
      fragmento.append(fuerte);
      ultimo = m.index + m[0].length;
    }
    fragmento.append(linea.slice(ultimo));
  });
  return fragmento;
}

export function vaciar(nodo) {
  while (nodo.firstChild) nodo.removeChild(nodo.firstChild);
  return nodo;
}

const SVG = "http://www.w3.org/2000/svg";

/** Icono del sprite de index.html (`<symbol id="i-…">`), decorativo para lectores de pantalla. */
export function icono(nombre, clase = "icono") {
  const svg = document.createElementNS(SVG, "svg");
  svg.setAttribute("class", clase);
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", "false");
  const uso = document.createElementNS(SVG, "use");
  uso.setAttribute("href", `#i-${nombre}`);
  svg.append(uso);
  return svg;
}

/**
 * Desplaza solo el contenedor con scroll más cercano para que `nodo` quede a la vista.
 *
 * No se usa scrollIntoView porque también desplaza el <body> aunque tenga
 * overflow:hidden, y en pantalla ancha eso esconde la barra superior.
 */
export function desplazarHasta(nodo, { centrar = false } = {}) {
  let contenedor = nodo.parentElement;
  while (contenedor && contenedor !== document.body) {
    const estilo = getComputedStyle(contenedor).overflowY;
    if ((estilo === "auto" || estilo === "scroll") && contenedor.scrollHeight > contenedor.clientHeight) break;
    contenedor = contenedor.parentElement;
  }
  const suave = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (!contenedor || contenedor === document.body) {
    // Sin columna con scroll propio (ventana angosta): se desplaza la página.
    const caja = nodo.getBoundingClientRect();
    if (centrar || caja.top < 0 || caja.bottom > window.innerHeight) {
      window.scrollBy({ top: caja.top - (centrar ? window.innerHeight / 2 - caja.height / 2 : 80), behavior: suave ? "smooth" : "auto" });
    }
    return;
  }
  const caja = nodo.getBoundingClientRect();
  const marco = contenedor.getBoundingClientRect();
  let delta = 0;
  if (centrar) delta = caja.top - marco.top - (marco.height - caja.height) / 2;
  else if (caja.top < marco.top) delta = caja.top - marco.top;
  else if (caja.bottom > marco.bottom) delta = caja.bottom - marco.bottom;
  if (delta) contenedor.scrollBy({ top: delta, behavior: centrar && suave ? "smooth" : "auto" });
}

/** Lleva la vista a un elemento y lo destaca un instante (cifra → evidencia). */
export function destacar(destino) {
  if (!destino) return;
  const plegable = destino.closest("details");
  if (plegable && !plegable.open) plegable.open = true;
  desplazarHasta(destino, { centrar: true });
  destino.classList.remove("destello");
  void destino.offsetWidth; // reinicia la transición si se pulsa dos veces seguidas
  destino.classList.add("destello");
  setTimeout(() => destino.classList.remove("destello"), 1800);
}

/** localStorage puede fallar (modo privado, almacenamiento bloqueado): nunca rompe la app. */
export const almacen = {
  leer(clave, porDefecto = null) {
    try {
      const valor = window.localStorage.getItem(clave);
      return valor === null ? porDefecto : valor;
    } catch {
      return porDefecto;
    }
  },
  guardar(clave, valor) {
    try {
      window.localStorage.setItem(clave, valor);
    } catch {
      /* sin almacenamiento: se recordará solo durante esta sesión */
    }
  },
};

/**
 * Banda de aviso o error con acciones ("Reintentar", "Ver explicación guardada").
 * `acciones`: [{ texto, al, primaria }]. Si `opciones` es null, oculta la banda.
 */
export function pintarBanda(nodo, opciones) {
  vaciar(nodo);
  if (!opciones) {
    nodo.hidden = true;
    return;
  }
  const { titulo, detalle, referencia, tono = "error", acciones = [] } = opciones;
  nodo.className = `banda banda--${tono}${nodo.id === "banda-global" ? " banda--global" : ""}`;
  nodo.append(
    icono(tono === "error" ? "error" : "info"),
    el(
      "div",
      { clase: "banda__texto" },
      el("p", { clase: "banda__titulo", texto: titulo }),
      detalle ? el("p", { clase: "banda__detalle", texto: detalle }) : null,
      referencia ? el("p", { clase: "banda__referencia", texto: `Referencia: ${referencia}` }) : null,
    ),
    acciones.length
      ? el("div", { clase: "banda__acciones" }, acciones.map((a) => el("button", { type: "button", clase: `boton boton--chico ${a.primaria ? "boton--primario" : "boton--secundario"}`, texto: a.texto, onClick: a.al })))
      : null,
  );
  nodo.hidden = false;
}

/** Aviso breve no bloqueante (reemplaza a alert()). */
export function avisar(texto, tono = "info") {
  const zona = document.getElementById("avisos");
  if (!zona) return;
  const aviso = el("div", { clase: `aviso aviso--${tono}`, role: "status" }, icono(tono === "error" ? "error" : "check"), el("span", { texto }));
  zona.append(aviso);
  setTimeout(() => aviso.classList.add("aviso--saliendo"), 3600);
  setTimeout(() => aviso.remove(), 4000);
}
