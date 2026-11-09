/**
 * Diálogo de confirmación humana: la única puerta por la que algo se vuelve decisión.
 *
 * El agente puede proponer ("confirmar bloqueo porque…"), pero nada se escribe sin que
 * el analista lo confirme aquí (requisito 4 de la vista y cuarto límite del agente). Se
 * usa <dialog> con showModal(): es un modal propio, accesible (atrapa el foco, cierra con
 * Esc) y con el estilo de la app, nunca alert/confirm/prompt.
 *
 * Desde el Momento 3 la firma la pone el servidor con el usuario de la sesión (ignora
 * cualquier nombre que mande el navegador): el diálogo ya no pide el nombre, solo muestra
 * "Firmará: Nombre (usuario)" para que quede claro quién queda en la auditoría.
 */

import { sesion } from "./sesion.js";

export function crearDialogoDecision() {
  const $ = (id) => document.getElementById(id);
  const dialogo = $("dialogo-decision");
  const formulario = $("form-decision");
  const titulo = $("dialogo-decision-titulo");
  const texto = $("dialogo-decision-texto");
  const firma = $("dialogo-decision-firma");
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
    mostrarError("");
    aceptar.disabled = true;
    aceptar.textContent = "Registrando…";
    try {
      const resultado = await enviarActual({ comentario: campoComentario.value.trim() || null });
      // Se resuelve antes de cerrar: el evento "close" resolvería la promesa con null.
      const resolver = resolverActual;
      resolverActual = null;
      dialogo.close("ok");
      resolver?.(resultado ?? true);
    } catch (fallo) {
      // El servidor responde en español (409 ya resuelta, 403 sin permiso…): se muestra tal cual.
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
     * el analista cancela. `enviar({comentario})` hace la petición; si lanza,
     * el diálogo sigue abierto mostrando el error.
     */
    abrir({ titulo: textoTitulo, descripcion, textoBoton, claseNivel = "", tono = "nivel", enviar }) {
      titulo.textContent = textoTitulo;
      texto.textContent = descripcion;
      textoAceptar = textoBoton;
      aceptar.textContent = textoBoton;
      aceptar.className = `boton ${tono === "nivel" ? "boton--nivel" : "boton--primario"}`;
      dialogo.className = `dialogo ${claseNivel}`;
      firma.textContent = sesion.firma;
      campoComentario.value = "";
      mostrarError("");
      enviarActual = enviar;
      dialogo.showModal();
      campoComentario.focus();
      return new Promise((resolver) => {
        resolverActual = resolver;
      });
    },
  };
}
