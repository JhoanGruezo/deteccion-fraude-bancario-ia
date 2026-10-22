"""Única puerta a la base de datos: todas las consultas de la app viven aquí.

Existe para que la API y el agente no escriban SQL (diseno/persistencia.md,
"Integración") y para que dos reglas de privacidad se cumplan en un solo lugar:

1. La tarjeta nunca sale completa: todo lo que va hacia afuera la trae enmascarada
   ("**** **** **** 1234").
2. fraude_confirmado_dataset (la etiqueta del dataset) nunca llega a la interfaz ni
   al agente: si el agente la viera, su "explicación" podría apoyarse en la respuesta
   correcta en lugar de en la evidencia. Solo obtener_caso_para_evaluacion la
   devuelve, y la usa eval/.

Todas las funciones reciben y devuelven tipos de Python (dict, list, str, int, float,
bool, None); las fechas salen como texto ISO y los montos como float. Nunca se
devuelven filas de psycopg. SQL explícito y a la vista, sin ORM.
"""

import json
import uuid
from datetime import date, datetime
from decimal import Decimal

from psycopg.types.json import Jsonb

from app.db.conexion import cursor

ACCIONES = ("confirmar_bloqueo", "descartar", "escalar")
# Estado en que queda el caso según la acción de la decisión vigente.
ESTADO_POR_ACCION = {
    "confirmar_bloqueo": "bloqueo_confirmado",
    "descartar": "descartado",
    "escalar": "escalado",
}
LIMITE_MAXIMO_BANDEJA = 1000

# Columnas de tareas_agente que cerrar_tarea acepta, y nombres alternativos que puede
# usar quien llama (el evento "fin" del agente dice "proveedor"/"modelo").
METRICAS_TAREA = {
    "motivo_fin", "iteraciones", "tokens_entrada", "tokens_salida", "costo_usd", "latencia_ms",
    "ttft_ms", "proveedor_final", "modelo_final", "reintentos", "conmutaciones", "desde_cache",
    "falla_forzada",
}
ALIAS_METRICAS = {"proveedor": "proveedor_final", "modelo": "modelo_final"}

# Motivos de fin que cuentan como "la tarea tuvo un fallo" para la tasa de recuperación.
MOTIVOS_DE_FALLO = ("respaldo", "error", "timeout")

# Fórmulas de /api/metricas, en palabras, para que quien las lea no tenga que adivinar.
DEFINICIONES_METRICAS = {
    "tasa_exito": "exitosas / tareas_sin_cache; exitosa = motivo_fin 'completada' sin plantilla; "
                  "las servidas desde caché no cuentan (se reportan en porcentaje_desde_cache)",
    "porcentaje_desde_cache": "100 × tareas desde caché / n_tareas",
    "latencia_y_ttft": "mediana y P90 (percentile_cont) de las tareas que no salieron de caché; TTFT = "
                       "primer fragmento de la llamada que produjo la respuesta final",
    "recuperacion": "recuperadas / tareas_con_fallo; con fallo = reintentos > 0, conmutaciones > 0, "
                    "motivo_fin respaldo/error/timeout o algún contrato_invalido en la traza; recuperada "
                    "= terminó 'completada' o con una explicación de plantilla guardada",
    "costo_por_tarea_usd": "costo de lista total / n_tareas (incluye las de caché, que cuestan 0)",
}


class ErrorRepositorio(Exception):
    """Base de los errores de negocio del repositorio (la API los traduce a HTTP)."""


class CasoNoEncontrado(ErrorRepositorio, LookupError):
    """El id_caso no existe (la API responde 404)."""


class PropuestaNoEncontrada(ErrorRepositorio, LookupError):
    """La propuesta no existe (la API responde 404)."""


class PropuestaYaResuelta(ErrorRepositorio):
    """La propuesta ya se confirmó o se rechazó antes (la API responde 409)."""


# --- Conversión de filas a tipos de Python ---------------------------------------------


def _a_python(valor):
    """Convierte un valor que devuelve psycopg a algo serializable en JSON."""
    if isinstance(valor, (datetime, date)):
        return valor.isoformat()
    if isinstance(valor, Decimal):
        return float(valor)
    if isinstance(valor, uuid.UUID):
        return str(valor)
    return valor


def _fila(fila):
    if fila is None:
        return None
    return {clave: _a_python(valor) for clave, valor in fila.items()}


def _filas(filas):
    return [_fila(fila) for fila in filas]


def _json(valor):
    # default=str: si una traza trae un datetime o un UUID, se guarda como texto en
    # lugar de romper la tarea por un detalle de serialización.
    return Jsonb(valor, dumps=lambda objeto: json.dumps(objeto, ensure_ascii=False, default=str))


def enmascarar_tarjeta(id_cuenta):
    """'4512345678901234' → '**** **** **** 1234'. Los ids cortos (sintéticos) se rellenan con ceros."""
    return "**** **** **** " + str(id_cuenta).zfill(4)[-4:]


def _con_tarjeta_enmascarada(fila):
    """Reemplaza id_cuenta por tarjeta_enmascarada en un dict que va hacia afuera."""
    fila["tarjeta_enmascarada"] = enmascarar_tarjeta(fila.pop("id_cuenta"))
    return fila


# --- Casos -----------------------------------------------------------------------------


def listar_casos(fuente=None, nivel=None, estado=None, busqueda=None, orden="score", limite=300):
    """Bandeja del analista: un resumen por caso, filtrado y ordenado.

    busqueda: coincide con el id del caso (SPK-000123, también un pedazo) o con
    EXACTAMENTE los últimos 4 dígitos de la tarjeta (lo único que el analista ve de
    ella). Antes se aceptaba un sufijo de cualquier largo (`like '%texto'`) y eso
    servía de oráculo: respondiendo sí/no a sufijos cada vez más largos se podía
    reconstruir el número completo dígito a dígito (validacion/app-analista.md).
    orden: "score" (mayor riesgo primero) o "fecha" (ventana más reciente primero).
    """
    condiciones = []
    parametros = {}
    if fuente:
        condiciones.append("c.fuente = %(fuente)s")
        parametros["fuente"] = fuente
    if nivel:
        condiciones.append("c.nivel_recomendacion = %(nivel)s")
        parametros["nivel"] = nivel
    if estado:
        condiciones.append("c.estado = %(estado)s")
        parametros["estado"] = estado
    if busqueda and busqueda.strip():
        texto = busqueda.strip()
        parametros["patron_caso"] = f"%{texto}%"
        if len(texto) == 4 and texto.isdigit():
            # Misma regla que enmascarar_tarjeta: ids cortos (sintéticos) rellenos con ceros.
            # lpad con greatest(...) porque lpad a secas TRUNCA los textos más largos que 4.
            condiciones.append("(c.id_caso ilike %(patron_caso)s or "
                               "right(lpad(c.id_cuenta, greatest(length(c.id_cuenta), 4), '0'), 4) = %(ultimos4)s)")
            parametros["ultimos4"] = texto
        else:
            condiciones.append("c.id_caso ilike %(patron_caso)s")
    donde = ("where " + " and ".join(condiciones)) if condiciones else ""
    # El orden se elige de una lista cerrada: nunca se interpola texto del usuario en el SQL.
    ordenar = "c.inicio_ventana desc, c.id_caso" if orden == "fecha" else "c.score_maximo desc, c.id_caso"
    parametros["limite"] = max(1, min(int(limite or 300), LIMITE_MAXIMO_BANDEJA))

    with cursor() as cur:
        cur.execute(
            f"""
            select c.id_caso, c.fuente, c.id_cuenta, c.inicio_ventana, c.nivel_recomendacion,
                   c.senal_principal, c.score_maximo, c.estado,
                   t.n_transacciones, t.monto_total,
                   exists (select 1 from explicaciones e where e.id_caso = c.id_caso) as tiene_explicacion
            from casos c
            join lateral (
                select count(*) as n_transacciones, coalesce(sum(tc.monto), 0) as monto_total
                from transacciones_caso tc
                where tc.id_caso = c.id_caso
            ) t on true
            {donde}
            order by {ordenar}
            limit %(limite)s
            """,
            parametros,
        )
        return [_con_tarjeta_enmascarada(fila) for fila in _filas(cur.fetchall())]


def contar_casos():
    """Contadores de la cabecera: total y casos por fuente, por nivel y por estado."""
    with cursor() as cur:
        cur.execute(
            """
            select fuente, nivel_recomendacion, estado, count(*) as n
            from casos
            group by fuente, nivel_recomendacion, estado
            """
        )
        filas = cur.fetchall()
    resultado = {"total": 0, "por_fuente": {}, "por_nivel": {}, "por_estado": {}}
    for fila in filas:
        resultado["total"] += fila["n"]
        for clave, columna in [("por_fuente", "fuente"), ("por_nivel", "nivel_recomendacion"), ("por_estado", "estado")]:
            resultado[clave][fila[columna]] = resultado[clave].get(fila[columna], 0) + fila["n"]
    return resultado


def _leer_caso(id_caso, con_etiqueta):
    with cursor() as cur:
        cur.execute(
            """
            select id_caso, fuente, id_cuenta, inicio_ventana, fin_ventana, tipos_fraude, score_maximo,
                   transacciones_sobre_umbral_bloqueo, nivel_recomendacion, motivo_recomendacion,
                   senal_principal, perfil_previo, modelo, umbral_verificacion, umbral_bloqueo,
                   fraude_confirmado_dataset, estado
            from casos
            where id_caso = %s
            """,
            (id_caso,),
        )
        caso = _fila(cur.fetchone())
        if caso is None:
            return None
        cur.execute(
            """
            select id_transaccion, fecha_hora, monto, categoria, comercio, ubicacion,
                   score, viaje_imposible, desviaciones
            from transacciones_caso
            where id_caso = %s
            order by fecha_hora, id_transaccion
            """,
            (id_caso,),
        )
        caso["transacciones"] = _filas(cur.fetchall())
    if not con_etiqueta:
        # Se quita aquí, no en el SELECT, para que sea imposible olvidarla en una
        # consulta nueva: la única ruta que la conserva es la de evaluación.
        caso.pop("fraude_confirmado_dataset")
    return _con_tarjeta_enmascarada(caso)


def obtener_caso(id_caso):
    """Caso completo para la interfaz y el agente: SIN fraude_confirmado_dataset y con la tarjeta enmascarada.

    Incluye "transacciones" (orden cronológico), cada una con sus desviaciones tal
    como las escribió el motor.
    """
    return _leer_caso(id_caso, con_etiqueta=False)


def obtener_caso_para_evaluacion(id_caso):
    """Igual que obtener_caso pero con fraude_confirmado_dataset. Solo para eval/."""
    return _leer_caso(id_caso, con_etiqueta=True)


def obtener_historial(id_caso, dias=30, limite=60):
    """Transacciones de la tarjeta del caso antes y durante la ventana, en orden cronológico.

    Cada una trae "en_caso" (si es una de las transacciones marcadas del caso) y su
    score cuando lo es. Si hay más de `limite`, se devuelven las más cercanas a la
    ventana (las más antiguas son las que menos dicen de la alerta). Lista vacía si
    la tarjeta no tiene historial (tarjeta nueva) o el caso no existe.
    """
    dias = max(0, int(dias))
    limite = max(1, int(limite))
    with cursor() as cur:
        cur.execute(
            """
            with caso as (
                select id_caso, fuente, id_cuenta, inicio_ventana, fin_ventana from casos where id_caso = %(id_caso)s
            ),
            -- Historial de la tarjeta, más las transacciones del caso por si alguna no
            -- estuviera en el historial (la semilla las incluye, pero no se asume).
            movimientos as (
                select h.id_transaccion, h.fecha_hora, h.monto, h.categoria, h.comercio, h.ubicacion
                from historial h, caso
                where h.fuente = caso.fuente and h.id_cuenta = caso.id_cuenta
                  and h.fecha_hora >= caso.inicio_ventana - make_interval(days => %(dias)s::int)
                  and h.fecha_hora <= caso.fin_ventana
                union all
                select tc.id_transaccion, tc.fecha_hora, tc.monto, tc.categoria, tc.comercio, tc.ubicacion
                from transacciones_caso tc join caso using (id_caso)
                where not exists (
                    select 1 from historial h2
                    where h2.fuente = caso.fuente and h2.id_transaccion = tc.id_transaccion
                )
            ),
            recientes as (
                select m.*, tc.score, (tc.id_transaccion is not null) as en_caso
                from movimientos m
                left join transacciones_caso tc
                       on tc.id_caso = %(id_caso)s and tc.id_transaccion = m.id_transaccion
                order by m.fecha_hora desc, m.id_transaccion desc
                limit %(limite)s
            )
            select * from recientes order by fecha_hora, id_transaccion
            """,
            {"id_caso": id_caso, "dias": dias, "limite": limite},
        )
        return _filas(cur.fetchall())


# --- Tareas del agente y trazas --------------------------------------------------------


def crear_tarea(tarea_id, id_caso, tipo, pregunta=None, falla_forzada=None):
    """Registra el inicio de una tarea del agente (tipo "explicacion" o "pregunta")."""
    with cursor() as cur:
        cur.execute(
            """
            insert into tareas_agente (tarea_id, id_caso, tipo, pregunta, falla_forzada)
            values (%s, %s, %s, %s, %s)
            """,
            (str(tarea_id), id_caso, tipo, pregunta, falla_forzada or None),
        )


def cerrar_tarea(tarea_id, **metricas):
    """Guarda las métricas finales de la tarea y marca terminada_en.

    Acepta las columnas de tareas_agente (motivo_fin, iteraciones, tokens_entrada,
    tokens_salida, costo_usd, latencia_ms, ttft_ms, proveedor_final, modelo_final,
    reintentos, conmutaciones, desde_cache, falla_forzada); también "proveedor" y
    "modelo" como alias de proveedor_final/modelo_final. Las claves desconocidas se
    ignoran: el evento "fin" del agente puede traer más datos de los que se guardan.
    """
    valores = {}
    for clave, valor in metricas.items():
        columna = ALIAS_METRICAS.get(clave, clave)
        if columna in METRICAS_TAREA and columna not in valores:
            valores[columna] = valor
    # Las columnas salen de la lista cerrada METRICAS_TAREA, nunca del llamador.
    asignaciones = ", ".join(f"{columna} = %({columna})s" for columna in valores)
    asignaciones = (asignaciones + ", " if asignaciones else "") + "terminada_en = now()"
    with cursor() as cur:
        cur.execute(
            f"update tareas_agente set {asignaciones} where tarea_id = %(tarea_id)s",
            {**valores, "tarea_id": str(tarea_id)},
        )


def registrar_traza(tarea_id, paso, tipo, detalle, duracion_ms=None):
    """Guarda un evento del agente (los mismos tipos que van por SSE, salvo "token")."""
    with cursor() as cur:
        cur.execute(
            "insert into trazas (tarea_id, paso, tipo, detalle, duracion_ms) values (%s, %s, %s, %s, %s)",
            (str(tarea_id), paso, tipo, _json(detalle if detalle is not None else {}), duracion_ms),
        )


def listar_trazas(tarea_id):
    """Traza completa de una tarea, en el orden en que ocurrió."""
    with cursor() as cur:
        cur.execute(
            """
            select id, tarea_id, paso, tipo, detalle, duracion_ms, creada_en
            from trazas
            where tarea_id = %s
            order by paso, id
            """,
            (str(tarea_id),),
        )
        return _filas(cur.fetchall())


def ultima_tarea(id_caso):
    """La tarea más reciente del caso (con todas sus métricas), o None."""
    with cursor() as cur:
        cur.execute(
            "select * from tareas_agente where id_caso = %s order by creada_en desc limit 1",
            (id_caso,),
        )
        return _fila(cur.fetchone())


# --- Explicaciones ---------------------------------------------------------------------


def explicacion_vigente(id_caso):
    """La explicación vigente del caso (la que se muestra y sirve de caché), o None.

    Prefiere la más reciente generada por la IA sobre cualquier plantilla de respaldo:
    una caída pasajera del proveedor no debe tapar una explicación buena que ya existía.
    """
    with cursor() as cur:
        cur.execute(
            """
            select id, id_caso, tarea_id, contenido, es_respaldo, proveedor, modelo, creada_en
            from explicaciones
            where id_caso = %s
            order by es_respaldo asc, creada_en desc, id desc
            limit 1
            """,
            (id_caso,),
        )
        return _fila(cur.fetchone())


def guardar_explicacion(id_caso, tarea_id, contenido, es_respaldo, proveedor, modelo):
    """Guarda una versión nueva de la explicación (las anteriores se conservan). Devuelve su id."""
    with cursor() as cur:
        cur.execute(
            """
            insert into explicaciones (id_caso, tarea_id, contenido, es_respaldo, proveedor, modelo)
            values (%s, %s, %s, %s, %s, %s)
            returning id
            """,
            (id_caso, str(tarea_id) if tarea_id else None, _json(contenido), bool(es_respaldo), proveedor, modelo),
        )
        return cur.fetchone()["id"]


# --- Propuestas y decisiones -----------------------------------------------------------

_COLUMNAS_PROPUESTA = """
    id, id as propuesta_id, id_caso, tarea_id, accion, argumento, estado,
    resuelta_por, comentario_resolucion, creada_en, resuelta_en
"""


def _validar_accion(accion):
    if accion not in ACCIONES:
        raise ValueError(f"Acción no válida: {accion}. Use una de: {', '.join(ACCIONES)}.")


def _validar_analista(analista):
    if not analista or not str(analista).strip():
        raise ValueError("Falta el nombre del analista.")
    return str(analista).strip()


def crear_propuesta(id_caso, tarea_id, accion, argumento):
    """Lo que hace la herramienta registrar_decision del agente: una propuesta PENDIENTE.

    Nunca escribe en decisiones; la decisión solo existe cuando un analista confirma
    la propuesta (resolver_propuesta). Devuelve la propuesta (con "id" y su alias
    "propuesta_id").
    """
    _validar_accion(accion)
    with cursor() as cur:
        cur.execute(
            f"""
            insert into propuestas_decision (id_caso, tarea_id, accion, argumento)
            values (%s, %s, %s, %s)
            returning {_COLUMNAS_PROPUESTA}
            """,
            (id_caso, str(tarea_id) if tarea_id else None, accion, argumento),
        )
        return _fila(cur.fetchone())


def propuestas_pendientes(id_caso):
    """Propuestas del agente que esperan confirmación humana, de la más antigua a la más nueva."""
    with cursor() as cur:
        cur.execute(
            f"""
            select {_COLUMNAS_PROPUESTA}
            from propuestas_decision
            where id_caso = %s and estado = 'pendiente'
            order by creada_en, id
            """,
            (id_caso,),
        )
        return _filas(cur.fetchall())


def _insertar_decision(cur, id_caso, accion, analista, comentario, propuesta_id):
    """Escribe la decisión y deja el caso en el estado que le corresponde (misma transacción)."""
    cur.execute(
        """
        insert into decisiones (id_caso, accion, analista, comentario, propuesta_id)
        values (%s, %s, %s, %s, %s)
        returning id, id_caso, accion, analista, comentario, propuesta_id, creada_en
        """,
        (id_caso, accion, analista, comentario, propuesta_id),
    )
    decision = _fila(cur.fetchone())
    cur.execute(
        "update casos set estado = %s where id_caso = %s returning estado",
        (ESTADO_POR_ACCION[accion], id_caso),
    )
    decision["estado_caso"] = cur.fetchone()["estado"]
    return decision


def resolver_propuesta(propuesta_id, confirmar, analista, comentario=None):
    """Confirmación humana de una propuesta del agente (el cuarto límite del agente).

    confirmar=True: la propuesta queda "confirmada" y se escribe la decisión con su
    acción, que cambia el estado del caso. confirmar=False: queda "rechazada" y no se
    escribe ninguna decisión. Todo ocurre en una transacción, con la propuesta
    bloqueada (FOR UPDATE) para que dos clics simultáneos no generen dos decisiones.

    Devuelve la propuesta actualizada con la clave "decision" (dict o None).
    Lanza PropuestaNoEncontrada, PropuestaYaResuelta o ValueError (sin analista).
    """
    analista = _validar_analista(analista)
    with cursor() as cur:
        cur.execute(
            "select id, id_caso, accion, estado from propuestas_decision where id = %s for update",
            (propuesta_id,),
        )
        actual = cur.fetchone()
        if actual is None:
            raise PropuestaNoEncontrada(f"No existe la propuesta {propuesta_id}.")
        if actual["estado"] != "pendiente":
            raise PropuestaYaResuelta(f"La propuesta {propuesta_id} ya fue {actual['estado']}.")

        cur.execute(
            f"""
            update propuestas_decision
            set estado = %s, resuelta_por = %s, comentario_resolucion = %s, resuelta_en = now()
            where id = %s
            returning {_COLUMNAS_PROPUESTA}
            """,
            ("confirmada" if confirmar else "rechazada", analista, comentario, propuesta_id),
        )
        propuesta = _fila(cur.fetchone())
        propuesta["decision"] = (
            _insertar_decision(cur, actual["id_caso"], actual["accion"], analista, comentario, propuesta_id)
            if confirmar
            else None
        )
        return propuesta


def registrar_decision(id_caso, accion, analista, comentario=None, propuesta_id=None):
    """Decisión del analista (manual, o la que resulta de confirmar una propuesta).

    No borra decisiones anteriores: queda el historial y la vigente es la última.
    Devuelve la decisión con "estado_caso". Lanza CasoNoEncontrado o ValueError.
    """
    _validar_accion(accion)
    analista = _validar_analista(analista)
    with cursor() as cur:
        cur.execute("select 1 from casos where id_caso = %s for update", (id_caso,))
        if cur.fetchone() is None:
            raise CasoNoEncontrado(f"No existe el caso {id_caso}.")
        return _insertar_decision(cur, id_caso, accion, analista, comentario, propuesta_id)


def decisiones_del_caso(id_caso):
    """Todas las decisiones del caso en orden cronológico (la última es la vigente)."""
    with cursor() as cur:
        cur.execute(
            """
            select id, id_caso, accion, analista, comentario, propuesta_id, creada_en
            from decisiones
            where id_caso = %s
            order by creada_en, id
            """,
            (id_caso,),
        )
        return _filas(cur.fetchall())


# --- Métricas en vivo ------------------------------------------------------------------


def resumen_metricas(desde=None):
    """Las cifras de medición de la app, calculadas sobre tareas_agente terminadas.

    Fórmulas (también van en la respuesta, clave "definiciones"):

    - tasa_exito = exitosas / tareas_sin_cache. exitosa = motivo_fin "completada" y
      sin explicación de plantilla. tareas_sin_cache = tareas que NO salieron de la
      caché: una apertura desde caché no ejercita al agente, y contarla como éxito
      inflaba la tasa (0,667 frente a 0,622 en la validación del 2026-10-21).
    - porcentaje_desde_cache = 100 × desde_cache / n_tareas (el ahorro, aparte).
    - latencia y TTFT (mediana y P90, con percentile_cont): solo tareas que no
      salieron de caché (no tienen TTFT y bajarían la mediana artificialmente). El
      TTFT es el de la llamada que produjo la respuesta final (ver agente/bucle.py).
    - costo total y por tarea (de lista, en USD; por tarea = total / n_tareas).
    - recuperación = recuperadas / tareas_con_fallo. con fallo = reintentos > 0,
      conmutaciones > 0, motivo_fin en MOTIVOS_DE_FALLO, o al menos un evento
      contrato_invalido en `trazas` (antes un JSON roto o un contrato inválido que el
      reintento arreglaba no se veía como fallo). recuperada = terminó "completada" o
      dejó una explicación de plantilla guardada (el analista recibió algo válido).

    Las tareas sin cerrar (sin terminada_en, por ejemplo si la base se cayó a mitad)
    no entran en ninguna cifra.

    desde: fecha o texto ISO; si se da, solo cuenta tareas creadas desde entonces.
    """
    with cursor() as cur:
        cur.execute(
            """
            with base as (
                select t.*,
                       coalesce(t.desde_cache, false) as de_cache,
                       exists (select 1 from explicaciones e
                               where e.tarea_id = t.tarea_id and e.es_respaldo) as con_plantilla,
                       exists (select 1 from trazas tr
                               where tr.tarea_id = t.tarea_id and tr.tipo = 'contrato_invalido') as con_contrato_invalido
                from tareas_agente t
                where t.terminada_en is not null
                  and (%(desde)s::timestamptz is null or t.creada_en >= %(desde)s::timestamptz)
            ),
            tareas as (
                select b.*,
                       (b.motivo_fin = 'completada' and not b.con_plantilla) as exitosa,
                       (coalesce(b.reintentos, 0) > 0 or coalesce(b.conmutaciones, 0) > 0
                        or b.motivo_fin = any(%(motivos_fallo)s) or b.con_contrato_invalido) as con_fallo
                from base b
            )
            select
                count(*) as n_tareas,
                count(*) filter (where not de_cache) as n_sin_cache,
                count(*) filter (where exitosa and not de_cache) as n_exitosas,
                count(*) filter (where de_cache) as n_desde_cache,
                percentile_cont(0.5) within group (order by latencia_ms) filter (where not de_cache) as latencia_mediana_ms,
                percentile_cont(0.9) within group (order by latencia_ms) filter (where not de_cache) as latencia_p90_ms,
                percentile_cont(0.5) within group (order by ttft_ms) filter (where not de_cache) as ttft_mediana_ms,
                percentile_cont(0.9) within group (order by ttft_ms) filter (where not de_cache) as ttft_p90_ms,
                coalesce(sum(costo_usd), 0) as costo_total_usd,
                coalesce(sum(tokens_entrada), 0) as tokens_entrada,
                coalesce(sum(tokens_salida), 0) as tokens_salida,
                count(*) filter (where con_fallo) as n_con_fallo,
                count(*) filter (where con_fallo and (motivo_fin = 'completada' or con_plantilla)) as n_recuperadas
            from tareas
            """,
            {"desde": desde, "motivos_fallo": list(MOTIVOS_DE_FALLO)},
        )
        fila = _fila(cur.fetchone())
        cur.execute(
            """
            select coalesce(motivo_fin, 'sin_motivo') as motivo_fin, count(*) as n
            from tareas_agente
            where terminada_en is not null
              and (%(desde)s::timestamptz is null or creada_en >= %(desde)s::timestamptz)
            group by 1
            """,
            {"desde": desde},
        )
        por_motivo = {f["motivo_fin"]: f["n"] for f in cur.fetchall()}

    n = fila["n_tareas"]

    def proporcion(parte, total):
        return round(parte / total, 4) if total else None

    def redondear(valor):
        return round(valor, 1) if valor is not None else None

    return {
        "desde": _a_python(desde) if desde is not None else None,
        "n_tareas": n,
        "tareas_sin_cache": fila["n_sin_cache"],
        "exitosas": fila["n_exitosas"],
        "tasa_exito": proporcion(fila["n_exitosas"], fila["n_sin_cache"]),
        "latencia_mediana_ms": redondear(fila["latencia_mediana_ms"]),
        "latencia_p90_ms": redondear(fila["latencia_p90_ms"]),
        "ttft_mediana_ms": redondear(fila["ttft_mediana_ms"]),
        "ttft_p90_ms": redondear(fila["ttft_p90_ms"]),
        "costo_total_usd": round(fila["costo_total_usd"], 6),
        "costo_por_tarea_usd": round(fila["costo_total_usd"] / n, 6) if n else None,
        "porcentaje_desde_cache": round(100 * fila["n_desde_cache"] / n, 1) if n else None,
        "tokens_entrada": fila["tokens_entrada"],
        "tokens_salida": fila["tokens_salida"],
        "tasa_recuperacion": proporcion(fila["n_recuperadas"], fila["n_con_fallo"]),
        "recuperacion": {
            "tareas_con_fallo": fila["n_con_fallo"],
            "recuperadas": fila["n_recuperadas"],
            "tasa": proporcion(fila["n_recuperadas"], fila["n_con_fallo"]),
        },
        "por_motivo_fin": por_motivo,
        "definiciones": DEFINICIONES_METRICAS,
    }
