"""La plantilla de respaldo siempre pasa el contrato (diseno/agente.md, "Plantilla").

Además de los casos borde del requisito (sin historial, viaje imposible, una sola
transacción), se corre sobre TODOS los casos reales que dejó el motor en
datos/salidas_*/casos_marcados.json, si el archivo está presente.
"""

import json
from pathlib import Path

import pytest

from app.agente.contrato import validar_explicacion
from app.agente.plantilla import explicacion_de_plantilla, formato_es
from app.pruebas.test_contrato import caso_de_ejemplo, evidencia_de

RAIZ = Path(__file__).resolve().parents[2]


def _valida(caso, historial):
    contenido = explicacion_de_plantilla(caso, historial)
    resultado, errores = validar_explicacion(json.dumps(contenido, ensure_ascii=False), evidencia_de(caso, historial))
    return contenido, resultado, errores


def test_formato_espanol():
    assert formato_es(1234.5) == "1.234,50"
    assert formato_es(0.997685, 3) == "0,998"


def test_plantilla_valida_con_historial_previo():
    caso = caso_de_ejemplo()
    historial = [
        {"fecha_hora": "2020-07-29 18:40:00", "monto": 45.3, "comercio": "Tienda Uno", "categoria": "home",
         "ubicacion": "New Boston", "en_caso": False},
        {"fecha_hora": "2020-07-30 00:06:13", "monto": 11.21, "comercio": "Greenholt, Jacobi and Gleason",
         "categoria": "gas_transport", "ubicacion": "New Boston", "en_caso": True},
    ]
    contenido, resultado, errores = _valida(caso, historial)
    assert errores == []
    assert resultado["es_respaldo"] is True
    assert "45,30" in contenido["que_paso"]
    assert contenido["recomendacion"]["accion"] == "bloquear_tarjeta"


def test_plantilla_tarjeta_sin_historial_lo_dice():
    caso = caso_de_ejemplo()
    caso["perfil_previo"]["sin_historial"] = True
    contenido, _, errores = _valida(caso, [])
    assert errores == []
    assert "no hay un perfil habitual" in contenido["que_paso"]


def test_plantilla_viaje_imposible_bloquea_acceso():
    caso = caso_de_ejemplo()
    caso["nivel_recomendacion"] = "bloquear_acceso_cuenta"
    caso["transacciones"][1]["viaje_imposible"] = True
    caso["transacciones"][1]["monto"] = 733495.44
    caso["transacciones"][1]["desviaciones"][0]["descripcion"] = (
        "Monto de 733.495,44: 3,7 veces su promedio previo (196.808,93). Más inusual que el 99,3 % de las transacciones normales.")
    contenido, _, errores = _valida(caso, [])
    assert errores == []
    assert "viaje_imposible" in contenido["senales_citadas"]
    assert "acceso a la cuenta" in contenido["recomendacion"]["objetivo"]
    assert "733.495,44" in contenido["que_paso"]


def test_plantilla_una_sola_transaccion_verificar():
    caso = caso_de_ejemplo()
    caso["nivel_recomendacion"] = "verificar_cliente"
    caso["transacciones"] = caso["transacciones"][1:]
    caso["transacciones_sobre_umbral_bloqueo"] = 0
    contenido, _, errores = _valida(caso, [])
    assert errores == []
    assert "sin bloquearla" in contenido["recomendacion"]["objetivo"]


def _casos_reales():
    casos = []
    for fuente, prefijo in (("sparkov", "SPK"), ("sinteticos", "SIN")):
        ruta = RAIZ / "datos" / f"salidas_{fuente}" / "casos_marcados.json"
        if ruta.exists():
            for caso in json.loads(ruta.read_text(encoding="utf-8")):
                caso["id_caso"] = caso["id_caso"].replace("C-", f"{prefijo}-")
                caso["fuente"] = fuente
                casos.append(caso)
    return casos


def test_plantilla_valida_en_todos_los_casos_reales_del_motor():
    casos = _casos_reales()
    if not casos:
        pytest.skip("no están los casos_marcados.json del motor")
    fallidos = {}
    for caso in casos:
        _, _, errores = _valida(caso, [])
        if errores:
            fallidos[caso["id_caso"]] = errores
    assert fallidos == {}, f"{len(fallidos)} de {len(casos)} casos fallan: {list(fallidos.items())[:3]}"


def _casos_de_la_semilla():
    casos = []
    for archivo in sorted((RAIZ / "semilla").glob("casos_*.json")):
        casos.extend(json.loads(archivo.read_text(encoding="utf-8")))
    return casos


def test_plantilla_valida_en_todos_los_casos_de_la_semilla_incluidos_los_sin_historial():
    """Los 339 casos que carga la app, con el contrato completo (incluida la regla de 'habitual')."""
    casos = _casos_de_la_semilla()
    if not casos:
        pytest.skip("no está la semilla")
    fallidos = {}
    for caso in casos:
        _, _, errores = _valida(caso, [])
        if errores:
            fallidos[caso["id_caso"]] = errores
    assert fallidos == {}, f"{len(fallidos)} de {len(casos)} casos fallan: {list(fallidos.items())[:3]}"


def test_plantilla_sin_historial_no_copia_el_gasto_habitual_de_la_rafaga():
    from app.agente.contrato import afirma_habito
    caso = next((c for c in _casos_de_la_semilla() if c["id_caso"] == "SPK-000006"), None)
    if caso is None:
        pytest.skip("no está SPK-000006 en la semilla")
    contenido = explicacion_de_plantilla(caso, [])
    assert afirma_habito(contenido["por_que_es_riesgo"]) == []
    assert "3.858,35" not in contenido["por_que_es_riesgo"]


def test_plantilla_sin_desviaciones_relevantes_no_deja_la_lista_vacia():
    caso = caso_de_ejemplo()
    for transaccion in caso["transacciones"]:
        for desviacion in transaccion["desviaciones"]:
            desviacion["relevante"] = False
    caso["transacciones"][1]["viaje_imposible"] = True
    caso["nivel_recomendacion"] = "bloquear_acceso_cuenta"
    contenido, _, errores = _valida(caso, [])
    assert errores == []
    assert "habitual:  " not in contenido["por_que_es_riesgo"] and "no se salen de lo normal" in contenido["por_que_es_riesgo"]
