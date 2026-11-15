"""Límite de peticiones por minuto (SPEC, RS5; clase 12, "consumo desmedido").

Existe porque los límites del agente (iteraciones, tokens, timeout) cuidan UNA tarea,
pero no impiden que alguien abra cien tareas seguidas: cada explicación regenerada o
cada pregunta es una llamada pagada al proveedor. El profesor lo llamó "dejar el
taxímetro abierto". Este límite es el freno de mano antes de llegar al modelo.

Tres categorías, cada una con su ventana deslizante de 60 s por cliente:

| Categoría | Qué cubre | Por defecto |
|---|---|---|
| `agente` | Rutas que llaman al LLM (explicación en vivo, preguntas) | 10 por minuto |
| `escritura` | Cualquier POST, PUT, PATCH o DELETE de la API | 30 por minuto |
| `lectura` | GET de la API | 240 por minuto |

Los archivos estáticos no se limitan. Al pasarse, la respuesta es 429 con un mensaje en
español y la cabecera `Retry-After`, que la interfaz usa para decir cuánto esperar.

Cada petición cuenta dos veces (auditoría 2026-11-14): contra el cupo de su **sesión** (la
cookie, guardada solo como hash) y contra el cupo de su **IP**, que es `FACTOR_IP` veces más
grande. Detrás del mapeo de puertos de Docker todas las peticiones locales llegan con la misma
IP: si el límite fuera solo por IP, un usuario que abusa frenaría a todos los demás. Con el
cupo por sesión, el que abusa agota el suyo; y quien rote cookies inventadas para esquivarlo
choca con el de la IP. Todo vive en memoria del proceso: la app corre en un solo proceso, y un
límite que se reinicia con la app es aceptable para este alcance.
"""

import hashlib
import math
import re
import threading
import time
from collections import deque

from fastapi import Request
from fastapi.responses import JSONResponse

from app import config

VENTANA_S = 60.0
FACTOR_IP = 5          # el cupo por IP es 5 veces el de una sesión
COOKIE_SESION = "sesion"
RUTAS_AGENTE = re.compile(r"^/api/casos/[^/]+/(explicacion|preguntas)/stream$")
METODOS_LECTURA = {"GET", "HEAD", "OPTIONS"}
MENSAJES = {
    "agente": "Demasiadas consultas al asistente de IA en poco tiempo.",
    "escritura": "Demasiadas acciones seguidas.",
    "lectura": "Demasiadas solicitudes seguidas.",
}


def categoria_de(metodo: str, ruta: str) -> str | None:
    """A qué límite pertenece una petición; None si no se limita (archivos del frontend)."""
    if not ruta.startswith("/api/"):
        return None
    if RUTAS_AGENTE.match(ruta):
        return "agente"
    return "lectura" if metodo.upper() in METODOS_LECTURA else "escritura"


def limites_desde_config() -> dict[str, int]:
    return {
        "agente": config.LIMITE_AGENTE_POR_MINUTO,
        "escritura": config.LIMITE_ESCRITURA_POR_MINUTO,
        "lectura": config.LIMITE_LECTURA_POR_MINUTO,
    }


class LimitadorDePeticiones:
    """Ventana deslizante por (cliente, categoría). Seguro entre hilos."""

    def __init__(self, limites: dict[str, int], reloj=time.monotonic):
        self.limites = limites
        self.reloj = reloj
        self._marcas: dict[tuple[str, str], deque] = {}
        self._candado = threading.Lock()
        self._ultima_limpieza = reloj()

    def registrar(self, cliente: str, categoria: str, factor: int = 1) -> float | None:
        """Anota la petición si cabe y devuelve None; si no cabe, devuelve los segundos de espera."""
        limite = self.limites.get(categoria, 0) * factor
        if limite <= 0:   # 0 = sin límite para esa categoría
            return None
        ahora = self.reloj()
        with self._candado:
            marcas = self._marcas.setdefault((cliente, categoria), deque())
            while marcas and ahora - marcas[0] >= VENTANA_S:
                marcas.popleft()
            if len(marcas) >= limite:
                return max(0.0, VENTANA_S - (ahora - marcas[0]))
            marcas.append(ahora)
            self._limpiar(ahora)
            return None

    def _limpiar(self, ahora: float):
        # Cada tanto se olvidan los clientes inactivos, para que la memoria no crezca.
        if ahora - self._ultima_limpieza < VENTANA_S:
            return
        self._ultima_limpieza = ahora
        for clave in [c for c, m in self._marcas.items() if not m or ahora - m[-1] >= VENTANA_S]:
            del self._marcas[clave]


def instalar(app, limitador: LimitadorDePeticiones | None = None):
    """Agrega el middleware a la app. El limitador queda en app.state para las pruebas."""
    app.state.limitador = limitador or LimitadorDePeticiones(limites_desde_config())

    @app.middleware("http")
    async def limitar_peticiones(request: Request, siguiente):
        categoria = categoria_de(request.method, request.url.path)
        if categoria is not None:
            limitador = request.app.state.limitador
            ip = request.client.host if request.client else "desconocido"
            cookie = request.cookies.get(COOKIE_SESION)
            if cookie:
                sesion = "sesion:" + hashlib.sha256(cookie.encode("utf-8", "replace")).hexdigest()[:24]
                espera = limitador.registrar(sesion, categoria)
                if espera is None:
                    espera = limitador.registrar("ip:" + ip, categoria, factor=FACTOR_IP)
            else:
                espera = limitador.registrar("ip:" + ip, categoria)
            if espera is not None:
                segundos = max(1, math.ceil(espera))
                return JSONResponse(
                    {"error": f"{MENSAJES[categoria]} Intenta de nuevo en {segundos} s.",
                     "categoria": categoria, "reintentar_en_s": segundos},
                    status_code=429, headers={"Retry-After": str(segundos)},
                )
        return await siguiente(request)


def instalar_saneamiento(app):
    """Rechaza antes de llegar a las rutas dos entradas que hacían daño (auditoría del 2026-10-31).

    - Un byte NUL (`%00`) en la ruta o en la consulta producía un 500 desde Postgres (B1): ahora
      es un 422 en español.
    - Un cuerpo enorme se leía y se parseaba entero (B6): ahora se corta por `Content-Length`.
    """
    from urllib.parse import unquote

    @app.middleware("http")
    async def sanear(request: Request, siguiente):
        crudo = unquote(request.url.path) + unquote(request.url.query or "")
        if chr(0) in crudo:
            return JSONResponse({"error": "La solicitud contiene caracteres no válidos."}, status_code=422)
        largo = request.headers.get("content-length")
        if largo and largo.isdigit() and int(largo) > config.MAXIMO_CUERPO_BYTES:
            return JSONResponse({"error": "La solicitud es demasiado grande."}, status_code=413)
        return await siguiente(request)
