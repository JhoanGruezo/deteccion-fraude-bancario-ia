"""Entrena el motor de riesgo, lo compara contra la regla de umbral fijo y genera los casos.

La comparación es la evidencia numérica de la prueba de necesidad: si la regla de
umbral fijo (la idea original: "monto alto o madrugada") tuviera un desempeño
parecido al de los modelos, no habría justificación para el modelo. El punto es
demostrar que no es así, porque el fraude real depende del perfil de cada cuenta,
no de un umbral global.

Uso, desde src/:
    python entrenar_modelo.py                      # datos sintéticos
    python entrenar_modelo.py --fuente sparkov     # dataset real de Kaggle (datos/fraudTrain.csv y fraudTest.csv)

Escribe en ../datos/salidas_<fuente>/: casos_marcados.json, casos_marcados.csv,
metricas_motor.json y modelo_riesgo.joblib.
"""

import argparse
import sys
import time
from datetime import datetime

from sklearn.metrics import average_precision_score

sys.stdout.reconfigure(encoding="utf-8")

from cargar_datos import ArchivoFaltante, cargar
from detectar_viaje_imposible import detectar
from motor_riesgo import (
    PROPORCION_NORMALES_ENTRENAMIENTO,
    construir_casos,
    dividir_temporal,
    elegir_modelo,
    elegir_umbrales,
    entrenar_modelos,
    guardar_salidas,
    metricas,
    preparar_referencias,
    regla_umbral_fijo,
    submuestrear_entrenamiento,
)
from perfil_cuenta import agregar_features

FILAS_PARA_SUBMUESTREAR = 200_000


def solo_uso_no_autorizado(datos):
    # El viaje imposible lo cubre el detector determinista (ver decisiones.md); el
    # modelo solo aprende el patrón de uso no autorizado.
    return datos[datos["tipo_fraude"] != "viaje_imposible"]


def imprimir_tabla(titulo, filas):
    print("=" * 78)
    print(titulo)
    print("=" * 78)
    print(f"{'':28}{'precisión':>12}{'recall':>10}{'F1':>10}{'AUC-PR':>10}")
    for nombre, m in filas.items():
        print(f"{nombre:28}{m['precision']:>12.3f}{m['recall']:>10.3f}{m['f1']:>10.3f}{m['auc_pr']:>10.3f}")
    print()


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fuente", choices=["sinteticos", "sparkov"], default="sinteticos")
    fuente = parser.parse_args().fuente
    inicio_corrida = time.time()

    try:
        datos = cargar(fuente)
    except ArchivoFaltante as error:
        print(f"[ERROR] {error}")
        sys.exit(1)
    print(f"Fuente: {fuente} — {len(datos):,} transacciones, {datos['id_cuenta'].nunique():,} tarjetas/cuentas")

    datos, features = agregar_features(datos)
    entrenamiento, validacion, prueba = dividir_temporal(datos, fuente)
    entrenamiento_ml = solo_uso_no_autorizado(entrenamiento)
    validacion_ml = solo_uso_no_autorizado(validacion)
    prueba_ml = solo_uso_no_autorizado(prueba)

    submuestreado = len(entrenamiento_ml) > FILAS_PARA_SUBMUESTREAR
    entrenamiento_ajuste = submuestrear_entrenamiento(entrenamiento_ml) if submuestreado else entrenamiento_ml
    for nombre_tramo, tramo in [("entrenamiento", entrenamiento_ml), ("validación", validacion_ml), ("prueba", prueba_ml)]:
        print(f"  {nombre_tramo:13} {tramo['fecha_hora'].min():%Y-%m-%d} a {tramo['fecha_hora'].max():%Y-%m-%d}"
              f"  {len(tramo):>9,} filas  {100 * tramo['es_fraude'].mean():.3f} % fraude")
    if submuestreado:
        print(f"  (se entrenó con todo el fraude y el {PROPORCION_NORMALES_ENTRENAMIENTO:.0%} de las normales: "
              f"{len(entrenamiento_ajuste):,} filas)")
    print()

    modelos = entrenar_modelos(entrenamiento_ajuste, features)
    nombre_elegido = elegir_modelo(modelos, validacion_ml, features)

    resultados_validacion, resultados_prueba, umbrales_por_modelo = {}, {}, {}
    umbral_monto = float(entrenamiento_ml["monto"].quantile(0.95))
    for nombre_tramo, tramo, destino in [("validacion", validacion_ml, resultados_validacion), ("prueba", prueba_ml, resultados_prueba)]:
        prediccion_regla = regla_umbral_fijo(tramo, umbral_monto)
        destino["regla_umbral_fijo"] = metricas(tramo["es_fraude"], prediccion_regla)
    for nombre, modelo in modelos.items():
        score_validacion = modelo.predict_proba(validacion_ml[features])[:, 1]
        _, umbral_f1, _ = elegir_umbrales(validacion_ml["es_fraude"], score_validacion)
        umbrales_por_modelo[nombre] = umbral_f1
        score_prueba = modelo.predict_proba(prueba_ml[features])[:, 1]
        resultados_validacion[nombre] = metricas(validacion_ml["es_fraude"], (score_validacion >= umbral_f1).astype(int), score_validacion)
        resultados_prueba[nombre] = metricas(prueba_ml["es_fraude"], (score_prueba >= umbral_f1).astype(int), score_prueba)

    modelo = modelos[nombre_elegido]
    umbral_verificacion, umbral_bloqueo, aviso_umbrales = elegir_umbrales(
        validacion_ml["es_fraude"], modelo.predict_proba(validacion_ml[features])[:, 1]
    )

    imprimir_tabla(f"VALIDACIÓN — cada modelo con su umbral de mejor F1 (regla: monto > {umbral_monto:,.2f} o antes de las 6 h)", resultados_validacion)
    imprimir_tabla("PRUEBA — mismos umbrales, sin retocar", resultados_prueba)
    print(f"Modelo elegido (mejor AUC-PR en validación): {nombre_elegido}")
    print(f"Umbral de verificación (mejor F2): {umbral_verificacion:.4f}   Umbral de bloqueo (mejor F1): {umbral_bloqueo:.4f}")
    if aviso_umbrales:
        print(f"[AVISO] {aviso_umbrales}")

    # AUC-PR de cada feature sola, como score: si alguna separa casi perfecto, es la
    # señal de alerta de CLAUDE.md (datos poco realistas o columna filtrada).
    auc_por_feature = {}
    for feature in features:
        valores = prueba_ml[feature].astype(float)
        auc_por_feature[feature] = round(max(
            average_precision_score(prueba_ml["es_fraude"], valores),
            average_precision_score(prueba_ml["es_fraude"], -valores),
        ), 4)
    print("\nAUC-PR de cada feature usada sola (prueba):")
    for feature, valor in sorted(auc_por_feature.items(), key=lambda par: -par[1]):
        print(f"  {feature:30} {valor:.3f}")

    # En Sparkov toda tarjeta nueva es fraude (artefacto del simulador). sin_historial
    # se queda como feature, pero se reporta también la prueba sin esas filas para no
    # vender ese rasgo como capacidad del modelo (decisiones.md, 2026-10-21).
    con_historial = prueba_ml[prueba_ml["sin_historial"] == 0]
    score_con_historial = modelo.predict_proba(con_historial[features])[:, 1]
    sin_tarjetas_nuevas = {
        "filas_excluidas": int(len(prueba_ml) - len(con_historial)),
        "fraudes_excluidos": int(prueba_ml["es_fraude"].sum() - con_historial["es_fraude"].sum()),
        nombre_elegido: metricas(con_historial["es_fraude"], (score_con_historial >= umbral_bloqueo).astype(int), score_con_historial),
        "regla_umbral_fijo": metricas(con_historial["es_fraude"], regla_umbral_fijo(con_historial, umbral_monto)),
    }
    print(f"\nPrueba SIN tarjetas nuevas ({sin_tarjetas_nuevas['filas_excluidas']} filas sin historial excluidas, "
          f"{sin_tarjetas_nuevas['fraudes_excluidos']} de ellas fraude):")
    imprimir_tabla("PRUEBA SIN TARJETAS NUEVAS — modelo elegido al umbral de bloqueo",
                   {nombre_elegido: sin_tarjetas_nuevas[nombre_elegido], "regla_umbral_fijo": sin_tarjetas_nuevas["regla_umbral_fijo"]})

    referencias = preparar_referencias(entrenamiento_ml, features)

    prueba = prueba.copy()
    prueba["score"] = modelo.predict_proba(prueba[features])[:, 1]

    print("\nDetector de viaje imposible sobre el tramo de prueba...")
    if fuente == "sparkov":
        # Decisión 2026-10-21: en Sparkov solo se mide. El simulador ubica los
        # comercios al azar a ~100 km del domicilio, así que casi todo par de compras
        # cercanas en el tiempo "exige" velocidades imposibles: no son tomas de control.
        alertas_medidas = detectar(prueba, comparar_por="coordenadas")
        alertas_para_casos = set()
        print(f"  {len(alertas_medidas):,} alertas en {prueba[prueba['id_transaccion'].isin(alertas_medidas)]['id_cuenta'].nunique():,} tarjetas "
              "(falsas alarmas: Sparkov no trae ese fraude etiquetado ni geografía real). No generan casos.")
    else:
        alertas_medidas = detectar(datos) & set(prueba["id_transaccion"])
        alertas_para_casos = alertas_medidas
        verdaderas = set(prueba.loc[prueba["tipo_fraude"] == "viaje_imposible", "id_transaccion"])
        print(f"  {len(alertas_medidas)} alertas; {len(alertas_medidas & verdaderas)} de {len(verdaderas)} viajes imposibles reales del tramo.")

    casos = construir_casos(prueba, umbral_verificacion, umbral_bloqueo, alertas_para_casos, datos,
                            modelo, features, referencias)
    casos_por_nivel, con_fraude_por_nivel = {}, {}
    for caso in casos:
        nivel = caso["nivel_recomendacion"]
        casos_por_nivel[nivel] = casos_por_nivel.get(nivel, 0) + 1
        con_fraude_por_nivel[nivel] = con_fraude_por_nivel.get(nivel, 0) + (caso["fraude_confirmado_dataset"] > 0)
    con_fraude = sum(con_fraude_por_nivel.values())
    tarjetas_con_fraude = set(prueba.loc[prueba["es_fraude"] == 1, "id_cuenta"])
    tarjetas_cubiertas = {c["id_cuenta"] for c in casos if c["fraude_confirmado_dataset"] > 0}

    resultado = {
        "fecha_corrida": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "fuente": fuente,
        "features": features,
        "tramos": {
            nombre: {"desde": tramo["fecha_hora"].min(), "hasta": tramo["fecha_hora"].max(),
                     "filas": len(tramo), "porcentaje_fraude": round(100 * float(tramo["es_fraude"].mean()), 4)}
            for nombre, tramo in [("entrenamiento", entrenamiento_ml), ("validacion", validacion_ml), ("prueba", prueba_ml)]
        },
        "submuestreo_entrenamiento": {"aplicado": submuestreado, "proporcion_normales": PROPORCION_NORMALES_ENTRENAMIENTO if submuestreado else 1.0,
                                       "filas_ajuste": len(entrenamiento_ajuste)},
        "regla_umbral_fijo": {"umbral_monto": round(umbral_monto, 2), "hora_menor_a": 6},
        "validacion": resultados_validacion,
        "prueba": resultados_prueba,
        "umbral_f1_por_modelo": umbrales_por_modelo,
        "modelo_elegido": nombre_elegido,
        "umbral_verificacion": umbral_verificacion,
        "umbral_bloqueo": umbral_bloqueo,
        "aviso_umbrales": aviso_umbrales,
        "auc_pr_por_feature_prueba": auc_por_feature,
        "prueba_sin_tarjetas_nuevas": sin_tarjetas_nuevas,
        "viaje_imposible": {"alertas_en_prueba": len(alertas_medidas), "generan_casos": fuente != "sparkov"},
        "casos": {"total": len(casos), "por_nivel": casos_por_nivel, "con_fraude_confirmado": con_fraude,
                  "con_fraude_confirmado_por_nivel": con_fraude_por_nivel,
                  "tarjetas_con_fraude_en_prueba": len(tarjetas_con_fraude),
                  "tarjetas_con_fraude_cubiertas": len(tarjetas_cubiertas & tarjetas_con_fraude)},
        "segundos_corrida": round(time.time() - inicio_corrida, 1),
    }
    paquete = {"modelo": modelo, "nombre": nombre_elegido, "features": features,
               "umbral_verificacion": umbral_verificacion, "umbral_bloqueo": umbral_bloqueo,
               "referencias": referencias}
    carpeta = f"../datos/salidas_{fuente}"
    guardar_salidas(casos, resultado, paquete, carpeta)

    print(f"\nCasos generados: {len(casos):,}")
    for nivel, total in sorted(casos_por_nivel.items()):
        print(f"  {nivel:24} {total:>5,} casos, {con_fraude_por_nivel[nivel]:>5,} con fraude confirmado "
              f"({100 * con_fraude_por_nivel[nivel] / total:.1f} %)")
    print(f"Tarjetas con fraude en prueba cubiertas por algún caso: "
          f"{len(tarjetas_cubiertas & tarjetas_con_fraude)} de {len(tarjetas_con_fraude)}")
    print(f"Archivos en {carpeta}/ ({resultado['segundos_corrida']} s)")


if __name__ == "__main__":
    main()
