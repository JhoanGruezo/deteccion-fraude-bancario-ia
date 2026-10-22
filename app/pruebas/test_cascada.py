"""Pruebas de la cascada: backoff, conmutación, agotados y fallas forzadas, sin red.

`ProveedorFalso` sigue un guion: cada llamada a generar consume el siguiente
elemento, que es un ErrorProveedor (se lanza) o una RespuestaModelo (se transmite).
Las esperas del backoff se registran en una lista en vez de dormir.
"""

import pytest

from app.proveedores.base import ErrorProveedor, LlamadaHerramienta, RespuestaModelo
from app.proveedores.cascada import ProveedorEnCascada


class ProveedorFalso:
    def __init__(self, nombre, guion, modelo=None):
        self.nombre = nombre
        self.modelo = modelo or f"{nombre}-falso"
        self.guion = list(guion)
        self.llamadas = 0
        self.mensajes_recibidos = []

    def generar(self, sistema, mensajes, herramientas, max_tokens, timeout_s):
        self.llamadas += 1
        self.mensajes_recibidos.append(list(mensajes))
        paso = self.guion.pop(0) if len(self.guion) > 1 else self.guion[0]   # el último se repite
        if isinstance(paso, ErrorProveedor):
            raise ErrorProveedor(paso.tipo, paso.mensaje)
        if callable(paso):
            paso = paso(mensajes)
        if paso.texto:
            mitad = len(paso.texto) // 2
            yield "texto", paso.texto[:mitad]
            yield "texto", paso.texto[mitad:]
        yield "fin", RespuestaModelo(paso.texto, list(paso.llamadas), paso.tokens_entrada, paso.tokens_salida,
                                     self.nombre, self.modelo)


def respuesta(texto="", llamadas=(), entrada=100, salida=50):
    return RespuestaModelo(texto, list(llamadas), entrada, salida, "", "")


def llamada(nombre, **argumentos):
    return LlamadaHerramienta(id=f"id_{nombre}", nombre=nombre, argumentos=argumentos)


def correr(cascada, falla=None):
    """Consume generar y devuelve (eventos, respuesta final)."""
    eventos, final = [], None
    for clase, dato in cascada.generar("sistema", [], [], 100, 5, falla_forzada=falla):
        if clase == "evento":
            eventos.append(dato)
        elif clase == "fin":
            final = dato
    return eventos, final


def test_429_hace_backoff_y_conmuta():
    esperas = []
    gemini = ProveedorFalso("gemini", [ErrorProveedor("cuota", "429")])
    claude = ProveedorFalso("claude", [respuesta("hola")])
    cascada = ProveedorEnCascada([gemini, claude], esperas=(1, 2, 4), dormir=esperas.append)

    eventos, final = correr(cascada)

    assert esperas == [1, 2, 4]
    assert gemini.llamadas == 4                      # 1 intento + 3 reintentos
    assert [e["tipo"] for e in eventos] == ["reintento", "reintento", "reintento", "conmutacion"]
    assert eventos[1]["texto"] == "Gemini respondió 429 (cuota agotada) · reintento 2/3 en 2 s"
    assert eventos[3]["de"] == "gemini" and eventos[3]["a"] == "claude"
    assert final.proveedor == "claude" and final.texto == "hola"


def test_tras_conmutar_la_siguiente_llamada_empieza_en_el_respaldo():
    gemini = ProveedorFalso("gemini", [ErrorProveedor("cuota", "429")])
    claude = ProveedorFalso("claude", [respuesta("uno")])
    cascada = ProveedorEnCascada([gemini, claude], esperas=(0, 0, 0), dormir=lambda s: None)
    correr(cascada)
    eventos, final = correr(cascada)
    assert eventos == [] and final.proveedor == "claude"
    assert gemini.llamadas == 4                      # no se le volvió a pegar


def test_error_pasajero_que_se_recupera_no_conmuta():
    gemini = ProveedorFalso("gemini", [ErrorProveedor("servidor", "503"), respuesta("ok")])
    cascada = ProveedorEnCascada([gemini], esperas=(0, 0, 0), dormir=lambda s: None)
    eventos, final = correr(cascada)
    assert [e["tipo"] for e in eventos] == ["reintento"]
    assert final.texto == "ok"


def test_autenticacion_conmuta_sin_esperar():
    esperas = []
    gemini = ProveedorFalso("gemini", [ErrorProveedor("autenticacion", "401")])
    claude = ProveedorFalso("claude", [respuesta("ok")])
    cascada = ProveedorEnCascada([gemini, claude], esperas=(1, 2, 4), dormir=esperas.append)
    eventos, final = correr(cascada)
    assert esperas == []
    assert gemini.llamadas == 1
    assert [e["tipo"] for e in eventos] == ["conmutacion"]
    assert final.proveedor == "claude"


def test_todo_caido_lanza_agotados():
    gemini = ProveedorFalso("gemini", [ErrorProveedor("servidor", "500")])
    claude = ProveedorFalso("claude", [ErrorProveedor("cuota", "429")])
    cascada = ProveedorEnCascada([gemini, claude], esperas=(0, 0, 0), dormir=lambda s: None)
    eventos = []
    with pytest.raises(ErrorProveedor) as error:
        for clase, dato in cascada.generar("s", [], [], 10, 1):
            eventos.append(dato)
    assert error.value.tipo == "agotados"
    assert error.value.solo_timeouts is False
    assert sum(e["tipo"] == "reintento" for e in eventos) == 6
    assert sum(e["tipo"] == "conmutacion" for e in eventos) == 1


def test_solo_timeouts_se_marcan():
    gemini = ProveedorFalso("gemini", [ErrorProveedor("timeout", "lento")])
    cascada = ProveedorEnCascada([gemini], esperas=(0,), dormir=lambda s: None)
    with pytest.raises(ErrorProveedor) as error:
        correr(cascada)
    assert error.value.solo_timeouts is True


def test_cascada_vacia():
    with pytest.raises(ErrorProveedor) as error:
        correr(ProveedorEnCascada([]))
    assert error.value.tipo == "agotados"


def test_falla_forzada_429_no_llama_al_principal():
    gemini = ProveedorFalso("gemini", [respuesta("no debería")])
    claude = ProveedorFalso("claude", [respuesta("respaldo")])
    cascada = ProveedorEnCascada([gemini, claude], esperas=(0, 0, 0), dormir=lambda s: None)
    eventos, final = correr(cascada, falla="429")
    assert gemini.llamadas == 0                      # simulada antes de la red: no gasta cuota
    assert eventos[-1]["tipo"] == "conmutacion" and eventos[0]["motivo"] == "cuota"
    assert final.texto == "respaldo"


def test_falla_forzada_todo_tumba_ambos_sin_llamarlos():
    gemini = ProveedorFalso("gemini", [respuesta("x")])
    claude = ProveedorFalso("claude", [respuesta("y")])
    cascada = ProveedorEnCascada([gemini, claude], esperas=(0,), dormir=lambda s: None)
    with pytest.raises(ErrorProveedor):
        correr(cascada, falla="todo")
    assert gemini.llamadas == claude.llamadas == 0


def test_falla_forzada_json_trunca_solo_la_primera_respuesta_final():
    gemini = ProveedorFalso("gemini", [
        respuesta(llamadas=[llamada("obtener_caso", id_caso="X")]),
        respuesta('{"que_paso": "uno dos tres cuatro"}'),
        respuesta('{"que_paso": "completo"}'),
    ])
    cascada = ProveedorEnCascada([gemini])
    _, primera = correr(cascada, falla="json")
    assert primera.llamadas                          # la de herramientas pasa intacta
    eventos, final = correr(cascada, falla="json")
    original = '{"que_paso": "uno dos tres cuatro"}'
    assert final.texto == original[: len(original) // 2]   # cortada a la mitad
    assert eventos[0]["tipo"] == "estado"
    _, siguiente = correr(cascada, falla="json")
    assert siguiente.texto == '{"que_paso": "completo"}'
