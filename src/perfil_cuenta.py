"""Features de cada transacción contra el perfil PREVIO de su tarjeta.

Corrige la filtración de la versión anterior de entrenar_modelo.py, que calculaba el
perfil con todas las transacciones de la cuenta, incluida la misma que se evaluaba y
las futuras (ver decisiones.md, "Actualización 2026-10-21"). Aquí cada feature usa
solo lo que el banco ya había visto de esa tarjeta antes de la transacción: sumas y
conteos acumulados desplazados una posición, sin iterrows, para que corra sobre el
millón largo de filas de Sparkov.

Las mismas cifras sostienen después la explicación del caso: si el resumen dice
"14 veces su promedio", ese promedio sale de aquí y no incluye la transacción que se
está explicando.
"""

import numpy as np
import pandas as pd

MINIMO_HISTORIAL = 10  # con menos transacciones previas no se habla de "perfil habitual"
PISO_DESVIACION_MONTO = 1.0  # evita dividir por cero en tarjetas de monto casi constante
SEGUNDOS_24H = 24 * 3600


def distancia_km_vectorizada(lat1, lon1, lat2, lon2):
    """Haversine sobre columnas enteras (misma fórmula que detectar_viaje_imposible.py)."""
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371 * np.arcsin(np.sqrt(a))


def _frecuencia_previa(datos, columna, n_previas):
    """Fracción de las transacciones anteriores de la tarjeta con el mismo valor en `columna`."""
    coincidencias_previas = datos.groupby(["id_cuenta", columna], sort=False, observed=True).cumcount()
    return coincidencias_previas / n_previas.where(n_previas > 0)


def _ventana_24h_previa(datos):
    """Conteo y suma de montos de la tarjeta en [t - 24 h, t), sin la transacción actual.

    Como los datos están ordenados por tarjeta y fecha, una llave numérica
    (código de tarjeta, segundos) es creciente y basta un searchsorted global.
    """
    codigo_cuenta = pd.factorize(datos["id_cuenta"])[0].astype("int64")
    # Segundos desde la época sin depender de la resolución interna de la fecha:
    # pandas 3 lee datetime64[us], y suponer nanosegundos (// 10**9) convertía la
    # ventana de 24 h en una de ~1 000 días (hallazgo 1 de validacion/motor-riesgo.md).
    segundos = ((datos["fecha_hora"] - pd.Timestamp(0)) // pd.Timedelta(seconds=1)).to_numpy().astype("int64")
    lapso_real = (datos["fecha_hora"].max() - datos["fecha_hora"].min()).total_seconds()
    if abs((segundos.max() - segundos.min()) - lapso_real) > 1:
        raise ValueError("La conversión de fechas a segundos no cuadra con el lapso real de los datos.")
    llave = codigo_cuenta * 10**11 + segundos
    inicio = np.searchsorted(llave, llave - SEGUNDOS_24H, side="left")
    posicion = np.arange(len(datos))
    suma_acumulada = np.concatenate([[0.0], np.cumsum(datos["monto"].to_numpy())])
    conteo = posicion - inicio
    monto = suma_acumulada[posicion] - suma_acumulada[inicio]
    return conteo, monto


def agregar_features(datos):
    """Agrega las features de perfil previo y devuelve (datos, lista de features)."""
    datos = datos.sort_values(["id_cuenta", "fecha_hora", "id_transaccion"]).reset_index(drop=True)
    por_cuenta = datos.groupby("id_cuenta", sort=False)

    n_previas = por_cuenta.cumcount()
    datos["n_previas"] = n_previas
    datos["sin_historial"] = (n_previas < MINIMO_HISTORIAL).astype(int)

    # Promedio y desviación del monto con solo las transacciones anteriores.
    suma_previa = por_cuenta["monto"].cumsum() - datos["monto"]
    suma_cuadrados_previa = (datos["monto"] ** 2).groupby(datos["id_cuenta"], sort=False).cumsum() - datos["monto"] ** 2
    promedio = suma_previa / n_previas.where(n_previas > 0)
    varianza = (suma_cuadrados_previa / n_previas.where(n_previas > 0) - promedio**2).clip(lower=0)
    datos["monto_promedio_previo"] = promedio
    datos["monto_desv_previa"] = np.sqrt(varianza).clip(lower=PISO_DESVIACION_MONTO)
    datos["z_monto"] = (datos["monto"] - promedio) / datos["monto_desv_previa"]
    datos["razon_monto"] = datos["monto"] / promedio.clip(lower=PISO_DESVIACION_MONTO)

    datos["frecuencia_hora_previa"] = _frecuencia_previa(datos, "hora", n_previas)

    conteo, monto_ventana = _ventana_24h_previa(datos)
    datos["conteo_24h_previo"] = conteo
    datos["monto_24h_previo"] = monto_ventana

    primera_fecha = por_cuenta["fecha_hora"].transform("first")
    dias_historial = ((datos["fecha_hora"] - primera_fecha).dt.total_seconds() / 86400).clip(lower=1)
    datos["tasa_diaria_previa"] = n_previas / dias_historial

    features = [
        "monto", "hora", "z_monto", "razon_monto", "frecuencia_hora_previa",
        "conteo_24h_previo", "monto_24h_previo", "tasa_diaria_previa", "sin_historial",
    ]
    neutros = {"z_monto": 0.0, "razon_monto": 1.0, "frecuencia_hora_previa": 0.5}

    if "latitud_domicilio" in datos.columns:
        # Sparkov: la ubicación es la del domicilio (constante); lo que varía es el
        # comercio, así que se mide la categoría y la distancia domicilio-comercio.
        datos["frecuencia_categoria_previa"] = _frecuencia_previa(datos, "categoria", n_previas)
        datos["distancia_domicilio_km"] = distancia_km_vectorizada(
            datos["latitud_domicilio"], datos["longitud_domicilio"], datos["latitud"], datos["longitud"]
        )
        distancia_previa = (
            datos.groupby("id_cuenta", sort=False)["distancia_domicilio_km"].cumsum() - datos["distancia_domicilio_km"]
        ) / n_previas.where(n_previas > 0)
        datos["distancia_promedio_previa_km"] = distancia_previa
        datos["distancia_vs_habitual_km"] = datos["distancia_domicilio_km"] - distancia_previa
        features += ["frecuencia_categoria_previa", "distancia_domicilio_km", "distancia_vs_habitual_km"]
        neutros.update({"frecuencia_categoria_previa": 0.5, "distancia_vs_habitual_km": 0.0})
    else:
        # Sintéticos: la ubicación sí es la ciudad de cada transacción.
        datos["frecuencia_ubicacion_previa"] = _frecuencia_previa(datos, "ubicacion", n_previas)
        features += ["frecuencia_ubicacion_previa"]
        neutros["frecuencia_ubicacion_previa"] = 0.5

    sin_historial = datos["sin_historial"] == 1
    for columna, neutro in neutros.items():
        datos.loc[sin_historial, columna] = neutro
        datos[columna] = datos[columna].fillna(neutro)

    return datos, features


def perfil_al_momento(datos, id_cuenta, fecha, cuantos=3):
    """Perfil de una tarjeta con todo lo anterior a `fecha` (para el resumen del caso).

    `datos` puede ser el conjunto completo o ya filtrado a esa tarjeta.
    """
    historial = datos[(datos["id_cuenta"] == id_cuenta) & (datos["fecha_hora"] < fecha)]
    n = len(historial)
    perfil = {"n_transacciones_previas": n, "sin_historial": n < MINIMO_HISTORIAL}
    if n == 0:
        return perfil

    dias = max((fecha - historial["fecha_hora"].min()).total_seconds() / 86400, 1)
    perfil["monto_promedio"] = round(float(historial["monto"].mean()), 2)
    perfil["monto_desviacion"] = round(float(historial["monto"].std(ddof=0)), 2)
    perfil["transacciones_por_dia"] = round(n / dias, 2)
    horas = historial["hora"].value_counts(normalize=True).head(cuantos)
    perfil["horas_habituales"] = [
        {"hora": int(hora), "porcentaje": round(100 * float(p), 1)} for hora, p in horas.items()
    ]
    if "categoria" in historial.columns:
        categorias = historial["categoria"].value_counts(normalize=True).head(cuantos)
        perfil["categorias_habituales"] = [
            {"categoria": str(c), "porcentaje": round(100 * float(p), 1)} for c, p in categorias.items()
        ]
    if "ubicacion" in historial.columns and "latitud_domicilio" not in historial.columns:
        ubicaciones = historial["ubicacion"].value_counts(normalize=True).head(cuantos)
        perfil["ubicaciones_habituales"] = [
            {"ubicacion": str(u), "porcentaje": round(100 * float(p), 1)} for u, p in ubicaciones.items()
        ]
    return perfil
