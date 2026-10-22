"""Servicio del agente: lo único que llama la API.

Orquesta una tarea completa (diseno/agente.md, "Servicio"):
caché → bucle → validación del contrato → un reintento → plantilla → persistencia.

- `explicar_caso`: si el caso ya tiene explicación guardada y no se pide regenerar,
  la sirve desde caché (y registra la tarea, para medir el ahorro). Si no, corre el
  bucle, valida contra el contrato, reintenta una vez con los errores y, si aun así
  no hay explicación válida (o cayeron los proveedores, o saltó un límite), usa la
  plantilla. Un candado por caso evita dos generaciones simultáneas del mismo caso.
- `responder_pregunta`: el mismo bucle en modo pregunta; la respuesta es texto libre.
  El rechazo se decide por la herramienta declarar_fuera_de_alcance (estructurado),
  no leyendo el texto.

`nivel_riesgo_en_palabras` lo escribe este servicio con la frase armada en código
(riesgo_en_palabras.py) sobre toda explicación que se guarda, del modelo o de la
plantilla: el modelo contradecía el percentil que citaba y el contrato no podía verlo.

Los dos son generadores de eventos (dict con "tipo"): la API los reenvía tal cual
por SSE y aquí mismo se guardan en `trazas`, todos menos "token" (de esos solo se
guarda el conteo). Ninguna excepción sale cruda: el usuario recibe un evento
"error" en español con una acción sugerida y el detalle técnico queda en la traza.

El repositorio y la cascada se pueden inyectar (parámetros con valor por defecto)
para probar el servicio con dobles, sin base de datos ni red.
"""

import threading
import uuid
from dataclasses import asdict
from typing import Iterator

from app import config
from app.agente import bucle, prompts
from app.agente.bucle import EstadoTarea, Limites
from app.agente.contrato import armar_evidencia, senales_citables, validar_explicacion
from app.agente.herramientas import ContextoHerramientas
from app.agente.plantilla import explicacion_de_plantilla
from app.agente.riesgo_en_palabras import con_nivel_de_codigo, nivel_riesgo_en_palabras, posicion_tolerante
from app.proveedores.base import Mensaje
from app.proveedores.cascada import cascada_desde_config

ESPERA_MAXIMA_CANDADO_S = 120   # más que una tarea completa con todos sus reintentos

_candados: dict[str, threading.Lock] = {}
_candado_del_registro = threading.Lock()

MOTIVOS_DE_RESPALDO = {
    "sin_proveedor": "Sin proveedor de IA configurado: explicación armada por reglas.",
    "proveedores_caidos": "Ningún proveedor de IA respondió: explicación armada por reglas con las señales guardadas.",
    "limite_iteraciones": "Se alcanzó el máximo de llamadas al modelo: explicación armada por reglas.",
    "limite_tokens": "Se agotó el presupuesto de tokens de la tarea: explicación armada por reglas.",
    "timeout": "El asistente de IA no respondió a tiempo: explicación armada por reglas.",
    "contrato": "La IA no logró una explicación anclada a la evidencia en dos intentos: explicación armada por reglas.",
}


def _candado_de(id_caso: str) -> threading.Lock:
    with _candado_del_registro:
        return _candados.setdefault(id_caso, threading.Lock())


def _repositorio_por_defecto():
    # Importe perezoso: así el agente se puede probar sin psycopg ni base de datos.
    from app.db import repositorio
    return repositorio


def _normalizar_falla(falla_forzada: str | None) -> str | None:
    """None → la del entorno (FALLA_FORZADA). "" → ninguna. Un valor desconocido se ignora."""
    falla = config.FALLA_FORZADA if falla_forzada is None else falla_forzada
    falla = (falla or "").strip().lower()
    return falla if falla in config.FALLAS_VALIDAS and falla else None


def _error_para_usuario(mensaje: str, accion_sugerida: str) -> dict:
    return {"tipo": "error", "mensaje": mensaje, "accion_sugerida": accion_sugerida}



class _Tarea:
    """Una tarea en curso: emite eventos, los guarda en trazas y cierra con métricas."""

    def __init__(self, repositorio, tarea_id: str, estado: EstadoTarea):
        self.repositorio = repositorio
        self.tarea_id = tarea_id
        self.estado = estado
        self.paso = 0

    def emitir(self, evento: dict) -> dict:
        if evento["tipo"] != "token":
            self.paso += 1
            detalle = {clave: valor for clave, valor in evento.items() if clave != "tipo"}
            self.repositorio.registrar_traza(self.tarea_id, self.paso, evento["tipo"], detalle,
                                             evento.get("duracion_ms"))
        return evento

    def cerrar(self, motivo_fin: str, desde_cache: bool = False, es_respaldo: bool = False) -> dict:
        e = self.estado
        metricas = {
            "motivo_fin": motivo_fin,
            "iteraciones": e.iteraciones,
            "tokens_entrada": e.tokens_entrada,
            "tokens_salida": e.tokens_salida,
            "costo_usd": round(e.costo_usd, 6),
            "latencia_ms": e.milisegundos(),
            "ttft_ms": e.ttft_ms,
            "proveedor_final": e.proveedor_final,
            "modelo_final": e.modelo_final,
            "reintentos": e.reintentos,
            "conmutaciones": e.conmutaciones,
            "desde_cache": desde_cache,
        }
        self.repositorio.cerrar_tarea(self.tarea_id, **metricas)
        return self.emitir({"tipo": "fin", "tarea_id": self.tarea_id, **metricas,
                            "tokens": e.tokens_totales, "fragmentos_streaming": e.fragmentos,
                            "es_respaldo": es_respaldo})

    def fallo_inesperado(self, error: Exception) -> Iterator[dict]:
        """Deja el detalle técnico en la traza y al usuario solo un mensaje en español."""
        evento = _error_para_usuario("Ocurrió un error inesperado al atender la solicitud.",
                                     "Vuelve a intentarlo; si se repite, revisa el registro del servidor.")
        try:
            self.emitir({**evento, "detalle_tecnico": f"{type(error).__name__}: {error}"})
            yield evento
            yield self.cerrar("error")
        except Exception:
            yield evento   # ni la traza se pudo guardar: al menos el usuario se entera


# --- Explicación -----------------------------------------------------------------------
def explicar_caso(id_caso: str, regenerar: bool = False, falla_forzada: str | None = None,
                  repositorio=None, cascada=None, limites: Limites | None = None) -> Iterator[dict]:
    repositorio = repositorio or _repositorio_por_defecto()
    candado = _candado_de(id_caso)
    if not candado.acquire(blocking=False):
        yield {"tipo": "estado", "texto": "Ya se está generando la explicación de este caso; esperando a que termine…"}
        if not candado.acquire(timeout=ESPERA_MAXIMA_CANDADO_S):
            yield _error_para_usuario("La otra generación de este caso no terminó a tiempo.",
                                      "Vuelve a intentarlo en un minuto.")
            return
        regenerar = False   # la que acaba de terminar es la vigente: se sirve desde caché
    try:
        yield from _explicar(id_caso, regenerar, _normalizar_falla(falla_forzada), repositorio,
                             cascada, limites or Limites.desde_config())
    finally:
        candado.release()


def _explicar(id_caso, regenerar, falla, repositorio, cascada, limites) -> Iterator[dict]:
    estado = EstadoTarea()
    try:
        caso = repositorio.obtener_caso(id_caso)
    except Exception:
        yield _error_para_usuario("No se pudo leer el caso de la base de datos.",
                                  "Revisa que la base esté arriba y vuelve a intentarlo.")
        return
    if caso is None:
        yield _error_para_usuario(f"No existe el caso {id_caso}.", "Vuelve a la bandeja y elige otro caso.")
        return

    tarea_id = str(uuid.uuid4())
    repositorio.crear_tarea(tarea_id, id_caso, "explicacion", falla_forzada=falla)
    tarea = _Tarea(repositorio, tarea_id, estado)
    try:
        yield tarea.emitir({"tipo": "inicio", "tarea_id": tarea_id, "tipo_tarea": "explicacion",
                            "id_caso": id_caso, "limites": asdict(limites), "falla_forzada": falla})

        proveedor = cascada if cascada is not None else cascada_desde_config()

        # 1. Caché: la explicación guardada ya está validada; no se gasta cuota. Una de
        #    plantilla solo se reutiliza si no hay IA disponible: si la hay, se reintenta.
        vigente = None if regenerar else repositorio.explicacion_vigente(id_caso)
        if vigente and (not vigente.get("es_respaldo") or proveedor.vacia):
            yield tarea.emitir({"tipo": "cache", "explicacion": con_nivel_de_codigo(vigente, caso, repositorio)})
            yield tarea.cerrar("completada", desde_cache=True, es_respaldo=bool(vigente.get("es_respaldo")))
            return

        # 2. Sin proveedores no hay bucle: directo a la plantilla.
        if proveedor.vacia:
            yield from _respaldo(tarea, caso, repositorio, "sin_proveedor", "respaldo")
            return

        # 3. Bucle + contrato, con un reintento si el contrato falla.
        yield tarea.emitir({"tipo": "estado", "texto": "El asistente está consultando la evidencia del caso…"})
        contexto = ContextoHerramientas(id_caso=id_caso, tarea_id=tarea_id, repositorio=repositorio)
        contenido = None
        for intento in (1, 2):
            for evento in bucle.ejecutar("explicacion", id_caso, None, contexto, limites, proveedor,
                                         estado, falla_forzada=falla):
                yield tarea.emitir(evento)
            if estado.motivo_fin != "completada":
                break
            evidencia = armar_evidencia(caso, estado.resultados)
            contenido, errores = validar_explicacion(estado.texto_final, evidencia)
            if contenido:
                break
            reintenta = intento == 1
            yield tarea.emitir({"tipo": "contrato_invalido", "errores": errores, "reintenta": reintenta})
            if reintenta:
                estado.mensajes.append(Mensaje(rol="usuario", texto=prompts.mensaje_reintento_contrato(
                    errores, senales_citables(caso))))

        # 4. Guardar la explicación válida o caer a la plantilla.
        if contenido:
            # El nivel en palabras lo pone el código, no el modelo (ver docstring del módulo).
            contenido["nivel_riesgo_en_palabras"] = nivel_riesgo_en_palabras(
                caso, posicion_tolerante(caso, repositorio))
            repositorio.guardar_explicacion(id_caso, tarea_id, contenido, False,
                                            estado.proveedor_final, estado.modelo_final)
            yield tarea.emitir({"tipo": "explicacion", "contenido": contenido,
                                "proveedor": estado.proveedor_final, "modelo": estado.modelo_final})
            yield tarea.cerrar("completada")
        elif estado.motivo_fin in ("limite_iteraciones", "limite_tokens", "timeout"):
            yield from _respaldo(tarea, caso, repositorio, estado.motivo_fin, estado.motivo_fin)
        elif estado.motivo_fin == "proveedores_caidos":
            yield from _respaldo(tarea, caso, repositorio, "proveedores_caidos", "respaldo")
        else:
            yield from _respaldo(tarea, caso, repositorio, "contrato", "respaldo")
    except Exception as error:
        yield from tarea.fallo_inesperado(error)


def _respaldo(tarea: _Tarea, caso: dict, repositorio, clave_motivo: str, motivo_fin: str) -> Iterator[dict]:
    """Último escalón: la explicación de plantilla, guardada y marcada como respaldo."""
    historial = repositorio.obtener_historial(caso["id_caso"], dias=7, limite=40)
    contenido = explicacion_de_plantilla(caso, historial, posicion_tolerante(caso, repositorio))
    repositorio.guardar_explicacion(caso["id_caso"], tarea.tarea_id, contenido, True, None, None)
    yield tarea.emitir({"tipo": "respaldo", "motivo": MOTIVOS_DE_RESPALDO[clave_motivo], "contenido": contenido})
    # La tarea guarda el motivo real (un límite, o "respaldo") para que la medición lo distinga.
    yield tarea.cerrar(motivo_fin, es_respaldo=True)


# --- Pregunta --------------------------------------------------------------------------
def responder_pregunta(id_caso: str, pregunta: str, falla_forzada: str | None = None,
                       repositorio=None, cascada=None, limites: Limites | None = None) -> Iterator[dict]:
    repositorio = repositorio or _repositorio_por_defecto()
    limites = limites or Limites.desde_config()
    falla = _normalizar_falla(falla_forzada)
    estado = EstadoTarea()

    if not (pregunta or "").strip():
        yield _error_para_usuario("La pregunta está vacía.", "Escribe qué quieres saber del caso.")
        return
    try:
        caso = repositorio.obtener_caso(id_caso)
    except Exception:
        yield _error_para_usuario("No se pudo leer el caso de la base de datos.",
                                  "Revisa que la base esté arriba y vuelve a intentarlo.")
        return
    if caso is None:
        yield _error_para_usuario(f"No existe el caso {id_caso}.", "Vuelve a la bandeja y elige otro caso.")
        return

    tarea_id = str(uuid.uuid4())
    repositorio.crear_tarea(tarea_id, id_caso, "pregunta", pregunta=pregunta, falla_forzada=falla)
    tarea = _Tarea(repositorio, tarea_id, estado)
    try:
        yield tarea.emitir({"tipo": "inicio", "tarea_id": tarea_id, "tipo_tarea": "pregunta",
                            "id_caso": id_caso, "limites": asdict(limites), "falla_forzada": falla})

        proveedor = cascada if cascada is not None else cascada_desde_config()
        if proveedor.vacia:
            yield tarea.emitir(_error_para_usuario(
                "No hay proveedor de IA configurado: las preguntas necesitan al asistente.",
                "La explicación armada por reglas sigue disponible en el detalle del caso."))
            yield tarea.cerrar("error")
            return

        contexto = ContextoHerramientas(id_caso=id_caso, tarea_id=tarea_id, repositorio=repositorio)
        for evento in bucle.ejecutar("pregunta", id_caso, pregunta, contexto, limites, proveedor,
                                     estado, falla_forzada=falla):
            yield tarea.emitir(evento)

        if estado.motivo_fin == "completada":
            texto = estado.texto_final.strip()
            # Rechazo, en orden de confianza: (1) el modelo llamó a declarar_fuera_de_alcance;
            # (2) intentó consultar otro caso y la herramienta se lo negó; (3) respaldo para un
            # modelo que ignore la herramienta: la respuesta EMPIEZA con la marca vieja. Ya no
            # se busca la marca en cualquier parte del texto (falló en los dos sentidos en eval/).
            rechazo = (estado.rechazo_declarado or estado.rechazos_alcance > 0
                       or texto.lower().startswith(prompts.MARCA_RECHAZO.lower()))
            yield tarea.emitir({"tipo": "respuesta", "texto": texto, "rechazo": rechazo})
            yield tarea.cerrar("rechazo" if rechazo else "completada")
        elif estado.motivo_fin in ("limite_iteraciones", "limite_tokens", "timeout"):
            yield tarea.emitir(_error_para_usuario(
                "La tarea se detuvo al llegar a uno de sus límites (ver la traza).",
                "Haz una pregunta más concreta o vuelve a intentarlo."))
            yield tarea.cerrar(estado.motivo_fin)
        else:
            yield tarea.emitir(_error_para_usuario(
                "Ningún proveedor de IA respondió.", "Vuelve a intentarlo en unos minutos."))
            yield tarea.cerrar("error")
    except Exception as error:
        yield from tarea.fallo_inesperado(error)
