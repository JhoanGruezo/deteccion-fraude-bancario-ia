-- Esquema de la base del analista (diseno/persistencia.md).
--
-- Es idempotente (todo "if not exists") porque la app lo aplica en CADA arranque
-- (app/db/migrar.py): así funciona igual con un volumen de Postgres nuevo que con
-- uno que ya tiene datos, sin pasos manuales ni scripts de initdb.
--
-- Tablas de datos del motor (se llenan una vez desde semilla/):
--   casos, transacciones_caso, historial
-- Tablas que escribe la app mientras se usa:
--   tareas_agente, trazas, explicaciones, propuestas_decision, decisiones

-- Un caso = las transacciones marcadas de una tarjeta en una ventana de 48 h, con la
-- recomendación de la regla determinista del motor.
create table if not exists casos (
    id_caso text primary key,                     -- SPK-000001 / SIN-000001
    fuente text not null check (fuente in ('sparkov', 'sinteticos')),
    id_cuenta text not null,                      -- número completo: solo sale enmascarado
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
    fraude_confirmado_dataset integer not null,   -- nunca sale hacia la interfaz (solo eval/)
    estado text not null default 'pendiente'
        check (estado in ('pendiente', 'bloqueo_confirmado', 'descartado', 'escalado'))
);
create index if not exists casos_filtros on casos (fuente, nivel_recomendacion, estado, score_maximo desc);

-- Transacciones marcadas de cada caso, con sus desviaciones tal como las escribió el
-- motor (contribución, percentil, relevante): es la evidencia que cita el agente.
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

-- Historial de las tarjetas con caso (30 días antes de la ventana + la ventana), para
-- que el agente pueda narrar la secuencia que desembocó en la alerta.
create table if not exists historial (
    fuente text not null, id_cuenta text not null, id_transaccion text not null,
    fecha_hora timestamp not null, monto numeric(14, 2) not null,
    categoria text, comercio text, ubicacion text,
    primary key (fuente, id_transaccion)
);
create index if not exists historial_tarjeta on historial (fuente, id_cuenta, fecha_hora);

-- Una tarea = una ejecución del agente (explicar un caso o responder una pregunta),
-- con las métricas que se reportan en vivo (latencia, TTFT, costo, caché, fallos).
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
create index if not exists tareas_caso on tareas_agente (id_caso, creada_en desc);

-- Cada evento del agente (salvo los fragmentos de texto), en orden.
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

-- Varias versiones por caso (botón regenerar); la vigente es la más reciente.
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

-- Lo único que el agente puede escribir: una propuesta que espera confirmación humana.
-- resuelta_por y comentario_resolucion guardan quién la confirmó o la rechazó (un
-- rechazo no deja fila en decisiones, y sin estas columnas se perdería el analista).
create table if not exists propuestas_decision (
    id bigserial primary key,
    id_caso text not null references casos (id_caso),
    tarea_id uuid references tareas_agente (tarea_id),
    accion text not null check (accion in ('confirmar_bloqueo', 'descartar', 'escalar')),
    argumento text not null,
    estado text not null default 'pendiente' check (estado in ('pendiente', 'confirmada', 'rechazada')),
    resuelta_por text,
    comentario_resolucion text,
    creada_en timestamptz not null default now(),
    resuelta_en timestamptz
);
create index if not exists propuestas_caso on propuestas_decision (id_caso, estado);

-- Decisiones del analista. No se borran: la vigente es la última.
create table if not exists decisiones (
    id bigserial primary key,
    id_caso text not null references casos (id_caso),
    accion text not null check (accion in ('confirmar_bloqueo', 'descartar', 'escalar')),
    analista text not null,
    comentario text,
    propuesta_id bigint references propuestas_decision (id),
    creada_en timestamptz not null default now()
);
create index if not exists decisiones_caso on decisiones (id_caso, creada_en);
