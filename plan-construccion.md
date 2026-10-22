# Plan de construcción — 2026-09-06

## Qué se decidió en esta sesión

- **Orden de trabajo elegido:** priorizar la migración a un dataset real
  (PaySim o Kaggle Credit Card Fraud), pero como no hay forma de descargarlo sin
  las credenciales del equipo, se dejó esa acción para cuando el equipo consiga el
  archivo, y mientras tanto se construyó la pieza que no dependía de eso: el
  detector de viaje imposible.
- **Esquema de datos:** se agregaron coordenadas fijas por ciudad (`latitud`,
  `longitud`) y un timestamp completo (`fecha_hora`) al CSV, en vez de solo la
  hora (0-23) que había antes. Justificación: sin coordenadas y sin orden temporal
  real entre transacciones de una misma cuenta, no hay manera de calcular
  distancia ni tiempo transcurrido, que es lo que necesita el detector de viaje
  imposible. Se mantiene la columna `hora` por compatibilidad con las features del
  modelo de ML.
- **Separación de responsabilidades confirmada:** el detector de viaje imposible
  vive en su propio script (`detectar_viaje_imposible.py`), separado de
  `entrenar_modelo.py`, y este último excluye del entrenamiento las filas de tipo
  `viaje_imposible` — cada componente cubre un tipo de fraude distinto, tal como
  ya establecía el mapa del modelo de `decisiones.md`.
- **Conseguir el dataset real:** decisión pospuesta a propósito; no bloquea el resto
  del trabajo.

## Arquitectura resultante

| Componente | Dónde vive | ¿Lleva modelo? | Estado |
|---|---|---|---|
| Generador de datos sintéticos | `src/generar_datos.py` | No | Hecho, con esquema de coordenadas + timestamp |
| Motor de riesgo de uso no autorizado | `src/entrenar_modelo.py` | Sí — ML clásico (Random Forest) | Hecho y validado sobre datos sintéticos (97.7-99% precisión) |
| Detector de viaje imposible | `src/detectar_viaje_imposible.py` | No — código determinista | Hecho y validado (100% precisión, 99.3% recall) |
| Validación con dataset real | Reemplazaría `datos/transacciones.csv` | — | Pendiente de que el equipo descargue PaySim o Kaggle |
| Interfaz de consultas en lenguaje natural | Carpeta nueva `interfaz/` (separada de `src/`) | Sí — LLM | No iniciada; es la segunda etapa, después de validar con datos reales |

## Orden de construcción

1. ~~Prototipo del motor de riesgo sobre datos sintéticos~~ (hecho antes de esta sesión).
2. ~~Detector de viaje imposible~~ (hecho en esta sesión).
3. Conseguir y migrar a un dataset real (PaySim o Kaggle) — bloqueado en el equipo.
4. Re-validar `entrenar_modelo.py` y `detectar_viaje_imposible.py` sobre ese dataset
   real; los resultados sobre datos sintéticos no se presentan como definitivos.
5. Construir la interfaz de consultas en lenguaje natural, en `interfaz/`.
6. Preparar el material para la asesoría con Julián (documento + resultados).

## Checklist de próximos pasos

- [ ] Descargar PaySim o Kaggle Credit Card Fraud y decirle a Claude dónde quedó el
      archivo, para ajustar `generar_datos.py`/el pipeline a sus columnas reales.
- [ ] Re-correr `entrenar_modelo.py` y `detectar_viaje_imposible.py` sobre ese
      dataset y comparar contra los resultados sintéticos documentados en
      `decisiones.md`.
- [ ] Decidir con qué se construye la interfaz de lenguaje natural (qué LLM/API,
      cómo se conecta a los casos marcados) — pendiente, no decidido todavía.
- [ ] Agendar y preparar la próxima asesoría con Julián con este documento y los
      números de `decisiones.md`.

---

# Plan de construcción — 2026-09-06 (segunda sesión)

## Qué se decidió en esta sesión

- **Se sumó al alcance la pieza "persistir los casos marcados"** y se anotó en
  `decisiones.md` (paso 4 de "Próximos pasos" y fila nueva en el mapa del modelo).
  Justificación: ni `entrenar_modelo.py` ni `detectar_viaje_imposible.py` guardan la
  lista de transacciones sospechosas, así que la interfaz de consultas y la
  explicación por caso no tendrían sobre qué operar. No lleva modelo — es escritura
  estructurada. No depende del dataset real, se puede empezar ya.

- **Se decidió construir lo que falta (persistencia, interfaz LLM, explicación por
  caso, y más adelante la migración al dataset real) a través de una cadena de
  skills-rol**, una por fase, en vez de improvisar cada componente. El equipo decide
  en cada fase; la skill organiza y pregunta. Quedan instaladas en
  `proyecto-fraude-bancario/.claude/skills/`:
  - `requisitos-fraude` — qué debe hacer un componente (entrega en `requisitos/`).
  - `disenar-fraude` — cómo se estructura (entrega en `diseno/`); usa
    `AskUserQuestion` para cada alternativa real, nunca decide sola.
  - `construir-fraude` — escribe el código en `src/` o `interfaz/` siguiendo
    `CLAUDE.md`; única skill que toca código.
  - `validar-fraude` — audita métricas y realismo (entrega en `validacion/`); no
    toca código, solo diagnostica.
  Flujo por componente: requisitos → diseño → construcción → validación.
  Frontera con `planear-fraude`: esta sigue decidiendo qué falta y en qué orden y
  los llamados de modelo/no-modelo con los seis ejes; las cuatro nuevas arrancan
  después, sobre un componente ya aprobado.

- **Idioma de las skills nuevas:** el cuerpo de instrucciones va en inglés (rinde
  algo mejor); los entregables que producen — docs y código — siguen en español por
  la condición #1 de `CLAUDE.md`, y así se lo indica cada skill al modelo.

- **Dónde viven los entregables:** carpetas nuevas por fase —
  `requisitos/<componente>.md`, `diseno/<componente>.md`,
  `validacion/<componente>.md`.

- **Nota operativa:** una skill recién creada no aparece en el listado invocable
  hasta abrir una sesión nueva en la carpeta del proyecto. Hasta entonces se sigue
  su flujo a mano.

## Arquitectura resultante

| Componente | Dónde vive | ¿Lleva modelo? | Estado |
|---|---|---|---|
| Generador de datos sintéticos | `src/generar_datos.py` | No | Hecho |
| Motor de riesgo de uso no autorizado | `src/entrenar_modelo.py` | Sí — Random Forest | Hecho y validado sobre sintéticos |
| Detector de viaje imposible | `src/detectar_viaje_imposible.py` | No — determinista | Hecho y validado sobre sintéticos |
| Persistencia de casos marcados | Por decidir (`src/` o archivo de salida) | No | En alcance; sin requisitos todavía — arranca por `requisitos-fraude` |
| Validación con dataset real | Reemplaza `datos/transacciones.csv` | — | Bloqueado en el equipo (falta el archivo) |
| Interfaz de consultas en lenguaje natural | Carpeta nueva `interfaz/` | Sí — LLM | No iniciada; depende de la persistencia |
| Explicación en lenguaje natural por caso | Con la interfaz o en `src/` (a decidir en diseño) | Sí — LLM (opcional) | No iniciada; depende de la persistencia |
| Skills-rol de construcción | `.claude/skills/{requisitos,disenar,construir,validar}-fraude/` | — | Instaladas en esta sesión |

## Orden de construcción

1. ~~Prototipo del motor de riesgo sobre datos sintéticos~~ (hecho).
2. ~~Detector de viaje imposible~~ (hecho).
3. Persistencia de los casos marcados — vía requisitos → diseño → construcción →
   validación. No depende del dataset real; se puede empezar ya.
4. Conseguir y migrar al dataset real (PaySim o Kaggle) — bloqueado en el equipo, va
   en paralelo con lo demás.
5. Re-validar `entrenar_modelo.py` y `detectar_viaje_imposible.py` sobre ese dataset.
6. Interfaz de consultas en lenguaje natural, en `interfaz/` — vía las cuatro fases.
7. Explicación en lenguaje natural por caso — vía las cuatro fases.
8. Preparar el material para la asesoría con Julián.

## Checklist de próximos pasos

- [ ] Abrir una sesión nueva en `proyecto-fraude-bancario/` para que las cuatro
      skills nuevas aparezcan en el listado invocable.
- [ ] Invocar `requisitos-fraude` para la persistencia de casos marcados (primer
      componente de la cadena).
- [ ] Descargar PaySim o Kaggle Credit Card Fraud y decirle a Claude dónde quedó el
      archivo, para ajustar el pipeline a sus columnas reales.
- [ ] Re-correr `entrenar_modelo.py` y `detectar_viaje_imposible.py` sobre ese
      dataset y comparar contra los números de `decisiones.md`.
- [ ] Decidir proveedor de LLM para la interfaz — queda para `disenar-fraude` cuando
      se llegue a ese componente, no ahora.
- [ ] Agendar y preparar la próxima asesoría con Julián.

---

# Plan de construcción — 2026-10-09 (tercera sesión)

## Qué se decidió en esta sesión

- **Persistencia de los casos marcados: Postgres en Docker.** Decidido con el usuario
  tras revisar el programa oficial de la materia en el campus: el curso trabaja
  Postgres en Docker desde la semana 7 y el reto de esa semana exige consumir el
  servidor MCP de Postgres sobre la base de datos *del proyecto* y exponer un
  servidor FastMCP propio. Elegir CSV o SQLite habría obligado a migrar después.
  El setup de referencia está en el material de la semana 7
  (`material/momento2/semana07/`).
- **Se suman al alcance oficial las piezas que exige la materia** (aprobado por el
  usuario; anotado también en `decisiones.md`): la interfaz de consultas se
  construye como **agente con herramientas propias y los 4 límites de seguridad
  obligatorios** (iteraciones máximas, presupuesto de tokens, aprobación humana
  para acciones de escritura, timeout por herramienta — sin límite de iteraciones
  no hay entrega), con **capa de abstracción del proveedor LLM**; una **suite de
  evaluación** con casos verificados a mano (al menos uno de rechazo) y la línea
  base de las cuatro cifras con fecha (tasa de éxito, costo por tarea, latencia
  mediana, recuperación); y los documentos **`docs/decisiones/semanaNN.md`**
  (07 a 10) con las plantillas que da cada reto.
- **Estrategia de datos del proyecto: consulta directa, no RAG.** Los datos son
  tabulares y viven en una base de datos; según la tabla de la semana 8, la
  respuesta correcta es una herramienta que consulta — y sustentar el "no RAG"
  califica igual o mejor en la rúbrica. Se documenta en
  `docs/decisiones/semana08.md` cuando se construya el agente.
- **La presentación del pitch quedó lista** (fuera del alcance de esta skill, se
  registra como contexto): `guion-pitch-presentacion.md`, `guion-jhoan.md`,
  `guion-jeison.md`, `presentacion-fraude-bancario.html` (para el buzón) y los dos
  decks en línea (con y sin notas del orador).

## Arquitectura resultante

| Componente | Dónde vive | ¿Lleva modelo? | Estado |
|---|---|---|---|
| Generador de datos sintéticos | `src/generar_datos.py` | No | Hecho |
| Motor de riesgo de uso no autorizado | `src/entrenar_modelo.py` | Sí — Random Forest | Hecho y validado sobre sintéticos |
| Detector de viaje imposible | `src/detectar_viaje_imposible.py` | No — determinista | Hecho y validado sobre sintéticos |
| Persistencia de casos marcados | **Postgres en Docker** (decidido hoy); escritura desde los dos detectores | No | Sin requisitos todavía — arranca por `requisitos-fraude` |
| Validación con dataset real | Reemplaza `datos/transacciones.csv` | — | Bloqueado en el equipo (credenciales de Kaggle) |
| Agente de consultas (antes "interfaz de lenguaje natural") | `interfaz/` | Sí — LLM, con herramientas propias, 4 límites y capa de proveedor | No iniciado; depende de la persistencia |
| Suite de evaluación y cifras | Archivo de casos + script (carpeta a decidir en diseño) | No | Nueva en alcance; depende del agente |
| Documentos de decisiones semanales | `docs/decisiones/semana07..10.md` | — | No iniciados; se llenan al construir cada pieza |
| Explicación en lenguaje natural por caso | Con el agente (a decidir en diseño) | Sí — LLM (opcional) | No iniciada |

## Orden de construcción

1. ~~Motor de riesgo sobre datos sintéticos~~ (hecho).
2. ~~Detector de viaje imposible~~ (hecho).
3. **Persistencia en Postgres** — levantar el contenedor con el setup de la semana 7,
   definir la tabla de casos, y que ambos detectores escriban ahí. Vía
   requisitos → diseño → construcción → validación. No depende del dataset real.
4. Dataset real (PaySim o Kaggle) — en paralelo; sigue bloqueado en las credenciales.
5. Re-validar los dos detectores sobre el dataset real.
6. **Agente de consultas** — herramientas de dominio sobre la BD (mínimo 2), los 4
   límites, capa de proveedor conmutable; consumir el MCP de Postgres y exponer el
   FastMCP propio (reto semana 7). Llena `docs/decisiones/semana07.md` y
   `semana08.md` (estrategia de datos: consulta directa, con las 5 preguntas de
   prueba verificadas a mano).
7. **Capa de aplicación usable por terceros** — manejo de 429/timeout/salida
   inválida con degradación, fuente y criterio visibles, costo por pregunta medido,
   y la prueba del compañero documentada (`docs/decisiones/semana09.md`).
8. **Suite de evaluación y línea base** — 5-10 casos verificados (≥1 de rechazo),
   script que los corre, trazas visibles, y las cuatro cifras con fecha
   (`docs/decisiones/semana10.md`).
9. Explicación por caso (LLM, opcional) — solo si queda margen.
10. Ensayo de la demo con reloj y plan B sin internet.

## Checklist de próximos pasos

- [ ] Invocar `requisitos-fraude` para la persistencia de casos marcados en
      Postgres (primer componente de la cadena; la decisión de motor ya está tomada).
- [ ] Levantar Postgres en Docker con el setup de la semana 7 y definir el esquema
      de la tabla de casos (campos: transacción, puntaje, features, tipo de fraude,
      fecha de marcado).
- [ ] Hacer que `entrenar_modelo.py` y `detectar_viaje_imposible.py` escriban los
      casos marcados a esa tabla.
- [ ] Descargar PaySim o Kaggle Credit Card Fraud (credenciales del equipo) y decir
      dónde quedó el archivo — sigue siendo el bloqueo más viejo del proyecto.
- [ ] Re-correr los dos detectores sobre el dataset real y comparar contra los
      números sintéticos de `decisiones.md`.
- [ ] Construir el agente de consultas: mínimo 2 herramientas de dominio, los 4
      límites de seguridad, capa de proveedor conmutable en una línea.
- [ ] Conectar el MCP de Postgres al proyecto y exponer el servidor FastMCP propio;
      llenar `docs/decisiones/semana07.md` con la plantilla del reto.
- [ ] Documentar la estrategia de datos (consulta directa, no RAG) con la tabla de
      la clase y las 5 preguntas verificadas → `docs/decisiones/semana08.md`.
- [ ] Capa de aplicación: degradación ante 429/timeout/salida inválida, fuente y
      criterio visibles, costo medido; prueba del compañero con otro equipo →
      `docs/decisiones/semana09.md`.
- [ ] Suite de evaluación (5-10 casos, ≥1 de rechazo) + script + trazas; registrar
      las cuatro cifras con fecha → `docs/decisiones/semana10.md`.
- [ ] Decidir proveedor de LLM del agente — en `disenar-fraude` cuando se llegue a
      ese componente, con criterios de costo y latencia.
- [ ] Ensayar la demo con reloj; exportar PDF de respaldo y probarla sin internet.

---

# Plan de construcción — 2026-10-10 (cuarta sesión)

## Qué se decidió en esta sesión

Sesión disparada por el feedback del profesor Julián (detalle completo en
`decisiones.md`, "Actualización 2026-10-10"). Decisiones:

- **El agente LLM vive dentro de la vista del analista**, no en una pantalla
  aparte. "Interfaz de consultas" y "explicación por caso" dejan de ser dos
  componentes y se fusionan en uno: **la vista del analista**. La explicación por
  caso pasa de opcional a **obligatoria** — ya no es "solo si queda margen".
- **Por cada caso el agente entrega**: resumen de qué pasó, por qué es un riesgo
  (qué se desvió del perfil de esa cuenta), y recomendación de bloqueo argumentada
  desde el scoring. El bloqueo sigue siendo decisión humana.
- **Trazabilidad score → features → explicación**: al marcar un caso se calculan y
  persisten sus desviaciones por feature contra el perfil histórico de la cuenta;
  el agente explica citando esos valores vía sus herramientas, nunca de memoria.
  Decidido así (el usuario delegó la elección): desviaciones como base obligatoria,
  **SHAP por predicción como mejora opcional** si sobra tiempo antes de la demo.
  Consecuencia directa: el esquema de la tabla de casos en Postgres debe incluir
  las desviaciones por feature y la explicación generada, no solo el score.
- **La vista del analista se construye con Streamlit** (elegido por el usuario
  sobre Flask+HTML y Gradio): todo en Python, tabla + detalle + chat en una pieza,
  cumple "usable por terceros, no terminal" sin gastar días en frontend.
- **Generación de la explicación: modo híbrido** (elegido por el usuario): se
  genera al marcar el caso y se guarda en Postgres, con botón "regenerar" en la UI.
  La demo no depende del API en vivo (inmune a 429) y cada explicación queda
  auditada junto a su score; las repreguntas del analista sí van en vivo.

## Arquitectura resultante

| Componente | Dónde vive | ¿Lleva modelo? | Estado |
|---|---|---|---|
| Generador de datos sintéticos | `src/generar_datos.py` | No | Hecho |
| Motor de riesgo de uso no autorizado | `src/entrenar_modelo.py` | Sí — Random Forest | Hecho y validado sobre sintéticos |
| Detector de viaje imposible | `src/detectar_viaje_imposible.py` | No — determinista | Hecho y validado sobre sintéticos |
| Persistencia de casos marcados | Postgres en Docker; escritura desde los dos detectores. **El esquema ahora incluye desviaciones por feature y explicación generada** | No | Sin requisitos todavía — arranca por `requisitos-fraude` |
| Validación con dataset real | Reemplaza `datos/transacciones.csv` | — | Bloqueado en el equipo (credenciales de Kaggle) |
| **Vista del analista** (fusiona el agente de consultas + explicación por caso) | `interfaz/`, app **Streamlit**: lista de casos → detalle con score desglosado → resumen/riesgo/recomendación guardados + chat del agente | Sí — LLM con herramientas propias (`obtener_caso`, `obtener_perfil_cuenta`, `obtener_score_y_features`…), 4 límites y capa de proveedor | No iniciada; depende de la persistencia |
| Explicabilidad del score (desviaciones por feature; SHAP opcional) | Se calcula al marcar el caso, se guarda con él | No (es cálculo sobre el perfil; SHAP sería análisis del modelo) | No iniciada; parte de la persistencia |
| Suite de evaluación y cifras | Archivo de casos + script (carpeta a decidir en diseño) | No | En alcance; depende del agente |
| Documentos de decisiones semanales | `docs/decisiones/semana07..10.md` | — | No iniciados |

## Orden de construcción

1. ~~Motor de riesgo sobre datos sintéticos~~ (hecho).
2. ~~Detector de viaje imposible~~ (hecho).
3. **Persistencia en Postgres** — ahora con el esquema ampliado: caso + score +
   desviaciones por feature + explicación generada + tipo de fraude + fecha.
   Vía requisitos → diseño → construcción → validación. No depende del dataset real.
4. Dataset real (PaySim o Kaggle) — en paralelo; sigue bloqueado en credenciales.
5. Re-validar los dos detectores sobre el dataset real.
6. **Vista del analista** — Streamlit + agente con herramientas sobre la BD, los 4
   límites, capa de proveedor; genera y guarda la explicación al marcar, botón
   regenerar, chat en vivo. Consume el MCP de Postgres y expone el FastMCP propio
   (semana 7). Llena `docs/decisiones/semana07.md` y `semana08.md`.
7. Degradación 429/timeout/salida inválida, fuente y criterio visibles, costo
   medido, prueba del compañero (`docs/decisiones/semana09.md`) — la explicación
   pre-generada ya es parte de esta estrategia.
8. Suite de evaluación y línea base de cuatro cifras (`docs/decisiones/semana10.md`).
9. SHAP por predicción — solo si queda margen; documentado como mejora, no requisito.
10. Ensayo de la demo con reloj y plan B sin internet.

## Checklist de próximos pasos

- [ ] Invocar `requisitos-fraude` para la persistencia en Postgres, con el alcance
      ampliado de esta sesión (desviaciones por feature y explicación en el esquema).
- [ ] Levantar Postgres en Docker (setup semana 7) y definir la tabla de casos con
      los campos nuevos.
- [ ] Hacer que `entrenar_modelo.py` y `detectar_viaje_imposible.py` escriban los
      casos marcados con sus desviaciones por feature.
- [ ] Descargar PaySim o Kaggle (credenciales del equipo) — sigue siendo el bloqueo
      más viejo del proyecto.
- [ ] Re-correr los dos detectores sobre el dataset real.
- [ ] Construir la vista del analista en Streamlit: tabla de casos, detalle con
      score desglosado, explicación guardada + botón regenerar, chat del agente.
- [ ] Agente: ≥2 herramientas de dominio, 4 límites, capa de proveedor conmutable;
      MCP de Postgres + FastMCP propio → `docs/decisiones/semana07.md`.
- [ ] Estrategia de datos (consulta directa, no RAG) → `docs/decisiones/semana08.md`.
- [ ] Degradación + costo medido + prueba del compañero → `docs/decisiones/semana09.md`.
- [ ] Suite de evaluación + cuatro cifras con fecha → `docs/decisiones/semana10.md`.
- [ ] Decidir proveedor de LLM — en `disenar-fraude` al llegar a la vista del
      analista.
- [ ] (Opcional, al final) SHAP por predicción como refuerzo de la trazabilidad.
- [ ] Ensayar la demo con reloj; respaldo sin internet.

---

# Plan de construcción — 2026-10-21 (quinta sesión)

## Qué se decidió en esta sesión

Sesión disparada por un nuevo comentario de Julián (detalle en `decisiones.md`,
"Actualización 2026-10-21"). Decisiones:

- **Orden: motor de riesgo primero.** Se corrige la filtración del perfil (solo
  historial previo, partición temporal) y el motor pasa a producir casos con sus
  desviaciones por feature. Sin eso, la explicación del LLM narraría razones falsas.
- **Dataset real: Sparkov** (`fraudTrain.csv` / `fraudTest.csv`). Descargado por
  Claude desde la cuenta de Kaggle del usuario, con su autorización. Desbloquea el
  pendiente más viejo del proyecto.
- **Nivel de bloqueo: regla determinista + argumento del LLM.** Uso no autorizado →
  tarjeta; viaje imposible → acceso a la cuenta; score intermedio → verificar.
- **El caso es una secuencia de transacciones** de la tarjeta, no una fila suelta; el
  agente suma una herramienta para leer el historial reciente.
- **Postgres en Docker local**, como estaba decidido.
- Proveedor de LLM: sigue pendiente para `disenar-fraude` de la vista del analista
  (candidato natural: Gemini, ya usado en la semana 6).

## Arquitectura resultante

| Componente | Dónde vive | ¿Lleva modelo? | Estado |
|---|---|---|---|
| Generador de datos sintéticos | `src/generar_datos.py` | No | Hecho; queda para pruebas y para viaje imposible |
| Adaptador del dataset real (Sparkov → columnas del proyecto) | `src/` (nombre en diseño) | No | **Nuevo**, parte del motor de riesgo |
| Motor de riesgo de uso no autorizado | `src/entrenar_modelo.py` | Sí — ML clásico | **Por corregir**: filtración del perfil, partición temporal, salida de casos con desviaciones |
| Detector de viaje imposible | `src/detectar_viaje_imposible.py` | No — determinista | Hecho sobre sintéticos; en Sparkov solo se mide falsas alarmas |
| Regla de recomendación de bloqueo | A decidir en diseño | No — determinista | **Nuevo** |
| Persistencia de casos marcados | Postgres en Docker | No | Sin iniciar; depende del motor |
| Vista del analista + agente | `interfaz/`, Streamlit | Sí — LLM con herramientas, ahora incluye historial reciente | Sin iniciar |
| Suite de evaluación y cuatro cifras | A decidir | No | Sin iniciar |

## Orden de construcción

1. **Motor de riesgo** (requisitos → diseño → construcción → validación): adaptador
   de Sparkov, perfil solo con historial previo, partición temporal, comparación de
   modelos contra la regla de umbral, casos marcados con desviaciones por feature y
   recomendación de bloqueo.
2. Persistencia en Postgres (Docker) con el esquema ampliado.
3. Vista del analista con el agente (resumen, riesgo, recomendación, historial).
4. Degradación ante fallos, suite de evaluación, cuatro cifras, documentos
   `docs/decisiones/semana07..10.md`.
5. Ensayo de la demo.

## Checklist de próximos pasos

- [x] Descargar el dataset real (Sparkov).
- [ ] `requisitos-fraude` → `requisitos/motor-riesgo.md`.
- [ ] `disenar-fraude` → `diseno/motor-riesgo.md`.
- [ ] `construir-fraude` del motor y corrida real con métricas completas.
- [ ] `validar-fraude` → `validacion/motor-riesgo.md`; actualizar los números de
      `decisiones.md`.
- [ ] Abrir Docker Desktop y seguir con la persistencia (mismo flujo de skills).
- [ ] Decidir proveedor de LLM en el diseño de la vista del analista.
- [ ] Vista del analista, degradación, suite de evaluación y documentos semanales.
- [ ] Ensayar la demo con reloj; respaldo sin internet.

---

# Plan de construcción — 2026-10-21 (sexta sesión, misma fecha)

## Qué se decidió en esta sesión

- El motor de riesgo quedó construido y validado dos veces (`validacion/motor-riesgo.md`).
  Cifras en `decisiones.md`, "Resultado del motor sobre Sparkov" y "Cierre del motor".
- La página de entrega del Momento 2 (31 de octubre) cambió el alcance: ZIP que arranca
  con un comando, `docs/decisiones.md` único, `eval/`, SSE real, fallos forzados en vivo
  (`decisiones.md`, "Actualización 2026-10-21 (2)").
- La app pasa a **FastAPI + SSE + frontend propio + Postgres en docker-compose**;
  proveedores **Gemini 3.8 Flash principal y Claude Haiku 5.5 de respaldo**, más la
  plantilla sin red; MCP solo como adaptador opcional al final.
- Producto: el analista registra decisiones solo con confirmación (human-in-the-loop);
  se cargan casos de Sparkov y sintéticos; la explicación se genera al abrir y se
  guarda (caché), con un lote pregenerado para la demo; sin login en el M2 (pasa al
  alcance del M3, junto con `docs/seguridad.md` y `docs/gobernanza.md`).
- Requisitos y diseños escritos: `persistencia`, `agente`, `vista-analista`,
  `evaluacion-entrega` (este último solo requisitos).

## Arquitectura resultante

| Componente | Dónde vive | ¿Lleva modelo? | Estado |
|---|---|---|---|
| Motor de riesgo (ML) + viaje imposible | `src/` | ML clásico / determinista | Hecho y validado |
| Persistencia + semilla + docker-compose | `app/db/`, `scripts/generar_semilla.py`, `semilla/` | No | En construcción |
| Agente (bucle, 4 límites, herramientas, contrato, cascada) | `app/agente/`, `app/proveedores/` | Sí — LLM | En construcción |
| Vista del analista (API + SSE + web) | `app/api/`, `app/web/`, `app/principal.py` | No | En construcción |
| Evaluación + entrega (suite, cuatro cifras, README, ZIP) | `eval/`, `docs/decisiones.md`, raíz | No | Requisitos listos; diseño pendiente |

## Orden de construcción

1. Persistencia, agente y vista en paralelo (interfaces fijadas en `diseno/`).
2. Integración en Docker y prueba con las llaves reales.
3. `validar-fraude` sobre la app (fallos forzados, límites, SSE en DevTools).
4. Diseño y construcción de `evaluacion-entrega`: suite dorada verificada a mano por
   el equipo, lote de medición, cuatro cifras, `docs/decisiones.md`, README, `run.sh`,
   script de ZIP y prueba en carpeta limpia.
5. Prueba del compañero, ensayo de la demo de 6 minutos y guía de estudio del código
   para cada integrante (falla crítica "lo hizo la IA y no sé qué hace").

## Checklist de próximos pasos

- [x] Motor de riesgo sobre Sparkov y sintéticos, validado.
- [ ] Integrar los tres componentes y levantar con `docker compose up`.
- [ ] Validar la app (fallos, límites, SSE, confirmación humana).
- [ ] Diseñar y construir `eval/` y el paquete de entrega.
- [ ] Verificar a mano los casos dorados (Jhoan y Jeison).
- [ ] Prueba del compañero documentada.
- [ ] Guía de estudio del código y ensayo de la demo con reloj.

---

# Plan de construcción — 2026-10-21 (séptima sesión: cierre del día)

## Qué quedó hecho

- App completa e integrada en `docker-compose` (Postgres + FastAPI + SSE + frontend),
  construida por componentes con requisitos → diseño → construcción → validación.
- Proveedores: Claude Haiku 5.5 principal y Gemini 3.1 Flash-Lite de respaldo
  (`decisiones.md`, 2026-10-21 (3)); prompt `2026-10-21.4`.
- Validaciones: `validacion/motor-riesgo.md` (dos pasadas) y `validacion/app-analista.md`;
  todos los hallazgos altos y medios corregidos. 123 pruebas unitarias + 14 de
  repositorio pasan.
- Evaluación: suite dorada 8/8 y lote de 19 tareas con las cuatro cifras
  (`eval/resultados/*_2157*`, `*_2158*`; `docs/decisiones.md` sección 9).
- Paquete: `README.md`, `run.sh`, `.env.example`, `scripts/empaquetar_entrega.py`;
  ZIP de 1,96 MB sin llaves, arranca en ~24 s desde carpeta limpia.

## Checklist de próximos pasos (equipo)

- [ ] Verificar a mano los 8 casos dorados y firmar `verificado_por` en
      `eval/casos_dorados.json` (Jhoan y Jeison).
- [ ] Prueba del compañero (3 tareas, desarrollador en silencio) → `docs/decisiones.md` §10.
- [ ] Repetir el arranque desde el ZIP en la máquina de otro integrante.
- [ ] Verificar las tarifas en las páginas oficiales de Anthropic y Google.
- [ ] Guía de estudio del código por integrante y ensayo de la demo de 6 min con reloj.
- [ ] (Opcional) adaptador FastMCP sobre `app/agente/herramientas.py`.
