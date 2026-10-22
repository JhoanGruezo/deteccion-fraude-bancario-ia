"""Genera las gráficas de la documentación (docs/img/graficas/) desde los datos reales.

Existe para que cada imagen del README y de la guía sea reproducible y coherente con
las cifras de docs/decisiones.md: nada se dibuja a mano, todo sale de los mismos
archivos que usa el proyecto.

- Sin el dataset de Kaggle: se generan las gráficas que salen de semilla/ y eval/
  (cifras clave, comparación de modelos, calidad por caso, latencia del lote).
- Con datos/fraudTrain.csv y fraudTest.csv: además, la distribución horaria del fraude
  y la curva precisión-recall del modelo frente a la regla de umbral fijo.

Uso, desde la raíz:  python scripts/generar_graficas.py

Colores: paleta categórica de referencia en modo claro (GitHub muestra las imágenes
sobre fondo claro), validada con el validador de la skill de visualización: azul,
naranja, aguamarina y amarillo pasan las pruebas de daltonismo entre vecinos; el
aguamarina y el amarillo tienen poco contraste con el fondo, por eso toda barra lleva
su valor escrito.
"""

import glob
import json
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SALIDA = os.path.join(RAIZ, "docs", "img", "graficas")

SUPERFICIE = "#fcfcfb"
TEXTO = "#0b0b0b"
TEXTO_SECUNDARIO = "#52514e"
REJILLA = "#e4e3df"
NEUTRO = "#a3a29c"         # referencia o "resto": nunca compite con una serie
AZUL, NARANJA, AGUAMARINA, AMARILLO = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"

plt.rcParams.update({
    "figure.facecolor": SUPERFICIE, "axes.facecolor": SUPERFICIE, "savefig.facecolor": SUPERFICIE,
    "font.size": 11, "axes.edgecolor": REJILLA, "axes.labelcolor": TEXTO_SECUNDARIO,
    "xtick.color": TEXTO_SECUNDARIO, "ytick.color": TEXTO_SECUNDARIO, "text.color": TEXTO,
    "axes.spines.top": False, "axes.spines.right": False,
})


def es(numero, decimales=1):
    """1234.5 -> '1.234,5': las gráficas hablan en formato colombiano, como la app."""
    texto = f"{numero:,.{decimales}f}"
    return texto.replace(",", "§").replace(".", ",").replace("§", ".")


EJE_COMA = FuncFormatter(lambda valor, _: es(valor, 1))


def titulo(figura, principal, secundario):
    figura.text(0.01, 0.98, principal, fontsize=14, fontweight="bold", va="top")
    figura.text(0.01, 0.91, secundario, fontsize=10, color=TEXTO_SECUNDARIO, va="top")


def guardar(figura, nombre):
    os.makedirs(SALIDA, exist_ok=True)
    ruta = os.path.join(SALIDA, nombre)
    figura.savefig(ruta, dpi=150)
    plt.close(figura)
    print(f"  {os.path.relpath(ruta, RAIZ)}")


def leer_json(ruta):
    with open(os.path.join(RAIZ, ruta), encoding="utf-8") as archivo:
        return json.load(archivo)


# ---------------------------------------------------------------------------------
# Gráficas que salen de semilla/ y eval/ (siempre se pueden generar)
# ---------------------------------------------------------------------------------

def cifras_clave(lote, metricas):
    """Las cuatro cifras de la línea base y la del motor, como tarjetas: un titular no es una gráfica."""
    cifras = lote["cifras"]
    tarjetas = [
        (es(metricas['prueba']['gradient_boosting']['auc_pr'], 3), "AUC-PR del motor", "regla de umbral fijo: " + es(metricas["prueba"]["regla_umbral_fijo"]["auc_pr"], 3)),
        (f"{es(100 * cifras['tasa_exito']['valor'], 1)} %", "éxito del agente", f"{cifras['tasa_exito']['exitos']} de {cifras['tasa_exito']['tareas']} tareas del lote"),
        (f"{es(cifras['costo_por_tarea']['mediana_usd'], 4)} USD", "costo mediano por tarea", "tarifa de lista, sin caché"),
        (f"{es(cifras['latencia']['mediana_ms'] / 1000, 1)} s", "latencia mediana", f"P90 {es(cifras['latencia']['p90_ms'] / 1000, 1)} s · caché {int(cifras['ahorro_cache']['latencia_mediana_cache_ms'])} ms"),
        (f"{es(100 * cifras['recuperacion']['valor'], 0)} %", "recuperación ante fallas", "429, timeout, JSON y caída total"),
    ]
    figura = plt.figure(figsize=(12, 2.6))
    titulo(figura, "Línea base del proyecto", f"Medida el {lote['fecha'][:10]} sobre datos reales (Sparkov) y con el agente en vivo")
    for i, (valor, etiqueta, nota) in enumerate(tarjetas):
        x = 0.01 + i * 0.198
        figura.patches.append(plt.Rectangle((x, 0.06), 0.185, 0.68, transform=figura.transFigure,
                                            facecolor="#f3f2ef", edgecolor=REJILLA, linewidth=1))
        figura.text(x + 0.012, 0.56, valor, fontsize=20, fontweight="bold", va="center")
        figura.text(x + 0.012, 0.33, etiqueta, fontsize=10.5, va="center")
        figura.text(x + 0.012, 0.17, nota, fontsize=8.5, color=TEXTO_SECUNDARIO, va="center")
    guardar(figura, "00-cifras-clave.png")


def comparacion_modelos(metricas):
    """F1 y AUC-PR de los modelos frente a la regla: la prueba de necesidad en una imagen."""
    prueba = metricas["prueba"]
    series = [
        ("Regla de umbral fijo", "regla_umbral_fijo", NEUTRO),
        ("Regresión logística", "regresion_logistica", AGUAMARINA),
        ("Random Forest", "random_forest", NARANJA),
        ("HistGradientBoosting (elegido)", "gradient_boosting", AZUL),
    ]
    medidas = [("F1", "f1"), ("AUC-PR", "auc_pr")]
    figura, eje = plt.subplots(figsize=(10, 5.2))
    figura.subplots_adjust(top=0.78, bottom=0.10, left=0.07, right=0.98)
    ancho = 0.19
    for i, (nombre, clave, color) in enumerate(series):
        posiciones = [m + (i - 1.5) * ancho for m in range(len(medidas))]
        valores = [prueba[clave][c] for _, c in medidas]
        eje.bar(posiciones, valores, width=ancho, color=color, edgecolor=SUPERFICIE, linewidth=2, label=nombre)
        for x, v in zip(posiciones, valores):
            eje.text(x, v + 0.015, es(v, 2), ha="center", va="bottom", fontsize=9.5)
    eje.set_xticks(range(len(medidas)), [n for n, _ in medidas], fontsize=11)
    eje.set_ylim(0, 1)
    eje.yaxis.set_major_formatter(EJE_COMA)
    eje.set_ylabel("puntaje (0 a 1)")
    eje.yaxis.grid(True, color=REJILLA, linewidth=0.8)
    eje.set_axisbelow(True)
    eje.legend(frameon=False, ncol=2, loc="upper left", fontsize=9.5)
    tramo = metricas["tramos"]["prueba"]
    titulo(figura, f"El modelo alcanza F1 {es(prueba['gradient_boosting']['f1'], 2)}; la regla de umbral fijo, {es(prueba['regla_umbral_fijo']['f1'], 2)}",
           f"Tramo de prueba de Sparkov ({tramo['desde'][:10]} a {tramo['hasta'][:10]}), {es(tramo['filas'], 0)} transacciones, "
           f"{es(tramo['porcentaje_fraude'], 2)} % de fraude.\n"
           "La regla marca casi todo el fraude (recall 0,84), pero solo el 1,4 % de sus alertas son fraude.")
    guardar(figura, "01-modelos-vs-regla.png")


def calidad_por_caso(casos_sparkov, casos_sinteticos):
    """Lo que ve el analista: cuántos casos de cada nivel traen fraude confirmado."""
    etiquetas = {"bloquear_tarjeta": "Bloquear tarjeta", "verificar_cliente": "Verificar con el cliente",
                 "bloquear_acceso_cuenta": "Bloquear acceso a la cuenta"}
    filas = []
    for fuente, casos in [("Sparkov", casos_sparkov), ("sintéticos", casos_sinteticos)]:
        for nivel in ["bloquear_tarjeta", "verificar_cliente", "bloquear_acceso_cuenta"]:
            del_nivel = [c for c in casos if c["nivel_recomendacion"] == nivel]
            if del_nivel:
                con = sum(1 for c in del_nivel if c["fraude_confirmado_dataset"] > 0)
                filas.append((f"{etiquetas[nivel]} · {fuente}", con, len(del_nivel) - con))
    filas.reverse()
    figura, eje = plt.subplots(figsize=(10, 4.4))
    figura.subplots_adjust(top=0.76, bottom=0.12, left=0.33, right=0.97)
    y = range(len(filas))
    con = [f[1] for f in filas]
    sin = [f[2] for f in filas]
    eje.barh(y, con, height=0.55, color=AZUL, edgecolor=SUPERFICIE, linewidth=2, label="con fraude confirmado")
    eje.barh(y, sin, left=con, height=0.55, color=NEUTRO, edgecolor=SUPERFICIE, linewidth=2, label="sin fraude confirmado")
    for i, (nombre, c, s) in enumerate(filas):
        total = c + s
        eje.text(total + 3, i, f"{c} de {total} ({es(100 * c / total, 1)} %)", va="center", fontsize=9.5)
    eje.set_yticks(list(y), [f[0] for f in filas])
    eje.set_xlabel("casos")
    eje.set_xlim(0, max(c + s for _, c, s in filas) * 1.32)
    eje.xaxis.grid(True, color=REJILLA, linewidth=0.8)
    eje.set_axisbelow(True)
    eje.legend(frameon=False, loc="lower right", fontsize=9.5)
    bloqueo = next(f for f in filas if f[0].startswith("Bloquear tarjeta · Sparkov"))
    titulo(figura, f"{es(100 * bloqueo[1] / (bloqueo[1] + bloqueo[2]), 0)} % de los casos de bloqueo en datos reales tienen fraude confirmado",
           "Casos que llegan a la bandeja del analista, por nivel de recomendación. Un caso agrupa las compras marcadas de una tarjeta en 48 h.")
    guardar(figura, "03-calidad-por-caso.png")


def latencia_lote(lote):
    """Latencia de cada tarea del lote de medición: caché, frío, preguntas y fallas forzadas."""
    def tipo_de(r):
        if r["falla_pedida"]:
            return "falla forzada", AMARILLO
        if r["metricas"]["desde_cache"]:
            return "desde caché", NARANJA
        if r["tipo"] == "pregunta":
            return "pregunta al agente", AGUAMARINA
        return "explicación en frío", AZUL

    resultados = list(reversed(lote["resultados"]))
    figura, eje = plt.subplots(figsize=(10, 7.4))
    figura.subplots_adjust(top=0.80, bottom=0.07, left=0.20, right=0.97)
    vistos = set()
    for i, r in enumerate(resultados):
        nombre, color = tipo_de(r)
        ms = r["metricas"]["latencia_cliente_ms"]
        eje.barh(i, ms / 1000, height=0.62, color=color, edgecolor=SUPERFICIE, linewidth=2,
                 label=None if nombre in vistos else nombre)
        vistos.add(nombre)
        texto = f"{ms} ms" if ms < 1000 else f"{es(ms / 1000, 1)} s"
        if r["falla_pedida"]:
            texto += f" · {r['falla_pedida']} → {r['metricas']['proveedor_final'] or 'plantilla'}"
        eje.text(ms / 1000 * 1.08, i, texto, va="center", fontsize=8.5)
    eje.set_xscale("log")
    eje.set_xlim(0.01, 400)
    eje.set_xticks([0.01, 0.1, 1, 10], ["10 ms", "100 ms", "1 s", "10 s"])
    eje.set_yticks(range(len(resultados)), [f"{r['id']} · {r['dorado']} · {r['id_caso']}" for r in resultados], fontsize=8.5)
    eje.xaxis.grid(True, color=REJILLA, linewidth=0.8)
    eje.set_axisbelow(True)
    eje.legend(frameon=False, loc="lower left", bbox_to_anchor=(0, 1.0), ncol=4, fontsize=9)
    ahorro = lote["cifras"]["ahorro_cache"]
    titulo(figura, f"La caché responde en {int(ahorro['latencia_mediana_cache_ms'])} ms; una explicación nueva, en unos 5 s",
           "Latencia de extremo a extremo de las 19 tareas del lote de medición (escala logarítmica). Las fallas 429 y timeout\n"
           "pagan el backoff de 1 + 2 + 4 s antes de conmutar al respaldo; la caída total termina en la plantilla.")
    guardar(figura, "05-latencia-del-lote.png")


# ---------------------------------------------------------------------------------
# Gráficas que necesitan el dataset de Kaggle en datos/
# ---------------------------------------------------------------------------------

def horas_del_fraude():
    import pandas as pd

    datos = pd.read_csv(os.path.join(RAIZ, "datos", "fraudTrain.csv"), usecols=["trans_date_trans_time", "is_fraud"])
    datos["hora"] = pd.to_datetime(datos["trans_date_trans_time"]).dt.hour
    reparto = datos.groupby("is_fraud")["hora"].value_counts(normalize=True).unstack(0).sort_index() * 100
    figura, eje = plt.subplots(figsize=(10, 4.8))
    figura.subplots_adjust(top=0.78, bottom=0.12, left=0.08, right=0.86)
    for clave, nombre, color in [(0, "legítimas", AZUL), (1, "fraudulentas", NARANJA)]:
        eje.plot(reparto.index, reparto[clave], color=color, linewidth=2, marker="o", markersize=4, label=nombre)
        eje.text(23.4, reparto[clave].iloc[-1], nombre, color=TEXTO, va="center", fontsize=9.5)
    eje.set_xticks(range(0, 24, 2), [f"{h} h" for h in range(0, 24, 2)])
    eje.set_ylabel("% de las transacciones de su tipo")
    eje.yaxis.grid(True, color=REJILLA, linewidth=0.8)
    eje.set_axisbelow(True)
    eje.legend(frameon=False, loc="upper center", fontsize=9.5)
    noche_fraude = reparto.loc[[22, 23, 0, 1, 2, 3], 1].sum()
    noche_legitima = reparto.loc[[22, 23, 0, 1, 2, 3], 0].sum()
    titulo(figura, f"El {es(noche_fraude, 0)} % del fraude ocurre entre las 22 h y las 3 h, frente al {es(noche_legitima, 0)} % de las compras legítimas",
           "Sparkov, tramo de entrenamiento (1,3 millones de transacciones). La hora ayuda, pero sola no alcanza: por eso el modelo\n"
           "la combina con el monto y el ritmo de cada tarjeta frente a su propio pasado.")
    guardar(figura, "04-hora-del-fraude.png")


def curva_precision_recall(metricas):
    import joblib
    from sklearn.metrics import precision_recall_curve

    sys.path.insert(0, os.path.join(RAIZ, "src"))
    from cargar_datos import cargar_sparkov
    from motor_riesgo import dividir_temporal
    from perfil_cuenta import agregar_features

    paquete = joblib.load(os.path.join(RAIZ, "datos", "salidas_sparkov", "modelo_riesgo.joblib"))
    datos, _ = agregar_features(cargar_sparkov(os.path.join(RAIZ, "datos", "fraudTrain.csv"),
                                               os.path.join(RAIZ, "datos", "fraudTest.csv")))
    _, _, prueba = dividir_temporal(datos, "sparkov")
    score = paquete["modelo"].predict_proba(prueba[paquete["features"]])[:, 1]
    precision, recall, umbrales = precision_recall_curve(prueba["es_fraude"], score)

    figura, eje = plt.subplots(figsize=(8.5, 6))
    figura.subplots_adjust(top=0.82, bottom=0.11, left=0.10, right=0.96)
    eje.plot(recall, precision, color=AZUL, linewidth=2, label=f"HistGradientBoosting (AUC-PR {es(metricas['prueba']['gradient_boosting']['auc_pr'], 3)})")
    regla = metricas["prueba"]["regla_umbral_fijo"]
    eje.plot(regla["recall"], regla["precision"], "o", color=NEUTRO, markersize=9,
             markeredgecolor=TEXTO_SECUNDARIO, label="regla de umbral fijo")
    eje.annotate(f"regla: recall {es(regla['recall'], 2)},\nprecisión {es(regla['precision'], 3)}",
                 (regla["recall"], regla["precision"]), xytext=(0.52, 0.18), fontsize=9.5,
                 arrowprops={"arrowstyle": "-", "color": TEXTO_SECUNDARIO})
    elegido = metricas["prueba"]["gradient_boosting"]
    eje.plot(elegido["recall"], elegido["precision"], "o", color=AZUL, markersize=9, markeredgecolor=SUPERFICIE)
    eje.annotate(f"umbral de bloqueo ({es(paquete['umbral_bloqueo'], 3)}):\nrecall {es(elegido['recall'], 2)}, precisión {es(elegido['precision'], 2)}",
                 (elegido["recall"], elegido["precision"]), xytext=(0.12, 0.55), fontsize=9.5,
                 arrowprops={"arrowstyle": "-", "color": TEXTO_SECUNDARIO})
    eje.set_xlabel("recall (fraude detectado)")
    eje.set_ylabel("precisión (alertas que eran fraude)")
    eje.set_xlim(0, 1.02)
    eje.set_ylim(0, 1.02)
    eje.xaxis.set_major_formatter(EJE_COMA)
    eje.yaxis.set_major_formatter(EJE_COMA)
    eje.grid(True, color=REJILLA, linewidth=0.8)
    eje.legend(frameon=False, loc="lower left", fontsize=9.5)
    titulo(figura, "A igual recall, el modelo es decenas de veces más preciso",
           "Curva precisión-recall del modelo elegido en el tramo de prueba de Sparkov, frente al punto de la regla de umbral fijo.")
    guardar(figura, "02-curva-precision-recall.png")


def main():
    metricas = leer_json("semilla/metricas_sparkov.json")
    lote = leer_json(os.path.relpath(sorted(glob.glob(os.path.join(RAIZ, "eval", "resultados", "lote_*.json")))[-1], RAIZ))
    print("Gráficas desde semilla/ y eval/:")
    cifras_clave(lote, metricas)
    comparacion_modelos(metricas)
    calidad_por_caso(leer_json("semilla/casos_sparkov.json"), leer_json("semilla/casos_sinteticos.json"))
    latencia_lote(lote)

    if os.path.exists(os.path.join(RAIZ, "datos", "fraudTrain.csv")):
        print("Gráficas desde el dataset de Kaggle (datos/):")
        horas_del_fraude()
        if os.path.exists(os.path.join(RAIZ, "datos", "salidas_sparkov", "modelo_riesgo.joblib")):
            curva_precision_recall(metricas)
    else:
        print("Sin datos/fraudTrain.csv: se omiten la gráfica de horas y la curva precisión-recall "
              "(las versiones ya generadas siguen en docs/img/graficas/).")


if __name__ == "__main__":
    main()
