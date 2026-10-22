"""Frontera de salida hacia el navegador: Server-Sent Events reales y depuración de datos.

Por qué existe este módulo aparte de las rutas:

1. El profesor revisa en DevTools → Network que la explicación llegue por
   `text/event-stream` real (está prohibido el "streaming falso"). Aquí vive el único
   código que convierte los eventos del agente en texto SSE, para que el formato
   (`id:`, `event:`, `data:`, `: ping`) sea idéntico en todas las rutas y se pueda
   probar en un solo lugar.
2. El generador del agente es síncrono y se bloquea mientras el modelo piensa. Si lo
   recorriéramos directamente dentro de la respuesta, no habría forma de mandar el
   `: ping` cada 15 s que evita que un proxy corte la conexión. Por eso el agente
   corre en un hilo propio que deja los eventos en una cola, y la respuesta lee esa
   cola con un tiempo de espera: si vence, escribe un ping.
3. Ese mismo hilo resuelve un caso borde de los requisitos: si el analista cierra el
   panel a mitad del stream, la respuesta HTTP se cancela pero el hilo sigue
   consumiendo al agente hasta el final, así que la explicación se guarda igual.
4. Todo lo que sale hacia la interfaz pasa por `depurar_para_interfaz`: es una segunda
   barrera (la primera está en el repositorio) para que nunca se filtre
   `fraude_confirmado_dataset` ni el número completo de la tarjeta.
"""

import itertools
import json
import logging
import queue
import threading
import uuid
from typing import Callable, Iterator

from fastapi.responses import StreamingResponse

registro = logging.getLogger("app.api.sse")

# Cada cuánto se manda un comentario `: ping` si el agente no ha producido nada.
# 15 s queda por debajo del corte típico de proxies (30-60 s). Las pruebas lo bajan.
INTERVALO_PING_S = 15.0

# Campos que jamás pueden llegar al navegador. `id_cuenta` es el número completo de la
# tarjeta en Sparkov; la interfaz solo usa `tarjeta_enmascarada`.
CAMPOS_PROHIBIDOS = frozenset({"fraude_confirmado_dataset", "id_cuenta"})

CABECERAS_SSE = {
    # Sin caché: cada apertura es una petición nueva al agente (o a su caché propia).
    "Cache-Control": "no-cache",
    # Nginx y otros proxies acumulan la respuesta si no se les pide lo contrario;
    # eso convertiría el SSE real en una respuesta que llega toda al final.
    "X-Accel-Buffering": "no",
    "Connection": "keep-alive",
}


def enmascarar_tarjeta(numero) -> str:
    """Devuelve la tarjeta con solo los últimos 4 dígitos visibles (formato del diseño)."""
    digitos = "".join(c for c in str(numero or "") if c.isalnum())
    return f"**** **** **** {digitos[-4:]}" if digitos else "**** **** **** ????"


def depurar_para_interfaz(dato):
    """Quita recursivamente los campos prohibidos antes de serializar hacia el navegador.

    Si un diccionario trae `id_cuenta` pero no `tarjeta_enmascarada`, se agrega la
    versión enmascarada en lugar de perder el dato: la interfaz necesita mostrar la
    tarjeta, solo que nunca completa.
    """
    if isinstance(dato, dict):
        limpio = {}
        for clave, valor in dato.items():
            if clave in CAMPOS_PROHIBIDOS:
                continue
            limpio[clave] = depurar_para_interfaz(valor)
        if "id_cuenta" in dato and "tarjeta_enmascarada" not in limpio:
            limpio["tarjeta_enmascarada"] = enmascarar_tarjeta(dato["id_cuenta"])
        return limpio
    if isinstance(dato, (list, tuple)):
        return [depurar_para_interfaz(v) for v in dato]
    return dato


def a_json(dato) -> str:
    """JSON en una sola línea (requisito de `data:`), con tildes legibles.

    `default=str` cubre fechas y decimales que pudieran escaparse del repositorio:
    preferimos un texto a una excepción a mitad de un stream.
    """
    return json.dumps(dato, ensure_ascii=False, default=str, separators=(",", ":"))


def formatear_evento(tipo: str, datos: dict, id_evento: int) -> str:
    """Un evento SSE completo. `id:` incremental permite verlos numerados en DevTools."""
    return f"id: {id_evento}\nevent: {tipo}\ndata: {a_json(depurar_para_interfaz(datos))}\n\n"


def formatear_comentario(texto: str) -> str:
    """Las líneas que empiezan con `:` son comentarios: el navegador las ignora, el proxy no."""
    return f": {texto}\n\n"


def normalizar_evento(evento) -> tuple[str | None, dict]:
    """Acepta los dos formatos razonables del agente: `{"tipo", "datos": {...}}` o plano.

    `diseno/agente.md` define los tipos y sus datos, pero no si los datos van anidados.
    Aceptar ambos evita que la API dependa de un detalle que el otro módulo puede
    cambiar sin avisar.
    """
    if not isinstance(evento, dict) or not evento.get("tipo"):
        return None, {}
    tipo = str(evento["tipo"])
    if isinstance(evento.get("datos"), dict):
        return tipo, dict(evento["datos"])
    return tipo, {clave: valor for clave, valor in evento.items() if clave != "tipo"}


def transmitir(producir: Callable[[], Iterator[dict]], texto_inicial: str) -> Iterator[str]:
    """Convierte el generador del agente en texto SSE, con pings y un `fin` garantizado.

    Orden garantizado al navegador:
    1. Un `estado` propio de la API, escrito antes de tocar al agente o al modelo: así
       el primer byte sale de inmediato y el TTFT de la interfaz se mide de verdad
       desde la petición hasta el primer `token`.
    2. Los eventos del agente, en el orden en que ocurren, cada uno apenas ocurre.
    3. Un `fin`. Si el agente termina sin emitirlo o lanza una excepción, la API emite
       un `error` en español (con referencia para buscar en el log) y un `fin` propio,
       para que el navegador cierre el EventSource y no reconecte en bucle.
    """
    cola: queue.Queue = queue.Queue()

    def trabajar():
        try:
            for evento in producir():
                cola.put(("evento", evento))
        except Exception:  # noqa: BLE001 — cualquier fallo del agente debe llegar como evento
            referencia = uuid.uuid4().hex[:12]
            registro.exception("Fallo dentro del stream del agente (referencia %s)", referencia)
            cola.put(("excepcion", referencia))
        finally:
            cola.put(("cerrar", None))

    contador = itertools.count(1)
    yield formatear_evento("estado", {"texto": texto_inicial, "origen": "api"}, next(contador))

    hilo = threading.Thread(target=trabajar, name="agente-sse", daemon=True)
    hilo.start()

    termino_con_fin = False
    while True:
        try:
            clase, carga = cola.get(timeout=INTERVALO_PING_S)
        except queue.Empty:
            yield formatear_comentario("ping")
            continue

        if clase == "evento":
            tipo, datos = normalizar_evento(carga)
            if tipo is None:
                continue
            yield formatear_evento(tipo, datos, next(contador))
            if tipo == "fin":
                # Se corta aquí aunque el hilo siga guardando la tarea: el analista no
                # tiene por qué esperar la escritura de métricas para ver el resultado.
                termino_con_fin = True
                break
        elif clase == "excepcion":
            yield formatear_evento(
                "error",
                {
                    "mensaje": "La generación se interrumpió por un error interno del sistema.",
                    "accion": "reintentar",
                    "referencia": carga,
                },
                next(contador),
            )
        else:  # "cerrar": el agente terminó (con o sin `fin`)
            break

    if not termino_con_fin:
        yield formatear_evento(
            "fin",
            {"motivo_fin": "error", "incompleto": True},
            next(contador),
        )


def respuesta_sse(flujo: Iterator[str]) -> StreamingResponse:
    """Envuelve el flujo en la respuesta HTTP con el tipo y las cabeceras de SSE."""
    return StreamingResponse(flujo, media_type="text/event-stream", headers=CABECERAS_SSE)
