"""Inicio de sesión, roles y protección CSRF de toda la API (SPEC, RF7 y RS6).

Reglas, aplicadas en un middleware para que ninguna ruta nueva quede abierta por olvido:

- Toda ruta `/api/...` exige una sesión válida, salvo `GET /api/salud` (la usa la pantalla de
  ingreso para decir si el sistema está arriba) y las rutas de `/api/sesion`.
- Toda petición que cambia algo (POST, PUT, PATCH, DELETE) exige además la cabecera
  `X-CSRF-Token` con el token de la sesión. Una página de otro sitio no lo conoce, así que no
  puede firmar decisiones ni desbloquear tarjetas con la cookie del analista.
- Las rutas de supervisión (`ajustes`, `demo/falla`, `alertas`) exigen el rol supervisor.
- Contra fuerza bruta: 5 intentos fallidos por usuario en 15 minutos lo bloquean 15 minutos (y
  el límite de peticiones por minuto sigue aplicando por IP).
- Los mensajes de error no dicen si el usuario existe.

`config.AUTENTICACION` existe solo para las pruebas unitarias de rutas que usan dobles sin
base; con la autenticación apagada la app lo dice en el registro al arrancar.
"""

import importlib
import threading
import time

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app import config

router = APIRouter(prefix="/api/sesion", tags=["sesion"])

COOKIE = "sesion"
CABECERA_CSRF = "x-csrf-token"
RUTAS_PUBLICAS = {"/api/salud"}
PREFIJO_PUBLICO = "/api/sesion"
METODOS_SEGUROS = {"GET", "HEAD", "OPTIONS"}
SOLO_SUPERVISOR = ("/api/ajustes", "/api/demo/", "/api/alertas", "/api/simulador")
INTENTOS_MAXIMOS = 5
VENTANA_INTENTOS_S = 15 * 60


def usuarios():
    return importlib.import_module("app.db.repositorio_usuarios")


class _Intentos:
    def __init__(self):
        self._fallos: dict[str, list[float]] = {}
        self._candado = threading.Lock()

    def bloqueado(self, usuario: str) -> bool:
        ahora = time.monotonic()
        with self._candado:
            recientes = [t for t in self._fallos.get(usuario, []) if ahora - t < VENTANA_INTENTOS_S]
            self._fallos[usuario] = recientes
            return len(recientes) >= INTENTOS_MAXIMOS

    def fallo(self, usuario: str) -> None:
        with self._candado:
            self._fallos.setdefault(usuario, []).append(time.monotonic())

    def exito(self, usuario: str) -> None:
        with self._candado:
            self._fallos.pop(usuario, None)


intentos = _Intentos()


class CuerpoIngreso(BaseModel):
    usuario: str = Field(..., min_length=1, max_length=60)
    clave: str = Field(..., min_length=1, max_length=200)


@router.post("/ingresar")
def ingresar(cuerpo: CuerpoIngreso, respuesta: Response):
    nombre = cuerpo.usuario.strip().lower()
    if intentos.bloqueado(nombre):
        raise HTTPException(429, "Demasiados intentos fallidos. Espera 15 minutos o pide ayuda a un supervisor.")
    usuario = usuarios().autenticar(nombre, cuerpo.clave)
    if usuario is None:
        intentos.fallo(nombre)
        raise HTTPException(401, "Usuario o contraseña incorrectos.")
    intentos.exito(nombre)
    token, csrf, expira = usuarios().crear_sesion(usuario["usuario"], config.HORAS_SESION)
    respuesta.set_cookie(COOKIE, token, httponly=True, samesite="strict", secure=config.COOKIE_SEGURA,
                         max_age=int(config.HORAS_SESION * 3600), path="/")
    return {"usuario": usuario, "csrf": csrf, "expira_en": expira.isoformat()}


@router.get("")
def sesion_actual(request: Request):
    """Quién soy y el token CSRF (la interfaz lo pide al cargar). 401 si no hay sesión."""
    sesion = usuarios().sesion_vigente(request.cookies.get(COOKIE)) if config.AUTENTICACION else None
    if not config.AUTENTICACION:
        return {"usuario": {"usuario": "pruebas", "nombre": "Pruebas", "rol": "supervisor"}, "csrf": "pruebas"}
    if sesion is None:
        raise HTTPException(401, "Inicia sesión para continuar.")
    return {"usuario": {k: sesion[k] for k in ("usuario", "nombre", "rol")}, "csrf": sesion["csrf"],
            "expira_en": sesion["expira_en"]}


@router.post("/salir")
def salir(request: Request, respuesta: Response):
    usuarios().cerrar_sesion(request.cookies.get(COOKIE))
    respuesta.delete_cookie(COOKIE, path="/")
    return {"ok": True}


def _error(estado: int, mensaje: str) -> JSONResponse:
    return JSONResponse({"error": mensaje}, status_code=estado)


def instalar(app):
    @app.middleware("http")
    async def exigir_sesion(request: Request, siguiente):
        ruta = request.url.path
        if not config.AUTENTICACION or not ruta.startswith("/api/") or ruta in RUTAS_PUBLICAS \
                or ruta.startswith(PREFIJO_PUBLICO):
            return await siguiente(request)
        try:
            sesion = usuarios().sesion_vigente(request.cookies.get(COOKIE))
        except Exception:  # noqa: BLE001 — base caída: que responda el manejador de errores
            return _error(503, "La base de datos no responde; intente de nuevo en unos segundos.")
        if sesion is None:
            return _error(401, "Inicia sesión para continuar.")
        if request.method.upper() not in METODOS_SEGUROS and request.headers.get(CABECERA_CSRF) != sesion["csrf"]:
            return _error(403, "La solicitud no trae el token de seguridad de tu sesión. Recarga la página.")
        if ruta.startswith(SOLO_SUPERVISOR) and request.method.upper() not in METODOS_SEGUROS \
                and sesion["rol"] != "supervisor":
            return _error(403, "Esta acción es solo para el rol supervisor.")
        request.state.usuario = {k: sesion[k] for k in ("usuario", "nombre", "rol")}
        return await siguiente(request)


def usuario_de(request: Request) -> dict | None:
    """El usuario de la sesión (o None con la autenticación apagada en pruebas)."""
    return getattr(request.state, "usuario", None)


def firma_de(request: Request) -> str | None:
    """Cómo queda firmada una decisión: nombre y usuario de la sesión."""
    usuario = usuario_de(request)
    return f"{usuario['nombre']} ({usuario['usuario']})" if usuario else None
