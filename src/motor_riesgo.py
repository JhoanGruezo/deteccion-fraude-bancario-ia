"""Motor de riesgo: partición temporal, comparación de modelos, umbrales y casos.

Convierte transacciones con features de perfil previo (perfil_cuenta.py) en casos
que un analista puede revisar sin interpretar un número: cada caso agrupa las
transacciones marcadas de una tarjeta en una ventana de 48 h y trae el score, las
desviaciones contra el perfil previo con cifras reales y una recomendación de
bloqueo decidida por regla determinista (decisiones.md, "Actualización
2026-10-21"). El LLM de la vista del analista solo redacta sobre esta evidencia.

La comparación contra la regla de umbral fijo sigue siendo la evidencia numérica de
la prueba de necesidad: se reporta lado a lado en el tramo de prueba.
"""

import json
import os
from datetime import datetime

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, f1_score, precision_recall_curve, precision_score, recall_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from perfil_cuenta import perfil_al_momento

VENTANA_CASO = pd.Timedelta(hours=48)  # las ráfagas de fraude de Sparkov duran ~45 h
INICIO_VALIDACION_SPARKOV = pd.Timestamp("2020-03-21")  # últimos 3 meses de fraudTrain
PROPORCION_NORMALES_ENTRENAMIENTO = 0.2
SEMILLA = 7
MINIMO_TRANSACCIONES_BLOQUEO = 2  # dos o más compras sobre el umbral de bloqueo en 48 h se bloquean
MINIMO_TRANSACCIONES_CASO = 2  # con menos transacciones marcadas no se abre caso (salvo viaje imposible)
PERCENTIL_RELEVANTE = 90
CONTRIBUCION_RELEVANTE = 0.05
TAMANO_REFERENCIA = 50_000  # muestra de transacciones normales para los percentiles

# Qué features forman cada señal (para la oclusión) y cuál es su valor principal con
# su dirección de riesgo (+1: más alto es más raro; -1: más bajo es más raro).
GRUPOS_SENAL = {
    "monto": ["monto", "z_monto", "razon_monto"],
    "hora": ["hora", "frecuencia_hora_previa"],
    "ritmo_24h": ["conteo_24h_previo", "tasa_diaria_previa"],
    "monto_24h": ["monto_24h_previo"],
    "categoria": ["frecuencia_categoria_previa"],
    "distancia": ["distancia_domicilio_km", "distancia_vs_habitual_km"],
    "ubicacion": ["frecuencia_ubicacion_previa"],
    "historial": ["sin_historial"],
}
VALOR_PRINCIPAL = {
    "monto": ("razon_monto", 1),
    "hora": ("frecuencia_hora_previa", -1),
    "ritmo_24h": ("conteo_24h_previo", 1),
    "monto_24h": ("monto_24h_previo", 1),
    "categoria": ("frecuencia_categoria_previa", -1),
    "distancia": ("distancia_vs_habitual_km", 1),
    "ubicacion": ("frecuencia_ubicacion_previa", -1),
    "historial": ("sin_historial", 1),
}


# ---------------------------------------------------------------------------
# Partición y entrenamiento
# ---------------------------------------------------------------------------

def dividir_temporal(datos, fuente):
    """Entrenamiento < validación < prueba, siempre por fecha (nunca al azar)."""
    if fuente == "sparkov":
        es_prueba = datos["tramo_origen"] == "prueba"
        es_validacion = ~es_prueba & (datos["fecha_hora"] >= INICIO_VALIDACION_SPARKOV)
    else:
        corte_validacion = datos["fecha_hora"].quantile(0.6)
        corte_prueba = datos["fecha_hora"].quantile(0.8)
        es_prueba = datos["fecha_hora"] >= corte_prueba
        es_validacion = ~es_prueba & (datos["fecha_hora"] >= corte_validacion)
    es_entrenamiento = ~es_prueba & ~es_validacion
    return datos[es_entrenamiento], datos[es_validacion], datos[es_prueba]


def submuestrear_entrenamiento(entrenamiento, proporcion_normales=PROPORCION_NORMALES_ENTRENAMIENTO, semilla=SEMILLA):
    """Todo el fraude + una fracción de las normales, solo para entrenar más rápido.

    Los umbrales se eligen sobre la validación completa, así que esto no sesga los
    cortes; queda registrado en metricas_motor.json.
    """
    fraude = entrenamiento[entrenamiento["es_fraude"] == 1]
    normales = entrenamiento[entrenamiento["es_fraude"] == 0].sample(frac=proporcion_normales, random_state=semilla)
    return pd.concat([fraude, normales]).sort_index()


def entrenar_modelos(entrenamiento, features):
    modelos = {
        "regresion_logistica": make_pipeline(
            StandardScaler(), LogisticRegression(class_weight="balanced", max_iter=1000)
        ),
        "random_forest": RandomForestClassifier(
            n_estimators=200, max_depth=12, min_samples_leaf=20,
            class_weight="balanced_subsample", n_jobs=-1, random_state=SEMILLA,
        ),
        "gradient_boosting": HistGradientBoostingClassifier(class_weight="balanced", random_state=SEMILLA),
    }
    for modelo in modelos.values():
        modelo.fit(entrenamiento[features], entrenamiento["es_fraude"])
    return modelos


def regla_umbral_fijo(datos, umbral_monto):
    """La idea original: monto alto (percentil 95 del ENTRENAMIENTO) o madrugada."""
    return ((datos["monto"] > umbral_monto) | (datos["hora"] < 6)).astype(int)


def metricas(y, prediccion, score=None):
    score = prediccion if score is None else score
    return {
        "precision": round(float(precision_score(y, prediccion, zero_division=0)), 4),
        "recall": round(float(recall_score(y, prediccion, zero_division=0)), 4),
        "f1": round(float(f1_score(y, prediccion, zero_division=0)), 4),
        "auc_pr": round(float(average_precision_score(y, score)), 4),
    }


def elegir_modelo(modelos, validacion, features):
    puntajes = {
        nombre: average_precision_score(validacion["es_fraude"], modelo.predict_proba(validacion[features])[:, 1])
        for nombre, modelo in modelos.items()
    }
    return max(puntajes, key=puntajes.get)


def elegir_umbrales(y_validacion, score_validacion):
    """Bloqueo: mejor F1. Verificación: mejor F2 (pesa el recall el doble).

    Devuelve (umbral_verificacion, umbral_bloqueo, aviso). Si la validación no tiene
    fraude, no hay curva que barrer: se usa 0,5 y se deja el aviso.
    """
    if y_validacion.sum() == 0:
        return 0.5, 0.5, "La validación no tiene fraude; se usó 0,5 para ambos umbrales."
    precision, recall, umbrales = precision_recall_curve(y_validacion, score_validacion)
    precision, recall = precision[:-1], recall[:-1]
    with np.errstate(divide="ignore", invalid="ignore"):
        f1 = np.nan_to_num(2 * precision * recall / (precision + recall))
        f2 = np.nan_to_num(5 * precision * recall / (4 * precision + recall))
    umbral_bloqueo = float(umbrales[np.argmax(f1)])
    umbral_verificacion = float(umbrales[np.argmax(f2)])
    aviso = None
    if umbral_verificacion > umbral_bloqueo:
        umbral_verificacion = umbral_bloqueo
        aviso = "El umbral de verificación salió mayor que el de bloqueo; se igualaron."
    return umbral_verificacion, umbral_bloqueo, aviso


# ---------------------------------------------------------------------------
# Casos, desviaciones y recomendación
# ---------------------------------------------------------------------------

def formato_es(numero, decimales=1):
    """1234.5 -> '1.234,5' (los textos que lee el analista van con coma decimal)."""
    texto = f"{numero:,.{decimales}f}"
    return texto.replace(",", "§").replace(".", ",").replace("§", ".")


def _cuantificador(porcentaje):
    """'solo el' tiene sentido para algo raro; para un 35 % basta 'el'."""
    return "solo el" if porcentaje < 20 else "el"


def preparar_referencias(entrenamiento, features, semilla=SEMILLA):
    """Medianas y distribuciones de las transacciones NORMALES del entrenamiento.

    Las medianas son el "valor típico" con el que se ocluye cada señal; las
    distribuciones dan el percentil de rareza. Se guardan en el .joblib para que la
    vista del analista explique cualquier caso con la misma vara.
    """
    normales = entrenamiento[entrenamiento["es_fraude"] == 0]
    muestra = normales.sample(n=min(TAMANO_REFERENCIA, len(normales)), random_state=semilla)
    return {
        "medianas": {f: float(normales[f].median()) for f in features},
        "distribuciones": {f: np.sort(muestra[f].to_numpy(dtype="float64")) for f in features},
    }


def percentil_rareza(valor, distribucion, direccion):
    """Porcentaje de transacciones normales menos extremas que `valor` en la dirección de riesgo."""
    if direccion > 0:
        menores = np.searchsorted(distribucion, valor, side="left")
    else:
        menores = len(distribucion) - np.searchsorted(distribucion, valor, side="right")
    return round(100 * menores / len(distribucion), 1)


def contribuciones_por_oclusion(modelo, filas, features, medianas):
    """Cuánto baja el score de cada fila si una señal se lleva a su valor típico.

    No cambia el modelo ni el score: solo se calcula para las transacciones
    marcadas, para saber qué pesó en ESE caso.
    """
    base = modelo.predict_proba(filas[features])[:, 1]
    contribuciones = pd.DataFrame(index=filas.index)
    for senal, grupo in GRUPOS_SENAL.items():
        columnas = [c for c in grupo if c in features]
        if not columnas:
            continue
        ocluidas = filas[features].copy()
        for columna in columnas:
            ocluidas[columna] = medianas[columna]
        contribuciones[senal] = base - modelo.predict_proba(ocluidas)[:, 1]
    return contribuciones


def recomendar(tipos_fraude, score_maximo, umbral_bloqueo, n_sobre_bloqueo):
    """Regla determinista del nivel de bloqueo; gana el más severo. El humano decide."""
    if "viaje_imposible" in tipos_fraude:
        return "bloquear_acceso_cuenta", "Viaje imposible: la misma cuenta operó en dos lugares que no se pueden recorrer en ese tiempo (posible toma de control)."
    if n_sobre_bloqueo >= MINIMO_TRANSACCIONES_BLOQUEO:
        return "bloquear_tarjeta", (
            f"{n_sobre_bloqueo} transacciones en 48 h superan el umbral de bloqueo {formato_es(umbral_bloqueo, 2)} "
            f"(score máximo {formato_es(score_maximo, 2)}): compras anómalas seguidas, patrón de uso no autorizado."
        )
    if n_sobre_bloqueo == 1:
        return "verificar_cliente", (
            f"Una sola transacción supera el umbral de bloqueo (score {formato_es(score_maximo, 2)}): "
            "una compra aislada se confirma con el cliente antes de bloquear."
        )
    return "verificar_cliente", (
        f"Score {formato_es(score_maximo, 2)} entre el umbral de verificación y el de bloqueo "
        f"({formato_es(umbral_bloqueo, 2)}): confirmar con el cliente antes de bloquear."
    )


def _senales_de(fila):
    """Las señales de la transacción contra el perfil previo, con cifras para citar."""
    if fila["sin_historial"] == 1:
        return [{
            "senal": "historial",
            "valor_observado": int(fila["n_previas"]),
            "valor_referencia": None,
            "descripcion": f"Sin historial suficiente ({int(fila['n_previas'])} transacciones previas) para compararla contra un perfil habitual.",
        }]

    senales = []
    promedio = float(fila["monto_promedio_previo"])
    senales.append({
        "senal": "monto",
        "valor_observado": round(float(fila["monto"]), 2),
        "valor_referencia": round(promedio, 2),
        "descripcion": f"Monto de {formato_es(fila['monto'], 2)}: {formato_es(fila['razon_monto'])} veces su promedio previo ({formato_es(promedio, 2)}).",
    })
    frecuencia_hora = 100 * float(fila["frecuencia_hora_previa"])
    hora = int(fila["hora"])
    senales.append({
        "senal": "hora",
        "valor_observado": hora,
        "valor_referencia": round(frecuencia_hora, 1),
        "descripcion": f"{'A la' if hora == 1 else 'A las'} {hora} h: {_cuantificador(frecuencia_hora)} {formato_es(frecuencia_hora)} % de sus transacciones previas fueron a esa hora.",
    })
    tasa = float(fila["tasa_diaria_previa"])
    conteo = int(fila["conteo_24h_previo"])
    senales.append({
        "senal": "ritmo_24h",
        "valor_observado": conteo,
        "valor_referencia": round(tasa, 2),
        "descripcion": f"En las 24 h anteriores hizo {conteo} transacciones; su ritmo habitual es {formato_es(tasa, 2)} por día.",
    })
    gasto_diario = promedio * tasa
    monto_24h = float(fila["monto_24h_previo"])
    senales.append({
        "senal": "monto_24h",
        "valor_observado": round(monto_24h, 2),
        "valor_referencia": round(gasto_diario, 2),
        "descripcion": f"En las 24 h anteriores movió {formato_es(monto_24h, 2)}; su gasto diario habitual es {formato_es(gasto_diario, 2)}.",
    })
    if "frecuencia_categoria_previa" in fila.index:
        frecuencia_categoria = 100 * float(fila["frecuencia_categoria_previa"])
        senales.append({
            "senal": "categoria",
            "valor_observado": str(fila["categoria"]),
            "valor_referencia": round(frecuencia_categoria, 1),
            "descripcion": f"Categoría {fila['categoria']}: {_cuantificador(frecuencia_categoria)} {formato_es(frecuencia_categoria)} % de sus compras previas.",
        })
    if "distancia_vs_habitual_km" in fila.index:
        habitual = float(fila["distancia_promedio_previa_km"])
        senales.append({
            "senal": "distancia",
            "valor_observado": round(float(fila["distancia_domicilio_km"]), 1),
            "valor_referencia": round(habitual, 1),
            "descripcion": f"Comercio a {formato_es(fila['distancia_domicilio_km'], 0)} km de su domicilio; su distancia promedio previa es {formato_es(habitual, 0)} km.",
        })
    if "frecuencia_ubicacion_previa" in fila.index:
        frecuencia_ubicacion = 100 * float(fila["frecuencia_ubicacion_previa"])
        senales.append({
            "senal": "ubicacion",
            "valor_observado": str(fila["ubicacion"]),
            "valor_referencia": round(frecuencia_ubicacion, 1),
            "descripcion": f"En {fila['ubicacion']}: {_cuantificador(frecuencia_ubicacion)} {formato_es(frecuencia_ubicacion)} % de sus transacciones previas fueron ahí.",
        })
    return senales


def desviaciones(fila, contribucion, referencias):
    """Señales con su contribución al score y su rareza, ordenadas por contribución.

    `relevante` marca las que el LLM puede citar: empujaron el score y son raras
    frente a las transacciones normales. El JSON conserva todas.
    """
    resultado = []
    for senal in _senales_de(fila):
        nombre = senal["senal"]
        columna, direccion = VALOR_PRINCIPAL[nombre]
        percentil = percentil_rareza(float(fila[columna]), referencias["distribuciones"][columna], direccion)
        aporte = round(float(contribucion.get(nombre, 0.0)), 4)
        relevante = nombre == "historial" or (
            aporte > 0 and (percentil >= PERCENTIL_RELEVANTE or aporte >= CONTRIBUCION_RELEVANTE)
        )
        senal["percentil_rareza"] = percentil
        senal["contribucion_modelo"] = aporte
        senal["relevante"] = bool(relevante)
        if relevante and nombre != "historial":
            senal["descripcion"] += f" Más inusual que el {formato_es(percentil)} % de las transacciones normales."
        resultado.append(senal)
    resultado.sort(key=lambda s: -s["contribucion_modelo"])
    return resultado


def construir_casos(prueba, umbral_verificacion, umbral_bloqueo, alertas_viaje, datos_completos,
                    modelo, features, referencias):
    """Agrupa las transacciones marcadas por tarjeta en ventanas de 48 h."""
    prueba = prueba.copy()
    prueba["viaje_imposible"] = prueba["id_transaccion"].isin(alertas_viaje)
    marcadas = prueba[(prueba["score"] >= umbral_verificacion) | prueba["viaje_imposible"]]
    marcadas = marcadas.sort_values(["id_cuenta", "fecha_hora", "id_transaccion"])
    aportes = contribuciones_por_oclusion(modelo, marcadas, features, referencias["medianas"])

    cuentas = marcadas["id_cuenta"].unique()
    historiales = dict(tuple(datos_completos[datos_completos["id_cuenta"].isin(cuentas)].groupby("id_cuenta")))

    casos = []
    for id_cuenta, grupo in marcadas.groupby("id_cuenta", sort=False):
        bloques, actual = [], []
        for indice, fila in grupo.iterrows():
            if actual and fila["fecha_hora"] > actual[0][1]["fecha_hora"] + VENTANA_CASO:
                bloques.append(actual)
                actual = []
            actual.append((indice, fila))
        bloques.append(actual)

        for bloque in bloques:
            filas = [f for _, f in bloque]
            # Una compra aislada no abre caso (decisión 2026-10-21, segunda validación:
            # en Sparkov esa cola tenía 0,8 % de fraude). El viaje imposible sí, porque
            # lo decide una regla exacta, no un score.
            if len(filas) < MINIMO_TRANSACCIONES_CASO and not any(f["viaje_imposible"] for f in filas):
                continue
            inicio = filas[0]["fecha_hora"]
            tipos = sorted({"viaje_imposible" if f["viaje_imposible"] else "uso_no_autorizado" for f in filas})
            score_maximo = max(float(f["score"]) for f in filas)
            n_sobre_bloqueo = sum(1 for f in filas if float(f["score"]) >= umbral_bloqueo)
            nivel, motivo = recomendar(tipos, score_maximo, umbral_bloqueo, n_sobre_bloqueo)
            transacciones = [{
                "id_transaccion": str(f["id_transaccion"]),
                "fecha_hora": f["fecha_hora"].strftime("%Y-%m-%d %H:%M:%S"),
                "monto": round(float(f["monto"]), 2),
                "categoria": str(f["categoria"]) if "categoria" in f.index else None,
                "comercio": str(f["comercio"]) if "comercio" in f.index else None,
                "ubicacion": str(f["ubicacion"]) if "ubicacion" in f.index else None,
                "score": round(float(f["score"]), 6),
                "viaje_imposible": bool(f["viaje_imposible"]),
                "desviaciones": desviaciones(f, aportes.loc[indice].to_dict(), referencias),
            } for indice, f in bloque]
            principal = max(transacciones, key=lambda t: t["score"])
            casos.append({
                "id_caso": f"C-{len(casos) + 1:06d}",
                "id_cuenta": str(id_cuenta),
                "inicio_ventana": inicio.strftime("%Y-%m-%d %H:%M:%S"),
                "fin_ventana": (inicio + VENTANA_CASO).strftime("%Y-%m-%d %H:%M:%S"),
                "tipos_fraude": tipos,
                "score_maximo": round(score_maximo, 6),
                "transacciones_sobre_umbral_bloqueo": n_sobre_bloqueo,
                "nivel_recomendacion": nivel,
                "motivo_recomendacion": motivo,
                "senal_principal": principal["desviaciones"][0]["senal"],
                "perfil_previo": perfil_al_momento(historiales[id_cuenta], id_cuenta, inicio),
                "transacciones": transacciones,
                # Solo para validar y armar la suite de evaluación: no se le muestra al analista.
                "fraude_confirmado_dataset": int(sum(int(f["es_fraude"]) for f in filas)),
            })
    return casos


# ---------------------------------------------------------------------------
# Salidas
# ---------------------------------------------------------------------------

def _a_json(valor):
    if isinstance(valor, (np.integer,)):
        return int(valor)
    if isinstance(valor, (np.floating,)):
        return float(valor)
    if isinstance(valor, (np.bool_,)):
        return bool(valor)
    if isinstance(valor, (pd.Timestamp, datetime)):
        return valor.strftime("%Y-%m-%d %H:%M:%S")
    raise TypeError(f"No se sabe serializar {type(valor)}")


def guardar_salidas(casos, resultado_metricas, paquete_modelo, carpeta):
    os.makedirs(carpeta, exist_ok=True)
    with open(os.path.join(carpeta, "casos_marcados.json"), "w", encoding="utf-8") as archivo:
        json.dump(casos, archivo, ensure_ascii=False, indent=2, default=_a_json)

    filas = [{
        "id_caso": c["id_caso"],
        "id_cuenta": c["id_cuenta"],
        "inicio_ventana": c["inicio_ventana"],
        "fin_ventana": c["fin_ventana"],
        "n_transacciones": len(c["transacciones"]),
        "monto_total": round(sum(t["monto"] for t in c["transacciones"]), 2),
        "score_maximo": c["score_maximo"],
        "nivel_recomendacion": c["nivel_recomendacion"],
        "tipos_fraude": "|".join(c["tipos_fraude"]),
        "senal_principal": c["senal_principal"],
        "transacciones_sobre_umbral_bloqueo": c["transacciones_sobre_umbral_bloqueo"],
        "fraude_confirmado_dataset": c["fraude_confirmado_dataset"],
    } for c in casos]
    pd.DataFrame(filas).to_csv(os.path.join(carpeta, "casos_marcados.csv"), index=False, encoding="utf-8")

    with open(os.path.join(carpeta, "metricas_motor.json"), "w", encoding="utf-8") as archivo:
        json.dump(resultado_metricas, archivo, ensure_ascii=False, indent=2, default=_a_json)

    joblib.dump(paquete_modelo, os.path.join(carpeta, "modelo_riesgo.joblib"))
