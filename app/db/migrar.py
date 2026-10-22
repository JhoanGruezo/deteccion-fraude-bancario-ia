"""Deja la base lista al arrancar la app: espera a Postgres, aplica el esquema y carga la semilla.

Existe porque la entrega exige que `docker compose up` deje todo funcionando sin
pasos manuales, en una máquina sin el dataset de Kaggle (requisitos/persistencia.md,
criterios 1 y 4). Se eligió migrar desde la app y no desde
docker-entrypoint-initdb.d porque initdb solo corre con un volumen vacío: así el
mismo arranque sirve para un volumen nuevo y para uno que ya tiene datos.

Reglas:
- El esquema es idempotente y se aplica siempre.
- La semilla se carga solo si la tabla casos está vacía, y en UNA transacción: si el
  arranque se interrumpe a mitad de carga, no queda una base a medias, y el siguiente
  arranque vuelve a intentarlo.
- Un candado de Postgres (pg_advisory_xact_lock) evita que dos procesos de la app
  arrancando a la vez carguen la semilla dos veces.
- Sin semilla, la app arranca igual con la bandeja vacía (/api/salud lo informa).

Se puede correr solo: python -m app.db.migrar
"""

import csv
import gzip
import json
import logging
import os
import sys
import time

import psycopg

from app import config
from app.db.conexion import cursor
from app.db.repositorio import _json

registro = logging.getLogger("app.db.migrar")

RUTA_ESQUEMA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "esquema.sql")
FUENTES = ("sparkov", "sinteticos")
INTENTOS_CONEXION = 10
CANDADO_MIGRACION = 7_271_031  # número arbitrario y fijo que identifica este candado
COLUMNAS_HISTORIAL = ("fuente", "id_cuenta", "id_transaccion", "fecha_hora", "monto", "categoria", "comercio", "ubicacion")

# Último resultado de preparar_base(), para que /api/salud pueda informarlo.
estado = {"preparada": False}


class BaseNoDisponible(RuntimeError):
    """Postgres no respondió tras todos los reintentos."""


def esperar_base(intentos=INTENTOS_CONEXION):
    """Reintenta la conexión con espera creciente (1 s, 2 s, … hasta 5 s: 35 s de espera,
    más lo que tarde en fallar cada intento; con un host inexistente fue ~75 s en total).

    depends_on: service_healthy ya espera a Postgres en docker-compose, pero esto cubre
    el arranque fuera de compose y un reinicio de la base mientras la app arranca.
    """
    for intento in range(1, intentos + 1):
        try:
            with psycopg.connect(config.DATABASE_URL, connect_timeout=5) as conexion:
                conexion.execute("select 1")
            return
        except psycopg.OperationalError as error:
            if intento == intentos:
                mensaje = (
                    f"No fue posible conectarse a Postgres tras {intentos} intentos. "
                    "Revise que el servicio 'db' esté arriba (docker compose ps) y que "
                    f"DATABASE_URL apunte a él. Último error: {str(error).strip().splitlines()[0]}"
                )
                registro.error(mensaje)
                raise BaseNoDisponible(mensaje) from None
            espera = min(intento, 5)
            registro.warning("Postgres aún no responde (intento %d/%d); nuevo intento en %d s.", intento, intentos, espera)
            time.sleep(espera)


def _leer_json(ruta):
    with open(ruta, encoding="utf-8") as archivo:
        return json.load(archivo)


def _semilla_disponible(carpeta):
    faltantes = [
        nombre
        for nombre in [f"casos_{fuente}.json" for fuente in FUENTES] + ["historial.csv.gz"]
        if not os.path.exists(os.path.join(carpeta, nombre))
    ]
    return faltantes


def _cargar_casos(cur, casos):
    cur.executemany(
        """
        insert into casos (
            id_caso, fuente, id_cuenta, inicio_ventana, fin_ventana, tipos_fraude, score_maximo,
            transacciones_sobre_umbral_bloqueo, nivel_recomendacion, motivo_recomendacion,
            senal_principal, perfil_previo, modelo, umbral_verificacion, umbral_bloqueo,
            fraude_confirmado_dataset
        ) values (
            %(id_caso)s, %(fuente)s, %(id_cuenta)s, %(inicio_ventana)s, %(fin_ventana)s, %(tipos_fraude)s,
            %(score_maximo)s, %(transacciones_sobre_umbral_bloqueo)s, %(nivel_recomendacion)s,
            %(motivo_recomendacion)s, %(senal_principal)s, %(perfil_previo)s, %(modelo)s,
            %(umbral_verificacion)s, %(umbral_bloqueo)s, %(fraude_confirmado_dataset)s
        )
        """,
        [{**caso, "perfil_previo": _json(caso["perfil_previo"])} for caso in casos],
    )
    transacciones = [
        {**transaccion, "id_caso": caso["id_caso"], "desviaciones": _json(transaccion["desviaciones"])}
        for caso in casos
        for transaccion in caso["transacciones"]
    ]
    cur.executemany(
        """
        insert into transacciones_caso (
            id_caso, id_transaccion, fecha_hora, monto, categoria, comercio, ubicacion,
            score, viaje_imposible, desviaciones
        ) values (
            %(id_caso)s, %(id_transaccion)s, %(fecha_hora)s, %(monto)s, %(categoria)s, %(comercio)s,
            %(ubicacion)s, %(score)s, %(viaje_imposible)s, %(desviaciones)s
        )
        """,
        transacciones,
    )
    return len(transacciones)


def _cargar_historial(cur, ruta):
    """Carga historial.csv.gz con COPY (decenas de miles de filas en un segundo)."""
    filas = 0
    with gzip.open(ruta, "rt", encoding="utf-8", newline="") as archivo:
        lector = csv.DictReader(archivo)
        with cur.copy(f"copy historial ({', '.join(COLUMNAS_HISTORIAL)}) from stdin") as copia:
            for fila in lector:
                # Celda vacía en el CSV = dato ausente (los sintéticos no traen comercio).
                copia.write_row([fila[columna] or None for columna in COLUMNAS_HISTORIAL])
                filas += 1
    return filas


def preparar_base(carpeta_semilla=None):
    """Espera a Postgres, aplica el esquema y, si casos está vacía, carga la semilla.

    Devuelve un dict con el resultado (también queda en migrar.estado):
    {"preparada", "semilla": "cargada" | "ya_cargada" | "ausente", "casos",
     "transacciones_caso", "historial", "faltantes", "segundos"}.
    Lanza BaseNoDisponible si Postgres no responde.
    """
    carpeta = carpeta_semilla or config.CARPETA_SEMILLA
    inicio = time.monotonic()
    esperar_base()

    with open(RUTA_ESQUEMA, encoding="utf-8") as archivo:
        esquema = archivo.read()

    resultado = {"preparada": True, "semilla": "ya_cargada", "faltantes": []}
    with cursor() as cur:
        # Candado de la transacción: el segundo proceso espera aquí y, al entrar, ya
        # encuentra la tabla casos llena.
        cur.execute("select pg_advisory_xact_lock(%s)", (CANDADO_MIGRACION,))
        cur.execute(esquema)
        cur.execute("select count(*) as n from casos")
        if cur.fetchone()["n"] == 0:
            faltantes = _semilla_disponible(carpeta)
            if faltantes:
                resultado.update(semilla="ausente", faltantes=faltantes)
                registro.warning(
                    "No se encontró la semilla en %s (faltan: %s). La app arranca con la bandeja vacía; "
                    "genérela con: python scripts/generar_semilla.py",
                    carpeta,
                    ", ".join(faltantes),
                )
            else:
                casos = [caso for fuente in FUENTES for caso in _leer_json(os.path.join(carpeta, f"casos_{fuente}.json"))]
                _cargar_casos(cur, casos)
                _cargar_historial(cur, os.path.join(carpeta, "historial.csv.gz"))
                resultado["semilla"] = "cargada"

        cur.execute(
            """
            select (select count(*) from casos) as casos,
                   (select count(*) from transacciones_caso) as transacciones_caso,
                   (select count(*) from historial) as historial
            """
        )
        resultado.update(cur.fetchone())

    resultado["segundos"] = round(time.monotonic() - inicio, 2)
    registro.info(
        "Base lista: semilla %s, %d casos, %d transacciones de caso, %d filas de historial (%.2f s).",
        resultado["semilla"], resultado["casos"], resultado["transacciones_caso"], resultado["historial"], resultado["segundos"],
    )
    estado.clear()
    estado.update(resultado)
    return resultado


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        resultado = preparar_base()
    except BaseNoDisponible:
        # El mensaje claro ya quedó en el log; se termina sin traza de Python.
        sys.exit(1)
    print(json.dumps(resultado, ensure_ascii=False))


if __name__ == "__main__":
    main()
