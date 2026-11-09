"""Genera la semilla del simulador en vivo (SPEC, RF8): un tramo real de Sparkov para reproducir.

Qué produce, en semilla/:

- `simulador_sparkov.json.gz`: la ventana elegida, el perfil acumulado de cada tarjeta que
  compra en ella (calculado con TODA su historia anterior, con el mismo código que usa la app,
  `app/riesgo/perfil_incremental.py`) y las transacciones de la ventana en orden, con su
  etiqueta del dataset para poder medir después.
- `historial_simulador.csv.gz`: los 30 días anteriores de esas tarjetas, para que el agente
  pueda narrar la secuencia de un caso nuevo igual que en uno de la semilla del M2.

Ventana por defecto: del 19 de julio de 2020 a las 20:00 a las 08:00 del 21 (36 h). Está en
la partición de PRUEBA (el modelo nunca la vio) y es la que más episodios de fraude ve
empezar entre las candidatas revisadas: 5 episodios, 54 compras fraudulentas y 28.367 USD en
5.810 transacciones de 875 tarjetas. Empieza de noche, que es cuando empieza el 88 % del fraude.

Uso, desde la raíz:  python scripts/generar_semilla_simulador.py [--inicio "2020-07-19 20:00"] [--horas 36]
Necesita datos/fraudTrain.csv y datos/fraudTest.csv.
"""

import argparse
import csv
import gzip
import json
import os
import sys
import time

import pandas as pd

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

import app.riesgo  # noqa: E402,F401 — agrega src/ a la ruta
from app.riesgo.perfil_incremental import EstadoTarjeta, actualizar  # noqa: E402
from cargar_datos import cargar_sparkov  # noqa: E402

CARPETA_SEMILLA = os.path.join(RAIZ, "semilla")
DIAS_HISTORIAL = 30
COLUMNAS_HISTORIAL = ("fuente", "id_cuenta", "id_transaccion", "fecha_hora", "monto", "categoria", "comercio", "ubicacion")
CAMPOS_COMPRA = ("fecha_hora", "monto", "categoria", "latitud", "longitud")


def _texto_fecha(valor):
    return pd.Timestamp(valor).strftime("%Y-%m-%d %H:%M:%S")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    argumentos = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    argumentos.add_argument("--inicio", default="2020-07-19 20:00")
    argumentos.add_argument("--horas", type=float, default=36)
    opciones = argumentos.parse_args()
    inicio_ventana = pd.Timestamp(opciones.inicio)
    fin_ventana = inicio_ventana + pd.Timedelta(hours=opciones.horas)

    reloj = time.monotonic()
    datos = cargar_sparkov(os.path.join(RAIZ, "datos", "fraudTrain.csv"), os.path.join(RAIZ, "datos", "fraudTest.csv"))
    # Mismo orden que src/perfil_cuenta.agregar_features: así el perfil es idéntico al del motor.
    datos = datos.sort_values(["fecha_hora", "id_transaccion"]).reset_index(drop=True)
    en_ventana = datos[(datos["fecha_hora"] >= inicio_ventana) & (datos["fecha_hora"] < fin_ventana)]
    tarjetas = sorted(en_ventana["id_cuenta"].unique())
    previas = datos[(datos["fecha_hora"] < inicio_ventana) & datos["id_cuenta"].isin(tarjetas)]
    print(f"Sparkov cargado ({len(datos):,} filas) en {time.monotonic() - reloj:.0f} s; "
          f"{len(tarjetas)} tarjetas compran en la ventana; {len(previas):,} compras previas para sus perfiles.")

    perfiles = []
    por_tarjeta = dict(tuple(previas.groupby("id_cuenta", sort=False)))
    domicilios = en_ventana.groupby("id_cuenta")[["latitud_domicilio", "longitud_domicilio"]].first()
    for numero, id_cuenta in enumerate(tarjetas, start=1):
        latitud, longitud = domicilios.loc[id_cuenta]
        estado = EstadoTarjeta(str(id_cuenta), float(latitud), float(longitud))
        historia = por_tarjeta.get(id_cuenta)
        if historia is not None:
            for fila in historia[list(CAMPOS_COMPRA)].itertuples(index=False):
                actualizar(estado, fila._asdict())
        perfiles.append({"alias": f"TAR-{numero:04d}", "id_cuenta": str(id_cuenta), "estado": estado.a_dict()})

    transacciones = [{
        "id_transaccion": str(f.id_transaccion), "id_cuenta": str(f.id_cuenta), "fecha_hora": _texto_fecha(f.fecha_hora),
        "monto": round(float(f.monto), 2), "categoria": f.categoria, "comercio": f.comercio, "ubicacion": f.ubicacion,
        "latitud": float(f.latitud), "longitud": float(f.longitud), "es_fraude": int(f.es_fraude),
    } for f in en_ventana.itertuples(index=False)]

    fraudes = en_ventana[en_ventana["es_fraude"] == 1]
    resumen = {
        "fuente": "sparkov", "inicio": _texto_fecha(inicio_ventana), "fin": _texto_fecha(fin_ventana),
        "transacciones": len(transacciones), "tarjetas": len(tarjetas),
        "compras_fraudulentas": len(fraudes), "monto_fraude_usd": round(float(fraudes["monto"].sum()), 2),
        "tarjetas_con_fraude": int(fraudes["id_cuenta"].nunique()),
        "generado": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    os.makedirs(CARPETA_SEMILLA, exist_ok=True)
    with gzip.open(os.path.join(CARPETA_SEMILLA, "simulador_sparkov.json.gz"), "wt", encoding="utf-8") as archivo:
        json.dump({"resumen": resumen, "perfiles": perfiles, "transacciones": transacciones}, archivo, ensure_ascii=False)

    desde = inicio_ventana - pd.Timedelta(days=DIAS_HISTORIAL)
    recientes = previas[previas["fecha_hora"] >= desde]
    with gzip.open(os.path.join(CARPETA_SEMILLA, "historial_simulador.csv.gz"), "wt", encoding="utf-8", newline="") as archivo:
        escritor = csv.writer(archivo)
        escritor.writerow(COLUMNAS_HISTORIAL)
        for f in recientes.itertuples(index=False):
            escritor.writerow(["sparkov", f.id_cuenta, f.id_transaccion, _texto_fecha(f.fecha_hora),
                               f"{f.monto:.2f}", f.categoria, f.comercio, f.ubicacion])

    print(json.dumps(resumen, ensure_ascii=False, indent=2))
    print(f"Historial de {DIAS_HISTORIAL} días: {len(recientes):,} filas. Listo en {time.monotonic() - reloj:.0f} s.")


if __name__ == "__main__":
    main()
