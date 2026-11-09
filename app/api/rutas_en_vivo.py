"""Rutas del flujo en vivo: recibir una transacción, ver las últimas y listar tarjetas (SPEC, RF1, RF8).

`POST /api/transacciones` es la puerta por la que el profesor puede inyectar una compra a
mano (por ejemplo, con un comercio malicioso) y ver qué hace el sistema. Por eso:

- la tarjeta se nombra por su **alias** (TAR-0001), nunca por su número;
- el cuerpo se valida con límites de longitud y rango antes de tocar la base;
- la fuente y el origen los pone el servidor, no el cliente;
- los errores salen en español con 404 o 422, nunca con una traza.
"""

import importlib
from datetime import timedelta

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api", tags=["en_vivo"])


def flujo():
    """Import diferido: la ruta existe aunque el motor (pandas, scikit-learn) aún no se haya cargado."""
    return importlib.import_module("app.riesgo.flujo")


def repositorio():
    return importlib.import_module("app.db.repositorio_en_vivo")


class CuerpoTransaccion(BaseModel):
    tarjeta: str = Field(..., min_length=3, max_length=20, description="Alias de la tarjeta, por ejemplo TAR-0001")
    monto: float = Field(..., gt=0, le=1_000_000)
    categoria: str = Field(..., min_length=1, max_length=60)
    comercio: str | None = Field(None, max_length=120)
    fecha_hora: str | None = Field(None, max_length=25, description="AAAA-MM-DD HH:MM:SS; por defecto, 10 min después de la última compra")
    latitud: float | None = Field(None, ge=-90, le=90)
    longitud: float | None = Field(None, ge=-180, le=180)


@router.post("/transacciones")
def recibir_transaccion(cuerpo: CuerpoTransaccion):
    tarjeta = repositorio().tarjeta_por_alias(cuerpo.tarjeta)
    if tarjeta is None:
        raise HTTPException(404, f"No existe la tarjeta {cuerpo.tarjeta}.")
    fuente, id_cuenta = tarjeta
    estado = repositorio().estado_de(fuente, id_cuenta)
    transaccion = cuerpo.model_dump(exclude={"tarjeta"})
    transaccion.update(fuente=fuente, id_cuenta=id_cuenta)
    # Sin fecha: la compra ocurre 10 minutos después de la última de la tarjeta (el reloj del
    # dataset, no el de hoy). Sin coordenadas: en el domicilio del titular.
    if not transaccion["fecha_hora"] and estado.get("ultima_fecha"):
        ultima = flujo()._fecha(estado["ultima_fecha"])
        transaccion["fecha_hora"] = (ultima + timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")
    if transaccion["latitud"] is None or transaccion["longitud"] is None:
        transaccion["latitud"], transaccion["longitud"] = estado["latitud_domicilio"], estado["longitud_domicilio"]
    try:
        resultado = flujo().evaluar_transaccion(transaccion, origen="api")
    except flujo().TransaccionInvalida as error:
        raise HTTPException(422, str(error)) from error
    resultado["tarjeta"] = cuerpo.tarjeta.strip().upper()
    return resultado


@router.get("/transacciones/recientes")
def transacciones_recientes(desde_id: int = Query(0, ge=0), limite: int = Query(100, ge=1, le=500)):
    return {"transacciones": repositorio().ultimas_evaluadas(limite=limite, desde_id=desde_id)}


@router.get("/tarjetas")
def tarjetas(limite: int = Query(50, ge=1, le=500)):
    return {"tarjetas": repositorio().listar_tarjetas(limite=limite)}


# --- Simulador (SPEC, RF8). Leer: cualquier sesión; controlar: solo supervisor. ---------------


def simulador():
    return importlib.import_module("app.riesgo.simulador").simulador()


class CuerpoSimulador(BaseModel):
    velocidad: int | None = None


@router.get("/simulador")
def estado_simulador():
    return simulador().resumen()


@router.post("/simulador/{accion}")
def controlar_simulador(accion: str, cuerpo: CuerpoSimulador | None = None):
    sim = simulador()
    velocidad = cuerpo.velocidad if cuerpo else None
    try:
        if accion == "iniciar":
            return sim.iniciar(velocidad)
        if accion == "pausar":
            return sim.pausar()
        if accion == "reanudar":
            return sim.reanudar()
        if accion == "detener":
            return sim.detener()
        if accion == "velocidad" and velocidad:
            return sim.cambiar_velocidad(velocidad)
    except (RuntimeError, ValueError, FileNotFoundError) as error:
        raise HTTPException(409 if isinstance(error, RuntimeError) else 422, str(error)) from error
    raise HTTPException(404, "Acción del simulador desconocida (iniciar, pausar, reanudar, detener, velocidad).")
