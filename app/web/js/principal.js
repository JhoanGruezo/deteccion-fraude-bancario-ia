/**
 * Arranque de la app, sesión y enrutado por hash.
 *
 * Rutas (cada una es una pestaña de la cabecera):
 *   #/casos           bandeja + detalle + agente (la vista de tres columnas del M2)
 *   #/caso/SPK-000123 lo mismo, con ese caso abierto
 *   #/en-vivo         simulador, feed de transacciones y decisiones recientes
 *   #/bloqueos        bloqueos activos y levantados, con desbloqueo
 *   #/buzon           buzón simulado del titular
 *   #/supervision     autonomía del agente, topes, cifras y alertas
 *
 * Solo la vista visible sondea la API: al cambiar de pestaña se llama a `ocultar()` de la
 * anterior (detiene sus sondeos) y a `mostrar()` de la nueva.
 *
 * Sesión: al cargar se pregunta GET /api/sesion; sin sesión se muestra la pantalla de
 * ingreso. Cualquier 401 posterior vuelve a esa pantalla sin tocar el hash, así que tras
 * ingresar se sigue en la misma vista o caso.
 */

import { api, manejarSinSesion } from "./api.js";
import { almacen, avisar, el, pintarBanda, vaciar } from "./dom.js";
import { crearBandeja } from "./bandeja.js";
import { crearBloqueos } from "./bloqueos.js";
import { crearBuzon } from "./buzon.js";
import { crearConversacion } from "./conversacion.js";
import { crearDialogoDecision } from "./decision.js";
import { crearDialogoDesbloqueo } from "./desbloqueo.js";
import { crearDetalle } from "./detalle.js";
import { crearEnVivo } from "./en_vivo.js";
import * as f from "./formato.js";
import { crearIngreso, fijarSesion, sesion } from "./sesion.js";
import { crearSupervision } from "./supervision.js";
import { crearTrazas } from "./trazas.js";

const RETARDO_TECLADO_MS = 350;
const INTERVALO_SALUD_MS = 30000;
const RUTA_CASO = /^#\/caso\/([A-Za-z0-9_-]+)$/;
const RUTAS = {
  "#/casos": "casos",
  "#/en-vivo": "en-vivo",
  "#/bloqueos": "bloqueos",
  "#/buzon": "buzon",
  "#/supervision": "supervision",
};
const TITULOS = {
  casos: "Casos",
  "en-vivo": "En vivo",
  bloqueos: "Bloqueos",
  buzon: "Buzón del titular",
  supervision: "Supervisión",
};

const DESCRIPCION_FALLAS = {
  "": ["Ninguna", "El agente usa los proveedores normalmente."],
  429: ["429 · cuota agotada", "El proveedor principal responde 429: se ven los reintentos con espera y la conmutación al de respaldo."],
  timeout: ["Timeout", "El proveedor principal excede el tiempo límite: reintentos y, si persiste, conmutación al de respaldo."],
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
  const botones = [$("boton-tema"), $("ingreso-tema")].filter(Boolean);
  const rotular = () => {
    for (const boton of botones) boton.setAttribute("aria-label", temaEfectivo() === "oscuro" ? "Cambiar a tema claro" : "Cambiar a tema oscuro");
  };
  rotular();
  for (const boton of botones) {
    boton.addEventListener("click", () => {
      const nuevo = temaEfectivo() === "oscuro" ? "claro" : "oscuro";
      document.documentElement.dataset.tema = nuevo;
      almacen.guardar("tema", nuevo);
      rotular();
    });
  }
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
    if (vistaActual === "casos" && (recargarBandeja || (baseAntes === false && estado.salud.base.disponible))) bandeja.cargar();
  } catch {
    estado.salud = null;
    pintarSistema();
  }
}

// ----- Panel de demo (solo supervisor) ----------------------------------------------------------
function etiquetaMetrica(clave) {
  const nombres = {
    n: "Tareas", n_tareas: "Tareas", total_tareas: "Tareas", tasa_exito: "Tasa de éxito",
    latencia_mediana_ms: "Latencia (mediana)", latencia_p90_ms: "Latencia (P90)", ttft_mediana_ms: "TTFT (mediana)",
    ttft_p90_ms: "TTFT (P90)", tasa_cache: "Desde caché", mediana_latencia_ms: "Latencia (mediana)",
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

// ----- Vistas ------------------------------------------------------------------------------------
const trazas = crearTrazas($("traza"));
const dialogo = crearDialogoDecision();
const desbloqueo = crearDialogoDesbloqueo();
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

const detalle = crearDetalle({ trazas, conversacion, dialogo, desbloqueo, alCambio: () => bandeja.cargar() });

// La vista de casos no sondea: carga la bandeja al mostrarse (y con el botón de actualizar).
let bandejaCargada = false;
const vistaCasos = {
  async mostrar() {
    const primeraVez = !bandejaCargada;
    bandejaCargada = true;
    await bandeja.cargar();
    if (primeraVez && !RUTA_CASO.test(location.hash)) bandeja.enfocar();
    else if (detalle.idActual) bandeja.marcar(detalle.idActual);
  },
  ocultar() {},
};

const vistas = {
  casos: vistaCasos,
  "en-vivo": crearEnVivo(),
  bloqueos: crearBloqueos({ desbloqueo }),
  buzon: crearBuzon(),
  supervision: crearSupervision(),
};
let vistaActual = null;

function vistaDeHash(hash) {
  if (RUTA_CASO.test(hash)) return "casos";
  return RUTAS[hash] || "casos";
}

function activarVista(nombre) {
  if (vistaActual === nombre) return;
  if (vistaActual) vistas[vistaActual].ocultar();
  for (const clave of Object.keys(vistas)) $(`vista-${clave}`).hidden = clave !== nombre;
  for (const enlace of document.querySelectorAll(".pestana")) {
    if (enlace.dataset.vista === nombre) enlace.setAttribute("aria-current", "page");
    else enlace.removeAttribute("aria-current");
  }
  $("saltar").setAttribute("href", nombre === "casos" ? "#detalle" : `#vista-${nombre}`);
  $("saltar").textContent = nombre === "casos" ? "Saltar al detalle del caso" : "Saltar al contenido";
  document.title = `${TITULOS[nombre]} · Riesgo`;
  const anterior = vistaActual;
  vistaActual = nombre;
  vistas[nombre].mostrar();
  // Al cambiar de pestaña, el foco va al título de la vista (lo anuncia el lector de pantalla).
  if (anterior && nombre !== "casos") $(`vista-${nombre}`).querySelector("h1")?.focus({ preventScroll: true });
  // En pantalla ancha cada página hace su propio scroll; en angosta, la ventana.
  if (nombre !== "casos") $(`vista-${nombre}`).scrollTop = 0;
  window.scrollTo(0, 0);
}

function seguirHash() {
  if (!sesion.usuario) return; // sin sesión manda la pantalla de ingreso
  activarVista(vistaDeHash(location.hash));
  const coincidencia = location.hash.match(RUTA_CASO);
  if (!coincidencia) return;
  const id = decodeURIComponent(coincidencia[1]);
  bandeja.marcar(id);
  if (detalle.idActual !== id) detalle.abrir(id);
}

// ----- Sesión ---------------------------------------------------------------------------------
const aplicacion = $("aplicacion");
const ingreso = crearIngreso({ alEntrar: entrar });
let temporizadorSalud = null;

function pintarUsuario() {
  const u = sesion.usuario;
  $("usuario-nombre").textContent = u?.nombre || "";
  const rol = $("usuario-rol");
  rol.textContent = sesion.rolLegible;
  rol.className = `rol rol--${u?.rol || "analista"}`;
  $("boton-demo").hidden = !(estado.config?.panel_demo && sesion.esSupervisor);
}

async function entrar(datos) {
  fijarSesion(datos);
  ingreso.ocultar();
  aplicacion.hidden = false;
  if (!estado.config) {
    try {
      estado.config = await api.config();
    } catch {
      estado.config = null;
    }
  }
  pintarUsuario();
  vistas["en-vivo"].reiniciarRol();
  if (!temporizadorSalud) temporizadorSalud = setInterval(() => refrescarSalud(), INTERVALO_SALUD_MS);
  // Tras una sesión vencida la vista visible se vuelve a mostrar (reanuda sus sondeos con
  // el rol nuevo); la primera vez la elige el hash.
  const vista = vistaActual;
  vistaActual = null;
  if (vista) activarVista(vista);
  seguirHash();
  if (vistaActual === "casos" && detalle.idActual) detalle.refrescar();
}

function mostrarIngreso(motivo) {
  if (vistaActual) vistas[vistaActual].ocultar();
  aplicacion.hidden = true;
  for (const abierto of document.querySelectorAll("dialog[open]")) abierto.close();
  ingreso.mostrar(motivo);
}

manejarSinSesion(() => {
  if (!sesion.usuario) return; // ya se está mostrando el ingreso
  mostrarIngreso("Tu sesión venció o se cerró. Ingresa de nuevo para seguir donde estabas.");
});

async function salir() {
  try {
    await api.salir();
  } catch {
    /* aunque falle, la sesión local se olvida */
  }
  mostrarIngreso("Cerraste la sesión.");
}

async function iniciar() {
  prepararTema();
  // El nombre del analista ya no se pide ni se guarda: firma el usuario de la sesión.
  almacen.borrar("analista.nombre");
  window.addEventListener("hashchange", seguirHash);
  $("boton-demo").addEventListener("click", abrirDemo);
  $("dialogo-demo-cerrar").addEventListener("click", () => $("dialogo-demo").close());
  $("boton-salir").addEventListener("click", salir);

  try {
    estado.salud = await api.salud();
  } catch {
    estado.salud = null;
  }
  pintarSistema();

  try {
    await entrar(await api.sesion());
  } catch (error) {
    mostrarIngreso(error?.estado === 401 ? "" : error?.message);
  }
}

iniciar();
