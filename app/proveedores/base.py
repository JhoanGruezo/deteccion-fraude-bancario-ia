"""Tipos comunes a todos los proveedores de IA y el error que todos lanzan.

Existe para que el bucle del agente no sepa nada de Gemini ni de Claude: habla con
"un proveedor" que recibe mensajes en un formato neutro (en español, definido aquí)
y devuelve fragmentos de texto y llamadas a herramientas en ese mismo formato. Cada
cliente (gemini.py, claude.py) traduce de ida y de vuelta al formato de su API. Así
se cumple el criterio de "capa de proveedor desacoplada": cambiar o agregar un
proveedor no toca el bucle (ver diseno/agente.md, "Tipos comunes").

También vive aquí el lector de SSE (Server-Sent Events) que comparten los dos
clientes, porque ambos transmiten la respuesta por ese mismo protocolo.
"""

import json
import time
from dataclasses import dataclass, field
from typing import Iterator, Protocol

import httpx


@dataclass
class LlamadaHerramienta:
    """Una herramienta que el modelo pidió ejecutar."""
    id: str                 # id que devuelve el proveedor (Claude) o generado (Gemini)
    nombre: str
    argumentos: dict
    # Gemini 3 exige devolver la "firma de pensamiento" de cada llamada en el turno
    # siguiente; si no viene (Claude), queda en None.
    firma: str | None = None


@dataclass
class Mensaje:
    """Un turno de la conversación, en el formato neutro del proyecto."""
    rol: str                # "usuario" | "asistente" | "herramienta"
    texto: str = ""
    llamadas: list[LlamadaHerramienta] = field(default_factory=list)   # rol asistente
    id_llamada: str | None = None                                       # rol herramienta
    nombre_herramienta: str | None = None
    resultado: dict | None = None


@dataclass
class RespuestaModelo:
    """Lo que dejó una llamada completa al modelo, ya traducido."""
    texto: str
    llamadas: list[LlamadaHerramienta]
    tokens_entrada: int
    tokens_salida: int
    proveedor: str
    modelo: str


# Tipos de error que entiende la cascada. Los reintentables son fallas pasajeras del
# lado del proveedor; los demás no se arreglan esperando, así que se conmuta de una.
TIPOS_REINTENTABLES = {"cuota", "timeout", "servidor"}


class ErrorProveedor(Exception):
    """Error normalizado de cualquier proveedor.

    tipo: "cuota" (429) | "timeout" | "servidor" (5xx o red) | "autenticacion" (401/403)
          | "solicitud" (otro 4xx) | "sin_llave" | "agotados" (la cascada se quedó sin
          proveedores).
    """

    def __init__(self, tipo: str, mensaje: str, reintentable: bool | None = None):
        super().__init__(mensaje)
        self.tipo = tipo
        self.mensaje = mensaje
        self.reintentable = tipo in TIPOS_REINTENTABLES if reintentable is None else reintentable


class Proveedor(Protocol):
    """Lo que el bucle y la cascada esperan de cualquier cliente de IA."""
    nombre: str
    modelo: str

    def generar(self, sistema: str, mensajes: list[Mensaje], herramientas: list[dict],
                max_tokens: int, timeout_s: float) -> Iterator[tuple[str, object]]:
        """Produce ("texto", fragmento) mientras llega y termina con ("fin", RespuestaModelo).
        Lanza ErrorProveedor."""
        ...


def error_desde_estado_http(codigo: int, cuerpo: str, proveedor: str) -> ErrorProveedor:
    """Traduce un código HTTP de error al tipo normalizado (igual para los dos proveedores)."""
    detalle = f"{proveedor} respondió HTTP {codigo}: {cuerpo[:300]}"
    if codigo == 429:
        return ErrorProveedor("cuota", detalle)
    if codigo in (401, 403):
        return ErrorProveedor("autenticacion", detalle)
    if codigo >= 500:
        return ErrorProveedor("servidor", detalle)
    return ErrorProveedor("solicitud", detalle)


def lineas_de_post_en_streaming(cliente: httpx.Client, url: str, encabezados: dict, cuerpo: dict,
                                timeout_s: float, proveedor: str) -> Iterator[str]:
    """Hace el POST en modo streaming y entrega las líneas crudas de la respuesta.

    Concentra en un solo lugar la traducción de fallas de red a ErrorProveedor:
    código HTTP de error → error_desde_estado_http; httpx.TimeoutException → "timeout";
    cualquier otra falla de transporte (conexión rechazada, DNS) → "servidor".

    El timeout de httpx cuenta por operación de lectura, no por llamada completa: un
    proveedor que manda un fragmento cada 20 s nunca lo dispararía. Por eso además se
    lleva un plazo total (`limite`) y se revisa en cada línea; eso es lo que hace real
    el límite "timeout por llamada al modelo".
    """
    limite = time.monotonic() + timeout_s
    try:
        with cliente.stream("POST", url, headers=encabezados, json=cuerpo, timeout=timeout_s) as respuesta:
            if respuesta.status_code != 200:
                cuerpo_error = respuesta.read().decode("utf-8", errors="replace")
                raise error_desde_estado_http(respuesta.status_code, cuerpo_error, proveedor)
            for linea in respuesta.iter_lines():
                if time.monotonic() > limite:
                    raise ErrorProveedor("timeout", f"{proveedor} superó {timeout_s:g} s en total")
                yield linea
    except httpx.TimeoutException as error:
        raise ErrorProveedor("timeout", f"{proveedor} no respondió en {timeout_s:g} s ({type(error).__name__})")
    except httpx.TransportError as error:
        raise ErrorProveedor("servidor", f"Falla de red hablando con {proveedor}: {error}")


def leer_eventos_sse(lineas: Iterator[str]) -> Iterator[tuple[str | None, dict]]:
    """Agrupa las líneas de un flujo SSE en eventos (nombre, datos JSON).

    En SSE cada evento son líneas "event: ..." y "data: ..." terminadas por una línea
    vacía. Gemini solo manda "data:"; Claude manda también "event:". Las líneas que
    no son JSON (por ejemplo, comentarios de keep-alive) se ignoran.
    """
    nombre_evento = None
    datos = []
    for linea in lineas:
        if linea == "":
            if datos:
                texto = "\n".join(datos)
                try:
                    yield nombre_evento, json.loads(texto)
                except json.JSONDecodeError:
                    pass
            nombre_evento, datos = None, []
        elif linea.startswith("event:"):
            nombre_evento = linea[len("event:"):].strip()
        elif linea.startswith("data:"):
            datos.append(linea[len("data:"):].strip())
    # Un flujo que termina sin la línea vacía final todavía puede traer un evento.
    if datos:
        try:
            yield nombre_evento, json.loads("\n".join(datos))
        except json.JSONDecodeError:
            pass
