"""Contrato de la explicación: reparación del JSON y anclaje verificado a la evidencia.

Por qué existe: el profesor pidió trazabilidad score → señales → explicación
(decisiones.md, 2026-10-10) y el reto 9 nombra el "contrato JSON roto". Pedirle al
modelo en el prompt que no invente no garantiza nada; este módulo lo comprueba en
código. Una explicación solo se muestra si pasa estas comprobaciones (diseno/agente.md,
"Contrato"):

0. Evidencia consultada: el modelo pidió obtener_caso y recibió su resultado. Sin
   eso, una respuesta "sin cifras" pasaría el paso 5 aunque fuera inventada entera
   (pasó con Gemini Flash-Lite en la demo del 429, validacion/app-analista.md).
1. Reparación: se quitan cercos de markdown, se toma el primer objeto {...}
   balanceado y, si está truncado, se intenta cerrarlo una sola vez.
2. Forma: claves obligatorias, tipos correctos, textos no vacíos.
3. Acción: la acción recomendada es exactamente la que decidió la regla del motor.
4. Citas: senales_citadas no está vacío y solo nombra señales relevantes del caso.
5. Cifras rastreables: cada número del texto con 3 o más cifras significativas
   aparece en lo que devolvieron las herramientas (con tolerancia de redondeo).
6. Lenguaje del analista: sin nombres internos de señales ni jerga de ML.
7. Tarjeta sin historial: si la tarjeta casi no tiene pasado, el texto no puede
   describir un gasto o promedio "habitual" (sería una contradicción para el analista).

`nivel_riesgo_en_palabras` ya no lo valida el contrato: lo arma el código
(riesgo_en_palabras.py) y el servicio lo escribe después de validar.

`validar_explicacion` devuelve (contenido, errores): si hay errores el contenido es
None, y los errores van tal cual al mensaje de reintento del modelo.
"""

import json
import re
from dataclasses import dataclass

# nivel_riesgo_en_palabras no está aquí a propósito: lo arma el código, no el modelo.
CLAVES_TEXTO = ("que_paso", "por_que_es_riesgo", "lo_que_no_se_sabe")
CLAVES_RECOMENDACION = ("accion", "objetivo", "argumento")
MINIMO_CIFRAS_SIGNIFICATIVAS = 3   # "48 h" o "3 veces" no se rastrean; "291,80" o "2020" sí


@dataclass
class Evidencia:
    """Lo que la explicación puede afirmar: la acción de la regla, las señales y las cifras."""
    nivel_recomendacion: str
    senales_relevantes: set[str]
    numeros: list[float]
    # Herramientas que devolvieron resultado en esta tarea. None = no se sabe (pruebas
    # que arman la evidencia a mano); armar_evidencia siempre lo llena.
    herramientas_consultadas: frozenset[str] | None = None
    poco_historial: bool = False


def senales_citables(caso: dict) -> list[str]:
    """Señales que una explicación puede poner en senales_citadas: unión de todo el caso.

    Las desviaciones marcadas relevantes en CUALQUIER transacción, la señal principal de
    la regla y "viaje_imposible" si alguna transacción lo tiene (ese detector es una
    bandera de la transacción, no una desviación). obtener_caso entrega esta misma
    lista al modelo, así que lo que se le muestra y lo que se le exige no pueden
    divergir.
    """
    senales = {d["senal"] for t in caso.get("transacciones", [])
               for d in t.get("desviaciones", []) if d.get("relevante")}
    if caso.get("senal_principal"):
        senales.add(caso["senal_principal"])
    if any(t.get("viaje_imposible") for t in caso.get("transacciones", [])):
        senales.add("viaje_imposible")
    return sorted(senales)


def tiene_poco_historial(caso: dict) -> bool:
    """La tarjeta casi no tiene pasado: el perfil lo dice o todas las transacciones lo señalan.

    Con poco historial las cifras "habituales" de las descripciones del motor salen de
    las primeras compras de la propia ráfaga (SPK-000006: "gasto diario habitual de
    3.858,35" con 0 compras previas), así que no describen un hábito del cliente.
    """
    if (caso.get("perfil_previo") or {}).get("sin_historial"):
        return True
    transacciones = caso.get("transacciones") or []
    return bool(transacciones) and all(
        any(d.get("senal") == "historial" and d.get("relevante") for d in t.get("desviaciones", []))
        for t in transacciones)


# --- Números en formato español -------------------------------------------------------
# Una "cifra" es una corrida de dígitos con puntos o comas internos: 1.234,56 · 0,97 · 2020.
_PATRON_CIFRA = re.compile(r"\d[\d.,]*\d|\d")
_ESPANOL_CON_MILES = re.compile(r"^\d{1,3}(\.\d{3})+(,\d+)?$")
_ESPANOL_SIMPLE = re.compile(r"^\d+(,\d+)?$")
_INGLES = re.compile(r"^(\d{1,3}(,\d{3})+|\d+)(\.\d+)?$")


def interpretar_cifra(token: str) -> tuple[float, int] | None:
    """Convierte una cifra escrita a (valor, decimales). Prefiere el formato español.

    "1.234,56" → (1234.56, 2); "0,97" → (0.97, 2); "2020" → (2020, 0). Si el modelo
    escribió en formato inglés ("96.05") también se interpreta, para que una cifra mal
    formateada no se escape de la comprobación.
    """
    if _ESPANOL_CON_MILES.match(token) or _ESPANOL_SIMPLE.match(token):
        entero, _, decimales = token.replace(".", "").partition(",")
        return float(f"{entero}.{decimales or 0}"), len(decimales)
    if _INGLES.match(token):
        entero, _, decimales = token.replace(",", "").partition(".")
        return float(f"{entero}.{decimales or 0}"), len(decimales)
    return None


def cifras_significativas(token: str) -> int:
    """Dígitos sin contar los ceros a la izquierda: "0,975" → 3; "00" → 0; "291,80" → 5."""
    return len(re.sub(r"\D", "", token).lstrip("0"))


def extraer_cifras(texto: str) -> list[str]:
    return _PATRON_CIFRA.findall(texto or "")


def numeros_de(valor) -> list[float]:
    """Todos los números que hay dentro de un resultado de herramienta, a cualquier profundidad.

    Los números de JSON se toman tal cual; los que vienen dentro de textos (las
    descripciones ya redactadas, las fechas, el motivo de la regla) se extraen con el
    mismo lector que se usa sobre la explicación, para comparar manzanas con manzanas.
    """
    if isinstance(valor, bool) or valor is None:
        return []
    if isinstance(valor, (int, float)):
        return [float(valor)]
    if isinstance(valor, str):
        return [n for n, _ in filter(None, (interpretar_cifra(t) for t in extraer_cifras(valor)))]
    if isinstance(valor, dict):
        return [n for v in valor.values() for n in numeros_de(v)]
    if isinstance(valor, (list, tuple)):
        return [n for v in valor for n in numeros_de(v)]
    return []


def es_rastreable(valor: float, decimales: int, numeros: list[float]) -> bool:
    """¿El número aparece en la evidencia, salvo redondeo a los decimales escritos?

    Tolerancia: media unidad de la última posición escrita ("479" acepta 478,66;
    "1,00" acepta 0,9977). También se acepta la versión en porcentaje de una fracción
    (score 0,9977 escrito como "99,8 %").
    """
    tolerancia = 0.5 * 10 ** (-decimales) + 1e-9
    return any(abs(valor - n) <= tolerancia or abs(valor - n * 100) <= tolerancia for n in numeros)


# --- Evidencia -------------------------------------------------------------------------
def armar_evidencia(caso: dict, resultados_herramientas: list) -> Evidencia:
    """La acción y las señales salen del caso guardado; las cifras, de lo que vio el modelo.

    Las cifras se toman SOLO de los resultados de herramientas de esta tarea: si el
    modelo escribió un número sin haberlo pedido, no es rastreable aunque exista en la
    base. Las señales citables las define senales_citables(caso).
    """
    return Evidencia(
        nivel_recomendacion=caso["nivel_recomendacion"],
        senales_relevantes=set(senales_citables(caso)),
        numeros=sorted(set(numeros_de(resultados_herramientas))),
        herramientas_consultadas=frozenset(r.get("nombre") for r in resultados_herramientas
                                           if isinstance(r, dict) and r.get("nombre")),
        poco_historial=tiene_poco_historial(caso),
    )


# --- Reparación ------------------------------------------------------------------------
def _primer_objeto_balanceado(texto: str) -> tuple[str, bool]:
    """Desde la primera "{", corta en la llave que la cierra. Devuelve (fragmento, completo)."""
    profundidad, en_cadena, escape = 0, False, False
    for i, caracter in enumerate(texto):
        if en_cadena:
            if escape:
                escape = False
            elif caracter == "\\":
                escape = True
            elif caracter == '"':
                en_cadena = False
        elif caracter == '"':
            en_cadena = True
        elif caracter == "{":
            profundidad += 1
        elif caracter == "}":
            profundidad -= 1
            if profundidad == 0:
                return texto[: i + 1], True
    return texto, False


def _cerrar_truncado(fragmento: str) -> str:
    """Cierra un JSON cortado: comilla abierta, clave sin valor, coma final, llaves y corchetes."""
    cierres, en_cadena, escape = [], False, False
    for caracter in fragmento:
        if en_cadena:
            if escape:
                escape = False
            elif caracter == "\\":
                escape = True
            elif caracter == '"':
                en_cadena = False
        elif caracter == '"':
            en_cadena = True
        elif caracter in "{[":
            cierres.append("}" if caracter == "{" else "]")
        elif caracter in "}]" and cierres:
            cierres.pop()

    reparado = fragmento[:-1] if escape else fragmento   # una barra invertida colgando
    if en_cadena:
        reparado += '"'
    reparado = reparado.rstrip()
    # Una clave que quedó sin valor ("..., "lo_que_no_se) se descarta entera.
    reparado = re.sub(r'([,{])\s*"[^"]*"\s*:?\s*$', lambda m: "{" if m.group(1) == "{" else "", reparado)
    reparado = re.sub(r",\s*$", "", reparado)
    return reparado + "".join(reversed(cierres))


def reparar_json(texto: str) -> tuple[dict | None, str | None]:
    """Paso 1 del contrato. Devuelve (objeto, None) o (None, motivo del fallo)."""
    sin_cercos = re.sub(r"```(?:json)?", "", texto or "")
    inicio = sin_cercos.find("{")
    if inicio == -1:
        return None, "la respuesta no contiene ningún objeto JSON"
    fragmento, _ = _primer_objeto_balanceado(sin_cercos[inicio:])
    try:
        datos = json.loads(fragmento)
    except json.JSONDecodeError:
        try:
            datos = json.loads(_cerrar_truncado(fragmento))   # un solo intento de reparación
        except json.JSONDecodeError as error:
            return None, f"el JSON está roto y no se pudo reparar ({error.msg})"
    if not isinstance(datos, dict):
        return None, "la respuesta no es un objeto JSON"
    return _desanidar(datos), None


# Campos de primer nivel que el modelo a veces escribe DENTRO de "recomendacion" (medido el
# 2026-10-31 con Claude Haiku: el contenido era correcto y se iba a la plantilla solo por
# la forma). Se suben a su lugar; todas las comprobaciones siguen aplicando igual.
_CAMPOS_QUE_SE_ANIDAN = ("senales_citadas", "lo_que_no_se_sabe", "nivel_riesgo_en_palabras")


def _desanidar(datos: dict) -> dict:
    recomendacion = datos.get("recomendacion")
    if isinstance(recomendacion, dict):
        for clave in _CAMPOS_QUE_SE_ANIDAN:
            if clave not in datos and clave in recomendacion:
                datos[clave] = recomendacion.pop(clave)
    return datos


# --- Validación ------------------------------------------------------------------------
def _revisar_forma(datos: dict) -> list[str]:
    errores = []
    for clave in CLAVES_TEXTO:
        if not isinstance(datos.get(clave), str) or not datos[clave].strip():
            errores.append(f"falta el campo «{clave}» o está vacío")
    recomendacion = datos.get("recomendacion")
    if not isinstance(recomendacion, dict):
        errores.append("falta el objeto «recomendacion»")
    else:
        for clave in CLAVES_RECOMENDACION:
            if not isinstance(recomendacion.get(clave), str) or not recomendacion[clave].strip():
                errores.append(f"falta «recomendacion.{clave}» o está vacío")
    senales = datos.get("senales_citadas")
    if not isinstance(senales, list) or not all(isinstance(s, str) for s in senales):
        errores.append("«senales_citadas» debe ser una lista de textos")
    return errores


def textos_con_cifras(datos: dict) -> list[str]:
    """Los campos de texto libre donde el modelo podría escribir cifras."""
    recomendacion = datos.get("recomendacion", {})
    return [datos[c] for c in CLAVES_TEXTO] + [recomendacion["objetivo"], recomendacion["argumento"]]


# --- Tarjeta sin historial ---------------------------------------------------------------
# Una cifra pegada a "habitual" o "promedio previo" en la misma cláusula es una
# afirmación concreta de un hábito ("su gasto diario habitual es 3.858,35"). Esta
# comprobación no da falsos rechazos con frases honestas como "no hay un perfil
# habitual con el cual comparar", que no traen cifra.
_HABITO_CON_CIFRA = re.compile(r"\b(habitual(?:es)?|promedio previo|su promedio)\b[^.;:\n]{0,40}?\d", re.I)
_HABITUAL = re.compile(r"\bhabitual(?:es)?\b", re.I)
# Si la oración que dice "habitual" trae una de estas palabras, está negando el hábito.
_NEGACION = re.compile(r"\b(no|sin|ningún|ninguna|ningun|nunca|tampoco|carece|inexistente|nueva|poco)\b", re.I)


def afirma_habito(texto: str) -> list[str]:
    """Fragmentos del texto que describen un comportamiento "habitual" del cliente.

    Dos formas: una cifra junto a "habitual"/"promedio previo" en la misma cláusula, o
    una oración con "habitual" que no lo niega. Lo usan el contrato (para tarjetas sin
    historial) y la plantilla (para no copiar esas descripciones del motor).
    """
    hallazgos = [m.group(0) for m in _HABITO_CON_CIFRA.finditer(texto or "")]
    for oracion in re.split(r"(?<=[.;!?])\s+", texto or ""):
        if _HABITUAL.search(oracion) and not _NEGACION.search(oracion):
            hallazgos.append(oracion.strip())
    return list(dict.fromkeys(hallazgos))


_TERMINOS_INTERNOS = ("monto_24h", "ritmo_24h", "sin_historial", "senal_principal", "nivel_recomendacion",
                      "contribucion_modelo", "percentil_rareza", "feature", "features", "AUC")


def validar_explicacion(texto: str, evidencia: Evidencia) -> tuple[dict | None, list[str]]:
    # 0. Sin evidencia consultada no hay explicación posible, traiga o no cifras.
    if evidencia.herramientas_consultadas is not None and "obtener_caso" not in evidencia.herramientas_consultadas:
        return None, ["no consultó la evidencia: la respuesta llegó sin haber llamado a obtener_caso, así que "
                      "nada de lo que dice está respaldado; llama primero a obtener_caso y escribe solo con lo "
                      "que devuelva"]

    # 1. Reparación
    datos, error = reparar_json(texto)
    if error:
        return None, [error]

    # 2. Forma: si falla, las demás comprobaciones no tienen sobre qué trabajar.
    errores = _revisar_forma(datos)
    if errores:
        return None, errores

    # 3. Acción: el agente argumenta la regla, no la cambia.
    accion = datos["recomendacion"]["accion"].strip()
    if accion != evidencia.nivel_recomendacion:
        errores.append(f"la acción «{accion}» no es la que decidió la regla "
                       f"(«{evidencia.nivel_recomendacion}»); argumenta esa, no otra")

    # 4. Citas: solo señales relevantes del caso.
    citadas = [s.strip() for s in datos["senales_citadas"]]
    if not citadas:
        errores.append("«senales_citadas» está vacío: cita al menos una señal relevante del caso")
    no_relevantes = [s for s in citadas if s not in evidencia.senales_relevantes]
    if no_relevantes:
        errores.append(f"citaste señales que no son relevantes en este caso: {', '.join(no_relevantes)} "
                       f"(las relevantes son: {', '.join(sorted(evidencia.senales_relevantes))})")

    # 5. Cifras rastreables.
    inventadas = []
    for texto_campo in textos_con_cifras(datos):
        for token in extraer_cifras(texto_campo):
            if cifras_significativas(token) < MINIMO_CIFRAS_SIGNIFICATIVAS:
                continue
            interpretada = interpretar_cifra(token)
            if interpretada is None or not es_rastreable(*interpretada, evidencia.numeros):
                inventadas.append(token)
    if inventadas:
        unicas = list(dict.fromkeys(inventadas))
        errores.append(f"tu respuesta citó {', '.join(unicas)}, que no aparece en la evidencia "
                       "devuelta por las herramientas; usa solo cifras que estén ahí")

    # 6. Lenguaje del analista: ni nombres internos de señales ni jerga de ML en el
    #    texto (regla 9 del prompt). Las categorías de Sparkov (grocery_pos…) sí son
    #    datos del caso, por eso se revisa una lista cerrada y no cualquier palabra_con_guion.
    usadas = sorted({termino for texto_campo in textos_con_cifras(datos)
                     for termino in _TERMINOS_INTERNOS if re.search(rf"\b{re.escape(termino)}\b", texto_campo, re.I)})
    if usadas:
        errores.append(f"el texto usa nombres internos o jerga ({', '.join(usadas)}); "
                       "descríbelos en palabras para el analista")

    # 7. Tarjeta sin historial: nada de "gasto habitual" ni "promedio previo" con cifra.
    if evidencia.poco_historial:
        habitos = [h for texto_campo in textos_con_cifras(datos) for h in afirma_habito(texto_campo)]
        if habitos:
            errores.append("la tarjeta casi no tiene historial previo, pero el texto describe un comportamiento "
                           f"habitual («{habitos[0][:80]}»); di que no hay un perfil con el cual comparar y no "
                           "cites cifras de un gasto o promedio habitual")

    if errores:
        return None, errores

    contenido = {clave: datos[clave].strip() for clave in CLAVES_TEXTO}
    # Lo que haya escrito el modelo queda solo como valor provisional: el servicio lo
    # reemplaza por la frase armada en código (riesgo_en_palabras.py).
    contenido["nivel_riesgo_en_palabras"] = str(datos.get("nivel_riesgo_en_palabras") or "").strip()
    contenido["recomendacion"] = {c: datos["recomendacion"][c].strip() for c in CLAVES_RECOMENDACION}
    contenido["senales_citadas"] = citadas
    contenido["es_respaldo"] = bool(datos.get("es_respaldo", False))
    return contenido, []
