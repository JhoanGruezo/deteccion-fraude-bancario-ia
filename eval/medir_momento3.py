"""Medición del Momento 3 (docs/SPEC.md §7): la noche del 19-jul-2020 con el sistema completo.

Qué hace, en orden:
1. Reinicia los datos en vivo (usuario dueño) y crea un usuario `evaluador` (supervisor) con una
   contraseña al azar que solo vive en este proceso.
2. Inicia sesión por la API, fija la falla forzada pedida (ninguna, o "todo" para medir con la IA
   caída), sube el tope de bloqueos por hora (el reloj acelerado mete 36 h en segundos y el tope
   es por hora REAL) y reproduce la noche completa con el simulador.
3. Espera a que terminen todos los triajes y a que no quede ningún caso crítico sin bloqueo.
4. Calcula las cifras con el usuario dueño (que sí ve la etiqueta del dataset) y las guarda en
   `eval/resultados/momento3_<fecha>_<nombre>.json`.

Cifras (todas sobre las mismas 5.810 compras):
- tiempo de decisión por compra (puntuación y camino completo, mediana y p99);
- casos por banda, bloqueos por actor, segundos desde que se abre el caso hasta el bloqueo;
- dinero del fraude que pasó y que se detuvo, frente a la regla del Momento 2 en tres escenarios
  (analista al instante, con cola de 90 min, y de noche sin turno hasta las 07:00);
- precisión y recall de los bloqueos por tarjeta, y bloqueos falsos por cada 1.000 compras;
- prueba de necesidad: decisiones del agente en la banda alta contra la etiqueta;
- costo del LLM (total, por triaje y por cada 1.000 compras) y recuperación ante fallas.

Uso (dentro del contenedor, porque la base no se publica):
    docker compose exec app python eval/medir_momento3.py --nombre base
    docker compose exec app python eval/medir_momento3.py --nombre ia_caida --falla todo
"""

import argparse
import json
import os
import secrets
import statistics
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "eval"))

import psycopg  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402

from app import config  # noqa: E402
from app.db import migrar  # noqa: E402
from app.db.repositorio_usuarios import derivar_clave  # noqa: E402
from cliente_sse import enviar_json, iniciar_sesion, obtener_json  # noqa: E402

URL = "http://localhost:8000"
COLA_ANALISTA = timedelta(minutes=90)
INICIO_TURNO = 7


def dueno():
    return psycopg.connect(config.DATABASE_URL, row_factory=dict_row)


def preparar_evaluador() -> str:
    clave = secrets.token_urlsafe(16)
    with dueno() as con:
        con.execute("""insert into usuarios (usuario, nombre, rol, hash_clave) values ('evaluador', 'Evaluación eval/', 'supervisor', %s)
                       on conflict (usuario) do update set hash_clave = excluded.hash_clave, activo = true""",
                    (derivar_clave(clave),))
    return clave


def esperar_fin(maximo_s: float) -> None:
    limite = time.monotonic() + maximo_s
    while time.monotonic() < limite:
        estado = obtener_json(f"{URL}/api/simulador")
        print(f"\r  simulador: {estado['estado']:<10} {estado['indice']:>5}/{estado['total']}  "
              f"reloj {estado['reloj_dataset']}", end="", flush=True)
        if estado["estado"] in ("terminado", "detenido"):
            break
        time.sleep(2)
    print()
    quieto_desde = None
    while time.monotonic() < limite:
        with dueno() as con:
            abiertas = con.execute("select count(*) as n from tareas_agente where tipo = 'triaje' and terminada_en is null").fetchone()["n"]
            criticos = con.execute("""select count(*) as n from casos c where origen = 'en_vivo' and banda = 'critica'
                                      and estado not in ('bloqueado', 'descartado', 'desbloqueado')""").fetchone()["n"]
        if abiertas == 0 and criticos == 0:
            quieto_desde = quieto_desde or time.monotonic()
            if time.monotonic() - quieto_desde > 8:
                return
        else:
            quieto_desde = None
        print(f"\r  esperando: {abiertas} triajes en curso, {criticos} críticos sin bloqueo   ", end="", flush=True)
        time.sleep(2)
    print("\n  AVISO: se agotó la espera; las cifras pueden estar incompletas.")


def percentil(valores, p):
    valores = sorted(v for v in valores if v is not None)
    if not valores:
        return None
    k = (len(valores) - 1) * p
    i, j = int(k), min(int(k) + 1, len(valores) - 1)
    return round(valores[i] + (valores[j] - valores[i]) * (k - i), 3)


def proximo_turno(momento: datetime) -> datetime:
    """Si la alerta llega fuera del turno (22:00-07:00), el analista la ve a las 07:00."""
    if 7 <= momento.hour < 22:
        return momento + COLA_ANALISTA
    dia = momento.date() if momento.hour < INICIO_TURNO else momento.date() + timedelta(days=1)
    return datetime.combine(dia, datetime.min.time()) + timedelta(hours=INICIO_TURNO)


def calcular(umbral_bloqueo: float) -> dict:
    with dueno() as con:
        tx = con.execute("""select id_transaccion, id_cuenta, fecha_hora, monto::float as monto, score, banda, decision,
                                   coalesce(es_fraude_dataset, 0) as fraude, latencia_puntuacion_ms, latencia_total_ms, id_caso
                            from transacciones_evaluadas where origen = 'simulador' order by fecha_hora, id_transaccion""").fetchall()
        casos = con.execute("select id_caso, banda, estado from casos where origen = 'en_vivo'").fetchall()
        bloqueos = con.execute("""select id_caso, id_cuenta, actor, tipo, segundos_hasta_bloqueo from bloqueos""").fetchall()
        tareas = con.execute("""select tarea_id, id_caso, motivo_fin, costo_usd::float as costo, tokens_entrada, tokens_salida,
                                       latencia_ms, proveedor_final, conmutaciones, reintentos
                                from tareas_agente where tipo = 'triaje'""").fetchall()
        trazas = con.execute("""select t.tarea_id, t.tipo, t.detalle from trazas t join tareas_agente a using (tarea_id)
                                where a.tipo = 'triaje' and t.tipo in ('inicio', 'accion_triaje', 'respaldo_triaje')
                                order by t.tarea_id, t.paso""").fetchall()
        avisos = con.execute("select autor_motivo, tipo, errores_validacion from notificaciones").fetchall()

    total_fraude = sum(t["monto"] for t in tx if t["fraude"])
    fraude_pasado = sum(t["monto"] for t in tx if t["fraude"] and t["decision"] == "aprobada")
    legitimo_rechazado = sum(t["monto"] for t in tx if not t["fraude"] and t["decision"] != "aprobada")

    # Regla del M2 sobre las mismas compras: caso al 2.º score sobre el umbral de bloqueo.
    por_tarjeta = defaultdict(list)
    for t in tx:
        por_tarjeta[t["id_cuenta"]].append(t)
    escenarios = {"m2_analista_al_instante": lambda abre: abre, "m2_cola_90_min": lambda abre: abre + COLA_ANALISTA,
                  "m2_noche_sin_turno": proximo_turno}
    perdido_m2 = {nombre: 0.0 for nombre in escenarios}
    for compras in por_tarjeta.values():
        marcas = [c["fecha_hora"] for c in compras if c["score"] >= umbral_bloqueo]
        for nombre, bloqueo_en in escenarios.items():
            corte = bloqueo_en(marcas[1]) if len(marcas) >= 2 else None
            perdido_m2[nombre] += sum(c["monto"] for c in compras if c["fraude"] and (corte is None or c["fecha_hora"] <= corte))

    # Dinero A TIEMPO REAL. En la simulación acelerada (3600x = 1 s real por cada hora del
    # dataset) los ~5 s que tarda el triaje equivalen a ~5 HORAS del dataset, y en ese lapso
    # artificial el ladrón alcanza a hacer varias compras más. Para no reportar ese artefacto, cada
    # bloqueo se traslada a tiempo real: la PRIMERA compra que dejó el caso en la banda en la que se
    # bloqueó (la que disparó el triaje) + los segundos REALES que pasaron hasta el bloqueo, contados
    # como segundos del dataset. Esos segundos incluyen la espera en la cola de triajes, que en la
    # simulación se satura (36 h de casos en 36 s) y en tiempo real no: la cifra es conservadora.
    with dueno() as con:
        disparos = con.execute(
            """select b.id_cuenta, b.actor, b.creado_en, d.fecha_hora as fecha_disparo,
                      extract(epoch from b.creado_en - d.recibida_en) as segundos_reales
               from bloqueos b
               -- Banda de la decisión: la banda con la que EMPEZÓ el triaje que bloqueó (si fue el
               -- agente); si fue la regla, la banda del caso al bloquear (crítica).
               left join lateral (select tr.detalle->>'banda' as banda from trazas tr
                                  where tr.tarea_id = b.tarea_id and tr.tipo = 'inicio' limit 1) i on true
               join lateral (select e.fecha_hora, e.recibida_en from transacciones_evaluadas e
                             where e.id_caso = b.id_caso and e.banda = coalesce(i.banda, b.banda)
                             order by e.recibida_en limit 1) d on true""").fetchall()
    bloqueo_real = {}
    for d in disparos:
        if d["fecha_disparo"] is None:
            continue
        momento = d["fecha_disparo"] + timedelta(seconds=float(d["segundos_reales"] or 0))
        bloqueo_real[d["id_cuenta"]] = min(momento, bloqueo_real.get(d["id_cuenta"], momento))
    perdido_m3_real = sum(c["monto"] for c in tx if c["fraude"] and (
        c["id_cuenta"] not in bloqueo_real or c["fecha_hora"] <= bloqueo_real[c["id_cuenta"]]))
    compras_por_tarjeta_real = [sum(1 for c in por_tarjeta[k] if c["fraude"] and (
        k not in bloqueo_real or c["fecha_hora"] <= bloqueo_real[k])) for k in {t["id_cuenta"] for t in tx if t["fraude"]}]
    segundos_reales = [float(d["segundos_reales"]) for d in disparos if d["segundos_reales"] is not None]

    # Bloqueos por tarjeta contra la etiqueta.
    tarjetas_fraude = {t["id_cuenta"] for t in tx if t["fraude"]}
    bloqueadas = defaultdict(set)
    for b in bloqueos:
        bloqueadas[b["actor"]].add(b["id_cuenta"])
    todas_bloqueadas = set().union(*bloqueadas.values()) if bloqueadas else set()
    verdaderas = todas_bloqueadas & tarjetas_fraude
    fraudes_por_tarjeta_aprobados = [sum(1 for c in por_tarjeta[k] if c["fraude"] and c["decision"] == "aprobada")
                                     for k in tarjetas_fraude]

    # Prueba de necesidad: qué hizo el agente en la banda alta, contra la etiqueta del caso.
    fraude_por_caso = defaultdict(int)
    for t in tx:
        if t["id_caso"]:
            fraude_por_caso[t["id_caso"]] += t["fraude"]
    tarea_caso = {t["tarea_id"]: t["id_caso"] for t in tareas}
    banda_inicio, accion_tarea = {}, {}
    for fila in trazas:
        if fila["tipo"] == "inicio":
            banda_inicio[fila["tarea_id"]] = fila["detalle"].get("banda")
        elif fila["tipo"] == "accion_triaje":
            accion_tarea[fila["tarea_id"]] = (fila["detalle"].get("accion"), fila["detalle"].get("resultado"))
        elif fila["tipo"] == "respaldo_triaje" and fila["tarea_id"] not in accion_tarea:
            accion_tarea[fila["tarea_id"]] = (fila["detalle"].get("accion"), fila["detalle"].get("resultado"))
    alta = {"agente_bloquea": [0, 0], "agente_verifica": [0, 0], "agente_deja": [0, 0], "otra": [0, 0]}  # [con fraude, sin fraude]
    for tarea_id, banda in banda_inicio.items():
        if banda != "alta":
            continue
        accion, resultado = accion_tarea.get(tarea_id, (None, None))
        clave = ("agente_bloquea" if accion in ("bloquear_tarjeta", "bloquear_acceso_cuenta") and resultado == "bloqueada"
                 else "agente_verifica" if accion == "solicitar_verificacion"
                 else "agente_deja" if accion == "dejar_a_analista" else "otra")
        alta[clave][0 if fraude_por_caso.get(tarea_caso[tarea_id], 0) else 1] += 1
    con_fraude_alta = sum(v[0] for v in alta.values())
    sin_fraude_alta = sum(v[1] for v in alta.values())
    tp, fp = alta["agente_bloquea"]

    n = len(tx)
    resultado = {
        "fecha": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "transacciones": n, "compras_fraudulentas": sum(t["fraude"] for t in tx), "tarjetas_con_fraude": len(tarjetas_fraude),
        "decision_ms": {"puntuacion_mediana": percentil([t["latencia_puntuacion_ms"] for t in tx], 0.5),
                        "puntuacion_p99": percentil([t["latencia_puntuacion_ms"] for t in tx], 0.99),
                        "camino_completo_mediana": percentil([t["latencia_total_ms"] for t in tx], 0.5),
                        "camino_completo_p99": percentil([t["latencia_total_ms"] for t in tx], 0.99)},
        "casos_por_banda": {b: sum(1 for c in casos if c["banda"] == b) for b in ("media", "alta", "critica")},
        "bloqueos_por_actor": {actor: len(ids) for actor, ids in bloqueadas.items()},
        "segundos_hasta_bloqueo": {"mediana": percentil([b["segundos_hasta_bloqueo"] for b in bloqueos], 0.5),
                                   "p95": percentil([b["segundos_hasta_bloqueo"] for b in bloqueos], 0.95),
                                   "maximo": percentil([b["segundos_hasta_bloqueo"] for b in bloqueos], 1.0)},
        "dinero_usd_a_tiempo_real": {
            "fraude_total": round(total_fraude, 2),
            "m3_fraude_que_pasa": round(perdido_m3_real, 2),
            "m3_porcentaje_detenido": round(100 * (1 - perdido_m3_real / total_fraude), 1) if total_fraude else None,
            **{f"{k}_fraude_que_pasa": round(v, 2) for k, v in perdido_m2.items()},
            **{f"{k}_porcentaje_detenido": round(100 * (1 - v / total_fraude), 1) if total_fraude else None
               for k, v in perdido_m2.items()},
            "segundos_reales_desde_la_compra_hasta_el_bloqueo": {
                "mediana": percentil(segundos_reales, 0.5), "maximo": percentil(segundos_reales, 1.0)},
            "compras_fraudulentas_que_pasan_por_tarjeta_robada": {
                "mediana": statistics.median(compras_por_tarjeta_real) if compras_por_tarjeta_real else None,
                "maximo": max(compras_por_tarjeta_real, default=None)}},
        "artefacto_simulacion_acelerada": {
            "nota": "a 3600x cada segundo real son 1 h del dataset: el triaje (~5 s) deja pasar horas de compras. "
                    "No es una cifra del sistema; se deja para mostrar por qué se mide a tiempo real.",
            "fraude_que_paso_medido": round(fraude_pasado, 2),
            "compras_legitimas_rechazadas_usd": round(legitimo_rechazado, 2),
            "compras_fraudulentas_aprobadas_por_tarjeta_robada_mediana":
                statistics.median(fraudes_por_tarjeta_aprobados) if fraudes_por_tarjeta_aprobados else None},
        "bloqueos_por_tarjeta": {"bloqueadas": len(todas_bloqueadas), "con_fraude": len(verdaderas),
                                 "precision": round(len(verdaderas) / len(todas_bloqueadas), 3) if todas_bloqueadas else None,
                                 "recall": round(len(verdaderas) / len(tarjetas_fraude), 3) if tarjetas_fraude else None,
                                 "falsos_por_1000_compras": round(1000 * len(todas_bloqueadas - tarjetas_fraude) / n, 2) if n else None},
        "prueba_de_necesidad_banda_alta": {
            "triajes_en_banda_alta": con_fraude_alta + sin_fraude_alta, "con_fraude": con_fraude_alta,
            "detalle_[con_fraude,sin_fraude]": alta,
            "agente_precision_al_bloquear": round(tp / (tp + fp), 3) if tp + fp else None,
            "agente_recall_al_bloquear": round(tp / con_fraude_alta, 3) if con_fraude_alta else None,
            "regla_siempre_bloquear_precision": round(con_fraude_alta / (con_fraude_alta + sin_fraude_alta), 3)
            if con_fraude_alta + sin_fraude_alta else None},
        "llm": {"triajes": len(tareas), "costo_total_usd": round(sum(t["costo"] or 0 for t in tareas), 4),
                "costo_por_triaje_usd": round(statistics.mean(t["costo"] or 0 for t in tareas), 5) if tareas else None,
                "costo_por_1000_compras_usd": round(1000 * sum(t["costo"] or 0 for t in tareas) / n, 4) if n else None,
                "latencia_triaje_ms_mediana": percentil([t["latencia_ms"] for t in tareas], 0.5),
                "motivo_fin": {m: sum(1 for t in tareas if t["motivo_fin"] == m) for m in {t["motivo_fin"] for t in tareas}},
                "proveedor": {p: sum(1 for t in tareas if t["proveedor_final"] == p) for p in {t["proveedor_final"] for t in tareas}},
                "con_reintento_o_conmutacion": sum(1 for t in tareas if (t["reintentos"] or 0) + (t["conmutaciones"] or 0) > 0)},
        "avisos": {"total": len(avisos), "motivo_del_agente": sum(1 for a in avisos if a["autor_motivo"] == "agente"),
                   "motivo_de_plantilla": sum(1 for a in avisos if a["autor_motivo"] == "plantilla"),
                   "rechazados_por_validacion": sum(1 for a in avisos if a["errores_validacion"])},
    }
    return resultado


def carpeta_de_resultados() -> str:
    """eval/resultados si se puede escribir; si no (dentro del contenedor la app no es dueña de
    /srv/eval), /tmp/resultados. Para traerlo: docker compose cp app:/tmp/resultados/. eval/resultados/"""
    for carpeta in (os.path.join(RAIZ, "eval", "resultados"), "/tmp/resultados"):
        try:
            os.makedirs(carpeta, exist_ok=True)
            if os.access(carpeta, os.W_OK):
                return carpeta
        except OSError:
            continue
    raise SystemExit("No hay una carpeta con permiso de escritura para los resultados.")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    argumentos = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    argumentos.add_argument("--nombre", default="base")
    argumentos.add_argument("--falla", default="", choices=["", "429", "timeout", "json", "todo"])
    argumentos.add_argument("--velocidad", type=int, default=3600)
    argumentos.add_argument("--espera-maxima", type=float, default=1800)
    argumentos.add_argument("--sin-esperar-triajes", action="store_true",
                            help="método anterior al 2026-11-14: el reloj del dataset sigue corriendo durante "
                                 "cada triaje y el agente alcanza a ver compras que en tiempo real no existían")
    argumentos.add_argument("--solo-calcular", action="store_true",
                            help="no reproduce la noche: recalcula las cifras con lo que ya está en la base")
    opciones = argumentos.parse_args()
    if opciones.solo_calcular:
        return guardar(opciones)

    print("1. Reiniciando los datos en vivo…")
    migrar.reiniciar_en_vivo()
    clave = preparar_evaluador()
    iniciar_sesion(URL, "evaluador", clave)
    enviar_json(f"{URL}/api/demo/falla", {"tipo": opciones.falla or None})
    enviar_json(f"{URL}/api/ajustes", {"clave": "autonomia_agente", "valor": True})
    enviar_json(f"{URL}/api/ajustes", {"clave": "tope_bloqueos_autonomos_por_hora", "valor": 500})
    esperar_triajes = not opciones.sin_esperar_triajes
    print(f"2. Reproduciendo la noche a {opciones.velocidad}x (falla forzada: {opciones.falla or 'ninguna'}; "
          f"reloj detenido durante cada triaje: {'sí' if esperar_triajes else 'no'})…")
    inicio = time.monotonic()
    enviar_json(f"{URL}/api/simulador/iniciar", {"velocidad": opciones.velocidad, "esperar_triajes": esperar_triajes})
    esperar_fin(opciones.espera_maxima)
    enviar_json(f"{URL}/api/demo/falla", {"tipo": None})
    enviar_json(f"{URL}/api/ajustes", {"clave": "tope_bloqueos_autonomos_por_hora", "valor": 30})
    print(f"3. Listo en {time.monotonic() - inicio:.0f} s. Calculando cifras…")
    guardar(opciones)


def guardar(opciones):

    from app.riesgo.motor_en_vivo import motor
    resultado = {"nombre": opciones.nombre, "falla_forzada": opciones.falla or None, "velocidad": opciones.velocidad,
                 "reloj_detenido_durante_triajes": not getattr(opciones, "sin_esperar_triajes", False),
                 "modelo_llm": config.CLAUDE_MODELO if "claude" in config.ORDEN_PROVEEDORES[:1] else config.GEMINI_MODELO,
                 **calcular(motor().umbral_bloqueo)}
    carpeta = carpeta_de_resultados()
    ruta = os.path.join(carpeta, f"momento3_{datetime.now():%Y-%m-%d_%H%M}_{opciones.nombre}.json")
    with open(ruta, "w", encoding="utf-8") as archivo:
        json.dump(resultado, archivo, ensure_ascii=False, indent=2, default=str)
    print(json.dumps(resultado, ensure_ascii=False, indent=2, default=str))
    print(f"\nGuardado en {ruta}")
    with dueno() as con:   # el usuario de la evaluación no queda utilizable
        con.execute("update usuarios set activo = false where usuario = 'evaluador'")
        con.execute("update sesiones set cerrada = true where usuario = 'evaluador'")


if __name__ == "__main__":
    main()
