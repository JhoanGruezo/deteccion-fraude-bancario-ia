/**
 * Explicación del agente: los cuatro bloques del contrato, rellenados EN VIVO.
 *
 * Cómo se evita el "streaming falso": los bloques solo muestran lo que el modelo ya
 * escribió. Cada evento `token` se suma a un búfer; el búfer se lee con el parser
 * tolerante de json_parcial.js y se pinta lo que haya en cada campo. No hay
 * temporizadores que "escriban" letra por letra: si el modelo tarda, la pantalla
 * espera; si llega de golpe (caché), aparece de golpe y una etiqueta lo dice.
 *
 * Cuando llega la versión validada (`explicacion`, `cache` o `respaldo`), se pinta la
 * definitiva: las cifras se enlazan con la fila de evidencia de donde salen (la regla
 * de trazabilidad de decisiones.md) y las señales citadas se vuelven chips con su
 * rareza y su peso.
 *
 * Lo que llega en vivo es un BORRADOR (el estado lo dice): si el servidor lo rechaza
 * (`contrato_invalido`) o cae a la plantilla (`respaldo`), se borra de inmediato. Antes
 * quedaba pintado hasta que llegaba el JSON siguiente: en la demo del 429 se vio ~10 s
 * una explicación inventada por el modelo de respaldo (validacion/app-analista.md).
 * Solo se pinta texto que sea parte del JSON de la explicación: el texto de una llamada
 * que pidió herramientas (un preámbulo) se descarta.
 */

import { abrirStream, api } from "./api.js";
import { destacar, el, icono, pintarBanda, vaciar } from "./dom.js";
import * as f from "./formato.js";
import { parsearJsonParcial } from "./json_parcial.js";

const CAMPOS_TEXTO = ["que_paso", "por_que_es_riesgo", "lo_que_no_se_sabe"];
// A qué bloque pertenece cada campo del contrato (para marcar el que está llegando).
const BLOQUE_DE_CAMPO = {
  que_paso: "que_paso",
  por_que_es_riesgo: "por_que_es_riesgo",
  senales_citadas: "por_que_es_riesgo",
  recomendacion: "recomendacion",
  nivel_riesgo_en_palabras: "recomendacion",
  lo_que_no_se_sabe: "lo_que_no_se_sabe",
};
// Números en formato español; se ignoran los que forman parte de fechas u horas
// ("2020-07-31 12:03"), que no son cifras citadas de la evidencia.
const CIFRA = /(?<![\d\-/.,:])(?:\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:,\d+)?)(?![\d\-/]|[.,:]\d)/g;

/** El contenido puede llegar anidado de varias formas según el evento; se busca el contrato. */
export function extraerContenido(datos) {
  const candidatos = [datos?.contenido, datos?.explicacion?.contenido, datos?.explicacion, datos];
  return candidatos.find((c) => c && typeof c === "object" && ("que_paso" in c || "recomendacion" in c)) || null;
}

/** Índice de evidencia: cada número del caso apunta al elemento donde se ve. */
function construirEvidencia(caso, historial) {
  const evidencia = [];
  const agregar = (valor, destino) => {
    if (typeof valor === "number" && Number.isFinite(valor)) evidencia.push({ valor, destino });
  };
  for (const tx of caso.transacciones || []) {
    agregar(tx.monto, `tx-${tx.id_transaccion}`);
    for (const d of tx.desviaciones || []) {
      const destino = `razon-${tx.id_transaccion}-${d.senal}`;
      agregar(d.valor_observado, destino);
      agregar(d.valor_referencia, destino);
      agregar(d.percentil_rareza, destino);
    }
    agregar(tx.score, `razones-${tx.id_transaccion}`);
  }
  const p = caso.perfil_previo || {};
  for (const clave of ["monto_promedio", "monto_desviacion", "transacciones_por_dia", "n_transacciones_previas"]) agregar(p[clave], "perfil-seccion");
  for (const lista of [p.horas_habituales, p.categorias_habituales, p.ubicaciones_habituales]) {
    for (const item of lista || []) {
      agregar(item.porcentaje, "perfil-seccion");
      agregar(item.hora, "perfil-seccion");
    }
  }
  agregar(caso.score_maximo, "caso-cabecera");
  agregar(caso.transacciones_sobre_umbral_bloqueo, "caso-cabecera");
  agregar(caso.umbral_bloqueo, "caso-cabecera");
  agregar(caso.umbral_verificacion, "caso-cabecera");
  for (const tx of historial || []) agregar(Number(tx.monto), `tx-${tx.id_transaccion}`);
  return evidencia;
}

/** Busca el número citado en la evidencia con la tolerancia de los decimales que escribió. */
function buscarEvidencia(evidencia, textoCifra) {
  const valor = f.leerNumeroEspanol(textoCifra);
  if (valor === null) return null;
  const decimales = (textoCifra.split(",")[1] || "").length;
  if (!decimales && valor < 10) return null; // "5 compras", "48 h": demasiado ambiguos para enlazar
  // Un entero solo se enlaza si coincide exacto ("10 transacciones" ↔ 10); un decimal
  // admite el redondeo de lo que escribió ("96,3" ↔ 96,31).
  const tolerancia = decimales ? 0.5 * 10 ** -decimales + 1e-9 : 1e-9;
  return evidencia.find((e) => Math.abs(e.valor - valor) <= tolerancia) || null;
}

/** Texto con las cifras rastreables convertidas en enlaces a su evidencia. */
function textoConCifras(texto, evidencia) {
  const fragmento = document.createDocumentFragment();
  let ultimo = 0;
  for (const coincidencia of texto.matchAll(CIFRA)) {
    const encontrada = buscarEvidencia(evidencia, coincidencia[0]);
    if (!encontrada) continue;
    fragmento.append(texto.slice(ultimo, coincidencia.index));
    fragmento.append(
      el("a", {
        clase: "cifra",
        href: `#${encontrada.destino}`,
        title: "Ver de dónde sale esta cifra",
        texto: coincidencia[0],
        onClick: (evento) => {
          evento.preventDefault();
          destacar(document.getElementById(encontrada.destino));
        },
      }),
    );
    ultimo = coincidencia.index + coincidencia[0].length;
  }
  fragmento.append(texto.slice(ultimo));
  return fragmento;
}

/** Para cada señal del caso, la desviación más fuerte y en cuántas transacciones aparece. */
function indexarSenales(caso) {
  const indice = new Map();
  for (const tx of caso.transacciones || []) {
    for (const d of tx.desviaciones || []) {
      if (!d.relevante) continue;
      const actual = indice.get(d.senal) || { mejor: null, tx: null, apariciones: 0 };
      actual.apariciones += 1;
      if (!actual.mejor || (d.contribucion_modelo ?? 0) > (actual.mejor.contribucion_modelo ?? 0)) {
        actual.mejor = d;
        actual.tx = tx;
      }
      indice.set(d.senal, actual);
    }
  }
  return indice;
}

export function crearExplicacion({ trazas, alPropuesta, alTerminar }) {
  const $ = (id) => document.getElementById(id);
  const contenedorBloques = $("explicacion-bloques");
  const bloques = Object.fromEntries([...contenedorBloques.querySelectorAll(".bloque")].map((b) => [b.dataset.campo, b]));
  const textoDe = (campo) => bloques[campo].querySelector(".bloque__texto");
  const nodoEstado = $("explicacion-estado");
  const nodoOrigen = $("explicacion-origen");
  const nodoSenales = $("senales-citadas");
  const nodoObjetivo = $("recomendacion-objetivo");
  const nodoNivel = $("recomendacion-nivel");
  const banda = $("banda-caso");
  const botonRegenerar = $("boton-regenerar");

  let caso = null;
  let guardada = null;
  let evidencia = [];
  let senales = new Map();
  let stream = null;
  let tarea = null;
  let bufer = "";
  let t0 = 0;
  let primerToken = false;
  let ultimoModo = { regenerar: false };
  let recibioFinal = false;
  let pintadoPendiente = null;

  function estado(texto, activo = true) {
    nodoEstado.textContent = texto || "";
    nodoEstado.classList.toggle("estado-vivo--activo", Boolean(texto) && activo);
  }

  function origen(tipo, texto) {
    if (!tipo) {
      nodoOrigen.hidden = true;
      return;
    }
    vaciar(nodoOrigen).append(icono({ cache: "cache", respaldo: "documento", vivo: "modelo", guardada: "cache" }[tipo] || "info"), texto);
    nodoOrigen.className = `origen origen--${tipo}`;
    nodoOrigen.hidden = false;
  }

  function limpiarBloques(esperando) {
    for (const campo of Object.keys(bloques)) {
      textoDe(campo).textContent = "";
      bloques[campo].classList.toggle("bloque--esperando", esperando);
      bloques[campo].classList.remove("bloque--llegando");
    }
    vaciar(nodoSenales);
    nodoObjetivo.textContent = "";
    nodoNivel.textContent = "";
  }

  function chipSenal(codigo) {
    const datos = senales.get(codigo);
    const idTip = `tip-${codigo}`;
    const boton = el(
      "button",
      { type: "button", clase: "senal__boton", "aria-describedby": idTip, onClick: () => datos && destacar(document.getElementById(`razon-${datos.tx.id_transaccion}-${codigo}`)) },
      f.senal(codigo),
      datos?.mejor?.percentil_rareza != null ? el("span", { clase: "senal__percentil", texto: `P${f.numero(datos.mejor.percentil_rareza, 0)}` }) : null,
    );
    const tip = el(
      "span",
      { clase: "tooltip", role: "tooltip", id: idTip },
      datos ? datos.mejor.descripcion : "Esta señal no aparece entre las razones relevantes del caso.",
      datos
        ? el(
            "dl",
            {},
            el("dt", { texto: "Rareza" }), el("dd", { texto: `más inusual que el ${f.porcentaje(datos.mejor.percentil_rareza)} de las normales` }),
            el("dt", { texto: "Peso en el score" }), el("dd", { texto: f.numero(datos.mejor.contribucion_modelo, 2) }),
            el("dt", { texto: "Aparece en" }), el("dd", { texto: `${datos.apariciones} de ${(caso.transacciones || []).length} transacciones` }),
          )
        : null,
    );
    // Si el globo no cabe a la derecha de la ventana, se abre hacia la izquierda.
    const ubicar = () => {
      tip.classList.remove("tooltip--izquierda");
      if (tip.getBoundingClientRect().right > document.documentElement.clientWidth - 8) tip.classList.add("tooltip--izquierda");
    };
    return el("span", { clase: "senal", onMouseenter: () => requestAnimationFrame(ubicar), onFocusin: () => requestAnimationFrame(ubicar) }, boton, tip);
  }

  /** Pinta el contenido (parcial o final). `final` activa cifras enlazadas y chips completos. */
  function pintar(valor, { final = false, claveEnCurso = null } = {}) {
    if (!valor || typeof valor !== "object") return;
    const poner = (nodo, texto) => {
      const limpio = typeof texto === "string" ? texto : "";
      if (final) vaciar(nodo).append(textoConCifras(limpio, evidencia));
      else nodo.textContent = limpio;
    };
    for (const campo of CAMPOS_TEXTO) poner(textoDe(campo), valor[campo]);
    const rec = valor.recomendacion && typeof valor.recomendacion === "object" ? valor.recomendacion : {};
    poner(textoDe("recomendacion"), rec.argumento);
    nodoObjetivo.textContent = rec.objetivo ? `${f.NIVELES[rec.accion]?.etiqueta || "Objetivo"}: ${rec.objetivo}` : "";
    nodoNivel.textContent = typeof valor.nivel_riesgo_en_palabras === "string" && valor.nivel_riesgo_en_palabras ? `Nivel de riesgo: ${valor.nivel_riesgo_en_palabras}` : "";

    // Mientras llega, una señal a medio escribir ("mon") no se muestra: solo las que existen en el caso.
    const citadas = Array.isArray(valor.senales_citadas) ? valor.senales_citadas.filter((s) => typeof s === "string") : [];
    vaciar(nodoSenales).append(...citadas.filter((s) => final || senales.has(s)).map(chipSenal));

    const bloqueActivo = final ? null : BLOQUE_DE_CAMPO[claveEnCurso];
    for (const [campo, bloque] of Object.entries(bloques)) bloque.classList.toggle("bloque--llegando", campo === bloqueActivo);
  }

  /** Borra el borrador en vivo: lo que se mostró no pasó (o no pasará) la validación. */
  function descartarBorrador() {
    bufer = "";
    if (pintadoPendiente) cancelAnimationFrame(pintadoPendiente);
    pintadoPendiente = null;
    if (!recibioFinal) limpiarBloques(true);
  }

  function pintarBufer() {
    pintadoPendiente = null;
    if (recibioFinal) return; // la versión validada manda: lo parcial ya no se repinta encima
    const leido = parsearJsonParcial(bufer);
    if (leido) pintar(leido.valor, { claveEnCurso: leido.claveEnCurso });
  }

  function pintarFinal(contenido) {
    if (!contenido) return;
    recibioFinal = true;
    if (pintadoPendiente) cancelAnimationFrame(pintadoPendiente);
    pintadoPendiente = null;
    for (const bloque of Object.values(bloques)) bloque.classList.remove("bloque--esperando");
    pintar(contenido, { final: true });
  }

  function mostrarGuardada() {
    detener();
    pintarBanda(banda, null);
    if (!guardada) return;
    limpiarBloques(false);
    pintarFinal(extraerContenido(guardada));
    origen(guardada.es_respaldo ? "respaldo" : "guardada", `Explicación guardada${guardada.creada_en ? ` · ${f.fechaHora(guardada.creada_en)}` : ""}${guardada.es_respaldo ? " · plantilla" : ""}`);
    estado("Se muestra la última explicación guardada; no se llamó al modelo.", false);
  }

  function accionesDeFallo() {
    const acciones = [{ texto: "Reintentar", primaria: true, al: () => iniciar(ultimoModo) }];
    if (guardada) acciones.push({ texto: "Ver explicación guardada", al: mostrarGuardada });
    return acciones;
  }

  function manejar(tipo, datos) {
    tarea?.evento(tipo, datos);
    switch (tipo) {
      case "estado":
        estado(datos.texto);
        break;
      case "modelo_llamado":
        bufer = ""; // una llamada nueva escribe un JSON nuevo (p. ej., tras un contrato inválido)
        estado(`Llamando a ${f.proveedor(datos.proveedor)}${datos.iteracion ? ` · iteración ${datos.iteracion}` : ""}…`);
        origen("vivo", `En vivo · ${f.proveedor(datos.proveedor)}`);
        break;
      case "herramienta":
        // El texto de una llamada que pide herramientas no es la explicación (es un preámbulo).
        descartarBorrador();
        estado(`El agente consulta ${datos.nombre}…`);
        break;
      case "token":
        if (!primerToken) {
          primerToken = true;
          tarea?.marcarPrimerToken(performance.now() - t0);
          estado("Recibiendo un borrador; se valida contra la evidencia al terminar…");
        }
        bufer += datos.texto || "";
        // Agrupa los repintados al ritmo de la pantalla: no altera qué se muestra, solo cuándo se dibuja.
        if (!pintadoPendiente) pintadoPendiente = requestAnimationFrame(pintarBufer);
        break;
      case "reintento":
        descartarBorrador(); // lo que alcanzó a llegar de la llamada fallida no sirve
        // La cascada ya trae el texto legible ("Gemini respondió 429 · reintento 2/3 en 2 s").
        if (datos.texto) {
          estado(datos.texto);
          break;
        }
        estado(`${f.proveedor(datos.proveedor)} respondió ${datos.motivo === "cuota" ? "429" : datos.motivo || "con error"} · reintento ${datos.intento ?? ""}${datos.espera_s != null ? ` en ${f.numero(datos.espera_s, 0)} s` : ""}`);
        break;
      case "conmutacion":
        descartarBorrador();
        estado(datos.texto || `Conmutando de ${f.proveedor(datos.de)} a ${f.proveedor(datos.a)}…`);
        break;
      case "contrato_invalido":
        // Estado honesto: lo pintado no pasó la validación y desaparece de la pantalla.
        descartarBorrador();
        estado(datos.reintenta === false
          ? "La respuesta no pasó la validación contra la evidencia; se usará la explicación armada por reglas…"
          : "La respuesta no pasó la validación contra la evidencia; reintentando…");
        break;
      case "limite":
        estado(`Se alcanzó el límite de ${datos.cual || "la tarea"}.`);
        break;
      case "cache": {
        // El servicio manda la explicación vigente anidada en `explicacion`; se acepta también plana.
        const guardadaEnCache = datos.explicacion && typeof datos.explicacion === "object" ? datos.explicacion : datos;
        pintarFinal(extraerContenido(datos));
        origen("cache", `Desde caché${guardadaEnCache.creada_en ? ` · ${f.fechaHora(guardadaEnCache.creada_en)}` : ""}${guardadaEnCache.es_respaldo ? " · plantilla" : ""}`);
        break;
      }
      case "explicacion":
        pintarFinal(extraerContenido(datos));
        break;
      case "respaldo":
        descartarBorrador();
        pintarFinal(extraerContenido(datos));
        origen("respaldo", "Plantilla de respaldo · armada por reglas con las razones guardadas");
        break;
      case "propuesta":
        alPropuesta?.(datos);
        break;
      case "error":
        pintarBanda(banda, { titulo: datos.mensaje || "La explicación no se pudo generar.", referencia: datos.referencia, acciones: accionesDeFallo() });
        break;
      case "fin":
        terminar(datos);
        break;
      default:
        break;
    }
  }

  function terminar(datos) {
    if (pintadoPendiente) {
      cancelAnimationFrame(pintadoPendiente);
      pintarBufer();
    }
    tarea?.terminar(datos);
    stream = null;
    botonRegenerar.disabled = false;
    for (const bloque of Object.values(bloques)) bloque.classList.remove("bloque--llegando", "bloque--esperando");
    if (datos.desde_cache || nodoOrigen.classList.contains("origen--cache")) estado("Servida desde caché, sin llamar al modelo.", false);
    else if (recibioFinal) {
      const tiempo = f.duracion(datos.latencia_ms ?? Math.round(performance.now() - t0));
      const porPlantilla = datos.motivo_fin === "respaldo" || nodoOrigen.classList.contains("origen--respaldo");
      estado(porPlantilla ? `Los proveedores de IA no respondieron: explicación armada por reglas en ${tiempo}.` : `Lista en ${tiempo}.`, false);
    }
    else {
      estado(`La tarea terminó sin una explicación válida (${f.motivoFin(datos.motivo_fin).toLowerCase()}).`, false);
      if (banda.hidden) pintarBanda(banda, { titulo: "No se obtuvo una explicación válida en esta tarea.", detalle: "Puedes reintentar o revisar la traza para ver qué límite o falla la detuvo.", acciones: accionesDeFallo() });
    }
    alTerminar?.(datos);
  }

  function interrumpido() {
    tarea?.interrumpir();
    stream = null;
    botonRegenerar.disabled = false;
    estado("", false);
    for (const bloque of Object.values(bloques)) bloque.classList.remove("bloque--esperando", "bloque--llegando");
    pintarBanda(banda, {
      titulo: "Conexión interrumpida antes de terminar.",
      detalle: "Si se cortó la red y el servidor sigue arriba, la tarea termina y se guarda igual: al reintentar saldrá de la caché.",
      acciones: accionesDeFallo(),
    });
  }

  function detener() {
    stream?.cerrar();
    stream = null;
    if (pintadoPendiente) cancelAnimationFrame(pintadoPendiente);
    pintadoPendiente = null;
  }

  /** Abre el stream de la explicación (caché si existe; si no, generación en vivo). */
  function iniciar({ regenerar = false } = {}) {
    if (!caso) return;
    detener();
    ultimoModo = { regenerar };
    pintarBanda(banda, null);
    limpiarBloques(true);
    origen(null);
    bufer = "";
    primerToken = false;
    recibioFinal = false;
    botonRegenerar.disabled = true;
    estado(regenerar ? "Pidiendo una explicación nueva…" : "Conectando…");
    tarea = trazas.nueva("explicacion", caso.id_caso);
    t0 = performance.now();
    stream = abrirStream(api.urlExplicacion(caso.id_caso, regenerar), manejar, interrumpido);
  }

  botonRegenerar.addEventListener("click", () => iniciar({ regenerar: true }));

  return {
    /** Prepara el caso nuevo (evidencia, señales) sin abrir todavía el stream. */
    preparar(nuevoCaso, explicacionGuardada) {
      detener();
      caso = nuevoCaso;
      guardada = explicacionGuardada || null;
      evidencia = construirEvidencia(caso, []);
      senales = indexarSenales(caso);
    },
    usarHistorial(historial) {
      if (caso) evidencia = construirEvidencia(caso, historial);
    },
    actualizarGuardada(explicacion) {
      guardada = explicacion || guardada;
    },
    iniciar,
    detener,
    get generando() {
      return Boolean(stream?.abierto);
    },
  };
}
