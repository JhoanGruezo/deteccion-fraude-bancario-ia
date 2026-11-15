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
    "autonomia_apagada": "Regla: caso crítico con la autonomía del agente apagada.",
    "analista_confirmo": "Bloqueo confirmado por un analista desde el detalle del caso.",
    "titular_no_reconoce": "El titular respondió en el aviso que no reconoce la compra.",
}
LARGO_MINIMO_MOTIVO_DESCARTE = 10


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


def bloquear(id_caso, tipo, actor, motivo_agente=None, tarea_id=None, usuario=None, causa_regla="red_de_seguridad",
             reabrir=False):
    """Bloquea si las guardas lo permiten y, si se bloqueó, avisa al titular."""
    motivo_registro = (motivo_agente or "").strip()[:600] if actor == "agente" else MOTIVO_REGLA.get(causa_regla, causa_regla)
    resultado = repositorio_acciones.bloquear(id_caso, tipo, actor, motivo_registro or "Sin motivo redactado.",
                                              tarea_id=tarea_id, usuario=usuario, reabrir=reabrir)
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


def tipo_de_bloqueo(caso) -> str:
    """Viaje imposible → acceso a la cuenta (posible toma de control); lo demás → la tarjeta."""
    return "acceso_cuenta" if "viaje_imposible" in (caso.get("tipos_fraude") or []) else "tarjeta"


def validar_decision(caso, accion, comentario):
    """Reglas de una decisión humana sobre un caso en vivo (auditoría 2026-11-14, A3).

    Devuelve un mensaje en español si la decisión no se puede registrar, o None si sí.
    Los casos de la semilla del Momento 2 no cambian: no tienen tarjeta que bloquear.
    """
    if not caso or caso.get("origen") != "en_vivo" or accion != "descartar":
        return None
    if repositorio_acciones.bloqueo_activo_del_caso(caso["id_caso"]):
        return ("La tarjeta de este caso está bloqueada: para devolvérsela al cliente usa «Desbloquear» "
                "en la vista Bloqueos, con su motivo. Descartar no levanta el bloqueo.")
    if len((comentario or "").strip()) < LARGO_MINIMO_MOTIVO_DESCARTE:
        return (f"Para descartar un caso en vivo escribe por qué (al menos {LARGO_MINIMO_MOTIVO_DESCARTE} "
                "caracteres): descartar apaga la red de seguridad de ese caso y queda en la auditoría.")
    return None


def aplicar_decision(id_caso, accion, usuario):
    """Efecto sobre la tarjeta de una decisión humana (auditoría 2026-11-14, C2).

    "Confirmar bloqueo" en un caso en vivo bloquea de verdad, firmado por el analista: antes
    solo cambiaba el estado del caso y la tarjeta seguía aceptando compras.
    """
    if accion != "confirmar_bloqueo":
        return None
    caso = repositorio.obtener_caso(id_caso)
    if not caso or caso.get("origen") != "en_vivo":
        return None
    return bloquear(id_caso, tipo_de_bloqueo(caso), "analista", usuario=usuario, causa_regla="analista_confirmo")


def respuesta_del_titular(id_caso, respuesta):
    """Efecto de la respuesta del titular (SPEC, RF5; auditoría 2026-11-14, A1).

    "No fui yo" bloquea la tarjeta si todavía no lo estaba, aunque el caso se hubiera
    descartado o desbloqueado: el titular sabe más que cualquier score. Si ya estaba
    bloqueada, la respuesta la confirma (queda en el aviso). "Fui yo" no desbloquea nada:
    sube el bloqueo al primer lugar de la cola de desbloqueo.
    """
    if respuesta != "no_fui_yo":
        return None
    caso = repositorio.obtener_caso(id_caso)
    if not caso or caso.get("origen") != "en_vivo":
        return None
    return bloquear(id_caso, tipo_de_bloqueo(caso), "regla", causa_regla="titular_no_reconoce", reabrir=True)


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
