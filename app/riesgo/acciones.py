"""Acciones sobre la tarjeta con su aviso: bloquear, pedir verificación, desbloquear (SPEC, RF3-RF6).

Une las guardas de la base (`app/db/repositorio_acciones.py`) con el aviso al titular
(`avisos.py`). Tres actores pueden pedir una acción, y cada uno entra por su propia puerta:

- **el agente**, solo a través de `AccionesDelAgente`, que fija el actor en "agente" y el caso
  en el que se creó: el modelo no puede decir que es otro actor ni actuar sobre otro caso;
- **la regla** (triaje caído o red de seguridad), con el motivo de plantilla;
- **un analista o supervisor**, desde la API y con su usuario de sesión (solo desbloquea,
  confirma o descarta).

Ningún camino de este módulo desbloquea en nombre del agente.
"""

import logging

from app.db import repositorio, repositorio_acciones
from app.riesgo import avisos

registro = logging.getLogger("app.riesgo.acciones")

MOTIVO_REGLA = {
    "red_de_seguridad": "Red de seguridad: el caso llegó a banda crítica y nadie lo había bloqueado a tiempo.",
    "triaje_sin_bloqueo": "Regla: caso crítico que el triaje del agente no bloqueó.",
}


def _avisar(id_caso, tipo, motivo_agente, bloqueo_id=None, del_agente=True):
    caso = repositorio.obtener_caso(id_caso)
    aviso = avisos.armar(tipo, caso, motivo_agente if del_agente else None)
    if not del_agente:
        aviso["errores_validacion"] = []          # la regla no redacta: usar la plantilla no es un error
    notificacion_id = repositorio_acciones.crear_notificacion({**aviso, "id_caso": id_caso, "bloqueo_id": bloqueo_id})
    estado, detalle = avisos.enviar(aviso)
    repositorio_acciones.marcar_envio(notificacion_id, estado, detalle)
    return {"notificacion_id": notificacion_id, "estado_envio": estado, "autor_motivo": aviso["autor_motivo"],
            "errores_validacion": aviso["errores_validacion"]}


def bloquear(id_caso, tipo, actor, motivo_agente=None, tarea_id=None, usuario=None, causa_regla="red_de_seguridad"):
    """Bloquea si las guardas lo permiten y, si se bloqueó, avisa al titular."""
    motivo_registro = (motivo_agente or "").strip()[:600] if actor == "agente" else MOTIVO_REGLA.get(causa_regla, causa_regla)
    resultado = repositorio_acciones.bloquear(id_caso, tipo, actor, motivo_registro or "Sin motivo redactado.",
                                              tarea_id=tarea_id, usuario=usuario)
    if resultado["resultado"] == "bloqueada":
        resultado["aviso"] = _avisar(id_caso, "bloqueo", motivo_agente, resultado["bloqueo_id"],
                                     del_agente=actor == "agente")
        if actor == "regla":
            repositorio_acciones.nueva_alerta(causa_regla, id_caso,
                                              {"segundos_hasta_bloqueo": resultado.get("segundos_hasta_bloqueo")})
        registro.info("Caso %s: %s bloqueó %s en %.1f s", id_caso, actor, tipo, resultado.get("segundos_hasta_bloqueo") or 0)
    return resultado


def solicitar_verificacion(id_caso, actor, motivo_agente=None):
    """Pide al titular que confirme la compra; no bloquea nada. Si ya está bloqueada, no hace nada."""
    caso = repositorio.obtener_caso(id_caso)
    if caso is None:
        return {"resultado": "no_permitido", "detalle": "El caso no existe."}
    if caso["estado"] in ("bloqueado", "descartado", "desbloqueado"):
        return {"resultado": "sin_cambio", "detalle": f"El caso está {caso['estado']}: no se pide verificación."}
    repositorio_acciones.marcar_en_verificacion(id_caso)
    return {"resultado": "verificacion_solicitada",
            "aviso": _avisar(id_caso, "verificacion", motivo_agente, del_agente=actor == "agente")}


class AccionesDelAgente:
    """Lo único que el agente puede hacer sobre una tarjeta, atado al caso de su tarea."""

    def __init__(self, id_caso: str, tarea_id: str):
        self._id_caso = id_caso
        self._tarea_id = tarea_id

    def bloquear(self, tipo: str, motivo_para_titular: str) -> dict:
        return bloquear(self._id_caso, tipo, "agente", motivo_para_titular, tarea_id=self._tarea_id)

    def solicitar_verificacion(self, motivo_para_titular: str) -> dict:
        return solicitar_verificacion(self._id_caso, "agente", motivo_para_titular)

    def dejar_a_analista(self, razon: str) -> dict:
        # No cambia nada en la base: el caso sigue en la cola humana. La razón queda en la traza.
        return {"resultado": "en_cola_humana", "razon": razon[:300]}
