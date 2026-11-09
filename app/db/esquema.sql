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

-- =====================================================================================
-- Momento 3 (docs/SPEC.md §6): puntuación en vivo, bloqueos, avisos, sesiones y ajustes.
-- Todo sigue siendo idempotente: sobre una base del Momento 2 solo agrega lo que falta.
-- =====================================================================================

-- Casos: los de la semilla (M2) y los que abre el motor en vivo. La banda la decide el
-- código (SPEC, RF2) y banda_desde es el reloj de la red de seguridad (RF4).
alter table casos add column if not exists origen text not null default 'semilla';
alter table casos add column if not exists banda text;
alter table casos add column if not exists banda_desde timestamptz;
alter table casos add column if not exists abierto_en timestamptz;
-- Los casos en vivo no guardan la etiqueta: la app no puede leerla ni sumarla. Para medir,
-- eval/ la toma de transacciones_evaluadas.es_fraude_dataset con el usuario dueño.
alter table casos alter column fraude_confirmado_dataset drop not null;
create sequence if not exists casos_en_vivo_seq;
alter table casos drop constraint if exists casos_origen_check;
alter table casos add constraint casos_origen_check check (origen in ('semilla', 'en_vivo'));
alter table casos drop constraint if exists casos_banda_check;
alter table casos add constraint casos_banda_check check (banda is null or banda in ('media', 'alta', 'critica'));
alter table casos drop constraint if exists casos_estado_check;
alter table casos add constraint casos_estado_check check (estado in (
    'pendiente', 'bloqueo_confirmado', 'descartado', 'escalado',     -- Momento 2
    'bloqueado', 'en_verificacion', 'desbloqueado'));                -- Momento 3

-- El triaje es el tercer tipo de tarea del agente.
alter table tareas_agente drop constraint if exists tareas_agente_tipo_check;
alter table tareas_agente add constraint tareas_agente_tipo_check
    check (tipo in ('explicacion', 'pregunta', 'triaje'));

-- Estado acumulado del perfil de cada tarjeta (app/riesgo/perfil_incremental.py): lo que
-- el banco sabe de ella antes de su próxima compra. Se actualiza en la misma transacción
-- que guarda la compra evaluada.
create table if not exists perfiles_tarjeta (
    fuente text not null,
    id_cuenta text not null,
    estado jsonb not null,
    actualizado_en timestamptz not null default now(),
    primary key (fuente, id_cuenta)
);

-- Cada transacción que entra en vivo (por el simulador o por la API), con su score, su
-- banda y cuánto tardó en decidirse. es_fraude_dataset es la etiqueta del dataset: la
-- escribe el simulador para poder medir después, pero ni la app ni el agente pueden
-- leerla (permisos de columna, app/db/roles.py).
create table if not exists transacciones_evaluadas (
    id bigserial primary key,
    fuente text not null,
    id_transaccion text not null,
    id_cuenta text not null,
    fecha_hora timestamp not null,
    monto numeric(14, 2) not null,
    categoria text, comercio text, ubicacion text,
    latitud double precision, longitud double precision,
    score double precision not null,
    banda text not null check (banda in ('sin_alerta', 'media', 'alta', 'critica')),
    viaje_imposible boolean not null default false,
    desviaciones jsonb not null default '[]',
    id_caso text references casos (id_caso),
    origen text not null check (origen in ('simulador', 'api')),
    latencia_puntuacion_ms double precision,
    latencia_total_ms double precision,
    recibida_en timestamptz not null default now(),
    es_fraude_dataset integer,
    unique (fuente, id_transaccion)
);
create index if not exists evaluadas_tarjeta on transacciones_evaluadas (fuente, id_cuenta, fecha_hora);
create index if not exists evaluadas_recientes on transacciones_evaluadas (recibida_en desc);

-- Bloqueos: quién bloqueó (agente, regla o analista), por qué y cuándo se levantó. El
-- índice único parcial impide dos bloqueos activos del mismo tipo sobre la misma tarjeta:
-- la idempotencia la garantiza la base, no el código que llama (SPEC, RF3, guarda 5).
create table if not exists bloqueos (
    id bigserial primary key,
    id_caso text not null references casos (id_caso),
    fuente text not null,
    id_cuenta text not null,
    tipo text not null check (tipo in ('tarjeta', 'acceso_cuenta')),
    actor text not null check (actor in ('agente', 'regla', 'analista')),
    usuario text,
    banda text not null,
    motivo text not null,
    tarea_id uuid references tareas_agente (tarea_id),
    segundos_hasta_bloqueo double precision,
    estado text not null default 'activo' check (estado in ('activo', 'levantado')),
    creado_en timestamptz not null default now(),
    levantado_por text,
    motivo_desbloqueo text,
    levantado_en timestamptz
);
create unique index if not exists un_bloqueo_activo on bloqueos (fuente, id_cuenta, tipo) where estado = 'activo';
create index if not exists bloqueos_caso on bloqueos (id_caso, creado_en desc);

-- Avisos al titular (SPEC, RF5). Se guarda lo que escribió el agente y lo que de verdad
-- salió, con el resultado de la validación, para poder auditar cada aviso.
create table if not exists notificaciones (
    id bigserial primary key,
    id_caso text not null references casos (id_caso),
    bloqueo_id bigint references bloqueos (id),
    tipo text not null check (tipo in ('bloqueo', 'verificacion')),
    canal text not null check (canal in ('simulado', 'correo')),
    destinatario text not null,
    cuerpo text not null,
    motivo_agente text,
    autor_motivo text not null check (autor_motivo in ('agente', 'plantilla')),
    errores_validacion jsonb not null default '[]',
    estado text not null default 'pendiente' check (estado in ('pendiente', 'enviada', 'fallida', 'retenida')),
    detalle_envio text,
    respuesta_titular text check (respuesta_titular in ('fui_yo', 'no_fui_yo')),
    respondida_en timestamptz,
    creada_en timestamptz not null default now(),
    enviada_en timestamptz
);
create index if not exists notificaciones_caso on notificaciones (id_caso, creada_en desc);

-- Usuarios y sesiones (SPEC, RF7). La contraseña se guarda derivada con scrypt y el token
-- de sesión solo como hash: si la base se filtra, ni las claves ni las sesiones sirven.
create table if not exists usuarios (
    usuario text primary key,
    nombre text not null,
    rol text not null check (rol in ('analista', 'supervisor')),
    hash_clave text not null,
    activo boolean not null default true,
    creado_en timestamptz not null default now()
);
create table if not exists sesiones (
    token_hash text primary key,
    usuario text not null references usuarios (usuario),
    csrf text not null,
    creada_en timestamptz not null default now(),
    expira_en timestamptz not null,
    cerrada boolean not null default false
);

-- Ajustes que el supervisor cambia en vivo (autonomía del agente, tope por hora).
create table if not exists ajustes_sistema (
    clave text primary key,
    valor jsonb not null,
    actualizado_por text,
    actualizado_en timestamptz not null default now()
);
insert into ajustes_sistema (clave, valor) values
    ('autonomia_agente', 'true'),
    ('tope_bloqueos_autonomos_por_hora', '30')
on conflict (clave) do nothing;

-- Alertas para el supervisor (tope alcanzado, red de seguridad que actuó, aviso retenido).
create table if not exists alertas (
    id bigserial primary key,
    tipo text not null,
    id_caso text references casos (id_caso),
    detalle jsonb not null default '{}',
    creada_en timestamptz not null default now(),
    atendida_por text,
    atendida_en timestamptz
);
create index if not exists alertas_pendientes on alertas (creada_en desc) where atendida_en is null;
