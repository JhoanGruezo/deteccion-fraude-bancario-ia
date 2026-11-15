"""Auditoría: paridad del score en vivo contra el motor por lotes EN LA NOCHE MEDIDA (5.810 compras).
Recorre la ventana con los perfiles de semilla/simulador_sparkov.json.gz y app/riesgo (perfil_incremental +
MotorEnVivo.evaluar), sin bloqueos ni base de datos, y compara score y banda contra el score por lotes del caché.
Uso: python motor-paridad_noche.py <caché de motor-puntuar.py>
"""
import gzip
import json
import sys

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
RAIZ = "C:/Users/Jhoan/Desktop/clase_sabado/proyecto-fraude-bancario"
sys.path.insert(0, RAIZ)
import app.riesgo  # noqa: E402,F401
from app.riesgo.motor_en_vivo import MotorEnVivo  # noqa: E402
from app.riesgo.perfil_incremental import EstadoTarjeta, actualizar  # noqa: E402

lotes = pd.read_pickle(sys.argv[1]).set_index("id_transaccion")["score"]
motor = MotorEnVivo(f"{RAIZ}/semilla/modelo_riesgo_sparkov.joblib")
with gzip.open(f"{RAIZ}/semilla/simulador_sparkov.json.gz", "rt", encoding="utf-8") as archivo:
    sim = json.load(archivo)
estados = {p["id_cuenta"]: EstadoTarjeta.desde_dict(p["estado"]) for p in sim["perfiles"]}


def banda(s):
    return "bloqueo" if s >= motor.umbral_bloqueo else "verificacion" if s >= motor.umbral_verificacion else "nada"


dif, cambios, lat = [], 0, []
for t in sim["transacciones"]:
    e = estados[t["id_cuenta"]]
    r = motor.evaluar(e, t, con_senales=False)
    s_lote = float(lotes[t["id_transaccion"]])
    dif.append(abs(r["score"] - s_lote))
    cambios += banda(r["score"]) != banda(s_lote)
    lat.append(r["latencia_puntuacion_ms"])
    actualizar(e, t)
dif = np.array(dif)
print(f"compras comparadas: {len(dif)}; diferencia máx {dif.max():.2e}; > 0,001: {(dif > 1e-3).sum()}; cambios de banda: {cambios}")
print(f"latencia de puntuar (esta máquina): mediana {np.median(lat):.2f} ms, p99 {np.percentile(lat, 99):.2f} ms")
