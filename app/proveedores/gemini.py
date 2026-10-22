"""Cliente propio de Gemini (REST v1beta) con tool calling y streaming SSE.

Por qué un cliente a mano con httpx y no el SDK de Google: el curso evalúa entender
el formato de tool calling de cada proveedor, y aquí queda a la vista (diseno/agente.md,
"Decisiones de esta sesión"). Este módulo solo traduce:

- de ida: Mensaje neutro → `contents` de Gemini (rol "user"/"model", partes
  `text`, `functionCall`, `functionResponse`), herramientas neutras →
  `tools: [{functionDeclarations: [...]}]`;
- de vuelta: cada evento SSE de `streamGenerateContent?alt=sse` → fragmentos de texto
  y LlamadaHerramienta; `usageMetadata` → tokens de entrada y salida.

No reintenta ni conmuta: eso es trabajo de cascada.py.
"""

import itertools
from typing import Iterator

import httpx

from app.proveedores.base import (
    ErrorProveedor,
    LlamadaHerramienta,
    Mensaje,
    RespuestaModelo,
    leer_eventos_sse,
    lineas_de_post_en_streaming,
)

URL_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

# Gemini 3 pide que cada functionCall devuelto en el historial lleve la firma de
# pensamiento que venía con él. Si la llamada la hizo otro proveedor (por ejemplo,
# Claude antes de una conmutación) no hay firma; la documentación de Gemini acepta
# este valor para saltarse la validación en ese caso.
FIRMA_AUSENTE = "skip_thought_signature_validator"

# Gemini no siempre manda id en sus functionCall; se generan ids propios para poder
# casar cada resultado con su llamada en la traza.
_contador_ids = itertools.count(1)


class ClienteGemini:
    nombre = "gemini"

    def __init__(self, llave: str, modelo: str, cliente: httpx.Client | None = None,
                 nivel_razonamiento: str | None = "low"):
        self.llave = llave
        self.modelo = modelo
        # El cliente HTTP se puede inyectar: las pruebas pasan uno con MockTransport.
        self.cliente = cliente or httpx.Client()
        # Razonamiento bajo: en Gemini 3 los tokens de "pensamiento" salen del mismo
        # max_tokens de la respuesta y, sin acotarlos, pueden truncar el JSON.
        self.nivel_razonamiento = nivel_razonamiento

    # --- Traducción de ida ------------------------------------------------------------
    @staticmethod
    def traducir_herramientas(herramientas: list[dict]) -> list[dict]:
        """Formato neutro {nombre, descripcion, parametros} → functionDeclarations."""
        if not herramientas:
            return []
        declaraciones = [
            {"name": h["nombre"], "description": h["descripcion"], "parameters": h["parametros"]}
            for h in herramientas
        ]
        return [{"functionDeclarations": declaraciones}]

    @staticmethod
    def traducir_mensajes(mensajes: list[Mensaje]) -> list[dict]:
        """Lista neutra → `contents` de Gemini.

        Gemini no tiene rol "herramienta": los resultados viajan como partes
        functionResponse dentro de un turno "user". Si hay varios resultados seguidos
        (llamadas en paralelo), van todos en el mismo turno.
        """
        contenidos = []
        for mensaje in mensajes:
            if mensaje.rol == "usuario":
                contenidos.append({"role": "user", "parts": [{"text": mensaje.texto}]})
            elif mensaje.rol == "asistente":
                partes = []
                if mensaje.texto:
                    partes.append({"text": mensaje.texto})
                for llamada in mensaje.llamadas:
                    partes.append({
                        "functionCall": {"name": llamada.nombre, "args": llamada.argumentos},
                        "thoughtSignature": llamada.firma or FIRMA_AUSENTE,
                    })
                contenidos.append({"role": "model", "parts": partes})
            elif mensaje.rol == "herramienta":
                parte = {"functionResponse": {"name": mensaje.nombre_herramienta,
                                              "response": mensaje.resultado or {}}}
                anterior = contenidos[-1] if contenidos else None
                if anterior and anterior["role"] == "user" and "functionResponse" in anterior["parts"][0]:
                    anterior["parts"].append(parte)
                else:
                    contenidos.append({"role": "user", "parts": [parte]})
        return contenidos

    def armar_cuerpo(self, sistema: str, mensajes: list[Mensaje], herramientas: list[dict],
                     max_tokens: int) -> dict:
        configuracion = {"maxOutputTokens": max_tokens}
        if self.nivel_razonamiento:
            configuracion["thinkingConfig"] = {"thinkingLevel": self.nivel_razonamiento}
        cuerpo = {
            "systemInstruction": {"parts": [{"text": sistema}]},
            "contents": self.traducir_mensajes(mensajes),
            "generationConfig": configuracion,
        }
        declaraciones = self.traducir_herramientas(herramientas)
        if declaraciones:
            cuerpo["tools"] = declaraciones
        return cuerpo

    # --- Llamada y traducción de vuelta ------------------------------------------------
    def generar(self, sistema: str, mensajes: list[Mensaje], herramientas: list[dict],
                max_tokens: int, timeout_s: float) -> Iterator[tuple[str, object]]:
        if not self.llave:
            raise ErrorProveedor("sin_llave", "GEMINI_API_KEY no está configurada")

        url = f"{URL_BASE}/{self.modelo}:streamGenerateContent?alt=sse"
        encabezados = {"x-goog-api-key": self.llave, "content-type": "application/json"}
        cuerpo = self.armar_cuerpo(sistema, mensajes, herramientas, max_tokens)

        texto_total = []
        llamadas = []
        uso = {}
        lineas = lineas_de_post_en_streaming(self.cliente, url, encabezados, cuerpo, timeout_s, "Gemini")
        for _, datos in leer_eventos_sse(lineas):
            # Un error a mitad del flujo llega como objeto {"error": {...}} con HTTP 200.
            if "error" in datos:
                codigo = datos["error"].get("code", 500)
                tipo = "cuota" if codigo == 429 else "servidor" if codigo >= 500 else "solicitud"
                raise ErrorProveedor(tipo, f"Gemini: {datos['error'].get('message', '')}")

            # usageMetadata viene acumulado: el último evento trae el total.
            uso = datos.get("usageMetadata", uso)
            for candidato in datos.get("candidates", [])[:1]:
                for parte in candidato.get("content", {}).get("parts", []):
                    if parte.get("thought"):
                        continue  # resúmenes de razonamiento: no son respuesta
                    if "functionCall" in parte:
                        llamada = parte["functionCall"]
                        llamadas.append(LlamadaHerramienta(
                            id=llamada.get("id") or f"gemini_{next(_contador_ids)}",
                            nombre=llamada.get("name", ""),
                            argumentos=llamada.get("args") or {},
                            firma=parte.get("thoughtSignature"),
                        ))
                    elif parte.get("text"):
                        texto_total.append(parte["text"])
                        yield "texto", parte["text"]

        yield "fin", RespuestaModelo(
            texto="".join(texto_total),
            llamadas=llamadas,
            tokens_entrada=uso.get("promptTokenCount", 0),
            # El razonamiento se cobra como salida, así que cuenta para el presupuesto.
            tokens_salida=uso.get("candidatesTokenCount", 0) + uso.get("thoughtsTokenCount", 0),
            proveedor=self.nombre,
            modelo=self.modelo,
        )
