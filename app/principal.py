"""Punto de entrada de la vista del analista: crea la app FastAPI y la deja lista.

Responsabilidades, en orden de arranque:

1. Preparar la base (`app.db.migrar.preparar_base()`: esquema + semilla). Si la base no
   está, la app arranca IGUAL y `/api/salud` lo informa: una pantalla que dice "la base
   no responde" es más útil en una sustentación que un contenedor que se reinicia.
2. Montar las rutas de la API (`app/api/`) y los archivos del frontend (`app/web/`).
3. Instalar los manejadores de error que garantizan que el analista nunca vea una
   traza de Python: todo error sale como JSON en español, y la traza va al log con una
   referencia corta que permite encontrarla.

Se corre con `uvicorn app.principal:app --host 0.0.0.0 --port 8000`, o con
`python -m app.principal` en desarrollo.
"""

import importlib
import logging
import os
import uuid
from contextlib import asynccontextmanager
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import config
from app.api import rutas_agente, rutas_casos, rutas_sistema

CARPETA_WEB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")

registro = logging.getLogger("app.principal")

# Mensajes por código para los errores que Starlette genera solo (ruta inexistente,
# método no permitido, cuerpo ilegible): sin esto saldrían en inglés ("Not Found").
MENSAJES_HTTP = {
    400: "La solicitud no se pudo leer (revisa que el cuerpo sea JSON válido en UTF-8)",
    404: "Recurso no encontrado",
    405: "Método no permitido para esta ruta",
}

MENSAJE_BASE_CAIDA = "La base de datos no responde; intente de nuevo en unos segundos."


def es_error_de_conexion(exc: BaseException) -> bool:
    """¿La excepción es "no hay base"? psycopg OperationalError o PoolTimeout del pool.

    Se busca también en la causa (__cause__/__context__) porque a veces llega envuelta.
    Se compara por clase importada en el momento, para que la app arranque aunque el
    driver no esté instalado (las pruebas sin base corren sin psycopg).
    """
    clases = []
    try:
        from psycopg import OperationalError
        clases.append(OperationalError)
    except ImportError:
        pass
    try:
        from psycopg_pool import PoolTimeout
        clases.append(PoolTimeout)
    except ImportError:
        pass
    vistos = 0
    while exc is not None and vistos < 5:
        if clases and isinstance(exc, tuple(clases)):
            return True
        exc = exc.__cause__ or exc.__context__
        vistos += 1
    return False


def _configurar_registro():
    """Log legible en la consola del contenedor; no se pisa si uvicorn ya lo configuró."""
    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def preparar_base_tolerante() -> dict:
    """Llama a `preparar_base()` y nunca deja que su fallo impida arrancar la app.

    Se captura también `SystemExit` porque el diseño de persistencia permite que la
    migración termine el proceso tras agotar sus reintentos; aquí preferimos seguir
    vivos y avisar en pantalla.
    """
    try:
        importlib.import_module("app.db.migrar").preparar_base()
        return {"preparada": True, "mensaje": None}
    except (Exception, SystemExit):  # noqa: BLE001 — el arranque no se cae por la base
        registro.exception("No se pudo preparar la base al arrancar; la app sigue en modo degradado")
        return {
            "preparada": False,
            "mensaje": "La base de datos no estaba disponible al arrancar. Revisa que el servicio de Postgres esté activo.",
        }


class EstaticosSinCacheVieja(StaticFiles):
    """Archivos del frontend que el navegador siempre revalida (ETag → 304 si no cambiaron).

    Sin esto, el navegador puede reutilizar un módulo ES viejo junto a uno nuevo tras un
    cambio (pasó en la revisión: `bandeja.js` nuevo importando de un `dom.js` en caché) y la
    app queda rota hasta forzar la recarga. Revalidar cuesta una petición corta por archivo.
    """

    def file_response(self, *args, **kwargs):
        respuesta = super().file_response(*args, **kwargs)
        respuesta.headers["Cache-Control"] = "no-cache"
        return respuesta


def _respuesta_error(estado: int, mensaje: str, referencia: str | None = None) -> JSONResponse:
    cuerpo = {"error": mensaje}
    if referencia:
        cuerpo["referencia"] = referencia
    return JSONResponse(cuerpo, status_code=estado)


def _instalar_manejadores(app: FastAPI):
    @app.exception_handler(StarletteHTTPException)
    async def error_http(request: Request, exc: StarletteHTTPException):
        # Nuestras rutas ponen el mensaje en español en `detail`. Las respuestas que
        # genera Starlette solo traen la frase estándar en inglés ("Not Found"): esas se
        # reemplazan por la versión en español.
        try:
            frase_estandar = HTTPStatus(exc.status_code).phrase
        except ValueError:
            frase_estandar = None
        propio = isinstance(exc.detail, str) and exc.detail and exc.detail != frase_estandar
        # El 400 de un cuerpo ilegible trae un texto propio de Starlette, en inglés.
        if propio and exc.status_code == 400 and "parsing the body" in exc.detail:
            propio = False
        mensaje = exc.detail if propio else MENSAJES_HTTP.get(exc.status_code, "Solicitud no válida")
        return _respuesta_error(exc.status_code, mensaje)

    @app.exception_handler(RequestValidationError)
    async def error_validacion(request: Request, exc: RequestValidationError):
        # Pydantic describe el problema en inglés; decimos en español qué campo falló.
        campos = sorted({str(e.get("loc", ["", "?"])[-1]) for e in exc.errors()})
        return _respuesta_error(422, f"La solicitud no tiene el formato esperado (revisa: {', '.join(campos)}).")

    @app.exception_handler(Exception)
    async def error_inesperado(request: Request, exc: Exception):
        # Única salida para lo imprevisto: mensaje fijo en español + referencia. La traza
        # completa queda en el log del servidor, nunca en la respuesta.
        referencia = uuid.uuid4().hex[:12]
        if es_error_de_conexion(exc):
            # La base caída no es un "error inesperado": se dice qué pasa y que es pasajero.
            # Una línea en el log basta (sin traza): la causa ya está clara.
            registro.warning("Base de datos no disponible en %s %s: %s", request.method, request.url.path,
                             type(exc).__name__)
            return _respuesta_error(503, MENSAJE_BASE_CAIDA)
        registro.error(
            "Error no controlado en %s %s (referencia %s)", request.method, request.url.path, referencia,
            exc_info=exc,
        )
        if isinstance(exc, ImportError):
            mensaje = "Un componente del sistema no está disponible en este momento."
            return _respuesta_error(503, mensaje, referencia)
        mensaje = "Ocurrió un error inesperado. Intenta de nuevo; si persiste, comparte la referencia con el equipo."
        return _respuesta_error(500, mensaje, referencia)


def crear_app() -> FastAPI:
    """Fábrica de la app: una instancia nueva por llamada, útil para las pruebas."""
    _configurar_registro()

    @asynccontextmanager
    async def ciclo_de_vida(app: FastAPI):
        app.state.estado_base = preparar_base_tolerante()
        yield

    app = FastAPI(
        title="Vista del analista · Detección de fraude",
        description="Bandeja de casos, explicación del agente por SSE y decisiones con confirmación humana.",
        version="1.0.0",
        lifespan=ciclo_de_vida,
    )
    # Valores antes del arranque: la salud funciona incluso si la app se usa sin lifespan.
    app.state.estado_base = {"preparada": False, "mensaje": None}
    app.state.demo = rutas_sistema.EstadoDemo(config.FALLA_FORZADA)

    _instalar_manejadores(app)
    app.include_router(rutas_casos.router)
    app.include_router(rutas_agente.router)
    app.include_router(rutas_sistema.router)

    app.mount("/static", EstaticosSinCacheVieja(directory=CARPETA_WEB), name="static")

    @app.get("/", include_in_schema=False)
    def inicio():
        # Sin caché para el HTML: tras cambiar el frontend, un F5 basta para verlo.
        return FileResponse(os.path.join(CARPETA_WEB, "index.html"), headers={"Cache-Control": "no-cache"})

    return app


app = crear_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.principal:app", host="0.0.0.0", port=config.PUERTO)
