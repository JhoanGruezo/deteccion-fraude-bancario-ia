# Diseño — persistencia

Implementa `requisitos/persistencia.md`. Primera versión (2026-10-21). Las elecciones
técnicas las delegó el usuario ("elige lo mejor, con buena ingeniería"); quedan
justificadas aquí.

## Decisiones de esta sesión

- **Postgres 16 (imagen `postgres:16-alpine`) en `docker-compose`**, con volumen
  nombrado y healthcheck. La app espera a que la base esté sana antes de arrancar.
- **Migración y semilla automáticas al arrancar la app** (no en
  `docker-entrypoint-initdb.d`). La app aplica `esquema.sql` (idempotente, `create ...
  if not exists`) y, si la tabla `casos` está vacía, carga la semilla. Así funciona
  igual con un volumen nuevo o uno existente, y no duplica datos.
- **La semilla viaja en el ZIP como archivos de datos, no como SQL:** `semilla/`
  con los JSON de casos de cada fuente y el historial en CSV comprimido. Se genera
  una vez, desde la máquina que tiene los CSV de Kaggle, con
  `scripts/generar_semilla.py`. El evaluador no necesita el dataset.
- **psycopg 3 + psycopg_pool, SQL explícito, sin ORM.** El esquema es chico y estable;
  el SQL a la vista se sustenta mejor ante la pregunta "¿qué hace esta línea?".
- **Identificadores de caso con prefijo de fuente** (`SPK-000001`, `SIN-000001`): los
  dos JSON del motor numeran desde `C-000001` y chocarían.

## Dónde vive

```
docker-compose.yml                — servicios db y app
semilla/                          — generado; viaja en el ZIP
  casos_sparkov.json
  casos_sinteticos.json
  historial.csv.gz                — transacciones previas de las tarjetas con caso
  metricas_sparkov.json, metricas_sinteticos.json
scripts/generar_semilla.py        — datos/salidas_* + CSV de Kaggle → semilla/
app/db/
  esquema.sql
  conexion.py                     — pool de conexiones
  repositorio.py                  — TODAS las consultas de la app (única puerta a la BD)
  migrar.py                       — aplica esquema + carga semilla si hace falta
```

## Esquema (`app/db/esquema.sql`)

```sql
create table if not exists casos (
    id_caso text primary key,                     -- SPK-000001 / SIN-000001
    fuente text not null check (fuente in ('sparkov', 'sinteticos')),
    id_cuenta text not null,
    inicio_ventana timestamp not null,
    fin_ventana timestamp not null,
    tipos_fraude text[] not null,
    score_maximo double precision not null,
    transacciones_sobre_umbral_bloqueo integer not null,
    nivel_recomendacion text not null
        check (nivel_recomendacion in ('bloquear_tarjeta', 'bloquear_acceso_cuenta', 'verificar_cliente')),
    motivo_recomendacion text not null,
    senal_principal text not null,
    perfil_previo jsonb not null,
    modelo text not null,
    umbral_verificacion double precision not null,
    umbral_bloqueo double precision not null,
    fraude_confirmado_dataset integer not null,   -- nunca sale hacia la interfaz
    estado text not null default 'pendiente'
        check (estado in ('pendiente', 'bloqueo_confirmado', 'descartado', 'escalado'))
);
create index if not exists casos_filtros on casos (fuente, nivel_recomendacion, estado, score_maximo desc);

create table if not exists transacciones_caso (
    id_caso text not null references casos (id_caso),
    id_transaccion text not null,
    fecha_hora timestamp not null,
    monto numeric(14, 2) not null,
    categoria text, comercio text, ubicacion text,
    score double precision not null,
    viaje_imposible boolean not null,
    desviaciones jsonb not null,
    primary key (id_caso, id_transaccion)
);

create table if not exists historial (
    fuente text not null, id_cuenta text not null, id_transaccion text not null,
    fecha_hora timestamp not null, monto numeric(14, 2) not null,
    categoria text, comercio text, ubicacion text,
    primary key (fuente, id_transaccion)
);
create index if not exists historial_tarjeta on historial (fuente, id_cuenta, fecha_hora);

create table if not exists tareas_agente (
    tarea_id uuid primary key,
    id_caso text not null references casos (id_caso),
    tipo text not null check (tipo in ('explicacion', 'pregunta')),
    pregunta text,
    motivo_fin text,              -- completada | limite_iteraciones | limite_tokens | timeout | respaldo | error | rechazo
    iteraciones integer default 0,
    tokens_entrada integer default 0, tokens_salida integer default 0,
    costo_usd numeric(12, 6) default 0,
    latencia_ms integer, ttft_ms integer,
    proveedor_final text, modelo_final text,
    reintentos integer default 0, conmutaciones integer default 0,
    desde_cache boolean default false,
    falla_forzada text,
    creada_en timestamptz not null default now(),
    terminada_en timestamptz
);

create table if not exists trazas (
    id bigserial primary key,
    tarea_id uuid not null references tareas_agente (tarea_id),
    paso integer not null,
    tipo text not null,           -- los mismos tipos de evento del agente (diseno/agente.md)
    detalle jsonb not null,
    duracion_ms integer,
    creada_en timestamptz not null default now()
);
create index if not exists trazas_tarea on trazas (tarea_id, paso);

create table if not exists explicaciones (
    id bigserial primary key,
    id_caso text not null references casos (id_caso),
    tarea_id uuid references tareas_agente (tarea_id),
    contenido jsonb not null,     -- contrato validado (diseno/agente.md)
    es_respaldo boolean not null default false,
    proveedor text, modelo text,
    creada_en timestamptz not null default now()
);
create index if not exists explicaciones_caso on explicaciones (id_caso, creada_en desc);

create table if not exists propuestas_decision (
    id bigserial primary key,
    id_caso text not null references casos (id_caso),
    tarea_id uuid references tareas_agente (tarea_id),
    accion text not null check (accion in ('confirmar_bloqueo', 'descartar', 'escalar')),
    argumento text not null,
    estado text not null default 'pendiente' check (estado in ('pendiente', 'confirmada', 'rechazada')),
    creada_en timestamptz not null default now(),
    resuelta_en timestamptz
);

create table if not exists decisiones (
    id bigserial primary key,
    id_caso text not null references casos (id_caso),
    accion text not null check (accion in ('confirmar_bloqueo', 'descartar', 'escalar')),
    analista text not null,
    comentario text,
    propuesta_id bigint references propuestas_decision (id),
    creada_en timestamptz not null default now()
);
```

Estado del caso al registrar una decisión: `confirmar_bloqueo` → `bloqueo_confirmado`,
`descartar` → `descartado`, `escalar` → `escalado`. Las decisiones no se borran: la
vigente es la última.

## Semilla (`scripts/generar_semilla.py`)

Se corre desde la raíz con los CSV de Kaggle presentes:
`python scripts/generar_semilla.py`. Pasos:

1. Lee `datos/salidas_<fuente>/casos_marcados.json` y `metricas_motor.json` de las
   dos fuentes.
2. Reescribe `id_caso` con el prefijo de fuente y agrega a cada caso `fuente`,
   `modelo`, `umbral_verificacion` y `umbral_bloqueo` (de las métricas).
3. Arma el historial: para cada caso, las transacciones de su tarjeta en los **30
   días anteriores a `inicio_ventana`**, más las de la propia ventana que no quedaron
   marcadas (para que la línea de tiempo muestre todo lo que pasó). Usa
   `src/cargar_datos.py` para traducir columnas. Deduplica por transacción.
4. Escribe `semilla/` e imprime filas y tamaño en MB de cada archivo.

## `app/db/repositorio.py` — interfaz (la usan el agente y la API)

Todas las funciones reciben y devuelven tipos de Python (dict, list, str, int,
float, datetime convertido a texto ISO), nunca filas de psycopg. Montos en `float`.

```python
listar_casos(fuente=None, nivel=None, estado=None, busqueda=None, orden="score", limite=300) -> list[dict]
    # resumen: id_caso, fuente, tarjeta_enmascarada, inicio_ventana, nivel_recomendacion,
    # senal_principal, score_maximo, n_transacciones, monto_total, estado, tiene_explicacion
    # busqueda: id del caso (o un pedazo) o EXACTAMENTE los últimos 4 de la tarjeta; un
    # sufijo más largo no busca por tarjeta (servía para reconstruir el número completo)
contar_casos() -> dict        # por fuente, nivel y estado (para la cabecera)
obtener_caso(id_caso) -> dict | None
    # caso completo SIN fraude_confirmado_dataset y con tarjeta enmascarada;
    # incluye "transacciones": [... con desviaciones ...]
obtener_caso_para_evaluacion(id_caso) -> dict | None   # incluye fraude_confirmado_dataset (solo eval/)
obtener_historial(id_caso, dias=30, limite=60) -> list[dict]
    # transacciones de la tarjeta del caso antes y durante la ventana, orden cronológico,
    # cada una con "en_caso": bool
crear_tarea(tarea_id, id_caso, tipo, pregunta=None, falla_forzada=None) -> None
cerrar_tarea(tarea_id, **metricas) -> None
registrar_traza(tarea_id, paso, tipo, detalle: dict, duracion_ms=None) -> None
listar_trazas(tarea_id) -> list[dict]
ultima_tarea(id_caso) -> dict | None
explicacion_vigente(id_caso) -> dict | None   # la más reciente: contenido, es_respaldo, proveedor, modelo, creada_en, tarea_id
guardar_explicacion(id_caso, tarea_id, contenido: dict, es_respaldo, proveedor, modelo) -> int
crear_propuesta(id_caso, tarea_id, accion, argumento) -> dict
propuestas_pendientes(id_caso) -> list[dict]
resolver_propuesta(propuesta_id, confirmar: bool, analista, comentario=None) -> dict
registrar_decision(id_caso, accion, analista, comentario=None, propuesta_id=None) -> dict
decisiones_del_caso(id_caso) -> list[dict]
resumen_metricas(desde=None) -> dict
    # sobre tareas_agente terminadas (fórmulas completas en el docstring y en la clave "definiciones"):
    # tasa de éxito = completadas sin plantilla / tareas que NO salieron de caché;
    # % desde caché aparte; mediana y P90 de latencia y TTFT sin las de caché;
    # costo total y por tarea; recuperación = recuperadas / con fallo, donde con fallo =
    # reintentos, conmutaciones, fin respaldo/error/timeout o algún contrato_invalido en
    # trazas, y recuperada = terminó completada o con plantilla guardada
```

Tarjeta enmascarada: `**** **** **** 1234` (últimos 4 dígitos).

`conexion.py` expone `pool()` (singleton `ConnectionPool` con `DATABASE_URL`, espera
máxima de 3 s por una conexión: con la base caída la API responde 503 "La base de datos
no responde…" en vez de colgarse 15 s) y un
context manager `cursor()` que hace commit al salir. `migrar.py` expone
`preparar_base()` y se puede correr solo: `python -m app.db.migrar`.

## Integración

- La API llama a `migrar.preparar_base()` al arrancar (evento de inicio de FastAPI).
- Nadie más que `repositorio.py` escribe SQL.
- `docker-compose.yml`: el servicio `db` lleva `POSTGRES_DB=fraude`,
  `POSTGRES_USER=fraude`, `POSTGRES_PASSWORD` desde `.env` (con valor por defecto
  solo de desarrollo), volumen `datos_postgres` y healthcheck `pg_isready`. El
  servicio `app` construye desde `app/Dockerfile` con contexto en la raíz (necesita
  `app/` y `semilla/`), expone el puerto 8000 y depende de `db` con
  `condition: service_healthy`.

## Manejo de errores

- Base no disponible al arrancar: la app reintenta la conexión 10 veces con espera
  creciente y, si no, termina con un mensaje claro en el log (no una traza).
- Semilla ausente: la app arranca, la bandeja queda vacía y `/api/salud` lo informa.
- Carga parcial interrumpida: la semilla se carga en una sola transacción.

## Cómo se valida

1. `docker compose up` en una carpeta limpia deja 339 casos (287 de Sparkov + 52 de sintéticos, o los de la
   corrida vigente) y el historial cargado.
2. Reiniciar no duplica filas.
3. Tres casos al azar: desviaciones idénticas a los JSON del motor.
4. Tamaño de `semilla/` reportado.
