"""Usuarios y sesiones (SPEC, RF7): contraseñas con scrypt y sesiones guardadas solo como hash.

- **Contraseñas:** `hashlib.scrypt` de la biblioteca estándar (función lenta a propósito, con
  sal propia por usuario). Se guarda "scrypt$n$r$p$sal$hash"; nunca la contraseña.
- **Sesiones:** el navegador guarda un token al azar en una cookie HttpOnly; la base guarda
  solo su SHA-256. Si alguien lee la tabla `sesiones`, no puede usar ninguna sesión.
- **CSRF:** cada sesión tiene su propio token, que el frontend manda en la cabecera
  `X-CSRF-Token` en toda petición que cambie algo.

Los usuarios iniciales los crea `app/db/migrar.py` con el usuario dueño (el rol de la app no
puede crear ni modificar usuarios).
"""

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from app.db.conexion import cursor
from app.db.repositorio import _fila

PARAMETROS_SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1}


def derivar_clave(clave: str, sal: bytes | None = None) -> str:
    sal = sal or secrets.token_bytes(16)
    derivada = hashlib.scrypt(clave.encode("utf-8"), salt=sal, dklen=32, **PARAMETROS_SCRYPT)
    codificar = lambda b: base64.b64encode(b).decode("ascii")  # noqa: E731
    return f"scrypt${PARAMETROS_SCRYPT['n']}${PARAMETROS_SCRYPT['r']}${PARAMETROS_SCRYPT['p']}${codificar(sal)}${codificar(derivada)}"


def verificar_clave(clave: str, guardada: str) -> bool:
    try:
        _, n, r, p, sal, esperada = guardada.split("$")
        derivada = hashlib.scrypt(clave.encode("utf-8"), salt=base64.b64decode(sal), n=int(n), r=int(r), p=int(p),
                                  dklen=32)
        return hmac.compare_digest(derivada, base64.b64decode(esperada))
    except (ValueError, TypeError):
        return False


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# Hash de una contraseña que no existe: si el usuario no existe se verifica contra este, para que
# la respuesta tarde lo mismo y no delate qué usuarios existen.
_HASH_FICTICIO = derivar_clave(secrets.token_urlsafe(16))


def autenticar(usuario: str, clave: str) -> dict | None:
    """El usuario (sin su hash) si la contraseña es correcta y está activo; None si no."""
    with cursor() as cur:
        cur.execute("select usuario, nombre, rol, hash_clave, activo from usuarios where usuario = %s",
                    ((usuario or "").strip().lower(),))
        fila = _fila(cur.fetchone())
    valida = verificar_clave(clave or "", fila["hash_clave"] if fila else _HASH_FICTICIO)
    if not fila or not valida or not fila["activo"]:
        return None
    return {"usuario": fila["usuario"], "nombre": fila["nombre"], "rol": fila["rol"]}


def crear_sesion(usuario: str, horas: float) -> tuple[str, str, datetime]:
    """(token para la cookie, token CSRF, vencimiento)."""
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
    expira = datetime.now(timezone.utc) + timedelta(hours=horas)
    with cursor() as cur:
        cur.execute("insert into sesiones (token_hash, usuario, csrf, expira_en) values (%s, %s, %s, %s)",
                    (_hash_token(token), usuario, csrf, expira))
    return token, csrf, expira


def sesion_vigente(token: str | None) -> dict | None:
    """Usuario y CSRF de una sesión abierta y no vencida, o None."""
    if not token or len(token) > 200:
        return None
    with cursor() as cur:
        cur.execute(
            """select s.csrf, s.expira_en, u.usuario, u.nombre, u.rol
               from sesiones s join usuarios u using (usuario)
               where s.token_hash = %s and not s.cerrada and s.expira_en > now() and u.activo""",
            (_hash_token(token),))
        return _fila(cur.fetchone())


def cerrar_sesion(token: str | None) -> None:
    if not token:
        return
    with cursor() as cur:
        cur.execute("update sesiones set cerrada = true where token_hash = %s", (_hash_token(token),))
