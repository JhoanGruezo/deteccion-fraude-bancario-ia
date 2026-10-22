/**
 * Panel de trazas: cada paso del agente, en vivo, con sus tiempos y métricas.
 *
 * Es la parte de la pantalla que demuestra que no hay "streaming falso": muestra en el
 * orden real los eventos que llegan por SSE (herramientas pedidas, llamadas al modelo,
 * reintentos, conmutaciones, validación del contrato) y, al final, TTFT, latencia,
 * tokens, costo, iteraciones, proveedor y motivo de fin que reporta el servidor.
 *
 * Los fragmentos de texto (`token`) no se listan uno por uno —serían cientos—: se
 * agrupan en una sola fila por llamada al modelo con el conteo que va subiendo.
 */

import { el, icono, vaciar } from "./dom.js";
import * as f from "./formato.js";

const MAXIMO_TAREAS = 8;
const LARGO_MAXIMO_DETALLE = 6000;

const MOTIVOS_FALLA = {
  cuota: "429 (cuota agotada)",
  429: "429 (cuota agotada)",
  timeout: "tiempo agotado",
  servidor: "error del servidor (5xx)",
  autenticacion: "error de autenticación",
  solicitud: "solicitud rechazada",
  sin_llave: "sin llave configurada",
  agotados: "todos los proveedores fallaron",
  json: "JSON roto",
};
const motivo = (m) => MOTIVOS_FALLA[m] || m || "";
const texto = (v) => (v === null || v === undefined ? "" : typeof v === "string" ? v : JSON.stringify(v));

function argumentosTexto(argumentos) {
  if (!argumentos || typeof argumentos !== "object") return "";
  return Object.entries(argumentos).map(([k, v]) => `${k}: ${texto(v)}`).join(" · ");
}

function resumenTexto(resumen) {
  if (!resumen) return "";
  if (typeof resumen === "string") return resumen;
  const partes = [];
  if (resumen.tamano ?? resumen.tamaño) partes.push(`${f.numero(resumen.tamano ?? resumen.tamaño)} caracteres`);
  if (Array.isArray(resumen.campos)) partes.push(`campos: ${resumen.campos.join(", ")}`);
  return partes.join(" · ") || argumentosTexto(resumen);
}

function limitesTexto(datos) {
  const l = datos.limites || {};
  const partes = [];
  if (l.max_iteraciones) partes.push(`${l.max_iteraciones} iteraciones`);
  if (l.presupuesto_tokens) partes.push(`${f.numero(l.presupuesto_tokens)} tokens`);
  if (l.timeout_modelo_s) partes.push(`${f.numero(l.timeout_modelo_s)} s por llamada`);
  const base = partes.length ? `Límites: ${partes.join(" · ")}` : "";
  return [base, datos.falla_forzada ? `Falla forzada: ${datos.falla_forzada}` : ""].filter(Boolean).join(" — ");
}

/** Cómo se ve cada tipo de evento: icono, tono y textos. */
const DESCRIPTORES = {
  inicio: { icono: "inicio", tono: "", titulo: () => "Tarea iniciada", sub: limitesTexto },
  estado: { icono: "estado", tono: "", titulo: (d) => d.texto || "Estado", sub: (d) => (d.origen === "api" ? "Conexión SSE abierta por el servidor" : "") },
  cache: { icono: "cache", tono: "resultado", titulo: () => "Explicación servida desde caché", sub: (d) => (d.creada_en ? `Generada el ${f.fechaHora(d.creada_en)}` : "Sin llamar al modelo") },
  modelo_llamado: {
    icono: "modelo", tono: "modelo",
    titulo: (d) => `Llamada a ${f.proveedor(d.proveedor)}`,
    sub: (d) => [d.modelo, d.iteracion ? `iteración ${d.iteracion}` : ""].filter(Boolean).join(" · "),
  },
  herramienta: { icono: "herramienta", tono: "herramienta", titulo: (d) => `Herramienta pedida: ${d.nombre}`, sub: (d) => argumentosTexto(d.argumentos) },
  resultado_herramienta: { icono: "resultado", tono: "resultado", titulo: (d) => `Resultado de ${d.nombre}`, sub: (d) => resumenTexto(d.resumen) },
  error_herramienta: { icono: "error", tono: "error", titulo: (d) => `Falló la herramienta ${d.nombre || ""}`.trim(), sub: (d) => texto(d.error) },
  reintento: {
    icono: "alerta", tono: "alerta",
    titulo: (d) => `${f.proveedor(d.proveedor)} respondió ${motivo(d.motivo)}`,
    sub: (d) => `Reintento ${d.intento ?? ""}${d.espera_s != null ? ` en ${f.numero(d.espera_s, d.espera_s % 1 ? 1 : 0)} s` : ""}`,
  },
  conmutacion: { icono: "cambio", tono: "alerta", titulo: (d) => `Conmutación: ${f.proveedor(d.de)} → ${f.proveedor(d.a)}`, sub: (d) => motivo(d.motivo) },
  limite: { icono: "limite", tono: "alerta", titulo: (d) => `Límite alcanzado: ${d.cual || ""}`, sub: (d) => texto(d.detalle) },
  contrato_invalido: {
    icono: "alerta", tono: "alerta",
    titulo: (d) => (d.etapa === "bucle" ? "Respondió sin consultar la evidencia: se descarta" : "La respuesta no pasó la validación contra la evidencia"),
    sub: (d) => [Array.isArray(d.errores) ? d.errores.join("; ") : texto(d.errores), d.reintenta || d.se_reintenta ? "se pide de nuevo" : ""].filter(Boolean).join(" — "),
  },
  propuesta: { icono: "propuesta", tono: "modelo", titulo: (d) => `Propuesta: ${f.ACCIONES[d.accion] || d.accion || ""}`, sub: () => "Pendiente de confirmación humana" },
  explicacion: { icono: "documento", tono: "resultado", titulo: () => "Explicación validada contra la evidencia", sub: () => "" },
  respuesta: { icono: "documento", tono: "resultado", titulo: () => "Respuesta entregada", sub: () => "" },
  respaldo: { icono: "documento", tono: "alerta", titulo: () => "Respaldo: explicación armada por reglas", sub: (d) => motivo(d.motivo) },
  error: { icono: "error", tono: "error", titulo: () => "Error", sub: (d) => d.mensaje || "" },
  fin: { icono: "fin", tono: "fin", titulo: (d) => `Tarea terminada · ${f.motivoFin(d.motivo_fin)}`, sub: () => "" },
};

const ESTADOS_TAREA = {
  en_curso: "En curso",
  completada: "Completada",
  respaldo: "Respaldo",
  cache: "Caché",
  error: "Con error",
  interrumpida: "Interrumpida",
};

class Tarea {
  constructor(contenedor, tipo, titulo) {
    this.contenedor = contenedor;
    this.t0 = performance.now();
    this.fragmentos = 0;
    this.filaTexto = null;
    this.ttftNavegador = null;
    this.desdeCache = false;
    this.estado = el("span", { clase: "estado tarea__estado", texto: ESTADOS_TAREA.en_curso });
    this.lista = el("ol", { clase: "eventos" });
    this.raiz = el(
      "details",
      { clase: "tarea", open: true },
      el(
        "summary",
        {},
        el("span", { clase: "tarea__tipo", texto: tipo === "pregunta" ? "Pregunta" : "Explicación" }),
        el("span", { texto: titulo }),
        el("time", { clase: "tarea__hora", texto: f.horaSegundos(new Date()) }),
        this.estado,
      ),
      this.lista,
    );
  }

  /** Registra un evento del stream en la lista de la tarea. */
  evento(tipo, datos = {}) {
    if (tipo === "token") return this._fragmento(datos);
    if (tipo === "modelo_llamado") this.filaTexto = null; // cada llamada tiene su propia fila de texto
    if (tipo === "cache") this.desdeCache = true;
    const descriptor = DESCRIPTORES[tipo] || { icono: "estado", tono: "", titulo: () => tipo, sub: () => "" };
    const sub = descriptor.sub(datos);
    const duracion = datos.duracion_ms ?? null;
    const fila = el(
      "li",
      { clase: `evento ${descriptor.tono ? `evento--${descriptor.tono}` : ""}`, dataset: { tipo } },
      icono(descriptor.icono),
      el("div", {}, el("p", { clase: "evento__titulo", texto: descriptor.titulo(datos) }), sub ? el("p", { clase: "evento__sub", texto: sub }) : null),
      el("span", { clase: "evento__tiempo" }, duracion != null ? el("strong", { texto: f.duracion(duracion) }) : null, `+${f.numero((performance.now() - this.t0) / 1000, 2)} s`),
      this._detalle(tipo, datos),
    );
    this._agregar(fila);
  }

  _fragmento(datos) {
    this.fragmentos += 1;
    if (!this.filaTexto) {
      this.contadorTexto = el("p", { clase: "evento__sub" });
      this.filaTexto = el(
        "li",
        { clase: "evento evento--texto", dataset: { tipo: "token" } },
        icono("texto"),
        el("div", {}, el("p", { clase: "evento__titulo", texto: "Recibiendo texto del modelo" }), this.contadorTexto),
        el("span", { clase: "evento__tiempo", texto: `+${f.numero((performance.now() - this.t0) / 1000, 2)} s` }),
      );
      this.fragmentosFila = 0;
      this.caracteresFila = 0;
      this._agregar(this.filaTexto);
    }
    this.fragmentosFila += 1;
    this.caracteresFila += (datos.texto || "").length;
    this.contadorTexto.textContent = `${f.numero(this.fragmentosFila)} fragmentos · ${f.numero(this.caracteresFila)} caracteres`;
  }

  /**
   * El JSON crudo del evento (nombres de excepción, cuerpos de error del proveedor en
   * inglés, argumentos) va plegado y rotulado como técnico: la fila visible solo lleva
   * el título y el resumen en español. Se pliega siempre, aunque la tarea esté abierta.
   */
  _detalle(tipo, datos) {
    const visibles = Object.keys(datos || {}).length;
    if (!visibles || tipo === "estado") return null;
    let contenido = JSON.stringify(datos, null, 2);
    if (contenido.length > LARGO_MAXIMO_DETALLE) contenido = `${contenido.slice(0, LARGO_MAXIMO_DETALLE)}\n… (recortado)`;
    const plegable = el("details", { clase: "evento__tecnico" }, el("summary", { texto: "Detalles técnicos" }), el("pre", { texto: contenido }));
    plegable.open = false;
    return plegable;
  }

  _agregar(fila) {
    // Sigue el último evento solo si el usuario no se alejó para leer algo anterior.
    const c = this.contenedor;
    const pegado = c.scrollHeight - c.scrollTop - c.clientHeight < 60;
    this.lista.append(fila);
    if (pegado) c.scrollTop = c.scrollHeight;
  }

  /** TTFT medido en el navegador: desde que se abrió el EventSource hasta el primer token. */
  marcarPrimerToken(ms) {
    this.ttftNavegador = ms;
  }

  terminar(datos = {}) {
    const motivoFin = datos.motivo_fin;
    const estado = datos.desde_cache || this.desdeCache ? "cache" : motivoFin === "completada" ? "completada" : motivoFin === "respaldo" ? "respaldo" : motivoFin === "error" ? "error" : "completada";
    this._estado(estado);
    const entrada = datos.tokens_entrada;
    const salida = datos.tokens_salida;
    const tokens = entrada != null || salida != null ? `${f.numero(entrada || 0)} / ${f.numero(salida || 0)}` : datos.tokens != null ? f.numero(datos.tokens) : "—";
    const proveedor = datos.proveedor_final || datos.proveedor;
    const modelo = datos.modelo_final || datos.modelo;
    const filas = [
      ["TTFT servidor", datos.ttft_ms != null ? f.duracion(datos.ttft_ms) : "—"],
      ["TTFT navegador", this.ttftNavegador != null ? f.duracion(Math.round(this.ttftNavegador)) : "—"],
      ["Latencia", datos.latencia_ms != null ? f.duracion(datos.latencia_ms) : f.duracion(Math.round(performance.now() - this.t0))],
      ["Tokens ent./sal.", tokens],
      ["Costo", datos.costo_usd != null ? f.costo(datos.costo_usd) : "—"],
      ["Iteraciones", datos.iteraciones != null ? f.numero(datos.iteraciones) : "—"],
      ["Proveedor", proveedor ? [f.proveedor(proveedor), modelo].filter(Boolean).join(" · ") : this.desdeCache ? "Caché" : "—"],
      ["Reintentos", `${f.numero(datos.reintentos || 0)} · conm. ${f.numero(datos.conmutaciones || 0)}`],
      ["Motivo de fin", f.motivoFin(motivoFin || (this.desdeCache ? "cache" : null))],
    ];
    const pie = el("dl", { clase: "pie-tarea", "aria-label": "Métricas de la tarea" }, filas.map(([dt, dd]) => el("div", {}, el("dt", { texto: dt }), el("dd", { texto: dd }))));
    this._agregar(pie);
  }

  interrumpir() {
    this._estado("interrumpida");
  }

  _estado(clave) {
    this.estado.textContent = ESTADOS_TAREA[clave] || clave;
    this.estado.classList.toggle("estado--cerrado", clave !== "en_curso");
  }
}

export function crearTrazas(contenedor) {
  const tareas = [];
  return {
    /** Abre una tarea nueva arriba; las anteriores se pliegan para no perder el foco. */
    nueva(tipo, titulo) {
      if (!tareas.length) vaciar(contenedor);
      for (const anterior of tareas) anterior.raiz.open = false;
      const tarea = new Tarea(contenedor, tipo, titulo);
      contenedor.prepend(tarea.raiz);
      contenedor.scrollTop = 0;
      tareas.unshift(tarea);
      while (tareas.length > MAXIMO_TAREAS) tareas.pop().raiz.remove();
      return tarea;
    },
  };
}
