"""Pool de conexiones a Postgres compartido por toda la app.

Existe para que ni la API ni el agente abran una conexión por consulta: FastAPI
atiende los endpoints síncronos en un pool de hilos y el agente ejecuta herramientas
en hilos propios, así que varias consultas pueden ir en paralelo. Un ConnectionPool
de psycopg_pool reparte conexiones ya abiertas entre esos hilos y verifica que sigan
vivas antes de entregarlas (por si Postgres se reinició).

Solo app/db/repositorio.py y app/db/migrar.py usan este módulo.

TIMEOUT_POOL_S es corto a propósito: con la base caída, el valor por defecto de 15 s
dejaba cada petición colgada 15 s antes de un 500 genérico (validacion/app-analista.md).
Con 3 s la API responde rápido un 503 con un mensaje claro (manejador en principal.py)
y la interfaz puede avisar; con la base sana, obtener una conexión tarda milisegundos.
"""

import threading
from contextlib import contextmanager

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app import config

_pool = None
_candado = threading.Lock()

TIMEOUT_POOL_S = 3.0


def pool():
    """Devuelve el pool único (lo crea la primera vez con config.DATABASE_URL)."""
    global _pool
    if _pool is None:
        with _candado:
            if _pool is None:
                # Se lee config.DATABASE_URL en este momento (no al importar) para que
                # las pruebas puedan apuntar a una base propia antes de abrir el pool.
                _pool = ConnectionPool(
                    config.DATABASE_URL,
                    min_size=1,
                    max_size=10,
                    timeout=TIMEOUT_POOL_S,
                    check=ConnectionPool.check_connection,
                    open=True,
                    name="fraude",
                )
    return _pool


def cerrar_pool():
    """Cierra el pool (al apagar la app o entre pruebas que cambian de base)."""
    global _pool
    with _candado:
        if _pool is not None:
            _pool.close()
            _pool = None


@contextmanager
def cursor():
    """Cursor que devuelve filas como dict; hace commit al salir y rollback si hubo error.

    Todo lo que se ejecute dentro de un mismo "with cursor()" es UNA transacción: así
    resolver una propuesta y escribir la decisión no puede quedar a medias.
    """
    with pool().connection() as conexion:
        with conexion.cursor(row_factory=dict_row) as cur:
            yield cur
