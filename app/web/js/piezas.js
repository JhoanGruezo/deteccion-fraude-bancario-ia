/**
 * Piezas visuales compartidas por las vistas del Momento 3 (chips de banda y de actor,
 * barras de score, estados vacíos, confirmación genérica).
 *
 * El color es el significado y es el mismo en toda la app: crítica = rojo, alta =
 * naranja, media = ámbar, sin alerta = neutro; agente IA = violeta, regla = gris
 * azulado, analista = verde. Todo se construye con `el()`, nunca con innerHTML: alias,
 * comercios y motivos vienen de datos que un atacante puede controlar.
 */

import { el, icono } from "./dom.js";
import * as f from "./formato.js";

/** Chip de banda de riesgo ("Crítica", "Alta"…). */
export function chipBanda(codigo, { conTitulo = true } = {}) {
  const b = f.banda(codigo);
  return el("span", { clase: `chip-banda banda-${b.clase}`, title: conTitulo ? `Banda de riesgo: ${b.etiqueta}` : null, texto: b.etiqueta });
}

/** Quién actuó, con su ícono: Agente IA, Regla de respaldo o Analista (usuario). */
export function chipActor(codigo, usuario) {
  const a = f.actor(codigo);
  const texto = codigo === "analista" && usuario ? `${a.etiqueta} · ${usuario}` : a.etiqueta;
  return el("span", { clase: `chip-actor actor-${a.clase}` }, icono(a.icono), el("span", { texto }));
}

/** Barra horizontal del score (0-1) con la cifra al lado. */
export function barraScore(score, codigoBanda) {
  const valor = Math.max(0, Math.min(1, Number(score) || 0));
  return el(
    "span",
    { clase: `score banda-${f.banda(codigoBanda).clase}`, title: `Score ${f.puntaje(valor)}` },
    el("span", { clase: "score__pista", "aria-hidden": "true" }, el("span", { clase: "score__relleno", estilo: { "--valor": `${(valor * 100).toFixed(1)}%` } })),
    el("span", { clase: "score__cifra", texto: f.puntaje(valor) }),
  );
}

/** Medidor de uso (12 de 30) con tono según qué tan cerca está del tope. */
export function medidorUso(usado, tope, { etiqueta } = {}) {
  const u = Number(usado) || 0;
  const t = Number(tope) || 0;
  const proporcion = t > 0 ? Math.min(1, u / t) : u > 0 ? 1 : 0;
  const tono = proporcion >= 1 ? "lleno" : proporcion >= 0.8 ? "cerca" : "normal";
  return el(
    "div",
    {
      clase: `uso uso--${tono}`,
      role: "meter",
      "aria-valuemin": "0",
      "aria-valuemax": String(t || 1),
      "aria-valuenow": String(Math.min(u, t || u)),
      "aria-label": etiqueta || "Uso",
    },
    el("span", { clase: "uso__relleno", estilo: { "--valor": `${(proporcion * 100).toFixed(1)}%` } }),
  );
}

/** Estado vacío con ícono, título, texto y acciones opcionales. */
export function estadoVacio({ iconoNombre = "info", titulo, texto, acciones = [] }) {
  return el(
    "div",
    { clase: "vacio-chico" },
    icono(iconoNombre, "vacio-chico__icono"),
    el("p", { clase: "vacio-chico__titulo", texto: titulo }),
    texto ? el("p", { clase: "vacio-chico__texto", texto }) : null,
    acciones.length ? el("div", { clase: "vacio-chico__acciones" }, acciones) : null,
  );
}

/** Mensaje de error de carga con "Reintentar". */
export function estadoError(mensaje, alReintentar) {
  return el(
    "div",
    { clase: "vacio-chico vacio-chico--error", role: "alert" },
    icono("error", "vacio-chico__icono"),
    el("p", { clase: "vacio-chico__titulo", texto: "No se pudo cargar." }),
    el("p", { clase: "vacio-chico__texto", texto: mensaje }),
    alReintentar ? el("div", { clase: "vacio-chico__acciones" }, el("button", { type: "button", clase: "boton boton--secundario boton--chico", texto: "Reintentar", onClick: alReintentar })) : null,
  );
}

/** Esqueleto de carga (rectángulos grises) mientras llega la primera respuesta. */
export function esqueleto(filas = 3) {
  return el("div", { clase: "esqueleto", "aria-hidden": "true" }, Array.from({ length: filas }, () => el("span", { clase: "esqueleto__fila" })));
}

/** Enlace a un caso (#/caso/ID). */
export function enlaceCaso(idCaso, texto) {
  if (!idCaso) return null;
  return el("a", { clase: "enlace-caso", href: `#/caso/${encodeURIComponent(idCaso)}`, title: `Abrir el caso ${idCaso}` }, el("span", { clase: "mono", texto: texto || idCaso }), icono("flecha"));
}

/**
 * Confirmación genérica con <dialog> (nunca confirm()). Devuelve true si se acepta.
 * Usa el diálogo #dialogo-confirmar de index.html.
 */
export function confirmar({ titulo, texto, textoBoton = "Aceptar", peligro = false }) {
  const $ = (id) => document.getElementById(id);
  const dialogo = $("dialogo-confirmar");
  $("dialogo-confirmar-titulo").textContent = titulo;
  $("dialogo-confirmar-texto").textContent = texto;
  const aceptar = $("dialogo-confirmar-aceptar");
  aceptar.textContent = textoBoton;
  aceptar.className = `boton ${peligro ? "boton--peligro" : "boton--primario"}`;
  dialogo.returnValue = "";
  dialogo.showModal();
  $("dialogo-confirmar-cancelar").focus();
  return new Promise((resolver) => {
    dialogo.addEventListener("close", () => resolver(dialogo.returnValue === "aceptar"), { once: true });
  });
}
