/**
 * Vista "Buzón del titular" (#/buzon): simula el teléfono del cliente con los avisos que
 * le mandó el banco, como un chat (el más viejo arriba, el más reciente abajo).
 *
 * Cada aviso dice si el motivo lo redactó el agente o salió de la plantilla. Si el motivo
 * del agente no pasó la validación (por ejemplo, porque un comercio malicioso intentó
 * meterle instrucciones y el texto resultante citaba cosas que no están en los datos), se
 * marca con un ícono y su explicación: es la defensa contra inyección hecha visible.
 *
 * "Sí, fui yo" / "No fui yo" llaman a POST /api/avisos/{id}/responder; la respuesta queda
 * como un mensaje del titular. Se refresca cada 4 s mientras la vista está visible.
 */

import { api } from "./api.js";
import { avisar, el, icono, vaciar } from "./dom.js";
import * as f from "./formato.js";
import { enlaceCaso, estadoError, estadoVacio, esqueleto } from "./piezas.js";
import { crearSondeo } from "./sondeo.js";

const fmtHoraChat = new Intl.DateTimeFormat("es-CO", { hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
const fmtDiaChat = new Intl.DateTimeFormat("es-CO", { weekday: "long", day: "numeric", month: "long" });

export function crearBuzon() {
  const $ = (id) => document.getElementById(id);
  const chat = $("buzon-chat");
  const filtro = $("buzon-filtro");
  const resumen = $("buzon-resumen");
  const horaTelefono = $("telefono-hora");

  let avisos = [];
  let firma = "";
  let cargado = false;
  let contador = 0;
  let cargadoAntes = false; // la primera pintura baja hasta el último mensaje
  const respondiendo = new Set();

  function horaDe(texto) {
    const fecha = f.aFecha(texto);
    return fecha ? fmtHoraChat.format(fecha) : "";
  }

  function pintarFiltro() {
    const elegido = filtro.value;
    const alias = [...new Set(avisos.map((a) => a.alias).filter(Boolean))].sort();
    const firmaOpciones = alias.join("|");
    if (filtro.dataset.firma === firmaOpciones) return;
    filtro.dataset.firma = firmaOpciones;
    vaciar(filtro).append(el("option", { value: "", texto: "Todas las tarjetas" }), ...alias.map((a) => el("option", { value: a, texto: a })));
    filtro.value = alias.includes(elegido) ? elegido : "";
  }

  async function responder(aviso, respuesta, botones) {
    respondiendo.add(aviso.id);
    for (const b of botones) b.disabled = true;
    try {
      await api.responderAviso(aviso.id, respuesta);
      avisar(respuesta === "fui_yo" ? "Respuesta enviada: «Sí, fui yo»" : "Respuesta enviada: «No fui yo»");
    } catch (error) {
      avisar(error.message, "error");
    } finally {
      respondiendo.delete(aviso.id);
      firma = "";
      sondeo.ahora();
    }
  }

  function burbujaBanco(aviso) {
    const errores = Array.isArray(aviso.errores_validacion) ? aviso.errores_validacion.filter(Boolean) : [];
    const delAgente = aviso.autor_motivo === "agente";
    contador += 1;
    const idTooltip = `tooltip-aviso-${aviso.id}-${contador}`;
    const botones = [];
    if (!aviso.respuesta_titular) {
      const si = el("button", { type: "button", clase: "respuesta-rapida", texto: "Sí, fui yo" });
      const no = el("button", { type: "button", clase: "respuesta-rapida respuesta-rapida--no", texto: "No fui yo" });
      botones.push(si, no);
      si.addEventListener("click", () => responder(aviso, "fui_yo", botones));
      no.addEventListener("click", () => responder(aviso, "no_fui_yo", botones));
      if (respondiendo.has(aviso.id)) for (const b of botones) b.disabled = true;
    }
    return el(
      "li",
      { clase: "msj msj--banco" },
      el(
        "div",
        { clase: "msj__burbuja" },
        el(
          "p",
          { clase: "msj__etiquetas" },
          el("span", { clase: `msj__tipo msj__tipo--${aviso.tipo === "verificacion" ? "verificacion" : "bloqueo"}`, texto: f.TIPOS_AVISO[aviso.tipo] || aviso.tipo || "Aviso" }),
          el("span", { clase: `msj__autor msj__autor--${delAgente ? "agente" : "plantilla"}`, title: delAgente ? "El motivo lo redactó el agente y pasó la validación" : "El motivo sale de una plantilla fija, no del agente" }, icono(delAgente ? "modelo" : "documento"), delAgente ? "Motivo del agente" : "Motivo de plantilla"),
          errores.length
            ? el(
                "span",
                { clase: "msj__validacion" },
                el("button", { type: "button", clase: "msj__validacion-boton", "aria-describedby": idTooltip, "aria-label": "El motivo del agente no pasó la validación" }, icono("alerta")),
                el("span", { clase: "msj__tooltip", role: "tooltip", id: idTooltip }, el("strong", { texto: "El motivo del agente no pasó la validación: " }), errores.join(" · "), el("span", { clase: "msj__tooltip-nota", texto: " Por eso se envió el texto de la plantilla." })),
              )
            : null,
        ),
        el("p", { clase: "msj__texto", texto: aviso.cuerpo || "" }),
        el("p", { clase: "msj__meta" }, el("span", { texto: [aviso.alias, aviso.canal].filter(Boolean).join(" · ") }), enlaceCaso(aviso.id_caso), el("time", { datetime: aviso.creada_en || "", texto: horaDe(aviso.creada_en) })),
        botones.length ? el("div", { clase: "msj__respuestas", role: "group", "aria-label": "Responder al banco" }, botones) : null,
      ),
    );
  }

  function burbujaTitular(aviso) {
    return el(
      "li",
      { clase: "msj msj--titular" },
      el(
        "div",
        { clase: `msj__burbuja${aviso.respuesta_titular === "no_fui_yo" ? " msj__burbuja--no" : ""}` },
        el("p", { clase: "msj__texto", texto: f.RESPUESTAS_TITULAR[aviso.respuesta_titular] || aviso.respuesta_titular }),
        el("p", { clase: "msj__meta" }, el("time", { datetime: aviso.respondida_en || "", texto: horaDe(aviso.respondida_en) }), icono("check")),
      ),
    );
  }

  function pintarChat() {
    const cercaDelFinal = chat.scrollHeight - chat.scrollTop - chat.clientHeight < 80;
    const elegido = filtro.value;
    const visibles = avisos.filter((a) => !elegido || a.alias === elegido).sort((a, b) => String(a.creada_en).localeCompare(String(b.creada_en)) || a.id - b.id);
    const pendientes = visibles.filter((a) => !a.respuesta_titular).length;
    resumen.textContent = visibles.length ? `${f.numero(visibles.length)} aviso${visibles.length === 1 ? "" : "s"} · ${f.numero(pendientes)} sin responder` : "";
    vaciar(chat);
    if (!visibles.length) {
      chat.append(
        el(
          "li",
          { clase: "msj msj--vacio" },
          estadoVacio({
            iconoNombre: "telefono",
            titulo: elegido ? `Sin avisos para ${elegido}` : "Sin mensajes del banco",
            texto: "Cuando el sistema bloquee una tarjeta o necesite verificar una compra, el aviso al titular llegará aquí.",
          }),
        ),
      );
      return;
    }
    let dia = "";
    for (const aviso of visibles) {
      const fecha = f.aFecha(aviso.creada_en);
      const clave = fecha ? fecha.toDateString() : "";
      if (clave && clave !== dia) {
        dia = clave;
        chat.append(el("li", { clase: "msj-dia" }, el("span", { texto: fmtDiaChat.format(fecha) })));
      }
      chat.append(burbujaBanco(aviso));
      if (aviso.respuesta_titular) chat.append(burbujaTitular(aviso));
    }
    if (cercaDelFinal || !cargadoAntes) chat.scrollTop = chat.scrollHeight;
  }

  async function cargar(senal) {
    horaTelefono.textContent = fmtHoraChat.format(new Date());
    let datos;
    try {
      datos = await api.avisos(150, senal);
    } catch (error) {
      if (error.name !== "AbortError" && error.estado !== 401 && !cargado) vaciar(chat).append(el("li", { clase: "msj msj--vacio" }, estadoError(error.message, () => sondeo.ahora())));
      throw error;
    }
    avisos = datos.avisos || [];
    const nuevaFirma = JSON.stringify(avisos.map((a) => [a.id, a.respuesta_titular, a.estado]));
    cargado = true;
    pintarFiltro();
    if (nuevaFirma === firma) return;
    // No se repinta mientras el foco está en un botón de respuesta: se perdería el foco.
    if (chat.contains(document.activeElement) && document.activeElement.matches(".respuesta-rapida") && firma) return;
    firma = nuevaFirma;
    pintarChat();
    cargadoAntes = true;
  }

  filtro.addEventListener("change", () => {
    cargadoAntes = false;
    pintarChat();
    cargadoAntes = true;
  });

  const sondeo = crearSondeo(cargar, 4000);

  return {
    mostrar() {
      if (!cargado) vaciar(chat).append(el("li", { clase: "msj msj--vacio" }, esqueleto(4)));
      cargadoAntes = false;
      firma = "";
      sondeo.iniciar();
    },
    ocultar() {
      sondeo.detener();
    },
  };
}
