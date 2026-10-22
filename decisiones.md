# Decisiones - Proyecto de curso: detección de fraude bancario

**Equipo:** Jhoan David Gruezo Gutiérrez y Jeison Nazarit

**Estado:** el profesor ya aprobó el dominio (fraude bancario) en la asesoría, pero
pidió dos cosas puntuales antes de dar luz verde a la ejecución: que identifiquemos
qué tipo de fraude vamos a detectar (no "fraude" en general), y que quede claro por
qué hace falta un modelo y no un conjunto de reglas fijas. Este documento resuelve
las dos, siguiendo el marco de la semana 3 (los seis ejes y la prueba de necesidad).

## De dónde partimos, y qué estaba mal en la primera versión

La idea inicial era: marcar como sospechosa una transacción si el monto es muy alto,
si ocurre de madrugada, o si la ubicación es rara. Las tres son reglas de un solo
umbral, evaluables con un `if`. Eso es exactamente el error que la clase señala como
"el error clásico del entusiasmo": meterle un modelo a algo que el código resuelve
igual de bien por una fracción del costo. Además, como reglas globales son débiles en
la práctica — "madrugada" es normal para alguien en otro huso horario o un turno
nocturno, y "monto alto" es normal para quien paga el arriendo una vez al mes. Un
umbral fijo sobre toda la población de usuarios genera demasiados falsos positivos, y
eso no es un problema de justificar la IA: es un problema de que el diseño en sí
sería malo.

Lo que sí sostiene la necesidad del modelo es distinto: el fraude es un patrón
adversarial (quien defrauda cambia de táctica para evadir la regla conocida en cuanto
la detecta), y la señal real no es un valor aislado sino la combinación de varias
variables cruzadas contra el comportamiento histórico de cada cuenta específica — no
existe "una hora sospechosa" universal, existe una hora inusual para esa cuenta en
particular. Escribir a mano una regla para cada combinación de cuenta x monto x hora x
ubicación no es viable; eso sí es "reglas infinitas o que cambian solas" en el sentido
de los seis ejes.

## Alcance: qué tipo de fraude vamos a detectar

Elegimos acotar a dos tipos concretos, ambos reconstruibles con los datos que un
banco realmente tiene (monto, hora, fecha, ubicación, cuenta origen/destino, y a
veces un código de referencia — no tienen visibilidad de qué producto se compró):

1. **Uso no autorizado de la cuenta** (tarjeta clonada o credenciales robadas): se
   manifiesta como una transacción con un monto anómalo *para el promedio histórico
   de esa cuenta*, en un horario atípico *para esa cuenta*, a veces junto con una
   ubicación distinta a las habituales de esa cuenta. Ninguna de las tres señales por
   separado alcanza para decidir; la combinación sí.
2. **Toma de control de cuenta vía viaje imposible**: dos transacciones de la misma
   cuenta en ubicaciones separadas por una distancia que no se puede recorrer en el
   tiempo transcurrido entre ambas (por ejemplo, una en Bogotá y once minutos después
   otra en una ciudad a varias horas de distancia).

Descartamos por ahora fraude de identidad sintética y lavado de activos/estructuración
porque necesitan datos que no tenemos (historial de apertura de cuentas, grafos de
transferencias entre terceros) y se salen del alcance de un proyecto de curso.

## Prueba de necesidad

**La pregunta:** si le quitamos el modelo, ¿el detector deja de existir o solo queda
más feo?

Aplicada al detector de uso no autorizado: sin un modelo que aprenda el perfil
normal de cada cuenta, no queda "más feo" — queda inviable en la práctica. Un
conjunto de reglas fijas por cuenta significaría escribir y mantener a mano miles de
reglas (una por cada cuenta, actualizada cada vez que el comportamiento normal de esa
persona cambia), lo cual nadie hace; y una regla global en su lugar produce
demasiados falsos positivos y falsos negativos como para ser operable (bloquear
arriendos legítimos, dejar pasar fraude que imita el patrón "normal" de la
población). El modelo aprende ese perfil por cuenta automáticamente a partir de datos,
que es justo lo que una regla escrita a mano no puede hacer a esa escala. **Pasa.**

Aplicada al detector de viaje imposible: el cálculo de distancia/tiempo entre dos
transacciones sí se puede escribir como una regla determinista (fórmula de distancia
entre coordenadas contra el tiempo transcurrido) — **no necesita modelo**, y lo
tratamos como código, no como IA. Lo dejamos en el alcance del proyecto porque es una
señal real y barata de calcular, pero es honesto no venderlo como "el mismo tipo de
IA" que el detector de uso no autorizado.

## Mapa de dónde va el modelo

Usando los seis ejes de la clase (entrada, reglas, determinismo, volumen, latencia,
costo del error):

| Componente | ¿Lleva modelo? | Justificación |
|---|---|---|
| Captura de la transacción (monto, hora, ubicación, cuenta) | No | Es el punto de entrada; datos ya estructurados, no hay nada que interpretar todavía |
| Cálculo de distancia/tiempo entre transacciones consecutivas de una cuenta (viaje imposible) | No | Entrada estructurada (coordenadas y timestamps), la regla se puede escribir exacta (fórmula de distancia), determinismo total, costo de un error de cálculo es alto si falla silenciosamente → favorece código |
| **Puntaje de riesgo de uso no autorizado** (combina desviación de monto, hora y ubicación respecto al perfil histórico de la cuenta) | **Sí — modelo de clasificación (ML clásico, no LLM)** | Entrada estructurada pero las reglas que la explican son infinitas (una por cada cuenta y cambian con el tiempo); se tolera cierta variación en el puntaje; volumen alto (miles de transacciones); latencia de milisegundos a segundos es aceptable en un flujo de revisión, no de bloqueo instantáneo; costo del error es alto pero revisable por un analista antes de bloquear la cuenta |
| Persistencia de los casos marcados (escribir a un archivo o tabla las transacciones que el modelo y el detector señalan, con su puntaje y sus features) | No | Escritura estructurada a partir de salidas que ya existen; no hay lenguaje ni ambigüedad que interpretar. Es el prerrequisito de las dos filas siguientes: no se puede consultar ni explicar lo que no está guardado en ninguna parte |
| Explicación en lenguaje natural del caso para el analista ("por qué se marcó esta transacción, qué riesgo implica y por qué debería bloquearse") | **Sí — LLM (obligatoria desde el 2026-10-10, pedida por el profesor)** | Traducir un vector de features y un puntaje en una recomendación legible es lenguaje abierto. Condición dura: la explicación se ancla a los datos reales del caso (score del modelo + desviaciones por feature contra el perfil de la cuenta, guardadas al marcar) — trazabilidad score → features → explicación, nunca texto que el LLM arme sin evidencia |
| **Consultas en lenguaje natural sobre los casos marcados** ("muéstrame las transacciones sospechosas de esta semana en Medellín mayores a 3 millones") | **Sí — LLM** | Entrada: lenguaje natural, espacio abierto. Reglas: infinitas preguntas posibles, no se pueden enumerar de antemano. Se tolera variación en la redacción. Volumen bajo (un analista preguntando, no miles de transacciones por segundo). Latencia de segundos es aceptable. Costo del error bajo: es una consulta de lectura, no una acción sobre la cuenta |
| Bloqueo o alerta final sobre la cuenta | No | Acción con costo de error alto e irreversible (afecta a un cliente real); la decide un analista humano, no el modelo ni el LLM |

Tres piezas llevan modelo (el puntaje de riesgo con ML clásico; la consulta en
lenguaje natural y la explicación por caso, ambas con LLM dentro del mismo agente), y
cada una por una razón distinta — no es "meterle IA a todo el sistema". El bloqueo
final sigue siendo decisión humana: el agente recomienda y argumenta, no actúa.

## Datos: qué tiene realmente un banco, y qué usamos nosotros

Un banco típicamente registra, por transacción: cuenta origen, cuenta destino, monto,
fecha y hora, tipo de transacción, y a veces un código de referencia del comercio —
no el detalle del producto comprado. Nosotros no tenemos acceso a datos reales de un
banco, así que:

- **Para el prototipo (esta primera etapa):** generamos datos sintéticos con
  `src/generar_datos.py`, con perfiles de comportamiento normal por cuenta (monto
  promedio propio, horas habituales, ubicación habitual) y fraude inyectado siguiendo
  los dos patrones descritos arriba — incluyendo a propósito casos "ruidosos" que
  parecen sospechosos por una sola señal (un monto alto legítimo, una hora rara
  legítima) pero no lo son, para que el modelo no pueda ganar con un solo umbral.
- **Para validar contra fraude real, más adelante:** el dataset público más parecido
  a los campos que describimos es **PaySim** (simulador de transacciones de dinero
  móvil, con monto, tipo de transacción, saldos antes/después y una etiqueta real de
  fraude), usado en cursos justamente porque se parece a un core bancario. La
  alternativa es el dataset de Kaggle "Credit Card Fraud Detection" (features
  anonimizadas por PCA, monto y tiempo, con etiqueta real). Cualquiera de los dos
  reemplaza a `generar_datos.py` sin cambiar el resto del pipeline, porque el
  entrenamiento espera un CSV con las mismas columnas lógicas.

## Métrica de evaluación

Accuracy no sirve: el fraude real es una fracción pequeña de las transacciones (en
nuestros datos sintéticos lo mantenemos entre 1% y 3% a propósito, para que se parezca
a la proporción real), así que un modelo que siempre responde "no es fraude" ya tiene
más de 97% de exactitud y es inútil. `src/entrenar_modelo.py` reporta precisión,
recall, F1 y el área bajo la curva precisión-recall (AUC-PR) para el modelo y para una
regla de umbral fijo equivalente a la idea original, lado a lado — esa comparación es
la evidencia numérica de la prueba de necesidad, no solo el argumento teórico.

## Resultado del prototipo (primera corrida)

Con datos sintéticos (16 000 transacciones, 400 cuentas, 1.8% de fraude), la regla
de umbral fijo (monto por encima del percentil 95 global, o transacción de
madrugada — la idea original) obtiene **recall 100% pero precisión 22.7%**: atrapa
todo el fraude, pero de cada 10 transacciones que marca, casi 8 son de clientes
legítimos (pagos grandes de rutina, horarios nocturnos normales para esa cuenta).
Operativamente eso es inviable: significa bloquear o llamar a revisión a la gran
mayoría de clientes honestos. El modelo (Random Forest sobre el perfil histórico de
cada cuenta) obtiene **recall 98.8% y precisión 97.7%**, con AUC-PR de 0.998 contra
0.227 de la regla. Esa diferencia — no la intuición, el número — es la evidencia de
que el problema no se resolvía con tres condicionales. El detalle completo está en
la salida de `src/entrenar_modelo.py`.

Una advertencia honesta para no sobrevender esto: los datos son sintéticos y el
modelo conoce la misma lógica con la que se generó el fraude, así que este resultado
prueba que el *pipeline* funciona, no que el modelo funcionaría igual de bien sobre
fraude real. Por eso el paso siguiente (ver "Próximos pasos") es correr lo mismo
sobre PaySim o Kaggle antes de presentar esto como validado.

**Detector de viaje imposible** (el segundo tipo de fraude, implementado después en
`src/detectar_viaje_imposible.py`): sobre los mismos datos sintéticos, la regla
determinista (distancia entre coordenadas contra tiempo transcurrido, velocidad
límite de 900 km/h) obtiene **precisión 100% y recall 99.3%** (148 de 149 casos
inyectados, cero falsos positivos). Este resultado tan limpio es esperado y no es
sospechoso como sí lo sería en un modelo de ML: la regla es exacta por
construcción, que es justo el argumento de por qué esta pieza no necesita un
modelo — no hay ambigüedad que aprender, solo una fórmula de física.

## Qué queda fuera de alcance por ahora

- Fraude de identidad sintética y lavado de activos (necesitan datos que no tenemos).
- Bloqueo automático de cuentas: el sistema puntúa y explica, un humano decide.
- Entrenar con datos reales de un banco (no tenemos acceso); se sustituye por datos
  sintéticos documentados como tales, y se deja preparado el cambio a PaySim o Kaggle.
- La interfaz de consultas en lenguaje natural (el componente LLM) es la segunda
  etapa, después de validar que el puntaje de riesgo funciona sobre datos sintéticos.

## Próximos pasos

1. ~~Correr `generar_datos.py` y `entrenar_modelo.py`, revisar que el modelo supere
   de forma clara a la regla de umbral fijo en precisión y recall.~~ Hecho.
2. ~~Implementar el detector de viaje imposible como código determinista.~~ Hecho —
   ver `src/detectar_viaje_imposible.py` y el resultado arriba.
3. Descargar PaySim o el dataset de Kaggle y correr el mismo pipeline sobre datos con
   fraude real, no solo el inyectado por nosotros. Pendiente de que el equipo
   consiga el archivo (no hay forma de descargarlo automáticamente sin sus
   credenciales de Kaggle).
4. **Persistir los casos marcados.** Hoy `entrenar_modelo.py` y
   `detectar_viaje_imposible.py` solo imprimen métricas; ninguno guarda la lista de
   transacciones sospechosas. Sin esa lista no hay nada sobre lo que consultar en el
   paso 5 ni nada que explicar en el paso 6. Falta decidir el formato (CSV, SQLite,
   JSON) y qué campos lleva cada caso; no depende del dataset real, se puede empezar
   ya.
5. Construir la vista del analista: la app (Streamlit) con la lista de casos
   marcados, el detalle de cada caso con su score desglosado, y el agente LLM
   embebido que consulta, resume y explica (componente LLM — las consultas y la
   explicación por caso se fusionaron en esta pieza el 2026-10-10 por pedido del
   profesor; ver la actualización de esa fecha).
6. Llevar este documento y los resultados numéricos a la próxima asesoría con Julián.

Cada componente pendiente se construye con el flujo de skills-rol del proyecto
(`requisitos-fraude` → `disenar-fraude` → `construir-fraude` → `validar-fraude`), una
skill por fase, en `.claude/skills/`. Detalle de cada sesión de planeación (qué se
decidió, arquitectura y checklist vigente) en `plan-construccion.md`.

## Actualización 2026-10-09 — alineación con los requisitos de la materia

Tras revisar el programa oficial del curso en el campus virtual y el material de las
semanas 7 a 10, se decidió con el equipo:

1. **La persistencia de los casos marcados (paso 4) será en Postgres sobre Docker**,
   no en CSV/SQLite/JSON: la materia trabaja Postgres desde la semana 7 y su reto
   exige consumir el servidor MCP de Postgres sobre la base de datos del proyecto.
2. **La interfaz de consultas (paso 5) se construye como agente con herramientas
   propias** — mínimo dos herramientas de dominio, los 4 límites de seguridad
   obligatorios (iteraciones máximas, presupuesto de tokens, aprobación humana para
   escrituras, timeout por herramienta) y una capa de abstracción del proveedor LLM
   conmutable. No es un extra: es el requisito central de la entrega de la semana 11.
3. **Estrategia de datos: consulta directa sobre la base de datos, sin RAG.** Los
   datos son tabulares; según el árbol de decisión de la semana 8, montar un
   pipeline vectorial aquí sería IA innecesaria — y sustentar ese "no" con la tabla
   de la clase califica igual o mejor en la rúbrica.
4. **Se suma al alcance una suite de evaluación**: 5-10 casos con respuesta
   verificada a mano (al menos uno que el sistema deba rechazar), un script que los
   corre, trazas visibles de qué herramienta pidió el agente, y la línea base de las
   cuatro cifras con fecha (tasa de éxito, costo por tarea, latencia mediana,
   recuperación). Complementa — no reemplaza — las métricas del modelo
   (precisión/recall/F1/AUC-PR) que ya exige este documento.
5. **Se suman los documentos `docs/decisiones/semana07..10.md`** con las plantillas
   que da cada reto del curso.

El orden de construcción y el checklist vigente están en `plan-construccion.md`
(sesión 2026-10-09).

## Actualización 2026-10-10 — feedback del profesor: el agente vive con el analista

En la revisión con el profesor Julián pidió subir el nivel de la pieza LLM. Sus
palabras, traducidas a requisitos:

1. **El agente va dentro de la vista del analista, no en una pantalla aparte.** El
   analista ve la lista de transacciones marcadas y, en esa misma vista, abre un caso
   y le pregunta al bot. Deja de existir "interfaz de consultas" como componente
   separado de "explicación por caso": son una sola pieza.
2. **Por cada caso marcado el agente entrega tres cosas:** un resumen de qué pasó
   (qué hizo esa cuenta, cuándo y dónde), por qué es un riesgo (qué se desvió del
   perfil histórico de *esa* cuenta — el mismo argumento que sostiene el modelo), y
   una recomendación de bloqueo argumentada a partir del scoring ("se debería
   bloquear porque…"), no un veredicto seco.
3. **Trazabilidad: score → features que pesaron → explicación.** La explicación no
   puede ser texto que el LLM redacte sin evidencia: tiene que poder rastrearse hasta
   el score real del Random Forest y las señales concretas del caso. Cómo se
   resuelve: al marcar un caso se calculan y persisten sus **desviaciones por
   feature** contra el perfil histórico de la cuenta (monto vs. su promedio, hora
   vs. sus horas habituales, ubicación vs. la habitual) — que son literalmente las
   features del modelo —, y el agente solo puede explicar citando esos valores
   guardados, que obtiene vía sus herramientas (p. ej. `obtener_caso`,
   `obtener_perfil_cuenta`, `obtener_score_y_features`). **SHAP por predicción queda
   como mejora opcional si sobra tiempo**, documentada pero no requisito: suma rigor,
   no reemplaza a las desviaciones como soporte narrable de la demo.
4. **La explicación pasa de opcional a obligatoria** (ya actualizado en el mapa del
   modelo de arriba). La frontera que no cambia: el bloqueo lo decide un humano; el
   agente recomienda y argumenta, nunca ejecuta el bloqueo.

Decisiones de implementación tomadas con el equipo en la sesión de planeación de esta
fecha (detalle en `plan-construccion.md`, cuarta sesión):

- **La vista del analista se construye con Streamlit** (todo en Python, rápido de
  montar, cubre tabla + detalle + chat; cumple el requisito de "usable por alguien
  ajeno al equipo, no terminal" de la semana 9 sin gastar días en frontend que la
  rúbrica no puntúa).
- **La explicación se genera al marcar el caso y se guarda en Postgres, con botón de
  regenerar en la UI** (modo híbrido): la demo no depende del API en vivo para
  mostrar explicaciones (inmune a un 429 frente a la clase), cada explicación queda
  auditada junto a su score y sus features, y el analista puede pedir otra redacción
  o repreguntar en vivo vía el agente.

Esto beneficia directamente a la rúbrica del Momento 2: la trazabilidad guardada es
la base de las "trazas visibles", las herramientas del agente son las ≥2 herramientas
de dominio del FastMCP (semana 7), y la explicación pre-generada es parte de la
estrategia de degradación ante 429/timeout (semana 9).

## Actualización 2026-10-21 — el profesor insiste: que el analista no interprete el score

Julián volvió sobre el mismo punto del 2026-10-10, con más detalle: al analista no
le debe llegar una alerta con una calificación que tenga que interpretar, sino el
caso ya razonado — qué pasó, qué secuencia de hechos llevó a la alerta, por qué eso
es un riesgo para *ese* cliente y qué se debería bloquear. Lo que agrega frente a la
actualización anterior:

1. **El objetivo del bloqueo se nombra.** La recomendación dice *qué* bloquear
   (tarjeta, acceso a la cuenta, o solo verificar con el cliente), no un "bloquear"
   genérico.
2. **El caso es una secuencia, no una fila.** "Pasó por esto, esto y esto" exige
   narrar las transacciones recientes de la tarjeta que desembocan en la alerta, en
   orden cronológico. El agente necesita una herramienta más para leer ese historial.

Decisiones tomadas con el equipo en esta fecha:

- **El nivel de bloqueo lo decide una regla y el LLM lo argumenta.** Se amarra a los
  dos tipos de fraude del alcance: uso no autorizado → bloquear la tarjeta; toma de
  control (viaje imposible) → bloquear el acceso a la cuenta; score intermedio →
  verificar con el cliente sin bloquear. Con los seis ejes: la entrada ya es
  estructurada (tipo de fraude y score), la regla se escribe exacta, se necesita
  determinismo y el costo del error es alto → código, no modelo. El LLM solo redacta
  el porqué citando las desviaciones guardadas. El bloqueo sigue siendo decisión
  humana; la regla produce una *recomendación*.
- **Dataset real: Sparkov** (Kaggle "Credit Card Transactions Fraud Detection",
  `fraudTrain.csv` / `fraudTest.csv`, licencia CC0). Reemplaza a PaySim y a Kaggle
  ULB como opción de validación porque es el único de los tres con historial por
  tarjeta, fecha-hora, monto, categoría y coordenadas: PaySim casi no repite cuentas
  de origen (no hay perfil que construir ni historia que narrar) y ULB no trae ni
  cuenta ni ubicación. Es simulado, pero no por nosotros, así que responde la crítica
  de que el modelo conoce la lógica con la que se generó el fraude. Limitación
  conocida: casi siempre es una tarjeta por cliente, y no trae casos etiquetados de
  viaje imposible — ese detector sigue validado sobre sintéticos y sobre Sparkov solo
  se mide su tasa de falsas alarmas.
- **Se corrige una filtración en `entrenar_modelo.py`.** El perfil de cada cuenta se
  calculaba con *todas* las transacciones (incluida la misma fraudulenta y las
  futuras) y después se partía al azar. Un sistema real solo conoce el pasado de la
  cuenta, así que parte del 97–99 % puede venir de ahí. Además, si el resumen dice
  "6 veces su promedio", ese promedio no puede incluir la transacción que se está
  explicando. El perfil pasa a calcularse solo con el historial previo y la
  partición pasa a ser temporal. Los números de "Resultado del prototipo" quedan
  como referencia histórica hasta que se recalculen.
- **Orden: primero el motor de riesgo**, porque todo lo que va encima (Postgres,
  vista, agente) depende de que las razones sean verdaderas.
- **Postgres sigue en Docker local** (setup de la semana 7).

De la transcripción de la última clase se rescata una sola idea que aplica aquí:
diseñar el camino de falla. Si el LLM falla (429, timeout) se muestra la explicación
guardada o una versión de plantilla armada solo con las desviaciones; si el LLM cita
una razón que no está en los datos del caso, la salida se rechaza — ese rechazo es un
candidato natural al caso de rechazo de la suite de evaluación.

## Actualización 2026-10-21 (2) — entrega del Momento 2 y arquitectura de la app

El sitio del curso publicó la página de entrega del Momento 2 (`/semana09/entrega_momento2`)
y reescribió la semana 9. Lo que cambia para este proyecto:

- **Entrega: sábado 31 de octubre de 2026**, demo de 6 min + 3 min de preguntas, con
  el entorno arriba desde el minuto cero.
- **ZIP autosuficiente** con `README.md` (contrato de arranque, modelo y proveedor
  justificados), `docker-compose.yml`, `run.sh`, `.env.example` sin llaves,
  `docs/decisiones.md` y `eval/`. Debe levantar con un comando en menos de 5 min;
  si no corre, la nota es cero.
- **Un solo `docs/decisiones.md`** reemplaza a los `docs/decisiones/semana07..10.md`
  previstos el 2026-10-09.
- **Prohibido el streaming falso** (lo revisan en DevTools): solo SSE real o estados
  honestos del proceso. Fallos forzados en vivo: 429 con conmutación a un proveedor
  de respaldo, timeout con reintento y JSON roto con reintento y degradación.
- La rúbrica ya no menciona MCP.

Decisiones tomadas con el equipo (el usuario pidió "buena ingeniería, no lo mínimo"
y delegó la elección técnica):

- **La vista del analista pasa de Streamlit a FastAPI + SSE real + frontend propio**
  (HTML/CSS/JS servido por el mismo backend), todo en `docker-compose` con Postgres.
  Reemplaza la decisión del 2026-10-10. Por qué: el reto exige SSE real o estados
  honestos y lo revisan en DevTools; una API con capas (datos, agente, proveedores,
  presentación) es lo que la rúbrica premia en "App" y "Agente", y la app de
  referencia del profesor (`semana09/demo`) usa el mismo patrón.
- **Proveedores: Gemini (`gemini-3.8-flash`) principal y Claude (Haiku 5.5) de
  respaldo**, más un último escalón sin red: la explicación de plantilla armada solo
  con las desviaciones guardadas. Las llaves van solo en variables de entorno, nunca
  en archivos del proyecto.
- **MCP:** las herramientas del agente viven en un módulo propio, desacoplado del
  bucle del agente. Se usan por tool calling y, si queda tiempo después de la
  medición, se exponen con un adaptador FastMCP pequeño, como demostración de que la
  capa está bien separada. No se consume el MCP de Postgres.

## Resultado del motor sobre Sparkov (2026-10-21) — reemplaza al "Resultado del prototipo"

Corrida de `python entrenar_modelo.py --fuente sparkov` con la filtración corregida,
partición temporal (entrenamiento 2019-01-01 a 2020-03-20, validación 2020-03-21 a
2020-06-21, prueba 2020-06-21 a 2020-12-31) y umbrales elegidos en validación. Tramo
de prueba (555 719 transacciones, 0,386 % de fraude):

| | Precisión | Recall | F1 | AUC-PR |
|---|---|---|---|---|
| Regla de umbral fijo (monto > p95 del entrenamiento o antes de las 6 h) | 0,014 | 0,845 | 0,028 | 0,012 |
| Regresión logística | 0,340 | 0,606 | 0,436 | 0,277 |
| Random Forest | 0,812 | 0,779 | 0,796 | 0,863 |
| **HistGradientBoosting (elegido por AUC-PR en validación)** | **0,786** | **0,838** | **0,811** | **0,884** |

Sin las tarjetas nuevas (artefacto de Sparkov: toda tarjeta sin historial es fraude),
el modelo elegido queda en precisión 0,773, recall 0,832, F1 0,801 y AUC-PR 0,875. El
artefacto aporta poco, pero se reporta aparte para no venderlo como capacidad.

A nivel de caso, con la regla de "2 o más transacciones sobre el umbral de bloqueo en
48 h": 249 casos de `bloquear_tarjeta`, 215 de ellos con fraude confirmado (86,3 %), y
215 de las 218 tarjetas con fraude cubiertas por algún caso. La cola de
`verificar_cliente` (621 casos, 0,8 % con fraude) está en revisión.

Lectura para la prueba de necesidad: la regla de umbral fijo, que era la idea
original, marca el 85 % del fraude pero con 1,4 % de precisión. Es decir, casi 70
falsas alarmas por cada fraude real. El modelo, que compara cada compra con el perfil
previo de su propia tarjeta, sube la precisión a 79 % con más recall. Los números
históricos de los sintéticos (97,7 % frente a 22,7 %) quedan como referencia: esos
datos son demasiado fáciles (los modelos dan 1,000 aun sin filtración) y solo
demuestran que la tubería y el detector de viaje imposible funcionan.

### Cierre del motor (2026-10-21, tras dos pasadas de `validar-fraude`)

- La cola de verificación quedó **solo para casos de 2 o más transacciones
  marcadas**: una compra aislada no abre caso (en Sparkov esa cola tenía 621 casos
  con 0,8 % de fraude). Resultado en Sparkov: **287 casos**, de ellos 249 de
  `bloquear_tarjeta` (86,3 % con fraude confirmado) y 38 de `verificar_cliente`
  (5,3 %); 213 de las 218 tarjetas con fraude quedan cubiertas.
- **Los sintéticos ahora inyectan el uso no autorizado en ráfagas** de 2 a 6 compras
  (como el fraude real de Sparkov), más ráfagas legítimas como ruido. Resultado: 52
  casos (19 `bloquear_tarjeta`, 33 `bloquear_acceso_cuenta`), todos con fraude
  confirmado. El detector de viaje imposible queda en precisión 1,000 y recall 0,967
  (145 de 150). Los sintéticos siguen siendo fáciles (AUC-PR 0,999): sirven para
  mostrar la tubería y el viaje imposible, no como evidencia del modelo.
- Las razones de cada transacción se ordenan por **contribución al score**
  (oclusión) y se citan con su **rareza en percentil** frente a las compras normales.
  Solo las relevantes llegan al LLM. Validado: las 15 026 descripciones cuadran con
  sus valores.

## Actualización 2026-10-21 (3) — orden de proveedores

Reemplaza la línea de proveedores de la actualización 2026-10-21 (2). Queda **Claude
Haiku 5.5 (`claude-haiku-5-5`) como principal y Gemini 3.1 Flash-Lite
(`gemini-3.1-flash-lite`) como respaldo**, con la plantilla sin red como último
escalón. El orden se configura con `ORDEN_PROVEEDORES` (por defecto `claude,gemini`).

Por qué, medido el mismo 21 de octubre y no supuesto:

- **Gemini 3.8 Flash no servía como principal ese día**: respondía 503 ("high
  demand") o tardaba 25-40 s por llamada, más que el timeout de 25 s del agente. 3.1
  Flash-Lite sí atendía tool calling en 4-17 s, así que pasó a ser el respaldo.
- **Claude razonaba por defecto**: Haiku 5.5 gastaba unos 1 400 tokens de
  pensamiento invisibles por respuesta, el primer token tardaba unos 9 s y la
  respuesta casi llenaba `max_tokens`. Redactar sobre evidencia ya calculada no lo
  necesita: se apagó (`CLAUDE_RAZONAMIENTO=false`, reactivable). Con eso las
  explicaciones salen en 5-8 s y cuestan unos USD 0,002.
- **Límites ajustados por medición**: una explicación con reintento de contrato
  consumió unos 28 000 tokens de entrada (cada iteración reenvía la conversación), por
  eso el presupuesto por tarea pasó de 24 000 a **40 000**; y la versión .1 del
  prompt se cortaba en `max_tokens`, que pasó de 1 800 a **2 500**.
- **Prompt**: la versión .2 fijó límites de extensión por campo (la .1 se cortaba) y
  la .3 prohibió los nombres internos de señales en el texto (`monto_24h`, etc.).

### Correcciones tras validar la app (prompt .4)

La validación de la app (`validacion/app-analista.md`) y la primera corrida de
`eval/` dejaron estas decisiones:

- **El nivel de riesgo en palabras lo arma el código**
  (`app/agente/riesgo_en_palabras.py`), no el LLM: en 3 de 9 explicaciones el modelo
  escribió lo contrario del percentil que citaba ("en el tope" con percentil 33,8). La
  frase sale del score, los umbrales, las transacciones sobre el umbral de bloqueo y
  el percentil entre los casos de su fuente. Mismo criterio de los seis ejes: entrada
  estructurada, regla exacta y error caro → código.
- **Sin evidencia no hay explicación**: una respuesta que llega sin haber consultado
  `obtener_caso` se descarta en el bucle (se le pide consultar) y el contrato la
  rechaza. La pantalla borra el borrador en cuanto el servidor lo rechaza.
- **El rechazo en modo pregunta es estructurado**: herramienta
  `declarar_fuera_de_alcance`, en lugar de buscar la frase "Fuera de alcance:" en el
  texto, que falló en los dos sentidos en `eval/`.
- **Tarjetas sin historial**: el texto no puede describir un gasto o promedio
  "habitual" (el contrato lo rechaza), porque esas cifras del motor salen de la propia
  ráfaga.
- **Métricas**: la tasa de éxito ya no cuenta las aperturas desde caché, y la
  recuperación cuenta los contratos inválidos como fallos (fórmulas en
  `repositorio.resumen_metricas`). El TTFT se mide en la llamada que produjo la
  respuesta final, no en un preámbulo.
