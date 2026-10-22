"""Pruebas del bucle (cuatro límites, errores de herramienta) y del servicio, sin red ni base.

`RepositorioFalso` implementa en memoria la interfaz de app/db/repositorio.py
(diseno/persistencia.md) que usa el agente. El modelo es un ProveedorFalso con guion
dentro de una ProveedorEnCascada real, así que se prueba el camino completo.
"""

import json
import time

from app.agente import servicio
from app.agente.bucle import EstadoTarea, Limites, ejecutar
from app.agente.herramientas import ContextoHerramientas, esquemas_para
from app.proveedores.base import ErrorProveedor
from app.proveedores.cascada import ProveedorEnCascada
from app.pruebas.test_cascada import ProveedorFalso, llamada, respuesta
from app.pruebas.test_contrato import caso_de_ejemplo, explicacion_valida

ID = "SPK-000001"


class RepositorioFalso:
    def __init__(self, caso=None, demora_obtener_caso_s=0.0, demora_solo_la_primera=False):
        self.casos = {ID: caso or caso_de_ejemplo()}
        self.demora = demora_obtener_caso_s
        self.demora_solo_la_primera = demora_solo_la_primera
        self.tareas, self.trazas, self.explicaciones = {}, [], []
        self.propuestas, self.decisiones = [], []

    def obtener_caso(self, id_caso):
        demora = self.demora
        if self.demora_solo_la_primera:
            self.demora = 0.0
        time.sleep(demora)
        return self.casos.get(id_caso)

    def obtener_historial(self, id_caso, dias=30, limite=60):
        return [{"fecha_hora": "2020-07-29 18:40:00", "monto": 45.3, "comercio": "Tienda Uno",
                 "categoria": "home", "ubicacion": "New Boston", "en_caso": False}]

    def listar_casos(self, fuente=None, limite=300, **filtros):
        return [{"id_caso": ID, "score_maximo": 0.997685}, {"id_caso": "SPK-000002", "score_maximo": 0.6}]

    def crear_tarea(self, tarea_id, id_caso, tipo, pregunta=None, falla_forzada=None):
        self.tareas[tarea_id] = {"id_caso": id_caso, "tipo": tipo, "falla_forzada": falla_forzada}

    def cerrar_tarea(self, tarea_id, **metricas):
        self.tareas[tarea_id].update(metricas)

    def registrar_traza(self, tarea_id, paso, tipo, detalle, duracion_ms=None):
        json.dumps(detalle)   # la traza va a jsonb: debe ser serializable
        self.trazas.append({"tarea_id": tarea_id, "paso": paso, "tipo": tipo, "detalle": detalle})

    def explicacion_vigente(self, id_caso):
        guardadas = [e for e in self.explicaciones if e["id_caso"] == id_caso]
        return guardadas[-1] if guardadas else None

    def guardar_explicacion(self, id_caso, tarea_id, contenido, es_respaldo, proveedor, modelo):
        self.explicaciones.append({"id_caso": id_caso, "tarea_id": tarea_id, "contenido": contenido,
                                   "es_respaldo": es_respaldo, "proveedor": proveedor, "modelo": modelo})
        return len(self.explicaciones)

    def crear_propuesta(self, id_caso, tarea_id, accion, argumento):
        propuesta = {"id": len(self.propuestas) + 1, "id_caso": id_caso, "accion": accion,
                     "argumento": argumento, "estado": "pendiente"}
        self.propuestas.append(propuesta)
        return propuesta

    def registrar_decision(self, *args, **kwargs):   # el agente NUNCA debe llegar aquí
        self.decisiones.append((args, kwargs))


def cascada_con(*guion, nombre="gemini"):
    return ProveedorEnCascada([ProveedorFalso(nombre, list(guion))], esperas=(0, 0, 0), dormir=lambda s: None)


def correr_bucle(cascada, repositorio=None, tipo="explicacion", pregunta=None, **limites):
    repositorio = repositorio or RepositorioFalso()
    estado = EstadoTarea()
    contexto = ContextoHerramientas(id_caso=ID, tarea_id="t-1", repositorio=repositorio)
    eventos = list(ejecutar(tipo, ID, pregunta, contexto, Limites(**limites), cascada, estado))
    return eventos, estado, repositorio


def tipos(eventos):
    return [e["tipo"] for e in eventos]


PIDE_CASO = respuesta(llamadas=[llamada("obtener_caso", id_caso=ID)])
FINAL_VALIDA = respuesta(json.dumps(explicacion_valida(), ensure_ascii=False))


# --- Bucle -----------------------------------------------------------------------------
def test_flujo_normal_herramienta_y_respuesta_final():
    eventos, estado, _ = correr_bucle(cascada_con(PIDE_CASO, FINAL_VALIDA))
    assert tipos(eventos)[:3] == ["modelo_llamado", "herramienta", "resultado_herramienta"]
    assert "token" in tipos(eventos)
    assert estado.motivo_fin == "completada" and estado.iteraciones == 2
    assert estado.resultados[0]["nombre"] == "obtener_caso"
    assert estado.tokens_totales == 300 and estado.ttft_ms is not None


def test_limite_de_iteraciones():
    eventos, estado, _ = correr_bucle(cascada_con(PIDE_CASO), max_iteraciones=2)   # el modelo nunca termina
    assert estado.iteraciones == 2
    assert estado.motivo_fin == "limite_iteraciones"
    assert eventos[-1] == {"tipo": "limite", "cual": "iteraciones",
                           "detalle": "Se alcanzó el máximo de 2 llamadas al modelo en esta tarea."}


def test_limite_de_tokens():
    caro = respuesta(llamadas=[llamada("obtener_caso", id_caso=ID)], entrada=300, salida=100)
    eventos, estado, _ = correr_bucle(cascada_con(caro), presupuesto_tokens=500)
    assert estado.iteraciones == 2                   # 400 < 500 deja hacer la segunda; 800 ya no
    assert estado.motivo_fin == "limite_tokens"
    assert eventos[-1]["cual"] == "tokens"


def test_timeout_de_herramienta_no_cuelga_el_bucle():
    # La primera consulta se cuelga; el modelo se entera, vuelve a pedirla y termina.
    repositorio = RepositorioFalso(demora_obtener_caso_s=0.5, demora_solo_la_primera=True)
    inicio = time.monotonic()
    eventos, estado, _ = correr_bucle(cascada_con(PIDE_CASO, PIDE_CASO, FINAL_VALIDA), repositorio,
                                      timeout_herramienta_s=0.05)
    assert time.monotonic() - inicio < 0.45
    error = next(e for e in eventos if e["tipo"] == "error_herramienta")
    assert error["error"] == "timeout_herramienta"
    assert estado.mensajes[2].resultado["error"] == "timeout_herramienta"   # el modelo se entera
    assert estado.motivo_fin == "completada" and estado.iteraciones == 3


def test_timeout_del_modelo_termina_con_limite():
    cascada = cascada_con(ErrorProveedor("timeout", "lento"))
    eventos, estado, _ = correr_bucle(cascada)
    assert estado.motivo_fin == "timeout"
    assert eventos[-1]["tipo"] == "limite" and eventos[-1]["cual"] == "timeout"


def test_herramienta_inexistente_es_error_controlado_y_cuenta_iteracion():
    pide_otra = respuesta(llamadas=[llamada("borrar_todo", id_caso=ID)])
    eventos, estado, _ = correr_bucle(cascada_con(pide_otra, PIDE_CASO, FINAL_VALIDA))
    error = next(e for e in eventos if e["tipo"] == "error_herramienta")
    assert error["error"] == "llamada_invalida" and "no existe" in error["detalle"]
    assert estado.iteraciones == 3 and estado.motivo_fin == "completada"


# --- Hallazgo 1: respuesta sin evidencia ----------------------------------------------
def test_explicacion_sin_consultar_obtener_caso_no_se_acepta_y_se_pide_consultar():
    # Gemini Flash-Lite en la demo del 429: respondió un JSON inventado sin pedir herramientas.
    eventos, estado, _ = correr_bucle(cascada_con(FINAL_VALIDA, PIDE_CASO, FINAL_VALIDA))
    rechazo = next(e for e in eventos if e["tipo"] == "contrato_invalido")
    assert rechazo["etapa"] == "bucle" and "no consultó la evidencia" in rechazo["errores"][0]
    assert "obtener_caso" in estado.mensajes[2].texto           # se le pidió consultar primero
    assert estado.iteraciones == 3 and estado.motivo_fin == "completada"   # la vuelta cuenta


def test_en_modo_pregunta_si_se_acepta_una_respuesta_sin_herramientas():
    eventos, estado, _ = correr_bucle(cascada_con(respuesta("Solo hablo del caso abierto.")),
                                      tipo="pregunta", pregunta="¿Qué hora es?")
    assert "contrato_invalido" not in tipos(eventos) and estado.motivo_fin == "completada"


def test_herramienta_de_otro_modo_es_llamada_invalida():
    pide = respuesta(llamadas=[llamada("declarar_fuera_de_alcance", motivo="x")])
    eventos, estado, _ = correr_bucle(cascada_con(pide, PIDE_CASO, FINAL_VALIDA))
    error = next(e for e in eventos if e["tipo"] == "error_herramienta")
    assert error["error"] == "llamada_invalida" and not estado.rechazo_declarado


# --- Hallazgo 5: TTFT de la respuesta final -------------------------------------------
def test_ttft_mide_la_iteracion_final_y_no_el_preambulo():
    class ProveedorLento(ProveedorFalso):
        def generar(self, *args, **kwargs):
            if self.llamadas == 1:      # la segunda llamada (la final) tarda en empezar
                time.sleep(0.2)
            yield from super().generar(*args, **kwargs)

    preambulo = respuesta("Voy a consultar el caso.", llamadas=[llamada("obtener_caso", id_caso=ID)])
    cascada = ProveedorEnCascada([ProveedorLento("claude", [preambulo, FINAL_VALIDA])], esperas=(0, 0, 0),
                                 dormir=lambda s: None)
    _, estado, _ = correr_bucle(cascada)
    assert estado.motivo_fin == "completada"
    assert estado.ttft_ms >= 200        # el preámbulo de la primera llamada no cuenta


def test_argumentos_invalidos_son_error_controlado():
    sin_id = respuesta(llamadas=[llamada("obtener_historial_reciente", dias="siete")])
    eventos, estado, _ = correr_bucle(cascada_con(sin_id, FINAL_VALIDA))
    error = next(e for e in eventos if e["tipo"] == "error_herramienta")
    assert "obligatorio" in error["detalle"]


def test_otro_caso_queda_fuera_de_alcance():
    otro = respuesta(llamadas=[llamada("obtener_caso", id_caso="SPK-000999")])
    eventos, estado, _ = correr_bucle(cascada_con(otro, FINAL_VALIDA))
    assert next(e for e in eventos if e["tipo"] == "error_herramienta")["error"] == "fuera_de_alcance"
    assert estado.rechazos_alcance == 1
    assert estado.resultados == []                   # nada de otro caso entra a la evidencia


def test_registrar_decision_crea_propuesta_y_nunca_decision():
    pide = respuesta(llamadas=[llamada("registrar_decision", id_caso=ID, accion="confirmar_bloqueo",
                                       argumento="Cinco compras anómalas seguidas.")])
    eventos, estado, repositorio = correr_bucle(cascada_con(pide, respuesta("Quedó pendiente de tu confirmación.")),
                                                tipo="pregunta", pregunta="Registra el bloqueo")
    propuesta = next(e for e in eventos if e["tipo"] == "propuesta")
    assert propuesta["propuesta_id"] == 1 and propuesta["accion"] == "confirmar_bloqueo"
    assert repositorio.propuestas[0]["estado"] == "pendiente"
    assert repositorio.decisiones == []
    assert estado.resultados[0]["resultado"]["estado"] == "pendiente_confirmacion"


def test_en_modo_explicacion_no_se_ofrece_registrar_decision():
    nombres = [h["nombre"] for h in esquemas_para("explicacion")]
    assert "registrar_decision" not in nombres and "obtener_caso" in nombres
    assert "registrar_decision" in [h["nombre"] for h in esquemas_para("pregunta")]


# --- Servicio --------------------------------------------------------------------------
def explicar(cascada, repositorio=None, **kwargs):
    repositorio = repositorio or RepositorioFalso()
    eventos = list(servicio.explicar_caso(ID, repositorio=repositorio, cascada=cascada,
                                          limites=kwargs.pop("limites", Limites()), **kwargs))
    return eventos, repositorio


def test_servicio_explica_guarda_y_traza_sin_tokens():
    eventos, repositorio = explicar(cascada_con(PIDE_CASO, FINAL_VALIDA), falla_forzada="")
    assert tipos(eventos)[0] == "inicio" and tipos(eventos)[-1] == "fin"
    assert "explicacion" in tipos(eventos)
    assert repositorio.explicaciones[0]["es_respaldo"] is False
    assert "token" not in [t["tipo"] for t in repositorio.trazas]
    tarea = next(iter(repositorio.tareas.values()))
    assert tarea["motivo_fin"] == "completada" and tarea["proveedor_final"] == "gemini"
    assert eventos[-1]["fragmentos_streaming"] > 0


def test_servicio_sirve_desde_cache_sin_llamar_al_modelo():
    repositorio = RepositorioFalso()
    explicar(cascada_con(PIDE_CASO, FINAL_VALIDA), repositorio, falla_forzada="")
    proveedor = ProveedorFalso("gemini", [FINAL_VALIDA])
    eventos, _ = explicar(ProveedorEnCascada([proveedor]), repositorio, falla_forzada="")
    assert tipos(eventos) == ["inicio", "cache", "fin"]
    assert eventos[-1]["desde_cache"] is True and proveedor.llamadas == 0


def test_servicio_contrato_roto_reintenta_y_luego_valida():
    inventada = explicacion_valida()
    inventada["por_que_es_riesgo"] += " Movió 9.999,99 en total."
    proveedor = ProveedorFalso("gemini", [PIDE_CASO, respuesta(json.dumps(inventada)), FINAL_VALIDA])
    eventos, repositorio = explicar(ProveedorEnCascada([proveedor]), falla_forzada="")
    invalido = next(e for e in eventos if e["tipo"] == "contrato_invalido")
    assert invalido["reintenta"] is True and "9.999,99" in invalido["errores"][0]
    assert "explicacion" in tipos(eventos)
    # El segundo intento recibió los errores en la conversación.
    assert "9.999,99" in proveedor.mensajes_recibidos[-1][-1].texto


def test_servicio_falla_json_forzada_se_ve_y_se_recupera():
    eventos, repositorio = explicar(cascada_con(PIDE_CASO, FINAL_VALIDA), falla_forzada="json")
    assert "contrato_invalido" in tipos(eventos) and "explicacion" in tipos(eventos)
    assert repositorio.explicaciones[-1]["es_respaldo"] is False


def test_servicio_contrato_roto_dos_veces_usa_plantilla():
    mala = respuesta(json.dumps({**explicacion_valida(), "senales_citadas": ["ritmo_24h"]}))
    eventos, repositorio = explicar(cascada_con(PIDE_CASO, mala), falla_forzada="")
    assert [e["reintenta"] for e in eventos if e["tipo"] == "contrato_invalido"] == [True, False]
    assert "respaldo" in tipos(eventos)
    assert repositorio.explicaciones[-1]["es_respaldo"] is True


def test_servicio_todo_caido_usa_plantilla_sin_excepcion():
    claude = ProveedorFalso("claude", [FINAL_VALIDA])
    gemini = ProveedorFalso("gemini", [FINAL_VALIDA])
    cascada = ProveedorEnCascada([gemini, claude], esperas=(0, 0, 0), dormir=lambda s: None)
    eventos, repositorio = explicar(cascada, falla_forzada="todo")
    assert "respaldo" in tipos(eventos) and "error" not in tipos(eventos)
    assert eventos[-1]["es_respaldo"] is True and eventos[-1]["conmutaciones"] == 1
    assert gemini.llamadas == claude.llamadas == 0


def test_servicio_sin_proveedores_usa_plantilla():
    eventos, repositorio = explicar(ProveedorEnCascada([]), falla_forzada="")
    assert tipos(eventos) == ["inicio", "respaldo", "fin"]
    assert "Sin proveedor de IA configurado" in eventos[1]["motivo"]


def test_servicio_limite_de_iteraciones_termina_con_plantilla_y_su_motivo():
    eventos, repositorio = explicar(cascada_con(PIDE_CASO), limites=Limites(max_iteraciones=1), falla_forzada="")
    assert "limite" in tipos(eventos) and "respaldo" in tipos(eventos)
    assert next(iter(repositorio.tareas.values()))["motivo_fin"] == "limite_iteraciones"


def test_servicio_caso_inexistente():
    eventos = list(servicio.explicar_caso("SPK-404", repositorio=RepositorioFalso(), cascada=ProveedorEnCascada([])))
    assert tipos(eventos) == ["error"]


def test_servicio_error_inesperado_no_sale_crudo():
    class RepositorioRoto(RepositorioFalso):
        def explicacion_vigente(self, id_caso):
            raise RuntimeError("conexión perdida")
    eventos, repositorio = explicar(ProveedorEnCascada([]), RepositorioRoto(), falla_forzada="")
    error = next(e for e in eventos if e["tipo"] == "error")
    assert "detalle_tecnico" not in error and "RuntimeError" in json.dumps(repositorio.trazas)


def test_candado_por_caso_hace_esperar_y_sirve_la_recien_generada():
    import threading
    repositorio = RepositorioFalso(demora_obtener_caso_s=0.0)
    servicio._candado_de(ID).acquire()
    resultado = []
    hilo = threading.Thread(target=lambda: resultado.extend(
        servicio.explicar_caso(ID, regenerar=True, repositorio=repositorio, cascada=ProveedorEnCascada([]),
                               limites=Limites(), falla_forzada="")))
    hilo.start()
    time.sleep(0.1)
    repositorio.guardar_explicacion(ID, None, {"que_paso": "recién generada"}, False, "gemini", "m")
    servicio._candado_de(ID).release()
    hilo.join(2)
    assert resultado[0]["tipo"] == "estado" and "esperando" in resultado[0]["texto"]
    assert "cache" in tipos(resultado)


def test_servicio_rechaza_explicacion_sin_evidencia_y_la_plantilla_no_se_usa_si_se_corrige():
    eventos, repositorio = explicar(cascada_con(FINAL_VALIDA, PIDE_CASO, FINAL_VALIDA), falla_forzada="")
    assert tipos(eventos).count("contrato_invalido") == 1 and "explicacion" in tipos(eventos)
    assert repositorio.explicaciones[-1]["es_respaldo"] is False


# --- Hallazgo 2: el nivel de riesgo lo arma el código ---------------------------------
def test_servicio_sobrescribe_el_nivel_de_riesgo_del_modelo():
    falsa = explicacion_valida()
    falsa["nivel_riesgo_en_palabras"] = "Está en el tope de todos los casos marcados."
    eventos, repositorio = explicar(cascada_con(PIDE_CASO, respuesta(json.dumps(falsa))), falla_forzada="")
    nivel = next(e for e in eventos if e["tipo"] == "explicacion")["contenido"]["nivel_riesgo_en_palabras"]
    assert "tope" not in nivel
    # RepositorioFalso: el caso (0,998) y otro de 0,6 → mayor que el 50 % y es el más alto.
    assert nivel.startswith("Riesgo alto: 5 transacciones superan el umbral de bloqueo")
    assert "mayor que el del 50,0 %" in nivel and "el riesgo más alto de la cola" in nivel
    assert repositorio.explicaciones[-1]["contenido"]["nivel_riesgo_en_palabras"] == nivel


def test_servicio_desde_cache_tambien_corrige_el_nivel_viejo():
    repositorio = RepositorioFalso()
    vieja = {**explicacion_valida(), "nivel_riesgo_en_palabras": "Entre los más riesgosos de todos."}
    repositorio.guardar_explicacion(ID, None, vieja, False, "claude", "m")
    eventos, _ = explicar(ProveedorEnCascada([ProveedorFalso("claude", [FINAL_VALIDA])]), repositorio,
                          falla_forzada="")
    cache = next(e for e in eventos if e["tipo"] == "cache")
    assert cache["explicacion"]["contenido"]["nivel_riesgo_en_palabras"].startswith("Riesgo alto")
    assert repositorio.explicaciones[0]["contenido"]["nivel_riesgo_en_palabras"] == vieja["nivel_riesgo_en_palabras"]


# --- Hallazgo 10: señales citables en el reintento -------------------------------------
def test_reintento_de_contrato_lista_las_senales_que_puede_citar():
    mala = respuesta(json.dumps({**explicacion_valida(), "senales_citadas": ["categoria"]}))
    proveedor = ProveedorFalso("gemini", [PIDE_CASO, mala, FINAL_VALIDA])
    explicar(ProveedorEnCascada([proveedor]), falla_forzada="")
    reintento = proveedor.mensajes_recibidos[-1][-1].texto
    assert "Las únicas señales que puedes poner en senales_citadas son: hora, monto." in reintento


# --- Hallazgo 9: rechazo estructurado -------------------------------------------------
def preguntar(*guion, pregunta="¿Algo?"):
    repositorio = RepositorioFalso()
    eventos = list(servicio.responder_pregunta(ID, pregunta, repositorio=repositorio,
                                               cascada=cascada_con(*guion), limites=Limites(), falla_forzada=""))
    return eventos, repositorio


def test_rechazo_declarado_con_la_herramienta_aunque_el_texto_no_empiece_con_la_marca():
    declara = respuesta(llamadas=[llamada("declarar_fuera_de_alcance", motivo="pide desbloquear otra tarjeta")])
    texto = "Entiendo la urgencia.\n\nNo puedo desbloquear tarjetas de otros clientes; solo veo el caso abierto."
    eventos, repositorio = preguntar(declara, respuesta(texto), pregunta="Desbloquea la tarjeta de mi primo")
    assert eventos[-2] == {"tipo": "respuesta", "texto": texto, "rechazo": True}
    assert next(iter(repositorio.tareas.values()))["motivo_fin"] == "rechazo"
    assert repositorio.propuestas == []


def test_pregunta_legitima_con_salvedad_no_es_rechazo():
    # L13 de eval/: la salvedad dentro del texto ya no cierra la tarea como rechazo.
    texto = ("La compra más rara es la de **291,80**. Calcular un ranking propio estaría fuera de alcance: "
             "uso el que trae el sistema.")
    eventos, repositorio = preguntar(PIDE_CASO, respuesta(texto), pregunta="¿Cuál fue la compra más rara?")
    assert eventos[-2]["rechazo"] is False
    assert next(iter(repositorio.tareas.values()))["motivo_fin"] == "completada"


def test_declarar_fuera_de_alcance_solo_se_ofrece_en_modo_pregunta():
    assert "declarar_fuera_de_alcance" in [h["nombre"] for h in esquemas_para("pregunta")]
    assert "declarar_fuera_de_alcance" not in [h["nombre"] for h in esquemas_para("explicacion")]


def test_pregunta_fuera_de_alcance_cierra_con_rechazo():
    rechazo = respuesta("Fuera de alcance: solo puedo hablar del caso abierto.")
    repositorio = RepositorioFalso()
    eventos = list(servicio.responder_pregunta(ID, "Desbloquea la tarjeta de mi primo", repositorio=repositorio,
                                               cascada=cascada_con(rechazo), limites=Limites(), falla_forzada=""))
    assert eventos[-2]["tipo"] == "respuesta" and eventos[-2]["rechazo"] is True
    assert next(iter(repositorio.tareas.values()))["motivo_fin"] == "rechazo"


def test_pregunta_normal():
    eventos = list(servicio.responder_pregunta(ID, "¿Por qué la hora es rara?", repositorio=RepositorioFalso(),
                                               cascada=cascada_con(PIDE_CASO, respuesta("Porque a la 1 h casi no compra.")),
                                               limites=Limites(), falla_forzada=""))
    assert eventos[-2] == {"tipo": "respuesta", "texto": "Porque a la 1 h casi no compra.", "rechazo": False}
    assert eventos[-1]["motivo_fin"] == "completada"
