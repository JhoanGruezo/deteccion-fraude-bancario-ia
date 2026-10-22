/**
 * Diálogo de confirmación humana: la única puerta por la que algo se vuelve decisión.
 *
 * El agente puede proponer ("confirmar bloqueo porque…"), pero nada se escribe sin que
 * el analista lo confirme aquí con su nombre (requisito 4 de la vista y cuarto límite
 * del agente). Se usa <dialog> con showModal(): es un modal propio, accesible (atrapa
 * el foco, cierra con Esc) y con el estilo de la app, nunca alert/confirm/prompt.
 *
 * El nombre del analista se recuerda en localStorage para no pedirlo en cada decisión;
 * si el almacenamiento no está disponible, simplemente se vuelve a pedir.
 */

import { almacen } from "./dom.js";

const CLAVE_ANALISTA = "analista.nombre";

export function crearDialogoDecision() {
  const $ = (id) => document.getElementById(id);
  const dialogo = $("dialogo-decision");
  const formulario = $("form-decision");
  const titulo = $("dialogo-decision-titulo");
  const texto = $("dialogo-decision-texto");
  const campoAnalista = $("campo-analista");
  const campoComentario = $("campo-comentario");
  const error = $("dialogo-decision-error");
  const aceptar = $("dialogo-decision-aceptar");
  const cancelar = $("dialogo-decision-cancelar");

  let enviarActual = null;
  let resolverActual = null;
  let textoAceptar = "";

  function mostrarError(mensaje) {
    error.textContent = mensaje || "";
    error.hidden = !mensaje;
  }

  formulario.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    const analista = campoAnalista.value.trim();
    if (!analista) {
      campoAnalista.setAttribute("aria-invalid", "true");
      mostrarError("Escribe tu nombre de analista: queda registrado con la decisión.");
      campoAnalista.focus();
      return;
    }
    campoAnalista.removeAttribute("aria-invalid");
    mostrarError("");
    aceptar.disabled = true;
    aceptar.textContent = "Registrando…";
    try {
      const resultado = await enviarActual({ analista, comentario: campoComentario.value.trim() || null });
      almacen.guardar(CLAVE_ANALISTA, analista);
      // Se resuelve antes de cerrar: el evento "close" resolvería la promesa con null.
      const resolver = resolverActual;
      resolverActual = null;
      dialogo.close("ok");
      resolver?.(resultado ?? true);
    } catch (fallo) {
      // El servidor responde en español (422 sin nombre, 409 ya resuelta…): se muestra tal cual.
      mostrarError(fallo.message || "No se pudo registrar la decisión. Intenta de nuevo.");
    } finally {
      aceptar.disabled = false;
      aceptar.textContent = textoAceptar;
    }
  });

  cancelar.addEventListener("click", () => dialogo.close("cancelar"));
  dialogo.addEventListener("close", () => {
    if (resolverActual) resolverActual(null);
    resolverActual = null;
  });

  return {
    /**
     * Abre el diálogo y devuelve una promesa con el resultado del servidor, o null si
     * el analista cancela. `enviar({analista, comentario})` hace la petición; si lanza,
     * el diálogo sigue abierto mostrando el error.
     */
    abrir({ titulo: textoTitulo, descripcion, textoBoton, claseNivel = "", tono = "nivel", enviar }) {
      titulo.textContent = textoTitulo;
      texto.textContent = descripcion;
      textoAceptar = textoBoton;
      aceptar.textContent = textoBoton;
      aceptar.className = `boton ${tono === "nivel" ? "boton--nivel" : "boton--primario"}`;
      dialogo.className = `dialogo ${claseNivel}`;
      campoAnalista.value = almacen.leer(CLAVE_ANALISTA, "");
      campoAnalista.removeAttribute("aria-invalid");
      campoComentario.value = "";
      mostrarError("");
      enviarActual = enviar;
      dialogo.showModal();
      (campoAnalista.value ? campoComentario : campoAnalista).focus();
      return new Promise((resolver) => {
        resolverActual = resolver;
      });
    },
  };
}
