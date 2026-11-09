/**
 * Sondeo periódico de la API que se detiene solo.
 *
 * Las vistas del Momento 3 (en vivo, bloqueos, buzón, supervisión) se actualizan
 * pidiendo cada pocos segundos. Reglas para no gastar el límite de lecturas del servidor
 * (240 por minuto) ni cargar la base con pestañas olvidadas:
 *
 * - Solo corre mientras la vista está visible: la vista llama a `iniciar()` al mostrarse
 *   y a `detener()` al ocultarse.
 * - Se pausa si la pestaña del navegador queda en segundo plano (visibilitychange).
 * - Nunca se superponen dos vueltas: la siguiente se programa al terminar la anterior.
 * - Ante un 429 espera los segundos de Retry-After; ante otro error, espera el doble
 *   (hasta 30 s) para no insistir contra un servidor caído. Con 401 se detiene: la
 *   pantalla de ingreso toma el control.
 */

const ESPERA_MAXIMA_MS = 30000;

export function crearSondeo(tarea, intervaloMs) {
  let activo = false;
  let temporizador = null;
  let enCurso = false;
  let espera = intervaloMs;
  let controlador = null;

  async function vuelta() {
    temporizador = null;
    if (!activo || document.hidden || enCurso) return;
    enCurso = true;
    controlador = new AbortController();
    try {
      await tarea(controlador.signal);
      espera = intervaloMs;
    } catch (error) {
      if (error?.name === "AbortError") return;
      if (error?.estado === 401) {
        activo = false;
        return;
      }
      espera = error?.reintentarEn ? error.reintentarEn * 1000 : Math.min(ESPERA_MAXIMA_MS, espera * 2);
    } finally {
      enCurso = false;
      controlador = null;
      programar();
    }
  }

  function programar(ms = espera) {
    clearTimeout(temporizador);
    temporizador = null;
    if (activo && !document.hidden) temporizador = setTimeout(vuelta, ms);
  }

  document.addEventListener("visibilitychange", () => {
    if (!activo) return;
    if (document.hidden) {
      clearTimeout(temporizador);
      temporizador = null;
    } else if (!enCurso) {
      vuelta();
    }
  });

  return {
    /** Empieza (o reanuda) y hace una vuelta inmediata. */
    iniciar() {
      activo = true;
      espera = intervaloMs;
      if (!enCurso) vuelta();
    },
    detener() {
      activo = false;
      clearTimeout(temporizador);
      temporizador = null;
      controlador?.abort();
    },
    /** Pide una vuelta ya (por ejemplo, justo después de una acción del usuario). */
    ahora() {
      if (!activo) return;
      if (enCurso) return;
      clearTimeout(temporizador);
      vuelta();
    },
    get activo() {
      return activo;
    },
  };
}
