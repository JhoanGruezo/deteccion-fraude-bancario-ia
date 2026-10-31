"""Pruebas del contrato de la explicación (diseno/agente.md, "Cómo se valida", punto 1).

El caso de ejemplo copia la forma real de datos/salidas_sparkov/casos_marcados.json
(caso C-000001, recortado a dos transacciones) con los campos que agrega la semilla
(id con prefijo, fuente, tarjeta enmascarada, umbrales). Las demás pruebas lo
importan de aquí.
"""

import copy
import json

from app.agente.contrato import (
    armar_evidencia,
    es_rastreable,
    interpretar_cifra,
    reparar_json,
    validar_explicacion,
)
from app.agente.herramientas import resumir_caso

_CASO = {
    "id_caso": "SPK-000001",
    "fuente": "sparkov",
    "tarjeta_enmascarada": "**** **** **** 0192",
    "inicio_ventana": "2020-07-30 00:06:13",
    "fin_ventana": "2020-08-01 00:06:13",
    "tipos_fraude": ["uso_no_autorizado"],
    "score_maximo": 0.997685,
    "transacciones_sobre_umbral_bloqueo": 5,
    "nivel_recomendacion": "bloquear_tarjeta",
    "motivo_recomendacion": ("5 transacciones en 48 h superan el umbral de bloqueo 0,97 (score máximo 1,00): "
                             "compras anómalas seguidas, patrón de uso no autorizado."),
    "senal_principal": "monto",
    "modelo": "random_forest",
    "umbral_verificacion": 0.5,
    "umbral_bloqueo": 0.97,
    "estado": "pendiente",
    "perfil_previo": {
        "n_transacciones_previas": 2250, "sin_historial": False, "monto_promedio": 96.05,
        "monto_desviacion": 88.19, "transacciones_por_dia": 3.92,
        "horas_habituales": [{"hora": 20, "porcentaje": 5.3}, {"hora": 22, "porcentaje": 4.8}],
        "categorias_habituales": [{"categoria": "grocery_pos", "porcentaje": 12.1}],
    },
    "transacciones": [
        {
            "id_transaccion": "eae5b35f33b8ba5895a691925baa8b77", "fecha_hora": "2020-07-30 00:06:13",
            "monto": 11.21, "categoria": "gas_transport", "comercio": "Greenholt, Jacobi and Gleason",
            "ubicacion": "New Boston", "score": 0.949532, "viaje_imposible": False,
            "desviaciones": [
                {"senal": "monto", "valor_observado": 11.21, "valor_referencia": 96.05,
                 "descripcion": "Monto de 11,21: 0,1 veces su promedio previo (96,05). Más inusual que el 19,4 % de las transacciones normales.",
                 "percentil_rareza": 19.4, "contribucion_modelo": 0.948, "relevante": True},
                {"senal": "hora", "valor_observado": 0, "valor_referencia": 3.7,
                 "descripcion": "A las 0 h: solo el 3,7 % de sus transacciones previas fueron a esa hora. Más inusual que el 68,9 % de las transacciones normales.",
                 "percentil_rareza": 68.9, "contribucion_modelo": 0.9057, "relevante": True},
                {"senal": "monto_24h", "valor_observado": 478.66, "valor_referencia": 376.53,
                 "descripcion": "En las 24 h anteriores movió 478,66; su gasto diario habitual es 376,53.",
                 "percentil_rareza": 84.8, "contribucion_modelo": 0.0042, "relevante": False},
                {"senal": "ritmo_24h", "valor_observado": 7, "valor_referencia": 3.92,
                 "descripcion": "En las 24 h anteriores hizo 7 transacciones; su ritmo habitual es 3,92 por día.",
                 "percentil_rareza": 82.7, "contribucion_modelo": -0.0396, "relevante": False},
            ],
        },
        {
            "id_transaccion": "d17cdaea0d88cb75fdbf4d4ece1dce0b", "fecha_hora": "2020-07-30 01:22:08",
            "monto": 291.8, "categoria": "grocery_pos", "comercio": "Kilback LLC",
            "ubicacion": "New Boston", "score": 0.983432, "viaje_imposible": False,
            "desviaciones": [
                {"senal": "monto", "valor_observado": 291.8, "valor_referencia": 96.01,
                 "descripcion": "Monto de 291,80: 3,0 veces su promedio previo (96,01). Más inusual que el 96,3 % de las transacciones normales.",
                 "percentil_rareza": 96.3, "contribucion_modelo": 0.98, "relevante": True},
                {"senal": "hora", "valor_observado": 1, "valor_referencia": 3.5,
                 "descripcion": "A la 1 h: solo el 3,5 % de sus transacciones previas fueron a esa hora. Más inusual que el 73,5 % de las transacciones normales.",
                 "percentil_rareza": 73.5, "contribucion_modelo": 0.9763, "relevante": True},
            ],
        },
    ],
}


def caso_de_ejemplo() -> dict:
    return copy.deepcopy(_CASO)


def evidencia_de(caso: dict, historial: list | None = None):
    """Evidencia como la vería el servicio después de que el modelo pidió obtener_caso."""
    resultados = [{"nombre": "obtener_caso", "resultado": resumir_caso(caso)}]
    if historial is not None:
        resultados.append({"nombre": "obtener_historial_reciente", "resultado": {"transacciones": historial}})
    return armar_evidencia(caso, resultados)


def explicacion_valida() -> dict:
    return {
        "que_paso": ("El 2020-07-30 a las 00:06 la tarjeta **** **** **** 0192 pagó 11,21 en Greenholt, "
                     "Jacobi and Gleason (New Boston) y a la 01:22 pagó 291,80 en Kilback LLC."),
        "por_que_es_riesgo": ("El monto de 291,80 es 3,0 veces su promedio previo (96,01), más inusual que el "
                              "96,3 % de las transacciones normales, y ocurrió a la 1 h, hora en la que solo hizo "
                              "el 3,5 % de sus compras."),
        "recomendacion": {"accion": "bloquear_tarjeta", "objetivo": "la tarjeta terminada en 0192",
                          "argumento": "5 transacciones en 48 h superan el umbral de bloqueo 0,97."},
        "senales_citadas": ["monto", "hora"],
        "nivel_riesgo_en_palabras": "Riesgo muy alto: el sistema le dio 0,998 sobre 1.",
        "lo_que_no_se_sabe": "No se sabe si el cliente reconoce estas compras.",
    }


def texto_valido() -> str:
    return json.dumps(explicacion_valida(), ensure_ascii=False)


# --- Pruebas ------------------------------------------------------------------------------
def test_explicacion_valida_pasa():
    contenido, errores = validar_explicacion(texto_valido(), evidencia_de(caso_de_ejemplo()))
    assert errores == []
    assert contenido["recomendacion"]["accion"] == "bloquear_tarjeta"
    assert contenido["es_respaldo"] is False


def test_campos_anidados_dentro_de_recomendacion_se_suben_y_se_validan():
    # Claude Haiku, 2026-10-31: senales_citadas y lo_que_no_se_sabe llegaban dentro de recomendacion.
    datos = explicacion_valida()
    datos["recomendacion"]["senales_citadas"] = datos.pop("senales_citadas")
    datos["recomendacion"]["lo_que_no_se_sabe"] = datos.pop("lo_que_no_se_sabe")
    contenido, errores = validar_explicacion(json.dumps(datos, ensure_ascii=False), evidencia_de(caso_de_ejemplo()))
    assert errores == []
    assert contenido["senales_citadas"] == ["monto", "hora"]
    assert "reconoce" in contenido["lo_que_no_se_sabe"]


def test_campos_anidados_siguen_pasando_por_las_comprobaciones():
    datos = explicacion_valida()
    datos.pop("senales_citadas")
    datos["recomendacion"]["senales_citadas"] = ["ubicacion_imposible"]   # no relevante en este caso
    _, errores = validar_explicacion(json.dumps(datos, ensure_ascii=False), evidencia_de(caso_de_ejemplo()))
    assert any("no son relevantes" in e for e in errores)


def test_json_con_cercos_y_texto_alrededor_se_repara():
    texto = "Aquí está la explicación:\n```json\n" + texto_valido() + "\n```\nEspero que sirva."
    contenido, errores = validar_explicacion(texto, evidencia_de(caso_de_ejemplo()))
    assert errores == []
    assert contenido["senales_citadas"] == ["monto", "hora"]


def test_json_truncado_en_el_ultimo_campo_se_repara():
    texto = texto_valido()
    truncado = texto[: texto.index("reconoce")]          # cortado a mitad de lo_que_no_se_sabe
    datos, error = reparar_json(truncado)
    assert error is None
    assert datos["lo_que_no_se_sabe"].startswith("No se sabe si el cliente")
    contenido, errores = validar_explicacion(truncado, evidencia_de(caso_de_ejemplo()))
    assert errores == []


def test_json_truncado_al_principio_no_se_puede_usar():
    texto = texto_valido()
    contenido, errores = validar_explicacion(texto[:60], evidencia_de(caso_de_ejemplo()))
    assert contenido is None
    assert errores   # le faltan campos obligatorios


def test_respuesta_sin_json():
    contenido, errores = validar_explicacion("No puedo responder eso.", evidencia_de(caso_de_ejemplo()))
    assert contenido is None and "ningún objeto JSON" in errores[0]


def test_accion_distinta_de_la_regla_se_rechaza():
    datos = explicacion_valida()
    datos["recomendacion"]["accion"] = "verificar_cliente"
    contenido, errores = validar_explicacion(json.dumps(datos), evidencia_de(caso_de_ejemplo()))
    assert contenido is None
    assert any("no es la que decidió la regla" in e for e in errores)


def test_senal_no_relevante_se_rechaza():
    datos = explicacion_valida()
    datos["senales_citadas"] = ["monto", "ritmo_24h"]     # ritmo_24h existe pero no es relevante
    contenido, errores = validar_explicacion(json.dumps(datos), evidencia_de(caso_de_ejemplo()))
    assert contenido is None
    assert any("ritmo_24h" in e for e in errores)


def test_senales_citadas_vacias_se_rechazan():
    datos = explicacion_valida()
    datos["senales_citadas"] = []
    contenido, errores = validar_explicacion(json.dumps(datos), evidencia_de(caso_de_ejemplo()))
    assert contenido is None


def test_cifra_inventada_se_rechaza_y_se_nombra():
    datos = explicacion_valida()
    datos["por_que_es_riesgo"] += " En total movió 1.234,56 en el día."
    contenido, errores = validar_explicacion(json.dumps(datos, ensure_ascii=False), evidencia_de(caso_de_ejemplo()))
    assert contenido is None
    assert any("1.234,56" in e for e in errores)


def test_cifra_que_el_modelo_no_pidio_no_es_rastreable():
    # 2250 transacciones previas existe en la base, pero solo lo devuelve obtener_perfil_cuenta,
    # que en esta evidencia no se llamó.
    datos = explicacion_valida()
    datos["que_paso"] += " Tenía 2.250 transacciones previas."
    contenido, errores = validar_explicacion(json.dumps(datos, ensure_ascii=False), evidencia_de(caso_de_ejemplo()))
    assert contenido is None and any("2.250" in e for e in errores)


def test_cifras_redondeadas_y_porcentajes_se_aceptan():
    datos = explicacion_valida()
    datos["por_que_es_riesgo"] += " Unos 292 en una sola compra; riesgo del 99,8 %."
    contenido, errores = validar_explicacion(json.dumps(datos, ensure_ascii=False), evidencia_de(caso_de_ejemplo()))
    assert errores == []


def test_lectura_de_cifras_en_formato_espanol():
    assert interpretar_cifra("1.234,56") == (1234.56, 2)
    assert interpretar_cifra("0,97") == (0.97, 2)
    assert interpretar_cifra("2020") == (2020.0, 0)
    assert interpretar_cifra("96.05") == (96.05, 2)       # formato inglés: igual se revisa
    assert es_rastreable(479, 0, [478.66])
    assert not es_rastreable(480, 0, [478.66])


def test_rechaza_nombres_internos_de_senales_en_el_texto():
    """Regla 9 del prompt, verificada en código: el analista no lee 'monto_24h'."""
    datos = explicacion_valida()
    datos["por_que_es_riesgo"] += " El monto_24h confirma la ráfaga."
    contenido, errores = validar_explicacion(json.dumps(datos, ensure_ascii=False), evidencia_de(caso_de_ejemplo()))
    assert contenido is None and any("monto_24h" in e for e in errores)


def test_las_categorias_con_guion_bajo_son_datos_y_se_aceptan():
    datos = explicacion_valida()
    datos["que_paso"] += " Compró en la categoría grocery_pos."
    contenido, errores = validar_explicacion(json.dumps(datos, ensure_ascii=False), evidencia_de(caso_de_ejemplo()))
    assert errores == [] and contenido is not None


# --- Hallazgo 1: sin evidencia consultada no hay explicación ---------------------------
def test_respuesta_sin_haber_consultado_obtener_caso_se_rechaza_aunque_no_traiga_cifras():
    datos = {**explicacion_valida(), "que_paso": "Hubo compras raras.", "por_que_es_riesgo": "Son inusuales."}
    datos["recomendacion"] = {**datos["recomendacion"], "argumento": "Patrón de uso no autorizado."}
    sin_herramientas = armar_evidencia(caso_de_ejemplo(), [])
    contenido, errores = validar_explicacion(json.dumps(datos, ensure_ascii=False), sin_herramientas)
    assert contenido is None and errores[0].startswith("no consultó la evidencia")


# --- Hallazgo 2: el nivel en palabras ya no es del modelo ------------------------------
def test_nivel_de_riesgo_es_opcional_y_no_se_valida():
    datos = explicacion_valida()
    del datos["nivel_riesgo_en_palabras"]
    contenido, errores = validar_explicacion(json.dumps(datos, ensure_ascii=False), evidencia_de(caso_de_ejemplo()))
    assert errores == [] and contenido["nivel_riesgo_en_palabras"] == ""
    datos["nivel_riesgo_en_palabras"] = "Mayor que el 12.345,6 % de los casos"   # cifra falsa, se ignora
    _, errores = validar_explicacion(json.dumps(datos, ensure_ascii=False), evidencia_de(caso_de_ejemplo()))
    assert errores == []


# --- Hallazgo 3: tarjeta sin historial -------------------------------------------------
def caso_sin_historial() -> dict:
    caso = caso_de_ejemplo()
    caso["perfil_previo"] = {"n_transacciones_previas": 0, "sin_historial": True}
    caso["transacciones"][1]["desviaciones"].append({
        "senal": "monto_24h", "valor_observado": 3071.99, "valor_referencia": 3858.35,
        "descripcion": "En las 24 h anteriores movió 3.071,99; su gasto diario habitual es 3.858,35.",
        "percentil_rareza": 99.8, "contribucion_modelo": 0.5, "relevante": True})
    return caso


def test_sin_historial_no_puede_citar_un_gasto_habitual():
    caso = caso_sin_historial()
    datos = explicacion_valida()
    datos["por_que_es_riesgo"] = "En 24 horas movió 3.071,99, frente a un gasto diario habitual de 3.858,35."
    contenido, errores = validar_explicacion(json.dumps(datos, ensure_ascii=False), evidencia_de(caso))
    assert contenido is None and any("casi no tiene historial" in e for e in errores)


def test_sin_historial_decir_que_no_hay_perfil_habitual_si_se_acepta():
    caso = caso_sin_historial()
    datos = explicacion_valida()
    # Sin el "3,0 veces su promedio previo (96,01)" del ejemplo base: eso sí afirma un hábito.
    datos["por_que_es_riesgo"] = ("El monto de 291,80 es más inusual que el 96,3 % de las transacciones normales "
                                  "y ocurrió a la 1 h.")
    datos["que_paso"] += " La tarjeta no tenía compras previas: no hay un perfil habitual con el cual comparar."
    contenido, errores = validar_explicacion(json.dumps(datos, ensure_ascii=False), evidencia_de(caso))
    assert errores == [], errores


def test_con_historial_hablar_de_lo_habitual_es_normal():
    datos = explicacion_valida()
    datos["por_que_es_riesgo"] += " Es 3,0 veces su promedio previo (96,01), lejos de lo habitual."
    _, errores = validar_explicacion(json.dumps(datos, ensure_ascii=False), evidencia_de(caso_de_ejemplo()))
    assert errores == []


def test_obtener_caso_avisa_poco_historial_y_lista_las_senales_citables():
    resumen = resumir_caso(caso_sin_historial())
    assert list(resumen)[:3] == ["id_caso", "senales_que_puedes_citar", "aviso_historial"]
    assert resumen["senales_que_puedes_citar"] == ["hora", "monto", "monto_24h"]
    assert "aviso_historial" not in resumir_caso(caso_de_ejemplo())
