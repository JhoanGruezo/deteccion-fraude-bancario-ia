"""Puntúa una transacción con el modelo entrenado, en milisegundos y sin red (SPEC, RF1).

Carga una sola vez el paquete que escribió el motor fuera de línea
(`semilla/modelo_riesgo_sparkov.joblib`: modelo, lista de features, umbrales de
verificación y de bloqueo, y referencias para los percentiles) y lo usa con las
features del perfil incremental (`perfil_incremental.py`).

Las señales en palabras (las "desviaciones" que cita el agente) solo se calculan si la
transacción llega al umbral de verificación: cuestan una predicción más por grupo de
señales (oclusión) y no hacen falta para las compras normales, que son casi todas.

El LLM no participa aquí. Que la decisión de riesgo no dependa de un proveedor externo
es lo que permite garantizar el bloqueo aunque la IA esté caída (SPEC, RF4).

Seguridad del archivo del modelo: `joblib.load` ejecuta lo que trae el archivo, así que
solo se carga el paquete de `semilla/`, que genera el propio equipo con
`src/entrenar_modelo.py`. La ruta viene de la configuración, nunca de una petición.
"""

import threading
import time

import joblib
import pandas as pd

import app.riesgo  # noqa: F401 — agrega src/ a la ruta
from app import config
from app.riesgo.perfil_incremental import EstadoTarjeta, es_viaje_imposible, features_de
from motor_riesgo import contribuciones_por_oclusion, desviaciones


def _nativo(valor):
    """numpy → tipos de Python, para que todo vaya a jsonb sin sorpresas."""
    if isinstance(valor, dict):
        return {k: _nativo(v) for k, v in valor.items()}
    if isinstance(valor, list):
        return [_nativo(v) for v in valor]
    if hasattr(valor, "item"):
        return valor.item()
    return valor


class MotorEnVivo:
    def __init__(self, ruta_paquete: str):
        paquete = joblib.load(ruta_paquete)
        self.modelo = paquete["modelo"]
        self.nombre = paquete["nombre"]
        self.features = list(paquete["features"])
        self.umbral_verificacion = float(paquete["umbral_verificacion"])
        self.umbral_bloqueo = float(paquete["umbral_bloqueo"])
        self.referencias = paquete["referencias"]

    def evaluar(self, estado: EstadoTarjeta, transaccion: dict, con_senales: bool | None = None) -> dict:
        """Score, viaje imposible y, si la compra es sospechosa, las señales que lo explican.

        No modifica el estado: quien llama decide cuándo sumar la compra al perfil.
        """
        inicio = time.perf_counter()
        valores = features_de(estado, transaccion)
        fila = pd.DataFrame([valores])
        score = float(self.modelo.predict_proba(fila[self.features])[:, 1][0])
        latencia_puntuacion_ms = (time.perf_counter() - inicio) * 1000
        viaje = es_viaje_imposible(estado, transaccion)

        senales = []
        if con_senales or (con_senales is None and score >= self.umbral_verificacion):
            aportes = contribuciones_por_oclusion(self.modelo, fila, self.features, self.referencias["medianas"])
            senales = desviaciones(fila.iloc[0], aportes.iloc[0].to_dict(), self.referencias)
        return _nativo({
            "score": round(score, 6),
            "viaje_imposible": viaje,
            "desviaciones": senales,
            "features": {f: valores[f] for f in self.features},
            "n_previas": valores["n_previas"],
            "latencia_puntuacion_ms": round(latencia_puntuacion_ms, 3),
            "latencia_total_ms": round((time.perf_counter() - inicio) * 1000, 3),
        })


_motor: MotorEnVivo | None = None
_candado = threading.Lock()


def motor() -> MotorEnVivo:
    """El motor único del proceso (se carga la primera vez que se usa)."""
    global _motor
    if _motor is None:
        with _candado:
            if _motor is None:
                _motor = MotorEnVivo(config.RUTA_MODELO)
    return _motor
