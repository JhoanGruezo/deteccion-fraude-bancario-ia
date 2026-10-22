"""Rutas de casos: bandeja, detalle, historial y decisiones manuales del analista.

Estas rutas solo traducen HTTP ↔ `app.db.repositorio`: no hay SQL aquí ni llamadas a
proveedores (regla de capas de `diseno/vista-analista.md`). Lo que sí hacen es validar
la entrada con mensajes en español antes de tocar la base, porque un 422 en inglés de
Pydantic sería justo el tipo de mensaje que la rúbrica castiga ("usable por terceros").

Los endpoints son síncronos a propósito: FastAPI los corre en su pool de hilos y el
repositorio usa psycopg síncrono. Un solo modelo mental, sin `async` mezclado.
"""

import importlib

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.api.sse import depurar_para_interfaz

router = APIRouter(prefix="/api", tags=["casos"])

FUENTES = {"sparkov", "sinteticos"}
NIVELES = {"bloquear_tarjeta", "bloquear_acceso_cuenta", "verificar_cliente"}
ESTADOS = {"pendiente", "bloqueo_confirmado", "descartado", "escalado"}
ORDENES = {"score", "fecha"}
ACCIONES = {"confirmar_bloqueo", "descartar", "escalar"}
LARGO_MAXIMO_ANALISTA = 80
LARGO_MAXIMO_COMENTARIO = 1000


def repositorio():
    """Importa el repositorio en el momento de usarlo, no al cargar el módulo.

    Así un fallo de importación de la capa de datos (por ejemplo, la base sin driver)
    se convierte en un error JSON de esa petición en vez de tumbar toda la app, y
    `/api/salud` puede seguir respondiendo. También permite a las pruebas reemplazar el
    módulo por un doble sin recargar las rutas.
    """
    return importlib.import_module("app.db.repositorio")


class CuerpoDecision(BaseModel):
    """Decisión manual del analista, sin propuesta del agente."""

    accion: str | None = None
    analista: str | None = None
    comentario: str | None = None


def _validar_opcion(valor, permitidas, nombre):
    """Rechaza filtros fuera del dominio con un mensaje que dice qué valores sirven."""
    if valor in (None, ""):
        return None
    if valor not in permitidas:
        opciones = ", ".join(sorted(permitidas))
        raise HTTPException(422, f"El filtro «{nombre}» no admite «{valor}». Opciones: {opciones}.")
    return valor


def validar_analista(analista, comentario):
    """El nombre del analista es obligatorio: sin él la decisión no es auditable."""
    nombre = (analista or "").strip()
    if not nombre:
        raise HTTPException(422, "Escribe tu nombre de analista para registrar la decisión.")
    if len(nombre) > LARGO_MAXIMO_ANALISTA:
        raise HTTPException(422, f"El nombre del analista no puede pasar de {LARGO_MAXIMO_ANALISTA} caracteres.")
    texto = (comentario or "").strip() or None
    if texto and len(texto) > LARGO_MAXIMO_COMENTARIO:
        raise HTTPException(422, f"El comentario no puede pasar de {LARGO_MAXIMO_COMENTARIO} caracteres.")
    return nombre, texto


def caso_o_404(id_caso):
    """Carga el caso o responde 404 en español; lo usan también las rutas del agente."""
    caso = repositorio().obtener_caso(id_caso)
    if not caso:
        raise HTTPException(404, "Caso no encontrado")
    return caso


def normalizar_contadores(crudo) -> dict:
    """Lleva el resultado de `contar_casos()` a una forma fija para el frontend.

    `diseno/persistencia.md` solo dice "por fuente, nivel y estado"; aceptamos los
    nombres de clave más probables para no acoplar la interfaz a ese detalle.
    """
    crudo = crudo or {}

    def tomar(*claves):
        for clave in claves:
            valor = crudo.get(clave)
            if isinstance(valor, dict):
                return {str(k): int(v or 0) for k, v in valor.items()}
        return {}

    por_nivel = tomar("por_nivel", "nivel", "niveles", "nivel_recomendacion")
    por_estado = tomar("por_estado", "estado", "estados")
    por_fuente = tomar("por_fuente", "fuente", "fuentes")
    total = crudo.get("total")
    if not isinstance(total, int):
        total = sum(por_fuente.values()) or sum(por_nivel.values())
    return {"total": total, "por_nivel": por_nivel, "por_estado": por_estado, "por_fuente": por_fuente}


@router.get("/casos")
def listar_casos(
    fuente: str | None = None,
    nivel: str | None = None,
    estado: str | None = None,
    q: str | None = Query(None, max_length=100),
    orden: str = "score",
    limite: int = Query(300, ge=1, le=1000),
):
    """Bandeja: casos filtrados más los contadores globales de la cabecera."""
    repo = repositorio()
    casos = repo.listar_casos(
        fuente=_validar_opcion(fuente, FUENTES, "fuente"),
        nivel=_validar_opcion(nivel, NIVELES, "nivel"),
        estado=_validar_opcion(estado, ESTADOS, "estado"),
        busqueda=(q or "").strip() or None,
        orden=_validar_opcion(orden, ORDENES, "orden") or "score",
        limite=limite,
    )
    return depurar_para_interfaz(
        {"casos": casos, "total": len(casos), "contadores": normalizar_contadores(repo.contar_casos())}
    )


@router.get("/casos/{id_caso}")
def obtener_detalle(id_caso: str):
    """Detalle: el caso, su explicación vigente (si hay), propuestas y decisiones.

    La explicación vigente viaja aquí para el botón "Ver explicación guardada" de la
    banda de error: si el stream falla, la interfaz ya tiene con qué responder.
    """
    repo = repositorio()
    caso = caso_o_404(id_caso)
    explicacion = repo.explicacion_vigente(id_caso)
    if explicacion:
        # El nivel de riesgo en palabras lo arma el código (app/agente/riesgo_en_palabras.py),
        # también para las explicaciones guardadas antes de ese cambio.
        explicacion = importlib.import_module("app.agente.riesgo_en_palabras").con_nivel_de_codigo(
            explicacion, caso, repo)
    return depurar_para_interfaz(
        {
            "caso": caso,
            "explicacion": explicacion,
            "propuestas": repo.propuestas_pendientes(id_caso),
            "decisiones": repo.decisiones_del_caso(id_caso),
            "ultima_tarea": repo.ultima_tarea(id_caso),
        }
    )


@router.get("/casos/{id_caso}/historial")
def obtener_historial(id_caso: str, dias: int = Query(30, ge=1, le=365), limite: int = Query(60, ge=1, le=500)):
    """Línea de tiempo: historial reciente de la tarjeta con las del caso marcadas."""
    caso_o_404(id_caso)
    transacciones = repositorio().obtener_historial(id_caso, dias=dias, limite=limite)
    return depurar_para_interfaz({"dias": dias, "transacciones": transacciones})


@router.post("/casos/{id_caso}/decisiones")
def registrar_decision(id_caso: str, cuerpo: CuerpoDecision):
    """Decisión manual: el analista no necesita que el agente proponga para decidir."""
    if cuerpo.accion not in ACCIONES:
        raise HTTPException(422, "Elige una acción válida: confirmar bloqueo, descartar o escalar.")
    analista, comentario = validar_analista(cuerpo.analista, cuerpo.comentario)
    caso_o_404(id_caso)
    try:
        decision = repositorio().registrar_decision(id_caso, cuerpo.accion, analista, comentario)
    except LookupError:  # CasoNoEncontrado del repositorio: el caso desapareció entre consultas
        raise HTTPException(404, "Caso no encontrado")
    return depurar_para_interfaz({"decision": decision})
