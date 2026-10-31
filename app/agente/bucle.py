"""El bucle del agente: modelo → herramientas → modelo, con sus cuatro límites.

Se escribe a mano, sin framework de agentes, porque el curso evalúa entender este
bucle y sus límites línea por línea (diseno/agente.md, "Decisiones de esta sesión").
Una iteración es una llamada al modelo. En cada una:

1. Si ya se hicieron `max_iteraciones` llamadas → límite "iteraciones" y fin.
2. Si los tokens acumulados llegan al presupuesto → límite "tokens" y fin.
3. Se llama al proveedor (la cascada) con `timeout_modelo_s`; los fragmentos de texto
   salen como eventos "token" a medida que llegan (streaming real).
4. Si el modelo pidió herramientas, cada una corre en un hilo aparte con
   `timeout_herramienta_s`; su resultado vuelve al modelo en la siguiente iteración.
   Si la herramienta escribe, solo crea una propuesta: la confirmación humana es el
   cuarto límite y el bucle no la espera.
5. Si no pidió herramientas, esa es la respuesta final. Excepción en modo
   explicación: si todavía no hay resultado de obtener_caso, la respuesta NO se
   acepta (sería inventada: pasó con Gemini Flash-Lite en la demo del 429). Se emite
   `contrato_invalido` para que la pantalla borre el borrador, se le pide al modelo
   que consulte primero y la vuelta cuenta como una iteración más. Así no se gasta
   el único reintento de contrato del servicio en un error que se arregla solo.

Lección de la semana 6: el tope de iteraciones es un presupuesto dimensionado para la
tarea más larga esperada, no una red de seguridad contra un modelo desbocado.

El bucle no guarda nada ni decide respaldos: produce eventos (dict con "tipo") y va
llenando un EstadoTarea que el servicio lee al final.
"""

import json
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as TiempoAgotado
from dataclasses import dataclass, field
from typing import Iterator

from app import config
from app.agente import prompts
from app.agente.herramientas import HERRAMIENTAS, ContextoHerramientas, esquemas_para, nombres_para, validar_argumentos
from app.proveedores.base import ErrorProveedor, Mensaje, RespuestaModelo

# Hilos para las herramientas. Python no puede matar un hilo: si una herramienta se
# pasa del timeout, el bucle sigue sin ella y el hilo termina solo cuando pueda. Por
# eso es un grupo compartido y no uno por llamada (cerrar un grupo esperaría al hilo
# colgado y el timeout no serviría).
_EJECUTOR_HERRAMIENTAS = ThreadPoolExecutor(max_workers=4, thread_name_prefix="herramienta")


@dataclass
class Limites:
    max_iteraciones: int = 6          # llamadas al modelo por tarea
    presupuesto_tokens: int = 40_000  # entrada + salida acumulados por tarea
    timeout_modelo_s: float = 25.0    # por llamada al modelo
    timeout_herramienta_s: float = 5.0
    max_tokens_respuesta: int = 2_500
    max_herramientas_por_iteracion: int = 6   # sin él, 30 llamadas en una vuelta saltaban el presupuesto

    @classmethod
    def desde_config(cls) -> "Limites":
        return cls(config.MAX_ITERACIONES, config.PRESUPUESTO_TOKENS, config.TIMEOUT_MODELO_S,
                   config.TIMEOUT_HERRAMIENTA_S, config.MAX_TOKENS_RESPUESTA,
                   config.MAX_HERRAMIENTAS_POR_ITERACION)


@dataclass
class EstadoTarea:
    """Todo lo que la tarea acumula. Sobrevive entre dos corridas del bucle (reintento de contrato)."""
    mensajes: list[Mensaje] = field(default_factory=list)
    iteraciones: int = 0
    tokens_entrada: int = 0
    tokens_salida: int = 0
    costo_usd: float = 0.0
    reintentos: int = 0
    conmutaciones: int = 0
    fragmentos: int = 0                # tokens de streaming emitidos (no se guardan, solo se cuentan)
    # TTFT: desde el inicio de la tarea hasta el primer fragmento de la iteración que
    # produjo la respuesta final, es decir, lo que el analista lee. Antes se medía el
    # primer fragmento de CUALQUIER iteración, y en Claude ese era casi siempre un
    # preámbulo antes de pedir herramientas: 0,8 s reportados frente a 2,2-5,4 s reales
    # hasta el primer carácter de la explicación (validacion/app-analista.md).
    ttft_ms: int | None = None
    rechazo_declarado: bool = False    # el modelo llamó a declarar_fuera_de_alcance (modo pregunta)
    proveedor_final: str | None = None
    modelo_final: str | None = None
    resultados: list[dict] = field(default_factory=list)   # lo que devolvieron las herramientas: la evidencia
    rechazos_alcance: int = 0          # pedidos del modelo sobre otro caso
    texto_final: str = ""
    motivo_fin: str | None = None      # completada | limite_iteraciones | limite_tokens | timeout | proveedores_caidos
    detalle_error: str | None = None
    inicio: float = field(default_factory=time.monotonic)

    @property
    def tokens_totales(self) -> int:
        return self.tokens_entrada + self.tokens_salida

    def milisegundos(self) -> int:
        return int((time.monotonic() - self.inicio) * 1000)


def costo_usd(respuesta: RespuestaModelo) -> float:
    """Costo de lista de una llamada: tokens × tarifa por millón (config.TARIFAS_USD_POR_MILLON)."""
    tarifa_entrada, tarifa_salida = config.TARIFAS_USD_POR_MILLON.get(respuesta.modelo, (0.0, 0.0))
    return (respuesta.tokens_entrada * tarifa_entrada + respuesta.tokens_salida * tarifa_salida) / 1_000_000


def _resumen_resultado(resultado: dict) -> dict:
    """Para la traza: qué forma tuvo el resultado, sin copiarlo entero."""
    resumen = {"campos": sorted(resultado), "tamano_caracteres": len(json.dumps(resultado, ensure_ascii=False))}
    if "n_transacciones" in resultado:
        resumen["n_transacciones"] = resultado["n_transacciones"]
    return resumen


def _ejecutar_llamada(llamada, contexto: ContextoHerramientas, limites: Limites,
                      estado: EstadoTarea, permitidas: list[str] | None = None,
                      sobrante: bool = False) -> Iterator[dict]:
    """Corre una herramienta pedida por el modelo y deja su resultado en la conversación.

    `permitidas`: las herramientas del modo de la tarea. Una que existe pero no se
    ofreció en este modo (por ejemplo registrar_decision al explicar) se trata igual
    que una inexistente: el modelo no puede saltarse el modo pidiéndola por su nombre.
    `sobrante`: la llamada pasó el tope de herramientas por iteración; no se ejecuta,
    pero recibe su resultado de error (las APIs exigen uno por cada llamada pedida).
    """
    yield {"tipo": "herramienta", "nombre": llamada.nombre, "argumentos": llamada.argumentos,
           "id_llamada": llamada.id}

    permitidas = list(HERRAMIENTAS) if permitidas is None else permitidas
    herramienta = HERRAMIENTAS.get(llamada.nombre) if llamada.nombre in permitidas else None
    if sobrante:
        problema = (f"se pidieron más de {limites.max_herramientas_por_iteracion} herramientas en una "
                    "sola vuelta; esta no se ejecutó. Pide solo las que necesites")
    elif herramienta is None:
        problema = (f"la herramienta «{llamada.nombre}» no existe en este modo; las disponibles son: "
                    f"{', '.join(permitidas)}")
    elif herramienta.escribe and not any(r["nombre"] == "obtener_caso" for r in estado.resultados):
        # Una propuesta tiene que poder rastrearse a la evidencia: sin haber leído el caso,
        # el argumento sería dictado por quien pregunta (auditoría del 2026-10-31, A29).
        problema = "antes de proponer una decisión consulta el caso con obtener_caso y argumenta con lo que devuelva"
    else:
        problema = validar_argumentos(herramienta, llamada.argumentos)

    if problema:
        # Error controlado: el modelo recibe el motivo y puede corregirse en la siguiente iteración.
        resultado = {"error": "llamada_invalida", "detalle": problema}
        yield {"tipo": "error_herramienta", "nombre": llamada.nombre, "error": "llamada_invalida",
               "detalle": problema}
    else:
        inicio = time.monotonic()
        futuro = _EJECUTOR_HERRAMIENTAS.submit(herramienta.ejecutar, llamada.argumentos, contexto)
        try:
            resultado = futuro.result(timeout=limites.timeout_herramienta_s)
        except TiempoAgotado:
            resultado = {"error": "timeout_herramienta",
                         "detalle": f"La herramienta tardó más de {limites.timeout_herramienta_s:g} s."}
        except Exception as error:   # una falla de la base no debe tumbar la tarea
            resultado = {"error": "fallo_herramienta", "detalle": f"{type(error).__name__}: {error}"}
        duracion_ms = int((time.monotonic() - inicio) * 1000)

        if "error" in resultado:
            if resultado["error"] == "fuera_de_alcance":
                estado.rechazos_alcance += 1
            yield {"tipo": "error_herramienta", "nombre": llamada.nombre, "error": resultado["error"],
                   "detalle": resultado.get("detalle"), "duracion_ms": duracion_ms}
        else:
            estado.resultados.append({"nombre": llamada.nombre, "resultado": resultado})
            if llamada.nombre == "declarar_fuera_de_alcance":
                estado.rechazo_declarado = True
            yield {"tipo": "resultado_herramienta", "nombre": llamada.nombre,
                   "resumen": _resumen_resultado(resultado), "duracion_ms": duracion_ms}
            if herramienta.escribe and resultado.get("propuesta_id") is not None:
                yield {"tipo": "propuesta", "propuesta_id": resultado["propuesta_id"],
                       "accion": llamada.argumentos.get("accion"),
                       "argumento": llamada.argumentos.get("argumento")}

    estado.mensajes.append(Mensaje(rol="herramienta", id_llamada=llamada.id,
                                   nombre_herramienta=llamada.nombre, resultado=resultado))


def ejecutar(tipo: str, id_caso: str, pregunta: str | None, contexto: ContextoHerramientas,
             limites: Limites, proveedor, estado: EstadoTarea,
             falla_forzada: str | None = None) -> Iterator[dict]:
    """Corre el bucle hasta una respuesta final o un límite. `proveedor` es una ProveedorEnCascada.

    Si `estado.mensajes` ya trae conversación (reintento por contrato), continúa desde
    ahí y los límites siguen contando sobre lo ya gastado en la tarea.
    """
    sistema = prompts.sistema_para(tipo)
    esquemas = esquemas_para(tipo)
    permitidas = nombres_para(tipo)
    if not estado.mensajes:
        estado.mensajes.append(Mensaje(rol="usuario", texto=prompts.mensaje_inicial(tipo, id_caso, pregunta)))
    estado.motivo_fin = None

    while True:
        # Límite 1: iteraciones.
        if estado.iteraciones >= limites.max_iteraciones:
            estado.motivo_fin = "limite_iteraciones"
            yield {"tipo": "limite", "cual": "iteraciones",
                   "detalle": f"Se alcanzó el máximo de {limites.max_iteraciones} llamadas al modelo en esta tarea."}
            return
        # Límite 2: presupuesto de tokens.
        if estado.tokens_totales >= limites.presupuesto_tokens:
            estado.motivo_fin = "limite_tokens"
            yield {"tipo": "limite", "cual": "tokens",
                   "detalle": f"Se gastaron {estado.tokens_totales} tokens de un presupuesto de "
                              f"{limites.presupuesto_tokens} por tarea."}
            return

        estado.iteraciones += 1
        actual = getattr(proveedor, "proveedor_actual", None)
        yield {"tipo": "modelo_llamado", "iteracion": estado.iteraciones,
               "proveedor": getattr(actual, "nombre", None), "modelo": getattr(actual, "modelo", None)}

        # Límite 3: timeout por llamada (lo aplica el cliente; la cascada reintenta o conmuta).
        respuesta = None
        ttft_iteracion = None   # primer fragmento de ESTA llamada; cuenta solo si resulta ser la final
        try:
            for clase, dato in proveedor.generar(sistema, estado.mensajes, esquemas,
                                                 limites.max_tokens_respuesta, limites.timeout_modelo_s,
                                                 falla_forzada=falla_forzada):
                if clase == "texto":
                    if ttft_iteracion is None:
                        ttft_iteracion = estado.milisegundos()
                    estado.fragmentos += 1
                    yield {"tipo": "token", "texto": dato}
                elif clase == "evento":
                    if dato["tipo"] == "reintento":
                        estado.reintentos += 1
                    elif dato["tipo"] == "conmutacion":
                        estado.conmutaciones += 1
                    yield dato
                elif clase == "fin":
                    respuesta = dato
        except ErrorProveedor as error:
            estado.detalle_error = error.mensaje
            if getattr(error, "solo_timeouts", False):
                estado.motivo_fin = "timeout"
                yield {"tipo": "limite", "cual": "timeout",
                       "detalle": f"Ningún proveedor respondió dentro de {limites.timeout_modelo_s:g} s por llamada."}
            else:
                estado.motivo_fin = "proveedores_caidos"
                yield {"tipo": "estado", "texto": "Ningún proveedor de IA respondió."}
            return

        estado.tokens_entrada += respuesta.tokens_entrada
        estado.tokens_salida += respuesta.tokens_salida
        estado.costo_usd += costo_usd(respuesta)
        estado.proveedor_final, estado.modelo_final = respuesta.proveedor, respuesta.modelo
        estado.mensajes.append(Mensaje(rol="asistente", texto=respuesta.texto, llamadas=respuesta.llamadas))

        if not respuesta.llamadas:
            if tipo == "explicacion" and not any(r["nombre"] == "obtener_caso" for r in estado.resultados):
                # Respuesta sin evidencia: no se acepta ni se le gasta el reintento de contrato.
                yield {"tipo": "contrato_invalido", "reintenta": True, "etapa": "bucle",
                       "errores": ["no consultó la evidencia: respondió sin haber llamado a obtener_caso"]}
                estado.mensajes.append(Mensaje(rol="usuario", texto=prompts.mensaje_sin_evidencia(id_caso)))
                continue
            estado.texto_final = respuesta.texto
            # Con reintento de contrato hay dos respuestas finales: vale la última, la que se muestra.
            estado.ttft_ms = ttft_iteracion
            estado.motivo_fin = "completada"
            return

        # Límite 4 (confirmación humana) vive dentro de registrar_decision: solo propone.
        for indice, llamada in enumerate(respuesta.llamadas):
            yield from _ejecutar_llamada(llamada, contexto, limites, estado, permitidas,
                                         sobrante=indice >= limites.max_herramientas_por_iteracion)
