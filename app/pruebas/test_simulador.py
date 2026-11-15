"""Pruebas del simulador en vivo (SPEC, RF8) con la semilla real y un flujo falso.

El reloj es real pero la velocidad máxima hace que la noche entera pase en segundos; el flujo
falso cuenta lo que recibe, así que se prueba el recorrido completo sin base ni modelo.
"""

import time

import pytest

from app import config
from app.riesgo.simulador import VELOCIDADES, Simulador


class FlujoFalso:
    def __init__(self, rechazar_desde=None):
        self.recibidas = []
        self.rechazar_desde = rechazar_desde

    def __call__(self, transaccion, origen, etiqueta):
        self.recibidas.append((transaccion, origen, etiqueta))
        n = len(self.recibidas)
        decision = "rechazada_por_bloqueo" if self.rechazar_desde and n >= self.rechazar_desde else "aprobada"
        return {"decision": decision, "evento": "caso_abierto" if n == 3 else None}


def esperar(simulador, estados=("terminado", "detenido"), maximo_s=60):
    limite = time.monotonic() + maximo_s
    while simulador.estado not in estados and time.monotonic() < limite:
        time.sleep(0.05)
    return simulador.estado


@pytest.fixture
def sin_esperas():
    """Simulador que no duerme: el reloj real avanza solo, la velocidad hace el resto."""
    return lambda flujo: Simulador(config.CARPETA_SEMILLA, evaluar=flujo, dormir=lambda s: None)


def test_reproduce_toda_la_noche_en_orden_con_etiqueta_y_origen(sin_esperas):
    flujo = FlujoFalso()
    simulador = sin_esperas(flujo)
    simulador.iniciar(max(VELOCIDADES))
    simulador.velocidad = 10 ** 9            # sin esperas reales para la prueba
    simulador._recalibrar = True
    assert esperar(simulador) == "terminado"
    resumen = simulador.resumen()
    assert resumen["procesadas"] == resumen["total"] == len(flujo.recibidas) > 5000
    fechas = [t["fecha_hora"] for t, _, _ in flujo.recibidas]
    assert fechas == sorted(fechas)
    assert {origen for _, origen, _ in flujo.recibidas} == {"simulador"}
    assert sum(etiqueta for _, _, etiqueta in flujo.recibidas) == 54        # las compras fraudulentas de la ventana
    assert all("es_fraude" not in t for t, _, _ in flujo.recibidas)        # la etiqueta no va dentro de la compra


def test_cuenta_rechazos_y_casos(sin_esperas):
    simulador = sin_esperas(FlujoFalso(rechazar_desde=5000))
    simulador.iniciar(max(VELOCIDADES))
    simulador.velocidad = 10 ** 9
    simulador._recalibrar = True
    esperar(simulador)
    resumen = simulador.resumen()
    assert resumen["rechazadas"] == resumen["total"] - 4999 and resumen["monto_rechazado"] > 0
    assert resumen["casos_abiertos"] == 1


def test_pausar_reanudar_y_detener():
    flujo = FlujoFalso()
    simulador = Simulador(config.CARPETA_SEMILLA, evaluar=flujo)
    simulador.iniciar(60)                     # a 60x la noche dura 36 min: da tiempo de pausar
    time.sleep(0.3)
    assert simulador.pausar()["estado"] == "pausado"
    procesadas = simulador.resumen()["procesadas"]
    time.sleep(0.3)
    assert simulador.resumen()["procesadas"] == procesadas
    assert simulador.reanudar()["estado"] == "corriendo"
    with pytest.raises(RuntimeError):
        simulador.iniciar()                    # no se arrancan dos a la vez
    assert simulador.detener()["estado"] == "detenido"


def test_con_esperar_triajes_no_suelta_compras_mientras_hay_un_triaje(sin_esperas):
    # Auditoría 2026-11-14 (H2): en modo medición el reloj del dataset se detiene durante el triaje.
    flujo, triaje_en_curso = FlujoFalso(), {"si": True}
    simulador = sin_esperas(flujo)
    simulador.ocupado = lambda: triaje_en_curso["si"]
    simulador.iniciar(3600, esperar_triajes=True)
    time.sleep(0.3)
    assert simulador.resumen()["procesadas"] == 0 and simulador.resumen()["esperar_triajes"] is True
    triaje_en_curso["si"] = False
    assert esperar(simulador) == "terminado"
    assert simulador.resumen()["procesadas"] == len(flujo.recibidas) > 0


def test_velocidad_invalida_se_rechaza():
    simulador = Simulador(config.CARPETA_SEMILLA, evaluar=FlujoFalso())
    with pytest.raises(ValueError):
        simulador.cambiar_velocidad(7)
