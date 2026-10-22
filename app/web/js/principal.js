/**
 * Arranque de la vista del analista y enrutado simple (#/caso/SPK-000123).
 *
 * Conecta los módulos (bandeja, detalle, explicación, trazas, conversación, diálogo
 * de decisión), pinta el estado del sistema en la barra superior y maneja el tema y el
 * panel de demo. El hash de la URL guarda el caso abierto: recargar la página o
 * compartir el enlace abre el mismo caso.
 */

import { api } from "./api.js";
import { almacen, avisar, el, pintarBanda, vaciar } from "./dom.js";
import { crearBandeja } from "./bandeja.js";
import { crearConversacion } from "./conversacion.js";
import { crearDialogoDecision } from "./decision.js";
import { crearDetalle } from "./detalle.js";
import * as f from "./formato.js";
import { crearTrazas } from "./trazas.js";

const RETARDO_TECLADO_MS = 350;
const INTERVALO_SALUD_MS = 30000;
const RUTA_CASO = /^#\/caso\/([A-Za-z0-9_-]+)$/;

const DESCRIPCION_FALLAS = {
  "": ["Ninguna", "El agente usa los proveedores normalmente."],
  429: ["429 · cuota agotada", "Gemini responde 429: se ven los reintentos con espera y la conmutación a Claude."],
  timeout: ["Timeout", "Gemini excede el tiempo límite: reintento y, si persiste, conmutación."],
  json: ["JSON roto", "La primera respuesta llega truncada: reparación, reintento y, si no, plantilla."],
  todo: ["Caída total", "Ambos proveedores fallan: la explicación sale de la plantilla por reglas."],
};

const $ = (id) => document.getElementById(id);
const estado = { salud: null, config: null, bandaDelSistema: null, avisoPlantillaVisto: false };

// ----- Tema ------------------------------------------------------------------------------
function temaEfectivo() {
  const elegido = document.documentElement.dataset.tema;
  if (elegido) return elegido;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "oscuro" : "claro";
}

function prepararTema() {
  const boton = $("boton-tema");
  const rotular = () => boton.setAttribute("aria-label", temaEfectivo() === "oscuro" ? "Cambiar a tema claro" : "Cambiar a tema oscuro");
  rotular();
  boton.addEventListener("click", () => {
    const nuevo = temaEfectivo() === "oscuro" ? "claro" : "oscuro";
    document.documentElement.dataset.tema = nuevo;
    almacen.guardar("tema", nuevo);
    rotular();
  });
}

// ----- Estado del sistema -------------------------------------------------------------------
function pastilla(texto, tono, titulo) {
  return el("li", { clase: `pastilla${tono ? ` pastilla--${tono}` : ""}`, title: titulo || null }, el("span", { clase: "pastilla__punto", "aria-hidden": "true" }), texto);
}

function pintarSistema() {
  const lista = vaciar($("estado-sistema"));
  const salud = estado.salud;
  if (!salud) {
    lista.append(pastilla("Sin conexión con el servidor", "mal"));
    return;
  }
  lista.append(
    salud.base.disponible
      ? pastilla(`Base · ${f.numero(salud.base.casos_cargados)} casos`, "ok")
      : pastilla("Base no disponible", "mal", salud.base.mensaje),
  );
  const conLlave = salud.proveedores.filter((p) => p.con_llave);
  lista.append(
    conLlave.length
      ? pastilla(`IA · ${conLlave.map((p) => p.etiqueta).join(" → ")}`, "ok", conLlave.map((p) => `${p.etiqueta}: ${p.modelo}`).join(" · "))
      : pastilla("Sin IA · plantilla por reglas", "mal", "No hay llaves de API configuradas"),
  );
  if (salud.falla_forzada) {
    const [nombre] = DESCRIPCION_FALLAS[salud.falla_forzada] || [salud.falla_forzada];
    lista.append(el("li", { clase: "pastilla pastilla--falla", title: "Falla forzada para la demo" }, `Falla forzada: ${nombre}`));
  }

  // Avisos de alcance global en la banda superior. Solo se quita la banda que puso este
  // código: la misma banda la usa el detalle para "el caso no existe".
  const banda = $("banda-global");
  if (!salud.base.disponible) {
    estado.bandaDelSistema = "base";
    pintarBanda(banda, {
      titulo: "La base de datos no responde.",
      detalle: salud.base.mensaje || "Revisa que el servicio de Postgres esté activo.",
      acciones: [{ texto: "Reintentar", primaria: true, al: () => refrescarSalud(true) }],
    });
  } else if (salud.modo_plantilla && !estado.avisoPlantillaVisto) {
    estado.bandaDelSistema = "plantilla";
    pintarBanda(banda, {
      tono: "info",
      titulo: "Sin llaves de IA configuradas: las explicaciones se arman por reglas.",
      detalle: "La app funciona completa con la plantilla y las razones guardadas. Configura GEMINI_API_KEY o ANTHROPIC_API_KEY en .env para el agente en vivo.",
      acciones: [{ texto: "Entendido", al: () => { estado.avisoPlantillaVisto = true; estado.bandaDelSistema = null; pintarBanda(banda, null); } }],
    });
  } else if (estado.bandaDelSistema) {
    estado.bandaDelSistema = null;
    pintarBanda(banda, null);
  }
}

async function refrescarSalud(recargarBandeja = false) {
  try {
    const baseAntes = estado.salud?.base?.disponible;
    estado.salud = await api.salud();
    pintarSistema();
    if (recargarBandeja || (baseAntes === false && estado.salud.base.disponible)) bandeja.cargar();
  } catch {
    estado.salud = null;
    pintarSistema();
  }
}

// ----- Panel de demo ---------------------------------------------------------------------------
function etiquetaMetrica(clave) {
  const nombres = {
    n: "Tareas", n_tareas: "Tareas", total_tareas: "Tareas", tasa_exito: "Tasa de éxito",
    latencia_mediana_ms: "Latencia (mediana)", latencia_p90_ms: "Latencia (P90)", ttft_mediana_ms: "TTFT (mediana)",
    ttft_p90_ms: "TTFT (P90)", costo_por_tarea_usd: "Costo por tarea", tasa_cache: "Desde caché", mediana_latencia_ms: "Latencia (mediana)",
    p90_latencia_ms: "Latencia (P90)", mediana_ttft_ms: "TTFT (mediana)", p90_ttft_ms: "TTFT (P90)",
    costo_total_usd: "Costo total", costo_por_tarea_usd: "Costo por tarea", porcentaje_cache: "Desde caché",
    recuperacion: "Recuperación de fallas", tasa_recuperacion: "Recuperación de fallas",
    tareas_sin_cache: "Tareas sin caché", exitosas: "Exitosas (sin caché)", porcentaje_desde_cache: "Desde caché",
  };
  return nombres[clave] || clave.replace(/_/g, " ");
}

function valorMetrica(clave, valor) {
  if (valor === null || valor === undefined) return "—";
  if (typeof valor !== "number") return String(valor);
  if (clave.endsWith("_ms")) return f.duracion(Math.round(valor));
  if (clave.includes("costo")) return f.costo(valor);
  if (clave.includes("tasa") || clave.includes("porcentaje") || clave.includes("recuperacion")) return f.porcentaje(valor <= 1 ? valor * 100 : valor);
  return f.numero(valor, Number.isInteger(valor) ? 0 : 2);
}

async function abrirDemo() {
  const dialogo = $("dialogo-demo");
  const opciones = $("opciones-falla");
  const vigente = estado.salud?.falla_forzada || "";
  for (const viejo of opciones.querySelectorAll(".opcion-falla")) viejo.remove();
  const validas = ["", ...(estado.config?.fallas_validas || ["429", "timeout", "json", "todo"])];
  for (const tipo of validas) {
    const [nombre, descripcion] = DESCRIPCION_FALLAS[tipo] || [tipo, ""];
    const entrada = el("input", { type: "radio", name: "falla", value: tipo, checked: tipo === vigente });
    entrada.addEventListener("change", async () => {
      try {
        await api.fijarFalla(tipo);
        avisar(tipo ? `Falla forzada: ${nombre}. Abre o regenera un caso para verla.` : "Sin falla forzada");
        await refrescarSalud();
      } catch (error) {
        avisar(error.message, "error");
      }
    });
    opciones.append(el("label", { clase: "opcion-falla" }, entrada, el("strong", { texto: nombre }), el("span", { texto: descripcion })));
  }

  const limites = estado.config?.limites || {};
  const filasLimites = [
    ["Iteraciones por tarea", f.numero(limites.max_iteraciones)],
    ["Presupuesto de tokens", f.numero(limites.presupuesto_tokens)],
    ["Timeout por llamada", limites.timeout_modelo_s != null ? `${f.numero(limites.timeout_modelo_s)} s` : "—"],
    ["Timeout de herramienta", limites.timeout_herramienta_s != null ? `${f.numero(limites.timeout_herramienta_s)} s` : "—"],
    ["Esperas de reintento", (limites.esperas_reintento_s || []).map((s) => `${f.numero(s)} s`).join(", ") || "—"],
    ["Confirmación humana", "Obligatoria"],
  ];
  vaciar($("demo-limites")).append(...filasLimites.flatMap(([dt, dd]) => [el("dt", { texto: dt }), el("dd", { texto: dd })]));

  const metricas = vaciar($("demo-metricas"));
  metricas.append(el("dt", { texto: "Cargando…" }), el("dd", {}));
  dialogo.showModal();
  try {
    const datos = await api.metricas();
    vaciar(metricas);
    const entradas = Object.entries(datos || {}).filter(([, v]) => typeof v !== "object" || v === null);
    if (!entradas.length) metricas.append(el("dt", { texto: "Todavía no hay tareas registradas." }), el("dd", {}));
    for (const [clave, valor] of entradas) metricas.append(el("dt", { texto: etiquetaMetrica(clave) }), el("dd", { texto: valorMetrica(clave, valor) }));
  } catch (error) {
    vaciar(metricas).append(el("dt", { texto: error.message }), el("dd", {}));
  }
}

// ----- Arranque ------------------------------------------------------------------------------------
const trazas = crearTrazas($("traza"));
const dialogo = crearDialogoDecision();
const conversacion = crearConversacion({ trazas, alPropuesta: (datos) => detalle.agregarPropuesta?.(datos) });
let temporizadorTeclado = null;

const bandeja = crearBandeja({
  alSeleccionar(id, { origen }) {
    clearTimeout(temporizadorTeclado);
    const ir = () => {
      if (location.hash !== `#/caso/${id}`) location.hash = `#/caso/${id}`;
      else if (detalle.idActual !== id) detalle.abrir(id);
    };
    // Con el teclado se espera a que el analista se detenga en un caso.
    if (origen === "teclado") temporizadorTeclado = setTimeout(ir, RETARDO_TECLADO_MS);
    else ir();
  },
});

const detalle = crearDetalle({ trazas, conversacion, dialogo, alCambio: () => bandeja.cargar() });

function seguirHash() {
  const coincidencia = location.hash.match(RUTA_CASO);
  if (!coincidencia) return;
  const id = decodeURIComponent(coincidencia[1]);
  bandeja.marcar(id);
  if (detalle.idActual !== id) detalle.abrir(id);
}

async function iniciar() {
  prepararTema();
  window.addEventListener("hashchange", seguirHash);
  $("boton-demo").addEventListener("click", abrirDemo);
  $("dialogo-demo-cerrar").addEventListener("click", () => $("dialogo-demo").close());

  const [salud, config] = await Promise.allSettled([api.salud(), api.config()]);
  estado.salud = salud.status === "fulfilled" ? salud.value : null;
  estado.config = config.status === "fulfilled" ? config.value : null;
  $("boton-demo").hidden = !estado.config?.panel_demo;
  pintarSistema();

  await bandeja.cargar();
  if (RUTA_CASO.test(location.hash)) seguirHash();
  else bandeja.enfocar();
  setInterval(() => refrescarSalud(), INTERVALO_SALUD_MS);
}

iniciar();
