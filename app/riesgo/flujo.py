"""El camino de cada transacción que llega: puntuar, decidir la banda, abrir o actualizar el caso.

Es el corazón del Momento 3 (SPEC, RF1 y RF2) y no llama al LLM: decide en milisegundos
con el modelo y reglas escritas en código. Cuando un caso se abre o sube de banda, avisa a
quien esté escuchando (el triaje del agente y la red de seguridad, fase 3) **después** de
guardar todo, así que una falla del agente nunca deja una compra a medio registrar.

Bandas del caso (las decide este módulo, nunca el modelo de lenguaje):

| Banda | Condición | Qué permite |
|---|---|---|
| crítica | ≥ 2 compras sobre el umbral de bloqueo en la ventana de 48 h, o viaje imposible donde cuenta | bloqueo obligatorio |
| alta | una compra sobre el umbral de bloqueo | el agente decide si bloquea |
| media | compras entre el umbral de verificación y el de bloqueo | solo verificación |

- El caso se abre con la **primera** compra marcada (en el M2 hacían falta dos; el
  análisis mostró que esa espera dejaba pasar el 13 % del monto).
- Una compra de una tarjeta **bloqueada** se rechaza: no entra al perfil ni al caso, y
  queda registrada como dinero detenido.
- El viaje imposible no abre casos en Sparkov: su geografía es falsa (14.153 falsas
  alarmas en el tramo de prueba, decisión del 2026-10-21). Se calcula y se guarda igual.
- La misma compra enviada dos veces (mismo id) no se evalúa dos veces: se devuelve lo
  que ya se decidió (idempotencia, por si el simulador o un cliente reintenta).
"""

import logging
import time
import uuid
from datetime import datetime, timedelta
from typing import Callable

import app.riesgo  # noqa: F401 — agrega src/ a la ruta
from app.db import repositorio_en_vivo as repositorio_por_defecto
from app.riesgo.motor_en_vivo import motor as motor_por_defecto
from app.riesgo.perfil_incremental import EstadoTarjeta, actualizar, perfil_resumido
from motor_riesgo import recomendar

registro = logging.getLogger("app.riesgo.flujo")

VENTANA_CASO = timedelta(hours=48)
VIAJE_IMPOSIBLE_ABRE_CASO = {"sparkov": False, "sinteticos": True}
ORDEN_BANDA = {"sin_alerta": 0, "media": 1, "alta": 2, "critica": 3}
EVENTOS_QUE_DISPARAN = ("caso_abierto", "subio_de_banda")
CAMPOS_OBLIGATORIOS = ("fuente", "id_cuenta", "fecha_hora", "monto", "categoria", "latitud", "longitud")

_oyentes: list[Callable[[dict], None]] = []


class TransaccionInvalida(ValueError):
    """La transacción no trae lo necesario para puntuarla (mensaje en español para el usuario)."""


def al_cambiar_caso(oyente: Callable[[dict], None]) -> None:
    """Registra una función que recibe {id_caso, banda, evento} al abrirse o subir de banda un caso."""
    if oyente not in _oyentes:
        _oyentes.append(oyente)


def quitar_oyentes() -> None:
    _oyentes.clear()


def banda_del_caso(transacciones: list[dict], umbral_bloqueo: float, viaje_cuenta: bool) -> tuple[str, int]:
    """Banda del caso y cuántas compras superan el umbral de bloqueo."""
    sobre_bloqueo = sum(1 for t in transacciones if float(t["score"]) >= umbral_bloqueo)
    viaje = viaje_cuenta and any(t["viaje_imposible"] for t in transacciones)
    if sobre_bloqueo >= 2 or viaje:
        return "critica", sobre_bloqueo
    return ("alta" if sobre_bloqueo == 1 else "media"), sobre_bloqueo


def _fecha(valor) -> datetime:
    if isinstance(valor, datetime):
        return valor.replace(tzinfo=None, microsecond=0)
    try:
        return datetime.fromisoformat(str(valor).strip().replace("T", " ")[:19])
    except ValueError as error:
        raise TransaccionInvalida("La fecha y hora debe tener el formato AAAA-MM-DD HH:MM:SS.") from error


def _normalizar(transaccion: dict) -> dict:
    faltan = [c for c in CAMPOS_OBLIGATORIOS if transaccion.get(c) in (None, "")]
    if faltan:
        raise TransaccionInvalida(f"Faltan datos de la transacción: {', '.join(faltan)}.")
    t = dict(transaccion)
    t["fecha_hora"] = _fecha(t["fecha_hora"])
    t["monto"] = round(float(t["monto"]), 2)
    if not 0 < t["monto"] <= 1_000_000:
        raise TransaccionInvalida("El monto debe ser mayor que 0 y como máximo 1.000.000.")
    t["latitud"], t["longitud"] = float(t["latitud"]), float(t["longitud"])
    if not (-90 <= t["latitud"] <= 90 and -180 <= t["longitud"] <= 180):
        raise TransaccionInvalida("Las coordenadas del comercio no son válidas.")
    t["categoria"] = str(t["categoria"])[:60]
    t["comercio"] = str(t["comercio"])[:120] if t.get("comercio") else None
    t["ubicacion"] = str(t["ubicacion"])[:80] if t.get("ubicacion") else None
    t["id_transaccion"] = str(t.get("id_transaccion") or uuid.uuid4().hex)[:64]
    return t


def _tipo(transaccion_caso: dict) -> str:
    return "viaje_imposible" if transaccion_caso.get("cuenta_viaje") else "uso_no_autorizado"


def evaluar_transaccion(transaccion: dict, origen: str = "api", etiqueta: int | None = None,
                        motor=None, repositorio=None, domicilio: tuple[float, float] | None = None) -> dict:
    """Puntúa la compra, la guarda y, si corresponde, abre o actualiza el caso de su tarjeta.

    `etiqueta` es la del dataset (solo la pasa el simulador, para medir; la app no la lee).
    `domicilio` (latitud, longitud) solo se usa si la tarjeta no tiene perfil todavía.
    """
    inicio = time.perf_counter()
    motor = motor or motor_por_defecto()
    repositorio = repositorio or repositorio_por_defecto
    t = _normalizar(transaccion)
    fuente, id_cuenta = t["fuente"], str(t["id_cuenta"])
    evento = None

    with repositorio.transaccion() as cur:
        previa = repositorio.ya_evaluada(cur, fuente, t["id_transaccion"])
        if previa:
            return {"repetida": True, "id_transaccion": t["id_transaccion"], **previa}

        perfil = repositorio.perfil_para_actualizar(cur, fuente, id_cuenta)
        if perfil is None:
            if domicilio is None:
                raise TransaccionInvalida("La tarjeta no tiene perfil: indique el domicilio del titular para crearlo.")
            nuevo = EstadoTarjeta(id_cuenta, float(domicilio[0]), float(domicilio[1]))
            repositorio.crear_perfil(cur, fuente, id_cuenta, nuevo.a_dict())
            perfil = repositorio.perfil_para_actualizar(cur, fuente, id_cuenta)
        estado = EstadoTarjeta.desde_dict(perfil["estado"])

        resultado = motor.evaluar(estado, t)
        viaje_cuenta = resultado["viaje_imposible"] and VIAJE_IMPOSIBLE_ABRE_CASO.get(fuente, True)
        if viaje_cuenta and not resultado["desviaciones"]:
            resultado = motor.evaluar(estado, t, con_senales=True)

        id_caso, banda = None, "sin_alerta"
        bloqueo = repositorio.bloqueo_activo(cur, fuente, id_cuenta)
        if bloqueo:
            # Tarjeta bloqueada: la compra se rechaza y no cuenta como hábito del cliente.
            decision, id_caso = "rechazada_por_bloqueo", bloqueo["id_caso"]
        else:
            decision = "aprobada"
            if resultado["score"] >= motor.umbral_verificacion or viaje_cuenta:
                id_caso, banda, evento = _abrir_o_actualizar_caso(cur, repositorio, motor, t, resultado,
                                                                  viaje_cuenta, estado)
            repositorio.guardar_en_historial(cur, fuente, id_cuenta, t)
            actualizar(estado, t)
            repositorio.guardar_perfil(cur, fuente, id_cuenta, estado.a_dict())

        latencia_total_ms = round((time.perf_counter() - inicio) * 1000, 3)
        guardada = repositorio.guardar_evaluada(cur, {
            **{k: t.get(k) for k in ("fuente", "id_transaccion", "fecha_hora", "monto", "categoria", "comercio",
                                     "ubicacion", "latitud", "longitud")},
            "id_cuenta": id_cuenta, "score": resultado["score"], "banda": banda,
            "viaje_imposible": resultado["viaje_imposible"], "desviaciones": resultado["desviaciones"],
            "id_caso": id_caso, "origen": origen, "decision": decision,
            "latencia_puntuacion_ms": resultado["latencia_puntuacion_ms"], "latencia_total_ms": latencia_total_ms,
            "es_fraude_dataset": etiqueta,
        })

    salida = {
        "repetida": False, "id": guardada["id"], "id_transaccion": t["id_transaccion"], "decision": decision,
        "score": resultado["score"], "banda": banda, "viaje_imposible": resultado["viaje_imposible"],
        "id_caso": id_caso, "evento": evento, "latencia_total_ms": latencia_total_ms,
        "latencia_puntuacion_ms": resultado["latencia_puntuacion_ms"],
    }
    if evento in EVENTOS_QUE_DISPARAN:
        _avisar({"id_caso": id_caso, "banda": banda, "evento": evento})
    return salida


def _abrir_o_actualizar_caso(cur, repositorio, motor, t, resultado, viaje_cuenta, estado):
    transaccion_caso = {
        "id_transaccion": t["id_transaccion"], "fecha_hora": t["fecha_hora"], "monto": t["monto"],
        "categoria": t["categoria"], "comercio": t.get("comercio"), "ubicacion": t.get("ubicacion"),
        "score": resultado["score"], "viaje_imposible": bool(viaje_cuenta),
        "desviaciones": resultado["desviaciones"], "cuenta_viaje": viaje_cuenta,
    }
    abierto = repositorio.caso_abierto(cur, t["fuente"], str(t["id_cuenta"]), t["fecha_hora"])
    previas = repositorio.transacciones_del_caso(cur, abierto["id_caso"]) if abierto else []
    todas = previas + [transaccion_caso]
    banda, sobre_bloqueo = banda_del_caso(todas, motor.umbral_bloqueo, viaje_cuenta=True)
    tipos = sorted(set(abierto["tipos_fraude"] if abierto else []) | {_tipo(transaccion_caso)})
    score_maximo = max(float(x["score"]) for x in todas)
    nivel, motivo = recomendar(tipos, score_maximo, motor.umbral_bloqueo, sobre_bloqueo)
    principal = max(todas, key=lambda x: float(x["score"]))
    senal_principal = (principal["desviaciones"] or [{"senal": "monto"}])[0]["senal"]
    datos = {"tipos_fraude": tipos, "score_maximo": round(score_maximo, 6),
             "transacciones_sobre_umbral_bloqueo": sobre_bloqueo, "nivel_recomendacion": nivel,
             "motivo_recomendacion": motivo, "senal_principal": senal_principal, "banda": banda}

    if abierto is None:
        id_caso = repositorio.crear_caso(cur, {
            **datos, "fuente": t["fuente"], "id_cuenta": str(t["id_cuenta"]),
            "inicio_ventana": t["fecha_hora"], "fin_ventana": t["fecha_hora"] + VENTANA_CASO,
            "perfil_previo": perfil_resumido(estado, t["fecha_hora"]), "modelo": motor.nombre,
            "umbral_verificacion": motor.umbral_verificacion, "umbral_bloqueo": motor.umbral_bloqueo,
        })
        evento = "caso_abierto"
    else:
        id_caso = abierto["id_caso"]
        subio = ORDEN_BANDA[banda] > ORDEN_BANDA.get(abierto["banda"] or "media", 1)
        repositorio.actualizar_caso(cur, id_caso, datos, subio)
        evento = "subio_de_banda" if subio else "caso_actualizado"
    repositorio.agregar_transaccion_al_caso(cur, id_caso, transaccion_caso)
    return id_caso, banda, evento


def _avisar(evento: dict) -> None:
    for oyente in list(_oyentes):
        try:
            oyente(evento)
        except Exception:  # noqa: BLE001 — un oyente roto no tumba la evaluación ya guardada
            registro.exception("Un oyente del flujo falló con el evento %s", evento)
