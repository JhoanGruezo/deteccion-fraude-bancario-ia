"""Explicación de respaldo armada en código, sin red: el último escalón de la degradación.

Si los dos proveedores caen, si se agota un límite o si el modelo no logra cumplir
el contrato en dos intentos, el analista igual recibe el caso razonado (decisiones.md,
2026-10-21: "si el LLM falla se muestra ... una versión de plantilla armada solo con
las desviaciones"). Tiene el mismo contrato que la explicación del agente y se marca
con es_respaldo = True para que la interfaz diga que la armó una regla, no la IA.

Todas sus cifras se copian de los datos guardados del caso (o de las descripciones
ya redactadas por el motor), así que siempre pasa la validación del contrato; las
pruebas lo comprueban. El nivel de riesgo en palabras sale de la misma función que
usa el servicio para las explicaciones del modelo (riesgo_en_palabras.py).
"""

from app.agente.contrato import afirma_habito, tiene_poco_historial
from app.agente.herramientas import tarjeta_enmascarada
from app.agente.riesgo_en_palabras import nivel_riesgo_en_palabras

OBJETIVOS = {
    "bloquear_tarjeta": "la tarjeta {tarjeta}",
    "bloquear_acceso_cuenta": "el acceso a la cuenta asociada a la tarjeta {tarjeta}",
    "verificar_cliente": "el contacto con el titular de la tarjeta {tarjeta}, sin bloquearla",
}


def formato_es(valor: float, decimales: int = 2) -> str:
    """1234.5 → "1.234,50" (punto de miles, coma decimal)."""
    texto = f"{float(valor):,.{decimales}f}"
    return texto.replace(",", "§").replace(".", ",").replace("§", ".")


def _fecha(texto: str) -> str:
    """"2020-07-30T00:06:13" o "2020-07-30 00:06:13" → "2020-07-30 00:06"."""
    return str(texto).replace("T", " ")[:16]


def _donde(transaccion: dict) -> str:
    lugar = transaccion.get("comercio") or transaccion.get("categoria") or "un comercio sin nombre registrado"
    if transaccion.get("ubicacion"):
        lugar += f" ({transaccion['ubicacion']})"
    return lugar


def _que_paso(caso: dict, historial: list[dict]) -> str:
    transacciones = caso.get("transacciones", [])
    pasos = "; ".join(
        f"el {_fecha(t['fecha_hora'])} pagó {formato_es(t['monto'])} en {_donde(t)}" for t in transacciones)
    texto = (f"Entre el {_fecha(caso['inicio_ventana'])} y el {_fecha(caso['fin_ventana'])}, la tarjeta "
             f"{tarjeta_enmascarada(caso)} tuvo {len(transacciones)} transacciones marcadas: {pasos}.")

    previas = [t for t in historial if not t.get("en_caso") and _fecha(t["fecha_hora"]) < _fecha(caso["inicio_ventana"])]
    if previas:
        ultima = previas[-1]
        texto += (f" Antes de la ventana, el historial reciente muestra {len(previas)} transacciones; la "
                  f"última fue el {_fecha(ultima['fecha_hora'])} por {formato_es(ultima['monto'])} en {_donde(ultima)}.")
    else:
        texto += " En el historial reciente no hay transacciones anteriores a la ventana."
    if tiene_poco_historial(caso):
        texto += " La tarjeta casi no tiene historial previo, así que no hay un perfil habitual con el cual comparar."
    return texto


def _por_que_es_riesgo(caso: dict) -> str:
    transacciones = caso.get("transacciones", [])
    mas_riesgosa = max(transacciones, key=lambda t: t.get("score", 0))
    descripciones = [d["descripcion"] for d in mas_riesgosa.get("desviaciones", []) if d.get("relevante")]
    encabezado = (f"En la transacción más riesgosa ({_fecha(mas_riesgosa['fecha_hora'])}, "
                  f"{formato_es(mas_riesgosa['monto'])})")
    if tiene_poco_historial(caso):
        # Las descripciones del motor que hablan de "gasto habitual" o "promedio previo"
        # se calcularon con las primeras compras de la propia ráfaga: copiarlas aquí
        # contradiría la frase "no hay perfil" (SPK-000006). Se dejan solo las demás.
        utiles = [d for d in descripciones if not afirma_habito(d)]
        if not utiles:
            utiles = [d["descripcion"] for t in transacciones for d in t.get("desviaciones", [])
                      if d.get("relevante") and d.get("senal") == "historial"][:1]
        texto = (f"La tarjeta casi no tiene compras previas, así que no hay un perfil propio con el cual "
                 f"comparar: el sistema la marcó por la secuencia de compras del caso. {encabezado} señaló: "
                 + (" ".join(utiles) or "ninguna desviación adicional."))
    elif descripciones:
        texto = f"{encabezado} se combinan estas señales frente a su perfil habitual: " + " ".join(descripciones)
    else:
        # Pasa en viajes imposibles: la alerta no viene del monto ni de la hora de las compras.
        texto = f"{encabezado} el monto, la hora y el lugar de la compra no se salen de lo normal para esta tarjeta."
    if any(t.get("viaje_imposible") for t in transacciones):
        texto += (" Además, la tarjeta operó en dos lugares que no se pueden recorrer en el tiempo que pasó "
                  "entre una transacción y otra (viaje imposible).")
    return texto


def senales_relevantes_del_caso(caso: dict) -> list[str]:
    senales = {d["senal"] for t in caso.get("transacciones", [])
               for d in t.get("desviaciones", []) if d.get("relevante")}
    if any(t.get("viaje_imposible") for t in caso.get("transacciones", [])):
        senales.add("viaje_imposible")
    return sorted(senales)


def explicacion_de_plantilla(caso: dict, historial: list[dict], posicion: dict | None = None) -> dict:
    """posicion: percentil del caso entre los de su fuente (riesgo_en_palabras.percentil_entre_casos)."""
    nivel = caso["nivel_recomendacion"]
    tarjeta = tarjeta_enmascarada(caso)
    return {
        "que_paso": _que_paso(caso, historial),
        "por_que_es_riesgo": _por_que_es_riesgo(caso),
        "recomendacion": {
            "accion": nivel,
            "objetivo": OBJETIVOS.get(nivel, "la tarjeta {tarjeta}").format(tarjeta=tarjeta),
            "argumento": f"{caso['motivo_recomendacion']} La decisión final es del analista.",
        },
        "senales_citadas": senales_relevantes_del_caso(caso),
        "nivel_riesgo_en_palabras": nivel_riesgo_en_palabras(caso, posicion),
        "lo_que_no_se_sabe": (
            "Esta explicación la armó una regla, sin el asistente de IA, solo con las señales guardadas del caso. "
            "No se sabe si el cliente reconoce estas compras ni si ya hubo contacto con el banco."),
        "es_respaldo": True,
    }
