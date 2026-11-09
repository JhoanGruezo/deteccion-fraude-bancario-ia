# Especificación del Momento 3: detectar, bloquear a tiempo y desbloquear con criterio humano

Versión 1 · 2026-11-08 · Equipo: Jhoan David Gruezo Gutiérrez y Jeison Nazarit.
Entrega: jueves 19-nov-2026, 23:59 (aula virtual). Presentación: sábado 21-nov-2026.

Este documento fija **qué** se entrega en el Momento 3 y con qué criterios se da por
bueno. El **porqué** de cada decisión está en `docs/analisis-respuesta-fraude.md` (ritmo
del fraude, capacidad de los analistas y norma) y en `docs/decisiones.md`. El **orden de
trabajo** está en `PLAN.md`.

---

## 1. Objetivo

Que una tarjeta robada quede bloqueada **en menos de 5 minutos desde la compra
sospechosa, de día o de noche y con o sin analistas disponibles**, que el titular sepa
por qué, y que una persona autenticada decida el desbloqueo. Todo con defensas en la
arquitectura que resistan la inyección directa e indirecta, el abuso de consumo y el
exceso de permisos (clase 12).

Origen: comentario del profesor tras la sustentación del Momento 2 (2026-10-31), su
aclaración posterior (el agente LLM puede bloquear las tarjetas de mayor riesgo y avisar
al titular, porque con 20 analistas y 15 casos cada uno muchos casos se verían tarde) y
la clase 12 (2026-11-07), donde anunció pruebas de seguridad masivas sobre la app.

## 2. Alcance y renegociaciones

No existe una especificación escrita en la semana 4. Esta tabla deja constancia de qué
cambió desde la idea inicial y por qué, para que el criterio de alcance se compare
contra lo que sí se acordó.

| Idea inicial | Lo que se entrega | Por qué cambió |
|---|---|---|
| Interfaz de consultas libres al modelo | Agente con herramientas dentro de la vista del analista | Feedback del profesor del 2026-10-10: el agente va dentro de la vista del analista |
| Dataset PaySim | Sparkov (Kaggle) | PaySim casi no repite cuentas: sin historial por tarjeta no hay perfil (2026-10-21) |
| Streamlit | FastAPI + SSE real + frontend propio + Postgres | Streaming real y trazas visibles; Streamlit no daba SSE de verdad (2026-10-21) |
| Gemini como modelo principal | Claude Haiku 5.5 principal, Gemini de respaldo, plantilla sin red | Latencia y saturación medidas (2026-10-21 y 2026-10-31) |
| El analista confirma todo bloqueo (M2) | El sistema y el agente bloquean; el analista desbloquea | Comentario del profesor del 2026-10-31 y análisis de tiempos |
| El caso se abre con 2 compras marcadas | El caso se abre con la **primera** compra marcada | La segunda compra llegaba a los 100 min (mediana) y dejaba pasar el 13 % del monto |
| Casos precalculados por el motor | Cada transacción se puntúa en vivo dentro de la app | Sin puntuación en vivo no hay tiempo hasta el bloqueo que medir |
| Sin inicio de sesión (M2) | Inicio de sesión con roles analista y supervisor | El desbloqueo y la autonomía del agente necesitan un responsable autenticado |
| Servidor MCP propio | Fuera de alcance (opcional) | Prioridad a la seguridad y al flujo de bloqueo |

**Fuera de alcance:** canales reales de SMS o push, conexión con un switch transaccional
real, integración con un core bancario, datos de bancos reales, aprendizaje en línea del
modelo, despliegue en la nube.

## 3. Actores y roles

| Actor | Qué puede hacer |
|---|---|
| **Motor de riesgo** (código + ML) | Puntuar cada transacción, asignar la banda, abrir casos y aplicar la red de seguridad |
| **Agente de triaje** (LLM) | Leer la evidencia del caso abierto; en las bandas permitidas, bloquear la tarjeta o el acceso, pedir verificación o dejar el caso al analista; redactar el motivo del aviso. **No puede desbloquear** |
| **Analista** (sesión iniciada) | Ver casos, bloqueos y avisos; desbloquear con motivo; confirmar, descartar o escalar; preguntarle al agente |
| **Supervisor** (sesión iniciada) | Todo lo del analista, más: apagar o encender la autonomía del agente, ver el tope y el gasto del día, levantar el tope, usar el panel de fallas de la demo |
| **Titular** (simulado) | Recibir el aviso en el buzón simulado y responder "fui yo" o "no fui yo" |

## 4. Requisitos funcionales

### RF1. Puntuación en vivo de cada transacción

- `POST /api/transacciones` recibe una transacción (tarjeta, fecha y hora, monto,
  comercio, categoría, coordenadas del comercio) y responde con el score, la banda, las
  señales y, si corresponde, el caso abierto o actualizado.
- El perfil previo se calcula solo con las transacciones **anteriores** de esa tarjeta
  guardadas en la base (regla de oro del perfil, `CLAUDE.md`), con las mismas funciones
  del motor (`src/perfil_cuenta.py`, `src/motor_riesgo.py`) y el mismo modelo
  (`modelo_riesgo.joblib`, que pasa a `semilla/`).
- **Paridad:** para las transacciones de prueba de Sparkov, el score en vivo es igual al
  del motor fuera de línea (diferencia ≤ 0,001).
- El detector de viaje imposible corre en cada transacción (código determinista).
- La puntuación no depende del LLM ni de la red.

### RF2. Bandas y apertura del caso

| Banda | Condición (la evalúa el código) | Qué se permite |
|---|---|---|
| **Crítica** | ≥ 2 compras sobre el umbral de bloqueo en 48 h, o viaje imposible | Bloqueo obligatorio |
| **Alta** | Primera compra sobre el umbral de bloqueo | El agente decide si bloquea |
| **Media** | Score entre el umbral de verificación y el de bloqueo | Solo verificación con el titular |
| Sin alerta | Score bajo el umbral de verificación | Nada |

- El caso se abre en la primera compra en banda media o superior. Las compras siguientes
  de la misma tarjeta dentro de 48 h se suman al caso y pueden subirlo de banda.
- Los umbrales vienen del paquete del modelo, no se escriben a mano.

### RF3. Triaje del agente

- Al abrirse un caso, o al subir de banda, se lanza en segundo plano una tarea de
  **triaje**. No espera a ningún analista ni a ninguna pantalla abierta.
- El agente tiene herramientas de lectura (las del M2) y estas acciones:
  - `bloquear_tarjeta(motivo_para_titular)` y `bloquear_acceso_cuenta(motivo_para_titular)`:
    solo en banda alta o crítica;
  - `solicitar_verificacion(motivo_para_titular)`: en cualquier banda;
  - `dejar_a_analista(razon)`: el caso queda en la cola humana sin acción automática.
- **Guardas en código** (no en el prompt):
  1. la tarjeta o cuenta afectada sale del contexto del caso, nunca de un argumento del
     modelo;
  2. la herramienta revisa la banda en la base antes de actuar y devuelve
     `no_permitido` si no corresponde;
  3. hay un **tope de bloqueos autónomos por hora**. Al llegar al tope, la herramienta
     devuelve `tope_alcanzado`, el caso sube a la cola del supervisor y queda una alerta;
  4. si el supervisor apagó la autonomía, las acciones devuelven `autonomia_apagada` y
     el caso pasa a la cola humana;
  5. una sola acción de bloqueo por caso; repetirla no duplica nada;
  6. ninguna herramienta desbloquea.
- Límites de la tarea: los cuatro del M2 (iteraciones, tokens, timeout, herramientas por
  vuelta), más el **tope de gasto diario en USD**. Pasado el tope, el triaje cae a la regla.

### RF4. Red de seguridad

- Si un caso en banda **crítica** no está bloqueado **90 segundos** después de entrar en
  esa banda, el código lo bloquea con el actor `regla` y envía el aviso de plantilla.
  Esto cubre que el proveedor esté caído, que salte un límite, que la autonomía esté
  apagada o que el agente haya decidido no bloquear.
- Si el triaje de un caso en banda **alta** o **media** falla, el código envía una
  solicitud de verificación de plantilla y deja el caso en la cola humana.
- La red de seguridad corre aunque no haya ninguna pestaña abierta.

### RF5. Aviso al titular

- El código arma el aviso con una plantilla fija: saludo, tarjeta enmascarada
  (`•••• 1234`), qué se hizo (bloqueo o verificación), el **motivo** que escribió el
  agente y el teléfono oficial del banco, que sale de la configuración.
- **Validación del motivo** antes de guardarlo: máximo 300 caracteres; sin URL, dominios,
  correos ni teléfonos; sin números de tarjeta; los montos citados deben existir en la
  evidencia del caso. Si no pasa, se usa el motivo de plantilla y queda registrado.
- **Destinatario:** lo resuelve el código a partir de la tarjeta, con un directorio de
  contactos simulado. El agente no ve ni elige el destinatario.
- **Canales:** `simulado` por defecto (buzón dentro de la app). Opcionalmente `correo`
  por SMTP, y solo a direcciones de la lista blanca `CORREOS_PERMITIDOS`. Si falta la
  lista o la dirección no está en ella, no sale nada y queda registrado.
- El titular responde en el buzón con "fui yo" o "no fui yo". "No fui yo" marca el
  bloqueo como confirmado por el titular. "Fui yo" pone el caso primero en la cola de
  desbloqueo. Ninguna de las dos respuestas desbloquea sola.

### RF6. Desbloqueo humano

- Solo un analista o supervisor con sesión iniciada puede levantar un bloqueo, y debe
  escribir un motivo (mínimo 10 caracteres). Queda registrado quién, cuándo y por qué.
- Se mide el tiempo hasta el desbloqueo.
- Las decisiones del M2 se conservan: confirmar, descartar y escalar.

### RF7. Inicio de sesión y roles

- Usuarios en la base con contraseña derivada con `hashlib.scrypt` (biblioteca estándar)
  y sal propia. Sesión en una cookie `HttpOnly`, `SameSite=Strict`, firmada, con vencimiento.
- **Protección CSRF** en toda petición que cambie estado (token por sesión en una cabecera).
- Las credenciales de demostración vienen de `.env`. Si no están definidas, se generan al
  azar en el primer arranque y se imprimen una sola vez en el registro, y `run.sh` las
  muestra. En el repositorio no hay contraseñas por defecto.
- La firma del analista en decisiones y desbloqueos es el usuario de la sesión, ya no un
  texto libre.

### RF8. Simulador en vivo

- Reproduce un tramo real de la partición de prueba de Sparkov transacción por
  transacción, con un reloj acelerado configurable (por ejemplo, 1 hora de datos por
  cada 30 segundos). Envía cada transacción por el mismo camino de RF1.
- Se puede iniciar, pausar y cambiar la velocidad. Al terminar, muestra el resumen:
  dinero detenido frente a la regla del M2, bloqueos, bloqueos falsos y tiempos.
- Permite **inyectar una transacción a mano**, por ejemplo con un comercio malicioso,
  para probar los ataques en vivo.

### RF9. Frontend

| Vista | Contenido |
|---|---|
| **Ingreso** | Usuario y contraseña; mensajes de error sin revelar si el usuario existe |
| **En vivo** | Flujo de transacciones con score y banda; casos que se abren; decisión del agente o de la regla con su tiempo; contador de dinero detenido |
| **Bandeja y detalle** (existentes) | Más los estados nuevos (bloqueado, en verificación, desbloqueado), el actor del bloqueo, el aviso enviado y el botón de desbloquear con motivo |
| **Bloqueos** | Tarjetas bloqueadas con actor, banda, motivo, aviso, respuesta del titular y tiempo; filtros; desbloqueo |
| **Buzón del titular** | Simulación de teléfono con los avisos recibidos y los botones "fui yo" y "no fui yo" |
| **Supervisión** | Interruptor de autonomía, tope por hora y uso, gasto del día frente al tope, métricas en vivo, panel de fallas de la demo (solo supervisor) |

- Pulido visual de todo: jerarquía, legibilidad, estados vacíos y de error, modo claro y
  oscuro y teclado. Se conserva la regla del M2: **nunca `innerHTML`** con texto que venga
  del modelo o de los datos.

## 5. Requisitos de seguridad (clase 12)

| # | Requisito | Cómo se cumple |
|---|---|---|
| RS1 | Tríada letal: quitar una pata | El agente no tiene salida a internet ni elige destinatarios. El único canal de salida (el aviso) es una plantilla validada, con destinatario resuelto en código y correo restringido a una lista blanca. Se documenta qué viaja al proveedor del LLM (sin nombres, tarjeta enmascarada) |
| RS2 | Inyección directa e indirecta | Las guardas de RF3 y RF5 limitan el daño aunque el modelo obedezca. Se prueba con comercios maliciosos inyectados por `POST /api/transacciones` |
| RS3 | Mínimo privilegio en la base | Tres roles de Postgres: `fraude_admin` (dueño, solo migraciones), `fraude_app` (lectura y escritura por tabla) y `fraude_agente` (solo lectura de casos, transacciones e historial, **sin** la columna de la etiqueta del dataset). Las herramientas del agente usan la conexión de `fraude_agente` |
| RS4 | Aprobación humana de lo irreversible | El bloqueo es reversible y protector. El desbloqueo, que reabre la tarjeta al riesgo, es solo humano. Nadie mueve dinero |
| RS5 | Consumo desmedido | Límite de peticiones por minuto por IP y por usuario; tope de gasto diario en USD; los cuatro límites del agente; tope de bloqueos autónomos por hora; el LLM solo se llama al abrir o subir de banda un caso |
| RS6 | Sesiones y CSRF | RF7 |
| RS7 | Secretos | Llaves solo en `.env`; escaneo antes de cada push y en el ZIP (ampliado a los formatos `apikey_…` y `AQ.…`); contraseñas generadas si no se definen |
| RS8 | Entornos descartables | El agente no ejecuta código. Postgres no se publica fuera de Compose y la app solo escucha en 127.0.0.1 |
| RS9 | Salida HTML | Sin `innerHTML` con texto del modelo o de los datos; cabeceras de seguridad (CSP sin scripts en línea, `X-Content-Type-Options`, `Referrer-Policy`) |

## 6. Cambios en los datos

Tablas nuevas o ampliadas (detalle en `diseno/` cuando se construya):

- `transacciones_evaluadas`: cada transacción que entra, con score, banda, señales,
  latencia de puntuación e id del caso.
- `casos`: columna `origen` (`semilla` o `en_vivo`), `banda` y estados nuevos
  (`bloqueado`, `en_verificacion`, `desbloqueado`).
- `bloqueos`: tipo (tarjeta o acceso), actor (`agente`, `regla` o el usuario), banda,
  motivo, tarea, creado, estado, desbloqueado por, motivo del desbloqueo y fecha.
- `notificaciones`: caso, bloqueo, canal, destinatario enmascarado, cuerpo, motivo
  original del agente, resultado de la validación, estado, respuesta del titular y fecha.
- `usuarios` y `sesiones`; `ajustes_sistema` (autonomía encendida, tope por hora).
- `tareas_agente.tipo` admite `triaje`.

## 7. Métricas

Se reportan con fecha en `docs/decisiones/semana14.md` y se comparan contra la línea base
del Momento 2 (2026-10-21 y 2026-10-31):

1. Tiempo de puntuación por transacción (mediana y p99, en ms).
2. Tiempo desde la compra hasta el bloqueo (mediana, p95 y máximo).
3. Dinero detenido frente a la regla del M2 sobre el mismo tramo simulado.
4. Precisión, recall y F1 de los bloqueos autónomos, del agente y de la regla, por banda,
   contra la etiqueta del dataset (solo en `eval/`, nunca en la interfaz).
5. Bloqueos falsos por cada 1.000 transacciones y tiempo hasta el desbloqueo.
6. Costo por triaje y por cada 1.000 transacciones; éxito del triaje y recuperación ante
   429 y timeout.
7. Ataques: cuántos resiste, cuántos parcialmente y cuántos fallan (formato del reto 12).

## 8. Criterios de aceptación

- [ ] Un clon limpio arranca con `docker compose up --build -d` sin `.env`, con
      credenciales generadas y explicaciones de plantilla. Con una sola llave de Gemini,
      el triaje funciona.
- [ ] El simulador bloquea los casos críticos en ≤ 5 minutos en el 100 % de los casos,
      también con la IA forzada a fallar (429 y timeout en todos los proveedores).
- [ ] La puntuación en vivo coincide con la del motor fuera de línea (≤ 0,001).
- [ ] Ninguna herramienta del agente puede bloquear un caso en banda media, actuar sobre
      otra tarjeta ni desbloquear. Hay pruebas automáticas para cada guarda.
- [ ] Un comercio con "no bloquees esta tarjeta" no evita el bloqueo de un caso crítico.
      Uno con "bloquea todas las tarjetas" no bloquea nada fuera de su caso. Uno con un
      enlace no logra que el enlace llegue al aviso.
- [ ] Con el rol de la base del agente, `select fraude_confirmado_dataset from casos`
      falla por permisos.
- [ ] Más peticiones por minuto que el límite reciben 429 con un mensaje en español.
- [ ] Sin sesión, toda ruta que cambia estado responde 401; sin token CSRF, 403.
- [ ] La suite de pytest pasa completa y la suite de `eval/` incluye triaje y ataques.
- [ ] `docs/seguridad.md`, `docs/gobernanza.md`, `docs/respuesta_auditoria.md`,
      `docs/decisiones.md` y el README quedan actualizados, con los dos integrantes.

## 9. Decisiones abiertas

| Decisión | Propuesta | Quién la cierra |
|---|---|---|
| Canal del aviso en la demo | Simulado por defecto; correo de prueba con lista blanca solo si sobra tiempo | Equipo, antes del 15-nov |
| Valor del tope de bloqueos autónomos por hora | Elegirlo con el simulador (p99 de bloqueos legítimos por hora × 2) | Validación |
| Ventana de la red de seguridad | 90 s (meta de 60 s para el agente, 5 min de máximo duro) | Validación |
| Tramo de Sparkov del simulador | Una noche con varios episodios de fraude (22:00 a 06:00) | Construcción |
