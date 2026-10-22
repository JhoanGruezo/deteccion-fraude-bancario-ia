"""Corre la suite de casos dorados contra la app y marca cada caso como éxito o fallo.

Por qué existe: "Medición y Trazas" vale 25 de 100 en la rúbrica del Momento 2 y pide
una suite de casos verificados a mano, con al menos uno de rechazo, que corra con un
comando. La suite habla con la app real por HTTP, consumiendo el mismo SSE que el
navegador (eval/cliente_sse.py), para que lo medido sea lo que vive el analista.

Qué es un éxito (diseno/evaluacion-entrega.md, idéntico para la suite y el lote):
- Explicación: la tarea termina con `motivo_fin = completada`, la explicación la
  escribió el agente (o es la guardada del agente, si se sirvió de caché) y el
  contrato es válido (forma, acción igual a la de la regla, señales citadas solo entre
  las relevantes) y se cumplen los hechos esperados del caso dorado (señales que
  deben citarse, hechos y cifras). Una explicación de plantilla NO es un éxito del
  agente: el lote la cuenta como recuperación.
- Rechazo: `motivo_fin = rechazo` y el agente no propuso ninguna decisión (ni evento
  `propuesta` ni llamada a `registrar_decision`).
- Pregunta (solo en el lote): termina `completada`, no es rechazo, la respuesta no
  está vacía, se apoyó en al menos una herramienta y cumple sus hechos si los tiene.

Las comprobaciones son reglas simples y explicables (presencia de cifras y señales en
el texto), no otro LLM: la evaluación tiene que poder sustentarse. Las cifras
rastreables (que cada número del texto exista en la evidencia) ya las exige
app/agente/contrato.py en el servidor: el evento `explicacion` solo sale si pasó esa
comprobación, y aquí se exige que la explicación venga de ese evento.

El lector de números está copiado (no importado) de app/agente/contrato.py a
propósito: la evaluación no debe depender del código que evalúa.

Uso (con la app arriba):
    python eval/correr_suite.py                 # los 8 casos
    python eval/correr_suite.py --solo D2,D7    # un subconjunto (para depurar)
Escribe eval/resultados/suite_<fecha>.json (con la traza de cada tarea) y .md.
"""

import argparse
import json
import os
import re
import statistics
import sys
import unicodedata
from datetime import datetime

CARPETA_EVAL = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, CARPETA_EVAL)

from cliente_sse import (URL_BASE_POR_DEFECTO, ResultadoStream, abrir_stream, obtener_json,  # noqa: E402
                         url_explicacion, url_pregunta)

RUTA_DORADOS = os.path.join(CARPETA_EVAL, "casos_dorados.json")
CARPETA_RESULTADOS = os.path.join(CARPETA_EVAL, "resultados")

CLAVES_TEXTO = ("que_paso", "por_que_es_riesgo", "nivel_riesgo_en_palabras", "lo_que_no_se_sabe")
CLAVES_RECOMENDACION = ("accion", "objetivo", "argumento")
NOMBRE_HERRAMIENTA_ESCRITURA = "registrar_decision"


# --- Lectura de números en formato español (copia de app/agente/contrato.py) --------------
_PATRON_CIFRA = re.compile(r"\d[\d.,]*\d|\d")
_ESPANOL_CON_MILES = re.compile(r"^\d{1,3}(\.\d{3})+(,\d+)?$")
_ESPANOL_SIMPLE = re.compile(r"^\d+(,\d+)?$")
_INGLES = re.compile(r"^(\d{1,3}(,\d{3})+|\d+)(\.\d+)?$")


def interpretar_cifra(token: str) -> tuple[float, int] | None:
    """"1.234,56" → (1234.56, 2); "0,97" → (0.97, 2). Acepta también formato inglés."""
    if _ESPANOL_CON_MILES.match(token) or _ESPANOL_SIMPLE.match(token):
        entero, _, decimales = token.replace(".", "").partition(",")
        return float(f"{entero}.{decimales or 0}"), len(decimales)
    if _INGLES.match(token):
        entero, _, decimales = token.replace(",", "").partition(".")
        return float(f"{entero}.{decimales or 0}"), len(decimales)
    return None


def cifras_del_texto(texto: str) -> list[tuple[float, int]]:
    cifras = []
    for token in _PATRON_CIFRA.findall(texto or ""):
        token = token.rstrip(".,")
        valor = interpretar_cifra(token)
        if valor is not None:
            cifras.append(valor)
    return cifras


def aparece_cifra(esperada: str, cifras: list[tuple[float, int]]) -> bool:
    """La cifra esperada aparece si algún número del texto la iguala con la precisión con
    que fue escrito: "291,8" o "292" cuentan como 291,80 (redondeo), "290" no."""
    objetivo = interpretar_cifra(esperada)
    if objetivo is None:
        return False
    for valor, decimales in cifras:
        if abs(valor - objetivo[0]) <= 0.5 * 10 ** (-decimales) + 1e-9:
            return True
    return False


def normalizar(texto: str) -> str:
    """Minúsculas y sin tildes, para que "Cúcuta" y "Cucuta" cuenten igual."""
    sin_tildes = unicodedata.normalize("NFD", texto or "")
    return "".join(c for c in sin_tildes if unicodedata.category(c) != "Mn").lower()


def contiene_alguno(texto: str, alternativas: list[str]) -> bool:
    """Una alternativa numérica ("5", "3109") se busca como número completo, no como
    subcadena (si no, "5" aparecería en "2025"); una de texto, como subcadena."""
    cifras = cifras_del_texto(texto)
    texto_normal = normalizar(texto)
    for alternativa in alternativas:
        if re.fullmatch(r"[\d.,]+", alternativa):
            objetivo = interpretar_cifra(alternativa)
            if objetivo and any(abs(v - objetivo[0]) < 1e-9 and d == objetivo[1] for v, d in cifras):
                return True
        elif normalizar(alternativa) in texto_normal:
            return True
    return False


# --- Lectura de lo que pasó en el stream ---------------------------------------------------
def texto_de_explicacion(contenido: dict) -> str:
    recomendacion = contenido.get("recomendacion") or {}
    partes = [str(contenido.get(clave, "")) for clave in CLAVES_TEXTO]
    partes += [str(recomendacion.get(clave, "")) for clave in CLAVES_RECOMENDACION]
    return "\n".join(partes)


def origen_de_explicacion(resultado: ResultadoStream) -> tuple[str, dict | None]:
    """De dónde salió lo que vio el analista: agente, caché (del agente o de plantilla),
    plantilla o nada."""
    evento = resultado.primero("explicacion")
    if evento and isinstance(evento.get("contenido"), dict):
        return "agente", evento["contenido"]
    cache = resultado.primero("cache")
    if cache and isinstance(cache.get("explicacion"), dict):
        guardada = cache["explicacion"]
        return ("cache_plantilla" if guardada.get("es_respaldo") else "cache"), guardada.get("contenido")
    respaldo = resultado.primero("respaldo")
    if respaldo and isinstance(respaldo.get("contenido"), dict):
        return "plantilla", respaldo["contenido"]
    return "ninguno", None


def hubo_escritura(resultado: ResultadoStream) -> bool:
    if resultado.todos("propuesta"):
        return True
    return any(h.get("nombre") == NOMBRE_HERRAMIENTA_ESCRITURA for h in resultado.todos("herramienta"))


def falla_aplicada(resultado: ResultadoStream) -> str | None:
    """La falla que la app de verdad aplicó a la tarea (viene en el evento `inicio`)."""
    return (resultado.primero("inicio") or {}).get("falla_forzada") or None


# --- Comprobaciones -----------------------------------------------------------------------
def revisar_contrato(contenido: dict, caso: dict) -> list[str]:
    """Forma, acción y citas, contra el caso tal como lo devuelve la API."""
    errores = []
    for clave in CLAVES_TEXTO:
        if not str(contenido.get(clave, "")).strip():
            errores.append(f"falta o está vacío «{clave}»")
    recomendacion = contenido.get("recomendacion")
    if not isinstance(recomendacion, dict):
        errores.append("falta «recomendacion»")
        recomendacion = {}
    for clave in CLAVES_RECOMENDACION:
        if not str(recomendacion.get(clave, "")).strip():
            errores.append(f"falta o está vacío «recomendacion.{clave}»")
    if recomendacion.get("accion") != caso["nivel_recomendacion"]:
        errores.append(f"acción «{recomendacion.get('accion')}» distinta de la regla «{caso['nivel_recomendacion']}»")
    citadas = contenido.get("senales_citadas") or []
    # Mismo conjunto citable que app/agente/contrato.py: desviaciones relevantes, la
    # señal principal y "viaje_imposible" si el detector determinista lo marcó.
    relevantes = {d["senal"] for t in caso["transacciones"] for d in t["desviaciones"] if d.get("relevante")}
    if caso.get("senal_principal"):
        relevantes.add(caso["senal_principal"])
    if any(t.get("viaje_imposible") for t in caso["transacciones"]):
        relevantes.add("viaje_imposible")
    if not citadas:
        errores.append("no cita ninguna señal")
    ajenas = [s for s in citadas if s not in relevantes]
    if ajenas:
        errores.append(f"cita señales no relevantes: {', '.join(ajenas)}")
    return errores


def revisar_esperado(texto: str, citadas: list[str], esperado: dict) -> tuple[list[dict], list[str]]:
    """Hechos esperados del caso dorado. Devuelve el detalle por hecho y los incumplidos."""
    detalle, incumplidos = [], []
    for senal in esperado.get("senales_que_deben_citarse", []):
        cumple = senal in citadas
        detalle.append({"hecho": f"cita la señal «{senal}»", "cumple": cumple})
        if not cumple:
            incumplidos.append(f"no cita la señal «{senal}»")
    for item in esperado.get("hechos", []):
        cumple = contiene_alguno(texto, item["debe_contener_alguno"])
        detalle.append({"hecho": item["enunciado"], "cumple": cumple})
        if not cumple:
            incumplidos.append(f"no {item['enunciado']}")
    cifras = cifras_del_texto(texto)
    for grupo in esperado.get("cifras_que_deben_aparecer", []):
        opciones = grupo if isinstance(grupo, list) else [grupo]
        cumple = any(aparece_cifra(c, cifras) for c in opciones)
        detalle.append({"hecho": f"menciona la cifra {' o '.join(opciones)}", "cumple": cumple})
        if not cumple:
            incumplidos.append(f"no menciona {' ni '.join(opciones)}")
    return detalle, incumplidos


def evaluar_explicacion(resultado: ResultadoStream, caso: dict, esperado: dict | None) -> dict:
    fin = resultado.fin
    origen, contenido = origen_de_explicacion(resultado)
    motivos = []
    if resultado.error_cliente:
        motivos.append(f"error del cliente: {resultado.error_cliente}")
    if fin.get("motivo_fin") != "completada":
        motivos.append(f"motivo_fin = {fin.get('motivo_fin')}")
    if origen not in ("agente", "cache"):
        motivos.append(f"la explicación salió de: {origen}")
    detalle_hechos = []
    explicacion_valida = False
    if contenido:
        errores_contrato = revisar_contrato(contenido, caso)
        explicacion_valida = not errores_contrato
        motivos += [f"contrato: {e}" for e in errores_contrato]
        if esperado:
            detalle_hechos, incumplidos = revisar_esperado(texto_de_explicacion(contenido),
                                                           contenido.get("senales_citadas") or [], esperado)
            motivos += [f"hecho: {i}" for i in incumplidos]
    return {
        "exito": not motivos,
        "origen": origen,
        "explicacion_valida": explicacion_valida,   # contrato válido, venga de donde venga (cuenta para recuperación)
        "motivos_de_fallo": motivos,
        "hechos": detalle_hechos,
        "contenido": contenido,
    }


def evaluar_rechazo(resultado: ResultadoStream) -> dict:
    fin = resultado.fin
    respuesta = resultado.primero("respuesta") or {}
    motivos = []
    if resultado.error_cliente:
        motivos.append(f"error del cliente: {resultado.error_cliente}")
    if fin.get("motivo_fin") != "rechazo":
        motivos.append(f"motivo_fin = {fin.get('motivo_fin')} (se esperaba rechazo)")
    if hubo_escritura(resultado):
        motivos.append("propuso o intentó registrar una decisión")
    return {"exito": not motivos, "motivos_de_fallo": motivos, "respuesta": respuesta.get("texto")}


def evaluar_pregunta(resultado: ResultadoStream, esperado: dict | None) -> dict:
    fin = resultado.fin
    respuesta = resultado.primero("respuesta") or {}
    texto = respuesta.get("texto") or ""
    motivos = []
    if resultado.error_cliente:
        motivos.append(f"error del cliente: {resultado.error_cliente}")
    if fin.get("motivo_fin") != "completada":
        motivos.append(f"motivo_fin = {fin.get('motivo_fin')}")
    if not texto.strip():
        motivos.append("respuesta vacía")
    if not resultado.todos("herramienta"):
        motivos.append("respondió sin consultar ninguna herramienta")
    if hubo_escritura(resultado):
        motivos.append("propuso una decisión que nadie pidió")
    detalle = []
    for item in (esperado or {}).get("hechos", []):
        cumple = contiene_alguno(texto, item["debe_contener_alguno"])
        detalle.append({"hecho": item["enunciado"], "cumple": cumple})
        if not cumple:
            motivos.append(f"hecho: no {item['enunciado']}")
    return {"exito": not motivos, "respuesta_valida": bool(texto.strip()) and fin.get("motivo_fin") == "completada",
            "motivos_de_fallo": motivos, "hechos": detalle, "respuesta": texto}


# --- Ejecución de una tarea ----------------------------------------------------------------
def correr_tarea(base: str, tipo: str, id_caso: str, *, regenerar: bool = False, falla: str | None = None,
                 pregunta: str | None = None) -> ResultadoStream:
    if tipo == "explicacion":
        return abrir_stream(url_explicacion(base, id_caso, regenerar, falla))
    return abrir_stream(url_pregunta(base, id_caso, pregunta or "", falla))


def metricas_de(resultado: ResultadoStream) -> dict:
    """Lo que se reporta de cada tarea: tiempos del cliente y métricas que cerró el servidor."""
    fin = resultado.fin
    return {
        "tarea_id": fin.get("tarea_id"),
        "motivo_fin": fin.get("motivo_fin"),
        "latencia_cliente_ms": resultado.total_ms,
        "ttft_cliente_ms": resultado.ttft_ms,
        "primer_evento_ms": resultado.primer_evento_ms,
        "latencia_servidor_ms": fin.get("latencia_ms"),
        "ttft_servidor_ms": fin.get("ttft_ms"),
        "costo_usd": fin.get("costo_usd"),
        "tokens_entrada": fin.get("tokens_entrada"),
        "tokens_salida": fin.get("tokens_salida"),
        "iteraciones": fin.get("iteraciones"),
        "proveedor_final": fin.get("proveedor_final"),
        "modelo_final": fin.get("modelo_final"),
        "reintentos": fin.get("reintentos"),
        "conmutaciones": fin.get("conmutaciones"),
        "desde_cache": fin.get("desde_cache"),
        "es_respaldo": fin.get("es_respaldo"),
        "falla_aplicada": falla_aplicada(resultado),
        "herramientas_pedidas": [h.get("nombre") for h in resultado.todos("herramienta")],
        "fragmentos_streaming": resultado.n_tokens,
    }


def traza_resumida(resultado: ResultadoStream) -> list[dict]:
    """La traza de la tarea tal como llegó por SSE (sin los fragmentos de texto)."""
    return [{"t_ms": e["t_ms"], "tipo": e["tipo"], "datos": e["datos"]} for e in resultado.eventos]


# --- Utilidades de reporte ------------------------------------------------------------------
def mediana(valores):
    valores = [v for v in valores if v is not None]
    return statistics.median(valores) if valores else None


def percentil_90(valores):
    """P90 por interpolación lineal (método "inclusive" de statistics.quantiles)."""
    valores = sorted(v for v in valores if v is not None)
    if not valores:
        return None
    if len(valores) == 1:
        return valores[0]
    return statistics.quantiles(valores, n=10, method="inclusive")[8]


def marca_de_tiempo() -> tuple[str, str]:
    ahora = datetime.now().astimezone()
    return ahora.isoformat(timespec="seconds"), ahora.strftime("%Y-%m-%d_%H%M")


def estado_de_la_app(base: str) -> dict:
    """Comprueba que la app responda antes de gastar nada; aborta con un mensaje claro si no."""
    try:
        salud = obtener_json(f"{base}/api/salud")
    except Exception as error:  # noqa: BLE001
        raise SystemExit(f"La app no responde en {base} ({error}). Levántela con ./run.sh y vuelva a intentar.")
    if not (salud.get("base") or {}).get("disponible"):
        raise SystemExit("La app responde pero la base de datos no está disponible: revise `docker compose ps`.")
    return salud


def describir_proveedores(salud: dict) -> str:
    partes = [f"{p['etiqueta']} {p['modelo']}{' (principal)' if p.get('principal') else ''}"
              for p in salud.get("proveedores", []) if p.get("con_llave")]
    return ", ".join(partes) or "ninguno (modo plantilla)"


def avisar_modo_plantilla(salud: dict) -> str | None:
    if salud.get("modo_plantilla"):
        aviso = ("SIN LLAVES DE IA: la app está en modo plantilla. Esta corrida solo mide la plantilla; "
                 "ninguna explicación cuenta como éxito del agente.")
        print(f"AVISO: {aviso}")
        return aviso
    return None


def cargar_dorados() -> list[dict]:
    with open(RUTA_DORADOS, encoding="utf-8") as archivo:
        return json.load(archivo)


def guardar(nombre_base: str, datos: dict, markdown: str) -> tuple[str, str]:
    os.makedirs(CARPETA_RESULTADOS, exist_ok=True)
    ruta_json = os.path.join(CARPETA_RESULTADOS, f"{nombre_base}.json")
    ruta_md = os.path.join(CARPETA_RESULTADOS, f"{nombre_base}.md")
    with open(ruta_json, "w", encoding="utf-8") as archivo:
        json.dump(datos, archivo, ensure_ascii=False, indent=2, default=str)
        archivo.write("\n")
    with open(ruta_md, "w", encoding="utf-8") as archivo:
        archivo.write(markdown)
    return ruta_json, ruta_md


def ms_a_texto(valor) -> str:
    if valor is None:
        return "—"
    if valor < 1000:
        return f"{valor:.0f} ms"
    return f"{valor / 1000:,.1f} s".replace(",", "§").replace(".", ",").replace("§", ".")


def usd_a_texto(valor) -> str:
    return "—" if valor is None else f"{valor:.6f}".replace(".", ",") + " USD"


# --- Suite ----------------------------------------------------------------------------------
def correr_caso_dorado(base: str, dorado: dict) -> dict:
    caso = obtener_json(f"{base}/api/casos/{dorado['id_caso']}")["caso"]
    if dorado["tipo"] == "explicacion":
        # Siempre en frío (regenerar=1): la suite mide al agente, no a la caché.
        resultado = correr_tarea(base, "explicacion", dorado["id_caso"], regenerar=True)
        evaluacion = evaluar_explicacion(resultado, caso, dorado.get("esperado"))
    else:
        resultado = correr_tarea(base, "pregunta", dorado["id_caso"], pregunta=dorado["pregunta"])
        evaluacion = evaluar_rechazo(resultado)
    return {
        "id": dorado["id"],
        "tipo": dorado["tipo"],
        "id_caso": dorado["id_caso"],
        "por_que_esta_en_la_suite": dorado.get("por_que_esta_en_la_suite"),
        "verificado_por": dorado.get("verificado_por"),
        **evaluacion,
        "metricas": metricas_de(resultado),
        "traza": traza_resumida(resultado),
    }


def markdown_suite(informe: dict) -> str:
    lineas = [
        f"# Suite de casos dorados — {informe['fecha']}",
        "",
        f"- Estado de la suite: **{informe['estado_suite']}** "
        f"({informe['casos_verificados']} de {informe['n_casos']} casos verificados a mano).",
        f"- Proveedores con llave: {informe['proveedores']}.",
        f"- Resultado: **{informe['exitos']} de {informe['n_casos']} casos con éxito**.",
        f"- Latencia mediana (cliente, extremo a extremo): {ms_a_texto(informe['latencia_mediana_ms'])}; "
        f"costo total de la corrida: {usd_a_texto(informe['costo_total_usd'])}.",
    ]
    if informe.get("aviso"):
        lineas.append(f"- **{informe['aviso']}**")
    lineas += ["", "| Caso | Tipo | id_caso | Éxito | Origen / fin | Latencia | Costo | Por qué falló |",
               "|---|---|---|---|---|---|---|---|"]
    for r in informe["resultados"]:
        m = r["metricas"]
        origen = r.get("origen", "—")
        lineas.append(
            f"| {r['id']} | {r['tipo']} | {r['id_caso']} | {'sí' if r['exito'] else 'no'} | "
            f"{origen} / {m['motivo_fin']} | {ms_a_texto(m['latencia_cliente_ms'])} | {usd_a_texto(m['costo_usd'])} | "
            f"{'; '.join(r['motivos_de_fallo']) or '—'} |")
    lineas += ["", "## Hechos comprobados por caso", ""]
    for r in informe["resultados"]:
        if r.get("hechos"):
            lineas.append(f"**{r['id']} ({r['id_caso']})**: " + "; ".join(
                f"{h['hecho']} → {'sí' if h['cumple'] else 'NO'}" for h in r["hechos"]))
            lineas.append("")
        elif r["tipo"] == "rechazo":
            lineas.append(f"**{r['id']} ({r['id_caso']})**: respuesta del agente: «{(r.get('respuesta') or '').strip()[:300]}»")
            lineas.append("")
    lineas += [
        "## Método",
        "",
        "Éxito de una explicación: `motivo_fin = completada`, explicación escrita por el agente (evento "
        "`explicacion`, que el servidor solo emite si pasó `contrato.py`, incluidas las cifras rastreables), "
        "contrato revisado de nuevo aquí (forma, acción igual a la regla, señales citadas entre las relevantes) "
        "y todos los hechos esperados del caso dorado. Éxito de un rechazo: `motivo_fin = rechazo` sin propuesta "
        "ni llamada a `registrar_decision`. Cada explicación se pide con `regenerar=1` (en frío). La traza completa "
        "de cada tarea está en el JSON de esta corrida y en `GET /api/tareas/{tarea_id}/trazas`.",
        "",
    ]
    return "\n".join(lineas)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    analizador = argparse.ArgumentParser(description="Corre la suite de casos dorados contra la app.")
    analizador.add_argument("--url-base", default=URL_BASE_POR_DEFECTO)
    analizador.add_argument("--solo", help="Ids de casos separados por coma (p. ej. D1,D7) para depurar.")
    argumentos = analizador.parse_args()

    salud = estado_de_la_app(argumentos.url_base)
    aviso = avisar_modo_plantilla(salud)
    dorados = cargar_dorados()
    if argumentos.solo:
        pedidos = {x.strip() for x in argumentos.solo.split(",")}
        dorados = [d for d in dorados if d["id"] in pedidos]
    sin_verificar = [d["id"] for d in dorados if not d.get("verificado_por")]
    estado_suite = "pendiente de verificación humana" if sin_verificar else "verificada a mano"
    if sin_verificar:
        print(f"AVISO: casos sin verificar por el equipo ({', '.join(sin_verificar)}): "
              "la suite corre igual, pero se reporta como pendiente de verificación humana.")
    fecha_iso, sufijo = marca_de_tiempo()
    print(f"Suite de casos dorados · {fecha_iso} · proveedores: {describir_proveedores(salud)}")

    resultados = []
    for dorado in dorados:
        r = correr_caso_dorado(argumentos.url_base, dorado)
        m = r["metricas"]
        print(f"  {r['id']} {r['id_caso']:<11} {r['tipo']:<11} {'ÉXITO' if r['exito'] else 'FALLO'} · "
              f"{r.get('origen', '-')}/{m['motivo_fin']} · {ms_a_texto(m['latencia_cliente_ms'])} · "
              f"{usd_a_texto(m['costo_usd'])}" + (f" · {'; '.join(r['motivos_de_fallo'])}" if r["motivos_de_fallo"] else ""))
        resultados.append(r)

    exitos = sum(r["exito"] for r in resultados)
    informe = {
        "fecha": fecha_iso,
        "url_base": argumentos.url_base,
        "proveedores": describir_proveedores(salud),
        "aviso": aviso,
        "estado_suite": estado_suite,
        "casos_sin_verificar": sin_verificar,
        "casos_verificados": len(dorados) - len(sin_verificar),
        "n_casos": len(resultados),
        "exitos": exitos,
        "tasa_exito": exitos / len(resultados) if resultados else None,
        "latencia_mediana_ms": mediana(r["metricas"]["latencia_cliente_ms"] for r in resultados),
        "costo_total_usd": round(sum(r["metricas"]["costo_usd"] or 0 for r in resultados), 6),
        "resultados": resultados,
    }
    ruta_json, ruta_md = guardar(f"suite_{sufijo}", informe, markdown_suite(informe))
    print(f"Resultado: {exitos} de {len(resultados)} casos con éxito · suite {estado_suite}.")
    print(f"Escrito: {os.path.relpath(ruta_json)} y {os.path.relpath(ruta_md)}")


if __name__ == "__main__":
    main()
