"""El nivel de riesgo en palabras lo arma el código (hallazgo 2 de validacion/app-analista.md).

Los tres casos donde el modelo se equivocó en la validación del 2026-10-21 se
reproducen aquí con su percentil real: la frase tiene que decir lo mismo que la cifra.
"""

from app.agente.riesgo_en_palabras import nivel_riesgo_en_palabras, percentil_entre_casos
from app.pruebas.test_contrato import caso_de_ejemplo


def _posicion(percentil, n=287, es_maximo=False, empatados=1):
    return {"percentil": percentil, "n_casos": n, "es_maximo": es_maximo, "empatados_en_maximo": empatados}


def test_percentil_bajo_no_se_describe_como_alto():
    # SPK-000280: percentil 3,5; el modelo escribió "por encima de casi todos los demás".
    frase = nivel_riesgo_en_palabras(caso_de_ejemplo(), _posicion(3.5))
    assert "mayor que el del 3,5 %" in frase and "de los más bajos de la cola" in frase
    assert "más altos" not in frase


def test_percentil_medio_y_alto():
    assert "en la mitad de la cola" in nivel_riesgo_en_palabras(caso_de_ejemplo(), _posicion(33.8))
    assert "de los más altos de la cola" in nivel_riesgo_en_palabras(caso_de_ejemplo(), _posicion(91.0))


def test_empate_en_el_tope_se_dice_como_tal():
    posicion = percentil_entre_casos(1.0, [1.0, 1.0, 1.0, 0.98])
    assert posicion == {"percentil": 25.0, "n_casos": 4, "es_maximo": True, "empatados_en_maximo": 3}
    frase = nivel_riesgo_en_palabras(caso_de_ejemplo(), posicion)
    assert "es el riesgo más alto de la cola, empatado con otros 2 casos" in frase


def test_cuantas_transacciones_superan_el_umbral_con_concordancia():
    caso = caso_de_ejemplo()                    # 2 transacciones; el caso dice 5 sobre el umbral
    assert nivel_riesgo_en_palabras(caso).startswith("Riesgo alto: 5 transacciones superan el umbral de bloqueo")
    caso["transacciones_sobre_umbral_bloqueo"] = 1
    assert "1 de sus 2 transacciones supera el umbral" in nivel_riesgo_en_palabras(caso)
    caso["transacciones_sobre_umbral_bloqueo"] = 2
    assert "sus 2 transacciones superan" in nivel_riesgo_en_palabras(caso)


def test_verificar_y_viaje_imposible_con_score_bajo():
    caso = caso_de_ejemplo()
    caso["transacciones_sobre_umbral_bloqueo"] = 0
    caso["score_maximo"], caso["umbral_verificacion"] = 0.95, 0.9
    assert nivel_riesgo_en_palabras(caso).startswith("Riesgo intermedio: ninguna transacción supera el umbral de bloqueo")
    caso["score_maximo"] = 0.2
    caso["transacciones"][1]["viaje_imposible"] = True
    frase = nivel_riesgo_en_palabras(caso)
    assert "la alerta viene del viaje imposible" in frase and "Riesgo alto" not in frase


def test_sin_percentil_la_frase_igual_sale_y_termina_en_punto():
    frase = nivel_riesgo_en_palabras(caso_de_ejemplo(), None)
    assert frase.endswith(".") and "casos marcados" not in frase
