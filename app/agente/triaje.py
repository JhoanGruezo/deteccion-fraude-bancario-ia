"""Triaje del agente en segundo plano y red de seguridad (SPEC, RF3 y RF4).

Cuando el flujo en vivo abre un caso o lo sube de banda (`app/riesgo/flujo.py`), el
**despachador** lanza un triaje en un hilo propio: no espera a que un analista abra la pantalla.
El agente lee la evidencia y toma UNA acción con las herramientas de triaje; las guardas viven
en el código y en la base (`app/db/repositorio_acciones.py`), no en el prompt.

Lo que pasa después del triaje, según el caso:

| Situación al terminar | Qué hace el código |
|---|---|
| El agente actuó (bloqueó, pidió verificación o lo dejó a un analista) | Se respeta, salvo en banda crítica sin bloqueo |
| Banda crítica y la tarjeta sigue sin bloqueo (por la razón que sea) | La regla bloquea en ese momento |
| Banda alta o media y el triaje falló (proveedor caído, límite, tope de gasto) | La regla pide verificación al titular con el motivo de plantilla |
| Autonomía del agente apagada | No se llama al LLM; crítica: bloquea la regla; el resto queda para los analistas |

La **red de seguridad** es un hilo aparte que cada pocos segundos busca casos críticos sin
bloqueo desde hace más de `SEGUNDOS_RED_DE_SEGURIDAD` (90 s por defecto) y los bloquea. Cubre
lo que el triaje no alcanzó: la cola de triajes llena, la app reiniciada a mitad, un hilo
colgado. Con las dos piezas, el objetivo de "bloqueado en menos de 5 minutos" no depende de
que la IA responda.
"""

import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from typing import Iterator

from app import config
from app.agente import bucle, servicio
from app.agente.bucle import EstadoTarea, Limites
from app.agente.herramientas import ACCIONES_DE_TRIAJE, ContextoHerramientas
from app.db.repositorio_agente import RepositorioDelAgente
from app.proveedores.cascada import cascada_desde_config

registro = logging.getLogger("app.agente.triaje")

ESTADOS_SIN_TRIAJE = ("bloqueado", "descartado", "desbloqueado", "bloqueo_confirmado")
# Resultados de una acción que las guardas rechazaron: no cuentan como decisión del agente.
RESULTADOS_NO_EFECTIVOS = ("no_permitido", "autonomia_apagada", "tope_alcanzado")


def _acciones_por_defecto():
    from app.riesgo import acciones
    return acciones


def _repositorio_acciones():
    from app.db import repositorio_acciones
    return repositorio_acciones


def _tipo_de_bloqueo(caso: dict) -> str:
    return "acceso_cuenta" if "viaje_imposible" in (caso.get("tipos_fraude") or []) else "tarjeta"


def _decision_del_agente(estado: EstadoTarea) -> dict | None:
    """La última acción de triaje que el agente ejecutó, con su resultado (rechazada o no)."""
    for registro_herramienta in reversed(estado.resultados):
        if registro_herramienta["nombre"] in ACCIONES_DE_TRIAJE:
            return {"accion": registro_herramienta["nombre"], **registro_herramienta["resultado"]}
    return None


def _es_efectiva(decision: dict | None) -> bool:
    return decision is not None and decision.get("resultado") not in RESULTADOS_NO_EFECTIVOS


def triar_caso(id_caso: str, falla_forzada: str | None = None, repositorio=None, cascada=None,
               limites: Limites | None = None, acciones=None, acciones_agente=None) -> Iterator[dict]:
    """Corre el triaje de un caso y, si hace falta, el respaldo de la regla. Generador de eventos."""
    repositorio = repositorio or servicio._repositorio_por_defecto()
    acciones = acciones or _acciones_por_defecto()
    limites = limites or Limites.desde_config()
    falla = servicio._normalizar_falla(falla_forzada)
    caso = repositorio.obtener_caso(id_caso)
    if caso is None or caso.get("estado") in ESTADOS_SIN_TRIAJE or not caso.get("banda"):
        return

    estado = EstadoTarea()
    tarea_id = str(uuid.uuid4())
    repositorio.crear_tarea(tarea_id, id_caso, "triaje", falla_forzada=falla)
    tarea = servicio._Tarea(repositorio, tarea_id, estado)
    try:
        yield tarea.emitir({"tipo": "inicio", "tarea_id": tarea_id, "tipo_tarea": "triaje", "id_caso": id_caso,
                            "banda": caso["banda"], "limites": asdict(limites), "falla_forzada": falla})
        proveedor = cascada if cascada is not None else cascada_desde_config()
        autonomia = _autonomia_encendida()
        if not autonomia:
            yield from _respaldo_de_regla(tarea, repositorio, acciones, id_caso, "autonomia_apagada")
            return
        if proveedor.vacia or servicio.tope_de_gasto_alcanzado(repositorio):
            motivo = "sin_proveedor" if proveedor.vacia else "tope_gasto"
            yield from _respaldo_de_regla(tarea, repositorio, acciones, id_caso, motivo)
            return

        contexto = ContextoHerramientas(
            id_caso=id_caso, tarea_id=tarea_id, repositorio=RepositorioDelAgente(repositorio),
            acciones=acciones_agente or acciones.AccionesDelAgente(id_caso, tarea_id))
        for evento in bucle.ejecutar("triaje", id_caso, None, contexto, limites, proveedor, estado,
                                     falla_forzada=falla):
            yield tarea.emitir(evento)

        decision = _decision_del_agente(estado)
        actual = repositorio.obtener_caso(id_caso)
        sin_bloqueo_critico = actual and actual.get("banda") == "critica" and actual.get("estado") != "bloqueado"
        if not _es_efectiva(decision) or sin_bloqueo_critico:
            if decision is None:
                motivo = estado.motivo_fin if estado.motivo_fin != "completada" else "sin_accion"
            else:
                motivo = "critico_sin_bloqueo" if _es_efectiva(decision) else decision.get("resultado")
            yield from _respaldo_de_regla(tarea, repositorio, acciones, id_caso, motivo, decision)
            return
        yield tarea.emitir({"tipo": "triaje", "decision": decision, "resumen": estado.texto_final.strip()[:500]})
        yield tarea.cerrar("completada")
    except Exception as error:   # noqa: BLE001
        yield from tarea.fallo_inesperado(error)
        # Aun con el agente roto, un caso crítico no se queda sin bloquear.
        try:
            for evento in _respaldo_de_regla(None, repositorio, acciones, id_caso, "error"):
                yield evento
        except Exception:  # noqa: BLE001
            registro.exception("El respaldo de la regla también falló para %s", id_caso)


def _autonomia_encendida() -> bool:
    try:
        return bool(_repositorio_acciones().ajustes().get("autonomia_agente", {}).get("valor", True))
    except Exception:  # noqa: BLE001 — sin poder leer el ajuste, se asume el valor por defecto
        return True


def _respaldo_de_regla(tarea, repositorio, acciones, id_caso, motivo, decision=None) -> Iterator[dict]:
    """La regla actúa cuando el agente no lo hizo: bloquea si es crítico; si no, pide verificación."""
    caso = repositorio.obtener_caso(id_caso)
    if caso is None:
        return
    if caso.get("banda") == "critica" and caso.get("estado") != "bloqueado":
        causa = "autonomia_apagada" if motivo == "autonomia_apagada" else "triaje_sin_bloqueo"
        resultado = acciones.bloquear(id_caso, _tipo_de_bloqueo(caso), "regla", causa_regla=causa)
        accion = "bloqueo_por_regla"
    elif caso.get("banda") in ("alta", "media") and motivo != "autonomia_apagada" and not _es_efectiva(decision):
        resultado = acciones.solicitar_verificacion(id_caso, "regla")
        accion = "verificacion_por_regla"
    else:
        resultado, accion = {"resultado": "en_cola_humana"}, "cola_humana"
    evento = {"tipo": "respaldo_triaje", "motivo": motivo, "accion": accion, "resultado": resultado.get("resultado"),
              "decision_agente": decision}
    if tarea is None:
        yield evento
        return
    yield tarea.emitir(evento)
    yield tarea.cerrar("respaldo")


# --- Despachador de triajes ---------------------------------------------------------------


class Despachador:
    """Corre los triajes en un grupo de hilos, uno por caso a la vez.

    Si un caso sube de banda mientras su triaje corre, se vuelve a triar al terminar (el agente
    tiene que ver la banda nueva). La espera es asíncrona: evaluar la transacción nunca espera
    al LLM.
    """

    def __init__(self, maximo: int | None = None, triar=triar_caso):
        self._ejecutor = ThreadPoolExecutor(max_workers=maximo or config.TRIAJES_SIMULTANEOS,
                                            thread_name_prefix="triaje")
        self._triar = triar
        self._en_curso: set[str] = set()
        self._repetir: set[str] = set()
        self._candado = threading.Lock()

    def al_cambiar_caso(self, evento: dict) -> None:
        self.encolar(evento["id_caso"])

    def encolar(self, id_caso: str) -> None:
        with self._candado:
            if id_caso in self._en_curso:
                self._repetir.add(id_caso)
                return
            self._en_curso.add(id_caso)
        self._ejecutor.submit(self._correr, id_caso)

    def _correr(self, id_caso: str) -> None:
        try:
            for _ in self._triar(id_caso):
                pass
        except Exception:  # noqa: BLE001
            registro.exception("El triaje del caso %s falló", id_caso)
        finally:
            with self._candado:
                self._en_curso.discard(id_caso)
                otra_vez = id_caso in self._repetir
                self._repetir.discard(id_caso)
            if otra_vez:
                self.encolar(id_caso)

    def ocupado(self) -> bool:
        with self._candado:
            return bool(self._en_curso)

    def apagar(self) -> None:
        self._ejecutor.shutdown(wait=False, cancel_futures=True)


# --- Red de seguridad ---------------------------------------------------------------------


class RedDeSeguridad(threading.Thread):
    """Hilo que bloquea los casos críticos que pasaron `segundos` sin bloqueo (SPEC, RF4)."""

    def __init__(self, segundos: float | None = None, intervalo: float | None = None, acciones=None,
                 repositorio=None):
        super().__init__(name="red-de-seguridad", daemon=True)
        self.segundos = config.SEGUNDOS_RED_DE_SEGURIDAD if segundos is None else segundos
        self.intervalo = config.INTERVALO_RED_DE_SEGURIDAD_S if intervalo is None else intervalo
        self._acciones = acciones
        self._repositorio = repositorio
        self._detener = threading.Event()

    def revisar_una_vez(self) -> list[dict]:
        acciones = self._acciones or _acciones_por_defecto()
        repositorio = self._repositorio or servicio._repositorio_por_defecto()
        resultados = []
        for id_caso in _repositorio_acciones().criticos_sin_bloqueo(self.segundos):
            caso = repositorio.obtener_caso(id_caso)
            if caso is None:
                continue
            resultado = acciones.bloquear(id_caso, _tipo_de_bloqueo(caso), "regla", causa_regla="red_de_seguridad")
            resultados.append({"id_caso": id_caso, **resultado})
        return resultados

    def run(self) -> None:
        while not self._detener.wait(self.intervalo):
            try:
                self.revisar_una_vez()
            except Exception:  # noqa: BLE001 — la red no se cae por un error pasajero de la base
                registro.exception("La red de seguridad falló en esta vuelta; sigue en la próxima")

    def detener(self) -> None:
        self._detener.set()
