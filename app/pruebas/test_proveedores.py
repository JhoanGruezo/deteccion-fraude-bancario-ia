"""Traducción de formatos de Gemini y Claude con respuestas SSE de ejemplo, sin red.

Cada cliente recibe un httpx.Client con MockTransport: la función `manejador`
inspecciona la petición que el cliente armó (URL, encabezados, cuerpo) y devuelve un
flujo SSE escrito a mano con la forma documentada de cada API.
"""

import json

import httpx
import pytest

from app.proveedores.base import ErrorProveedor, LlamadaHerramienta, Mensaje
from app.proveedores.claude import ClienteClaude
from app.proveedores.gemini import FIRMA_AUSENTE, ClienteGemini

HERRAMIENTAS = [{"nombre": "obtener_caso", "descripcion": "Devuelve el caso.",
                 "parametros": {"type": "object", "properties": {"id_caso": {"type": "string"}},
                                "required": ["id_caso"]}}]


def sse(eventos, con_nombre=False):
    """Arma el cuerpo SSE: una línea data (y event, si aplica) por evento y una línea vacía."""
    lineas = []
    for evento in eventos:
        if con_nombre:
            lineas.append(f"event: {evento['type']}")
        lineas.append(f"data: {json.dumps(evento)}")
        lineas.append("")
    return ("\n".join(lineas) + "\n").encode()


def cliente_http(manejador):
    return httpx.Client(transport=httpx.MockTransport(manejador))


def consumir(generador):
    textos, final = [], None
    for clase, dato in generador:
        if clase == "texto":
            textos.append(dato)
        else:
            final = dato
    return textos, final


# --- Gemini ------------------------------------------------------------------------------
def test_gemini_traduce_peticion_y_llamada_a_herramienta():
    peticiones = []

    def manejador(peticion):
        peticiones.append(peticion)
        cuerpo = sse([
            {"candidates": [{"content": {"role": "model", "parts": [
                {"functionCall": {"name": "obtener_caso", "args": {"id_caso": "SPK-000001"}},
                 "thoughtSignature": "firma-abc"}]}}],
             "usageMetadata": {"promptTokenCount": 210, "candidatesTokenCount": 12, "thoughtsTokenCount": 30}},
        ])
        return httpx.Response(200, content=cuerpo, headers={"content-type": "text/event-stream"})

    cliente = ClienteGemini("llave-de-prueba", "gemini-3.8-flash", cliente=cliente_http(manejador))
    textos, final = consumir(cliente.generar("sistema", [Mensaje("usuario", "Explica el caso SPK-000001.")],
                                             HERRAMIENTAS, 1800, 25))

    peticion = peticiones[0]
    assert peticion.url.path.endswith("/models/gemini-3.8-flash:streamGenerateContent")
    assert peticion.url.params["alt"] == "sse"
    assert peticion.headers["x-goog-api-key"] == "llave-de-prueba"
    cuerpo = json.loads(peticion.content)
    assert cuerpo["systemInstruction"]["parts"][0]["text"] == "sistema"
    assert cuerpo["tools"][0]["functionDeclarations"][0]["name"] == "obtener_caso"
    assert cuerpo["generationConfig"]["maxOutputTokens"] == 1800

    assert textos == []
    assert final.llamadas[0].nombre == "obtener_caso"
    assert final.llamadas[0].argumentos == {"id_caso": "SPK-000001"}
    assert final.llamadas[0].firma == "firma-abc"
    assert (final.tokens_entrada, final.tokens_salida) == (210, 42)   # el razonamiento cuenta como salida


def test_gemini_transmite_texto_por_fragmentos():
    def manejador(peticion):
        return httpx.Response(200, content=sse([
            {"candidates": [{"content": {"parts": [{"text": "pensando...", "thought": True}]}}]},
            {"candidates": [{"content": {"parts": [{"text": '{"que_paso": '}]}}]},
            {"candidates": [{"content": {"parts": [{"text": '"algo"}'}]}, "finishReason": "STOP"}],
             "usageMetadata": {"promptTokenCount": 500, "candidatesTokenCount": 8}},
        ]))

    textos, final = consumir(ClienteGemini("k", "m", cliente=cliente_http(manejador)).generar("s", [], [], 10, 5))
    assert textos == ['{"que_paso": ', '"algo"}']
    assert final.texto == '{"que_paso": "algo"}' and final.llamadas == []
    assert (final.tokens_entrada, final.tokens_salida) == (500, 8)


def test_gemini_traduce_historial_con_resultados_agrupados():
    mensajes = [
        Mensaje("usuario", "Explica"),
        Mensaje("asistente", llamadas=[LlamadaHerramienta("a", "obtener_caso", {"id_caso": "X"}, firma="f1"),
                                       LlamadaHerramienta("b", "obtener_perfil_cuenta", {"id_caso": "X"})]),
        Mensaje("herramienta", id_llamada="a", nombre_herramienta="obtener_caso", resultado={"ok": 1}),
        Mensaje("herramienta", id_llamada="b", nombre_herramienta="obtener_perfil_cuenta", resultado={"ok": 2}),
    ]
    contenidos = ClienteGemini.traducir_mensajes(mensajes)
    assert [c["role"] for c in contenidos] == ["user", "model", "user"]
    assert contenidos[1]["parts"][0]["thoughtSignature"] == "f1"
    assert contenidos[1]["parts"][1]["thoughtSignature"] == FIRMA_AUSENTE    # llamada sin firma (p. ej. de Claude)
    assert [p["functionResponse"]["name"] for p in contenidos[2]["parts"]] == ["obtener_caso", "obtener_perfil_cuenta"]


@pytest.mark.parametrize("codigo, tipo", [(429, "cuota"), (503, "servidor"), (401, "autenticacion"),
                                          (403, "autenticacion"), (400, "solicitud")])
def test_gemini_mapea_codigos_http(codigo, tipo):
    cliente = ClienteGemini("k", "m", cliente=cliente_http(lambda p: httpx.Response(codigo, text="error")))
    with pytest.raises(ErrorProveedor) as error:
        consumir(cliente.generar("s", [], [], 10, 5))
    assert error.value.tipo == tipo
    assert error.value.reintentable == (tipo in ("cuota", "servidor"))


def test_gemini_timeout_de_httpx_es_timeout():
    def manejador(peticion):
        raise httpx.ReadTimeout("lento", request=peticion)
    with pytest.raises(ErrorProveedor) as error:
        consumir(ClienteGemini("k", "m", cliente=cliente_http(manejador)).generar("s", [], [], 10, 5))
    assert error.value.tipo == "timeout" and error.value.reintentable


def test_gemini_falla_de_red_es_servidor():
    def manejador(peticion):
        raise httpx.ConnectError("sin red", request=peticion)
    with pytest.raises(ErrorProveedor) as error:
        consumir(ClienteGemini("k", "m", cliente=cliente_http(manejador)).generar("s", [], [], 10, 5))
    assert error.value.tipo == "servidor"


def test_sin_llave_no_llama_a_la_red():
    def manejador(peticion):
        raise AssertionError("no debía llamar")
    for cliente in (ClienteGemini("", "m", cliente=cliente_http(manejador)),
                    ClienteClaude("", "m", cliente=cliente_http(manejador))):
        with pytest.raises(ErrorProveedor) as error:
            consumir(cliente.generar("s", [], [], 10, 5))
        assert error.value.tipo == "sin_llave" and not error.value.reintentable


# --- Claude ------------------------------------------------------------------------------
EVENTOS_CLAUDE = [
    {"type": "message_start", "message": {"id": "msg_1", "role": "assistant", "content": [],
                                          "usage": {"input_tokens": 320, "output_tokens": 1}}},
    {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
    {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Voy a "}},
    {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "consultar."}},
    {"type": "content_block_stop", "index": 0},
    {"type": "content_block_start", "index": 1,
     "content_block": {"type": "tool_use", "id": "toolu_01", "name": "obtener_historial_reciente", "input": {}}},
    {"type": "content_block_delta", "index": 1, "delta": {"type": "input_json_delta", "partial_json": '{"id_caso": "SPK'}},
    {"type": "content_block_delta", "index": 1, "delta": {"type": "input_json_delta", "partial_json": '-000001", "dias": 7}'}},
    {"type": "content_block_stop", "index": 1},
    {"type": "ping"},
    {"type": "message_delta", "delta": {"stop_reason": "tool_use"}, "usage": {"output_tokens": 57}},
    {"type": "message_stop"},
]


def test_claude_traduce_peticion_texto_y_tool_use():
    peticiones = []

    def manejador(peticion):
        peticiones.append(peticion)
        return httpx.Response(200, content=sse(EVENTOS_CLAUDE, con_nombre=True))

    cliente = ClienteClaude("llave-de-prueba", "claude-haiku-5-5", cliente=cliente_http(manejador))
    textos, final = consumir(cliente.generar("sistema", [Mensaje("usuario", "Hola")], HERRAMIENTAS, 1800, 25))

    peticion = peticiones[0]
    assert str(peticion.url) == "https://api.anthropic.com/v1/messages"
    assert peticion.headers["x-api-key"] == "llave-de-prueba"
    assert peticion.headers["anthropic-version"] == "2023-06-01"
    cuerpo = json.loads(peticion.content)
    assert cuerpo["stream"] is True and cuerpo["system"] == "sistema" and cuerpo["max_tokens"] == 1800
    assert cuerpo["tools"][0]["input_schema"]["required"] == ["id_caso"]

    assert textos == ["Voy a ", "consultar."]
    assert final.texto == "Voy a consultar."
    assert final.llamadas[0].id == "toolu_01"
    assert final.llamadas[0].argumentos == {"id_caso": "SPK-000001", "dias": 7}
    assert (final.tokens_entrada, final.tokens_salida) == (320, 57)


def test_claude_traduce_historial_con_tool_result():
    mensajes = [
        Mensaje("usuario", "Explica"),
        Mensaje("asistente", texto="", llamadas=[LlamadaHerramienta("toolu_1", "obtener_caso", {"id_caso": "X"}),
                                                 LlamadaHerramienta("toolu_2", "obtener_perfil_cuenta", {"id_caso": "X"})]),
        Mensaje("herramienta", id_llamada="toolu_1", nombre_herramienta="obtener_caso", resultado={"monto": 291.8}),
        Mensaje("herramienta", id_llamada="toolu_2", nombre_herramienta="obtener_perfil_cuenta", resultado={}),
    ]
    salida = ClienteClaude.traducir_mensajes(mensajes)
    assert [m["role"] for m in salida] == ["user", "assistant", "user"]
    assert [b["type"] for b in salida[1]["content"]] == ["tool_use", "tool_use"]   # sin bloque de texto vacío
    assert [b["tool_use_id"] for b in salida[2]["content"]] == ["toolu_1", "toolu_2"]
    assert json.loads(salida[2]["content"][0]["content"]) == {"monto": 291.8}


def test_claude_error_a_mitad_del_flujo():
    eventos = [EVENTOS_CLAUDE[0], {"type": "error", "error": {"type": "overloaded_error", "message": "Overloaded"}}]
    cliente = ClienteClaude("k", "m", cliente=cliente_http(lambda p: httpx.Response(200, content=sse(eventos, True))))
    with pytest.raises(ErrorProveedor) as error:
        consumir(cliente.generar("s", [], [], 10, 5))
    assert error.value.tipo == "servidor" and error.value.reintentable


def test_claude_429_es_cuota():
    cliente = ClienteClaude("k", "m", cliente=cliente_http(lambda p: httpx.Response(429, json={"error": {}})))
    with pytest.raises(ErrorProveedor) as error:
        consumir(cliente.generar("s", [], [], 10, 5))
    assert error.value.tipo == "cuota"
