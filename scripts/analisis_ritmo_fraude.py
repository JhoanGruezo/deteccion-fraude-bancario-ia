"""Ritmo del fraude en Sparkov: cuánto tiempo hay para actuar después de la primera compra robada.

Produce las cifras de docs/analisis-respuesta-fraude.md (secciones 2 y 3):
- cómo se reparte en el tiempo un episodio de fraude (compras, duración, minutos entre compras);
- cuánto se pierde si la tarjeta se bloquea X minutos después de la primera compra fraudulenta;
- a qué hora empieza el fraude;
- cuánto dinero dejaba pasar la regla del Momento 2, que abría el caso en la SEGUNDA compra marcada.

Uso, desde la raíz:  python scripts/analisis_ritmo_fraude.py
Necesita datos/fraudTrain.csv y datos/fraudTest.csv (Kaggle, no van al repositorio) y semilla/.
"""

import json
import os
import sys

import pandas as pd

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COLUMNAS = ["trans_date_trans_time", "cc_num", "amt", "is_fraud"]
SEPARACION_EPISODIOS = pd.Timedelta(days=7)   # dos fraudes de la misma tarjeta a más de 7 días son episodios distintos
RETRASOS_MINUTOS = [0, 1, 5, 15, 30, 60, 120, 240, 480, 1440]


def cargar_fraudes():
    rutas = [os.path.join(RAIZ, "datos", nombre) for nombre in ("fraudTrain.csv", "fraudTest.csv")]
    faltantes = [r for r in rutas if not os.path.exists(r)]
    if faltantes:
        sys.exit(f"Faltan los archivos de Sparkov: {', '.join(faltantes)}")
    datos = pd.concat([pd.read_csv(r, usecols=COLUMNAS) for r in rutas])
    datos["fecha_hora"] = pd.to_datetime(datos["trans_date_trans_time"])
    fraudes = datos[datos["is_fraud"] == 1].sort_values(["cc_num", "fecha_hora"]).copy()
    fraudes["separacion"] = fraudes.groupby("cc_num")["fecha_hora"].diff()
    fraudes["nuevo_episodio"] = fraudes["separacion"].isna() | (fraudes["separacion"] > SEPARACION_EPISODIOS)
    fraudes["episodio"] = fraudes["nuevo_episodio"].cumsum()
    fraudes["inicio_episodio"] = fraudes.groupby("episodio")["fecha_hora"].transform("min")
    fraudes["minutos_desde_inicio"] = (fraudes["fecha_hora"] - fraudes["inicio_episodio"]).dt.total_seconds() / 60
    return fraudes


def ritmo(fraudes):
    episodios = fraudes.groupby("episodio")
    compras = episodios.size()
    duracion_h = episodios["fecha_hora"].agg(lambda s: (s.max() - s.min()).total_seconds() / 3600)
    entre = fraudes.loc[~fraudes["nuevo_episodio"], "separacion"].dt.total_seconds() / 60
    print(f"Tarjetas con fraude: {fraudes['cc_num'].nunique()} · episodios: {fraudes['episodio'].nunique()} · "
          f"compras fraudulentas: {len(fraudes)} · monto: {fraudes['amt'].sum():,.2f} USD")
    print(f"Compras por episodio: mediana {compras.median():g} (p25 {compras.quantile(.25):g}, p75 {compras.quantile(.75):g})")
    print(f"Duración del episodio: mediana {duracion_h.median():.1f} h")
    print(f"Minutos entre compras fraudulentas: mediana {entre.median():.1f}, p25 {entre.quantile(.25):.1f}, "
          f"p10 {entre.quantile(.10):.1f}; < 5 min: {(entre < 5).mean() * 100:.1f} %; < 60 min: {(entre < 60).mean() * 100:.1f} %")

    total = fraudes["amt"].sum()
    print("\nBloqueo X minutos después de la primera compra fraudulenta:")
    for minutos in RETRASOS_MINUTOS:
        perdido = fraudes.loc[fraudes["minutos_desde_inicio"] <= minutos, "amt"].sum() / total * 100
        print(f"  {minutos:>5} min → se pierde {perdido:5.1f} %, se salva {100 - perdido:5.1f} %")

    hora_inicio = episodios["fecha_hora"].min().dt.hour
    nocturno = ((hora_inicio >= 22) | (hora_inicio < 6)).mean() * 100
    print(f"\nEpisodios que empiezan entre las 22:00 y las 06:00: {nocturno:.1f} %")


def regla_momento2():
    """En la semilla: cuánto pasa entre la 1.ª y la 2.ª compra sobre el umbral de bloqueo."""
    with open(os.path.join(RAIZ, "semilla", "casos_sparkov.json"), encoding="utf-8") as archivo:
        casos = json.load(archivo)
    casos = casos["casos"] if isinstance(casos, dict) else casos
    minutos, total, tras_primera, tras_segunda = [], 0.0, 0.0, 0.0
    for caso in casos:
        transacciones = sorted(caso["transacciones"], key=lambda t: t["fecha_hora"])
        sobre = [pd.Timestamp(t["fecha_hora"]) for t in transacciones if t["score"] >= caso["umbral_bloqueo"]]
        if not sobre:
            continue
        for t in transacciones:
            momento, monto = pd.Timestamp(t["fecha_hora"]), float(t["monto"])
            total += monto
            tras_primera += monto if momento > sobre[0] else 0
            tras_segunda += monto if len(sobre) > 1 and momento > sobre[1] else 0
        if len(sobre) > 1:
            minutos.append((sobre[1] - sobre[0]).total_seconds() / 60)
    serie = pd.Series(minutos)
    print(f"\nRegla del Momento 2 ({len(casos)} casos de Sparkov en la semilla):")
    print(f"  minutos entre la 1.ª y la 2.ª compra marcada: mediana {serie.median():.1f}, p25 {serie.quantile(.25):.1f}")
    print(f"  dinero que pasa entre las dos marcas: {tras_primera - tras_segunda:,.0f} USD "
          f"({(tras_primera - tras_segunda) / total * 100:.1f} % del monto marcado)")


if __name__ == "__main__":
    ritmo(cargar_fraudes())
    regla_momento2()
