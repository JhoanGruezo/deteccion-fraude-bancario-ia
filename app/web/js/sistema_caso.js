/**
 * Sección "Qué hizo el sistema" del detalle de un caso en vivo (Momento 3).
 *
 * Va arriba de la explicación porque es lo primero que pregunta un analista al abrir un
 * caso que ya se movió solo: ¿quién actuó (el agente o la regla de respaldo), qué hizo,
 * cuánto costó y tardó, qué se bloqueó y qué se le dijo al titular?
 *
 * Los avisos muestran el texto completo que recibió el titular, quién redactó el motivo
 * (agente o plantilla) y, si el motivo del agente no pasó la validación, los errores: es
 * la evidencia de que un comercio con instrucciones no logró colarse en el aviso.
 */

import { el, icono, vaciar } from "./dom.js";
import * as f from "./formato.js";
import { chipActor, chipBanda } from "./piezas.js";
import { tarjetaBloqueo } from "./bloqueos.js";

function dato(etiqueta, valor) {
  return el("div", {}, el("dt", { texto: etiqueta }), el("dd", { texto: valor }));
}

function pintarTriaje(triaje) {
  const r = triaje.resultado || {};
  const porAgente = r.tipo === "triaje" || (r.decision && !r.motivo);
  const decision = porAgente ? r.decision || {} : null;
  const accion = porAgente ? decision?.accion : r.accion;
  const resultado = porAgente ? decision?.resultado : r.resultado;
  const decisionAgente = !porAgente ? r.decision_agente : null;
  return el(
    "div",
    { clase: `triaje triaje--${porAgente ? "agente" : "regla"}` },
    el(
      "p",
      { clase: "triaje__titulo" },
      chipActor(porAgente ? "agente" : "regla"),
      el("strong", { texto: f.accionTriaje(accion) }),
      resultado ? el("span", { clase: "triaje__resultado", texto: `(${f.resultadoTriaje(resultado)})` }) : null,
    ),
    porAgente && r.resumen ? el("p", { clase: "triaje__resumen", texto: r.resumen }) : null,
    !porAgente
      ? el(
          "p",
          { clase: "triaje__resumen" },
          "Actuó la regla de respaldo porque ",
          el("strong", { texto: f.motivoRespaldo(r.motivo) }),
          decisionAgente?.accion ? `. El agente había intentado «${f.accionTriaje(decisionAgente.accion).toLowerCase()}» (${f.resultadoTriaje(decisionAgente.resultado)}).` : ".",
        )
      : null,
    decision?.detalle ? el("p", { clase: "triaje__detalle", texto: decision.detalle }) : null,
    el(
      "dl",
      { clase: "triaje__datos" },
      dato("Proveedor", triaje.proveedor_final ? `${f.proveedor(triaje.proveedor_final)}${triaje.modelo_final ? ` · ${triaje.modelo_final}` : ""}` : "—"),
      dato("Costo", f.costo(triaje.costo_usd)),
      dato("Latencia", f.duracion(triaje.latencia_ms)),
      dato("Iteraciones", f.numero(triaje.iteraciones)),
      dato("Fin", f.motivoFin(triaje.motivo_fin)),
      dato("Cuándo", f.fechaHora(triaje.creada_en)),
    ),
  );
}

function pintarAviso(aviso) {
  const errores = Array.isArray(aviso.errores_validacion) ? aviso.errores_validacion.filter(Boolean) : [];
  const delAgente = aviso.autor_motivo === "agente";
  return el(
    "article",
    { clase: "aviso-caso" },
    el(
      "p",
      { clase: "aviso-caso__cabecera" },
      el("span", { clase: `msj__tipo msj__tipo--${aviso.tipo === "verificacion" ? "verificacion" : "bloqueo"}`, texto: f.TIPOS_AVISO[aviso.tipo] || aviso.tipo }),
      el("span", { clase: `msj__autor msj__autor--${delAgente ? "agente" : "plantilla"}` }, icono(delAgente ? "modelo" : "documento"), delAgente ? "Motivo del agente" : "Motivo de plantilla"),
      el("span", { clase: "aviso-caso__meta", texto: [aviso.canal, aviso.destinatario, f.fechaHora(aviso.creada_en)].filter(Boolean).join(" · ") }),
    ),
    el("p", { clase: "aviso-caso__texto", texto: aviso.cuerpo || "" }),
    errores.length
      ? el(
          "div",
          { clase: "aviso-caso__errores", role: "note" },
          el("p", {}, icono("alerta"), el("strong", { texto: "El motivo del agente no pasó la validación" }), " — se envió el texto de la plantilla:"),
          el("ul", {}, errores.map((e) => el("li", { texto: e }))),
        )
      : null,
    el(
      "p",
      { clase: "aviso-caso__respuesta" },
      aviso.respuesta_titular
        ? [el("span", { clase: `chip-titular chip-titular--${aviso.respuesta_titular === "fui_yo" ? "fui" : "no"}`, texto: `Titular: ${f.RESPUESTAS_TITULAR[aviso.respuesta_titular] || aviso.respuesta_titular}` }), aviso.respondida_en ? ` · ${f.fechaHora(aviso.respondida_en)}` : ""]
        : el("span", { clase: "aviso-caso__espera", texto: "El titular aún no responde." }),
    ),
  );
}

/**
 * Pinta (u oculta) la sección. `datos` es la respuesta de GET /api/casos/{id}.
 * `alDesbloquear(bloqueo)` abre el diálogo de desbloqueo.
 */
export function pintarSistemaCaso(seccion, datos, { alDesbloquear }) {
  const bloqueos = datos?.bloqueos || [];
  const avisos = datos?.avisos || [];
  const triaje = datos?.ultimo_triaje || null;
  const enVivo = datos?.caso?.origen === "en_vivo";
  const cuerpo = seccion.querySelector(".sistema-caso__cuerpo");
  const ayuda = seccion.querySelector(".seccion__ayuda");
  vaciar(cuerpo);
  if (!bloqueos.length && !avisos.length && !triaje && !enVivo) {
    seccion.hidden = true;
    return;
  }
  seccion.hidden = false;
  const caso = datos.caso || {};
  vaciar(ayuda).append(
    enVivo ? "Caso del flujo en vivo" : "Acciones registradas para este caso",
    ...(caso.banda ? [" · banda ", chipBanda(caso.banda)] : []),
    caso.abierto_en ? ` · abierto ${f.fechaHora(caso.abierto_en)}` : "",
  );

  cuerpo.append(
    el(
      "div",
      { clase: "sistema-caso__bloque" },
      el("h4", { clase: "sistema-caso__subtitulo", texto: "Último triaje" }),
      triaje ? pintarTriaje(triaje) : el("p", { clase: "aviso-suave", texto: "Este caso todavía no tiene triaje: el agente lo revisa en segundo plano al abrirse o al subir de banda." }),
    ),
    el(
      "div",
      { clase: "sistema-caso__bloque" },
      el("h4", { clase: "sistema-caso__subtitulo", texto: `Bloqueos (${bloqueos.length})` }),
      bloqueos.length
        ? el("div", { clase: "sistema-caso__lista" }, bloqueos.map((b) => tarjetaBloqueo({ ...b, id_caso: b.id_caso || caso.id_caso, tarjeta_enmascarada: b.tarjeta_enmascarada || caso.tarjeta_enmascarada }, { alDesbloquear, compacto: true })))
        : el("p", { clase: "aviso-suave", texto: "Ningún bloqueo en este caso." }),
    ),
    el(
      "div",
      { clase: "sistema-caso__bloque" },
      el("h4", { clase: "sistema-caso__subtitulo", texto: `Avisos al titular (${avisos.length})` }),
      avisos.length ? el("div", { clase: "sistema-caso__lista" }, avisos.map(pintarAviso)) : el("p", { clase: "aviso-suave", texto: "No se ha enviado ningún aviso al titular." }),
    ),
  );
}
