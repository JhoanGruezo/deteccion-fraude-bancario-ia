"""Corre el lote de medición contra la app y calcula las cuatro cifras de la línea base.

Por qué existe: la rúbrica del Momento 2 pide "las cuatro cifras con fecha, con el
método explicado y con mediana en latencia" en docs/decisiones.md, y el reto 9 pide
medir latencia P50/P90, costo y ahorro por caché sobre al menos 15 consultas. Este
script corre las 19 tareas de eval/lote_medicion.json en orden (las 6 explicaciones
doradas en frío, las mismas 6 desde caché, 3 preguntas y 4 fallas forzadas) y deja la
evidencia en eval/resultados/lote_<fecha>.json (con la traza de cada tarea) y .md.

Las cuatro cifras (diseno/evaluacion-entrega.md):
1. Tasa de éxito = tareas con éxito / tareas. Éxito con la misma definición que la
   suite (eval/correr_suite.py): la plantilla no es éxito del agente.
2. Costo por tarea = mediana de `costo_usd` (tarifa de lista de app/config.py) de las
   tareas NO servidas desde caché. La caché cuesta 0 y se reporta aparte como ahorro.
3. Latencia de extremo a extremo (medida por el cliente, desde la petición hasta el
   evento `fin`): mediana y P90 de las tareas no servidas desde caché, y TTFT mediano
   (petición → primer fragmento de texto del modelo).
4. Recuperación = tareas con fallo (forzado o real: reintentos, conmutación, contrato
   inválido, límite, caída) que terminaron con una explicación válida (del agente, del
   respaldo o de la plantilla) o con una respuesta válida / tareas con fallo.
Además: ahorro por caché = latencia y costo de la segunda apertura frente a la primera.

Las fallas se piden por tarea con `?falla=` (no con POST /api/demo/falla): así el lote
no cambia el estado global de la app que otra persona puede estar usando. Si una
tarea limpia recibe una falla que no pidió (porque alguien la fijó en el panel de
demo), queda marcada como "contaminada" en el informe.

Uso (con la app arriba; cada corrida cuesta unos centavos de dólar):
    python eval/correr_lote.py
"""

import argparse
import json
import os
import sys

CARPETA_EVAL = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, CARPETA_EVAL)

from cliente_sse import URL_BASE_POR_DEFECTO, obtener_json  # noqa: E402
from correr_suite import (avisar_modo_plantilla, cargar_dorados, correr_tarea, describir_proveedores,  # noqa: E402
                          estado_de_la_app, evaluar_explicacion, evaluar_pregunta, guardar, marca_de_tiempo,
                          mediana, metricas_de, ms_a_texto, percentil_90, traza_resumida, usd_a_texto)

RUTA_LOTE = os.path.join(CARPETA_EVAL, "lote_medicion.json")
MOTIVOS_DE_FALLO = {"respaldo", "limite_iteraciones", "limite_tokens", "timeout", "error"}


def hubo_fallo(resultado, metricas: dict) -> tuple[bool, str | None]:
    """¿La tarea sufrió algún fallo, forzado o real? Devuelve (sí/no, descripción)."""
    if metricas["falla_aplicada"]:
        return True, f"forzada: {metricas['falla_aplicada']}"
    reales = []
    if resultado.error_cliente:
        reales.append("conexión")
    if metricas["reintentos"]:
        reales.append(f"{metricas['reintentos']} reintento(s)")
    if metricas["conmutaciones"]:
        reales.append("conmutación de proveedor")
    if resultado.todos("contrato_invalido"):
        reales.append("contrato inválido")
    if metricas["motivo_fin"] in MOTIVOS_DE_FALLO:
        reales.append(f"motivo_fin {metricas['motivo_fin']}")
    return (True, "real: " + ", ".join(reales)) if reales else (False, None)


def correr_tarea_del_lote(base: str, tarea: dict, dorados: dict, casos: dict) -> dict:
    dorado = dorados[tarea["dorado"]]
    id_caso = dorado["id_caso"]
    if id_caso not in casos:
        casos[id_caso] = obtener_json(f"{base}/api/casos/{id_caso}")["caso"]
    if tarea["tipo"] == "explicacion":
        resultado = correr_tarea(base, "explicacion", id_caso, regenerar=tarea.get("regenerar", False),
                                 falla=tarea.get("falla"))
        evaluacion = evaluar_explicacion(resultado, casos[id_caso], dorado.get("esperado"))
        salio_bien = evaluacion["explicacion_valida"] and resultado.termino_con_fin
    else:
        resultado = correr_tarea(base, "pregunta", id_caso, pregunta=tarea["pregunta"], falla=tarea.get("falla"))
        evaluacion = evaluar_pregunta(resultado, tarea.get("esperado"))
        salio_bien = evaluacion["respuesta_valida"]
    metricas = metricas_de(resultado)
    con_fallo, descripcion_fallo = hubo_fallo(resultado, metricas)
    contaminada = (tarea.get("falla") or None) != metricas["falla_aplicada"]
    return {
        "id": tarea["id"],
        "tipo": tarea["tipo"],
        "dorado": tarea["dorado"],
        "id_caso": id_caso,
        "proposito": tarea.get("proposito"),
        "regenerar": tarea.get("regenerar"),
        "falla_pedida": tarea.get("falla"),
        "contaminada": contaminada,
        **evaluacion,
        "con_fallo": con_fallo,
        "descripcion_fallo": descripcion_fallo,
        "recuperada": con_fallo and salio_bien,
        "metricas": metricas,
        "traza": traza_resumida(resultado),
    }


def calcular_cifras(resultados: list[dict]) -> dict:
    n = len(resultados)
    exitos = sum(r["exito"] for r in resultados)
    no_cache = [r for r in resultados if not r["metricas"]["desde_cache"]]
    sin_falla_no_cache = [r for r in no_cache if not r["falla_pedida"]]
    con_fallo = [r for r in resultados if r["con_fallo"]]
    recuperadas = sum(r["recuperada"] for r in con_fallo)

    # Ahorro por caché: cada explicación en frío contra su segunda apertura del mismo caso.
    pares = []
    frias = {r["dorado"]: r for r in resultados if r["tipo"] == "explicacion" and r["regenerar"] and not r["falla_pedida"]}
    for r in resultados:
        if r["tipo"] == "explicacion" and not r["regenerar"] and r["dorado"] in frias:
            fria = frias[r["dorado"]]
            pares.append({"dorado": r["dorado"], "desde_cache": bool(r["metricas"]["desde_cache"]),
                          "latencia_fria_ms": fria["metricas"]["latencia_cliente_ms"],
                          "latencia_cache_ms": r["metricas"]["latencia_cliente_ms"],
                          "costo_frio_usd": fria["metricas"]["costo_usd"],
                          "costo_cache_usd": r["metricas"]["costo_usd"]})
    pares_validos = [p for p in pares if p["desde_cache"]]
    lat_fria = mediana(p["latencia_fria_ms"] for p in pares_validos)
    lat_cache = mediana(p["latencia_cache_ms"] for p in pares_validos)
    costo_frio = mediana(p["costo_frio_usd"] for p in pares_validos)

    return {
        "n_tareas": n,
        "tasa_exito": {"exitos": exitos, "tareas": n, "valor": exitos / n if n else None},
        "costo_por_tarea": {
            "mediana_usd": mediana(r["metricas"]["costo_usd"] for r in no_cache),
            "tareas_consideradas": len(no_cache),
            "mediana_sin_fallas_forzadas_usd": mediana(r["metricas"]["costo_usd"] for r in sin_falla_no_cache),
            "total_lote_usd": round(sum(r["metricas"]["costo_usd"] or 0 for r in resultados), 6),
        },
        "latencia": {
            "mediana_ms": mediana(r["metricas"]["latencia_cliente_ms"] for r in no_cache),
            "p90_ms": percentil_90([r["metricas"]["latencia_cliente_ms"] for r in no_cache]),
            "tareas_consideradas": len(no_cache),
            "mediana_sin_fallas_forzadas_ms": mediana(r["metricas"]["latencia_cliente_ms"] for r in sin_falla_no_cache),
            "mediana_todas_ms": mediana(r["metricas"]["latencia_cliente_ms"] for r in resultados),
            "ttft_mediano_ms": mediana(r["metricas"]["ttft_cliente_ms"] for r in resultados),
            "tareas_con_ttft": sum(r["metricas"]["ttft_cliente_ms"] is not None for r in resultados),
        },
        "recuperacion": {"recuperadas": recuperadas, "tareas_con_fallo": len(con_fallo),
                         "valor": recuperadas / len(con_fallo) if con_fallo else None},
        "ahorro_cache": {
            "pares": pares,
            "pares_servidos_desde_cache": len(pares_validos),
            "latencia_mediana_fria_ms": lat_fria,
            "latencia_mediana_cache_ms": lat_cache,
            "costo_mediano_frio_usd": costo_frio,
            "costo_cache_usd": 0.0 if pares_validos else None,
            "reduccion_latencia": (1 - lat_cache / lat_fria) if lat_fria and lat_cache is not None else None,
        },
        "tareas_contaminadas": [r["id"] for r in resultados if r["contaminada"]],
    }


def porcentaje(valor) -> str:
    return "—" if valor is None else f"{valor * 100:.1f} %".replace(".", ",")


def markdown_lote(informe: dict) -> str:
    c = informe["cifras"]
    t, co, la, re_, ah = c["tasa_exito"], c["costo_por_tarea"], c["latencia"], c["recuperacion"], c["ahorro_cache"]
    lineas = [
        f"# Lote de medición — {informe['fecha']}",
        "",
        f"Proveedores con llave: {informe['proveedores']}. Tareas corridas: {c['n_tareas']} "
        f"(el lote completo son 6 explicaciones en frío, 6 desde caché, 3 preguntas y 4 fallas forzadas).",
    ]
    if informe.get("aviso"):
        lineas.append(f"\n**{informe['aviso']}**")
    if c["tareas_contaminadas"]:
        lineas.append(f"\n**Tareas contaminadas** (recibieron una falla distinta a la pedida): {', '.join(c['tareas_contaminadas'])}.")
    lineas += [
        "",
        "## Las cuatro cifras",
        "",
        "| Cifra | Valor | Cómo se calcula |",
        "|---|---|---|",
        f"| Tasa de éxito | **{porcentaje(t['valor'])}** ({t['exitos']} de {t['tareas']}) | tareas con éxito / tareas del lote; la plantilla no cuenta como éxito |",
        f"| Costo por tarea | **{usd_a_texto(co['mediana_usd'])}** (mediana) | mediana de `costo_usd` a tarifa de lista, {co['tareas_consideradas']} tareas no servidas desde caché; sin las fallas forzadas: {usd_a_texto(co['mediana_sin_fallas_forzadas_usd'])}; total del lote: {usd_a_texto(co['total_lote_usd'])} |",
        f"| Latencia | **mediana {ms_a_texto(la['mediana_ms'])}**, P90 {ms_a_texto(la['p90_ms'])}; TTFT mediano {ms_a_texto(la['ttft_mediano_ms'])} | extremo a extremo medida por el cliente (petición → `fin`), {la['tareas_consideradas']} tareas no servidas desde caché; sin fallas forzadas: mediana {ms_a_texto(la['mediana_sin_fallas_forzadas_ms'])}; TTFT sobre {la['tareas_con_ttft']} tareas con texto en streaming |",
        f"| Recuperación | **{porcentaje(re_['valor'])}** ({re_['recuperadas']} de {re_['tareas_con_fallo']}) | tareas con fallo forzado o real que terminaron con explicación o respuesta válida / tareas con fallo |",
        "",
        f"**Ahorro por caché** ({ah['pares_servidos_desde_cache']} pares): la segunda apertura tarda "
        f"{ms_a_texto(ah['latencia_mediana_cache_ms'])} (mediana) frente a {ms_a_texto(ah['latencia_mediana_fria_ms'])} "
        f"en frío ({porcentaje(ah['reduccion_latencia'])} menos) y cuesta 0 USD frente a "
        f"{usd_a_texto(ah['costo_mediano_frio_usd'])} (mediana en frío).",
        "",
        "## Tareas",
        "",
        "| Tarea | Caso | Qué mide | Éxito | Origen / fin | Fallo | ¿Recuperada? | Latencia | TTFT | Costo | Proveedor | Por qué no fue éxito |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in informe["resultados"]:
        m = r["metricas"]
        lineas.append(
            f"| {r['id']} | {r['dorado']} {r['id_caso']} | {r['proposito']} | {'sí' if r['exito'] else 'no'} | "
            f"{r.get('origen', 'pregunta')} / {m['motivo_fin']} | {r['descripcion_fallo'] or '—'} | "
            f"{('sí' if r['recuperada'] else 'no') if r['con_fallo'] else '—'} | {ms_a_texto(m['latencia_cliente_ms'])} | "
            f"{ms_a_texto(m['ttft_cliente_ms'])} | {usd_a_texto(m['costo_usd'])} | {m['proveedor_final'] or '—'} | "
            f"{'; '.join(r['motivos_de_fallo']) or '—'} |")
    lineas += [
        "",
        "## Método",
        "",
        "Cada tarea abre el mismo SSE que el navegador (`eval/cliente_sse.py`) y se mide con el reloj del cliente. "
        "Las mediana y el P90 (interpolación lineal) se calculan sobre las tareas no servidas desde caché, porque la "
        "caché se reporta aparte como ahorro. El costo es el de lista (tokens × tarifa por millón de `app/config.py`), "
        "aunque la cuenta tenga créditos. La traza completa de cada tarea está en el JSON de esta corrida y en "
        "`GET /api/tareas/{tarea_id}/trazas`.",
        "",
    ]
    return "\n".join(lineas)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    analizador = argparse.ArgumentParser(description="Corre el lote de medición y calcula las cuatro cifras.")
    analizador.add_argument("--url-base", default=URL_BASE_POR_DEFECTO)
    argumentos = analizador.parse_args()

    salud = estado_de_la_app(argumentos.url_base)
    aviso = avisar_modo_plantilla(salud)
    dorados = {d["id"]: d for d in cargar_dorados()}
    with open(RUTA_LOTE, encoding="utf-8") as archivo:
        tareas = json.load(archivo)["tareas"]
    fecha_iso, sufijo = marca_de_tiempo()
    print(f"Lote de medición · {fecha_iso} · {len(tareas)} tareas · proveedores: {describir_proveedores(salud)}")

    casos, resultados, interrumpido = {}, [], None
    for tarea in tareas:
        # Si la base se cae a mitad del lote, lo que sigue mediría la caída de la
        # infraestructura y no al agente: se detiene y se guarda como corrida parcial.
        try:
            disponible = (obtener_json(f"{argumentos.url_base}/api/salud").get("base") or {}).get("disponible")
        except Exception:  # noqa: BLE001
            disponible = False
        if not disponible:
            interrumpido = f"la app o su base de datos dejó de responder antes de {tarea['id']}"
            print(f"INTERRUMPIDO: {interrumpido}. Se guarda como corrida parcial (no sirve como línea base).")
            break
        r = correr_tarea_del_lote(argumentos.url_base, tarea, dorados, casos)
        m = r["metricas"]
        print(f"  {r['id']} {r['dorado']} {r['tipo']:<11} {'ÉXITO' if r['exito'] else 'fallo'} · "
              f"{r.get('origen', 'pregunta')}/{m['motivo_fin']} · {ms_a_texto(m['latencia_cliente_ms'])} · "
              f"{usd_a_texto(m['costo_usd'])} · {m['proveedor_final'] or '-'}"
              + (f" · {r['descripcion_fallo']} → {'recuperada' if r['recuperada'] else 'NO recuperada'}" if r["con_fallo"] else "")
              + (f" · {'; '.join(r['motivos_de_fallo'])}" if r["motivos_de_fallo"] else ""))
        resultados.append(r)

    cifras = calcular_cifras(resultados)
    if interrumpido:
        aviso = f"CORRIDA PARCIAL: {interrumpido}." + (f" {aviso}" if aviso else "")
    informe = {"fecha": fecha_iso, "url_base": argumentos.url_base, "proveedores": describir_proveedores(salud),
               "aviso": aviso, "parcial": bool(interrumpido), "cifras": cifras, "resultados": resultados}
    ruta_json, ruta_md = guardar(f"lote_{sufijo}{'_parcial' if interrumpido else ''}", informe, markdown_lote(informe))

    t, co, la, re_ = cifras["tasa_exito"], cifras["costo_por_tarea"], cifras["latencia"], cifras["recuperacion"]
    print(f"Tasa de éxito: {porcentaje(t['valor'])} ({t['exitos']}/{t['tareas']}) · "
          f"costo mediano: {usd_a_texto(co['mediana_usd'])} · latencia mediana {ms_a_texto(la['mediana_ms'])} "
          f"(P90 {ms_a_texto(la['p90_ms'])}, TTFT {ms_a_texto(la['ttft_mediano_ms'])}) · "
          f"recuperación: {porcentaje(re_['valor'])} ({re_['recuperadas']}/{re_['tareas_con_fallo']})")
    print(f"Escrito: {os.path.relpath(ruta_json)} y {os.path.relpath(ruta_md)}")


if __name__ == "__main__":
    main()
