"""Pools de conexiones a Postgres, uno por rol de la base (mínimo privilegio).

Existe para que ni la API ni el agente abran una conexión por consulta: FastAPI
atiende los endpoints síncronos en un pool de hilos y el agente ejecuta herramientas
en hilos propios, así que varias consultas pueden ir en paralelo. Un ConnectionPool
de psycopg_pool reparte conexiones ya abiertas entre esos hilos y verifica que sigan
vivas antes de entregarlas (por si Postgres se reinició).

**Roles (SPEC, RS3; clase 12, "mínimo privilegio real").** La app ya no trabaja con el
usuario dueño de la base. Al arrancar, `app/db/roles.py` crea dos usuarios con permisos
mínimos y guarda aquí cómo conectarse con cada uno:

- `app`: lo que necesita la API (leer casos sin la etiqueta del dataset, escribir
  tareas, trazas, explicaciones, propuestas y decisiones). No puede borrar ni cambiar el
  esquema.
- `agente`: lo que usan las herramientas del LLM. **Solo lectura**, y sin la columna
  `fraude_confirmado_dataset`. Aunque una inyección lograra que el modelo pidiera
  otra cosa, la base no se lo permitiría.

Cuál pool usa una consulta lo decide `usar_rol()`, una variable de contexto: el
repositorio no cambia, y `app/db/repositorio_agente.py` envuelve las lecturas del
agente en `usar_rol("agente")`. Si los roles no se pudieron crear (por ejemplo, una
base donde el usuario no puede crear roles, o las pruebas unitarias), todo cae en
`config.DATABASE_URL`, como en el Momento 2, y /api/salud lo informa.

Solo app/db/repositorio.py, app/db/roles.py y app/db/migrar.py usan este módulo.

TIMEOUT_POOL_S es corto a propósito: con la base caída, el valor por defecto de 15 s
dejaba cada petición colgada 15 s antes de un 500 genérico (validacion/app-analista.md).
Con 3 s la API responde rápido un 503 con un mensaje claro (manejador en principal.py)
y la interfaz puede avisar; con la base sana, obtener una conexión tarda milisegundos.
"""

import contextvars
import threading
from contextlib import contextmanager

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app import config

ROLES = ("app", "agente")
TIMEOUT_POOL_S = 3.0
TAMANO_MAXIMO = {"app": 10, "agente": 4}

_pools: dict[str, ConnectionPool] = {}
_urls_por_rol: dict[str, str] = {}
_candado = threading.Lock()
_rol_actual: contextvars.ContextVar[str] = contextvars.ContextVar("rol_base", default="app")


def configurar_roles(urls: dict[str, str]) -> None:
    """Fija la cadena de conexión de cada rol y cierra los pools abiertos con la anterior."""
    with _candado:
        _cerrar_todos()
        _urls_por_rol.clear()
        _urls_por_rol.update(urls)


def roles_activos() -> bool:
    """True si la app trabaja con los roles de mínimo privilegio (y no con el dueño de la base)."""
    return all(rol in _urls_por_rol for rol in ROLES)


def _url_de(rol: str) -> str:
    # Se lee config.DATABASE_URL en este momento (no al importar) para que las pruebas
    # puedan apuntar a una base propia antes de abrir el pool.
    return _urls_por_rol.get(rol) or config.DATABASE_URL


def pool(rol: str | None = None) -> ConnectionPool:
    """Devuelve el pool del rol pedido (o del rol del contexto); lo crea la primera vez."""
    rol = rol or _rol_actual.get()
    if rol not in ROLES:
        raise ValueError(f"Rol de base desconocido: {rol}")
    existente = _pools.get(rol)
    if existente is not None:
        return existente
    with _candado:
        if rol not in _pools:
            _pools[rol] = ConnectionPool(
                _url_de(rol),
                min_size=1,
                max_size=TAMANO_MAXIMO[rol],
                timeout=TIMEOUT_POOL_S,
                check=ConnectionPool.check_connection,
                open=True,
                name=f"fraude_{rol}",
            )
        return _pools[rol]


def _cerrar_todos():
    for abierto in _pools.values():
        abierto.close()
    _pools.clear()


def cerrar_pool():
    """Cierra los pools (al apagar la app o entre pruebas que cambian de base) y olvida los roles."""
    with _candado:
        _cerrar_todos()
        _urls_por_rol.clear()


@contextmanager
def usar_rol(rol: str):
    """Hace que las consultas de este bloque (en este hilo) usen el pool del rol indicado."""
    if rol not in ROLES:
        raise ValueError(f"Rol de base desconocido: {rol}")
    marca = _rol_actual.set(rol)
    try:
        yield
    finally:
        _rol_actual.reset(marca)


@contextmanager
def cursor():
    """Cursor que devuelve filas como dict; hace commit al salir y rollback si hubo error.

    Todo lo que se ejecute dentro de un mismo "with cursor()" es UNA transacción: así
    resolver una propuesta y escribir la decisión no puede quedar a medias. Usa el pool
    del rol del contexto (por defecto, "app").
    """
    with pool().connection() as conexion:
        with conexion.cursor(row_factory=dict_row) as cur:
            yield cur
