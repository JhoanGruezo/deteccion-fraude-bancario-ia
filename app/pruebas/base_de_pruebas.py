"""Bases de datos desechables para las pruebas que necesitan Postgres de verdad.

Cada módulo de pruebas crea su propia base (junto a la de DATABASE_URL), la migra y la
borra al terminar, junto con sus roles de mínimo privilegio. Así las pruebas no se
ensucian entre sí ni tocan la base de la demo.
"""

import os
import re
from contextlib import contextmanager

import psycopg
from psycopg import sql

from app import config
from app.db import conexion, migrar, roles


def url_con_base(url, base):
    """Cambia el nombre de la base en una URL postgresql://usuario:clave@host:puerto/base."""
    return re.sub(r"/[^/?]+(\?|$)", f"/{base}\\1", url, count=1) if url.count("/") >= 3 else url + "/" + base


def _recrear(url_administracion, base):
    with psycopg.connect(url_administracion, autocommit=True) as administracion:
        administracion.execute(sql.SQL("drop database if exists {} with (force)").format(sql.Identifier(base)))
        administracion.execute(sql.SQL("create database {}").format(sql.Identifier(base)))


def _borrar(url_administracion, base):
    with psycopg.connect(url_administracion, autocommit=True) as administracion:
        administracion.execute(sql.SQL("drop database if exists {} with (force)").format(sql.Identifier(base)))
        for rol in roles.PERMISOS:
            administracion.execute(sql.SQL("drop role if exists {}").format(sql.Identifier(roles.nombre_rol(base, rol))))


@contextmanager
def base_migrada(nombre, carpeta_semilla=None):
    """Base nueva y migrada (con la semilla indicada, o vacía si la carpeta no la tiene)."""
    url_original = os.environ.get("DATABASE_URL", config.DATABASE_URL)
    _recrear(url_original, nombre)
    conexion.cerrar_pool()
    config.DATABASE_URL = url_con_base(url_original, nombre)
    try:
        yield migrar.preparar_base(carpeta_semilla=carpeta_semilla)
    finally:
        conexion.cerrar_pool()
        config.DATABASE_URL = url_original
        _borrar(url_original, nombre)


def como_dueno(consulta, parametros=()):
    """Ejecuta una consulta con el usuario dueño de la base actual (para verificar, no para la app)."""
    with psycopg.connect(config.DATABASE_URL) as dueno:
        return dueno.execute(consulta, parametros).fetchall()
