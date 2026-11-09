/**
 * Vista "Supervisión" (#/supervision): los controles que deciden cuánto actúa el agente
 * solo y las cifras para saber si está actuando bien.
 *
 * - Autonomía del agente (interruptor). Apagarla pide confirmación: los casos pasan a la
 *   cola humana y la red de seguridad sigue activa (la regla bloquea los casos críticos
 *   que pasen cierto tiempo sin bloqueo).
 * - Tope de bloqueos autónomos por hora, con el uso de la última hora.
 * - Gasto en IA del día frente al tope diario.
 * - Cifras de operación (tiempos hasta el bloqueo, quién bloquea, latencia por decisión).
 * - Alertas pendientes con "Atender".
 *
 * Para el rol analista todo se ve en solo lectura: los controles quedan deshabilitados con
 * la explicación al lado (el servidor igual rechaza la escritura con 403).
 * Se refresca cada 5 s mientras la vista está visible.
 */

import { api } from "./api.js";
import { avisar, el, icono, vaciar } from "./dom.js";
import * as f from "./formato.js";
import { confirmar, enlaceCaso, estadoError, estadoVacio, medidorUso } from "./piezas.js";
import { sesion } from "./sesion.js";
import { crearSondeo } from "./sondeo.js";

export function crearSupervision() {
  const $ = (id) => document.getElementById(id);
  const nodos = {
    soloLectura: $("sup-solo-lectura"),
    interruptor: $("sup-autonomia"),
    autonomiaEstado: $("sup-autonomia-estado"),
    autonomiaTexto: $("sup-autonomia-texto"),
    autonomiaMeta: $("sup-autonomia-meta"),
    tope: $("sup-tope"),
    topeGuardar: $("sup-tope-guardar"),
    topeForm: $("form-tope"),
    topeUso: $("sup-tope-uso"),
    topeMedidor: $("sup-tope-medidor"),
    topeMeta: $("sup-tope-meta"),
    topeError: $("sup-tope-error"),
    gastoTexto: $("sup-gasto-texto"),
    gastoMedidor: $("sup-gasto-medidor"),
    gastoNota: $("sup-gasto-nota"),
    cifras: $("sup-cifras"),
    alertas: $("sup-alertas"),
    alertasTotal: $("sup-alertas-total"),
    error: $("sup-error"),
  };

  let datos = null;
  let topeEditado = false;
  let firmaAlertas = "";
  let ocupado = false;

  function meta(ajuste) {
    if (!ajuste) return "";
    const quien = ajuste.actualizado_por ? `por ${ajuste.actualizado_por}` : "";
    return ajuste.actualizado_en ? `Último cambio ${quien} · ${f.fechaHora(ajuste.actualizado_en)}`.replace("  ", " ") : "";
  }

  function pintarControles() {
    const supervisor = sesion.esSupervisor;
    nodos.soloLectura.hidden = supervisor;
    const autonomia = Boolean(datos.ajustes?.autonomia_agente?.valor);
    nodos.interruptor.setAttribute("aria-checked", String(autonomia));
    nodos.interruptor.disabled = !supervisor || ocupado;
    nodos.autonomiaEstado.textContent = autonomia ? "Encendida" : "Apagada";
    nodos.autonomiaEstado.className = `interruptor__estado interruptor__estado--${autonomia ? "on" : "off"}`;
    nodos.autonomiaTexto.textContent = autonomia
      ? "El agente puede bloquear por su cuenta, sin esperar a un analista, hasta el tope por hora."
      : `El agente no bloquea solo: los casos pasan a la cola humana. La red de seguridad sigue activa (${f.numero(datos.segundos_red_de_seguridad)} s).`;
    nodos.autonomiaMeta.textContent = meta(datos.ajustes?.autonomia_agente);

    const tope = Number(datos.ajustes?.tope_bloqueos_autonomos_por_hora?.valor ?? 0);
    const usados = Number(datos.cifras?.bloqueos_agente_hora ?? 0);
    if (!topeEditado && document.activeElement !== nodos.tope) nodos.tope.value = String(tope);
    nodos.tope.disabled = !supervisor;
    nodos.topeGuardar.disabled = !supervisor || ocupado;
    nodos.topeUso.textContent = `${f.numero(usados)} de ${f.numero(tope)} en la última hora`;
    vaciar(nodos.topeMedidor).append(medidorUso(usados, tope, { etiqueta: "Bloqueos autónomos en la última hora frente al tope" }));
    nodos.topeMeta.textContent = tope === 0 ? "Con tope 0 el agente no puede bloquear solo aunque la autonomía esté encendida." : meta(datos.ajustes?.tope_bloqueos_autonomos_por_hora);

    const gasto = Number(datos.gasto_del_dia_usd ?? 0);
    const topeGasto = Number(datos.tope_gasto_diario_usd ?? 0);
    nodos.gastoTexto.textContent = `${f.gasto(gasto)} de ${f.usd(topeGasto)}`;
    vaciar(nodos.gastoMedidor).append(medidorUso(gasto, topeGasto, { etiqueta: "Gasto en IA del día frente al tope diario" }));
    nodos.gastoNota.textContent = topeGasto && gasto >= topeGasto ? "Se alcanzó el tope diario de gasto en IA." : topeGasto ? `Queda ${f.gasto(Math.max(0, topeGasto - gasto))} para hoy.` : "";
  }

  function cifra(etiqueta, valor, nota, { destacada = false, extra = null } = {}) {
    return el(
      "div",
      { clase: `cifra-sup${destacada ? " cifra-sup--destacada" : ""}` },
      el("dt", { clase: "cifra-sup__etiqueta", texto: etiqueta }),
      el("dd", { clase: "cifra-sup__valor", texto: valor }),
      nota ? el("dd", { clase: "cifra-sup__nota", texto: nota }) : null,
      extra,
    );
  }

  function repartoActores(agente, regla) {
    const total = agente + regla;
    if (!total) return null;
    const pa = (agente / total) * 100;
    return el(
      "dd",
      { clase: "reparto", "aria-hidden": "true" },
      el("span", { clase: "reparto__parte actor-agente", estilo: { "--valor": `${pa.toFixed(1)}%` } }),
      el("span", { clase: "reparto__parte actor-regla", estilo: { "--valor": `${(100 - pa).toFixed(1)}%` } }),
    );
  }

  function pintarCifras() {
    const c = datos.cifras || {};
    const agente = Number(c.bloqueos_por_agente) || 0;
    const regla = Number(c.bloqueos_por_regla) || 0;
    vaciar(nodos.cifras).append(
      cifra("Hasta el bloqueo · mediana", f.segundos(c.mediana_s_hasta_bloqueo), `máximo ${f.segundos(c.maximo_s_hasta_bloqueo)}`, { destacada: true }),
      cifra("Bloqueos por agente / regla", `${f.numero(agente)} / ${f.numero(regla)}`, agente + regla ? `${f.porcentaje((agente / (agente + regla)) * 100, 0)} los hizo el agente` : "Aún no hay bloqueos", { extra: repartoActores(agente, regla) }),
      cifra("Hasta el desbloqueo · mediana", f.segundos(c.mediana_s_hasta_desbloqueo), "desde el bloqueo hasta que un analista lo levanta"),
      cifra("Decisión por transacción", f.milisegundos(c.mediana_ms_decision), `mediana · p99 ${f.milisegundos(c.p99_ms_decision)}`),
      cifra("Monto detenido", f.usd(c.monto_detenido), `${f.numero(c.compras_detenidas)} compras rechazadas por bloqueo`, { destacada: true }),
      cifra("Bloqueos activos", f.numero(c.bloqueos_activos), c.esperan_desbloqueo ? `${f.numero(c.esperan_desbloqueo)} esperan desbloqueo (el titular dijo «fui yo»)` : "ninguno espera desbloqueo"),
      cifra("Casos en la cola humana", f.numero(c.casos_en_cola), "esperan la decisión de un analista"),
      cifra("Transacciones evaluadas", f.numero(c.transacciones_evaluadas), "por el motor en el flujo en vivo"),
    );
  }

  async function atender(alerta, boton) {
    boton.disabled = true;
    try {
      await api.atenderAlerta(alerta.id);
      avisar("Alerta atendida");
      firmaAlertas = "";
      sondeo.ahora();
    } catch (error) {
      avisar(error.message, "error");
      boton.disabled = false;
    }
  }

  function pintarAlertas() {
    const alertas = datos.alertas || [];
    const firma = JSON.stringify(alertas.map((a) => a.id)) + sesion.esSupervisor;
    nodos.alertasTotal.textContent = alertas.length ? `${f.numero(alertas.length)} pendiente${alertas.length === 1 ? "" : "s"}` : "";
    if (firma === firmaAlertas) return;
    firmaAlertas = firma;
    vaciar(nodos.alertas);
    if (!alertas.length) {
      nodos.alertas.append(el("li", {}, estadoVacio({ iconoNombre: "check", titulo: "Sin alertas pendientes", texto: "Aquí aparecen el tope de bloqueos alcanzado, las actuaciones de la red de seguridad y los triajes que no bloquearon un caso crítico." })));
      return;
    }
    for (const a of alertas) {
      const boton = el("button", { type: "button", clase: "boton boton--secundario boton--chico", disabled: !sesion.esSupervisor, title: sesion.esSupervisor ? null : "Solo el rol supervisor puede atender alertas" }, icono("check"), "Atender");
      boton.addEventListener("click", () => atender(a, boton));
      nodos.alertas.append(
        el(
          "li",
          { clase: `alerta-sup alerta-sup--${a.tipo}` },
          el("span", { clase: "alerta-sup__icono", "aria-hidden": "true" }, icono(a.tipo === "red_de_seguridad" ? "regla" : a.tipo === "tope_bloqueos_agente" ? "limite" : "alerta")),
          el(
            "div",
            { clase: "alerta-sup__cuerpo" },
            el("p", { clase: "alerta-sup__titulo", texto: f.tipoAlerta(a.tipo) }),
            a.detalle ? el("p", { clase: "alerta-sup__detalle", texto: typeof a.detalle === "string" ? a.detalle : JSON.stringify(a.detalle) }) : null,
            el("p", { clase: "alerta-sup__meta" }, el("span", { title: f.fechaHora(a.creada_en), texto: f.haceCuanto(a.creada_en) }), enlaceCaso(a.id_caso)),
          ),
          boton,
        ),
      );
    }
  }

  async function cargar(senal) {
    try {
      datos = await api.supervision(senal);
    } catch (error) {
      if (error.name !== "AbortError" && error.estado !== 401) {
        nodos.error.hidden = false;
        vaciar(nodos.error).append(estadoError(error.message, () => sondeo.ahora()));
      }
      throw error;
    }
    nodos.error.hidden = true;
    pintarControles();
    pintarCifras();
    pintarAlertas();
  }

  async function guardarAjuste(clave, valor, mensaje) {
    ocupado = true;
    if (datos) pintarControles();
    try {
      await api.cambiarAjuste(clave, valor);
      avisar(mensaje);
      return true;
    } catch (error) {
      avisar(error.message, "error");
      return false;
    } finally {
      ocupado = false;
      sondeo.ahora();
    }
  }

  nodos.interruptor.addEventListener("click", async () => {
    if (!datos || !sesion.esSupervisor) return;
    const encendida = Boolean(datos.ajustes?.autonomia_agente?.valor);
    if (encendida) {
      const ok = await confirmar({
        titulo: "¿Apagar la autonomía del agente?",
        texto: `El agente dejará de bloquear por su cuenta: los casos pasan a la cola humana y un analista decide cada uno. La red de seguridad sigue activa: si un caso crítico pasa ${f.numero(datos.segundos_red_de_seguridad)} s sin bloqueo, la regla lo bloquea.`,
        textoBoton: "Apagar autonomía",
        peligro: true,
      });
      if (!ok) return nodos.interruptor.focus();
    }
    const guardado = await guardarAjuste("autonomia_agente", !encendida, encendida ? "Autonomía apagada: los casos van a la cola humana" : "Autonomía encendida");
    if (guardado) datos.ajustes.autonomia_agente.valor = !encendida;
    pintarControles();
    nodos.interruptor.focus();
  });

  nodos.tope.addEventListener("input", () => {
    topeEditado = true;
    nodos.topeError.hidden = true;
  });

  nodos.topeForm.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    const valor = Number(nodos.tope.value);
    if (!Number.isInteger(valor) || valor < 0 || valor > 500) {
      nodos.topeError.textContent = "El tope debe ser un número entero entre 0 y 500.";
      nodos.topeError.hidden = false;
      nodos.tope.focus();
      return;
    }
    if (await guardarAjuste("tope_bloqueos_autonomos_por_hora", valor, `Tope guardado: ${f.numero(valor)} bloqueos por hora`)) topeEditado = false;
  });

  const sondeo = crearSondeo(cargar, 5000);

  return {
    mostrar() {
      firmaAlertas = "";
      sondeo.iniciar();
    },
    ocultar() {
      sondeo.detener();
    },
  };
}
