"""Genera transacciones sintéticas con perfiles de comportamiento por cuenta.

Cada cuenta tiene su propio monto promedio, sus horas habituales y su ubicación
habitual. Se inyectan dos tipos de fraude, siguiendo el alcance de decisiones.md:

- "uso_no_autorizado": combina monto, hora y a veces ubicación atípicos para esa
  cuenta a la vez — ninguna señal aislada alcanza, hay que combinarlas (lo detecta
  el modelo de ML en entrenar_modelo.py). Desde el 2026-10-21 llega en RÁFAGAS de 2
  a 6 compras en pocas horas, como en el fraude real de Sparkov: quien roba una
  tarjeta la usa varias veces seguidas antes de que la bloqueen.
- "viaje_imposible": la misma cuenta transacciona en dos ciudades separadas por una
  distancia que no se puede recorrer en el tiempo transcurrido entre ambas (lo
  detecta la regla determinista en detectar_viaje_imposible.py, sin modelo).

También se inyecta ruido legítimo (pago grande legítimo, hora rara legítima, viaje
legítimo con tiempo suficiente para haber viajado de verdad, y ráfagas legítimas de
compras seguidas) para que ninguna señal aislada separe las clases perfectamente.
"""

import csv
import math
import random
from datetime import datetime, time, timedelta

RUTA_SALIDA = "../datos/transacciones.csv"
NUM_CUENTAS = 400
TRANSACCIONES_POR_CUENTA = 40
PROPORCION_VIAJE_IMPOSIBLE = 0.01
PROPORCION_USO_NO_AUTORIZADO = 0.006  # probabilidad de que arranque una ráfaga (2 a 6 compras)
PROPORCION_RUIDO = 0.08
TAMANO_RAFAGA_FRAUDE = (2, 6)
TAMANO_RAFAGA_LEGITIMA = (2, 3)
FECHA_INICIO = datetime(2026, 1, 1)

CIUDADES = {
    "Bogota": (4.7110, -74.0721),
    "Medellin": (6.2442, -75.5812),
    "Cali": (3.4516, -76.5320),
    "Barranquilla": (10.9639, -74.7964),
    "Cartagena": (10.3910, -75.4794),
    "Bucaramanga": (7.1193, -73.1227),
    "Pereira": (4.8087, -75.6906),
    "Manizales": (5.0703, -75.5138),
    "Cucuta": (7.8939, -72.5078),
    "Ibague": (4.4389, -75.2322),
}
UBICACIONES = list(CIUDADES.keys())

random.seed(7)


def distancia_km(ciudad_a, ciudad_b):
    """Distancia entre dos ciudades con la fórmula de Haversine."""
    lat1, lon1 = CIUDADES[ciudad_a]
    lat2, lon2 = CIUDADES[ciudad_b]
    radio_tierra_km = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return 2 * radio_tierra_km * math.asin(math.sqrt(a))


def ciudad_lejana(ciudad_origen, distancia_minima_km=150):
    """Otra ciudad, a una distancia mínima dada (0 = cualquier otra ciudad)."""
    candidatas = [
        c for c in UBICACIONES
        if c != ciudad_origen and distancia_km(ciudad_origen, c) >= distancia_minima_km
    ]
    if not candidatas:
        candidatas = [c for c in UBICACIONES if c != ciudad_origen]
    return random.choice(candidatas)


def generar_perfil_cuenta(id_cuenta):
    """Crea el comportamiento normal de una cuenta: cuánto gasta, a qué horas y desde dónde."""
    return {
        "id_cuenta": id_cuenta,
        "monto_promedio": random.uniform(50_000, 800_000),
        "horas_habituales": random.sample(range(6, 23), k=random.randint(3, 6)),
        "ubicacion_habitual": random.choice(UBICACIONES),
    }


def construir_fila(id_transaccion, perfil, monto, fecha_hora, ubicacion, tipo_fraude):
    latitud, longitud = CIUDADES[ubicacion]
    return {
        "id_transaccion": id_transaccion,
        "id_cuenta": perfil["id_cuenta"],
        "monto": round(monto, 2),
        "fecha_hora": fecha_hora.strftime("%Y-%m-%d %H:%M"),
        "hora": fecha_hora.hour,
        "ubicacion": ubicacion,
        "latitud": latitud,
        "longitud": longitud,
        "monto_promedio_cuenta": round(perfil["monto_promedio"], 2),
        "ubicacion_habitual_cuenta": perfil["ubicacion_habitual"],
        "tipo_fraude": tipo_fraude,
        "es_fraude": 0 if tipo_fraude == "normal" else 1,
    }


def generar_transacciones_cuenta(perfil, id_transaccion_inicial):
    """Genera la secuencia cronológica de transacciones de una cuenta.

    Invariante importante: `tiempo_actual` siempre es EXACTAMENTE el fecha_hora que
    se acaba de escribir en la fila anterior (nunca una fecha base que se desvíe de
    lo que de verdad quedó guardado). Si no se respeta esto, el "viaje imposible"
    puede terminar separado por días en vez de minutos de la transacción anterior
    real, y el detector determinista deja de tener algo que detectar.
    """
    filas = []
    id_transaccion = id_transaccion_inicial
    tiempo_actual = FECHA_INICIO + timedelta(days=random.uniform(0, 5))
    ubicacion_actual = perfil["ubicacion_habitual"]

    for _ in range(TRANSACCIONES_POR_CUENTA):
        r = random.random()

        if r < PROPORCION_VIAJE_IMPOSIBLE:
            # Salto de pocos minutos a una ciudad lejana: físicamente no se puede recorrer.
            fecha_hora = tiempo_actual + timedelta(minutes=random.uniform(1, 8))
            ubicacion = ciudad_lejana(ubicacion_actual, distancia_minima_km=150)
            monto = max(1000, random.gauss(perfil["monto_promedio"], perfil["monto_promedio"] * 0.3))
            tipo_fraude = "viaje_imposible"

        elif r < PROPORCION_VIAJE_IMPOSIBLE + PROPORCION_USO_NO_AUTORIZADO:
            # Ráfaga de uso no autorizado: varias compras de madrugada, montos varias
            # veces el promedio de la cuenta, en una misma ciudad (a veces otra), con
            # minutos u horas entre una y otra. Cada fila avanza tiempo_actual.
            fecha_base = (tiempo_actual + timedelta(days=random.randint(1, 4))).date()
            fecha_hora = datetime.combine(fecha_base, time(hour=random.choice(range(0, 5)), minute=random.randint(0, 59)))
            ubicacion = ciudad_lejana(perfil["ubicacion_habitual"], distancia_minima_km=0) \
                if random.random() < 0.5 else perfil["ubicacion_habitual"]
            for posicion in range(random.randint(*TAMANO_RAFAGA_FRAUDE)):
                if posicion > 0:
                    fecha_hora += timedelta(minutes=random.uniform(10, 90))
                monto = perfil["monto_promedio"] * random.uniform(2, 8)
                filas.append(construir_fila(id_transaccion, perfil, monto, fecha_hora, ubicacion, "uso_no_autorizado"))
                id_transaccion += 1
            ubicacion_actual = ubicacion
            tiempo_actual = fecha_hora
            continue

        else:
            # Todo lo demás avanza al menos un día completo antes de fijar la hora,
            # para poder controlar la hora exacta (madrugada, habitual) sin arriesgarse
            # a retroceder en el tiempo respecto a la transacción anterior.
            fecha_base = (tiempo_actual + timedelta(days=random.randint(1, 4))).date()

            if r < PROPORCION_VIAJE_IMPOSIBLE + PROPORCION_USO_NO_AUTORIZADO + PROPORCION_RUIDO:
                tipo_ruido = random.choice(["monto_alto_legitimo", "hora_rara_legitima", "viaje_legitimo", "rafaga_legitima"])
                if tipo_ruido == "rafaga_legitima":
                    # Compras seguidas legítimas (mercado, gasolina, almuerzo): a horas
                    # habituales y con montos normales, para que "varias compras
                    # seguidas" no sea por sí sola una señal de fraude.
                    fecha_hora = datetime.combine(fecha_base, time(hour=random.choice(perfil["horas_habituales"]), minute=random.randint(0, 59)))
                    for posicion in range(random.randint(*TAMANO_RAFAGA_LEGITIMA)):
                        if posicion > 0:
                            fecha_hora += timedelta(minutes=random.uniform(10, 60))
                        monto = max(1000, random.gauss(perfil["monto_promedio"], perfil["monto_promedio"] * 0.3))
                        filas.append(construir_fila(id_transaccion, perfil, monto, fecha_hora, perfil["ubicacion_habitual"], "normal"))
                        id_transaccion += 1
                    ubicacion_actual = perfil["ubicacion_habitual"]
                    tiempo_actual = fecha_hora
                    continue
                if tipo_ruido == "monto_alto_legitimo":
                    monto = perfil["monto_promedio"] * random.uniform(3, 6)
                    hora = random.choice(perfil["horas_habituales"])
                    ubicacion = perfil["ubicacion_habitual"]
                elif tipo_ruido == "hora_rara_legitima":
                    monto = max(1000, random.gauss(perfil["monto_promedio"], perfil["monto_promedio"] * 0.3))
                    hora = random.choice(range(0, 6))
                    ubicacion = perfil["ubicacion_habitual"]
                else:
                    # Viaje legítimo: cambia de ciudad, con al menos un día de por medio, no minutos.
                    monto = max(1000, random.gauss(perfil["monto_promedio"], perfil["monto_promedio"] * 0.3))
                    hora = random.choice(perfil["horas_habituales"])
                    ubicacion = ciudad_lejana(perfil["ubicacion_habitual"], distancia_minima_km=0)
                tipo_fraude = "normal"

            else:
                monto = max(1000, random.gauss(perfil["monto_promedio"], perfil["monto_promedio"] * 0.3))
                hora = random.choice(perfil["horas_habituales"])
                ubicacion = perfil["ubicacion_habitual"]
                tipo_fraude = "normal"

            fecha_hora = datetime.combine(fecha_base, time(hour=hora, minute=random.randint(0, 59)))

        filas.append(construir_fila(id_transaccion, perfil, monto, fecha_hora, ubicacion, tipo_fraude))
        ubicacion_actual = ubicacion
        id_transaccion += 1
        tiempo_actual = fecha_hora

    return filas, id_transaccion


def main():
    perfiles = [generar_perfil_cuenta(i) for i in range(NUM_CUENTAS)]
    filas = []
    id_transaccion = 0

    for perfil in perfiles:
        filas_cuenta, id_transaccion = generar_transacciones_cuenta(perfil, id_transaccion)
        filas.extend(filas_cuenta)

    random.shuffle(filas)

    with open(RUTA_SALIDA, "w", newline="", encoding="utf-8") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=list(filas[0].keys()))
        escritor.writeheader()
        escritor.writerows(filas)

    total_uso_no_autorizado = sum(1 for f in filas if f["tipo_fraude"] == "uso_no_autorizado")
    total_viaje_imposible = sum(1 for f in filas if f["tipo_fraude"] == "viaje_imposible")
    total_fraude = total_uso_no_autorizado + total_viaje_imposible

    print(f"Generadas {len(filas)} transacciones de {NUM_CUENTAS} cuentas.")
    print(f"Fraude total: {total_fraude} ({100 * total_fraude / len(filas):.2f}%)")
    print(f"  - Uso no autorizado: {total_uso_no_autorizado}")
    print(f"  - Viaje imposible: {total_viaje_imposible}")
    print(f"Guardado en {RUTA_SALIDA}")


if __name__ == "__main__":
    main()
