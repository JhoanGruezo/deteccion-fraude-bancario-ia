"""El nivel de riesgo del caso en palabras, armado por código y no por el modelo.

Por qué existe (validacion/app-analista.md, hallazgo 2): cuando el LLM redactaba
`nivel_riesgo_en_palabras`, 3 de 9 explicaciones afirmaban lo contrario del percentil
que citaban ("está en el tope de los casos marcados" con percentil 33,8; "por encima
de casi todos" con 3,5). El contrato no puede ver ese error porque las cifras sí son
rastreables: lo falso es el adjetivo. Como la frase sale de cuatro datos exactos
(score máximo, umbrales, transacciones sobre el umbral de bloqueo y percentil entre
los casos de su fuente), se arma aquí con reglas fijas y el servicio la escribe sobre
lo que haya dicho el modelo. Es la misma lógica de los seis ejes de decisiones.md:
entrada estructurada, regla exacta y costo alto del error → código, no modelo.

La cuenta del percentil es la misma que devuelve la herramienta
obtener_score_y_umbrales, para que el analista vea una sola cifra en toda la app.
"""


# Solo para cuando el caso no trae umbrales ni conteo (datos incompletos).
NIVEL_SEGUN_REGLA = {
    "bloquear_tarjeta": "Riesgo alto según la regla del sistema",
    "bloquear_acceso_cuenta": "Riesgo alto según la regla del sistema, con señales de toma de control de la cuenta",
    "verificar_cliente": "Riesgo intermedio según la regla del sistema",
}


def percentil_entre_casos(score: float | None, scores: list[float]) -> dict | None:
    """Qué tan arriba queda un score entre los de los casos marcados de su fuente.

    percentil = % de casos con score estrictamente menor (la cuenta histórica de la
    herramienta). Además se cuenta cuántos casos empatan con el máximo, porque en
    Sparkov casi todos los casos marcados tienen score 0,97-1,00 y un empate en el
    tope daría un percentil "medio" para un caso que en realidad está arriba.
    """
    if score is None or not scores:
        return None
    por_debajo = sum(1 for s in scores if s < score)
    maximo = max(scores)
    return {
        "percentil": round(100 * por_debajo / len(scores), 1),
        "n_casos": len(scores),
        "es_maximo": score >= maximo,
        "empatados_en_maximo": sum(1 for s in scores if s >= maximo),
    }


def posicion_del_caso(caso: dict, repositorio) -> dict | None:
    """Percentil del caso entre los casos marcados de su misma fuente, leído del repositorio."""
    casos = repositorio.listar_casos(fuente=caso.get("fuente"), limite=100_000)
    return percentil_entre_casos(caso.get("score_maximo"), [c["score_maximo"] for c in casos or []])


def posicion_tolerante(caso: dict, repositorio) -> dict | None:
    """Igual, pero si la consulta falla devuelve None y la frase sale sin percentil."""
    try:
        return posicion_del_caso(caso, repositorio)
    except Exception:   # noqa: BLE001 — una frase sin percentil es mejor que una tarea caída
        return None


def _porcentaje(valor: float) -> str:
    """33.8 → "33,8" (formato colombiano, como el resto del texto del analista)."""
    return f"{float(valor):.1f}".replace(".", ",")


def _cuantas_superan(n_sobre: int, n_transacciones: int) -> str:
    """Sujeto y verbo concordados: "su única transacción supera", "3 de sus 5 transacciones superan"."""
    if n_transacciones and n_sobre == n_transacciones:
        return "su única transacción supera" if n_sobre == 1 else f"sus {n_sobre} transacciones superan"
    if n_transacciones and n_sobre < n_transacciones:
        verbo = "supera" if n_sobre == 1 else "superan"
        return f"{n_sobre} de sus {n_transacciones} transacciones {verbo}"
    return "1 transacción supera" if n_sobre == 1 else f"{n_sobre} transacciones superan"


def _tramo(posicion: dict) -> str:
    """El adjetivo sale del percentil con cortes fijos; nunca de la impresión del modelo."""
    if posicion["es_maximo"]:
        otros = posicion["empatados_en_maximo"] - 1
        return " (es el riesgo más alto de la cola" + (f", empatado con otros {otros} casos)" if otros else ")")
    if posicion["percentil"] >= 75:
        return " (de los más altos de la cola)"
    if posicion["percentil"] < 25:
        return " (de los más bajos de la cola)"
    return " (en la mitad de la cola)"


def nivel_riesgo_en_palabras(caso: dict, posicion: dict | None = None) -> str:
    """Frase para el analista con el nivel de riesgo del caso, correcta por construcción.

    caso: el caso como lo guarda el repositorio (score_maximo, umbrales,
    transacciones_sobre_umbral_bloqueo, transacciones). posicion: el resultado de
    percentil_entre_casos, o None si no se pudo calcular (la frase se arma sin él).
    """
    transacciones = caso.get("transacciones") or []
    n_transacciones = len(transacciones)
    n_sobre = int(caso.get("transacciones_sobre_umbral_bloqueo") or 0)
    score = caso.get("score_maximo")
    umbral_verificacion = caso.get("umbral_verificacion")
    hay_viaje_imposible = any(t.get("viaje_imposible") for t in transacciones)

    if n_sobre >= 1:
        frase = f"Riesgo alto: {_cuantas_superan(n_sobre, n_transacciones)} el umbral de bloqueo del sistema"
        if hay_viaje_imposible:
            frase += ", y además hay un viaje imposible entre dos de ellas"
    elif score is not None and umbral_verificacion is not None and score >= umbral_verificacion:
        frase = ("Riesgo intermedio: ninguna transacción supera el umbral de bloqueo, pero al menos una "
                 "supera el de verificación")
        if hay_viaje_imposible:
            frase += "; la alerta fuerte viene del viaje imposible"
    elif score is None or umbral_verificacion is None:
        # Faltan los datos para comparar con los umbrales: no se afirma nada que no se
        # pueda comprobar; se dice solo el nivel que fijó la regla.
        frase = NIVEL_SEGUN_REGLA.get(caso.get("nivel_recomendacion"), "Nivel de riesgo según la regla del sistema")
    elif hay_viaje_imposible:
        frase = ("Las compras en sí no superan los umbrales de riesgo del sistema: la alerta viene del viaje "
                 "imposible entre dos transacciones")
    else:
        frase = "Ninguna transacción supera los umbrales de riesgo del sistema"

    if posicion:
        frase += (f". Entre los {posicion['n_casos']} casos marcados de su fuente, su riesgo es mayor que el del "
                  f"{_porcentaje(posicion['percentil'])} %{_tramo(posicion)}")
    return frase + "."


def con_nivel_de_codigo(explicacion: dict, caso: dict, repositorio) -> dict:
    """Copia de una explicación guardada con el nivel de riesgo armado en código.

    Las explicaciones guardadas antes de la versión .4 del prompt traen el nivel que
    redactó el modelo (a veces falso). Al servirlas desde caché o en el detalle se
    reemplaza al vuelo, sin reescribir la base: la fila guardada sigue siendo la
    evidencia de lo que el modelo dijo.
    """
    contenido = explicacion.get("contenido") if isinstance(explicacion, dict) else None
    if not isinstance(contenido, dict):
        return explicacion
    nuevo = dict(contenido, nivel_riesgo_en_palabras=nivel_riesgo_en_palabras(
        caso, posicion_tolerante(caso, repositorio)))
    return {**explicacion, "contenido": nuevo}
