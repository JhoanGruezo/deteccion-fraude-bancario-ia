"""Pruebas del repositorio y de la migración contra un Postgres real.

Existen para sostener los criterios de aceptación de requisitos/persistencia.md con
una corrida y no con una promesa: la semilla carga exactamente lo que dicen los JSON
del motor, re-migrar no duplica, las desviaciones guardadas son idénticas a las del
JSON, fraude_confirmado_dataset y la tarjeta completa nunca salen por obtener_caso, y
el flujo propuesta → confirmación humana → decisión deja el caso en el estado que
corresponde.

No se usa la base de la app: cada corrida crea su propia base (fraude_pruebas, junto
a la de DATABASE_URL) y la borra al final, para no ensuciar la demo con decisiones y
tareas de prueba. Con la base del compose arriba (docker compose up -d db), desde la
raíz del proyecto:

    docker compose run --rm --no-deps app python -m pytest app/pruebas/test_repositorio.py -q

o, montando el código sin reconstruir la imagen, en un python:3.12-slim conectado a
la red del compose con DATABASE_URL=postgresql://fraude:fraude_dev@db:5432/fraude.
"""

import json
import os
import random
import re
import uuid

import psycopg
import pytest
from psycopg import sql

from app import config
from app.db import conexion, migrar, repositorio

CARPETA_SEMILLA = config.CARPETA_SEMILLA
BASE_PRUEBAS = "fraude_pruebas"
PATRON_TARJETA = re.compile(r"^\*\*\*\* \*\*\*\* \*\*\*\* \d{4}$")


def _url_con_base(url, base):
    """Cambia el nombre de la base en una URL postgresql://usuario:clave@host:puerto/base."""
    return re.sub(r"/[^/?]+(\?|$)", f"/{base}\\1", url, count=1) if url.count("/") >= 3 else url + "/" + base


def _recrear_base(url_administracion, base):
    with psycopg.connect(url_administracion, autocommit=True) as administracion:
        administracion.execute(sql.SQL("drop database if exists {} with (force)").format(sql.Identifier(base)))
        administracion.execute(sql.SQL("create database {}").format(sql.Identifier(base)))


def _borrar_base(url_administracion, base):
    with psycopg.connect(url_administracion, autocommit=True) as administracion:
        administracion.execute(sql.SQL("drop database if exists {} with (force)").format(sql.Identifier(base)))


def _usar_base(url):
    """Apunta la app a otra base: el pool se vuelve a crear con la URL nueva."""
    conexion.cerrar_pool()
    config.DATABASE_URL = url


def _leer_semilla(fuente):
    with open(os.path.join(CARPETA_SEMILLA, f"casos_{fuente}.json"), encoding="utf-8") as archivo:
        return json.load(archivo)


@pytest.fixture(scope="session")
def semilla():
    casos = _leer_semilla("sparkov") + _leer_semilla("sinteticos")
    return {caso["id_caso"]: caso for caso in casos}


@pytest.fixture(scope="session")
def base_cargada():
    """Base de pruebas nueva, migrada una vez con la semilla real; se borra al terminar."""
    url_original = os.environ.get("DATABASE_URL", config.DATABASE_URL)
    url_pruebas = _url_con_base(url_original, BASE_PRUEBAS)
    _recrear_base(url_original, BASE_PRUEBAS)
    _usar_base(url_pruebas)
    resultado = migrar.preparar_base()
    yield resultado
    conexion.cerrar_pool()
    _borrar_base(url_original, BASE_PRUEBAS)
    config.DATABASE_URL = url_original


# --- Semilla y migración ---------------------------------------------------------------


def test_semilla_ausente_deja_la_base_vacia_sin_fallar(tmp_path):
    url_original = os.environ.get("DATABASE_URL", config.DATABASE_URL)
    base = BASE_PRUEBAS + "_vacia"
    _recrear_base(url_original, base)
    _usar_base(_url_con_base(url_original, base))
    try:
        resultado = migrar.preparar_base(carpeta_semilla=str(tmp_path))
        assert resultado["semilla"] == "ausente"
        assert resultado["casos"] == 0
        assert "historial.csv.gz" in resultado["faltantes"]
        assert repositorio.listar_casos() == []
    finally:
        conexion.cerrar_pool()
        _borrar_base(url_original, base)
        config.DATABASE_URL = url_original


def test_carga_coincide_con_los_json(base_cargada, semilla):
    assert base_cargada["semilla"] == "cargada"
    assert base_cargada["casos"] == len(semilla)
    assert base_cargada["transacciones_caso"] == sum(len(c["transacciones"]) for c in semilla.values())
    assert base_cargada["historial"] > 0

    conteos = repositorio.contar_casos()
    assert conteos["total"] == len(semilla)
    for fuente in ("sparkov", "sinteticos"):
        assert conteos["por_fuente"][fuente] == len(_leer_semilla(fuente))
    assert conteos["por_estado"] == {"pendiente": len(semilla)}


def test_remigrar_no_duplica(base_cargada):
    antes = (base_cargada["casos"], base_cargada["transacciones_caso"], base_cargada["historial"])
    segunda = migrar.preparar_base()
    assert segunda["semilla"] == "ya_cargada"
    assert (segunda["casos"], segunda["transacciones_caso"], segunda["historial"]) == antes


def test_desviaciones_identicas_al_json(base_cargada, semilla):
    # Criterio 3: para casos al azar (semilla fija, reproducible), la evidencia guardada
    # es exactamente la del motor, transacción por transacción y en el mismo orden.
    for id_caso in random.Random(7).sample(sorted(semilla), 5):
        guardado = repositorio.obtener_caso(id_caso)
        esperado = {t["id_transaccion"]: t for t in semilla[id_caso]["transacciones"]}
        assert len(guardado["transacciones"]) == len(esperado)
        for transaccion in guardado["transacciones"]:
            original = esperado[transaccion["id_transaccion"]]
            assert transaccion["desviaciones"] == original["desviaciones"]
            assert transaccion["score"] == original["score"]
            assert transaccion["monto"] == pytest.approx(original["monto"])
        assert guardado["perfil_previo"] == semilla[id_caso]["perfil_previo"]


# --- Lo que nunca sale hacia la interfaz -----------------------------------------------


def test_obtener_caso_oculta_etiqueta_y_tarjeta(base_cargada, semilla):
    id_caso = "SPK-000001"
    caso = repositorio.obtener_caso(id_caso)
    assert "fraude_confirmado_dataset" not in caso
    assert "id_cuenta" not in caso
    assert PATRON_TARJETA.match(caso["tarjeta_enmascarada"])
    assert caso["tarjeta_enmascarada"].endswith(semilla[id_caso]["id_cuenta"][-4:])
    assert semilla[id_caso]["id_cuenta"] not in json.dumps(caso)

    para_eval = repositorio.obtener_caso_para_evaluacion(id_caso)
    assert para_eval["fraude_confirmado_dataset"] == semilla[id_caso]["fraude_confirmado_dataset"]
    assert repositorio.obtener_caso("NO-EXISTE") is None


def test_bandeja_resumen_filtros_y_enmascarado(base_cargada):
    casos = repositorio.listar_casos(limite=1000)
    assert len(casos) == base_cargada["casos"]
    claves = {
        "id_caso", "fuente", "tarjeta_enmascarada", "inicio_ventana", "nivel_recomendacion", "senal_principal",
        "score_maximo", "n_transacciones", "monto_total", "estado", "tiene_explicacion",
    }
    assert set(casos[0]) == claves
    assert all(PATRON_TARJETA.match(c["tarjeta_enmascarada"]) for c in casos)
    scores = [c["score_maximo"] for c in casos]
    assert scores == sorted(scores, reverse=True)

    sinteticos = repositorio.listar_casos(fuente="sinteticos", nivel="bloquear_acceso_cuenta")
    assert sinteticos and all(c["fuente"] == "sinteticos" for c in sinteticos)
    assert repositorio.listar_casos(busqueda="SPK-000001")[0]["id_caso"] == "SPK-000001"
    assert len(repositorio.listar_casos(limite=10)) == 10


def test_busqueda_por_tarjeta_solo_con_los_ultimos_4_exactos(base_cargada, semilla):
    """La búsqueda no puede servir de oráculo para reconstruir el número completo."""
    caso = semilla["SPK-000006"]
    numero = caso["id_cuenta"]
    por_ultimos4 = repositorio.listar_casos(busqueda=numero[-4:], limite=1000)
    assert "SPK-000006" in [c["id_caso"] for c in por_ultimos4]
    # Un sufijo más largo (o el número completo) ya no encuentra nada por la tarjeta.
    for texto in (numero[-5:], numero[-8:], numero):
        assert "SPK-000006" not in [c["id_caso"] for c in repositorio.listar_casos(busqueda=texto, limite=1000)]


def test_caso_con_viaje_imposible_y_uso_no_autorizado(base_cargada):
    caso = repositorio.obtener_caso("SIN-000001")
    assert set(caso["tipos_fraude"]) == {"uso_no_autorizado", "viaje_imposible"}


def test_historial_cronologico_con_marcas_del_caso(base_cargada, semilla):
    id_caso = "SPK-000001"
    historial = repositorio.obtener_historial(id_caso, dias=30, limite=500)
    fechas = [t["fecha_hora"] for t in historial]
    assert fechas == sorted(fechas)
    marcadas = {t["id_transaccion"] for t in historial if t["en_caso"]}
    assert marcadas == {t["id_transaccion"] for t in semilla[id_caso]["transacciones"]}
    assert any(not t["en_caso"] for t in historial)
    assert all(t["fecha_hora"] <= semilla[id_caso]["fin_ventana"].replace(" ", "T") for t in historial)

    recortado = repositorio.obtener_historial(id_caso, dias=30, limite=5)
    assert len(recortado) == 5
    assert recortado == historial[-5:]  # el recorte conserva lo más cercano a la alerta


# --- Agente: tareas, trazas, explicaciones ---------------------------------------------


def test_tarea_trazas_y_explicacion_vigente(base_cargada):
    id_caso = "SPK-000002"
    tarea_id = str(uuid.uuid4())
    repositorio.crear_tarea(tarea_id, id_caso, "explicacion")
    repositorio.registrar_traza(tarea_id, 1, "herramienta", {"nombre": "obtener_caso", "argumentos": {"id_caso": id_caso}})
    repositorio.registrar_traza(tarea_id, 2, "resultado_herramienta", {"nombre": "obtener_caso"}, duracion_ms=42)
    assert [t["tipo"] for t in repositorio.listar_trazas(tarea_id)] == ["herramienta", "resultado_herramienta"]

    contenido = {"que_paso": "uno", "recomendacion": {"accion": "bloquear_tarjeta"}}
    repositorio.guardar_explicacion(id_caso, tarea_id, {"que_paso": "versión vieja"}, True, None, None)
    id_nueva = repositorio.guardar_explicacion(id_caso, tarea_id, contenido, False, "gemini", "gemini-3.8-flash")
    vigente = repositorio.explicacion_vigente(id_caso)
    assert vigente["id"] == id_nueva and vigente["contenido"] == contenido and vigente["es_respaldo"] is False

    repositorio.cerrar_tarea(tarea_id, motivo_fin="completada", latencia_ms=900, proveedor="gemini", desconocida=1)
    tarea = repositorio.ultima_tarea(id_caso)
    assert tarea["tarea_id"] == tarea_id
    assert tarea["proveedor_final"] == "gemini" and tarea["terminada_en"] is not None
    assert next(c for c in repositorio.listar_casos(busqueda=id_caso))["tiene_explicacion"] is True


# --- Confirmación humana ---------------------------------------------------------------


def test_propuesta_confirmada_crea_decision_y_cambia_estado(base_cargada):
    id_caso = "SPK-000003"
    tarea_id = str(uuid.uuid4())
    repositorio.crear_tarea(tarea_id, id_caso, "explicacion")
    propuesta = repositorio.crear_propuesta(id_caso, tarea_id, "confirmar_bloqueo", "cinco compras anómalas")
    assert propuesta["estado"] == "pendiente" and propuesta["propuesta_id"] == propuesta["id"]
    assert [p["id"] for p in repositorio.propuestas_pendientes(id_caso)] == [propuesta["id"]]
    # La propuesta sola no es una decisión ni cambia el caso (cuarto límite del agente).
    assert repositorio.decisiones_del_caso(id_caso) == []
    assert repositorio.obtener_caso(id_caso)["estado"] == "pendiente"

    with pytest.raises(ValueError):
        repositorio.resolver_propuesta(propuesta["id"], True, "  ")

    resuelta = repositorio.resolver_propuesta(propuesta["id"], True, "Ana", "revisado")
    assert resuelta["estado"] == "confirmada" and resuelta["resuelta_por"] == "Ana"
    assert resuelta["decision"]["accion"] == "confirmar_bloqueo"
    assert resuelta["decision"]["estado_caso"] == "bloqueo_confirmado"
    assert repositorio.obtener_caso(id_caso)["estado"] == "bloqueo_confirmado"
    assert repositorio.propuestas_pendientes(id_caso) == []
    decisiones = repositorio.decisiones_del_caso(id_caso)
    assert len(decisiones) == 1 and decisiones[0]["propuesta_id"] == propuesta["id"]

    with pytest.raises(repositorio.PropuestaYaResuelta):
        repositorio.resolver_propuesta(propuesta["id"], True, "Ana")
    with pytest.raises(repositorio.PropuestaNoEncontrada):
        repositorio.resolver_propuesta(999_999, True, "Ana")


def test_propuesta_rechazada_no_escribe_decision(base_cargada):
    id_caso = "SPK-000004"
    propuesta = repositorio.crear_propuesta(id_caso, None, "descartar", "parece legítimo")
    resuelta = repositorio.resolver_propuesta(propuesta["id"], False, "Luis", "no estoy de acuerdo")
    assert resuelta["estado"] == "rechazada" and resuelta["decision"] is None
    assert resuelta["resuelta_por"] == "Luis"
    assert repositorio.decisiones_del_caso(id_caso) == []
    assert repositorio.obtener_caso(id_caso)["estado"] == "pendiente"


def test_dos_decisiones_gana_la_ultima_sin_perder_la_anterior(base_cargada):
    id_caso = "SPK-000005"
    repositorio.registrar_decision(id_caso, "escalar", "Ana")
    ultima = repositorio.registrar_decision(id_caso, "descartar", "Luis", "falsa alarma")
    assert ultima["estado_caso"] == "descartado"
    assert [d["accion"] for d in repositorio.decisiones_del_caso(id_caso)] == ["escalar", "descartar"]
    assert repositorio.obtener_caso(id_caso)["estado"] == "descartado"
    with pytest.raises(repositorio.CasoNoEncontrado):
        repositorio.registrar_decision("NO-EXISTE", "escalar", "Ana")
    with pytest.raises(ValueError):
        repositorio.registrar_decision(id_caso, "borrar", "Ana")


# --- Métricas --------------------------------------------------------------------------


def test_resumen_metricas(base_cargada):
    with conexion.cursor() as cur:
        cur.execute("select clock_timestamp() as ahora")
        desde = cur.fetchone()["ahora"]

    id_caso = "SIN-000002"
    # Tres tareas que llamaron al modelo, una con fallo recuperado y una desde caché.
    tareas = [
        dict(motivo_fin="completada", latencia_ms=1000, ttft_ms=100, costo_usd=0.001),
        dict(motivo_fin="completada", latencia_ms=2000, ttft_ms=200, costo_usd=0.002, reintentos=2, conmutaciones=1),
        dict(motivo_fin="respaldo", latencia_ms=3000, ttft_ms=300, costo_usd=0.003),
        dict(motivo_fin="completada", latencia_ms=5, desde_cache=True),
        # Contrato inválido que el reintento arregló: fallo recuperado aunque no hubo reintentos de red.
        dict(motivo_fin="completada", latencia_ms=4000, ttft_ms=400, costo_usd=0.0, _traza="contrato_invalido"),
        # Cayó a la plantilla y la guardó: el analista recibió una explicación válida → recuperada.
        dict(motivo_fin="respaldo", latencia_ms=6000, costo_usd=0.0, _plantilla=True),
    ]
    for metricas in tareas:
        tarea_id = str(uuid.uuid4())
        traza = metricas.pop("_traza", None)
        plantilla = metricas.pop("_plantilla", False)
        repositorio.crear_tarea(tarea_id, id_caso, "explicacion")
        if traza:
            repositorio.registrar_traza(tarea_id, 1, traza, {"errores": ["x"], "reintenta": True})
        if plantilla:
            repositorio.guardar_explicacion(id_caso, tarea_id, {"que_paso": "plantilla"}, True, None, None)
        repositorio.cerrar_tarea(tarea_id, **metricas)

    resumen = repositorio.resumen_metricas(desde=desde)
    assert resumen["n_tareas"] == 6
    # Éxito sin la de caché: completadas sin plantilla (1, 2 y 5) sobre 5 que llamaron al modelo.
    assert resumen["tareas_sin_cache"] == 5 and resumen["exitosas"] == 3
    assert resumen["tasa_exito"] == 0.6
    assert resumen["latencia_mediana_ms"] == 3000      # la de caché no entra
    assert resumen["latencia_p90_ms"] == 5200          # percentile_cont: 4000 + 0,6 × 2000
    assert resumen["ttft_mediana_ms"] == 250           # sin la de caché ni la de TTFT nulo
    assert resumen["costo_total_usd"] == pytest.approx(0.006)
    assert resumen["costo_por_tarea_usd"] == pytest.approx(0.001)
    assert resumen["porcentaje_desde_cache"] == 16.7
    # Con fallo: 2 (reintentos), 3 (respaldo sin plantilla), 5 (contrato) y 6 (respaldo con plantilla).
    assert resumen["recuperacion"] == {"tareas_con_fallo": 4, "recuperadas": 3, "tasa": 0.75}
    assert resumen["tasa_recuperacion"] == 0.75
    assert resumen["por_motivo_fin"] == {"completada": 4, "respaldo": 2}
    assert set(resumen["definiciones"]) >= {"tasa_exito", "recuperacion"}
