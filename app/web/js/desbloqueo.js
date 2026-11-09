/**
 * Diálogo para levantar un bloqueo (lista de Bloqueos y detalle del caso).
 *
 * Desbloquear exige un motivo escrito de al menos 10 caracteres: queda en la auditoría
 * del caso junto con la firma del usuario de la sesión, que pone el servidor. El botón
 * solo se habilita cuando el motivo alcanza el mínimo, y aun así el servidor lo vuelve a
 * validar (422 motivo corto, 409 si otro analista ya lo levantó): esos mensajes se
 * muestran tal cual, sin cerrar el diálogo.
 */

import { api } from "./api.js";
import { el, vaciar } from "./dom.js";
import * as f from "./formato.js";
import { sesion } from "./sesion.js";

const MINIMO = 10;

export function crearDialogoDesbloqueo() {
  const $ = (id) => document.getElementById(id);
  const dialogo = $("dialogo-desbloqueo");
  const formulario = $("form-desbloqueo");
  const titulo = $("dialogo-desbloqueo-titulo");
  const resumen = $("dialogo-desbloqueo-resumen");
  const campo = $("campo-motivo-desbloqueo");
  const contador = $("contador-motivo-desbloqueo");
  const firma = $("dialogo-desbloqueo-firma");
  const error = $("dialogo-desbloqueo-error");
  const aceptar = $("dialogo-desbloqueo-aceptar");
  const cancelar = $("dialogo-desbloqueo-cancelar");

  let bloqueoActual = null;
  let resolverActual = null;

  function mostrarError(mensaje) {
    error.textContent = mensaje || "";
    error.hidden = !mensaje;
  }

  function actualizarContador() {
    const largo = campo.value.trim().length;
    const falta = Math.max(0, MINIMO - largo);
    contador.textContent = falta ? `${largo} / ${campo.maxLength} · faltan ${falta} caracteres` : `${largo} / ${campo.maxLength}`;
    contador.classList.toggle("contador-texto--ok", !falta);
    aceptar.disabled = Boolean(falta);
  }

  campo.addEventListener("input", actualizarContador);

  formulario.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    const motivo = campo.value.trim();
    if (motivo.length < MINIMO) {
      mostrarError(`Escribe por qué desbloqueas (al menos ${MINIMO} caracteres).`);
      campo.focus();
      return;
    }
    mostrarError("");
    aceptar.disabled = true;
    aceptar.textContent = "Desbloqueando…";
    try {
      const resultado = await api.desbloquear(bloqueoActual.id, motivo);
      const resolver = resolverActual;
      resolverActual = null;
      dialogo.close("ok");
      resolver?.(resultado);
    } catch (fallo) {
      mostrarError(fallo.message || "No se pudo desbloquear. Intenta de nuevo.");
    } finally {
      aceptar.textContent = "Desbloquear";
      actualizarContador();
    }
  });

  cancelar.addEventListener("click", () => dialogo.close("cancelar"));
  dialogo.addEventListener("close", () => {
    resolverActual?.(null);
    resolverActual = null;
  });

  return {
    /**
     * Abre el diálogo para un bloqueo ({id, id_caso, alias, tarjeta_enmascarada, tipo,
     * actor, motivo, respuesta_titular…}). Devuelve la respuesta del servidor o null.
     */
    abrir(bloqueo) {
      bloqueoActual = bloqueo;
      const tarjeta = [bloqueo.alias, bloqueo.tarjeta_enmascarada ? f.tarjetaCorta(bloqueo.tarjeta_enmascarada) : null].filter(Boolean).join(" · ");
      titulo.textContent = bloqueo.tipo === "acceso_cuenta" ? "Devolver el acceso a la cuenta" : "Desbloquear la tarjeta";
      const actor = f.actor(bloqueo.actor);
      vaciar(resumen).append(
        el("div", {}, el("dt", { texto: "Tarjeta" }), el("dd", { texto: tarjeta || "—" })),
        el("div", {}, el("dt", { texto: "Caso" }), el("dd", { clase: "mono", texto: bloqueo.id_caso || "—" })),
        el("div", {}, el("dt", { texto: "Bloqueó" }), el("dd", { texto: `${actor.etiqueta}${bloqueo.usuario ? ` (${bloqueo.usuario})` : ""}` })),
        bloqueo.respuesta_titular
          ? el("div", {}, el("dt", { texto: "El titular dice" }), el("dd", { texto: f.RESPUESTAS_TITULAR[bloqueo.respuesta_titular] || bloqueo.respuesta_titular }))
          : null,
      );
      firma.textContent = sesion.firma;
      campo.value = "";
      mostrarError("");
      actualizarContador();
      aceptar.textContent = "Desbloquear";
      dialogo.showModal();
      campo.focus();
      return new Promise((resolver) => {
        resolverActual = resolver;
      });
    },
  };
}
