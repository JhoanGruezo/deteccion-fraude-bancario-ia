"""Auditoría: viaje imposible en Sparkov (vectorizado, misma fórmula y límite que src/detectar_viaje_imposible.py)
y anchura de los intervalos de la noche. Uso: python motor-viaje.py <caché de motor-puntuar.py>"""
import sys

import numpy as np
import pandas as pd
from scipy.stats import beta

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, "C:/Users/Jhoan/Desktop/clase_sabado/proyecto-fraude-bancario/src")
from perfil_cuenta import distancia_km_vectorizada  # noqa: E402

d = pd.read_pickle(sys.argv[1]).sort_values(["id_cuenta", "fecha_hora"]).reset_index(drop=True)
mismo = d.id_cuenta.eq(d.id_cuenta.shift())
horas = (d.fecha_hora - d.fecha_hora.shift()).dt.total_seconds() / 3600
dist = distancia_km_vectorizada(d.latitud.shift(), d.longitud.shift(), d.latitud, d.longitud)
alerta = mismo & (horas > 0) & (dist / horas > 900)
cero = mismo & (horas == 0) & (dist > 0)
pr = d.tramo_origen == "prueba"
# El detector por lotes corre solo sobre el tramo de prueba: el primer par de cada tarjeta en prueba no cuenta
primera_en_prueba = pr & ~(pr.shift(fill_value=False) & mismo)
a_pr = alerta & pr & ~primera_en_prueba
print(f"alertas en prueba: {int(a_pr.sum()):,} en {d.loc[a_pr, 'id_cuenta'].nunique()} tarjetas "
      f"({100 * a_pr.sum() / pr.sum():.2f} % de las compras); de ellas fraude: {int(d.loc[a_pr, 'es_fraude'].sum())}")
print(f"pares con 0 segundos y distancia > 0 (el detector los IGNORA por 'horas > 0'): {int(cero.sum())} en todo Sparkov")
print(f"distancia mediana de las alertas {np.median(dist[a_pr]):.0f} km, separación mediana {np.median(horas[a_pr]) * 60:.1f} min")
w = (d.fecha_hora >= "2020-07-19 20:00") & (d.fecha_hora < "2020-07-21 08:00")
print(f"en la noche del 19-jul: {int((alerta & w).sum())} alertas en {d.loc[alerta & w, 'id_cuenta'].nunique()} tarjetas "
      f"(si abrieran caso crítico serían bloqueos obligatorios)")


def wilson(k, n, z=1.96):
    p = k / n
    c = (p + z * z / (2 * n)) / (1 + z * z / n)
    m = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return round(c - m, 3), round(c + m, 3)


print("\nIntervalos de la noche (Wilson para proporciones, Poisson exacto para 1 evento):")
print(f"  precisión de bloqueos 9/10: {wilson(9, 10)}; recall 9/9: {wilson(9, 9)}")
print(f"  agente en banda alta: precisión 3/3 {wilson(3, 3)}, recall 3/5 {wilson(3, 5)}, 'bloquear siempre' 5/13 {wilson(5, 13)}")
lo, hi = beta.ppf(0.025, 1, 1) if False else 0.0253, 5.572   # Poisson exacto para k=1: [0,0253; 5,572]
print(f"  1 bloqueo falso en 5.810 compras: {1000 / 5810:.2f} por 1.000, IC [{1000 * lo / 5810:.3f}, {1000 * hi / 5810:.2f}]")
