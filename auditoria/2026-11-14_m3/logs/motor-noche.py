"""Auditoría: la noche del 19-jul-2020 (semilla del simulador) con scores fuera de línea.
1) cuadre de la ventana; 2) episodios truncados al inicio y al final; 3) contrafactuales M2/M3 replicando
eval/medir_momento3.py:130-141; 4) qué tan representativa es la noche (todas las ventanas de 36 h del tramo
de prueba que empiezan a las 20:00); 5) población completa del tramo de prueba con IC por bootstrap de tarjetas;
6) fuga: filas del historial M2 en el FUTURO del triaje para las tarjetas que abren caso.
Uso: python motor-noche.py <caché de motor-puntuar.py>
"""
import json
import sys

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
RAIZ = "C:/Users/Jhoan/Desktop/clase_sabado/proyecto-fraude-bancario"
d = pd.read_pickle(sys.argv[1]).sort_values(["fecha_hora", "id_transaccion"]).reset_index(drop=True)
p = json.load(open(f"{RAIZ}/datos/salidas_sparkov/metricas_motor.json", encoding="utf-8"))
UV, UB = p["umbral_verificacion"], p["umbral_bloqueo"]
INI, FIN = pd.Timestamp("2020-07-19 20:00"), pd.Timestamp("2020-07-21 08:00")
COLA = pd.Timedelta(minutes=90)
H48 = pd.Timedelta(hours=48)


def turno(t):
    if 7 <= t.hour < 22:
        return t + COLA
    dia = t.normalize() if t.hour < 7 else t.normalize() + pd.Timedelta(days=1)
    return dia + pd.Timedelta(hours=7)


def perdido(fr, corte):
    return fr.monto.sum() if corte is None else fr.loc[fr.fecha_hora <= corte, "monto"].sum()


# Episodios (separación > 7 días) sobre TODO el dataset
f = d[d.es_fraude == 1].sort_values(["id_cuenta", "fecha_hora"]).copy()
sep = f.groupby("id_cuenta")["fecha_hora"].diff()
f["ep"] = (sep.isna() | (sep > pd.Timedelta(days=7))).cumsum()
f["ini_ep"] = f.groupby("ep")["fecha_hora"].transform("min")
f["fin_ep"] = f.groupby("ep")["fecha_hora"].transform("max")
inicios_ep = f.groupby("ep").ini_ep.first()


def contrafactuales(w):
    """Replica medir_momento3.calcular: marcas = score >= UB dentro de la ventana; % del fraude detenido."""
    total = w.loc[w.es_fraude == 1, "monto"].sum()
    perd = {"m2_instante": 0.0, "m2_cola90": 0.0, "m2_noche": 0.0, "bloquear_1a_marca": 0.0}
    for _, c in w.groupby("id_cuenta"):
        fr = c[c.es_fraude == 1]
        if fr.empty:
            continue
        marcas = c.loc[c.score >= UB, "fecha_hora"].tolist()
        dos = marcas[1] if len(marcas) >= 2 else None
        perd["m2_instante"] += perdido(fr, dos)
        perd["m2_cola90"] += perdido(fr, dos + COLA if dos is not None else None)
        perd["m2_noche"] += perdido(fr, turno(dos) if dos is not None else None)
        perd["bloquear_1a_marca"] += perdido(fr, marcas[0] if marcas else None)
    res = {"fraude_total": round(total, 2)}
    for k, v in perd.items():
        res[k] = round(100 * (1 - v / total), 1) if total else None
    return res


w = d[(d.fecha_hora >= INI) & (d.fecha_hora < FIN)]
print(f"[1] ventana: {len(w)} compras, {w.id_cuenta.nunique()} tarjetas, {int(w.es_fraude.sum())} fraudulentas, "
      f"{w.loc[w.es_fraude == 1, 'monto'].sum():,.2f} USD, {w.loc[w.es_fraude == 1, 'id_cuenta'].nunique()} tarjetas con fraude")
print("[3] contrafactuales con scores fuera de línea (% del monto fraudulento detenido):", contrafactuales(w))
print("    JSON del M3: m2_instante 61.8, m2_cola90 34.9, m2_noche 29.3, M3 71.4, IA caída 61.8")

print("\n[2] episodios de las tarjetas con fraude en la ventana")
eps = set(f.loc[f.id_transaccion.isin(w.id_transaccion), "ep"])
fw = f[f.ep.isin(eps)]
tot = {"antes": 0.0, "dentro": 0.0, "despues": 0.0}
for c, g in fw.groupby("id_cuenta"):
    partes = {"antes": g[g.fecha_hora < INI], "dentro": g[(g.fecha_hora >= INI) & (g.fecha_hora < FIN)],
              "despues": g[g.fecha_hora >= FIN]}
    for k, v in partes.items():
        tot[k] += v.monto.sum()
    cw = w[w.id_cuenta == c]
    marcas = cw.loc[cw.score >= UB, "fecha_hora"].tolist()
    pf = partes["dentro"].fecha_hora.min()
    sc = cw.loc[cw.fecha_hora == pf, "score"].iloc[0]
    print(f"  ...{c[-4:]} episodio {g.ini_ep.iloc[0]} a {g.fin_ep.iloc[0]}: "
          + ", ".join(f"{k} {len(v)} ({v.monto.sum():,.0f} USD)" for k, v in partes.items())
          + f"; score 1.a fraudulenta en ventana {sc:.3f}; marcas>=UB {len(marcas)}; 1.a marca {marcas[0] if marcas else None}")
print("  totales del episodio: " + ", ".join(f"{k} {v:,.0f} USD" for k, v in tot.items()))
print(f"  episodios que empiezan dentro de la ventana: {int(inicios_ep.loc[list(eps)].between(INI, FIN).sum())} de {len(eps)}")

print("\n[4] todas las ventanas de 36 h que empiezan a las 20:00 en el tramo de prueba")
filas = []
primer = d.loc[d.tramo_origen == "prueba", "fecha_hora"].min().normalize() + pd.Timedelta(days=1, hours=20)
for ini in pd.date_range(primer, pd.Timestamp("2020-12-30 20:00"), freq="D"):
    v = d[(d.fecha_hora >= ini) & (d.fecha_hora < ini + pd.Timedelta(hours=36))]
    if v.es_fraude.sum() == 0:
        continue
    r = contrafactuales(v)
    r.update(inicio=ini, compras=len(v), tarjetas_fraude=v.loc[v.es_fraude == 1, "id_cuenta"].nunique(),
             episodios_empiezan=int(inicios_ep.between(ini, ini + pd.Timedelta(hours=36)).sum()))
    filas.append(r)
t = pd.DataFrame(filas)
t.to_csv(f"{RAIZ}/auditoria/2026-11-14_m3/logs/motor-ventanas_36h.csv", index=False)
fila_19 = t[t.inicio == INI].iloc[0]
print(f"  {len(t)} ventanas con fraude. Episodios que empiezan: max {t.episodios_empiezan.max()}, 19-jul = "
      f"{fila_19.episodios_empiezan} (ventanas con más: {(t.episodios_empiezan > fila_19.episodios_empiezan).sum()}, "
      f"empatadas: {(t.episodios_empiezan == fila_19.episodios_empiezan).sum() - 1})")
for k in ("m2_instante", "bloquear_1a_marca", "m2_cola90", "m2_noche"):
    q = t[k].quantile([.1, .5, .9]).round(1).tolist()
    print(f"  {k:18}: p10/mediana/p90 = {q}; 19-jul = {fila_19[k]}")
dif = (t.bloquear_1a_marca - t.m2_instante)
print(f"  margen máximo atribuible al agente (1.a marca - 2.a marca): mediana {dif.median():.1f} pts, "
      f"p10 {dif.quantile(.1):.1f}, p90 {dif.quantile(.9):.1f}; 19-jul = {fila_19.bloquear_1a_marca - fila_19.m2_instante:.1f}")

print("\n[5] población: tarjetas con fraude del tramo de prueba, episodio completo (sin truncar)")
pr = d[d.tramo_origen == "prueba"]
tarj = pr.loc[pr.es_fraude == 1, "id_cuenta"].unique()
reg = []
for c in tarj:
    cw = pr[pr.id_cuenta == c]
    fr = cw[cw.es_fraude == 1]
    a, b = fr.fecha_hora.min() - H48, fr.fecha_hora.max()
    marcas = cw.loc[(cw.score >= UB) & cw.fecha_hora.between(a, b), "fecha_hora"].tolist()
    m2 = next((marcas[i] for i in range(1, len(marcas)) if marcas[i] - marcas[i - 1] <= H48), None)
    reg.append(dict(c=c, total=fr.monto.sum(), b1=perdido(fr, marcas[0] if marcas else None), b2=perdido(fr, m2),
                    b2c=perdido(fr, m2 + COLA if m2 is not None else None),
                    b2n=perdido(fr, turno(m2) if m2 is not None else None),
                    marcada=bool(marcas), critica=m2 is not None))
r = pd.DataFrame(reg)
rng = np.random.default_rng(7)
for k, nombre in (("b1", "bloquear en la 1.a marca (techo del M3: el agente bloquea toda la banda alta)"),
                  ("b2", "bloquear en la 2.a marca al instante (= IA caída = M2 con analista instantáneo)"),
                  ("b2c", "M2 con cola de 90 min"), ("b2n", "M2 de noche sin turno")):
    est = 100 * (1 - r[k].sum() / r.total.sum())
    bs = []
    for _ in range(1000):
        s = r.iloc[rng.integers(0, len(r), len(r))]
        bs.append(100 * (1 - s[k].sum() / s.total.sum()))
    print(f"  {nombre}: {est:.1f} % detenido [IC 95 % {np.percentile(bs, 2.5):.1f}, {np.percentile(bs, 97.5):.1f}]")
print(f"  tarjetas con fraude: {len(r)}; con alguna marca: {r.marcada.sum()}; que llegan a crítica: {r.critica.sum()}")
hon = pr[~pr.id_cuenta.isin(tarj)]
ev1 = ev2 = 0
for c, cw in hon[hon.score >= UB].groupby("id_cuenta"):
    ts = cw.fecha_hora.tolist()
    ev1 += 1
    ev2 += any(ts[i] - ts[i - 1] <= H48 for i in range(1, len(ts)))
print(f"  tarjetas honestas con >=1 marca: {ev1}; con 2 marcas en 48 h (bloqueo obligatorio falso): {ev2}; "
      f"compras del tramo {len(pr):,} -> {1000 * ev2 / len(pr):.3f} tarjetas falsas por 1.000 compras (la noche: 0,17)")
print(f"  precisión por tarjeta de la banda crítica: {r.critica.sum() / (r.critica.sum() + ev2):.3f}; "
      f"recall por tarjeta: {r.critica.mean():.3f}")
print(f"  'bloquear siempre en alta': precisión por tarjeta {r.marcada.sum() / (r.marcada.sum() + ev1):.3f}, "
      f"falsos {1000 * ev1 / len(pr):.3f} por 1.000")

print("\n[6] fuga de futuro en obtener_historial (repositorio.py:278-281): filas del historial M2 en (t_apertura, t_apertura + 48 h]")
h2 = pd.read_csv(f"{RAIZ}/semilla/historial.csv.gz", dtype={"id_cuenta": str, "id_transaccion": str})
h2 = h2[h2.fuente == "sparkov"].copy()
h2["fecha_hora"] = pd.to_datetime(h2.fecha_hora)
lab = dict(zip(d.id_transaccion, d.es_fraude))
abre = w[w.score >= UV].groupby("id_cuenta").fecha_hora.min()
alta = w[w.score >= UB].groupby("id_cuenta").fecha_hora.min()
n_con_fuga = 0
for c, t0 in abre.items():
    fut = h2[(h2.id_cuenta == c) & (h2.fecha_hora > t0) & (h2.fecha_hora <= t0 + H48)]
    fr_w = int(w.loc[w.id_cuenta == c, "es_fraude"].sum())
    n_fr = int(sum(lab.get(x, 0) for x in fut.id_transaccion))
    n_con_fuga += len(fut) > 0
    print(f"  ...{c[-4:]} abre caso {t0} (1.a marca de bloqueo {alta.get(c)}) compras fraudulentas en ventana={fr_w}: "
          f"{len(fut)} filas futuras visibles para el agente, {n_fr} fraudulentas")
print(f"  tarjetas que abren caso: {len(abre)}; con filas futuras visibles: {n_con_fuga}")
