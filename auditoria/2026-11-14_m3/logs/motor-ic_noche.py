"""Auditoría: IC por bootstrap de TARJETAS (9) para las cifras de dinero de la noche, con scores fuera de línea."""
import json, sys
import numpy as np, pandas as pd
sys.stdout.reconfigure(encoding="utf-8")
d = pd.read_pickle(sys.argv[1])
UB = json.load(open("C:/Users/Jhoan/Desktop/clase_sabado/proyecto-fraude-bancario/datos/salidas_sparkov/metricas_motor.json"))["umbral_bloqueo"]
w = d[(d.fecha_hora >= "2020-07-19 20:00") & (d.fecha_hora < "2020-07-21 08:00")].sort_values("fecha_hora")
filas = []
for c, g in w.groupby("id_cuenta"):
    fr = g[g.es_fraude == 1]
    if fr.empty: continue
    m = g.loc[g.score >= UB, "fecha_hora"].tolist()
    lost = lambda t: fr.monto.sum() if t is None else fr.loc[fr.fecha_hora <= t, "monto"].sum()
    filas.append((c[-4:], fr.monto.sum(), lost(m[0] if m else None), lost(m[1] if len(m) > 1 else None)))
r = pd.DataFrame(filas, columns=["tarjeta", "total", "p1", "p2"])
r["dif_usd"] = r.p2 - r.p1
print(r.round(2).to_string(index=False))
rng = np.random.default_rng(7)
for k, n in (("p2", "2.a marca (IA caída, 61,8 %)"), ("p1", "1.a marca (techo, 79,6 %)")):
    bs = [100 * (1 - s[k].sum() / s.total.sum()) for s in (r.iloc[rng.integers(0, len(r), len(r))] for _ in range(5000))]
    print(f"{n}: IC 95 % por tarjeta [{np.percentile(bs, 2.5):.1f}, {np.percentile(bs, 97.5):.1f}]")
print(f"la diferencia 1.a vs 2.a marca se concentra en: {r.sort_values('dif_usd', ascending=False).head(3)[['tarjeta','dif_usd']].values.tolist()}")
