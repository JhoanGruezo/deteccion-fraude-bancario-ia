"""Rutas del sistema: salud, configuración visible, métricas, trazas y panel de demo.

Son las rutas que hacen visible "por dentro" la app durante la sustentación: qué
proveedor está activo, qué límites tiene el agente, cuánto tardó y costó cada tarea y,
con el panel de demo, qué falla se está forzando. Nada de esto expone llaves de API: de
cada proveedor solo se dice si tiene llave o no.
"""

import importlib
import logging
import threading
import uuid

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app import config
from app.api.sse import INTERVALO_PING_S, depurar_para_interfaz

router = APIRouter(prefix="/api", tags=["sistema"])
registro = logging.getLogger("app.api.sistema")


def repositorio():
    """Import diferido: ver la explicación en `rutas_casos.repositorio`."""
    return importlib.import_module("app.db.repositorio")


class EstadoDemo:
    """Falla forzada elegida desde el panel de demo, en memoria del proceso.

    Vive en `app.state` (una instancia por app) y no en una variable global para que
    cada prueba arranque limpia. El candado evita una lectura a medias si dos
    peticiones cambian la falla a la vez. Arranca con `FALLA_FORZADA` del entorno, así
    el panel muestra la falla que de verdad está activa.
    """

    def __init__(self, falla_inicial: str | None):
        self._candado = threading.Lock()
        self._falla = falla_inicial or None

    @property
    def falla(self) -> str | None:
        with self._candado:
            return self._falla

    def fijar(self, falla: str | None) -> None:
        with self._candado:
            self._falla = falla or None


def falla_vigente(request: Request) -> str | None:
    """La falla que se le pasa al agente en la próxima tarea."""
    # "" (y no None) significa "ninguna": el servicio interpreta None como "usar la del
    # entorno", y limpiar la falla desde el panel debe apagarla aunque .env la tenga.
    estado = getattr(request.app.state, "demo", None)
    return (estado.falla or "") if estado else (config.FALLA_FORZADA or "")


def _proveedores() -> list[dict]:
    """Proveedores en el orden de la cascada, sin exponer ninguna llave."""
    catalogo = {
        "gemini": {"etiqueta": "Gemini", "modelo": config.GEMINI_MODELO, "con_llave": bool(config.GEMINI_API_KEY)},
        "claude": {"etiqueta": "Claude", "modelo": config.CLAUDE_MODELO, "con_llave": bool(config.ANTHROPIC_API_KEY)},
    }
    lista = []
    for posicion, nombre in enumerate(config.ORDEN_PROVEEDORES):
        if nombre in catalogo:
            lista.append({"nombre": nombre, "principal": posicion == 0, **catalogo[nombre]})
    return lista


@router.get("/salud")
def salud(request: Request):
    """Estado de la base, casos cargados, proveedores con llave y falla activa.

    Responde 200 aunque la base esté caída: es justo cuando más se necesita saber qué
    pasa, y la interfaz usa esta ruta para mostrar el aviso correspondiente.
    """
    arranque = getattr(request.app.state, "estado_base", {"preparada": False, "mensaje": None})
    base = {"disponible": False, "casos_cargados": 0, "mensaje": arranque.get("mensaje")}
    try:
        contadores = repositorio().contar_casos() or {}
        total = contadores.get("total")
        if not isinstance(total, int):
            por_fuente = contadores.get("por_fuente") or contadores.get("fuente") or {}
            total = sum(int(v or 0) for v in por_fuente.values()) if isinstance(por_fuente, dict) else 0
        base.update(disponible=True, casos_cargados=total, mensaje=None)
    except Exception:  # noqa: BLE001 — la salud informa, no propaga
        registro.exception("La consulta de salud a la base falló")
        base["mensaje"] = base["mensaje"] or "No se pudo consultar la base de datos."

    proveedores = _proveedores()
    con_llave = [p for p in proveedores if p["con_llave"]]
    return {
        "estado": "ok" if base["disponible"] and con_llave else "degradado",
        "base": base,
        "proveedores": proveedores,
        "modo_plantilla": not con_llave,
        "falla_forzada": falla_vigente(request),
        "panel_demo": config.PERMITIR_FALLAS_DESDE_UI,
    }


@router.get("/config")
def configuracion(request: Request):
    """Límites y modelos vigentes: la interfaz los muestra para que nada sea "magia"."""
    return {
        "limites": {
            "max_iteraciones": config.MAX_ITERACIONES,
            "presupuesto_tokens": config.PRESUPUESTO_TOKENS,
            "timeout_modelo_s": config.TIMEOUT_MODELO_S,
            "timeout_herramienta_s": config.TIMEOUT_HERRAMIENTA_S,
            "max_tokens_respuesta": config.MAX_TOKENS_RESPUESTA,
            "esperas_reintento_s": list(config.ESPERAS_REINTENTO_S),
        },
        "proveedores": _proveedores(),
        "panel_demo": config.PERMITIR_FALLAS_DESDE_UI,
        "fallas_validas": sorted(f for f in config.FALLAS_VALIDAS if f),
        "falla_forzada": falla_vigente(request),
        "intervalo_ping_s": INTERVALO_PING_S,
    }


@router.get("/metricas")
def metricas():
    """Las cifras en vivo de las tareas del agente (éxito, latencias, costo, caché)."""
    return depurar_para_interfaz(repositorio().resumen_metricas() or {})


@router.get("/tareas/{tarea_id}/trazas")
def trazas_de_tarea(tarea_id: str):
    """Traza completa de una tarea, para revisarla después de que el stream terminó."""
    try:
        uuid.UUID(tarea_id)
    except ValueError:
        raise HTTPException(422, "El identificador de la tarea no es válido.")
    return depurar_para_interfaz({"tarea_id": tarea_id, "trazas": repositorio().listar_trazas(tarea_id)})


class CuerpoFalla(BaseModel):
    tipo: str | None = None


@router.post("/demo/falla")
def fijar_falla(cuerpo: CuerpoFalla, request: Request):
    """Fija la falla forzada para las siguientes tareas (429, timeout, json, todo o ninguna).

    Solo si `PERMITIR_FALLAS_DESDE_UI` está activo: en una instalación real nadie
    debería poder tumbar al proveedor desde el navegador.
    """
    if not config.PERMITIR_FALLAS_DESDE_UI:
        raise HTTPException(403, "El panel de demo está deshabilitado en esta instalación.")
    tipo = (cuerpo.tipo or "").strip()
    if tipo not in config.FALLAS_VALIDAS:
        opciones = ", ".join(sorted(f for f in config.FALLAS_VALIDAS if f))
        raise HTTPException(422, f"Falla desconocida «{tipo}». Opciones: {opciones} o ninguna.")
    request.app.state.demo.fijar(tipo or None)
    registro.info("Falla forzada desde el panel de demo: %s", tipo or "ninguna")
    return {"falla_forzada": request.app.state.demo.falla}
