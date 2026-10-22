"""Rutas del agente: explicación y preguntas por SSE real, y resolución de propuestas.

Aquí no hay lógica del agente: las rutas validan la entrada, comprueban que el caso
exista ANTES de abrir el stream (después ya no se puede responder un 404 limpio) y
entregan el generador de `app.agente.servicio` a `sse.transmitir`, que lo escribe al
socket evento por evento.

La confirmación de una propuesta también vive aquí porque es la otra mitad del cuarto
límite del agente: el agente solo propone; esta ruta es la única puerta por la que una
propuesta se vuelve decisión, y exige el nombre del analista.
"""

import importlib

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from app import config
from app.api.rutas_casos import caso_o_404, repositorio, validar_analista
from app.api.rutas_sistema import falla_vigente
from app.api.sse import depurar_para_interfaz, respuesta_sse, transmitir

router = APIRouter(prefix="/api", tags=["agente"])

LARGO_MAXIMO_PREGUNTA = 500


def servicio():
    """Import diferido del agente: si su módulo falla al importar, la bandeja sigue viva."""
    return importlib.import_module("app.agente.servicio")


def _falla_para_tarea(request: Request, falla: str | None) -> str | None:
    """Decide qué falla forzada recibe la tarea.

    El parámetro `?falla=` solo cuenta si el panel de demo está habilitado; si no, se
    ignora y manda la configuración del proceso. Un valor desconocido se rechaza antes
    de abrir el stream, porque después el navegador no podría leer el 422.
    """
    pedido = (falla or "").strip()
    if pedido and config.PERMITIR_FALLAS_DESDE_UI:
        if pedido not in config.FALLAS_VALIDAS:
            raise HTTPException(422, f"Falla desconocida «{pedido}».")
        return pedido
    return falla_vigente(request)


@router.get("/casos/{id_caso}/explicacion/stream")
def explicacion_en_vivo(
    id_caso: str,
    request: Request,
    regenerar: bool = False,
    falla: str | None = Query(None, max_length=20),
):
    """SSE: explicación del caso (caché si existe; si no, el agente la genera en vivo)."""
    caso_o_404(id_caso)
    falla_forzada = _falla_para_tarea(request, falla)
    texto_inicial = "Regenerando: consultando el caso…" if regenerar else "Consultando el caso…"
    return respuesta_sse(
        transmitir(
            lambda: servicio().explicar_caso(id_caso, regenerar=regenerar, falla_forzada=falla_forzada),
            texto_inicial,
        )
    )


@router.get("/casos/{id_caso}/preguntas/stream")
def pregunta_en_vivo(
    id_caso: str,
    request: Request,
    q: str = Query("", max_length=2000),
    falla: str | None = Query(None, max_length=20),
):
    """SSE: respuesta del agente a una pregunta del analista sobre el caso abierto."""
    pregunta = q.strip()
    if not pregunta:
        raise HTTPException(422, "Escribe una pregunta sobre el caso.")
    if len(pregunta) > LARGO_MAXIMO_PREGUNTA:
        raise HTTPException(422, f"La pregunta no puede pasar de {LARGO_MAXIMO_PREGUNTA} caracteres.")
    caso_o_404(id_caso)
    falla_forzada = _falla_para_tarea(request, falla)
    return respuesta_sse(
        transmitir(
            lambda: servicio().responder_pregunta(id_caso, pregunta, falla_forzada=falla_forzada),
            "Pregunta recibida: consultando el caso…",
        )
    )


class CuerpoResolucion(BaseModel):
    """Confirmar o rechazar una propuesta. Campos opcionales a propósito: la validación
    se hace a mano para responder en español y no con el 422 genérico de Pydantic."""

    analista: str | None = None
    comentario: str | None = None


MENSAJE_YA_RESUELTA = "Esta propuesta ya fue resuelta. Recarga el caso para ver la decisión vigente."


def _resolver(propuesta_id: int, confirmar: bool, cuerpo: CuerpoResolucion):
    """Resuelve una propuesta con la confirmación explícita del analista.

    El repositorio avisa con excepciones propias: `PropuestaNoEncontrada` (es un
    `LookupError`) → 404 y `PropuestaYaResuelta` → 409. Se aceptan también `None` y
    `ValueError` por si esa capa cambia, para no convertir un conflicto en un 500.
    """
    analista, comentario = validar_analista(cuerpo.analista, cuerpo.comentario)
    repo = repositorio()
    ya_resuelta = tuple(c for c in (getattr(repo, "PropuestaYaResuelta", None), ValueError) if isinstance(c, type))
    try:
        resultado = repo.resolver_propuesta(propuesta_id, confirmar, analista, comentario)
    except LookupError:
        raise HTTPException(404, "Propuesta no encontrada")
    except ya_resuelta:
        raise HTTPException(409, MENSAJE_YA_RESUELTA)
    if not resultado:
        raise HTTPException(404, "Propuesta no encontrada")
    if isinstance(resultado, dict) and resultado.get("error"):
        raise HTTPException(409, MENSAJE_YA_RESUELTA)
    return depurar_para_interfaz({"resultado": resultado})


@router.post("/propuestas/{propuesta_id}/confirmar")
def confirmar_propuesta(propuesta_id: int, cuerpo: CuerpoResolucion):
    return _resolver(propuesta_id, True, cuerpo)


@router.post("/propuestas/{propuesta_id}/rechazar")
def rechazar_propuesta(propuesta_id: int, cuerpo: CuerpoResolucion):
    return _resolver(propuesta_id, False, cuerpo)
