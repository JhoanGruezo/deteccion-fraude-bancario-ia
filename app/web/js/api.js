/**
 * Cliente de la API: fetch para lo normal y EventSource nativo para el SSE.
 *
 * Todas las respuestas de error del backend tienen la forma {"error", "referencia"?}
 * en español; aquí se convierten en ErrorApi para que cada módulo muestre el mensaje
 * tal cual, sin tener que conocer códigos HTTP.
 */

export class ErrorApi extends Error {
  constructor(mensaje, estado = 0, referencia = null) {
    super(mensaje);
    this.estado = estado;
    this.referencia = referencia;
  }
}

async function pedir(ruta, { metodo = "GET", cuerpo, senal } = {}) {
  let respuesta;
  try {
    respuesta = await fetch(ruta, {
      method: metodo,
      headers: cuerpo === undefined ? { Accept: "application/json" } : { Accept: "application/json", "Content-Type": "application/json" },
      body: cuerpo === undefined ? undefined : JSON.stringify(cuerpo),
      signal: senal,
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
    throw new ErrorApi(datos?.error || `El servidor respondió con el código ${respuesta.status}.`, respuesta.status, datos?.referencia || null);
  }
  return datos;
}

const codificar = encodeURIComponent;

export const api = {
  salud: () => pedir("/api/salud"),
  config: () => pedir("/api/config"),
  metricas: () => pedir("/api/metricas"),
  casos(filtros = {}, senal) {
    const parametros = new URLSearchParams();
    for (const [clave, valor] of Object.entries(filtros)) if (valor) parametros.set(clave, valor);
    return pedir(`/api/casos?${parametros}`, { senal });
  },
  caso: (id, senal) => pedir(`/api/casos/${codificar(id)}`, { senal }),
  historial: (id, senal) => pedir(`/api/casos/${codificar(id)}/historial?dias=30&limite=80`, { senal }),
  trazas: (tareaId) => pedir(`/api/tareas/${codificar(tareaId)}/trazas`),
  confirmarPropuesta: (id, cuerpo) => pedir(`/api/propuestas/${codificar(id)}/confirmar`, { metodo: "POST", cuerpo }),
  rechazarPropuesta: (id, cuerpo) => pedir(`/api/propuestas/${codificar(id)}/rechazar`, { metodo: "POST", cuerpo }),
  registrarDecision: (id, cuerpo) => pedir(`/api/casos/${codificar(id)}/decisiones`, { metodo: "POST", cuerpo }),
  fijarFalla: (tipo) => pedir("/api/demo/falla", { metodo: "POST", cuerpo: { tipo: tipo || null } }),
  urlExplicacion: (id, regenerar) => `/api/casos/${codificar(id)}/explicacion/stream?regenerar=${regenerar ? 1 : 0}`,
  urlPregunta: (id, pregunta) => `/api/casos/${codificar(id)}/preguntas/stream?q=${codificar(pregunta)}`,
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
 *   y se avisa con `alInterrumpir` para que la interfaz ofrezca "Reintentar".
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
  });

  return {
    cerrar,
    get abierto() {
      return !terminado;
    },
  };
}
