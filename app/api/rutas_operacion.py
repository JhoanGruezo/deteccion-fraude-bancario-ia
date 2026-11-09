"""Rutas de la operación del Momento 3: bloqueos, desbloqueo, buzón del titular y supervisión.

- **Desbloquear** (SPEC, RF6) es la acción humana que reabre la tarjeta al riesgo: exige sesión,
  token CSRF (lo revisa el middleware de sesión) y un motivo escrito de al menos 10 caracteres.
  Queda firmada con el usuario de la sesión, no con un nombre que escriba el navegador.
- **Responder un aviso** simula al titular en el buzón de la app ("fui yo" / "no fui yo"). No
  desbloquea nada: "fui yo" sube el bloqueo al primer lugar de la cola de desbloqueo.
- **Ajustes** (autonomía del agente, tope de bloqueos por hora) y **alertas**: solo supervisor.
"""

import importlib

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app import config
from app.api.sesion import firma_de, usuario_de
from app.api.sse import depurar_para_interfaz

router = APIRouter(prefix="/api", tags=["operacion"])

LARGO_MINIMO_MOTIVO = 10
AJUSTES_PERMITIDOS = {
    "autonomia_agente": lambda v: isinstance(v, bool),
    "tope_bloqueos_autonomos_por_hora": lambda v: isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 500,
}


def acciones():
    return importlib.import_module("app.db.repositorio_acciones")


def repositorio():
    return importlib.import_module("app.db.repositorio")


class CuerpoDesbloqueo(BaseModel):
    motivo: str = Field("", max_length=500)


class CuerpoRespuesta(BaseModel):
    respuesta: str


class CuerpoAjuste(BaseModel):
    clave: str
    valor: bool | int


@router.get("/bloqueos")
def bloqueos(estado: str | None = Query(None, pattern="^(activo|levantado)$"), limite: int = Query(200, ge=1, le=1000)):
    return depurar_para_interfaz({"bloqueos": acciones().listar_bloqueos(estado=estado, limite=limite)})


@router.post("/bloqueos/{bloqueo_id}/desbloquear")
def desbloquear(bloqueo_id: int, cuerpo: CuerpoDesbloqueo, request: Request):
    motivo = cuerpo.motivo.strip()
    if len(motivo) < LARGO_MINIMO_MOTIVO:
        raise HTTPException(422, f"Escribe por qué desbloqueas (al menos {LARGO_MINIMO_MOTIVO} caracteres): "
                                 "queda en la auditoría del caso.")
    firma = firma_de(request) or "pruebas"
    levantado = acciones().desbloquear(bloqueo_id, firma, motivo)
    if levantado is None:
        raise HTTPException(409, "Ese bloqueo ya no está activo (otro analista lo levantó o no existe).")
    return depurar_para_interfaz({"desbloqueo": levantado, "firmado_por": firma})


@router.get("/avisos")
def avisos(limite: int = Query(100, ge=1, le=500)):
    return depurar_para_interfaz({"avisos": acciones().listar_avisos(limite=limite)})


@router.post("/avisos/{aviso_id}/responder")
def responder_aviso(aviso_id: int, cuerpo: CuerpoRespuesta):
    if cuerpo.respuesta not in ("fui_yo", "no_fui_yo"):
        raise HTTPException(422, "La respuesta debe ser «fui_yo» o «no_fui_yo».")
    id_caso = acciones().responder_notificacion(aviso_id, cuerpo.respuesta)
    if id_caso is None:
        raise HTTPException(409, "Ese aviso ya tiene respuesta o no existe.")
    return {"id_caso": id_caso, "respuesta": cuerpo.respuesta}


@router.get("/supervision")
def supervision():
    ajustes = acciones().ajustes()
    gasto = repositorio().gasto_del_dia()
    return depurar_para_interfaz({
        "ajustes": ajustes,
        "gasto_del_dia_usd": gasto,
        "tope_gasto_diario_usd": config.TOPE_GASTO_DIARIO_USD,
        "segundos_red_de_seguridad": config.SEGUNDOS_RED_DE_SEGURIDAD,
        "cifras": acciones().resumen_supervision(),
        "alertas": acciones().alertas_pendientes(),
    })


@router.post("/ajustes")
def cambiar_ajuste(cuerpo: CuerpoAjuste, request: Request):
    validar = AJUSTES_PERMITIDOS.get(cuerpo.clave)
    if validar is None:
        raise HTTPException(422, f"Ajuste desconocido. Opciones: {', '.join(AJUSTES_PERMITIDOS)}.")
    if not validar(cuerpo.valor):
        raise HTTPException(422, "Valor no válido para ese ajuste (autonomía: true/false; tope: entero de 0 a 500).")
    usuario = usuario_de(request)
    acciones().cambiar_ajuste(cuerpo.clave, cuerpo.valor, usuario["usuario"] if usuario else "pruebas")
    return {"clave": cuerpo.clave, "valor": cuerpo.valor}


@router.post("/alertas/{alerta_id}/atender")
def atender(alerta_id: int, request: Request):
    usuario = usuario_de(request)
    if not acciones().atender_alerta(alerta_id, usuario["usuario"] if usuario else "pruebas"):
        raise HTTPException(409, "La alerta ya estaba atendida o no existe.")
    return {"ok": True}
