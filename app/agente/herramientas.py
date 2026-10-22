"""Las herramientas del agente: esquema que ve el modelo + implementación que corre aquí.

Existe como módulo propio, separado del bucle, por dos razones del diseño
(diseno/agente.md, "Herramientas"; decisiones.md, 2026-10-21 (2)):

1. **Es la única puerta del agente a la evidencia.** El prompt de usuario solo dice
   "Explica el caso SPK-000123"; todo lo demás (desviaciones, perfil, historial,
   umbrales) el modelo tiene que pedirlo aquí. Eso hace visible el tool calling en la
   traza y es lo que permite anclar cada cifra a lo que las herramientas devolvieron.
2. **Desacople:** el registro (`HERRAMIENTAS`) no sabe nada del bucle ni de los
   proveedores, así que se podría exponer después con un adaptador MCP sin tocarlo.

Reglas que se cumplen en código, no en el prompt:
- cada herramienta valida que el `id_caso` pedido sea el del caso abierto; si no,
  devuelve {"error": "fuera_de_alcance"} (el agente solo ve el caso abierto);
- `registrar_decision` es la única que escribe y solo crea una PROPUESTA pendiente de
  confirmación humana: nunca escribe en la tabla de decisiones (cuarto límite);
- `declarar_fuera_de_alcance` no lee ni escribe nada: es la señal ESTRUCTURADA de que
  el agente rechaza la pregunta. Reemplaza a la marca de texto "Fuera de alcance:",
  que falló en los dos sentidos en la corrida de eval/ del 2026-10-21 (una pregunta
  legítima cerrada como rechazo por usar la frase como salvedad, y un rechazo real
  perdido porque la marca venía en el segundo párrafo). Solo existe en modo pregunta;
- los resultados se recortan (montos a 2 decimales, sin ids internos ni la etiqueta
  real del dataset) para cuidar el presupuesto de tokens.
"""

from dataclasses import dataclass
from typing import Any, Callable

from app.agente.contrato import senales_citables, tiene_poco_historial
from app.agente.prompts import DESCRIPCION_PARAMETRO_ID_CASO, DESCRIPCIONES
from app.agente.riesgo_en_palabras import nivel_riesgo_en_palabras, posicion_del_caso

ACCIONES_DE_DECISION = ("confirmar_bloqueo", "descartar", "escalar")


@dataclass
class ContextoHerramientas:
    """Lo que toda herramienta necesita saber y que el modelo NO controla."""
    id_caso: str
    tarea_id: str
    repositorio: Any   # app.db.repositorio o un doble de prueba con la misma interfaz


@dataclass
class Herramienta:
    nombre: str
    descripcion: str
    parametros: dict                                   # JSON Schema de los argumentos
    escribe: bool
    ejecutar: Callable[[dict, ContextoHerramientas], dict]
    solo_pregunta: bool = False                        # no se ofrece en modo explicación

    def esquema_neutro(self) -> dict:
        """Formato que entienden los clientes de proveedor (cada uno lo traduce al suyo)."""
        return {"nombre": self.nombre, "descripcion": self.descripcion, "parametros": self.parametros}


# --- Utilidades de recorte -------------------------------------------------------------
def _redondear(valor, decimales=2):
    return round(float(valor), decimales) if isinstance(valor, (int, float)) and not isinstance(valor, bool) else valor


def tarjeta_enmascarada(caso: dict) -> str:
    """Usa la máscara del repositorio; si no viene, la arma con los últimos 4 dígitos."""
    if caso.get("tarjeta_enmascarada"):
        return caso["tarjeta_enmascarada"]
    return f"**** **** **** {str(caso.get('id_cuenta', ''))[-4:]}"


def _fuera_de_alcance(argumentos: dict, contexto: ContextoHerramientas) -> dict | None:
    """Devuelve el error de alcance si el modelo pidió un caso distinto del abierto."""
    pedido = str(argumentos.get("id_caso", "")).strip().upper()
    if pedido != contexto.id_caso.strip().upper():
        return {"error": "fuera_de_alcance",
                "detalle": f"Solo puedes consultar el caso abierto ({contexto.id_caso})."}
    return None


def _caso_o_error(contexto: ContextoHerramientas) -> tuple[dict | None, dict | None]:
    caso = contexto.repositorio.obtener_caso(contexto.id_caso)
    if caso is None:
        return None, {"error": "caso_inexistente", "detalle": f"No existe el caso {contexto.id_caso}."}
    return caso, None


AVISO_POCO_HISTORIAL = (
    "La tarjeta casi no tiene compras previas. Las cifras que algunas descripciones llaman "
    "'habitual' o 'promedio previo' salen de las primeras compras de este mismo caso, no de un "
    "hábito del cliente: no las presentes como su comportamiento habitual ni hables de lo "
    "'habitual'; di que no hay un perfil con el cual comparar."
)


def resumir_caso(caso: dict) -> dict:
    """El caso tal como lo ve el modelo: solo señales relevantes y montos redondeados.

    `senales_que_puedes_citar` va arriba y explícito porque en casos largos (ráfagas de
    12 compras) el modelo citaba señales que veía en el texto pero que no son relevantes
    (categoria, hora) y el contrato lo rechazaba dos veces seguidas (eval/, caso D1).
    """
    transacciones = []
    for t in caso.get("transacciones", []):
        senales = [
            {"senal": d["senal"],
             "descripcion": d["descripcion"],
             "percentil_rareza": _redondear(d.get("percentil_rareza"), 1),
             "contribucion": _redondear(d.get("contribucion_modelo"), 3)}
            for d in t.get("desviaciones", []) if d.get("relevante")
        ]
        resumen = {
            "fecha_hora": t["fecha_hora"],
            "monto": _redondear(t["monto"]),
            "comercio": t.get("comercio"),
            "categoria": t.get("categoria"),
            "ubicacion": t.get("ubicacion"),
            "score": _redondear(t.get("score"), 3),
            "senales_relevantes": senales,
        }
        if t.get("viaje_imposible"):
            resumen["viaje_imposible"] = True
        transacciones.append(resumen)
    resumen_caso = {
        "id_caso": caso["id_caso"],
        "senales_que_puedes_citar": senales_citables(caso),
    }
    if tiene_poco_historial(caso):
        resumen_caso["aviso_historial"] = AVISO_POCO_HISTORIAL
    return {
        **resumen_caso,
        "fuente": caso.get("fuente"),
        "tarjeta": tarjeta_enmascarada(caso),
        "inicio_ventana": caso["inicio_ventana"],
        "fin_ventana": caso["fin_ventana"],
        "tipos_fraude_sospechados": caso.get("tipos_fraude", []),
        "nivel_recomendacion": caso["nivel_recomendacion"],
        "motivo_recomendacion": caso["motivo_recomendacion"],
        "senal_principal": caso.get("senal_principal"),
        "score_maximo": _redondear(caso.get("score_maximo"), 3),
        "transacciones_sobre_umbral_bloqueo": caso.get("transacciones_sobre_umbral_bloqueo"),
        # Totales calculados aquí, en código, para que el modelo no tenga que sumar.
        "n_transacciones": len(transacciones),
        "monto_total": _redondear(sum(float(t["monto"]) for t in caso.get("transacciones", []))),
        "transacciones": transacciones,
    }


# --- Implementaciones ------------------------------------------------------------------
def _obtener_caso(argumentos: dict, contexto: ContextoHerramientas) -> dict:
    error = _fuera_de_alcance(argumentos, contexto)
    if error:
        return error
    caso, error = _caso_o_error(contexto)
    return error or resumir_caso(caso)


def _obtener_perfil_cuenta(argumentos: dict, contexto: ContextoHerramientas) -> dict:
    error = _fuera_de_alcance(argumentos, contexto)
    if error:
        return error
    caso, error = _caso_o_error(contexto)
    if error:
        return error
    perfil = {clave: _redondear(valor) for clave, valor in (caso.get("perfil_previo") or {}).items()}
    perfil["tarjeta"] = tarjeta_enmascarada(caso)
    if perfil.get("sin_historial"):
        perfil["nota"] = "Tarjeta con muy poco historial previo: no hay un perfil habitual confiable."
    return perfil


def _obtener_historial_reciente(argumentos: dict, contexto: ContextoHerramientas) -> dict:
    error = _fuera_de_alcance(argumentos, contexto)
    if error:
        return error
    dias = max(1, min(30, int(argumentos.get("dias", 7))))
    historial = contexto.repositorio.obtener_historial(contexto.id_caso, dias=dias, limite=40)
    transacciones = [
        {"fecha_hora": t["fecha_hora"], "monto": _redondear(t["monto"]), "comercio": t.get("comercio"),
         "categoria": t.get("categoria"), "ubicacion": t.get("ubicacion"), "en_caso": bool(t.get("en_caso"))}
        for t in historial
    ]
    return {"dias": dias, "n_transacciones": len(transacciones), "transacciones": transacciones}


def _obtener_score_y_umbrales(argumentos: dict, contexto: ContextoHerramientas) -> dict:
    error = _fuera_de_alcance(argumentos, contexto)
    if error:
        return error
    caso, error = _caso_o_error(contexto)
    if error:
        return error
    resultado = {
        "score_maximo": _redondear(caso["score_maximo"], 3),
        "umbral_verificacion": _redondear(caso.get("umbral_verificacion"), 3),
        "umbral_bloqueo": _redondear(caso.get("umbral_bloqueo"), 3),
        "transacciones_sobre_umbral_bloqueo": caso.get("transacciones_sobre_umbral_bloqueo"),
        "modelo": caso.get("modelo"),
    }
    # Percentil del caso entre los casos marcados de su misma fuente: "más riesgoso que
    # el X % de los casos" es más legible para el analista que "0,998".
    posicion = posicion_del_caso(caso, contexto.repositorio)
    if posicion:
        resultado["percentil_entre_casos"] = posicion["percentil"]
        resultado["n_casos_comparados"] = posicion["n_casos"]
    # La frase la arma el código (riesgo_en_palabras.py): el modelo la cita si la
    # necesita, en vez de inventar un adjetivo que contradiga el percentil.
    resultado["nivel_riesgo_en_palabras"] = nivel_riesgo_en_palabras(caso, posicion)
    return resultado


def _registrar_decision(argumentos: dict, contexto: ContextoHerramientas) -> dict:
    error = _fuera_de_alcance(argumentos, contexto)
    if error:
        return error
    # Solo crea la propuesta. La decisión real la escribe la API cuando el analista
    # confirma (repositorio.resolver_propuesta); esta herramienta nunca la toca.
    propuesta = contexto.repositorio.crear_propuesta(
        contexto.id_caso, contexto.tarea_id, argumentos["accion"], argumentos["argumento"])
    return {
        "estado": "pendiente_confirmacion",
        "propuesta_id": propuesta.get("id", propuesta.get("propuesta_id")),
        "accion": argumentos["accion"],
        "mensaje": "La propuesta quedó pendiente: solo el analista puede confirmarla en la pantalla.",
    }


def _declarar_fuera_de_alcance(argumentos: dict, contexto: ContextoHerramientas) -> dict:
    # No toca la base: su efecto es que el bucle marque la tarea como rechazo
    # (EstadoTarea.rechazo_declarado) de forma determinista, sin leer el texto.
    return {
        "registrado": True,
        "mensaje": ("Rechazo registrado. Ahora explícale al analista en una o dos frases por qué no puedes "
                    "ayudar con eso y qué sí puedes hacer con el caso abierto."),
    }


# --- Esquemas ---------------------------------------------------------------------------
_ID_CASO = {"type": "string", "description": DESCRIPCION_PARAMETRO_ID_CASO}


def _esquema(propiedades: dict, requeridos: list[str]) -> dict:
    return {"type": "object", "properties": propiedades, "required": requeridos}


HERRAMIENTAS: dict[str, Herramienta] = {
    h.nombre: h for h in [
        Herramienta("obtener_caso", DESCRIPCIONES["obtener_caso"],
                    _esquema({"id_caso": _ID_CASO}, ["id_caso"]), False, _obtener_caso),
        Herramienta("obtener_perfil_cuenta", DESCRIPCIONES["obtener_perfil_cuenta"],
                    _esquema({"id_caso": _ID_CASO}, ["id_caso"]), False, _obtener_perfil_cuenta),
        Herramienta("obtener_historial_reciente", DESCRIPCIONES["obtener_historial_reciente"],
                    _esquema({"id_caso": _ID_CASO,
                              "dias": {"type": "integer", "description": "Días hacia atrás, de 1 a 30 (normalmente 7)."}},
                             ["id_caso"]), False, _obtener_historial_reciente),
        Herramienta("obtener_score_y_umbrales", DESCRIPCIONES["obtener_score_y_umbrales"],
                    _esquema({"id_caso": _ID_CASO}, ["id_caso"]), False, _obtener_score_y_umbrales),
        Herramienta("registrar_decision", DESCRIPCIONES["registrar_decision"],
                    _esquema({"id_caso": _ID_CASO,
                              "accion": {"type": "string", "enum": list(ACCIONES_DE_DECISION),
                                         "description": "confirmar_bloqueo, descartar o escalar."},
                              "argumento": {"type": "string",
                                            "description": "Por qué, en una o dos frases, con la evidencia del caso."}},
                             ["id_caso", "accion", "argumento"]), True, _registrar_decision),
        Herramienta("declarar_fuera_de_alcance", DESCRIPCIONES["declarar_fuera_de_alcance"],
                    _esquema({"motivo": {"type": "string",
                                         "description": "En una frase, qué pidió el analista y por qué no se puede."}},
                             ["motivo"]), False, _declarar_fuera_de_alcance, solo_pregunta=True),
    ]
}

# En modo explicación el agente solo lee el caso: no propone decisiones ni rechaza.
SOLO_LECTURA = [n for n, h in HERRAMIENTAS.items() if not h.escribe and not h.solo_pregunta]


def nombres_para(tipo: str) -> list[str]:
    """Nombres de las herramientas permitidas en el modo de la tarea (el bucle rechaza las demás)."""
    return SOLO_LECTURA if tipo == "explicacion" else list(HERRAMIENTAS)


def esquemas_para(tipo: str) -> list[dict]:
    """Herramientas que se le ofrecen al modelo según el modo de la tarea."""
    return [HERRAMIENTAS[n].esquema_neutro() for n in nombres_para(tipo)]


_TIPOS_JSON = {"string": str, "integer": int, "number": (int, float), "boolean": bool, "object": dict, "array": list}


def validar_argumentos(herramienta: Herramienta, argumentos: dict) -> str | None:
    """Revisión mínima de los argumentos contra el esquema; devuelve el problema o None.

    No es un validador de JSON Schema completo: revisa lo que nuestros esquemas usan
    (requeridos, tipo y enum), que es lo que un modelo suele equivocar.
    """
    if not isinstance(argumentos, dict) or "_json_invalido" in argumentos:
        return "los argumentos no son un objeto JSON válido"
    propiedades = herramienta.parametros.get("properties", {})
    for requerido in herramienta.parametros.get("required", []):
        if requerido not in argumentos:
            return f"falta el argumento obligatorio «{requerido}»"
    for nombre, valor in argumentos.items():
        if nombre not in propiedades:
            return f"argumento desconocido «{nombre}»"
        esquema = propiedades[nombre]
        tipo_python = _TIPOS_JSON.get(esquema.get("type"))
        # Gemini a veces manda enteros como 7.0: se aceptan si no tienen parte decimal.
        if esquema.get("type") == "integer" and isinstance(valor, float) and valor.is_integer():
            argumentos[nombre] = valor = int(valor)
        if tipo_python and not isinstance(valor, tipo_python):
            return f"«{nombre}» debe ser de tipo {esquema['type']}"
        # En Python True es un int: hay que rechazarlo a mano donde se espera un número.
        if esquema.get("type") in ("integer", "number") and isinstance(valor, bool):
            return f"«{nombre}» debe ser de tipo {esquema['type']}"
        if "enum" in esquema and valor not in esquema["enum"]:
            return f"«{nombre}» debe ser uno de: {', '.join(esquema['enum'])}"
    return None
