"""Detecta viajes imposibles: la misma cuenta transacciona en dos ciudades distintas
en menos tiempo del que toma viajar esa distancia.

Es código determinista (distancia entre coordenadas contra tiempo transcurrido y una
velocidad máxima plausible), no un modelo — ver decisiones.md, sección "Prueba de
necesidad", por qué esta pieza específica no lleva IA: la regla se puede escribir
exacta y el costo de un error de cálculo silencioso es alto.

Este detector es independiente del modelo de entrenar_modelo.py: cubre el segundo
tipo de fraude del alcance del proyecto (toma de control vía viaje imposible), que el
modelo de ML no busca detectar.
"""

import math
import sys

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

RUTA_DATOS = "../datos/transacciones.csv"
VELOCIDAD_MAXIMA_PLAUSIBLE_KMH = 900  # velocidad de crucero de un vuelo comercial


def distancia_km(lat1, lon1, lat2, lon2):
    """Distancia entre dos coordenadas con la fórmula de Haversine."""
    radio_tierra_km = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return 2 * radio_tierra_km * math.asin(math.sqrt(a))


def detectar(datos, comparar_por="ubicacion"):
    """Devuelve el conjunto de id_transaccion marcados como viaje imposible.

    comparar_por="ubicacion" (por defecto) solo evalúa pares con ciudad distinta, como
    en los datos sintéticos. comparar_por="coordenadas" evalúa todo par consecutivo,
    para datasets como Sparkov donde la ciudad es la del domicilio y lo que cambia
    son las coordenadas del comercio. La fórmula y el límite de velocidad no cambian.
    """
    datos = datos.copy()
    datos["fecha_hora"] = pd.to_datetime(datos["fecha_hora"])
    datos = datos.sort_values(["id_cuenta", "fecha_hora"])

    alertas = []
    for _, grupo in datos.groupby("id_cuenta"):
        anterior = None
        for _, fila in grupo.iterrows():
            cambio_de_lugar = anterior is not None and (
                comparar_por == "coordenadas" or fila["ubicacion"] != anterior["ubicacion"]
            )
            if cambio_de_lugar:
                horas_transcurridas = (fila["fecha_hora"] - anterior["fecha_hora"]).total_seconds() / 3600
                if horas_transcurridas > 0:
                    distancia = distancia_km(
                        anterior["latitud"], anterior["longitud"], fila["latitud"], fila["longitud"]
                    )
                    velocidad_requerida = distancia / horas_transcurridas
                    if velocidad_requerida > VELOCIDAD_MAXIMA_PLAUSIBLE_KMH:
                        alertas.append(fila["id_transaccion"])
            anterior = fila
    return set(alertas)


def main():
    datos = pd.read_csv(RUTA_DATOS)
    alertas = detectar(datos)
    verdaderas = set(datos.loc[datos["tipo_fraude"] == "viaje_imposible", "id_transaccion"])

    verdaderos_positivos = len(alertas & verdaderas)
    falsos_positivos = len(alertas - verdaderas)
    falsos_negativos = len(verdaderas - alertas)
    precision = verdaderos_positivos / len(alertas) if alertas else 0.0
    recall = verdaderos_positivos / len(verdaderas) if verdaderas else 0.0

    print("=" * 70)
    print(f"DETECTOR DE VIAJE IMPOSIBLE (regla determinista, velocidad > {VELOCIDAD_MAXIMA_PLAUSIBLE_KMH} km/h)")
    print("=" * 70)
    print(f"Transacciones marcadas: {len(alertas)}")
    print(f"De esas, eran fraude real de este tipo: {verdaderos_positivos}")
    print(f"Fraude real de este tipo que existía en los datos: {len(verdaderas)}")
    print(f"Precisión: {precision:.3f}")
    print(f"Recall: {recall:.3f}")
    print(f"Falsos positivos: {falsos_positivos}")
    print(f"Falsos negativos: {falsos_negativos}")


if __name__ == "__main__":
    main()
