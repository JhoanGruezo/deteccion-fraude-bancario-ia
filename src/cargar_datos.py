"""Carga las transacciones de cualquiera de las dos fuentes con las columnas del proyecto.

Existe para que el resto del motor no sepa de dónde vienen los datos: los sintéticos
de generar_datos.py ya traen las columnas del proyecto, y Sparkov (dataset público de
Kaggle, ver decisiones.md "Actualización 2026-10-21") se traduce aquí a esas mismas
columnas. Las columnas personales de Sparkov (nombre, dirección, fecha de
nacimiento, oficio) no se leen: no son features y no hacen falta para explicar un
caso.
"""

import os

import pandas as pd

RUTA_SINTETICOS = "../datos/transacciones.csv"
RUTA_SPARKOV_ENTRENAMIENTO = "../datos/fraudTrain.csv"
RUTA_SPARKOV_PRUEBA = "../datos/fraudTest.csv"

COLUMNAS_SPARKOV = {
    "trans_num": "id_transaccion",
    "cc_num": "id_cuenta",
    "trans_date_trans_time": "fecha_hora",
    "amt": "monto",
    "category": "categoria",
    "merchant": "comercio",
    "merch_lat": "latitud",
    "merch_long": "longitud",
    "lat": "latitud_domicilio",
    "long": "longitud_domicilio",
    "city": "ubicacion",
    "is_fraud": "es_fraude",
}


class ArchivoFaltante(Exception):
    """Falta un CSV de la fuente pedida; el mensaje dice cuál y dónde ponerlo."""


def _verificar_archivo(ruta):
    if not os.path.exists(ruta):
        raise ArchivoFaltante(
            f"No se encontró {os.path.abspath(ruta)}. "
            "Descárguelo y déjelo en la carpeta datos/ del proyecto."
        )


def cargar_sinteticos(ruta=RUTA_SINTETICOS):
    _verificar_archivo(ruta)
    datos = pd.read_csv(ruta)
    datos["fecha_hora"] = pd.to_datetime(datos["fecha_hora"])
    datos["id_transaccion"] = datos["id_transaccion"].astype(str)
    datos["id_cuenta"] = datos["id_cuenta"].astype(str)
    return datos


def cargar_sparkov(ruta_entrenamiento=RUTA_SPARKOV_ENTRENAMIENTO, ruta_prueba=RUTA_SPARKOV_PRUEBA):
    partes = []
    for ruta, tramo in [(ruta_entrenamiento, "entrenamiento"), (ruta_prueba, "prueba")]:
        _verificar_archivo(ruta)
        parte = pd.read_csv(
            ruta,
            usecols=list(COLUMNAS_SPARKOV),
            dtype={"cc_num": str, "category": "category", "city": "category"},
        ).rename(columns=COLUMNAS_SPARKOV)
        parte["tramo_origen"] = tramo
        partes.append(parte)

    datos = pd.concat(partes, ignore_index=True)
    datos["fecha_hora"] = pd.to_datetime(datos["fecha_hora"])
    datos["hora"] = datos["fecha_hora"].dt.hour
    # Sparkov antepone "fraud_" al nombre de todos los comercios, fraudulentos o no;
    # se quita para que el analista no lea una pista falsa.
    datos["comercio"] = datos["comercio"].str.removeprefix("fraud_")
    datos["categoria"] = datos["categoria"].astype(str)
    datos["ubicacion"] = datos["ubicacion"].astype(str)
    datos["tipo_fraude"] = datos["es_fraude"].map({1: "uso_no_autorizado", 0: "normal"})
    for columna in ["monto", "latitud", "longitud", "latitud_domicilio", "longitud_domicilio"]:
        datos[columna] = datos[columna].astype("float64")
    return datos


def cargar(fuente):
    if fuente == "sinteticos":
        return cargar_sinteticos()
    if fuente == "sparkov":
        return cargar_sparkov()
    raise ValueError(f"Fuente desconocida: {fuente}. Use 'sinteticos' o 'sparkov'.")
