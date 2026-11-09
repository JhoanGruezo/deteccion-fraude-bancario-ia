"""Consultas del flujo en vivo: perfiles de tarjeta, transacciones evaluadas y casos en vivo.

Va aparte de `repositorio.py` para no mezclar el camino crítico (cada transacción que
llega) con la bandeja del Momento 2, pero sigue la misma regla: todo el SQL de la app vive
en `app/db/`, explícito y sin ORM.

Las funciones de escritura reciben el cursor de una transacción que abre quien llama
(`app/riesgo/flujo.py`): leer el perfil, decidir la banda, abrir o actualizar el caso,
guardar la compra y actualizar el perfil ocurren en UNA transacción de Postgres. Si algo
falla a mitad, no queda una compra guardada con el perfil sin actualizar ni un caso a medias.

Para que dos compras simultáneas de la misma tarjeta no se pisen, el perfil se lee con
`for update`: la segunda espera a que termine la primera. Compras de tarjetas distintas
no se esperan entre sí.
"""

from contextlib import contextmanager

from app.db.conexion import cursor
from app.db.repositorio import _fila, _filas, _json, enmascarar_tarjeta

ESTADOS_CERRADOS = ("descartado", "desbloqueado")


@contextmanager
def transaccion():
    """Una transacción de Postgres (commit al salir, rollback si hubo error)."""
    with cursor() as cur:
        yield cur


# --- Perfiles de tarjeta -----------------------------------------------------------------


def perfil_para_actualizar(cur, fuente, id_cuenta):
    """Estado del perfil de la tarjeta, bloqueando su fila hasta el fin de la transacción."""
    cur.execute("select estado, alias from perfiles_tarjeta where fuente = %s and id_cuenta = %s for update",
                (fuente, id_cuenta))
    return _fila(cur.fetchone())


def tarjeta_por_alias(alias):
    """(fuente, id_cuenta) de un alias como TAR-0001, o None. El número no sale de aquí hacia la interfaz."""
    with cursor() as cur:
        cur.execute("select fuente, id_cuenta from perfiles_tarjeta where alias = %s", (alias.strip().upper(),))
        fila = cur.fetchone()
    return (fila["fuente"], fila["id_cuenta"]) if fila else None


def crear_perfil(cur, fuente, id_cuenta, estado, alias=None):
    cur.execute(
        """insert into perfiles_tarjeta (fuente, id_cuenta, estado, alias) values (%s, %s, %s, %s)
           on conflict (fuente, id_cuenta) do nothing""",
        (fuente, id_cuenta, _json(estado), alias),
    )


def guardar_perfil(cur, fuente, id_cuenta, estado):
    cur.execute("update perfiles_tarjeta set estado = %s, actualizado_en = now() where fuente = %s and id_cuenta = %s",
                (_json(estado), fuente, id_cuenta))


def estado_de(fuente, id_cuenta):
    """Estado del perfil (sin bloquear la fila), o {} si la tarjeta no tiene perfil."""
    with cursor() as cur:
        cur.execute("select estado from perfiles_tarjeta where fuente = %s and id_cuenta = %s", (fuente, id_cuenta))
        fila = cur.fetchone()
    return fila["estado"] if fila else {}


def listar_tarjetas(limite=50):
    """Tarjetas con perfil, solo con su alias y sus últimos 4 dígitos (para elegir a cuál inyectar)."""
    with cursor() as cur:
        cur.execute("""select alias, fuente, id_cuenta, (estado->>'n')::int as n_compras
                       from perfiles_tarjeta where alias is not null order by alias limit %s""", (limite,))
        filas = _filas(cur.fetchall())
    return [{"alias": f["alias"], "fuente": f["fuente"], "tarjeta_enmascarada": enmascarar_tarjeta(f["id_cuenta"]),
             "n_compras": f["n_compras"]} for f in filas]


# --- Bloqueos que afectan la autorización ------------------------------------------------


def bloqueo_activo(cur, fuente, id_cuenta):
    """El bloqueo activo de la tarjeta (de tarjeta o de acceso), o None."""
    cur.execute("""select id, tipo, actor, id_caso from bloqueos
                   where fuente = %s and id_cuenta = %s and estado = 'activo'
                   order by creado_en limit 1""", (fuente, id_cuenta))
    return _fila(cur.fetchone())


# --- Casos en vivo -----------------------------------------------------------------------


def caso_abierto(cur, fuente, id_cuenta, fecha_hora):
    """Caso en vivo de la tarjeta cuya ventana de 48 h contiene la compra (y que no se cerró)."""
    cur.execute(
        """select id_caso, inicio_ventana, fin_ventana, banda, estado, tipos_fraude
           from casos
           where origen = 'en_vivo' and fuente = %s and id_cuenta = %s
             and estado <> all(%s) and inicio_ventana <= %s and fin_ventana >= %s
           order by inicio_ventana desc limit 1 for update""",
        (fuente, id_cuenta, list(ESTADOS_CERRADOS), fecha_hora, fecha_hora),
    )
    return _fila(cur.fetchone())


def crear_caso(cur, caso):
    cur.execute("select nextval('casos_en_vivo_seq') as n")
    id_caso = f"VIV-{cur.fetchone()['n']:06d}"
    cur.execute(
        """insert into casos (
               id_caso, fuente, id_cuenta, inicio_ventana, fin_ventana, tipos_fraude, score_maximo,
               transacciones_sobre_umbral_bloqueo, nivel_recomendacion, motivo_recomendacion, senal_principal,
               perfil_previo, modelo, umbral_verificacion, umbral_bloqueo, origen, banda, banda_desde, abierto_en)
           values (%(id_caso)s, %(fuente)s, %(id_cuenta)s, %(inicio_ventana)s, %(fin_ventana)s, %(tipos_fraude)s,
                   %(score_maximo)s, %(transacciones_sobre_umbral_bloqueo)s, %(nivel_recomendacion)s,
                   %(motivo_recomendacion)s, %(senal_principal)s, %(perfil_previo)s, %(modelo)s,
                   %(umbral_verificacion)s, %(umbral_bloqueo)s, 'en_vivo', %(banda)s, now(), now())""",
        {**caso, "id_caso": id_caso, "perfil_previo": _json(caso["perfil_previo"])},
    )
    return id_caso


def actualizar_caso(cur, id_caso, cambios, subio_de_banda):
    """Actualiza las columnas que cambian al sumar una compra; reinicia el reloj si subió de banda."""
    columnas = ("tipos_fraude", "score_maximo", "transacciones_sobre_umbral_bloqueo", "nivel_recomendacion",
                "motivo_recomendacion", "senal_principal", "banda")
    asignaciones = ", ".join(f"{c} = %({c})s" for c in columnas)
    if subio_de_banda:
        asignaciones += ", banda_desde = now()"
    cur.execute(f"update casos set {asignaciones} where id_caso = %(id_caso)s",
                {**{c: cambios[c] for c in columnas}, "id_caso": id_caso})


def transacciones_del_caso(cur, id_caso):
    cur.execute("""select id_transaccion, fecha_hora, monto, score, viaje_imposible, desviaciones
                   from transacciones_caso where id_caso = %s order by fecha_hora, id_transaccion""", (id_caso,))
    return _filas(cur.fetchall())


def agregar_transaccion_al_caso(cur, id_caso, t):
    cur.execute(
        """insert into transacciones_caso (id_caso, id_transaccion, fecha_hora, monto, categoria, comercio, ubicacion,
                                           score, viaje_imposible, desviaciones)
           values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) on conflict do nothing""",
        (id_caso, t["id_transaccion"], t["fecha_hora"], t["monto"], t.get("categoria"), t.get("comercio"),
         t.get("ubicacion"), t["score"], t["viaje_imposible"], _json(t["desviaciones"])),
    )


# --- Transacciones evaluadas -------------------------------------------------------------


def guardar_en_historial(cur, fuente, id_cuenta, t):
    cur.execute(
        """insert into historial (fuente, id_cuenta, id_transaccion, fecha_hora, monto, categoria, comercio, ubicacion,
                                 origen)
           values (%s, %s, %s, %s, %s, %s, %s, %s, 'en_vivo') on conflict do nothing""",
        (fuente, id_cuenta, t["id_transaccion"], t["fecha_hora"], t["monto"], t.get("categoria"),
         t.get("comercio"), t.get("ubicacion")),
    )


def ya_evaluada(cur, fuente, id_transaccion):
    cur.execute("select id, decision, banda, id_caso from transacciones_evaluadas where fuente = %s and id_transaccion = %s",
                (fuente, id_transaccion))
    return _fila(cur.fetchone())


def guardar_evaluada(cur, registro):
    cur.execute(
        """insert into transacciones_evaluadas (
               fuente, id_transaccion, id_cuenta, fecha_hora, monto, categoria, comercio, ubicacion, latitud,
               longitud, score, banda, viaje_imposible, desviaciones, id_caso, origen, decision,
               latencia_puntuacion_ms, latencia_total_ms, es_fraude_dataset)
           values (%(fuente)s, %(id_transaccion)s, %(id_cuenta)s, %(fecha_hora)s, %(monto)s, %(categoria)s,
                   %(comercio)s, %(ubicacion)s, %(latitud)s, %(longitud)s, %(score)s, %(banda)s,
                   %(viaje_imposible)s, %(desviaciones)s, %(id_caso)s, %(origen)s, %(decision)s,
                   %(latencia_puntuacion_ms)s, %(latencia_total_ms)s, %(es_fraude_dataset)s)
           returning id, recibida_en""",
        {**registro, "desviaciones": _json(registro["desviaciones"])},
    )
    return _fila(cur.fetchone())


def ultimas_evaluadas(limite=100, desde_id=0):
    """Feed de la vista En vivo: las compras más recientes, sin el número de tarjeta."""
    with cursor() as cur:
        cur.execute(
            """select e.id, e.fuente, e.id_cuenta, p.alias, e.fecha_hora, e.monto, e.categoria, e.comercio,
                      e.score, e.banda, e.decision, e.id_caso, e.origen, e.latencia_total_ms, e.recibida_en
               from transacciones_evaluadas e
               left join perfiles_tarjeta p on p.fuente = e.fuente and p.id_cuenta = e.id_cuenta
               where e.id > %s order by e.id desc limit %s""",
            (desde_id, limite),
        )
        filas = _filas(cur.fetchall())
    for fila in filas:
        fila["tarjeta_enmascarada"] = enmascarar_tarjeta(fila.pop("id_cuenta"))
    return filas
