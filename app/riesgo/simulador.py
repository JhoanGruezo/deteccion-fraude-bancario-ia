"""Simulador en vivo (SPEC, RF8): reproduce un tramo real de Sparkov compra por compra.

Lee `semilla/simulador_sparkov.json.gz` (36 h de la partición de prueba, 5.810 compras) y manda
cada compra por el MISMO camino que una compra real (`flujo.evaluar_transaccion`), con un reloj
acelerado: `velocidad` segundos del dataset por cada segundo real (300 = las 36 h en ~7 minutos).
Así lo que se ve en la demo —casos que se abren, el agente que bloquea, la regla que cubre,
compras rechazadas— es el sistema de verdad, no una animación.

La etiqueta del dataset viaja con cada compra hasta `transacciones_evaluadas.es_fraude_dataset`
para medir después con el usuario dueño (eval/); la app no la puede leer.

Corre en un hilo propio y se controla desde la API (solo supervisor): iniciar, pausar, reanudar,
detener y cambiar la velocidad. Si una compra ya se evaluó (por ejemplo, al iniciar otra vez sin
reiniciar los datos), el flujo la reconoce y no la duplica.
"""

import gzip
import json
import logging
import os
import threading
import time
from datetime import datetime

from app import config

registro = logging.getLogger("app.riesgo.simulador")

ARCHIVO = "simulador_sparkov.json.gz"
VELOCIDADES = (60, 120, 300, 600, 1800, 3600)
VELOCIDAD_POR_DEFECTO = 300
ESPERA_MAXIMA_S = 2.0          # nunca dormir más que esto de corrido: así pausar/detener responde rápido


def _fecha(texto: str) -> datetime:
    return datetime.strptime(texto, "%Y-%m-%d %H:%M:%S")


class Simulador:
    def __init__(self, carpeta: str | None = None, evaluar=None, reloj=time.monotonic, dormir=time.sleep):
        self._carpeta = carpeta or config.CARPETA_SEMILLA
        self._evaluar = evaluar
        self._reloj, self._dormir = reloj, dormir
        self._candado = threading.Lock()
        self._hilo: threading.Thread | None = None
        self._continuar = threading.Event()
        self._detener = threading.Event()
        self._datos = None
        self.estado = "detenido"
        self.velocidad = VELOCIDAD_POR_DEFECTO
        self.indice = 0
        self.contadores = {"procesadas": 0, "repetidas": 0, "rechazadas": 0, "monto_rechazado": 0.0,
                           "casos_abiertos": 0, "errores": 0}
        self.reloj_dataset: str | None = None

    # --- Datos ------------------------------------------------------------------------------
    def disponible(self) -> bool:
        return os.path.exists(os.path.join(self._carpeta, ARCHIVO))

    def _cargar(self):
        if self._datos is None:
            with gzip.open(os.path.join(self._carpeta, ARCHIVO), "rt", encoding="utf-8") as archivo:
                self._datos = json.load(archivo)
        return self._datos

    # --- Control ------------------------------------------------------------------------------
    def iniciar(self, velocidad: int | None = None) -> dict:
        with self._candado:
            if self.estado in ("corriendo", "pausado"):
                raise RuntimeError("El simulador ya está en marcha.")
            if not self.disponible():
                raise FileNotFoundError("No está la semilla del simulador (semilla/simulador_sparkov.json.gz).")
            self._cargar()
            self.cambiar_velocidad(velocidad or self.velocidad)
            self.indice = 0
            self.contadores = {k: 0 if k != "monto_rechazado" else 0.0 for k in self.contadores}
            self._detener.clear()
            self._continuar.set()
            self.estado = "corriendo"
            self._hilo = threading.Thread(target=self._correr, name="simulador", daemon=True)
            self._hilo.start()
        registro.info("Simulador iniciado a %dx.", self.velocidad)
        return self.resumen()

    def pausar(self) -> dict:
        if self.estado == "corriendo":
            self._continuar.clear()
            self.estado = "pausado"
        return self.resumen()

    def reanudar(self) -> dict:
        if self.estado == "pausado":
            self.estado = "corriendo"
            self._continuar.set()
        return self.resumen()

    def detener(self) -> dict:
        self._detener.set()
        self._continuar.set()
        if self._hilo:
            self._hilo.join(timeout=5)
        if self.estado != "terminado":
            self.estado = "detenido"
        return self.resumen()

    def cambiar_velocidad(self, velocidad: int) -> dict:
        if velocidad not in VELOCIDADES:
            raise ValueError(f"Velocidad no válida. Opciones: {', '.join(map(str, VELOCIDADES))}.")
        self.velocidad = velocidad
        self._recalibrar = True
        return self.resumen()

    # --- Bucle ---------------------------------------------------------------------------------
    def _correr(self):
        from app.riesgo import flujo
        evaluar = self._evaluar or flujo.evaluar_transaccion
        transacciones = self._datos["transacciones"]
        fuente = self._datos["resumen"]["fuente"]
        inicio_dataset = _fecha(transacciones[0]["fecha_hora"])
        self._recalibrar = True
        while self.indice < len(transacciones) and not self._detener.is_set():
            if not self._continuar.is_set():
                self._continuar.wait()
                self._recalibrar = True
                continue
            t = transacciones[self.indice]
            momento = _fecha(t["fecha_hora"])
            if self._recalibrar:
                # Ancla: este instante real corresponde a este instante del dataset.
                ancla_real, ancla_dataset, self._recalibrar = self._reloj(), momento, False
            objetivo = ancla_real + (momento - ancla_dataset).total_seconds() / self.velocidad
            espera = objetivo - self._reloj()
            if espera > 0:
                self._dormir(min(espera, ESPERA_MAXIMA_S))
                continue
            try:
                compra = {k: t[k] for k in ("id_transaccion", "id_cuenta", "fecha_hora", "monto", "categoria",
                                            "comercio", "ubicacion", "latitud", "longitud")}
                resultado = evaluar({**compra, "fuente": fuente}, origen="simulador", etiqueta=t["es_fraude"])
                self.contadores["procesadas"] += 1
                if resultado.get("repetida"):
                    self.contadores["repetidas"] += 1
                if resultado.get("decision") == "rechazada_por_bloqueo":
                    self.contadores["rechazadas"] += 1
                    self.contadores["monto_rechazado"] += float(t["monto"])
                if resultado.get("evento") == "caso_abierto":
                    self.contadores["casos_abiertos"] += 1
            except Exception:  # noqa: BLE001 — una compra rota no detiene la noche entera
                self.contadores["errores"] += 1
                registro.exception("El simulador no pudo evaluar %s", t["id_transaccion"])
            self.reloj_dataset = t["fecha_hora"]
            self.indice += 1
        self.estado = "terminado" if self.indice >= len(transacciones) else "detenido"
        registro.info("Simulador %s: %s", self.estado, self.contadores)
        del inicio_dataset

    def resumen(self) -> dict:
        if self._datos is None and self.disponible():
            self._cargar()            # así la vista muestra el tramo y el total antes de iniciar
        datos = self._datos or {}
        resumen_semilla = datos.get("resumen", {})
        total = resumen_semilla.get("transacciones") or len(datos.get("transacciones", []))
        return {"estado": self.estado, "velocidad": self.velocidad, "velocidades": list(VELOCIDADES),
                "indice": self.indice, "total": total, "reloj_dataset": self.reloj_dataset,
                "inicio_dataset": resumen_semilla.get("inicio"), "fin_dataset": resumen_semilla.get("fin"),
                "disponible": self.disponible(), **self.contadores,
                "monto_rechazado": round(self.contadores["monto_rechazado"], 2)}


_simulador: Simulador | None = None


def simulador() -> Simulador:
    global _simulador
    if _simulador is None:
        _simulador = Simulador()
    return _simulador
