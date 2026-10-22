"""Cliente propio de Claude (Messages API) con tool use y streaming SSE.

Es el proveedor de respaldo de la cascada (diseno/agente.md). Igual que gemini.py,
se escribe a mano con httpx para que el formato quede a la vista:

- de ida: Mensaje neutro → `messages` de Claude (rol "user"/"assistant", bloques
  `text`, `tool_use`, `tool_result`), herramientas neutras → `tools[].input_schema`;
- de vuelta: los eventos SSE (`message_start`, `content_block_start`,
  `content_block_delta`, `message_delta`, `error`) → fragmentos de texto,
  LlamadaHerramienta y tokens.

Los argumentos de una herramienta llegan por pedazos de JSON (`input_json_delta`) y
solo se pueden leer cuando el bloque termina; por eso se acumulan por índice.
"""

import json
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

URL_MENSAJES = "https://api.anthropic.com/v1/messages"
VERSION_API = "2023-06-01"


class ClienteClaude:
    nombre = "claude"

    def __init__(self, llave: str, modelo: str, cliente: httpx.Client | None = None,
                 razonamiento: bool = False):
        self.llave = llave
        self.modelo = modelo
        self.cliente = cliente or httpx.Client()
        # Haiku 5.5 razona por defecto: medido el 2026-10-21, gastaba ~1 400 tokens de
        # pensamiento invisibles por respuesta, subía la espera del primer token a ~9 s
        # y casi llenaba max_tokens. Para redactar sobre evidencia ya calculada no hace
        # falta; se reactiva con CLAUDE_RAZONAMIENTO=true.
        self.razonamiento = razonamiento

    # --- Traducción de ida ------------------------------------------------------------
    @staticmethod
    def traducir_herramientas(herramientas: list[dict]) -> list[dict]:
        return [
            {"name": h["nombre"], "description": h["descripcion"], "input_schema": h["parametros"]}
            for h in herramientas
        ]

    @staticmethod
    def traducir_mensajes(mensajes: list[Mensaje]) -> list[dict]:
        """Lista neutra → `messages` de Claude.

        Los resultados de herramientas van como bloques tool_result en un turno "user";
        Claude exige que todos los resultados de un mismo turno del asistente lleguen
        juntos en el siguiente mensaje, así que los seguidos se agrupan.
        """
        salida = []
        for mensaje in mensajes:
            if mensaje.rol == "usuario":
                salida.append({"role": "user", "content": mensaje.texto})
            elif mensaje.rol == "asistente":
                bloques = []
                if mensaje.texto:  # Claude rechaza bloques de texto vacíos
                    bloques.append({"type": "text", "text": mensaje.texto})
                for llamada in mensaje.llamadas:
                    bloques.append({"type": "tool_use", "id": llamada.id,
                                    "name": llamada.nombre, "input": llamada.argumentos})
                salida.append({"role": "assistant", "content": bloques})
            elif mensaje.rol == "herramienta":
                bloque = {"type": "tool_result", "tool_use_id": mensaje.id_llamada,
                          "content": json.dumps(mensaje.resultado or {}, ensure_ascii=False)}
                anterior = salida[-1] if salida else None
                if (anterior and anterior["role"] == "user" and isinstance(anterior["content"], list)
                        and anterior["content"][0].get("type") == "tool_result"):
                    anterior["content"].append(bloque)
                else:
                    salida.append({"role": "user", "content": [bloque]})
        return salida

    def armar_cuerpo(self, sistema: str, mensajes: list[Mensaje], herramientas: list[dict],
                     max_tokens: int) -> dict:
        cuerpo = {
            "model": self.modelo,
            "max_tokens": max_tokens,
            "system": sistema,
            "messages": self.traducir_mensajes(mensajes),
            "stream": True,
        }
        if herramientas:
            cuerpo["tools"] = self.traducir_herramientas(herramientas)
        if not self.razonamiento:
            cuerpo["thinking"] = {"type": "disabled"}
        return cuerpo

    # --- Llamada y traducción de vuelta ------------------------------------------------
    def generar(self, sistema: str, mensajes: list[Mensaje], herramientas: list[dict],
                max_tokens: int, timeout_s: float) -> Iterator[tuple[str, object]]:
        if not self.llave:
            raise ErrorProveedor("sin_llave", "ANTHROPIC_API_KEY no está configurada")

        encabezados = {
            "x-api-key": self.llave,
            "anthropic-version": VERSION_API,
            "content-type": "application/json",
        }
        cuerpo = self.armar_cuerpo(sistema, mensajes, herramientas, max_tokens)

        texto_total = []
        bloques_herramienta = {}   # índice del bloque → {"id", "nombre", "json_parcial"}
        tokens_entrada = tokens_salida = 0
        lineas = lineas_de_post_en_streaming(self.cliente, URL_MENSAJES, encabezados, cuerpo, timeout_s, "Claude")
        for evento, datos in leer_eventos_sse(lineas):
            tipo = datos.get("type", evento)
            if tipo == "message_start":
                uso = datos.get("message", {}).get("usage", {})
                tokens_entrada = uso.get("input_tokens", 0)
                tokens_salida = uso.get("output_tokens", 0)
            elif tipo == "content_block_start":
                bloque = datos.get("content_block", {})
                if bloque.get("type") == "tool_use":
                    bloques_herramienta[datos["index"]] = {
                        "id": bloque["id"], "nombre": bloque["name"], "json_parcial": []}
            elif tipo == "content_block_delta":
                delta = datos.get("delta", {})
                if delta.get("type") == "text_delta":
                    texto_total.append(delta["text"])
                    yield "texto", delta["text"]
                elif delta.get("type") == "input_json_delta":
                    bloques_herramienta[datos["index"]]["json_parcial"].append(delta.get("partial_json", ""))
            elif tipo == "message_delta":
                # El conteo de salida en message_delta es acumulado.
                tokens_salida = datos.get("usage", {}).get("output_tokens", tokens_salida)
            elif tipo == "error":
                # Error a mitad del flujo (por ejemplo, overloaded_error) con HTTP 200.
                error = datos.get("error", {})
                tipo_error = error.get("type", "")
                normalizado = ("cuota" if tipo_error == "rate_limit_error"
                               else "servidor" if tipo_error in ("overloaded_error", "api_error")
                               else "solicitud")
                raise ErrorProveedor(normalizado, f"Claude: {tipo_error} {error.get('message', '')}")

        llamadas = []
        for indice in sorted(bloques_herramienta):
            bloque = bloques_herramienta[indice]
            texto_json = "".join(bloque["json_parcial"]) or "{}"
            try:
                argumentos = json.loads(texto_json)
            except json.JSONDecodeError:
                # Se deja pasar: el bucle lo trata como "argumentos inválidos".
                argumentos = {"_json_invalido": texto_json}
            llamadas.append(LlamadaHerramienta(id=bloque["id"], nombre=bloque["nombre"], argumentos=argumentos))

        yield "fin", RespuestaModelo(
            texto="".join(texto_total),
            llamadas=llamadas,
            tokens_entrada=tokens_entrada,
            tokens_salida=tokens_salida,
            proveedor=self.nombre,
            modelo=self.modelo,
        )
