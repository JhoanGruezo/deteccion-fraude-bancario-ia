"""Usuarios de Postgres con mínimo privilegio para la app y para el agente (SPEC, RS3).

Existe por la clase 12: un agente que entra a la base con el usuario administrador puede
hacer todo lo que ese usuario puede, y la única barrera queda en el prompt. Aquí la
barrera la pone Postgres:

| Rol | Qué puede | Qué no puede |
|---|---|---|
| `<base>_app` (la API) | Leer casos, transacciones e historial; escribir tareas, trazas, explicaciones, propuestas, decisiones, bloqueos, avisos, sesiones y transacciones en vivo; cambiar columnas puntuales (estado de un caso, desbloqueo) | Leer la etiqueta del dataset; borrar filas; cambiar el esquema; cambiar usuarios; reescribir montos o scores guardados |
| `<base>_agente` (herramientas del LLM) | Leer casos (sin la etiqueta), transacciones, historial y explicaciones | Escribir cualquier cosa |

El dueño de la base (`DATABASE_URL`, el usuario del compose) solo se usa para migrar y
para crear estos roles, en el arranque.

Decisiones:
- **Contraseñas nuevas en cada arranque**, al azar y solo en memoria: no hay que
  guardarlas en `.env` ni en el repositorio, y una contraseña filtrada deja de servir al
  reiniciar la app.
- **Nombres por base** (`fraude_app`, `fraude_pruebas_app`): los roles de Postgres son
  de todo el servidor, y así las pruebas, que crean su propia base, no le cambian la
  contraseña a la app que está corriendo.
- **Permisos de columna**: en `casos` y `transacciones_evaluadas` se concede SELECT
  columna por columna, todas menos las de la etiqueta (`COLUMNAS_ETIQUETA`). La lista se lee del catálogo en cada arranque, así
  que una columna nueva queda visible sin tocar este archivo, y la etiqueta nunca.
- **Revocar todo y volver a conceder** en cada arranque: si un permiso sobraba, desaparece.

Las tablas que se agreguen después deben sumarse a `PERMISOS`; si no, ningún rol podrá
usarlas y la prueba lo detecta.
"""

import logging
import secrets

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo

from app import config

registro = logging.getLogger("app.db.roles")

# Columnas con la etiqueta del dataset (la "respuesta correcta"): ningún rol de la app
# las puede leer. Solo eval/ las lee, con el usuario dueño.
COLUMNAS_ETIQUETA = {"fraude_confirmado_dataset", "es_fraude_dataset"}
TODAS = "*"
SIN_ETIQUETA = "sin_etiqueta"

# tabla → {privilegio: TODAS | SIN_ETIQUETA | [columnas]}
PERMISOS = {
    "app": {
        # Momento 2
        "casos": {"select": SIN_ETIQUETA, "insert": SIN_ETIQUETA,
                  "update": ["estado", "banda", "banda_desde", "score_maximo", "tipos_fraude",
                             "transacciones_sobre_umbral_bloqueo", "nivel_recomendacion",
                             "motivo_recomendacion", "senal_principal"]},
        "transacciones_caso": {"select": TODAS, "insert": TODAS},
        "historial": {"select": TODAS, "insert": TODAS},
        "tareas_agente": {"select": TODAS, "insert": TODAS, "update": TODAS},
        "trazas": {"select": TODAS, "insert": TODAS},
        "explicaciones": {"select": TODAS, "insert": TODAS},
        "propuestas_decision": {"select": TODAS, "insert": TODAS, "update": TODAS},
        "decisiones": {"select": TODAS, "insert": TODAS},
        # Momento 3. La etiqueta de transacciones_evaluadas se puede ESCRIBIR (la trae el
        # simulador, para medir) pero no leer.
        "perfiles_tarjeta": {"select": TODAS, "insert": TODAS, "update": TODAS},
        "transacciones_evaluadas": {"select": SIN_ETIQUETA, "insert": TODAS},
        "bloqueos": {"select": TODAS, "insert": TODAS,
                     "update": ["estado", "levantado_por", "motivo_desbloqueo", "levantado_en"]},
        "notificaciones": {"select": TODAS, "insert": TODAS,
                           "update": ["estado", "detalle_envio", "enviada_en", "respuesta_titular", "respondida_en"]},
        "usuarios": {"select": TODAS},
        "sesiones": {"select": TODAS, "insert": TODAS, "update": ["cerrada"]},
        "ajustes_sistema": {"select": TODAS, "update": ["valor", "actualizado_por", "actualizado_en"]},
        "alertas": {"select": TODAS, "insert": TODAS, "update": ["atendida_por", "atendida_en"]},
    },
    "agente": {
        "casos": {"select": SIN_ETIQUETA},
        "transacciones_caso": {"select": TODAS},
        "historial": {"select": TODAS},
        "explicaciones": {"select": TODAS},
    },
}
# Conexiones simultáneas máximas por rol (un poco más que el tamaño de su pool).
LIMITE_CONEXIONES = {"app": 15, "agente": 6}


def nombre_rol(base: str, rol: str) -> str:
    return f"{base}_{rol}"


def _columnas(cur, tabla: str) -> list[str]:
    cur.execute(
        "select column_name from information_schema.columns "
        "where table_schema = 'public' and table_name = %s order by ordinal_position",
        (tabla,),
    )
    return [fila[0] for fila in cur.fetchall()]


def _conceder(cur, privilegio: str, tabla: str, columnas, rol_bd: str):
    if columnas == TODAS:
        sentencia = sql.SQL("grant {} on table {} to {}").format(
            sql.SQL(privilegio), sql.Identifier(tabla), sql.Identifier(rol_bd))
    else:
        if columnas == SIN_ETIQUETA:
            columnas = [c for c in _columnas(cur, tabla) if c not in COLUMNAS_ETIQUETA]
        sentencia = sql.SQL("grant {} ({}) on table {} to {}").format(
            sql.SQL(privilegio), sql.SQL(", ").join(map(sql.Identifier, columnas)),
            sql.Identifier(tabla), sql.Identifier(rol_bd))
    cur.execute(sentencia)


def _preparar_rol(cur, base: str, rol: str, clave: str) -> str:
    rol_bd = nombre_rol(base, rol)
    cur.execute("select 1 from pg_roles where rolname = %s", (rol_bd,))
    accion = "alter" if cur.fetchone() else "create"
    cur.execute(sql.SQL(
        "{} role {} login nosuperuser nocreatedb nocreaterole noinherit noreplication "
        "connection limit {} password {}").format(
        sql.SQL(accion), sql.Identifier(rol_bd), sql.Literal(LIMITE_CONEXIONES[rol]), sql.Literal(clave)))
    # Revocar todo y volver a conceder: lo que sobraba de un arranque anterior desaparece.
    cur.execute(sql.SQL("revoke all on all tables in schema public from {}").format(sql.Identifier(rol_bd)))
    cur.execute(sql.SQL("revoke all on all sequences in schema public from {}").format(sql.Identifier(rol_bd)))
    cur.execute(sql.SQL("revoke create on schema public from {}").format(sql.Identifier(rol_bd)))
    cur.execute(sql.SQL("grant usage on schema public to {}").format(sql.Identifier(rol_bd)))
    cur.execute(sql.SQL("grant connect on database {} to {}").format(sql.Identifier(base), sql.Identifier(rol_bd)))
    for tabla, privilegios in PERMISOS[rol].items():
        for privilegio, columnas in privilegios.items():
            _conceder(cur, privilegio, tabla, columnas, rol_bd)
    if any("insert" in p for p in PERMISOS[rol].values()):
        # Los bigserial necesitan la secuencia para insertar.
        cur.execute(sql.SQL("grant usage on all sequences in schema public to {}").format(sql.Identifier(rol_bd)))
    return rol_bd


def aplicar_roles(url_administracion: str | None = None) -> dict:
    """Crea o actualiza los roles y devuelve {"activos", "roles", "urls" | "error"}.

    No lanza: si el usuario de DATABASE_URL no puede crear roles, la app sigue con él (como
    en el Momento 2) y el resultado lo explica para /api/salud.
    """
    url_administracion = url_administracion or config.DATABASE_URL
    claves = {rol: secrets.token_urlsafe(32) for rol in PERMISOS}
    try:
        with psycopg.connect(url_administracion, connect_timeout=5) as conexion:
            with conexion.cursor() as cur:
                cur.execute("select current_database()")
                base = cur.fetchone()[0]
                nombres = {rol: _preparar_rol(cur, base, rol, claves[rol]) for rol in PERMISOS}
    except psycopg.Error as error:
        detalle = str(error).strip().splitlines()[0] if str(error).strip() else type(error).__name__
        registro.warning("No se pudieron crear los roles de mínimo privilegio (%s). La app sigue con el "
                         "usuario de DATABASE_URL, como en el Momento 2.", detalle)
        return {"activos": False, "error": detalle}
    urls = {rol: make_conninfo(url_administracion, user=nombres[rol], password=claves[rol]) for rol in PERMISOS}
    registro.info("Roles de mínimo privilegio listos: %s.", ", ".join(nombres.values()))
    return {"activos": True, "roles": nombres, "urls": urls}
