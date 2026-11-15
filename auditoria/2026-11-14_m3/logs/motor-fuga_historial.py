"""Auditoría: ¿el historial del M2 (semilla/historial.csv.gz) mete compras FUTURAS de las tarjetas del simulador?

obtener_historial (app/db/repositorio.py:258) devuelve filas de `historial` con fecha <= fin_ventana del caso
(primera marca + 48 h) y prioriza las más recientes. reiniciar_en_vivo no borra las filas de origen semilla.
Este script cuenta, por tarjeta del simulador, las filas del historial del M2 con fecha >= inicio de la ventana.
Solo lee archivos de semilla/; no toca la base.
"""
import gzip, json, sys
import pandas as pd
sys.stdout.reconfigure(encoding="utf-8")
RAIZ = "C:/Users/Jhoan/Desktop/clase_sabado/proyecto-fraude-bancario"
with gzip.open(f"{RAIZ}/semilla/simulador_sparkov.json.gz", "rt", encoding="utf-8") as f:
    sim = json.load(f)
print("resumen semilla simulador:", sim["resumen"])
tx = pd.DataFrame(sim["transacciones"]); tx["fecha_hora"] = pd.to_datetime(tx["fecha_hora"])
inicio = pd.Timestamp(sim["resumen"]["inicio"]); fin = pd.Timestamp(sim["resumen"]["fin"])
h2 = pd.read_csv(f"{RAIZ}/semilla/historial.csv.gz", dtype={"id_cuenta": str, "id_transaccion": str})
h2 = h2[h2["fuente"] == "sparkov"]; h2["fecha_hora"] = pd.to_datetime(h2["fecha_hora"])
hs = pd.read_csv(f"{RAIZ}/semilla/historial_simulador.csv.gz", dtype={"id_cuenta": str, "id_transaccion": str})
hs["fecha_hora"] = pd.to_datetime(hs["fecha_hora"])
print(f"historial simulador: max fecha {hs['fecha_hora'].max()} (inicio ventana {inicio})")
tarjetas = set(tx["id_cuenta"]); fraude = set(tx.loc[tx.es_fraude == 1, "id_cuenta"])
comun = tarjetas & set(h2["id_cuenta"])
futuras = h2[h2["id_cuenta"].isin(tarjetas) & (h2["fecha_hora"] >= inicio)]
print(f"tarjetas del simulador: {len(tarjetas)}; con historial del M2: {len(comun)}; con fraude en la ventana: {len(fraude)}")
print(f"filas del historial M2 con fecha >= inicio de la ventana para tarjetas del simulador: {len(futuras)} "
      f"en {futuras['id_cuenta'].nunique()} tarjetas")
# Etiqueta de esas filas futuras (desde el CSV completo)
datos = pd.concat([pd.read_csv(f"{RAIZ}/datos/{n}", usecols=["trans_num", "cc_num", "is_fraud"], dtype={"cc_num": str})
                   for n in ("fraudTrain.csv", "fraudTest.csv")])
etiqueta = dict(zip(datos["trans_num"], datos["is_fraud"]))
futuras = futuras.assign(es_fraude=futuras["id_transaccion"].map(etiqueta))
casos = json.load(open(f"{RAIZ}/semilla/casos_sparkov.json", encoding="utf-8"))
casos = casos["casos"] if isinstance(casos, dict) else casos
for c in sorted(futuras["id_cuenta"].unique()):
    f = futuras[futuras.id_cuenta == c]
    m2 = [(k["id_caso"], k["inicio_ventana"], k["fin_ventana"]) for k in casos if k["id_cuenta"] == c]
    print(f"  tarjeta …{c[-4:]} fraude_en_ventana={c in fraude}: {len(f)} filas futuras "
          f"({int(f.es_fraude.sum())} fraude), {f.fecha_hora.min()} a {f.fecha_hora.max()}; casos M2: {m2}")
# Para cada tarjeta con fraude: primera compra en la ventana con fraude
for c in sorted(fraude):
    t = tx[(tx.id_cuenta == c)]
    print(f"  fraude …{c[-4:]}: compras fraudulentas en ventana {int(t.es_fraude.sum())}, "
          f"primera {t.loc[t.es_fraude==1,'fecha_hora'].min()}, en historial M2: {c in comun}")
