"""Cascada de proveedores: reintentos con backoff, conmutación y fallas forzadas.

Es la respuesta del proyecto al reto de la semana 9 (ver diseno/agente.md,
"Cascada"): un 429 o un timeout del proveedor principal no puede tumbar la demo.
Para cada proveedor, en orden:

- error reintentable (cuota, servidor, timeout) → espera 1 s, 2 s, 4 s (tres
  reintentos como máximo) y, si sigue fallando, conmuta al siguiente;
- error no reintentable (autenticación, sin llave, solicitud inválida) → conmuta de
  inmediato, porque esperar no lo arregla;
- si ninguno responde → ErrorProveedor("agotados") y el servicio usa la plantilla.

Cada reintento y cada conmutación se entregan como ("evento", {...}) ANTES de
esperar, para que la pantalla muestre el estado honesto ("Gemini respondió 429 ·
reintento 2/3 en 2 s") mientras la espera ocurre, no después.

Las fallas forzadas (FALLA_FORZADA) se simulan aquí, antes de tocar la red, para
poder mostrarlas en vivo sin gastar cuota.
"""

import time
from typing import Callable, Iterator

from app import config
from app.proveedores.base import ErrorProveedor, Mensaje, Proveedor, RespuestaModelo

NOMBRES_VISIBLES = {"gemini": "Gemini", "claude": "Claude"}


def _visible(nombre: str) -> str:
    return NOMBRES_VISIBLES.get(nombre, nombre)


def _motivo_legible(error: ErrorProveedor) -> str:
    return {
        "cuota": "respondió 429 (cuota agotada)",
        "timeout": "no respondió a tiempo",
        "servidor": "tuvo un error del servidor",
        "autenticacion": "rechazó la llave",
        "sin_llave": "no tiene llave configurada",
        "solicitud": "rechazó la solicitud",
    }.get(error.tipo, error.tipo)


class ProveedorEnCascada:
    def __init__(self, proveedores: list[Proveedor], esperas=(1, 2, 4),
                 dormir: Callable[[float], None] = time.sleep):
        self.proveedores = list(proveedores)
        self.esperas = tuple(esperas)
        # Se inyecta para que las pruebas no esperen de verdad.
        self.dormir = dormir
        # Proveedor con el que se empieza la próxima llamada. Tras una conmutación
        # queda en el que sí respondió: las siguientes iteraciones de la misma tarea
        # no vuelven a pagar el backoff del proveedor caído.
        self.indice_actual = 0
        self._json_forzado_aplicado = False

    @property
    def vacia(self) -> bool:
        return not self.proveedores

    @property
    def proveedor_actual(self) -> Proveedor | None:
        """El proveedor con el que empezará la próxima llamada (para la traza)."""
        return self.proveedores[self.indice_actual] if self.proveedores else None

    def _falla_simulada(self, indice: int, falla_forzada: str | None) -> ErrorProveedor | None:
        """Devuelve el error que hay que simular para este proveedor, o None."""
        es_principal = indice == 0
        if falla_forzada == "429" and es_principal:
            return ErrorProveedor("cuota", "Falla forzada: 429 simulado (no se llamó a la red)")
        if falla_forzada == "timeout" and es_principal:
            return ErrorProveedor("timeout", "Falla forzada: timeout simulado (no se llamó a la red)")
        if falla_forzada == "todo":
            return ErrorProveedor("servidor", "Falla forzada: proveedor caído simulado (no se llamó a la red)")
        return None

    def _llamar(self, proveedor: Proveedor, sistema, mensajes, herramientas, max_tokens, timeout_s,
                falla_forzada) -> Iterator[tuple[str, object]]:
        """Una llamada real a un proveedor; con falla "json" trunca la primera respuesta final."""
        if falla_forzada != "json" or self._json_forzado_aplicado:
            yield from proveedor.generar(sistema, mensajes, herramientas, max_tokens, timeout_s)
            return

        # Con la falla "json" pendiente no se sabe si esta respuesta será la final
        # hasta que termina, así que se retiene el texto y se decide al final.
        fragmentos = []
        for clase, dato in proveedor.generar(sistema, mensajes, herramientas, max_tokens, timeout_s):
            if clase == "texto":
                fragmentos.append(dato)
                continue
            respuesta: RespuestaModelo = dato
            if respuesta.llamadas:
                # No es la respuesta final: se entrega intacta.
                for fragmento in fragmentos:
                    yield "texto", fragmento
            else:
                self._json_forzado_aplicado = True
                respuesta.texto = respuesta.texto[: len(respuesta.texto) // 2]
                yield "evento", {"tipo": "estado",
                                 "texto": "Falla forzada «json»: la respuesta se cortó a la mitad a propósito."}
                yield "texto", respuesta.texto
            yield "fin", respuesta

    def generar(self, sistema: str, mensajes: list[Mensaje], herramientas: list[dict],
                max_tokens: int, timeout_s: float, falla_forzada: str | None = None
                ) -> Iterator[tuple[str, object]]:
        """Igual que Proveedor.generar, pero además entrega ("evento", dict) de reintento y conmutación."""
        if self.vacia:
            raise ErrorProveedor("agotados", "No hay ningún proveedor de IA configurado", reintentable=False)

        ultimo_error = None
        tipos_de_error = []
        for indice in range(self.indice_actual, len(self.proveedores)):
            proveedor = self.proveedores[indice]
            intentos_totales = 1 + len(self.esperas)
            for intento in range(1, intentos_totales + 1):
                try:
                    simulada = self._falla_simulada(indice, falla_forzada)
                    if simulada:
                        raise simulada
                    yield from self._llamar(proveedor, sistema, mensajes, herramientas,
                                            max_tokens, timeout_s, falla_forzada)
                    self.indice_actual = indice
                    return
                except ErrorProveedor as error:
                    ultimo_error = error
                    tipos_de_error.append(error.tipo)
                    quedan_reintentos = intento < intentos_totales
                    if not (error.reintentable and quedan_reintentos):
                        break
                    espera = self.esperas[intento - 1]
                    yield "evento", {
                        "tipo": "reintento",
                        "proveedor": proveedor.nombre,
                        "motivo": error.tipo,
                        "intento": intento,
                        "de": len(self.esperas),
                        "espera_s": espera,
                        "detalle": error.mensaje,
                        "texto": f"{_visible(proveedor.nombre)} {_motivo_legible(error)} · "
                                 f"reintento {intento}/{len(self.esperas)} en {espera:g} s",
                    }
                    self.dormir(espera)

            # Este proveedor no respondió: se pasa al siguiente, si lo hay.
            if indice + 1 < len(self.proveedores):
                siguiente = self.proveedores[indice + 1]
                yield "evento", {
                    "tipo": "conmutacion",
                    "de": proveedor.nombre,
                    "a": siguiente.nombre,
                    "motivo": ultimo_error.tipo,
                    "detalle": ultimo_error.mensaje,
                    "texto": f"{_visible(proveedor.nombre)} {_motivo_legible(ultimo_error)}: "
                             f"se cambia a {_visible(siguiente.nombre)}",
                }

        error = ErrorProveedor("agotados", f"Ningún proveedor respondió (último: {ultimo_error.mensaje})",
                               reintentable=False)
        # Si todo lo que falló fueron timeouts, el bucle lo reporta como límite de tiempo.
        error.solo_timeouts = bool(tipos_de_error) and all(t == "timeout" for t in tipos_de_error)
        raise error


def cascada_desde_config() -> ProveedorEnCascada:
    """Arma la cascada con los proveedores que tienen llave, en ORDEN_PROVEEDORES.

    Un proveedor sin llave no entra: si no hay ninguno, la cascada queda vacía y el
    servicio usa la plantilla desde el inicio (diseno/agente.md, "Manejo de errores").
    """
    # Importes locales: así importar la cascada no exige que ambos clientes carguen.
    from app.proveedores.claude import ClienteClaude
    from app.proveedores.gemini import ClienteGemini

    disponibles = {
        "gemini": (config.GEMINI_API_KEY, lambda: ClienteGemini(config.GEMINI_API_KEY, config.GEMINI_MODELO)),
        "claude": (config.ANTHROPIC_API_KEY, lambda: ClienteClaude(config.ANTHROPIC_API_KEY, config.CLAUDE_MODELO,
                                                                razonamiento=config.CLAUDE_RAZONAMIENTO)),
    }
    proveedores = []
    for nombre in config.ORDEN_PROVEEDORES:
        llave, crear = disponibles.get(nombre, ("", None))
        if llave and crear:
            proveedores.append(crear())
    return ProveedorEnCascada(proveedores, esperas=config.ESPERAS_REINTENTO_S)
