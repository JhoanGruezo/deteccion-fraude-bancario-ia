"""Acciones sobre las tarjetas: bloquear, pedir verificación, desbloquear, avisar y alertar.

Aquí viven las guardas que no pueden depender del modelo de lenguaje (SPEC, RF3). Cada
acción lee de la BASE, dentro de la misma transacción y con la fila del caso bloqueada, todo
lo que decide si está permitida: la banda del caso, la tarjeta, si la autonomía del agente
está encendida y cuántos bloqueos autónomos van en la última hora. Nada de eso llega como
argumento desde el LLM; el agente solo aporta el motivo, y el motivo se valida aparte
(`app/riesgo/avisos.py`).

Resultados posibles de `bloquear` (campo "resultado"):

- "bloqueada": se creó el bloqueo y el caso quedó en estado "bloqueado".
- "ya_bloqueada": la tarjeta ya tenía un bloqueo activo de ese tipo; no se duplica (lo
  garantiza además el índice único parcial de la tabla).
- "no_permitido": el actor no puede bloquear este caso (por ejemplo, el agente en banda media,
  o un caso ya cerrado).
- "autonomia_apagada": el supervisor apagó la autonomía del agente.
- "tope_alcanzado": el agente llegó al tope de bloqueos autónomos por hora; queda una alerta.
"""

from datetime import datetime

import psycopg

from app.db.conexion import cursor
from app.db.repositorio import _fila, _filas, _json, enmascarar_tarjeta

BANDAS_QUE_EL_AGENTE_PUEDE_BLOQUEAR = ("alta", "critica")
ESTADOS_CERRADOS = ("descartado", "desbloqueado")


def _ajuste(cur, clave, por_defecto):
    cur.execute("select valor from ajustes_sistema where clave = %s", (clave,))
    fila = cur.fetchone()
    return fila["valor"] if fila else por_defecto


def ajustes():
    with cursor() as cur:
        cur.execute("select clave, valor, actualizado_por, actualizado_en from ajustes_sistema order by clave")
        return {f["clave"]: {k: v for k, v in f.items() if k != "clave"} for f in _filas(cur.fetchall())}


def cambiar_ajuste(clave, valor, usuario):
    with cursor() as cur:
        cur.execute("""update ajustes_sistema set valor = %s, actualizado_por = %s, actualizado_en = now()
                       where clave = %s returning clave""", (_json(valor), usuario, clave))
        if cur.fetchone() is None:
            raise KeyError(clave)


def registrar_alerta(cur, tipo, id_caso, detalle):
    cur.execute("insert into alertas (tipo, id_caso, detalle) values (%s, %s, %s) returning id",
                (tipo, id_caso, _json(detalle)))
    return cur.fetchone()["id"]


def nueva_alerta(tipo, id_caso, detalle):
    """Alerta para el supervisor, en su propia transacción."""
    with cursor() as cur:
        return registrar_alerta(cur, tipo, id_caso, detalle)


def alertas_pendientes(limite=50):
    with cursor() as cur:
        cur.execute("""select id, tipo, id_caso, detalle, creada_en from alertas
                       where atendida_en is null order by creada_en desc limit %s""", (limite,))
        return _filas(cur.fetchall())


def _caso_para_actuar(cur, id_caso):
    cur.execute("""select id_caso, fuente, id_cuenta, banda, estado, abierto_en, origen
                   from casos where id_caso = %s for update""", (id_caso,))
    return _fila(cur.fetchone())


def bloquear(id_caso, tipo, actor, motivo, tarea_id=None, usuario=None):
    """Bloquea la tarjeta (o el acceso) del caso si las guardas lo permiten. Ver docstring del módulo."""
    if tipo not in ("tarjeta", "acceso_cuenta"):
        raise ValueError(f"Tipo de bloqueo desconocido: {tipo}")
    with cursor() as cur:
        caso = _caso_para_actuar(cur, id_caso)
        if caso is None:
            return {"resultado": "no_permitido", "detalle": "El caso no existe."}
        if caso["estado"] in ESTADOS_CERRADOS:
            return {"resultado": "no_permitido", "detalle": f"El caso está {caso['estado']}."}
        if actor == "agente":
            if caso["banda"] not in BANDAS_QUE_EL_AGENTE_PUEDE_BLOQUEAR:
                return {"resultado": "no_permitido",
                        "detalle": f"En banda {caso['banda'] or 'sin banda'} el agente solo puede pedir verificación."}
            if not _ajuste(cur, "autonomia_agente", True):
                return {"resultado": "autonomia_apagada", "detalle": "El supervisor apagó la autonomía del agente."}
            tope = int(_ajuste(cur, "tope_bloqueos_autonomos_por_hora", 30))
            cur.execute("""select count(*) as n from bloqueos
                           where actor = 'agente' and creado_en > now() - interval '1 hour'""")
            if cur.fetchone()["n"] >= tope:
                registrar_alerta(cur, "tope_bloqueos_agente", id_caso, {"tope_por_hora": tope})
                return {"resultado": "tope_alcanzado",
                        "detalle": f"Se alcanzó el tope de {tope} bloqueos autónomos por hora; el caso pasa al supervisor."}
        cur.execute("""select id from bloqueos where fuente = %s and id_cuenta = %s and tipo = %s and estado = 'activo'""",
                    (caso["fuente"], caso["id_cuenta"], tipo))
        existente = cur.fetchone()
        if existente:
            return {"resultado": "ya_bloqueada", "bloqueo_id": existente["id"]}
        try:
            cur.execute(
                """insert into bloqueos (id_caso, fuente, id_cuenta, tipo, actor, usuario, banda, motivo, tarea_id,
                                         segundos_hasta_bloqueo)
                   values (%s, %s, %s, %s, %s, %s, %s, %s, %s,
                           extract(epoch from now() - coalesce(%s::timestamptz, now())))
                   returning id, segundos_hasta_bloqueo""",
                (id_caso, caso["fuente"], caso["id_cuenta"], tipo, actor, usuario, caso["banda"] or "media",
                 motivo[:600], tarea_id, caso["abierto_en"]),
            )
        except psycopg.errors.UniqueViolation:
            # Carrera con otro actor (agente y red de seguridad a la vez): ganó el otro.
            return {"resultado": "ya_bloqueada"}
        nuevo = _fila(cur.fetchone())
        cur.execute("update casos set estado = 'bloqueado' where id_caso = %s", (id_caso,))
    return {"resultado": "bloqueada", "bloqueo_id": nuevo["id"],
            "segundos_hasta_bloqueo": nuevo["segundos_hasta_bloqueo"],
            "tarjeta_enmascarada": enmascarar_tarjeta(caso["id_cuenta"]), "banda": caso["banda"]}


def marcar_en_verificacion(id_caso):
    """El caso queda esperando la respuesta del titular (solo si no está bloqueado ni cerrado)."""
    with cursor() as cur:
        cur.execute("""update casos set estado = 'en_verificacion'
                       where id_caso = %s and estado = 'pendiente' returning estado""", (id_caso,))
        return cur.fetchone() is not None


def desbloquear(bloqueo_id, usuario, motivo):
    """Levanta un bloqueo activo. Solo lo llama la API con un usuario autenticado (SPEC, RF6)."""
    with cursor() as cur:
        cur.execute("""update bloqueos set estado = 'levantado', levantado_por = %s, motivo_desbloqueo = %s,
                              levantado_en = now()
                       where id = %s and estado = 'activo'
                       returning id, id_caso, extract(epoch from levantado_en - creado_en) as segundos_bloqueada""",
                    (usuario, motivo, bloqueo_id))
        levantado = _fila(cur.fetchone())
        if levantado is None:
            return None
        cur.execute("""update casos set estado = 'desbloqueado' where id_caso = %s and not exists (
                           select 1 from bloqueos where id_caso = %s and estado = 'activo')""",
                    (levantado["id_caso"], levantado["id_caso"]))
    return levantado


# --- Avisos ------------------------------------------------------------------------------


def crear_notificacion(n):
    with cursor() as cur:
        cur.execute(
            """insert into notificaciones (id_caso, bloqueo_id, tipo, canal, destinatario, cuerpo, motivo_agente,
                                           autor_motivo, errores_validacion, estado)
               values (%(id_caso)s, %(bloqueo_id)s, %(tipo)s, %(canal)s, %(destinatario)s, %(cuerpo)s,
                       %(motivo_agente)s, %(autor_motivo)s, %(errores_validacion)s, 'pendiente')
               returning id""",
            {**n, "errores_validacion": _json(n.get("errores_validacion", []))},
        )
        return cur.fetchone()["id"]


def marcar_envio(notificacion_id, estado, detalle=None):
    with cursor() as cur:
        cur.execute("""update notificaciones set estado = %s, detalle_envio = %s,
                              enviada_en = case when %s = 'enviada' then now() else enviada_en end
                       where id = %s""", (estado, detalle, estado, notificacion_id))


def responder_notificacion(notificacion_id, respuesta):
    """Respuesta del titular ("fui_yo" o "no_fui_yo"); solo la primera cuenta."""
    with cursor() as cur:
        cur.execute("""update notificaciones set respuesta_titular = %s, respondida_en = now()
                       where id = %s and respuesta_titular is null returning id_caso""", (respuesta, notificacion_id))
        fila = cur.fetchone()
    return fila["id_caso"] if fila else None


def avisos_del_caso(id_caso):
    with cursor() as cur:
        cur.execute("""select id, tipo, canal, destinatario, cuerpo, autor_motivo, errores_validacion, estado,
                              respuesta_titular, respondida_en, creada_en
                       from notificaciones where id_caso = %s order by creada_en""", (id_caso,))
        return _filas(cur.fetchall())


# --- Red de seguridad ----------------------------------------------------------------------


def criticos_sin_bloqueo(segundos):
    """Casos en banda crítica que llevan más de `segundos` sin bloqueo activo y no están cerrados."""
    with cursor() as cur:
        cur.execute(
            """select c.id_caso from casos c
               where c.banda = 'critica' and c.estado <> all(%s) and c.estado <> 'bloqueado'
                 and c.banda_desde <= now() - make_interval(secs => %s)
                 and not exists (select 1 from bloqueos b where b.fuente = c.fuente and b.id_cuenta = c.id_cuenta
                                 and b.estado = 'activo')
               order by c.banda_desde""",
            (list(ESTADOS_CERRADOS), float(segundos)),
        )
        return [f["id_caso"] for f in cur.fetchall()]


def ahora_de_la_base() -> datetime:
    with cursor() as cur:
        cur.execute("select now() as ahora")
        return cur.fetchone()["ahora"]
