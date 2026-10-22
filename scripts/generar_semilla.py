"""Arma la carpeta semilla/ que la app carga en Postgres la primera vez que arranca.

Existe porque el ZIP de entrega tiene que levantar en una máquina que NO tiene los
500 MB de Kaggle (requisitos/persistencia.md, criterio 1). El motor de riesgo deja
sus casos en datos/salidas_<fuente>/, pero la vista del analista y el agente
necesitan además el historial de cada tarjeta para narrar "qué pasó antes de la
alerta", y ese historial solo existe en los CSV grandes. Este script se corre una
vez, en la máquina que sí tiene los CSV, y deja en semilla/ solo lo que la app usa:

- casos_sparkov.json / casos_sinteticos.json: los casos del motor con id de caso
  prefijado por fuente (SPK-/SIN-, porque los dos JSON numeran desde C-000001 y
  chocarían) y con el modelo y los umbrales que los produjeron.
- historial.csv.gz: para cada caso, las transacciones de su tarjeta en los 30 días
  anteriores a la ventana y las de la propia ventana, sin repetir transacciones.
- metricas_sparkov.json / metricas_sinteticos.json: copia de las métricas del motor.

Se corre desde la raíz del proyecto: python scripts/generar_semilla.py
Diseño completo en diseno/persistencia.md.
"""

import json
import os
import sys

import pandas as pd

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CARPETA_DATOS = os.path.join(RAIZ, "datos")
CARPETA_SEMILLA = os.path.join(RAIZ, "semilla")

# cargar_datos.py vive en src/ y es la única pieza que sabe traducir las columnas
# de Sparkov; se importa en lugar de duplicar esa traducción aquí.
sys.path.insert(0, os.path.join(RAIZ, "src"))
import cargar_datos  # noqa: E402

DIAS_HISTORIAL = 30  # requisitos/persistencia.md: "al menos los 30 días anteriores a la ventana"
FUENTES = {"sparkov": "SPK", "sinteticos": "SIN"}
COLUMNAS_HISTORIAL = ["fuente", "id_cuenta", "id_transaccion", "fecha_hora", "monto", "categoria", "comercio", "ubicacion"]


def leer_json(ruta):
    with open(ruta, encoding="utf-8") as archivo:
        return json.load(archivo)


def escribir_json(datos, ruta):
    # Sin sangría: la semilla viaja en el ZIP y la indentación casi duplica el tamaño.
    with open(ruta, "w", encoding="utf-8") as archivo:
        json.dump(datos, archivo, ensure_ascii=False, separators=(",", ":"))


def preparar_casos(casos, metricas, fuente):
    """Prefija el id de caso con la fuente y le pega el modelo y los umbrales del motor.

    El número del caso se conserva (C-000123 → SPK-000123) para poder cruzar un caso
    de la app con la fila correspondiente de datos/salidas_<fuente>/casos_marcados.csv.
    """
    prefijo = FUENTES[fuente]
    preparados = []
    for caso in casos:
        numero = int(caso["id_caso"].split("-")[1])
        nuevo = dict(caso)
        nuevo["id_caso"] = f"{prefijo}-{numero:06d}"
        nuevo["fuente"] = fuente
        nuevo["modelo"] = metricas["modelo_elegido"]
        nuevo["umbral_verificacion"] = metricas["umbral_verificacion"]
        nuevo["umbral_bloqueo"] = metricas["umbral_bloqueo"]
        preparados.append(nuevo)
    return preparados


def cargar_transacciones(fuente):
    # Las rutas de cargar_datos.py son relativas a src/; desde la raíz se pasan explícitas.
    if fuente == "sparkov":
        return cargar_datos.cargar_sparkov(
            os.path.join(CARPETA_DATOS, "fraudTrain.csv"),
            os.path.join(CARPETA_DATOS, "fraudTest.csv"),
        )
    return cargar_datos.cargar_sinteticos(os.path.join(CARPETA_DATOS, "transacciones.csv"))


def armar_historial(casos, transacciones, fuente):
    """Transacciones de cada tarjeta con caso: 30 días antes de la ventana y la ventana misma.

    Se guardan también las transacciones marcadas de la ventana (no solo las que no
    quedaron marcadas): así la línea de tiempo de la app se lee de una sola tabla y
    una transacción marcada en un caso aparece igual en otro caso solapado de la
    misma tarjeta. La desduplicación por id_transaccion evita repetirlas cuando dos
    casos de una tarjeta se solapan en el tiempo.
    """
    # Primero se reduce a las tarjetas con caso (unas cientos de 1,8 millones de filas
    # en Sparkov) para que el cruce con las ventanas sea barato.
    cuentas = {caso["id_cuenta"] for caso in casos}
    de_las_cuentas = transacciones[transacciones["id_cuenta"].isin(cuentas)]
    por_cuenta = dict(tuple(de_las_cuentas.groupby("id_cuenta")))

    partes = []
    for caso in casos:
        filas = por_cuenta.get(caso["id_cuenta"])
        if filas is None:
            continue
        inicio = pd.Timestamp(caso["inicio_ventana"]) - pd.Timedelta(days=DIAS_HISTORIAL)
        fin = pd.Timestamp(caso["fin_ventana"])
        partes.append(filas[(filas["fecha_hora"] >= inicio) & (filas["fecha_hora"] <= fin)])

    historial = pd.concat(partes, ignore_index=True).drop_duplicates("id_transaccion")
    # Los sintéticos no traen comercio ni categoría: quedan vacíos y la app los muestra así.
    for columna in ["categoria", "comercio"]:
        if columna not in historial.columns:
            historial[columna] = None
    historial["fuente"] = fuente
    historial["monto"] = historial["monto"].round(2)
    historial["fecha_hora"] = historial["fecha_hora"].dt.strftime("%Y-%m-%d %H:%M:%S")
    return historial[COLUMNAS_HISTORIAL].sort_values(["id_cuenta", "fecha_hora"])


def verificar_historial(casos, historial):
    """Cuenta casos sin historial previo y transacciones marcadas que no quedaron en el historial."""
    ids_historial = set(historial["id_transaccion"])
    faltantes = sum(
        1 for caso in casos for transaccion in caso["transacciones"] if transaccion["id_transaccion"] not in ids_historial
    )
    # Las fechas están en texto AAAA-MM-DD HH:MM:SS, que se ordena igual que la fecha.
    fechas_por_cuenta = historial.groupby("id_cuenta")["fecha_hora"].apply(list).to_dict()
    sin_previas = sum(
        1
        for caso in casos
        if not any(fecha < caso["inicio_ventana"] for fecha in fechas_por_cuenta.get(caso["id_cuenta"], []))
    )
    return faltantes, sin_previas


def tamano_mb(ruta):
    return os.path.getsize(ruta) / (1024 * 1024)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    os.makedirs(CARPETA_SEMILLA, exist_ok=True)
    historiales = []
    resumen = []

    for fuente in FUENTES:
        carpeta = os.path.join(CARPETA_DATOS, f"salidas_{fuente}")
        casos = leer_json(os.path.join(carpeta, "casos_marcados.json"))
        metricas = leer_json(os.path.join(carpeta, "metricas_motor.json"))
        casos = preparar_casos(casos, metricas, fuente)

        print(f"[{fuente}] cargando transacciones…")
        transacciones = cargar_transacciones(fuente)
        historial = armar_historial(casos, transacciones, fuente)
        faltantes, sin_previas = verificar_historial(casos, historial)
        print(
            f"[{fuente}] {len(casos)} casos, {sum(len(c['transacciones']) for c in casos)} transacciones marcadas, "
            f"{len(historial)} filas de historial ({historial['id_cuenta'].nunique()} tarjetas)."
        )
        print(f"[{fuente}] casos sin historial previo a la ventana: {sin_previas}")
        if faltantes:
            print(f"[{fuente}] AVISO: {faltantes} transacciones marcadas no aparecen en el historial.")

        ruta_casos = os.path.join(CARPETA_SEMILLA, f"casos_{fuente}.json")
        ruta_metricas = os.path.join(CARPETA_SEMILLA, f"metricas_{fuente}.json")
        escribir_json(casos, ruta_casos)
        escribir_json(metricas, ruta_metricas)
        resumen.append((ruta_casos, len(casos)))
        resumen.append((ruta_metricas, 1))
        historiales.append(historial)

    historial = pd.concat(historiales, ignore_index=True)
    ruta_historial = os.path.join(CARPETA_SEMILLA, "historial.csv.gz")
    # mtime fijo: dos corridas sobre los mismos datos producen el mismo archivo byte a byte.
    historial.to_csv(ruta_historial, index=False, compression={"method": "gzip", "mtime": 0})
    resumen.append((ruta_historial, len(historial)))

    print("\nArchivos de semilla/:")
    total = 0.0
    for ruta, filas in resumen:
        mb = tamano_mb(ruta)
        total += mb
        print(f"  {os.path.basename(ruta):26s} {filas:>8d} filas  {mb:7.2f} MB")
    print(f"  {'total':26s} {'':>8s}        {total:7.2f} MB")


if __name__ == "__main__":
    main()
