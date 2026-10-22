/**
 * Detalle del caso: cabecera con el veredicto, explicación, línea de tiempo, razones,
 * perfil habitual, propuestas del agente y decisiones del analista.
 *
 * Orden de carga al abrir un caso: detalle + historial en paralelo; con el detalle ya
 * pintado se abre el stream de la explicación (caché al instante o generación en
 * vivo). Si el analista cambia de caso a mitad de camino, las respuestas viejas se
 * descartan con un contador de versión para que nunca se mezclen dos casos.
 */

import { api } from "./api.js";
import { avisar, el, icono, pintarBanda, vaciar } from "./dom.js";
import { crearExplicacion } from "./explicacion.js";
import * as f from "./formato.js";

const ESTADO_TRAS_ACCION = { confirmar_bloqueo: "bloqueo_confirmado", descartar: "descartado", escalar: "escalado" };

export function crearDetalle({ trazas, conversacion, dialogo, alCambio }) {
  const $ = (id) => document.getElementById(id);
  const vacio = $("detalle-vacio");
  const contenido = $("detalle-contenido");
  const columna = $("detalle");
  const banda = $("banda-caso");

  let caso = null;
  let propuestas = [];
  let version = 0;
  let controlador = null;

  const explicacion = crearExplicacion({
    trazas,
    alPropuesta: agregarPropuesta,
    alTerminar: () => {
      refrescar();
      alCambio?.();
    },
  });

  // ----- Cabecera -------------------------------------------------------------------
  function claseNivel() {
    return `nivel-${f.NIVELES[caso.nivel_recomendacion]?.clase || "cerrado"}`;
  }

  function pintarCabecera() {
    const nivel = f.NIVELES[caso.nivel_recomendacion] || { etiqueta: caso.nivel_recomendacion };
    const estado = f.ESTADOS[caso.estado] || { etiqueta: caso.estado, cerrado: false };
    f.fijarMonedaDeFuente(caso.fuente);
    contenido.className = `detalle ${claseNivel()}`;
    $("caso-id").textContent = caso.id_caso;
    $("caso-tarjeta").textContent = `Tarjeta ${f.tarjetaCorta(caso.tarjeta_enmascarada)}`;
    $("caso-fuente").textContent = f.FUENTES[caso.fuente] || caso.fuente || "";
    const nodoEstado = $("caso-estado");
    nodoEstado.textContent = estado.etiqueta;
    nodoEstado.className = `estado${estado.cerrado ? " estado--cerrado" : ""}`;
    $("caso-nivel").textContent = `Recomendación: ${nivel.etiqueta}`;
    $("caso-motivo").textContent = caso.motivo_recomendacion || "";
    const n = (caso.transacciones || []).length;
    const datos = [
      ["Ventana", `${f.fechaHora(caso.inicio_ventana)} → ${f.hora(caso.fin_ventana)} ${f.fecha(caso.fin_ventana) !== f.fecha(caso.inicio_ventana) ? `(${f.fecha(caso.fin_ventana)})` : ""}`],
      ["Score máximo", f.puntaje(caso.score_maximo)],
      ["Transacciones marcadas", `${f.numero(n)}${caso.transacciones_sobre_umbral_bloqueo != null ? ` · ${f.numero(caso.transacciones_sobre_umbral_bloqueo)} sobre el umbral` : ""}`],
      ["Monto en el caso", f.moneda((caso.transacciones || []).reduce((s, t) => s + Number(t.monto || 0), 0))],
      ["Señal principal", f.senal(caso.senal_principal)],
    ];
    if (caso.umbral_bloqueo != null) datos.push(["Umbrales", `verificar ${f.puntaje(caso.umbral_verificacion)} · bloquear ${f.puntaje(caso.umbral_bloqueo)}`]);
    vaciar($("caso-datos")).append(...datos.map(([dt, dd]) => el("div", {}, el("dt", { texto: dt }), el("dd", { texto: dd }))));
  }

  // ----- Línea de tiempo --------------------------------------------------------------
  function pintarLinea(historial, falloHistorial) {
    const lista = vaciar($("linea-tiempo"));
    const ayuda = $("linea-ayuda");
    const scores = new Map((caso.transacciones || []).map((t) => [t.id_transaccion, t.score]));
    // Las transacciones del caso siempre están, aunque el historial no las traiga.
    const porId = new Map();
    for (const tx of historial || []) porId.set(tx.id_transaccion, { ...tx, en_caso: Boolean(tx.en_caso) || scores.has(tx.id_transaccion) });
    for (const tx of caso.transacciones || []) if (!porId.has(tx.id_transaccion)) porId.set(tx.id_transaccion, { ...tx, en_caso: true });
    const movimientos = [...porId.values()].sort((a, b) => String(a.fecha_hora).localeCompare(String(b.fecha_hora)));

    const promedio = Number(caso.perfil_previo?.monto_promedio) || null;
    const maximo = Math.max(...movimientos.map((m) => Number(m.monto) || 0), promedio || 0, 1);
    const previas = movimientos.filter((m) => !m.en_caso).length;
    const sinHistorial = caso.perfil_previo?.sin_historial || previas === 0;

    ayuda.replaceChildren(
      el(
        "span",
        { clase: "leyenda" },
        el("span", {}, el("span", { clase: "leyenda__muestra leyenda__muestra--caso" }), "Transacción del caso (con su score)"),
        el("span", {}, el("span", { clase: "leyenda__muestra" }), "Historial previo"),
        promedio ? el("span", {}, el("span", { clase: "leyenda__muestra leyenda__muestra--promedio" }), `Promedio previo ${f.moneda(promedio)}`) : null,
      ),
    );

    if (falloHistorial) lista.append(el("li", { clase: "aviso-suave", texto: `No se pudo cargar el historial (${falloHistorial}). Se muestran solo las transacciones del caso.` }));
    else if (sinHistorial) lista.append(el("li", { clase: "aviso-suave", texto: "Esta tarjeta no tiene historial previo en los últimos 30 días: el sistema solo conoce las transacciones del caso, por eso la señal «historial» pesa." }));

    let diaActual = "";
    let marcaPuesta = false;
    for (const mov of movimientos) {
      const dia = f.claveDia(mov.fecha_hora);
      if (dia !== diaActual) {
        diaActual = dia;
        lista.append(el("li", { clase: "linea__dia", texto: f.dia(mov.fecha_hora) }));
      }
      if (!marcaPuesta && mov.en_caso) {
        marcaPuesta = true;
        lista.append(el("li", { clase: "linea__marca", texto: "Empieza la ventana del caso" }));
      }
      const monto = Number(mov.monto) || 0;
      const descripcion = [f.categoria(mov.categoria), mov.comercio, mov.ubicacion].filter(Boolean).join(" · ");
      lista.append(
        el(
          "li",
          { id: `tx-${mov.id_transaccion}`, clase: `mov${mov.en_caso ? " mov--caso" : ""}` },
          el("time", { clase: "mov__hora", datetime: String(mov.fecha_hora).replace(" ", "T"), texto: f.hora(mov.fecha_hora) }),
          el(
            "span",
            { clase: "mov__pista", "aria-hidden": "true" },
            el("span", { clase: "mov__barra", estilo: { "--ancho": `${((monto / maximo) * 100).toFixed(1)}%` } }),
            promedio ? el("span", { clase: "mov__promedio", estilo: { "--promedio": `${((promedio / maximo) * 100).toFixed(1)}%` } }) : null,
          ),
          el("span", { clase: "mov__monto", texto: f.moneda(monto) }),
          el("span", { clase: "mov__desc", title: descripcion, texto: descripcion || "—" }),
          el("span", { clase: "mov__score", texto: mov.en_caso && scores.has(mov.id_transaccion) ? `score ${f.puntaje(scores.get(mov.id_transaccion))}` : "" }),
        ),
      );
    }
  }

  // ----- Razones -------------------------------------------------------------------------
  function medidor(valor, { signo = false, maximo = 1 } = {}) {
    const numero = Number(valor) || 0;
    const ancho = Math.min(100, (Math.abs(numero) / maximo) * 100);
    return el(
      "span",
      { clase: `medidor${signo ? " medidor--signo" : ""}${signo && numero < 0 ? " medidor--negativo" : ""}` },
      el("span", { clase: "medidor__pista", "aria-hidden": "true" }, el("span", { clase: "medidor__relleno", estilo: { "--valor": `${ancho.toFixed(1)}%` } })),
      el("span", { clase: "razon__cifra", texto: signo ? f.numero(numero, 2) : f.porcentaje(numero) }),
    );
  }

  function tablaRazones(idTx, desviaciones) {
    return el(
      "table",
      { clase: "tabla-razones" },
      el("thead", {}, el("tr", {}, el("th", { scope: "col", texto: "Señal" }), el("th", { scope: "col", texto: "Qué se observó" }), el("th", { scope: "col", texto: "Rareza" }), el("th", { scope: "col", texto: "Peso en el score" }))),
      el(
        "tbody",
        {},
        desviaciones.map((d) =>
          el(
            "tr",
            { id: `razon-${idTx}-${d.senal}` },
            el("td", { clase: "razon__senal", texto: f.senal(d.senal) }),
            el("td", { texto: d.descripcion || "—" }),
            el("td", {}, medidor(d.percentil_rareza, { maximo: 100 })),
            el("td", {}, medidor(d.contribucion_modelo, { signo: true })),
          ),
        ),
      ),
    );
  }

  function pintarRazones() {
    const contenedor = vaciar($("razones"));
    const transacciones = [...(caso.transacciones || [])].sort((a, b) => String(a.fecha_hora).localeCompare(String(b.fecha_hora)));
    if (!transacciones.length) {
      contenedor.append(el("p", { clase: "aviso-suave", texto: "El caso no trae transacciones con razones guardadas." }));
      return;
    }
    // Se abren las de mayor score (hasta 3): son las que sostienen la recomendación.
    const abiertas = new Set([...transacciones].sort((a, b) => b.score - a.score).slice(0, 3).map((t) => t.id_transaccion));
    for (const tx of transacciones) {
      const desviaciones = [...(tx.desviaciones || [])].sort((a, b) => (b.contribucion_modelo ?? 0) - (a.contribucion_modelo ?? 0));
      const relevantes = desviaciones.filter((d) => d.relevante);
      const otras = desviaciones.filter((d) => !d.relevante);
      contenedor.append(
        el(
          "details",
          { clase: "razon-grupo", id: `razones-${tx.id_transaccion}`, open: abiertas.has(tx.id_transaccion) },
          el(
            "summary",
            {},
            el(
              "span",
              { clase: "razon-grupo__titulo" },
              el("span", { texto: f.fechaHora(tx.fecha_hora) }),
              el("strong", { texto: f.moneda(tx.monto) }),
              el("span", { texto: [f.categoria(tx.categoria), tx.comercio].filter(Boolean).join(" · ") }),
              tx.viaje_imposible ? el("span", { clase: "chip-nivel nivel-acceso", texto: "Viaje imposible" }) : null,
            ),
            el("span", { clase: "mov__score", texto: `score ${f.puntaje(tx.score)}` }),
          ),
          el(
            "div",
            { clase: "razon-grupo__cuerpo" },
            relevantes.length ? tablaRazones(tx.id_transaccion, relevantes) : el("p", { clase: "aviso-suave", texto: "Ninguna señal superó el criterio de relevancia en esta transacción." }),
            otras.length
              ? el("details", { clase: "no-relevantes" }, el("summary", { texto: `${otras.length} señal${otras.length === 1 ? "" : "es"} no relevante${otras.length === 1 ? "" : "s"}` }), tablaRazones(tx.id_transaccion, otras))
              : null,
          ),
        ),
      );
    }
  }

  // ----- Perfil --------------------------------------------------------------------------
  function distribucion(titulo, items, etiqueta) {
    if (!items?.length) return null;
    return el(
      "div",
      { clase: "dato distribucion" },
      el("span", { clase: "dato__etiqueta", texto: titulo }),
      items.map((item) =>
        el(
          "div",
          { clase: "distribucion__fila" },
          el("span", { texto: etiqueta(item) }),
          el("span", { clase: "medidor__pista", "aria-hidden": "true" }, el("span", { clase: "medidor__relleno", estilo: { "--valor": `${Math.min(100, item.porcentaje || 0)}%` } })),
          el("span", { texto: f.porcentaje(item.porcentaje) }),
        ),
      ),
    );
  }

  function pintarPerfil() {
    const contenedor = vaciar($("perfil"));
    const p = caso.perfil_previo || {};
    if (p.sin_historial) {
      contenedor.append(el("p", { clase: "aviso-suave", texto: `Sin historial suficiente: antes del caso la tarjeta solo tenía ${f.numero(p.n_transacciones_previas || 0)} transacción(es). El perfil no es confiable y el sistema lo trata como señal de riesgo.` }));
    }
    const dato = (etiqueta, valor, nota) => el("div", { clase: "dato" }, el("span", { clase: "dato__etiqueta", texto: etiqueta }), el("span", { clase: "dato__valor", texto: valor }), nota ? el("span", { clase: "dato__nota", texto: nota }) : null);
    contenedor.append(
      el(
        "div",
        { clase: "perfil" },
        dato("Transacciones previas", f.numero(p.n_transacciones_previas)),
        dato("Monto promedio", f.moneda(p.monto_promedio), p.monto_desviacion != null ? `desviación ${f.moneda(p.monto_desviacion)}` : null),
        dato("Ritmo habitual", p.transacciones_por_dia != null ? `${f.numero(p.transacciones_por_dia, 2)} / día` : "—"),
        distribucion("Horas habituales", p.horas_habituales, (h) => `${h.hora} h`),
        distribucion("Categorías habituales", p.categorias_habituales, (c) => f.categoria(c.categoria)),
        distribucion("Ubicaciones habituales", p.ubicaciones_habituales, (u) => u.ubicacion),
      ),
    );
  }

  // ----- Propuestas y decisiones -----------------------------------------------------------
  function objetivoDe(accion) {
    if (accion !== "confirmar_bloqueo") return "";
    return caso.nivel_recomendacion === "bloquear_acceso_cuenta" ? "el acceso a la cuenta" : `la tarjeta ${f.tarjetaCorta(caso.tarjeta_enmascarada)}`;
  }

  async function resolverPropuesta(propuesta, confirmar) {
    const accion = f.ACCIONES[propuesta.accion] || propuesta.accion;
    const id = propuesta.id ?? propuesta.propuesta_id;
    const resultado = await dialogo.abrir({
      titulo: confirmar ? `Confirmar: ${accion.toLowerCase()}` : "Rechazar la propuesta del agente",
      descripcion: confirmar
        ? `Se registrará «${accion}» para ${caso.id_caso}${objetivoDe(propuesta.accion) ? ` sobre ${objetivoDe(propuesta.accion)}` : ""}, con tu nombre. El caso pasará a «${f.ESTADOS[ESTADO_TRAS_ACCION[propuesta.accion]]?.etiqueta || "cerrado"}».`
        : `La propuesta «${accion}» quedará rechazada y el caso seguirá pendiente. No se ejecuta ninguna acción sobre la tarjeta.`,
      textoBoton: confirmar ? "Confirmar" : "Rechazar propuesta",
      claseNivel: claseNivel(),
      tono: confirmar ? "nivel" : "primario",
      enviar: (cuerpo) => (confirmar ? api.confirmarPropuesta(id, cuerpo) : api.rechazarPropuesta(id, cuerpo)),
    });
    if (resultado) {
      avisar(confirmar ? "Decisión registrada" : "Propuesta rechazada");
      await refrescar();
      alCambio?.();
    }
  }

  async function decidir(accion) {
    const etiqueta = f.ACCIONES[accion];
    const descripciones = {
      confirmar_bloqueo: `Se registrará el bloqueo de ${objetivoDe(accion)} para ${caso.id_caso}, con tu nombre.`,
      escalar: `El caso ${caso.id_caso} pasará a «Escalado» para revisión de otro nivel.`,
      descartar: `El caso ${caso.id_caso} se marcará como descartado (falsa alarma). Deja un comentario si es posible.`,
    };
    const resultado = await dialogo.abrir({
      titulo: etiqueta,
      descripcion: descripciones[accion],
      textoBoton: etiqueta,
      claseNivel: claseNivel(),
      tono: accion === "confirmar_bloqueo" ? "nivel" : "primario",
      enviar: (cuerpo) => api.registrarDecision(caso.id_caso, { accion, ...cuerpo }),
    });
    if (resultado) {
      avisar("Decisión registrada");
      await refrescar();
      alCambio?.();
    }
  }

  function agregarPropuesta(datos) {
    const id = datos.propuesta_id ?? datos.id;
    if (id == null || propuestas.some((p) => (p.id ?? p.propuesta_id) === id)) return;
    propuestas.push({ id, accion: datos.accion, argumento: datos.argumento, estado: "pendiente" });
    pintarPropuestas();
  }

  function pintarPropuestas() {
    const contenedor = vaciar($("propuestas"));
    // Cada regeneración puede dejar otra propuesta igual: se muestra la más reciente de cada
    // acción y se avisa cuántas más quedan detrás, en vez de apilar recuadros idénticos.
    const pendientes = propuestas.filter((p) => (p.estado || "pendiente") === "pendiente");
    const porAccion = new Map();
    for (const p of pendientes) porAccion.set(p.accion, [...(porAccion.get(p.accion) || []), p]);
    for (const grupo of porAccion.values()) {
      const propuesta = grupo.reduce((a, b) => (Number(b.id ?? b.propuesta_id) > Number(a.id ?? a.propuesta_id) ? b : a));
      const anteriores = grupo.length - 1;
      contenedor.append(
        el(
          "div",
          { clase: "propuesta", role: "group", "aria-label": "Propuesta del agente" },
          el("p", { clase: "propuesta__titulo" }, icono("propuesta"), `Propuesta del agente: ${(f.ACCIONES[propuesta.accion] || propuesta.accion || "").toLowerCase()}`),
          propuesta.argumento ? el("p", { clase: "propuesta__argumento", texto: `Porque ${propuesta.argumento.replace(/^porque\s+/i, "")}` }) : null,
          el("p", {
            clase: "propuesta__nota",
            texto: `El agente no ejecuta acciones: solo se registra si la confirmas.${anteriores ? ` Hay ${anteriores} propuesta${anteriores === 1 ? "" : "s"} anterior${anteriores === 1 ? "" : "es"} igual${anteriores === 1 ? "" : "es"} sin resolver.` : ""}`,
          }),
          el(
            "div",
            { clase: "propuesta__botones" },
            el("button", { type: "button", clase: "boton boton--nivel", texto: "Confirmar", onClick: () => resolverPropuesta(propuesta, true) }),
            el("button", { type: "button", clase: "boton boton--secundario", texto: "Rechazar", onClick: () => resolverPropuesta(propuesta, false) }),
          ),
        ),
      );
    }
  }

  function pintarDecisiones(decisiones) {
    const lista = vaciar($("decisiones"));
    const ordenadas = [...(decisiones || [])].sort((a, b) => String(b.creada_en).localeCompare(String(a.creada_en)));
    ordenadas.forEach((d, i) =>
      lista.append(
        el(
          "li",
          { clase: "decision" },
          el("span", { clase: "decision__accion", texto: `${f.ACCIONES[d.accion] || d.accion}${i === 0 ? " (vigente)" : ""}` }),
          el("span", { clase: "decision__meta", texto: `${d.analista}${d.creada_en ? ` · ${f.fechaHora(d.creada_en)}` : ""}${d.propuesta_id ? " · a propuesta del agente" : ""}` }),
          d.comentario ? el("span", { clase: "decision__comentario", texto: `«${d.comentario}»` }) : null,
        ),
      ),
    );
  }

  for (const boton of contenido.querySelectorAll(".decision-manual [data-accion]")) {
    boton.addEventListener("click", () => caso && decidir(boton.dataset.accion));
  }

  /** Vuelve a pedir el detalle (estado, propuestas, decisiones) sin reiniciar la explicación. */
  async function refrescar() {
    if (!caso) return;
    const versionActual = version;
    try {
      const datos = await api.caso(caso.id_caso);
      if (versionActual !== version) return;
      caso = { ...caso, ...datos.caso };
      propuestas = datos.propuestas || [];
      pintarCabecera();
      pintarPropuestas();
      pintarDecisiones(datos.decisiones);
      explicacion.actualizarGuardada(datos.explicacion);
    } catch {
      /* el refresco es oportunista: si falla, la vista sigue con lo que tenía */
    }
  }

  async function abrir(id) {
    version += 1;
    const versionActual = version;
    controlador?.abort();
    controlador = new AbortController();
    explicacion.detener();
    vacio.hidden = true;
    contenido.hidden = false;
    contenido.classList.add("detalle--cargando");
    contenido.setAttribute("aria-busy", "true");
    pintarBanda(banda, null);

    const [detalle, historial] = await Promise.allSettled([api.caso(id, controlador.signal), api.historial(id, controlador.signal)]);
    if (versionActual !== version) return; // el analista ya abrió otro caso
    contenido.classList.remove("detalle--cargando");
    contenido.removeAttribute("aria-busy");

    if (detalle.status === "rejected") {
      if (detalle.reason?.name === "AbortError") return;
      caso = null;
      conversacion.abrirCaso(null);
      contenido.hidden = true;
      vacio.hidden = false;
      const noExiste = detalle.reason?.estado === 404;
      pintarBanda($("banda-global"), {
        titulo: noExiste ? `El caso ${id} no existe.` : "No se pudo abrir el caso.",
        detalle: noExiste ? "Puede que la base se haya recargado. Elige otro caso de la bandeja." : detalle.reason?.message,
        referencia: detalle.reason?.referencia,
        acciones: noExiste ? [] : [{ texto: "Reintentar", primaria: true, al: () => abrir(id) }],
      });
      return;
    }
    pintarBanda($("banda-global"), null);

    const datos = detalle.value;
    caso = datos.caso;
    propuestas = datos.propuestas || [];
    pintarCabecera();
    pintarRazones();
    pintarPerfil();
    pintarPropuestas();
    pintarDecisiones(datos.decisiones);
    const historialOk = historial.status === "fulfilled" ? historial.value.transacciones || [] : null;
    pintarLinea(historialOk || [], historialOk ? null : historial.reason?.message || "error");

    explicacion.preparar(caso, datos.explicacion);
    if (historialOk) explicacion.usarHistorial(historialOk);
    conversacion.abrirCaso(caso);
    columna.scrollTop = 0;
    explicacion.iniciar({ regenerar: false });
  }

  return {
    abrir,
    agregarPropuesta,
    get idActual() {
      return caso?.id_caso || null;
    },
  };
}
