/**
 * Conversación con el agente sobre el caso abierto, también por SSE real.
 *
 * Cada pregunta abre su propio stream y su propia tarea en el panel de trazas. La
 * respuesta crece con los fragmentos que llegan (`token`) y se reemplaza por el texto
 * final (`respuesta`) cuando el agente termina. El historial se guarda por caso en
 * memoria: al volver a un caso, la conversación sigue ahí.
 *
 * El texto del agente se pinta con `textoConFormato` (negritas **así** y saltos de
 * línea) construyendo nodos, nunca con innerHTML: es texto de un modelo que leyó datos
 * del caso, y un comercio llamado "<img onerror=…>" no puede ejecutar nada. El texto de
 * una llamada que pidió herramientas (un preámbulo, a veces en inglés) se descarta en
 * cuanto llega el evento `herramienta`.
 */

import { abrirStream, api } from "./api.js";
import { el, textoConFormato, vaciar } from "./dom.js";
import * as f from "./formato.js";

const SUGERENCIAS = [
  "¿Cuál fue la compra más rara y por qué?",
  "¿Qué tan distinto es esto de su comportamiento habitual?",
  "¿Por qué se recomienda este bloqueo y no otro?",
];

export function crearConversacion({ trazas, alPropuesta }) {
  const $ = (id) => document.getElementById(id);
  const lista = $("conversacion");
  const formulario = $("form-pregunta");
  const campo = $("campo-pregunta");
  const boton = $("boton-preguntar");
  const etiquetaCaso = $("conversacion-caso");

  const historiales = new Map(); // id_caso → [{ rol, texto, estado, meta }]
  let caso = null;
  let stream = null;
  let enCurso = null; // { respuesta, pregunta, tarea } de la pregunta que se está escuchando

  function habilitar() {
    const activo = Boolean(caso) && !stream;
    campo.disabled = !caso;
    boton.disabled = !activo || !campo.value.trim();
    campo.placeholder = caso ? `Pregunta sobre ${caso.id_caso}…` : "Abre un caso para preguntar";
  }

  function nodoMensaje(mensaje) {
    const nodo = el("div", { clase: `mensaje mensaje--${mensaje.rol}${mensaje.estado === "llegando" ? " mensaje--esperando" : ""}${mensaje.estado === "error" ? " mensaje--error" : ""}` });
    actualizarNodo(nodo, mensaje);
    return nodo;
  }

  function actualizarNodo(nodo, mensaje) {
    vaciar(nodo);
    nodo.classList.toggle("mensaje--esperando", mensaje.estado === "llegando" && !mensaje.texto);
    nodo.classList.toggle("mensaje--error", mensaje.estado === "error");
    if (mensaje.texto) nodo.append(mensaje.rol === "agente" ? textoConFormato(mensaje.texto) : mensaje.texto);
    if (mensaje.meta) nodo.append(el("span", { clase: "mensaje__meta", texto: mensaje.meta }));
    if (mensaje.reintentar) {
      nodo.append(el("div", { clase: "mensaje__accion" }, el("button", { type: "button", clase: "boton boton--secundario boton--chico", texto: "Reintentar", onClick: mensaje.reintentar })));
    }
  }

  function pintar() {
    vaciar(lista);
    const mensajes = caso ? historiales.get(caso.id_caso) || [] : [];
    if (caso && !mensajes.length) {
      lista.append(
        el(
          "div",
          { clase: "sugerencias" },
          el("p", { clase: "sugerencias__titulo", texto: "El agente solo responde sobre este caso, con sus datos. Puedes empezar con:" }),
          SUGERENCIAS.map((s) => el("button", { type: "button", clase: "sugerencia", texto: s, onClick: () => preguntar(s) })),
        ),
      );
    }
    for (const mensaje of mensajes) {
      mensaje.nodo = nodoMensaje(mensaje);
      lista.append(mensaje.nodo);
    }
    lista.scrollTop = lista.scrollHeight;
  }

  function preguntar(texto) {
    const pregunta = texto.trim();
    if (!caso || !pregunta || stream) return;
    const idCaso = caso.id_caso;
    const mensajes = historiales.get(idCaso) || [];
    historiales.set(idCaso, mensajes);
    mensajes.push({ rol: "analista", texto: pregunta });
    const respuesta = { rol: "agente", texto: "", estado: "llegando" };
    mensajes.push(respuesta);
    campo.value = "";
    pintar();

    const tarea = trazas.nueva("pregunta", idCaso);
    const t0 = performance.now();
    let bufer = "";
    let primero = true;
    const refrescar = () => respuesta.nodo?.isConnected && actualizarNodo(respuesta.nodo, respuesta);
    enCurso = { respuesta, pregunta, tarea };

    stream = abrirStream(
      api.urlPregunta(idCaso, pregunta),
      (tipo, datos) => {
        tarea.evento(tipo, datos);
        if (tipo === "modelo_llamado") bufer = "";
        else if (tipo === "herramienta") {
          // Lo escrito antes de pedir herramientas no es la respuesta: se quita de la vista.
          bufer = "";
          respuesta.texto = "";
          refrescar();
        } else if (tipo === "token") {
          if (primero) {
            primero = false;
            tarea.marcarPrimerToken(performance.now() - t0);
          }
          bufer += datos.texto || "";
          respuesta.texto = bufer;
          refrescar();
        } else if (tipo === "respuesta" || (tipo === "respaldo" && datos.texto)) {
          respuesta.texto = datos.texto || respuesta.texto;
          refrescar();
        } else if (tipo === "propuesta") alPropuesta?.(datos);
        else if (tipo === "error") {
          respuesta.estado = "error";
          respuesta.texto = datos.mensaje || "El agente no pudo responder.";
          respuesta.reintentar = () => preguntar(pregunta);
          refrescar();
        } else if (tipo === "fin") {
          tarea.terminar(datos);
          if (respuesta.estado !== "error") respuesta.estado = "listo";
          if (!respuesta.texto) respuesta.texto = "El agente terminó sin respuesta.";
          const proveedor = datos.proveedor_final || datos.proveedor;
          respuesta.meta = [
            datos.motivo_fin === "rechazo" ? "Fuera del alcance del caso" : null,
            proveedor ? f.proveedor(proveedor) : null,
            f.duracion(datos.latencia_ms ?? Math.round(performance.now() - t0)),
          ].filter(Boolean).join(" · ");
          stream = null;
          refrescar();
          habilitar();
        }
      },
      () => {
        tarea.interrumpir();
        respuesta.estado = "error";
        respuesta.texto = respuesta.texto || "Se perdió la conexión antes de recibir la respuesta.";
        respuesta.reintentar = () => preguntar(pregunta);
        stream = null;
        refrescar();
        habilitar();
      },
    );
    habilitar();
  }

  formulario.addEventListener("submit", (evento) => {
    evento.preventDefault();
    preguntar(campo.value);
  });
  campo.addEventListener("input", habilitar);
  campo.addEventListener("keydown", (evento) => {
    // Enter envía; Shift+Enter agrega una línea.
    if (evento.key === "Enter" && !evento.shiftKey) {
      evento.preventDefault();
      preguntar(campo.value);
    }
  });

  habilitar();

  return {
    abrirCaso(nuevo) {
      // Una pregunta en curso de otro caso sigue en el servidor; aquí solo se deja de escuchar.
      if (stream && caso?.id_caso !== nuevo?.id_caso) {
        stream.cerrar();
        stream = null;
        enCurso.tarea.interrumpir();
        enCurso.respuesta.estado = "error";
        enCurso.respuesta.texto = enCurso.respuesta.texto || "Dejaste el caso antes de recibir la respuesta.";
        const { pregunta } = enCurso;
        enCurso.respuesta.reintentar = () => preguntar(pregunta);
      }
      caso = nuevo;
      etiquetaCaso.textContent = caso ? caso.id_caso : "";
      pintar();
      habilitar();
    },
  };
}
