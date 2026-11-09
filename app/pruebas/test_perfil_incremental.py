"""Paridad del perfil incremental contra `src/perfil_cuenta.agregar_features` (SPEC, RF1).

Existe porque el score en vivo solo vale si las features son las mismas con las que se
entrenó el modelo. Se arma una historia sintética con lo que hace difícil la paridad
(ráfagas dentro de 24 h, compras exactamente a 24 h de distancia, tarjetas que pasan
de "sin historial" a tener perfil, categorías nuevas, horas repetidas), se calculan las
features con la función original sobre todo el conjunto, y se comparan una por una con
las del perfil incremental, recorriendo las transacciones en el mismo orden.

La paridad del SCORE con el modelo real sobre Sparkov la mide
scripts/validar_paridad_en_vivo.py (necesita el dataset de Kaggle).
"""

import math
import random
from datetime import datetime, timedelta

import pandas as pd
import pytest

import app.riesgo  # noqa: F401 — agrega src/ a la ruta
from app.riesgo.perfil_incremental import (EstadoTarjeta, actualizar, es_viaje_imposible,
                                           features_de)
from perfil_cuenta import agregar_features

FEATURES = ["monto", "hora", "z_monto", "razon_monto", "frecuencia_hora_previa", "conteo_24h_previo",
            "monto_24h_previo", "tasa_diaria_previa", "sin_historial", "frecuencia_categoria_previa",
            "distancia_domicilio_km", "distancia_vs_habitual_km"]
CATEGORIAS = ["grocery_pos", "gas_transport", "shopping_net", "misc_pos", "food_dining"]


def _historia_sintetica(semilla=11):
    azar = random.Random(semilla)
    filas = []
    for tarjeta in range(4):
        casa = (40 + azar.uniform(-5, 5), -90 + azar.uniform(-10, 10))
        fecha = datetime(2020, 1, 1) + timedelta(hours=azar.randint(0, 48))
        for i in range(azar.randint(25, 60)):
            paso = azar.choice([timedelta(minutes=azar.randint(1, 50)),      # ráfaga
                                timedelta(hours=azar.randint(2, 30)),
                                timedelta(hours=24)])                          # borde exacto de la ventana
            fecha += paso
            filas.append({
                "id_cuenta": f"4000{tarjeta}", "id_transaccion": f"t{tarjeta}-{i:03d}", "fecha_hora": fecha,
                "monto": round(azar.choice([azar.uniform(1, 80), azar.uniform(200, 1500)]), 2),
                "categoria": azar.choice(CATEGORIAS[: 2 + tarjeta]),
                "latitud": casa[0] + azar.uniform(-1, 1), "longitud": casa[1] + azar.uniform(-1, 1),
                "latitud_domicilio": casa[0], "longitud_domicilio": casa[1], "ubicacion": "Ciudad",
            })
    datos = pd.DataFrame(filas)
    datos["hora"] = datos["fecha_hora"].dt.hour
    return datos


@pytest.fixture(scope="module")
def comparacion():
    datos = _historia_sintetica()
    esperadas, features = agregar_features(datos.copy())
    assert features == FEATURES
    estados, obtenidas = {}, []
    for fila in esperadas.to_dict("records"):     # agregar_features ya las deja en orden
        estado = estados.setdefault(fila["id_cuenta"], EstadoTarjeta(
            fila["id_cuenta"], fila["latitud_domicilio"], fila["longitud_domicilio"]))
        transaccion = {k: fila[k] for k in ("fecha_hora", "monto", "categoria", "latitud", "longitud")}
        obtenidas.append(features_de(estado, transaccion))
        actualizar(estado, transaccion)
    return esperadas, obtenidas


@pytest.mark.parametrize("feature", FEATURES)
def test_cada_feature_coincide_con_el_motor_fuera_de_linea(comparacion, feature):
    esperadas, obtenidas = comparacion
    for esperada, obtenida in zip(esperadas[feature].tolist(), obtenidas):
        assert math.isclose(float(esperada), float(obtenida[feature]), rel_tol=1e-9, abs_tol=1e-9), \
            f"{feature}: fuera de línea {esperada} ≠ en vivo {obtenida[feature]}"


def test_la_historia_cubre_los_casos_dificiles(comparacion):
    esperadas, _ = comparacion
    assert (esperadas["sin_historial"] == 1).any() and (esperadas["sin_historial"] == 0).any()
    assert (esperadas["conteo_24h_previo"] >= 3).any()        # hubo ráfagas


def test_el_estado_sobrevive_a_guardarse_en_la_base():
    datos = _historia_sintetica(semilla=3)
    estado = EstadoTarjeta("40000", datos.loc[0, "latitud_domicilio"], datos.loc[0, "longitud_domicilio"])
    for fila in datos[datos["id_cuenta"] == "40000"].head(30).to_dict("records"):
        actualizar(estado, fila)
    recuperado = EstadoTarjeta.desde_dict(estado.a_dict())
    siguiente = {"fecha_hora": estado.ultima_fecha + timedelta(hours=1), "monto": 999.0,
                 "categoria": "shopping_net", "latitud": 41.0, "longitud": -89.0}
    assert features_de(recuperado, siguiente) == features_de(estado, siguiente)


def test_viaje_imposible_misma_regla_que_el_detector():
    estado = EstadoTarjeta("1", 40.7, -74.0)
    actualizar(estado, {"fecha_hora": datetime(2020, 1, 1, 10), "monto": 10, "categoria": "a",
                        "latitud": 40.7, "longitud": -74.0})                # Nueva York
    los_angeles = {"fecha_hora": datetime(2020, 1, 1, 11), "monto": 10, "categoria": "a",
                   "latitud": 34.05, "longitud": -118.24}                   # ~3 900 km en 1 h
    assert es_viaje_imposible(estado, los_angeles)
    tarde = {**los_angeles, "fecha_hora": datetime(2020, 1, 1, 18)}        # 8 h: ~490 km/h, plausible
    assert not es_viaje_imposible(estado, tarde)
