"""Auditoría: puntúa todo Sparkov con el modelo de semilla/ (fuera de línea) y guarda un caché en el scratchpad.
Recalcula además las métricas del motor en prueba (§8) con IC por bootstrap de tarjetas y líneas base alternativas."""
import os, sys, time
import joblib, numpy as np, pandas as pd
from sklearn.metrics import average_precision_score, precision_recall_curve, f1_score, precision_score, recall_score
sys.stdout.reconfigure(encoding="utf-8")
RAIZ = "C:/Users/Jhoan/Desktop/clase_sabado/proyecto-fraude-bancario"
CACHE = sys.argv[1]
sys.path.insert(0, f"{RAIZ}/src")
from cargar_datos import cargar_sparkov
from perfil_cuenta import agregar_features
from motor_riesgo import dividir_temporal

t0 = time.time()
d = cargar_sparkov(f"{RAIZ}/datos/fraudTrain.csv", f"{RAIZ}/datos/fraudTest.csv")
d, feats = agregar_features(d)
p = joblib.load(f"{RAIZ}/semilla/modelo_riesgo_sparkov.joblib")
assert list(p["features"]) == feats
d["score"] = p["modelo"].predict_proba(d[feats])[:, 1]
UV, UB = p["umbral_verificacion"], p["umbral_bloqueo"]
print(f"puntuado en {time.time()-t0:.0f} s; umbral_verificacion={UV:.6f} umbral_bloqueo={UB:.6f}")
ent, val, pru = dividir_temporal(d, "sparkov")
print(f"entrenamiento {ent.fecha_hora.min()} a {ent.fecha_hora.max()}; validacion {val.fecha_hora.min()} a {val.fecha_hora.max()}; "
      f"prueba {pru.fecha_hora.min()} a {pru.fecha_hora.max()}")
print(f"¿19-jul-2020 está en prueba? {pru.fecha_hora.min() <= pd.Timestamp('2020-07-19 20:00') <= pru.fecha_hora.max()}")

def m(y, pred, s=None):
    return dict(precision=round(precision_score(y, pred, zero_division=0), 4), recall=round(recall_score(y, pred), 4),
                f1=round(f1_score(y, pred), 4), auc_pr=round(average_precision_score(y, pred if s is None else s), 4))
y = pru.es_fraude.to_numpy()
print("\nGB en prueba al umbral de bloqueo:", m(y, (pru.score >= UB).astype(int), pru.score))
# IC por bootstrap de TARJETAS (las filas de una tarjeta no son independientes)
rng = np.random.default_rng(7)
grupos = pru.groupby("id_cuenta").indices; claves = list(grupos)
s_arr = pru.score.to_numpy(); aucs, f1s = [], []
for _ in range(200):
    idx = np.concatenate([grupos[claves[i]] for i in rng.integers(0, len(claves), len(claves))])
    aucs.append(average_precision_score(y[idx], s_arr[idx])); f1s.append(f1_score(y[idx], s_arr[idx] >= UB))
print(f"  IC 95 % bootstrap por tarjeta (200): AUC-PR [{np.percentile(aucs,2.5):.3f}, {np.percentile(aucs,97.5):.3f}], "
      f"F1 [{np.percentile(f1s,2.5):.3f}, {np.percentile(f1s,97.5):.3f}]")
umbral_monto = float(ent.monto.quantile(0.95))
regla = ((pru.monto > umbral_monto) | (pru.hora < 6)).astype(int)
print(f"\nRegla reportada (monto > {umbral_monto:.2f} O hora < 6):", m(y, regla), f"marca {regla.mean()*100:.1f} % de las compras")
# Precisión del modelo al MISMO recall que la regla (comparación justa para una regla binaria)
pr, rc, th = precision_recall_curve(y, pru.score)
i = np.where(rc[:-1] >= regla[y == 1].mean())[0][-1]
print(f"  GB a recall {rc[i]:.3f}: precisión {pr[i]:.3f} (la regla: {precision_score(y, regla):.3f})")
# Líneas base menos débiles, con parámetros elegidos en VALIDACIÓN
noche = lambda h: (h >= 22) | (h < 4)
ra = ((pru.monto > umbral_monto) & noche(pru.hora)).astype(int)
print("Regla A (monto > p95 Y hora 22-04):", m(y, ra))
yv = val.es_fraude.to_numpy(); mejor = (0, None)
for q in np.linspace(0.80, 0.999, 200):
    u = float(ent.monto.quantile(q)); f = f1_score(yv, (val.monto > u) & noche(val.hora))
    mejor = max(mejor, (f, u))
rb = ((pru.monto > mejor[1]) & noche(pru.hora)).astype(int)
print(f"Regla B (monto > {mejor[1]:.2f} elegido por F1 en validación, Y hora 22-04):", m(y, rb))
mejor = (0, None)
for q in np.linspace(0.80, 0.999, 200):
    u = float(ent.monto.quantile(q)); mejor = max(mejor, (f1_score(yv, val.monto > u), u))
print(f"Regla C (solo monto > {mejor[1]:.2f}, F1 en validación):", m(y, (pru.monto > mejor[1]).astype(int)))
print(f"AUC-PR del monto solo como score continuo: {average_precision_score(y, pru.monto):.4f}")
cols = ["id_transaccion", "id_cuenta", "fecha_hora", "monto", "hora", "es_fraude", "tramo_origen", "score", "sin_historial",
        "categoria", "latitud", "longitud", "latitud_domicilio", "longitud_domicilio"]
d[cols].to_pickle(CACHE)
print(f"\ncaché: {CACHE} ({time.time()-t0:.0f} s)")
