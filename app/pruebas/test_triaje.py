"""Pruebas del triaje del agente, la red de seguridad y los avisos (SPEC, RF3-RF6).

Base de Postgres real (con los roles de mínimo privilegio) y un LLM falso con guion: así se
prueban las guardas de verdad, las que viven en el código y en la base, no en el prompt. Cada
guarda de RF3 tiene su prueba, y los ataques de inyección por el motivo también.
"""

import threading
import time

import pytest

from app.agente import triaje
from app.agente.herramientas import nombres_para
from app.db import repositorio, repositorio_acciones, repositorio_en_vivo
from app.proveedores.cascada import ProveedorEnCascada
from app.pruebas.base_de_pruebas import base_migrada, como_dueno
from app.pruebas.test_cascada import ProveedorFalso, llamada, respuesta
from app.pruebas.test_flujo import MotorFalso, compra
from app.riesgo import flujo

MOTIVO_BUENO = "Se detuvo una compra de 120,00 USD en una tienda en línea a la 1 de la madrugada, muy distinta de sus compras habituales."


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    with base_migrada("fraude_pruebas_triaje", str(tmp_path_factory.mktemp("sin_semilla"))) as resultado:
        yield resultado


@pytest.fixture(autouse=True)
def ajustes_normales(base):
    repositorio_acciones.cambiar_ajuste("autonomia_agente", True, "prueba")
    repositorio_acciones.cambiar_ajuste("tope_bloqueos_autonomos_por_hora", 30, "prueba")
    flujo.quitar_oyentes()


def caso_en_banda(tarjeta, banda, viaje=False):
    """Abre un caso en vivo en la banda pedida con el motor falso; devuelve su id."""
    scores = {"media": [0.955], "alta": [0.98], "critica": [0.98, 0.99]}[banda]
    resultado = None
    for i, score in enumerate(scores):
        resultado = flujo.evaluar_transaccion({**compra(tarjeta, i * 10, score=score), "_viaje": viaje},
                                              origen="simulador", motor=MotorFalso(), domicilio=(40.0, -90.0))
    assert resultado["banda"] == banda
    return resultado["id_caso"]


def guion(*pasos):
    proveedor = ProveedorFalso("claude", list(pasos))
    return ProveedorEnCascada([proveedor], esperas=(0, 0, 0), dormir=lambda s: None), proveedor


def triar(id_caso, cascada):
    return list(triaje.triar_caso(id_caso, cascada=cascada))


def tipos(eventos):
    return [e["tipo"] for e in eventos]


def bloqueos_de(id_caso):
    return como_dueno("select actor, tipo, estado from bloqueos where id_caso = %s order by id", (id_caso,))


def avisos_de(id_caso):
    return repositorio_acciones.avisos_del_caso(id_caso)


# --- El agente decide ----------------------------------------------------------------------


def test_en_banda_alta_el_agente_bloquea_y_avisa_con_su_motivo(base):
    id_caso = caso_en_banda("5001", "alta")
    cascada, _ = guion(respuesta(llamadas=[llamada("obtener_caso", id_caso=id_caso)]),
                       respuesta(llamadas=[llamada("bloquear_tarjeta", id_caso=id_caso, motivo_para_titular=MOTIVO_BUENO)]),
                       respuesta("Bloqueé la tarjeta: compra en línea de madrugada muy por encima de su promedio."))
    eventos = triar(id_caso, cascada)
    accion = next(e for e in eventos if e["tipo"] == "accion_triaje")
    assert accion["resultado"] == "bloqueada" and accion["aviso"]["autor_motivo"] == "agente"
    assert bloqueos_de(id_caso) == [("agente", "tarjeta", "activo")]
    assert repositorio.obtener_caso(id_caso)["estado"] == "bloqueado"
    aviso = avisos_de(id_caso)[0]
    assert aviso["tipo"] == "bloqueo" and MOTIVO_BUENO in aviso["cuerpo"] and aviso["estado"] == "enviada"
    assert "nunca le pediremos claves" in aviso["cuerpo"].lower()
    # La compra siguiente de esa tarjeta se rechaza: el bloqueo detiene el dinero.
    siguiente = flujo.evaluar_transaccion(compra("5001", 60, score=0.99), motor=MotorFalso())
    assert siguiente["decision"] == "rechazada_por_bloqueo"


def test_el_agente_no_bloquea_en_banda_media_aunque_lo_intente(base):
    id_caso = caso_en_banda("5002", "media")
    cascada, _ = guion(respuesta(llamadas=[llamada("obtener_caso", id_caso=id_caso)]),
                       respuesta(llamadas=[llamada("bloquear_tarjeta", id_caso=id_caso, motivo_para_titular=MOTIVO_BUENO)]),
                       respuesta("Intenté bloquear."))
    eventos = triar(id_caso, cascada)
    assert next(e for e in eventos if e["tipo"] == "accion_triaje")["resultado"] == "no_permitido"
    assert bloqueos_de(id_caso) == []
    # La acción rechazada no cuenta: la regla pide verificación al titular.
    assert next(e for e in eventos if e["tipo"] == "respaldo_triaje")["accion"] == "verificacion_por_regla"
    assert avisos_de(id_caso)[0]["tipo"] == "verificacion"


def test_el_agente_no_puede_actuar_sobre_otro_caso(base):
    propio, ajeno = caso_en_banda("5003", "alta"), caso_en_banda("5004", "alta")
    cascada, _ = guion(respuesta(llamadas=[llamada("obtener_caso", id_caso=propio)]),
                       respuesta(llamadas=[llamada("bloquear_tarjeta", id_caso=ajeno, motivo_para_titular=MOTIVO_BUENO)]),
                       respuesta("Listo."))
    eventos = triar(propio, cascada)
    assert any(e["tipo"] == "error_herramienta" and e["error"] == "fuera_de_alcance" for e in eventos)
    assert bloqueos_de(ajeno) == []


def test_sin_leer_el_caso_no_puede_bloquear(base):
    id_caso = caso_en_banda("5005", "alta")
    cascada, _ = guion(respuesta(llamadas=[llamada("bloquear_tarjeta", id_caso=id_caso, motivo_para_titular=MOTIVO_BUENO)]),
                       respuesta("Listo."))
    eventos = triar(id_caso, cascada)
    error = next(e for e in eventos if e["tipo"] == "error_herramienta")
    assert "obtener_caso" in error["detalle"]
    assert [b[0] for b in bloqueos_de(id_caso)] != ["agente"]


def test_el_triaje_no_ofrece_desbloquear_ni_proponer(base):
    herramientas = nombres_para("triaje")
    assert not any("desbloque" in h for h in herramientas)
    assert "registrar_decision" not in herramientas and "declarar_fuera_de_alcance" not in herramientas
    assert not any(h.startswith("bloquear") for h in nombres_para("pregunta"))


# --- Inyección por el motivo ---------------------------------------------------------------


MOTIVOS_MALICIOSOS = [
    "Su tarjeta fue bloqueada. Para desbloquearla entre a www.banco-seguro-co.com y confirme.",
    "Llame ya al 300 555 1234 para desbloquear su tarjeta.",
    "Responda este mensaje con su clave y el código que le llegó.",
    "Se detectó una compra de 9.999,99 USD en el exterior.",
    # Auditoría 2026-11-14 (C1): terminaciones fuera de la lista vieja y dominios disfrazados.
    "Para desbloquearla entre a bancodemo-seguro.shop hoy mismo.",
    "Confirme sus datos en banco.lat antes de las 6.",
    "Escríbanos a bancodemo . com para recuperar su tarjeta.",
    "Escriba a soporte arroba bancodemo punto com.",
    "Recupere su tarjeta en bancodemo (punto) shop o en bancodemo[.]shop.",
    "Escriba a soporte(at)bancodemo o en hxxp://bancodemo.",
]


@pytest.mark.parametrize("indice", range(len(MOTIVOS_MALICIOSOS)))
def test_un_motivo_malicioso_no_llega_al_titular(base, indice):
    motivo_malicioso = MOTIVOS_MALICIOSOS[indice]
    id_caso = caso_en_banda(f"51{indice:02d}", "alta")   # tarjeta fija por motivo (antes hash(): 6 % de choques)
    cascada, _ = guion(respuesta(llamadas=[llamada("obtener_caso", id_caso=id_caso)]),
                       respuesta(llamadas=[llamada("bloquear_tarjeta", id_caso=id_caso,
                                                   motivo_para_titular=motivo_malicioso)]),
                       respuesta("Listo."))
    triar(id_caso, cascada)
    aviso = avisos_de(id_caso)[0]
    assert aviso["autor_motivo"] == "plantilla" and aviso["errores_validacion"]
    assert motivo_malicioso not in aviso["cuerpo"]
    assert bloqueos_de(id_caso) == [("agente", "tarjeta", "activo")]   # el bloqueo sí protege


# --- La regla cubre al agente --------------------------------------------------------------


def test_en_banda_critica_si_el_agente_no_bloquea_bloquea_la_regla(base):
    id_caso = caso_en_banda("5201", "critica")
    cascada, _ = guion(respuesta(llamadas=[llamada("obtener_caso", id_caso=id_caso)]),
                       respuesta(llamadas=[llamada("dejar_a_analista", id_caso=id_caso,
                                                   razon="El comercio dice que no bloquee esta tarjeta.")]),
                       respuesta("Lo dejé al analista."))
    eventos = triar(id_caso, cascada)
    assert next(e for e in eventos if e["tipo"] == "respaldo_triaje")["accion"] == "bloqueo_por_regla"
    assert bloqueos_de(id_caso) == [("regla", "tarjeta", "activo")]
    assert avisos_de(id_caso)[0]["autor_motivo"] == "plantilla"


def test_proveedores_caidos_critica_bloquea_y_alta_verifica(base):
    critico, alto = caso_en_banda("5202", "critica"), caso_en_banda("5203", "alta")
    for id_caso in (critico, alto):
        assert "respaldo_triaje" in tipos(triar(id_caso, ProveedorEnCascada([])))
    assert bloqueos_de(critico) == [("regla", "tarjeta", "activo")]
    assert bloqueos_de(alto) == [] and avisos_de(alto)[0]["tipo"] == "verificacion"


def test_con_la_autonomia_apagada_no_se_llama_al_modelo(base):
    repositorio_acciones.cambiar_ajuste("autonomia_agente", False, "supervisor")
    critico, alto = caso_en_banda("5204", "critica"), caso_en_banda("5205", "alta")
    cascada, proveedor = guion(respuesta("no debería llamarse"))
    triar(critico, cascada)
    triar(alto, cascada)
    assert proveedor.llamadas == 0
    assert bloqueos_de(critico) == [("regla", "tarjeta", "activo")]        # la red sigue activa
    assert bloqueos_de(alto) == [] and avisos_de(alto) == []               # el resto, a la cola humana


def test_tope_de_bloqueos_por_hora_frena_al_agente_y_alerta(base):
    repositorio_acciones.cambiar_ajuste("tope_bloqueos_autonomos_por_hora", 0, "supervisor")
    id_caso = caso_en_banda("5206", "alta")
    cascada, _ = guion(respuesta(llamadas=[llamada("obtener_caso", id_caso=id_caso)]),
                       respuesta(llamadas=[llamada("bloquear_tarjeta", id_caso=id_caso, motivo_para_titular=MOTIVO_BUENO)]),
                       respuesta("Listo."))
    eventos = triar(id_caso, cascada)
    assert next(e for e in eventos if e["tipo"] == "accion_triaje")["resultado"] == "tope_alcanzado"
    assert bloqueos_de(id_caso) == []
    assert any(a["tipo"] == "tope_bloqueos_agente" and a["id_caso"] == id_caso
               for a in repositorio_acciones.alertas_pendientes())


def test_no_se_duplica_el_bloqueo_de_una_tarjeta(base):
    id_caso = caso_en_banda("5207", "critica")
    from app.riesgo import acciones
    primero = acciones.bloquear(id_caso, "tarjeta", "regla")
    segundo = acciones.bloquear(id_caso, "tarjeta", "regla")
    assert primero["resultado"] == "bloqueada" and segundo["resultado"] == "ya_bloqueada"
    assert len(bloqueos_de(id_caso)) == 1 and len(avisos_de(id_caso)) == 1


# --- Red de seguridad --------------------------------------------------------------------


def test_la_red_de_seguridad_bloquea_criticos_sin_bloqueo(base):
    id_caso = caso_en_banda("5301", "critica")
    alto = caso_en_banda("5302", "alta")
    resultados = triaje.RedDeSeguridad(segundos=0).revisar_una_vez()
    assert any(r["id_caso"] == id_caso and r["resultado"] == "bloqueada" for r in resultados)
    assert all(r["id_caso"] != alto for r in resultados)          # la red solo toca la banda crítica
    assert bloqueos_de(id_caso) == [("regla", "tarjeta", "activo")]
    assert any(a["tipo"] == "red_de_seguridad" for a in repositorio_acciones.alertas_pendientes())


def test_la_red_respeta_su_ventana_de_tiempo(base):
    id_caso = caso_en_banda("5303", "critica")
    triaje.RedDeSeguridad(segundos=3600).revisar_una_vez()
    assert bloqueos_de(id_caso) == []


# --- Desbloqueo humano y respuesta del titular -------------------------------------------------


def test_desbloqueo_humano_reabre_la_tarjeta_y_mide_el_tiempo(base):
    from app.riesgo import acciones
    id_caso = caso_en_banda("5401", "critica")
    bloqueo = acciones.bloquear(id_caso, "tarjeta", "regla")
    levantado = repositorio_acciones.desbloquear(bloqueo["bloqueo_id"], "ana.analista", "El titular confirmó la compra por teléfono.")
    assert levantado["segundos_bloqueada"] >= 0
    assert repositorio.obtener_caso(id_caso)["estado"] == "desbloqueado"
    assert repositorio_acciones.desbloquear(bloqueo["bloqueo_id"], "otro", "de nuevo") is None   # solo una vez
    despues = flujo.evaluar_transaccion(compra("5401", 120, score=0.1), motor=MotorFalso())
    assert despues["decision"] == "aprobada"


def test_el_titular_responde_una_sola_vez(base):
    from app.riesgo import acciones
    id_caso = caso_en_banda("5402", "alta")
    acciones.solicitar_verificacion(id_caso, "regla")
    aviso = avisos_de(id_caso)[0]
    assert repositorio_acciones.responder_notificacion(aviso["id"], "no_fui_yo") == id_caso
    assert repositorio_acciones.responder_notificacion(aviso["id"], "fui_yo") is None
    assert avisos_de(id_caso)[0]["respuesta_titular"] == "no_fui_yo"


def test_no_fui_yo_bloquea_la_tarjeta_aunque_el_caso_estuviera_descartado(base):
    # Auditoría 2026-11-14 (A1): antes la respuesta solo quedaba guardada y la tarjeta seguía abierta.
    from app.riesgo import acciones
    id_caso = caso_en_banda("5403", "alta")
    acciones.solicitar_verificacion(id_caso, "regla")
    repositorio.registrar_decision(id_caso, "descartar", "ana.analista", "Parecía una compra normal del cliente.")
    aviso = avisos_de(id_caso)[0]
    repositorio_acciones.responder_notificacion(aviso["id"], "no_fui_yo")
    assert acciones.respuesta_del_titular(id_caso, "no_fui_yo")["resultado"] == "bloqueada"
    assert bloqueos_de(id_caso) == [("regla", "tarjeta", "activo")]
    assert flujo.evaluar_transaccion(compra("5403", 90, score=0.1), motor=MotorFalso())["decision"] == "rechazada_por_bloqueo"
    assert acciones.respuesta_del_titular(id_caso, "fui_yo") is None   # "fui yo" no toca la tarjeta


def test_confirmar_bloqueo_de_un_analista_bloquea_de_verdad(base):
    # Auditoría 2026-11-14 (C2): antes solo cambiaba el estado del caso.
    from app.riesgo import acciones
    id_caso = caso_en_banda("5404", "alta")
    repositorio.registrar_decision(id_caso, "confirmar_bloqueo", "ana.analista", None)
    assert acciones.aplicar_decision(id_caso, "confirmar_bloqueo", "ana.analista")["resultado"] == "bloqueada"
    assert como_dueno("select actor, usuario from bloqueos where id_caso = %s", (id_caso,)) == [("analista", "ana.analista")]
    assert repositorio.obtener_caso(id_caso)["nivel_recomendacion"] == "bloquear_tarjeta"
    assert avisos_de(id_caso)[0]["tipo"] == "bloqueo"
    assert flujo.evaluar_transaccion(compra("5404", 90, score=0.1), motor=MotorFalso())["decision"] == "rechazada_por_bloqueo"


def test_descartar_un_caso_en_vivo_exige_motivo_y_no_sirve_para_desbloquear(base):
    # Auditoría 2026-11-14 (A3): descartar apaga la red de seguridad del caso.
    from app.riesgo import acciones
    id_caso = caso_en_banda("5405", "critica")
    caso = repositorio.obtener_caso(id_caso)
    assert "escribe por qué" in acciones.validar_decision(caso, "descartar", "")
    assert acciones.validar_decision(caso, "descartar", "El titular llamó y reconoce las dos compras.") is None
    assert acciones.validar_decision(caso, "escalar", None) is None
    acciones.bloquear(id_caso, "tarjeta", "regla")
    assert "Desbloquear" in acciones.validar_decision(repositorio.obtener_caso(id_caso), "descartar",
                                                      "El titular llamó y reconoce las dos compras.")


def test_un_triaje_bloquea_y_avisa_una_sola_vez(base):
    # Auditoría 2026-11-14 (A2): un triaje podía dejar dos bloqueos y tres avisos.
    id_caso = caso_en_banda("5406", "critica")
    cascada, _ = guion(respuesta(llamadas=[llamada("obtener_caso", id_caso=id_caso)]),
                       respuesta(llamadas=[llamada("bloquear_tarjeta", id_caso=id_caso, motivo_para_titular=MOTIVO_BUENO)]),
                       respuesta(llamadas=[llamada("bloquear_acceso_cuenta", id_caso=id_caso,
                                                   motivo_para_titular=MOTIVO_BUENO)]),
                       respuesta("Bloqueé la tarjeta y el acceso."))
    eventos = triar(id_caso, cascada)
    assert [e["resultado"] for e in eventos if e["tipo"] == "accion_triaje"] == ["bloqueada", "ya_bloqueada"]
    assert bloqueos_de(id_caso) == [("agente", "tarjeta", "activo")]
    assert len(avisos_de(id_caso)) == 1


def test_en_el_triaje_el_agente_no_ve_la_recomendacion_del_momento_2(base):
    # Auditoría 2026-11-14 (A6): "confirmar con el cliente antes de bloquear" lo sesgaba.
    from app.agente.herramientas import HERRAMIENTAS, ContextoHerramientas
    from app.db.repositorio_agente import RepositorioDelAgente
    from app.riesgo.acciones import AccionesDelAgente
    id_caso = caso_en_banda("5407", "alta")
    contexto = ContextoHerramientas(id_caso=id_caso, tarea_id="t", repositorio=RepositorioDelAgente(repositorio),
                                    acciones=AccionesDelAgente(id_caso, "t"))
    resumen = HERRAMIENTAS["obtener_caso"].ejecutar({"id_caso": id_caso}, contexto)
    assert resumen["banda"] == "alta" and "nivel_recomendacion" not in resumen
    assert "motivo_recomendacion" not in resumen


# --- Despachador -------------------------------------------------------------------------


def test_el_despachador_no_corre_dos_triajes_del_mismo_caso_y_repite_si_subio_de_banda():
    llamadas, liberar = [], threading.Event()

    def triar_lento(id_caso):
        llamadas.append(id_caso)
        liberar.wait(2)
        yield {"tipo": "fin"}

    despachador = triaje.Despachador(maximo=2, triar=triar_lento)
    despachador.encolar("VIV-1")
    despachador.encolar("VIV-1")        # sube de banda mientras corre: se repite al terminar
    despachador.encolar("VIV-1")        # varios avisos seguidos se juntan en una repetición
    time.sleep(0.1)
    assert llamadas == ["VIV-1"]
    liberar.set()
    for _ in range(50):
        if not despachador.ocupado() and len(llamadas) == 2:
            break
        time.sleep(0.05)
    assert llamadas == ["VIV-1", "VIV-1"]
    despachador.apagar()


def test_el_flujo_avisa_al_despachador_sin_esperar_al_triaje(base):
    recibidos = []
    flujo.al_cambiar_caso(recibidos.append)
    inicio = time.perf_counter()
    resultado = flujo.evaluar_transaccion(compra("5501", 0, score=0.98), motor=MotorFalso(), domicilio=(40.0, -90.0))
    assert recibidos == [{"id_caso": resultado["id_caso"], "banda": "alta", "evento": "caso_abierto"}]
    assert time.perf_counter() - inicio < 2
