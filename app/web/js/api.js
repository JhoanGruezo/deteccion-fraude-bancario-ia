/**
 * Cliente de la API: fetch para lo normal y EventSource nativo para el SSE.
 *
 * Todas las respuestas de error del backend tienen la forma {"error", "referencia"?}
 * en español; aquí se convierten en ErrorApi para que cada módulo muestre el mensaje
 * tal cual, sin tener que conocer códigos HTTP.
 *
 * Sesión (Momento 3):
 * - La cookie de sesión es HttpOnly: el navegador la manda sola y este código nunca la ve.
 * - Toda petición que cambia algo lleva la cabecera X-CSRF-Token con el token que entregó
 *   el servidor al iniciar sesión (lo fija sesion.js con `fijarCsrf`). Una página de otro
 *   sitio no lo conoce, así que no puede firmar decisiones con la cookie del analista.
 * - Un 401 fuera de /api/sesion significa "la sesión venció": se avisa una sola vez con
 *   el manejador que registra principal.js, que vuelve a la pantalla de ingreso.
 * - Un 429 incluye en el mensaje los segundos de Retry-After, para decir cuánto esperar.
 * - El SSE (EventSource) manda la cookie solo y es GET: no necesita CSRF.
 */

export class ErrorApi extends Error {
  constructor(mensaje, estado = 0, referencia = null, reintentarEn = null) {
    super(mensaje);
    this.estado = estado;
    this.referencia = referencia;
    this.reintentarEn = reintentarEn; // segundos de Retry-After (solo en 429)
  }
}

let tokenCsrf = null;
let alSinSesion = null;

/** Guarda el token CSRF de la sesión vigente (null al salir). */
export function fijarCsrf(token) {
  tokenCsrf = token || null;
}

/** Registra qué hacer cuando el servidor dice que no hay sesión (401). */
export function manejarSinSesion(funcion) {
  alSinSesion = funcion;
}

function segundosDe(cabecera) {
  const valor = Number.parseInt(cabecera || "", 10);
  return Number.isFinite(valor) && valor > 0 ? valor : null;
}

async function pedir(ruta, { metodo = "GET", cuerpo, senal } = {}) {
  const cabeceras = { Accept: "application/json" };
  if (cuerpo !== undefined) cabeceras["Content-Type"] = "application/json";
  if (metodo !== "GET" && tokenCsrf) cabeceras["X-CSRF-Token"] = tokenCsrf;
  let respuesta;
  try {
    respuesta = await fetch(ruta, {
      method: metodo,
      headers: cabeceras,
      body: cuerpo === undefined ? undefined : JSON.stringify(cuerpo),
      signal: senal,
      credentials: "same-origin",
    });
  } catch (error) {
    if (error.name === "AbortError") throw error;
    throw new ErrorApi("No hay conexión con el servidor. Revisa que la aplicación siga corriendo.");
  }
  let datos = null;
  try {
    datos = await respuesta.json();
  } catch {
    /* respuesta sin cuerpo JSON: se usa el mensaje genérico de abajo */
  }
  if (!respuesta.ok) {
    let mensaje = datos?.error || `El servidor respondió con el código ${respuesta.status}.`;
    let espera = null;
    if (respuesta.status === 429) {
      espera = segundosDe(respuesta.headers.get("Retry-After"));
      if (espera) mensaje = `${mensaje} Intenta de nuevo en ${espera} s.`;
    }
    const error = new ErrorApi(mensaje, respuesta.status, datos?.referencia || null, espera);
    // La pantalla de ingreso maneja sus propios 401 (credenciales malas): no es "sesión vencida".
    if (respuesta.status === 401 && !ruta.startsWith("/api/sesion")) alSinSesion?.(error);
    throw error;
  }
  return datos;
}

const codificar = encodeURIComponent;

function conParametros(ruta, parametros = {}) {
  const busqueda = new URLSearchParams();
  for (const [clave, valor] of Object.entries(parametros)) if (valor !== undefined && valor !== null && valor !== "") busqueda.set(clave, valor);
  const texto = busqueda.toString();
  return texto ? `${ruta}?${texto}` : ruta;
}

export const api = {
  // ----- Sesión -----
  sesion: () => pedir("/api/sesion"),
  ingresar: (usuario, clave) => pedir("/api/sesion/ingresar", { metodo: "POST", cuerpo: { usuario, clave } }),
  salir: () => pedir("/api/sesion/salir", { metodo: "POST", cuerpo: {} }),

  // ----- Sistema -----
  salud: () => pedir("/api/salud"),
  config: () => pedir("/api/config"),
  metricas: () => pedir("/api/metricas"),
  fijarFalla: (tipo) => pedir("/api/demo/falla", { metodo: "POST", cuerpo: { tipo: tipo || null } }),

  // ----- Casos (M2) -----
  casos: (filtros = {}, senal) => pedir(conParametros("/api/casos", filtros), { senal }),
  caso: (id, senal) => pedir(`/api/casos/${codificar(id)}`, { senal }),
  historial: (id, senal) => pedir(`/api/casos/${codificar(id)}/historial?dias=30&limite=80`, { senal }),
  trazas: (tareaId) => pedir(`/api/tareas/${codificar(tareaId)}/trazas`),
  confirmarPropuesta: (id, cuerpo) => pedir(`/api/propuestas/${codificar(id)}/confirmar`, { metodo: "POST", cuerpo }),
  rechazarPropuesta: (id, cuerpo) => pedir(`/api/propuestas/${codificar(id)}/rechazar`, { metodo: "POST", cuerpo }),
  registrarDecision: (id, cuerpo) => pedir(`/api/casos/${codificar(id)}/decisiones`, { metodo: "POST", cuerpo }),
  urlExplicacion: (id, regenerar) => `/api/casos/${codificar(id)}/explicacion/stream?regenerar=${regenerar ? 1 : 0}`,
  urlPregunta: (id, pregunta) => `/api/casos/${codificar(id)}/preguntas/stream?q=${codificar(pregunta)}`,

  // ----- Flujo en vivo -----
  transaccionesRecientes: ({ desdeId = 0, limite = 100 } = {}, senal) => pedir(conParametros("/api/transacciones/recientes", { desde_id: desdeId, limite }), { senal }),
  tarjetas: (limite = 50) => pedir(conParametros("/api/tarjetas", { limite })),
  inyectarTransaccion: (cuerpo) => pedir("/api/transacciones", { metodo: "POST", cuerpo }),
  simulador: (senal) => pedir("/api/simulador", { senal }),
  controlarSimulador: (accion, velocidad) => pedir(`/api/simulador/${codificar(accion)}`, { metodo: "POST", cuerpo: velocidad ? { velocidad } : {} }),

  // ----- Operación -----
  bloqueos: (estado, senal, limite = 200) => pedir(conParametros("/api/bloqueos", { estado, limite }), { senal }),
  desbloquear: (id, motivo) => pedir(`/api/bloqueos/${codificar(id)}/desbloquear`, { metodo: "POST", cuerpo: { motivo } }),
  avisos: (limite = 100, senal) => pedir(conParametros("/api/avisos", { limite }), { senal }),
  responderAviso: (id, respuesta) => pedir(`/api/avisos/${codificar(id)}/responder`, { metodo: "POST", cuerpo: { respuesta } }),
  supervision: (senal) => pedir("/api/supervision", { senal }),
  cambiarAjuste: (clave, valor) => pedir("/api/ajustes", { metodo: "POST", cuerpo: { clave, valor } }),
  atenderAlerta: (id) => pedir(`/api/alertas/${codificar(id)}/atender`, { metodo: "POST", cuerpo: {} }),
};

/** Tipos de evento del agente (diseno/agente.md, tabla de eventos). */
export const TIPOS_EVENTO = [
  "inicio", "estado", "cache", "modelo_llamado", "token", "herramienta", "resultado_herramienta",
  "error_herramienta", "reintento", "conmutacion", "limite", "contrato_invalido", "propuesta",
  "explicacion", "respuesta", "respaldo", "error", "fin",
];

/**
 * Abre un stream SSE y reparte sus eventos.
 *
 * Detalles que importan:
 * - Los eventos llevan nombre (`event: token`), así que hay que escuchar cada tipo;
 *   `onmessage` solo recibe los que no tienen nombre.
 * - Nuestro evento `error` comparte nombre con el error de conexión nativo de
 *   EventSource. Se distinguen porque el nuestro trae `data` (es un MessageEvent).
 * - Al recibir `fin` se cierra la conexión: si no, EventSource reconecta solo y
 *   pediría otra generación en bucle.
 * - Si la conexión cae antes de `fin`, también se cierra (sin reconexión automática)
 *   y se avisa con `alInterrumpir` para que la interfaz ofrezca "Reintentar". Si la
 *   causa fue la sesión vencida, se comprueba con GET /api/sesion: su 401 no dispara
 *   el manejador global, así que aquí se dispara a mano.
 */
export function abrirStream(url, alEvento, alInterrumpir) {
  const fuente = new EventSource(url);
  let terminado = false;
  const cerrar = () => {
    terminado = true;
    fuente.close();
  };

  for (const tipo of TIPOS_EVENTO) {
    fuente.addEventListener(tipo, (evento) => {
      if (terminado) return;
      if (tipo === "error" && typeof evento.data !== "string") return; // error de conexión nativo
      let datos = {};
      try {
        datos = JSON.parse(evento.data || "{}");
      } catch {
        datos = {};
      }
      alEvento(tipo, datos);
      if (tipo === "fin") cerrar();
    });
  }
  fuente.addEventListener("error", (evento) => {
    if (typeof evento.data === "string" || terminado) return;
    cerrar();
    alInterrumpir?.();
    api.sesion().catch((error) => {
      if (error?.estado === 401) alSinSesion?.(error);
    });
  });

  return {
    cerrar,
    get abierto() {
      return !terminado;
    },
  };
}
