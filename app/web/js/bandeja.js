/**
 * Bandeja de casos: contadores por nivel, filtros y la lista navegable con teclado.
 *
 * Es un listbox accesible: el foco queda en la lista y ↑/↓ mueven la selección
 * (aria-activedescendant), así un lector de pantalla anuncia cada caso. Con el
 * teclado la apertura del caso espera un instante (la decide principal.js) para no
 * disparar una generación del agente por cada fila que se atraviesa.
 */

import { ErrorApi, api } from "./api.js";
import { desplazarHasta, el, icono, vaciar } from "./dom.js";
import * as f from "./formato.js";

const RETARDO_BUSQUEDA_MS = 300;

export function crearBandeja({ alSeleccionar, alError }) {
  const $ = (id) => document.getElementById(id);
  const lista = $("lista-casos");
  const contadores = $("contadores");
  const total = $("bandeja-total");
  const formulario = $("filtros");
  const campos = { q: $("filtro-q"), fuente: $("filtro-fuente"), estado: $("filtro-estado"), orden: $("filtro-orden") };

  const filtros = { fuente: "", nivel: "", estado: "", q: "", orden: "score" };
  let casos = [];
  let seleccionado = null;
  let controlador = null;
  let temporizador = null;

  const hayFiltros = () => Boolean(filtros.fuente || filtros.nivel || filtros.estado || filtros.q);

  function pintarContadores(datos) {
    const porNivel = datos?.por_nivel || {};
    const pendientes = datos?.por_estado?.pendiente;
    total.textContent = `${f.numero(datos?.total ?? casos.length)} casos${pendientes != null ? ` · ${f.numero(pendientes)} pendientes` : ""}`;
    const opciones = [
      { valor: "", etiqueta: "Todos", cifra: datos?.total ?? casos.length, clase: "" },
      ...Object.entries(f.NIVELES).map(([valor, n]) => ({ valor, etiqueta: n.etiqueta, cifra: porNivel[valor] || 0, clase: `nivel-${n.clase}` })),
    ];
    vaciar(contadores).append(
      ...opciones.map((o) =>
        el(
          "button",
          {
            type: "button",
            clase: `contador ${o.clase}`,
            "aria-pressed": String(filtros.nivel === o.valor),
            onClick: () => {
              filtros.nivel = filtros.nivel === o.valor ? "" : o.valor;
              cargar();
            },
          },
          el("span", { clase: "contador__cifra", texto: f.numero(o.cifra) }),
          el("span", { clase: "contador__etiqueta", texto: o.etiqueta }),
        ),
      ),
    );
  }

  function fila(caso) {
    const nivel = f.NIVELES[caso.nivel_recomendacion] || { corta: caso.nivel_recomendacion, clase: "cerrado" };
    const estado = f.ESTADOS[caso.estado] || { etiqueta: caso.estado, cerrado: false };
    const nodo = el(
      "li",
      {
        id: `fila-${caso.id_caso}`,
        role: "option",
        "aria-selected": String(caso.id_caso === seleccionado),
        clase: `fila nivel-${estado.cerrado ? "cerrado" : nivel.clase}${estado.cerrado ? " fila--cerrada" : ""}`,
        dataset: { id: caso.id_caso },
        onClick: () => seleccionar(caso.id_caso, { origen: "clic" }),
      },
      el("span", { clase: "chip-nivel", texto: nivel.corta }),
      el("span", { clase: "fila__id", texto: caso.id_caso }),
      el("span", { clase: "fila__score", title: "Score máximo del caso", texto: f.puntaje(caso.score_maximo) }),
      el(
        "span",
        { clase: "fila__meta" },
        el("span", { clase: "mono", texto: f.tarjetaCorta(caso.tarjeta_enmascarada) }),
        el("span", { texto: f.fecha(caso.inicio_ventana) }),
        el("span", { texto: f.senal(caso.senal_principal) }),
        el("span", { texto: `${f.numero(caso.n_transacciones)} tx` }),
      ),
      el(
        "span",
        { clase: "fila__pie" },
        el("span", { clase: `estado${estado.cerrado ? " estado--cerrado" : ""}`, texto: estado.etiqueta }),
        caso.tiene_explicacion ? el("span", { clase: "fila__explicada" }, icono("check"), "Explicación lista") : null,
      ),
    );
    return nodo;
  }

  function pintarLista() {
    vaciar(lista);
    if (!casos.length) {
      lista.removeAttribute("aria-activedescendant");
      lista.append(
        hayFiltros()
          ? el(
              "li",
              { clase: "lista-vacia" },
              el("strong", { texto: "Ningún caso coincide con los filtros." }),
              el("button", { type: "button", clase: "boton boton--secundario boton--chico", texto: "Quitar filtros", onClick: limpiarFiltros }),
            )
          : el(
              "li",
              { clase: "lista-vacia" },
              el("strong", { texto: "No hay casos cargados." }),
              "La base está vacía. Genera la semilla con ",
              el("code", { texto: "python scripts/generar_semilla.py" }),
              " y reinicia con ",
              el("code", { texto: "docker compose up" }),
              ": la app la carga sola al arrancar.",
            ),
      );
      return;
    }
    lista.append(...casos.map(fila));
    if (seleccionado && casos.some((c) => c.id_caso === seleccionado)) lista.setAttribute("aria-activedescendant", `fila-${seleccionado}`);
  }

  function pintarError(error) {
    vaciar(lista).append(
      el(
        "li",
        { clase: "lista-vacia" },
        el("strong", { texto: "No se pudo cargar la bandeja." }),
        error.message,
        el("div", { clase: "mensaje__accion" }, el("button", { type: "button", clase: "boton boton--secundario boton--chico", texto: "Reintentar", onClick: () => cargar() })),
      ),
    );
  }

  async function cargar() {
    controlador?.abort();
    controlador = new AbortController();
    lista.setAttribute("aria-busy", "true");
    try {
      const datos = await api.casos({ ...filtros, limite: 500 }, controlador.signal);
      casos = datos.casos || [];
      pintarContadores(datos.contadores);
      pintarLista();
    } catch (error) {
      if (error.name === "AbortError") return;
      pintarError(error);
      if (error instanceof ErrorApi) alError?.(error);
    } finally {
      lista.removeAttribute("aria-busy");
    }
  }

  function limpiarFiltros() {
    Object.assign(filtros, { fuente: "", nivel: "", estado: "", q: "" });
    campos.q.value = "";
    campos.fuente.value = "";
    campos.estado.value = "";
    cargar();
  }

  function marcar(id) {
    seleccionado = id;
    for (const nodo of lista.querySelectorAll(".fila")) nodo.setAttribute("aria-selected", String(nodo.dataset.id === id));
    const nodo = id ? document.getElementById(`fila-${id}`) : null;
    if (nodo) {
      lista.setAttribute("aria-activedescendant", nodo.id);
      desplazarHasta(nodo);
    }
  }

  function seleccionar(id, { origen = "clic" } = {}) {
    marcar(id);
    alSeleccionar?.(id, { origen });
  }

  function mover(delta) {
    if (!casos.length) return;
    const indice = casos.findIndex((c) => c.id_caso === seleccionado);
    const siguiente = indice < 0 ? (delta > 0 ? 0 : casos.length - 1) : Math.min(casos.length - 1, Math.max(0, indice + delta));
    seleccionar(casos[siguiente].id_caso, { origen: "teclado" });
  }

  lista.addEventListener("keydown", (evento) => {
    const teclas = { ArrowDown: 1, ArrowUp: -1, PageDown: 10, PageUp: -10 };
    if (evento.key in teclas) {
      evento.preventDefault();
      mover(teclas[evento.key]);
    } else if (evento.key === "Home" || evento.key === "End") {
      evento.preventDefault();
      if (casos.length) seleccionar(casos[evento.key === "Home" ? 0 : casos.length - 1].id_caso, { origen: "teclado" });
    } else if (evento.key === "Enter" && seleccionado) {
      evento.preventDefault();
      seleccionar(seleccionado, { origen: "clic" });
    }
  });

  formulario.addEventListener("submit", (evento) => evento.preventDefault());
  for (const nombre of ["fuente", "estado", "orden"]) {
    campos[nombre].addEventListener("change", () => {
      filtros[nombre] = campos[nombre].value;
      cargar();
    });
  }
  campos.q.addEventListener("input", () => {
    clearTimeout(temporizador);
    temporizador = setTimeout(() => {
      filtros.q = campos.q.value.trim();
      cargar();
    }, RETARDO_BUSQUEDA_MS);
  });

  return {
    cargar,
    marcar,
    enfocar: () => lista.focus(),
  };
}
