"""Auditoría: recálculo independiente de las cifras de docs/analisis-respuesta-fraude.md (88 %, 7,8 %, 58,2 %, 13 %).
No reutiliza scripts/analisis_ritmo_fraude.py; lee los CSV y la semilla directamente."""
import json, sys
import numpy as np, pandas as pd
sys.stdout.reconfigure(encoding="utf-8")
RAIZ = "C:/Users/Jhoan/Desktop/clase_sabado/proyecto-fraude-bancario"
d = pd.concat([pd.read_csv(f"{RAIZ}/datos/{n}", usecols=["trans_date_trans_time", "cc_num", "amt", "is_fraud"])
               for n in ("fraudTrain.csv", "fraudTest.csv")])
d["t"] = pd.to_datetime(d["trans_date_trans_time"])
f = d[d.is_fraud == 1].sort_values(["cc_num", "t"]).copy()
print(f"tarjetas con fraude {f.cc_num.nunique()}, compras {len(f)}, monto {f.amt.sum():,.2f}")
for gap_dias in (7, None):
    g = f.copy()
    sep = g.groupby("cc_num")["t"].diff()
    nuevo = sep.isna() if gap_dias is None else (sep.isna() | (sep > pd.Timedelta(days=gap_dias)))
    g["ep"] = nuevo.cumsum()
    g["ini"] = g.groupby("ep")["t"].transform("min")
    g["min"] = (g["t"] - g["ini"]).dt.total_seconds() / 60
    ep = g.groupby("ep")
    hi = ep["t"].min().dt.hour
    print(f"\n[episodios con separación {gap_dias} días] n={g.ep.nunique()}")
    print(f"  episodios que empiezan 22-06: {((hi >= 22) | (hi < 6)).mean()*100:.1f} %  "
          f"(22-04: {((hi >= 22) | (hi < 4)).mean()*100:.1f} %)")
    for m in (0, 5, 15, 60, 90, 120, 480, 1440):
        print(f"  bloqueo a {m:>5} min de la 1.a compra: se pierde {g.loc[g['min'] <= m, 'amt'].sum()/g.amt.sum()*100:5.1f} %")
# Otras lecturas de "el fraude es nocturno"
h = f["t"].dt.hour
print(f"\ncompras fraudulentas 22-06: {((h>=22)|(h<6)).mean()*100:.1f} %; monto fraudulento 22-06: "
      f"{f.loc[(h>=22)|(h<6),'amt'].sum()/f.amt.sum()*100:.1f} %")
hl = d.loc[d.is_fraud == 0, "t"].dt.hour
print(f"compras legítimas 22-06 (referencia): {((hl>=22)|(hl<6)).mean()*100:.1f} %")
# 13 % de la regla M2 (semilla)
casos = json.load(open(f"{RAIZ}/semilla/casos_sparkov.json", encoding="utf-8"))
casos = casos["casos"] if isinstance(casos, dict) else casos
lab = dict(zip(*[pd.concat([pd.read_csv(f"{RAIZ}/datos/{n}", usecols=["trans_num", "is_fraud"]) for n in ("fraudTrain.csv","fraudTest.csv")])[c] for c in ("trans_num","is_fraud")]))
tot = entre = tot_f = entre_f = entre_excl = 0.0; mins = []
for c in casos:
    tx = sorted(c["transacciones"], key=lambda t: t["fecha_hora"])
    marcas = [pd.Timestamp(t["fecha_hora"]) for t in tx if t["score"] >= c["umbral_bloqueo"]]
    if not marcas: continue
    for t in tx:
        m, a, fr = pd.Timestamp(t["fecha_hora"]), float(t["monto"]), lab.get(t["id_transaccion"], 0)
        tot += a; tot_f += a * fr
        if m > marcas[0] and (len(marcas) < 2 or m <= marcas[1]):
            entre += a; entre_f += a * fr
            if len(marcas) > 1 and m < marcas[1]: entre_excl += a
    if len(marcas) > 1: mins.append((marcas[1] - marcas[0]).total_seconds() / 60)
s = pd.Series(mins)
print(f"\nRegla M2 ({len(casos)} casos): min entre 1.a y 2.a marca mediana {s.median():.1f}, p25 {s.quantile(.25):.1f}")
print(f"  monto entre 1.a marca (excl.) y 2.a marca (incl.): {entre:,.0f} USD = {entre/tot*100:.1f} % del monto de las compras marcadas de los casos")
print(f"  sin contar la 2.a marca misma: {entre_excl:,.0f} USD = {entre_excl/tot*100:.1f} %")
print(f"  solo fraude: {entre_f:,.0f} USD = {entre_f/tot_f*100:.1f} % del monto fraudulento marcado")
