"""Paridad del score en vivo contra el motor fuera de línea, sobre Sparkov y con el modelo real.

Criterio de aceptación de la SPEC (RF1), para las transacciones del tramo de prueba:
1. **Ninguna** cambia de banda (sin alerta, verificación, bloqueo) entre el score en vivo
   y el del motor fuera de línea: la decisión es la misma.
2. Al menos el 99,99 % difiere en 0,001 o menos.

Por qué no se exige el 100 % en el segundo punto (hallazgo del 2026-11-08): el motor
fuera de línea calcula `monto_24h_previo` como resta de dos sumas acumuladas sobre el
millón largo de filas, y arrastra error de redondeo (314,2600000053644 en vez de
314,26). La app suma exacto. Si el árbol del modelo corta justo en ese valor, el score
cambia unas milésimas (0,004 frente a 0,002 en el único caso visto en 37.427), lejos de
los umbrales. El valor en vivo es el correcto.

También mide cuánto tarda puntuar una transacción (mediana y p99), la primera cifra de
§7 de la SPEC.

Cómo: se calculan las features de todo Sparkov con `agregar_features` (como en el
entrenamiento) y se puntúan con el modelo. Después, para una muestra de tarjetas, se
recorre su historia completa en orden con el perfil incremental de la app y se puntúa
cada transacción del tramo de prueba con `MotorEnVivo.evaluar`.

Uso, desde la raíz:  python scripts/validar_paridad_en_vivo.py [--tarjetas 60]
Necesita datos/fraudTrain.csv y datos/fraudTest.csv. Tarda unos minutos.
"""

import argparse
import os
import random
import sys
import time

import numpy as np

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

import app.riesgo  # noqa: E402,F401 — agrega src/ a la ruta
from app.riesgo.motor_en_vivo import MotorEnVivo  # noqa: E402
from app.riesgo.perfil_incremental import EstadoTarjeta, actualizar  # noqa: E402
from cargar_datos import cargar_sparkov  # noqa: E402
from perfil_cuenta import agregar_features  # noqa: E402

TOLERANCIA = 0.001
PROPORCION_MINIMA_DENTRO = 0.9999


def banda(score, motor):
    if score >= motor.umbral_bloqueo:
        return "bloqueo"
    return "verificacion" if score >= motor.umbral_verificacion else "sin_alerta"


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    argumentos = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    argumentos.add_argument("--tarjetas", type=int, default=60, help="tarjetas de la muestra (mitad con fraude)")
    opciones = argumentos.parse_args()

    motor = MotorEnVivo(os.path.join(RAIZ, "semilla", "modelo_riesgo_sparkov.joblib"))
    inicio = time.monotonic()
    datos = cargar_sparkov(os.path.join(RAIZ, "datos", "fraudTrain.csv"), os.path.join(RAIZ, "datos", "fraudTest.csv"))
    datos, features = agregar_features(datos)
    assert features == motor.features, "las features del motor no coinciden con las del paquete del modelo"
    print(f"Sparkov cargado y con features: {len(datos):,} filas en {time.monotonic() - inicio:.0f} s")

    prueba = datos["tramo_origen"] == "prueba"
    con_fraude = sorted(datos.loc[prueba & (datos["es_fraude"] == 1), "id_cuenta"].unique())
    sin_fraude = sorted(set(datos.loc[prueba, "id_cuenta"].unique()) - set(con_fraude))
    azar = random.Random(7)
    mitad = opciones.tarjetas // 2
    muestra = azar.sample(con_fraude, min(mitad, len(con_fraude))) + azar.sample(sin_fraude, min(mitad, len(sin_fraude)))

    subconjunto = datos[datos["id_cuenta"].isin(muestra)].copy()
    subconjunto["score_fuera_de_linea"] = motor.modelo.predict_proba(subconjunto[features])[:, 1]

    diferencias, latencias, latencias_con_senales, cambios_de_banda = [], [], [], 0
    for id_cuenta, grupo in subconjunto.groupby("id_cuenta", sort=False):
        primera = grupo.iloc[0]
        estado = EstadoTarjeta(id_cuenta, primera["latitud_domicilio"], primera["longitud_domicilio"])
        for fila in grupo.to_dict("records"):           # ya en orden (agregar_features ordena)
            transaccion = {k: fila[k] for k in ("fecha_hora", "monto", "categoria", "latitud", "longitud")}
            if fila["tramo_origen"] == "prueba":
                resultado = motor.evaluar(estado, transaccion, con_senales=False)
                diferencias.append(abs(resultado["score"] - fila["score_fuera_de_linea"]))
                cambios_de_banda += banda(resultado["score"], motor) != banda(fila["score_fuera_de_linea"], motor)
                if diferencias[-1] > TOLERANCIA:
                    # Diagnóstico: qué features no coinciden en la transacción que se sale.
                    distintas = {f: (fila[f], resultado["features"][f]) for f in features
                                 if not np.isclose(float(fila[f]), float(resultado["features"][f]), rtol=1e-9, atol=1e-9)}
                    print(f"  {fila['id_transaccion']} ({fila['fecha_hora']}): fuera de línea "
                          f"{fila['score_fuera_de_linea']:.6f}, en vivo {resultado['score']:.6f}; "
                          f"features distintas (fuera de línea, en vivo): {distintas or 'ninguna'}")
                latencias.append(resultado["latencia_total_ms"])
                if fila["score_fuera_de_linea"] >= motor.umbral_verificacion:
                    latencias_con_senales.append(motor.evaluar(estado, transaccion, con_senales=True)["latencia_total_ms"])
            actualizar(estado, transaccion)

    diferencias = np.array(diferencias)
    print(f"\nTarjetas: {len(muestra)} · transacciones del tramo de prueba comparadas: {len(diferencias):,}")
    dentro = (diferencias <= TOLERANCIA).mean()
    print(f"Diferencia de score: máxima {diferencias.max():.2e}, media {diferencias.mean():.2e}; "
          f"por encima de {TOLERANCIA}: {(diferencias > TOLERANCIA).sum()} ({100 * (1 - dentro):.4f} %)")
    print(f"Transacciones que cambian de banda: {cambios_de_banda}")
    print(f"Tiempo de puntuación (solo score): mediana {np.median(latencias):.2f} ms, p99 {np.percentile(latencias, 99):.2f} ms")
    if latencias_con_senales:
        print(f"Tiempo con señales (compras sospechosas, n={len(latencias_con_senales)}): "
              f"mediana {np.median(latencias_con_senales):.2f} ms, p99 {np.percentile(latencias_con_senales, 99):.2f} ms")
    cumple = cambios_de_banda == 0 and dentro >= PROPORCION_MINIMA_DENTRO
    print("PARIDAD: CUMPLE" if cumple else "PARIDAD: NO CUMPLE")
    sys.exit(0 if cumple else 1)


if __name__ == "__main__":
    main()
