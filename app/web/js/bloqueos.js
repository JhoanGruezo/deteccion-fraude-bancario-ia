/**
 * Vista "Bloqueos" (#/bloqueos): todas las tarjetas y accesos bloqueados, quién los
 * bloqueó y en cuánto tiempo, qué aviso recibió el titular y qué respondió.
 *
 * Los bloqueos activos en los que el titular respondió "fui yo" vienen primero desde el
 * servidor y aquí se destacan: son falsas alarmas probables con un cliente sin tarjeta,
 * la prioridad de desbloqueo. Desbloquear abre el diálogo de desbloqueo.js (motivo de al
 * menos 10 caracteres, firma del usuario de la sesión).
 *
 * Se refresca cada 8 s mientras la vista está visible.
 */

import { api } from "./api.js";
import { avisar, el, icono, vaciar } from "./dom.js";
import * as f from "./formato.js";
import { chipActor, chipBanda, enlaceCaso, estadoError, estadoVacio, esqueleto } from "./piezas.js";
import { crearSondeo } from "./sondeo.js";

const FILTROS = [
  { valor: "activo", etiqueta: "Activos" },
  { valor: "levantado", etiqueta: "Levantados" },
  { valor: "", etiqueta: "Todos" },
];

/** Tarjeta de un bloqueo; la usa también el detalle del caso (con `compacto`). */
export function tarjetaBloqueo(b, { alDesbloquear, compacto = false } = {}) {
  const activo = b.estado === "activo";
  const fueEl = activo && b.respuesta_titular === "fui_yo";
  const noFueEl = b.respuesta_titular === "no_fui_yo";
  const tarjeta = [b.alias, b.tarjeta_enmascarada ? f.tarjetaCorta(b.tarjeta_enmascarada) : null].filter(Boolean).join(" · ");
  return el(
    "article",
    { clase: `bloqueo${activo ? " bloqueo--activo" : " bloqueo--levantado"}${fueEl ? " bloqueo--prioridad" : ""}${compacto ? " bloqueo--compacto" : ""}`, "aria-label": `Bloqueo ${b.id}` },
    fueEl
      ? el("p", { clase: "bloqueo__prioridad" }, icono("alerta"), el("span", {}, "El titular dice que ", el("strong", { texto: "FUE ÉL" }), " → prioridad de desbloqueo"))
      : null,
    el(
      "div",
      { clase: "bloqueo__cabecera" },
      el(
        "p",
        { clase: "bloqueo__titulo" },
        icono(activo ? "candado" : "candado-abierto"),
        el("span", { texto: `${f.tipoBloqueo(b.tipo)}${tarjeta && !compacto ? ` ${tarjeta}` : ""}` }),
      ),
      chipBanda(b.banda),
      el("span", { clase: `estado${activo ? " estado--activo" : " estado--cerrado"}`, texto: activo ? "Activo" : "Levantado" }),
      !compacto ? enlaceCaso(b.id_caso) : null,
    ),
    el(
      "p",
      { clase: "bloqueo__actor" },
      chipActor(b.actor, b.usuario),
      b.segundos_hasta_bloqueo != null ? el("span", { clase: "bloqueo__tiempo" }, "bloqueó en ", el("strong", { texto: f.segundos(b.segundos_hasta_bloqueo) })) : null,
      el("span", { clase: "bloqueo__fecha", title: f.fechaHora(b.creado_en), texto: f.haceCuanto(b.creado_en) }),
      b.score_maximo != null ? el("span", { clase: "bloqueo__fecha", texto: `score ${f.puntaje(b.score_maximo)}` }) : null,
    ),
    b.motivo ? el("p", { clase: "bloqueo__motivo" }, el("span", { clase: "bloqueo__rotulo", texto: "Motivo" }), el("span", { texto: b.motivo })) : null,
    noFueEl ? el("p", { clase: "chip-titular chip-titular--no", texto: "El titular confirma que NO fue él: mantener el bloqueo" }) : null,
    activo && !b.respuesta_titular && b.aviso ? el("p", { clase: "bloqueo__espera", texto: "Esperando la respuesta del titular." }) : null,
    b.aviso
      ? el(
          "details",
          { clase: "bloqueo__aviso" },
          el("summary", {}, `Aviso enviado al titular · motivo ${b.autor_motivo === "agente" ? "del agente" : "de plantilla"}`, b.respondida_en ? ` · respondió ${f.haceCuanto(b.respondida_en)}` : ""),
          el("p", { clase: "bloqueo__aviso-texto", texto: b.aviso }),
        )
      : null,
    !activo && (b.levantado_por || b.motivo_desbloqueo)
      ? el(
          "p",
          { clase: "bloqueo__levantado" },
          icono("candado-abierto"),
          el("span", {}, "Levantado por ", el("strong", { texto: b.levantado_por || "—" }), b.levantado_en ? ` · ${f.fechaHora(b.levantado_en)}` : "", b.motivo_desbloqueo ? el("span", { clase: "bloqueo__motivo-desbloqueo", texto: `«${b.motivo_desbloqueo}»` }) : null),
        )
      : null,
    activo && alDesbloquear
      ? el(
          "div",
          { clase: "bloqueo__acciones" },
          el("button", { type: "button", clase: `boton ${fueEl ? "boton--primario" : "boton--secundario"} boton--chico`, onClick: () => alDesbloquear(b) }, icono("candado-abierto"), "Desbloquear"),
        )
      : null,
  );
}

export function crearBloqueos({ desbloqueo }) {
  const $ = (id) => document.getElementById(id);
  const lista = $("lista-bloqueos");
  const segmento = $("filtro-bloqueos");
  const total = $("bloqueos-total");
  const actualizar = $("bloqueos-actualizar");

  let filtro = "activo";
  let firma = "";
  let cargado = false;

  function pintarSegmento() {
    vaciar(segmento).append(
      ...FILTROS.map((o) =>
        el("button", {
          type: "button",
          clase: "segmento__opcion",
          "aria-pressed": String(filtro === o.valor),
          texto: o.etiqueta,
          onClick: () => {
            if (filtro === o.valor) return;
            filtro = o.valor;
            firma = "";
            cargado = false;
            pintarSegmento();
            vaciar(lista).append(el("li", {}, esqueleto(4)));
            sondeo.ahora();
          },
        }),
      ),
    );
  }

  async function alDesbloquear(bloqueo) {
    const resultado = await desbloqueo.abrir(bloqueo);
    if (resultado) {
      avisar(`Bloqueo levantado · firmado por ${resultado.firmado_por || "tu usuario"}`);
      firma = "";
      sondeo.ahora();
    }
  }

  async function cargar(senal) {
    let datos;
    try {
      datos = await api.bloqueos(filtro || null, senal);
    } catch (error) {
      if (error.name !== "AbortError" && error.estado !== 401 && !cargado) vaciar(lista).append(el("li", {}, estadoError(error.message, () => sondeo.ahora())));
      throw error;
    }
    cargado = true;
    const bloqueos = datos.bloqueos || [];
    // El minuto actual entra en la firma para que los "hace 2 min" no se queden congelados.
    const nuevaFirma = JSON.stringify(bloqueos.map((b) => [b.id, b.estado, b.respuesta_titular, b.aviso ? 1 : 0])) + Math.floor(Date.now() / 60000);
    const activos = bloqueos.filter((b) => b.estado === "activo").length;
    const prioridad = bloqueos.filter((b) => b.estado === "activo" && b.respuesta_titular === "fui_yo").length;
    total.textContent = `${f.numero(bloqueos.length)} bloqueo${bloqueos.length === 1 ? "" : "s"}${filtro !== "activo" ? ` · ${f.numero(activos)} activos` : ""}${prioridad ? ` · ${f.numero(prioridad)} con prioridad de desbloqueo` : ""}`;
    if (nuevaFirma === firma) return;
    firma = nuevaFirma;
    // Conserva lo que el usuario tenía desplegado (los avisos) entre repintados.
    const abiertos = new Set([...lista.querySelectorAll("details[open]")].map((d) => d.closest("[data-id]")?.dataset.id));
    vaciar(lista);
    if (!bloqueos.length) {
      lista.append(el("li", {},
        estadoVacio({
          iconoNombre: "escudo",
          titulo: filtro === "activo" ? "No hay bloqueos activos" : filtro === "levantado" ? "Aún no se ha levantado ningún bloqueo" : "Todavía no hay bloqueos",
          texto: "Los bloqueos aparecen cuando el agente, la regla de respaldo o un analista detienen una tarjeta. Inicia el simulador en «En vivo» para generarlos.",
          acciones: [el("a", { clase: "boton boton--secundario boton--chico", href: "#/en-vivo" }, icono("pulso"), "Ir a En vivo")],
        }),
      ));
      return;
    }
    for (const b of bloqueos) {
      const nodo = tarjetaBloqueo(b, { alDesbloquear });
      const contenedor = el("li", { dataset: { id: String(b.id) } }, nodo);
      if (abiertos.has(String(b.id))) contenedor.querySelector("details")?.setAttribute("open", "");
      lista.append(contenedor);
    }
  }

  const sondeo = crearSondeo(cargar, 8000);
  actualizar.addEventListener("click", () => {
    firma = "";
    sondeo.ahora();
  });
  pintarSegmento();

  return {
    mostrar() {
      if (!cargado) vaciar(lista).append(el("li", {}, esqueleto(4)));
      sondeo.iniciar();
    },
    ocultar() {
      sondeo.detener();
    },
  };
}
