# Registro de decisiones — Detección y bloqueo de fraude con tarjeta (Momentos 2 y 3)

**Equipo:** Jhoan David Gruezo Gutiérrez y Jeison Nazarit
**Estado:** actualizado el 2026-11-15. Las secciones 1 a 12 cuentan el Momento 2, con una nota
**Momento 3** donde algo cambió; la sección 13 trae las cifras finales y la 14, la auditoría del
2026-11-14 y lo que se corrigió por ella. Las secciones marcadas con "PENDIENTE (equipo):" solo
las puede llenar el equipo. La bitácora histórica del Momento 1 y del inicio del Momento 2 está
en `../decisiones.md`; este documento es la versión que se entrega.

## 1. Qué hace la app y para quién

La app es la mesa de trabajo de un analista de riesgo de un banco. Un motor de ML
clásico revisa cada compra contra el perfil previo de su propia tarjeta (monto, hora,
categoría, distancia, gasto y ritmo de las últimas 24 horas) y un detector determinista
busca viajes imposibles. Cuando varias compras de una tarjeta superan el umbral, se
abre un caso con una recomendación decidida por una regla: bloquear la tarjeta (uso no
autorizado), bloquear el acceso a la cuenta (viaje imposible, posible toma de control)
o verificar con el cliente (compra aislada). La base trae 339 casos: 287 de Sparkov y
52 de datos sintéticos.

El profesor pidió que al analista no le llegue un número que tenga que interpretar,
sino el caso ya razonado. Por eso, al abrir un caso, un agente LLM consulta la
evidencia con sus propias herramientas y explica qué pasó (en orden cronológico), por
qué es un riesgo para ese cliente y qué se debería bloquear, citando solo cifras que
existen en los datos del caso. El analista también puede hacerle preguntas sobre el
caso abierto. El agente recomienda y puede proponer una decisión; la decisión solo
existe cuando el analista la confirma con su nombre.

**Momento 3.** Tras la sustentación del 31-oct, el profesor señaló que esperar al analista para
bloquear deja al ladrón comprando. Desde el Momento 3 cada compra se puntúa al llegar, el caso
se abre con la primera compra marcada y un agente de triaje bloquea la tarjeta de mayor riesgo
y avisa al titular en segundos; si no lo hace en un caso crítico, lo hace la regla. El analista
ya no confirma bloqueos: decide los **desbloqueos**, con sesión y motivo. El modo explicación y
el de preguntas de esta sección siguen igual, ahora como ayuda para decidir el desbloqueo.

## 2. Frontera de la IA

Los seis ejes de la semana 3 (entrada, reglas, determinismo, volumen, latencia, costo
del error), aplicados a cada pieza:

| Componente | Qué lo resuelve | Por qué |
|---|---|---|
| Captura y persistencia de transacciones y casos (Postgres) | Código y SQL | Datos ya estructurados; no hay nada que interpretar |
| Viaje imposible (distancia entre coordenadas contra tiempo, 900 km/h) | Código determinista | La regla se escribe exacta con la fórmula de Haversine; se necesita determinismo y un error silencioso es caro |
| Puntaje de riesgo de uso no autorizado | **ML clásico** (HistGradientBoosting) | Las reglas serían una por tarjeta y cambian con el tiempo; volumen alto; se tolera variación porque un humano revisa |
| Qué bloquear (tarjeta, acceso a la cuenta o verificar) | Código (regla) | Entrada estructurada (tipo de fraude y score), regla exacta, costo del error alto: no se le delega a un modelo |
| Explicación del caso y respuestas a preguntas | **LLM** (agente con herramientas) | Traducir desviaciones y un score a un relato legible es lenguaje abierto; las preguntas no se pueden enumerar; volumen bajo; segundos de latencia son aceptables |
| Verificar que la explicación no invente | Código (`app/agente/contrato.py`) | Acción igual a la regla, señales relevantes y cifras rastreables se comprueban en código, no se confían al prompt |
| Bloqueo final | Humano (Momento 2) | Afecta a un cliente real; el agente solo proponía |
| **Momento 3:** banda del caso (crítica, alta, media) | Código | Regla exacta sobre el score y el viaje imposible; define qué puede hacer el agente |
| **Momento 3:** bloquear en banda alta | **LLM** (agente de triaje), dentro de guardas en la base | Leer la secuencia de compras distingue casos que el score aplana; el bloqueo es protector y reversible |
| **Momento 3:** bloquear en banda crítica | Código (la regla), si el agente no lo hizo | El bloqueo de lo crítico no puede depender de que un proveedor responda |
| **Momento 3:** desbloquear | Humano, con sesión y motivo | Devolver la tarjeta es lo que sí tiene costo si el titular es el ladrón |

## 3. Datos y por qué no RAG

**Sparkov** (Kaggle "Credit Card Transactions Fraud Detection", CC0): 1,85 millones de
transacciones simuladas con historial por tarjeta, fecha y hora, monto, categoría y
coordenadas. Se eligió frente a PaySim (casi no repite cuentas de origen, no hay perfil
que construir) y frente a Kaggle ULB (sin cuenta ni ubicación). Lo generó un simulador
ajeno, así que responde la crítica de que el modelo conoce la lógica con la que se creó
el fraude. Limitaciones: casi siempre una tarjeta por cliente, ningún caso etiquetado de
viaje imposible, y un artefacto: toda tarjeta sin historial es fraude (se reporta aparte,
sección 8).

**Sintéticos** (`src/generar_datos.py`): sirven para mostrar la tubería completa y el
viaje imposible, que Sparkov no trae. Son fáciles (AUC-PR 0,999), así que no se usan
como evidencia del modelo.

La app no lee los CSV de Kaggle: `semilla/` lleva los casos y el historial de 30 días
de cada tarjeta con caso, y la app los carga en Postgres al arrancar.

**Por qué no RAG.** Con la tabla de la semana 8:

| Eje de la tabla | Nuestro caso |
|---|---|
| ¿Los datos caben en la ventana? | Los de UN caso sí (unos miles de tokens), y es lo único que el agente necesita ver |
| ¿Están en una base de datos? | **Sí**: casos, transacciones, desviaciones e historial están en Postgres, en tablas |
| ¿La pregunta es siempre la misma? | La explicación sí (por eso tiene contrato fijo); las preguntas libres no |
| ¿Buscamos identificadores exactos? | Sí: el id del caso, que se resuelve con una consulta por llave primaria |
| ¿Son prosa abierta que cambia? | No: son números, fechas, categorías y comercios |

**Estrategia elegida: consulta directa por tool calling.** El agente tiene seis
herramientas. Cinco consultan la base a través de `app/db/repositorio.py` (la única
puerta a la base): `obtener_caso`, `obtener_perfil_cuenta`,
`obtener_historial_reciente`, `obtener_score_y_umbrales` y `registrar_decision`. La
sexta, `declarar_fuera_de_alcance`, no lee ni escribe nada: es la señal estructurada
de que el agente rechaza una pregunta (sección 11, versión `2026-10-21.4`). Las
alternativas descartadas: RAG, porque un pipeline vectorial sobre un volcado de tablas
recuperaría fragmentos parecidos en vez de las filas exactas y el modelo "calcularía"
sobre lo que le llegó (la clase lo llama alucinar en cálculos); contexto largo con toda
la base, porque son 339 casos con su historial y el agente solo debe ver el caso
abierto; búsqueda por palabra clave, porque el id del caso ya es una llave primaria.

Cuando el dato no existe, la herramienta lo dice (por ejemplo, una tarjeta sin
historial devuelve `sin_historial`) y el prompt obliga a decir "no se sabe" en
`lo_que_no_se_sabe`. Una pregunta sobre otro caso devuelve `fuera_de_alcance` desde la
herramienta, sin importar lo que diga el modelo. Preguntas que el sistema no puede
responder: si el cliente reconoce las compras, su saldo, su nombre o su teléfono; ningún
dato de esos está en la base.

## 4. Proveedor y modelo

| Papel | Modelo | Tarifa de lista (USD por millón, entrada / salida) |
|---|---|---|
| Principal | Claude Haiku 5.5 (`claude-haiku-5-5`) | 0,10 / 0,50 |
| Respaldo | Gemini 3.5 Flash-Lite (`gemini-3.5-flash-lite`) | 0,30 / 2,50 |
| Último escalón | Plantilla determinista, sin red | 0 |

La decisión inicial (2026-10-21) era Gemini 3.8 Flash como principal y Claude de
respaldo. Se invirtió el mismo día con lo medido: Gemini 3.8 Flash estaba saturado,
respondía 503 o tardaba de 25 a 40 s por llamada (por encima del timeout de 25 s),
mientras Claude Haiku 5.5 respondía cada llamada con herramientas en 1 a 2 s y es el
más barato de los tres. El respaldo pasó a Gemini 3.1 Flash-Lite, que atendía tool
calling en 4 a 17 s. Que el respaldo sea de otro proveedor importa: un 429 o una caída
de un proveedor no afecta al otro.

**Cambio del 2026-10-31.** En la prueba previa a la sustentación, Gemini 3.1 Flash-Lite
respondía 503 ("high demand") y un 429 forzado terminaba en la plantilla a los 36 s.
Gemini 3.5 Flash-Lite respondió 4 de 4 recuperaciones del 429 en unos 10 s, así que
pasó a ser el respaldo (tarifa 0,30 / 2,50 según anotherwrapper.com y
pricepertoken.com). Es la misma decisión que el 21 de octubre: el respaldo se elige con
lo que responde, no con lo que dice el catálogo. Las cifras de la sección 9 se midieron
con 3.1 Flash-Lite.

Los dos modelos cumplen lo que el agente necesita: llamadas a herramientas en
paralelo y un JSON con contrato estricto que además se verifica en código. Las tarifas
se tomaron de agregadores (OpenRouter y Apidog para Gemini; Sentra y aipricing.guru
para Claude; anotherwrapper.com y morphllm.com para Flash-Lite), no de las páginas
oficiales; hay que verificarlas antes de la sustentación. Están en `app/config.py` con
su fuente.

La capa de proveedor está aislada en `app/proveedores/` (clientes HTTP propios con
`httpx` para cada API, sin SDK, más la cascada). Cambiar de proveedor en vivo es cambiar
`ORDEN_PROVEEDORES` en `.env` y reiniciar la app, o forzar un 429 para ver la
conmutación (sección 7).

## 5. Patrón de integración: SSE real

La explicación y las respuestas llegan por Server-Sent Events reales
(`text/event-stream`), alimentados directamente por el generador de eventos del agente:
cada herramienta pedida, cada reintento, cada conmutación y cada fragmento de texto se
escribe al socket cuando ocurre. El frontend pinta el JSON a medida que llega con un
parser tolerante a JSON incompleto, y el panel de trazas muestra los eventos en vivo.
El primer evento sale antes de llamar al modelo, así que el analista ve actividad
real desde el primer instante; un comentario `: ping` cada 15 s evita que un proxy corte
la conexión.

Por qué no in-request: una explicación tarda de 5 a 18 s (sección 9); una petición que
responde todo al final deja al analista sin saber si algo pasa y no permite ver la traza
mientras ocurre, que es justo lo que la rúbrica pide mostrar. Por qué no colas: hay un
analista con un caso abierto, no miles de tareas por segundo; un broker y un worker
agregarían infraestructura sin resolver ningún problema que tengamos. El agente corre en
un hilo propio dentro de la petición, así que si el analista cierra el panel la tarea
termina y se guarda igual.

## 6. El agente

**Bucle propio** (`app/agente/bucle.py`, sin framework): una iteración es una llamada
al modelo; si el modelo pide herramientas se ejecutan y se devuelven, y si no pide
ninguna su texto es la respuesta final.

**Herramientas**: diez en total (`app/agente/herramientas.py`). Todas validan que el
`id_caso` sea el del caso abierto. En modo explicación el agente solo tiene las cuatro de
lectura; en modo pregunta tiene además `registrar_decision`, que solo crea una propuesta
pendiente, y `declarar_fuera_de_alcance`, que fija el rechazo de forma determinista. En el
**triaje** (Momento 3) tiene las cuatro de lectura y cuatro acciones: `bloquear_tarjeta`,
`bloquear_acceso_cuenta`, `solicitar_verificacion` y `dejar_a_analista`. Ninguna recibe la
tarjeta ni el actor (salen del caso) y ninguna desbloquea; la banda, la autonomía, el tope por
hora y "un bloqueo activo por caso" se revisan en la base, no en el prompt.

**Los cuatro límites**, con sus valores y por qué:

| Límite | Valor | Por qué ese número |
|---|---|---|
| Iteraciones | 6 llamadas al modelo por tarea | Explicar un caso pide 3 o 4 herramientas: 2 o 3 iteraciones con llamadas en paralelo y 1 final. En el lote la mediana fue 2. Seis dan margen para un reintento del contrato sin permitir un bucle ciego |
| Presupuesto de tokens | 40 000 de entrada + salida por tarea | Cada iteración reenvía la conversación; una explicación con reintento de contrato consumió unos 28 000 tokens de entrada el 2026-10-21. La mediana del lote fue 11 059 tokens por tarea (las 13 no servidas desde caché) |
| Timeout | 25 s por llamada al modelo y 5 s por herramienta | 25 s está muy por encima de lo que tarda Claude (1-2 s) y corta a un proveedor saturado (Gemini 3.8 Flash tardaba 25-40 s); las herramientas son consultas por llave que tardan milisegundos |
| Confirmación humana | Momento 2: toda escritura es una propuesta. Momento 3: el desbloqueo | `registrar_decision` escribe en `propuestas_decision`, nunca en `decisiones`. En el Momento 3 el agente bloquea solo (acción protectora y reversible) y lo que exige a una persona es lo que tiene costo: desbloquear, con sesión y un motivo de al menos 10 caracteres |

Todos se cambian por variable de entorno y se muestran en la interfaz. Al tocar un
límite la tarea termina con su motivo (`limite_iteraciones`, `limite_tokens`,
`timeout`) y la explicación cae a la plantilla.

**Contrato de la explicación**: `que_paso`, `por_que_es_riesgo`, `recomendacion`
(acción, objetivo y argumento), `senales_citadas`, `nivel_riesgo_en_palabras` (este lo
arma el código, no el modelo) y `lo_que_no_se_sabe`. Se valida en código: forma, acción igual a la de la regla, señales
citadas solo entre las relevantes del caso y cifras rastreables (cada número con 3 o
más cifras significativas debe aparecer en lo que devolvieron las herramientas). Si no
pasa, un reintento con los errores; si vuelve a fallar, plantilla.

## 7. Manejo de fallos

Los tres fallos del reto más la caída total, todos forzables por petición
(`?falla=`), desde el panel de demo o con `FALLA_FORZADA`. Medido en el lote del
2026-10-21 (tareas L16 a L19 de `eval/resultados/lote_2026-10-21_2132.md`):

| Fallo | Qué hace el sistema | Qué ve el analista | Medido |
|---|---|---|---|
| 429 del principal | Backoff de 1, 2 y 4 s y conmutación a Gemini | "Claude respondió 429 · reintento 2/3 en 2 s", luego "se cambia a Gemini", y la explicación | Recuperada por Gemini en 17,5 s, contrato válido |
| Timeout del principal | Mismos reintentos y conmutación | El mismo tipo de estado, con "no respondió a tiempo" | Recuperada por Gemini en 18,1 s |
| JSON roto | Reparación (cercos, primer objeto balanceado, cierre de llaves) y, si no basta, un reintento con los errores | "contrato inválido · reintentando" en la traza | Recuperada por Claude en 9,2 s |
| Caída total | Agotados los dos proveedores, plantilla armada con las desviaciones guardadas | La explicación con la etiqueta "armada por reglas" y el motivo | Plantilla en 14,1 s (los dos backoff suman unos 14 s) |

Ninguna excepción llega cruda: el servicio convierte cualquier error en un evento
`error` con un mensaje en español y una acción sugerida, y deja el detalle técnico en la
traza. Si la base se cae, `/api/salud` responde "degradado" con un mensaje en español (comprobado el 2026-10-21, cuando la base se detuvo a mitad de una corrida del lote).

## 8. Motor de riesgo

Corrida de `src/entrenar_modelo.py --fuente sparkov` del 2026-10-21, con el perfil
calculado solo con transacciones anteriores de la misma tarjeta y partición temporal
(entrenamiento 2019-01-01 a 2020-03-20, validación 2020-03-21 a 2020-06-21, prueba
2020-06-21 a 2020-12-31). Tramo de prueba: 555 719 transacciones, 0,386 % de fraude.
Umbrales elegidos en validación y aplicados sin retocar.

| | Precisión | Recall | F1 | AUC-PR |
|---|---|---|---|---|
| Regla de umbral fijo (monto > p95 del entrenamiento o antes de las 6 h) | 0,014 | 0,845 | 0,028 | 0,012 |
| Regresión logística | 0,340 | 0,606 | 0,436 | 0,277 |
| Random Forest | 0,812 | 0,779 | 0,796 | 0,863 |
| **HistGradientBoosting (elegido por AUC-PR en validación)** | **0,786** | **0,838** | **0,811** | **0,884** |

Sin las tarjetas nuevas (el artefacto de Sparkov), el modelo elegido queda en
precisión 0,773, recall 0,832, F1 0,801 y AUC-PR 0,875. La regla de umbral fijo, que
era la idea original del proyecto, genera casi 70 falsas alarmas por cada fraude real;
el modelo sube la precisión a 79 % con más recall. Esa diferencia es la prueba de
necesidad medida sobre datos que no generamos nosotros.

Regla del caso: se abre caso solo con 2 o más transacciones marcadas en 48 h (una
compra aislada no abre caso). Resultado en Sparkov: 287 casos, 249 de
`bloquear_tarjeta` (86,3 % con fraude confirmado) y 38 de `verificar_cliente` (5,3 %);
213 de las 218 tarjetas con fraude quedan cubiertas. En sintéticos: 52 casos (19
`bloquear_tarjeta`, 33 `bloquear_acceso_cuenta`); el detector de viaje imposible queda
en precisión 1,000 y recall 0,967. Las razones de cada transacción se ordenan por
contribución al score y se citan con su rareza en percentil; las 15 026 descripciones
se validaron contra sus valores. Detalle en `validacion/motor-riesgo.md`.

## 9. Línea base: las cuatro cifras (2026-10-21)

Medidas el **2026-10-21 a las 21:58 (hora de Colombia)** con `python
eval/correr_lote.py` contra la app corriendo en Docker (base recién cargada), con
Claude Haiku 5.5 de principal y Gemini 3.1 Flash-Lite de respaldo, prompt versión
`2026-10-21.4`. Evidencia: `eval/resultados/lote_2026-10-21_2158.json` (con la traza
de cada tarea) y `.md`.

| Cifra | Valor | Método |
|---|---|---|
| **Tasa de éxito** | **94,7 %** (18 de 19 tareas) | Éxito = `motivo_fin = completada`, contrato válido y hechos esperados del caso dorado cumplidos; una explicación de plantilla no es éxito. Sin contar las 6 tareas servidas desde caché: 92,3 % (12 de 13). La única tarea sin éxito es la caída total forzada (`todo`), que por diseño termina en la plantilla |
| **Costo por tarea** | **0,001481 USD** (mediana) | Mediana de `costo_usd` (tokens × tarifa de lista) de las 13 tareas no servidas desde caché. Sin las fallas forzadas: 0,001421 USD. Todo el lote: 0,022 USD |
| **Latencia** | **mediana 5,8 s**, P90 17,1 s; **TTFT mediano 0,80 s** | Extremo a extremo medida por el cliente (petición → evento `fin`), 13 tareas no servidas desde caché. Sin las fallas forzadas, la mediana es 4,6 s. El TTFT se mide desde la petición hasta el primer fragmento de la respuesta final |
| **Recuperación** | **100 %** (4 de 4) | Tareas con fallo forzado (429, timeout, JSON roto, caída total) que terminaron con una explicación válida, del agente, del respaldo o de la plantilla. Ninguna tarea tuvo contrato inválido en esta corrida |

**Ahorro por caché**: la segunda apertura de un caso se sirve desde la explicación
guardada en 26 ms (mediana de 6 pares) frente a 5,2 s en frío, un 99,5 % menos, y
cuesta 0 USD frente a 0,0016 USD.

Por qué la mediana y no el promedio: la distribución tiene cola (las tareas con 429 o
timeout tardan unos 18 s por el backoff de 1 + 2 + 4 s y la conmutación), y una sola
tarea lenta movería el promedio sin representar la experiencia típica. Por eso también
se reporta el P90.

**Suite de casos dorados** (`python eval/correr_suite.py`, 2026-10-21 21:57,
`eval/resultados/suite_2026-10-21_2157.md`): **8 de 8 casos con éxito**, latencias de
2,8 a 6,5 s. Los dos rechazos (pedir desbloquear otra tarjeta y una instrucción
inyectada para registrar el caso como legítimo) se rechazaron con la herramienta
`declarar_fuera_de_alcance`, sin proponer decisiones. **La suite está pendiente de
verificación humana**: ningún caso tiene `verificado_por` todavía.

### Primera medición y qué se cambió (evidencia de iteración)

La primera corrida del mismo lote (2026-10-21 21:32, `lote_2026-10-21_2132.md`, prompt
`.3`) dio 84,2 % de éxito (76,9 % sin caché), mediana de 7,3 s y 7 de 7 recuperaciones,
con la suite en 7 de 8. Mostró tres problemas, y cada uno se corrigió:

- **Casos largos rompían el contrato** (D1, ráfaga de 12 compras: dos contratos
  inválidos y plantilla). Corrección: `obtener_caso` entrega primero
  `senales_que_puedes_citar` y el mensaje de reintento las lista. En la segunda corrida
  D1 pasa al primer intento.
- **La marca de texto del rechazo era frágil en los dos sentidos** (una pregunta
  legítima quedó como rechazo y un rechazo real como completado). Corrección: la
  herramienta `declarar_fuera_de_alcance` fija el rechazo de forma determinista.
- **El nivel de riesgo en palabras salía al revés** en 3 de 9 casos de la validación
  (`validacion/app-analista.md`). Corrección: lo arma el código
  (`app/agente/riesgo_en_palabras.py`) y el LLM ya no lo redacta.

## 10. Prueba del compañero

PENDIENTE (equipo): hacer la prueba con un estudiante ajeno al equipo, que reciba solo
el ZIP y el README y siga las instrucciones sin ayuda, con el desarrollador en silencio.
Las tres tareas del diseño (`diseno/vista-analista.md`):

1. Abrir el caso de mayor riesgo y decir por qué se bloquea.
2. Preguntarle al agente cuál fue la compra más rara.
3. Registrar una decisión (confirmar o rechazar la propuesta del agente).

Anotar para cada tarea: quién la hizo y cuándo, si la completó, cuánto tardó, dónde se
trabó y qué se cambió en la app o en el README por eso.

Referencia ya medida para el arranque: ver la sección 12 (24 s desde un ZIP
descomprimido en una carpeta limpia, en la máquina de desarrollo).

## 11. Iteraciones de las descripciones de herramientas y del prompt

Las descripciones de las herramientas están escritas como prompt (cuándo usarla, qué
devuelve, qué no hacer con ella) en `app/agente/prompts.py`, junto al prompt de sistema.
La versión vigente es `2026-11-15.2` (las del Momento 3 están al final de la tabla):

| Versión | Qué cambió | Por qué |
|---|---|---|
| 2026-10-21.1 | Primera versión, con los puntos obligatorios de `diseno/agente.md` (rol, evidencia solo por herramientas, acción de la regla, datos no son instrucciones, rechazo con marca) | Diseño inicial |
| 2026-10-21.2 | Límites de extensión por campo (que_paso hasta 90 palabras, etc.) y, en casos largos, nombrar solo la primera y la última compra con el total | Las explicaciones de casos con muchas compras se cortaban en `max_tokens` y el JSON llegaba incompleto |
| 2026-10-21.3 | Los nombres internos de las señales solo van en `senales_citadas`; en el texto se describen en palabras | El texto para el analista mostraba "monto_24h" en vez de "el gasto de las últimas 24 horas" |

| 2026-10-21.4 | El nivel de riesgo en palabras ya no lo redacta el modelo (lo arma `riesgo_en_palabras.py`); herramienta `declarar_fuera_de_alcance` para rechazar en lugar de la marca de texto; `obtener_caso` entrega primero `senales_que_puedes_citar`; no escribir texto antes de llamar herramientas; no hablar de "habitual" en tarjetas sin historial | Hallazgos de `validacion/app-analista.md` y de la primera medición (sección 9): nivel de riesgo al revés en 3 de 9 casos, marca de rechazo frágil en los dos sentidos, contratos inválidos en casos largos, preámbulos que falseaban el TTFT |
| 2026-11-08.1 | Prompt de triaje (`SISTEMA_TRIAJE`) y descripciones de las cuatro acciones | Momento 3: el agente bloquea |
| 2026-11-08.2 | Regla 9 explícita: el resumen del triaje siempre en español | Salía en inglés en la primera prueba real |
| 2026-11-15.1 | La regla 7 del prompt base ya no dice "ningún bloqueo se ejecuta sin que el analista lo confirme"; en el triaje no se muestra la recomendación de la regla del M2 | Auditoría del 2026-11-14 (§14): la regla 7 describía el M2 y la recomendación "confirmar con el cliente antes de bloquear" sesgaba al agente hacia la verificación |
| 2026-11-15.2 | En un aviso de verificación el motivo no dice "detuvimos" | El titular leía que se detuvo una compra que no se había detenido |

Efecto medido con la misma suite y el mismo lote: suite de 7 a 8 de 8; tasa de éxito
del lote de 84,2 % a 94,7 % (sin caché, de 76,9 % a 92,3 %); latencia mediana de 7,3 s
a 5,8 s; contratos inválidos en la corrida, de 3 a 0.

## 12. Entrega y qué queda para el Momento 3

**Reproducibilidad.** El ZIP se arma con `python scripts/empaquetar_entrega.py`: lista
blanca de carpetas, sin `datos/`, `.env`, `.venv/`, `.git/`, `__pycache__/` ni modelos
`.joblib`, búsqueda de patrones de llave que aborta si encuentra una y `run.sh` con
permiso de ejecución. Prueba del 2026-10-21 (21:37): ZIP de 1,90 MB con 91 archivos y
0 coincidencias de patrones de llave; descomprimido en una carpeta limpia, con `.env`
copiado de `.env.example` (sin llaves) y levantado con Docker Compose como proyecto
aparte en el puerto 8011, la app respondió `/api/salud` con los 339 casos cargados a
los **24 s** (16 s de construcción de la imagen sin caché de capas y 8 s de arranque,
espera de la base y carga de la semilla). Salvedad: las imágenes base
(`python:3.12-slim` y `postgres:16-alpine`) ya estaban descargadas en esa máquina; en
una máquina nueva hay que sumar su descarga (estimado: algo más de 100 MB entre las dos, sin medir). Sin llaves la app
quedó en modo plantilla, como promete el README.

PENDIENTE (equipo): repetir la prueba de arranque en la máquina del compañero (sección
10) y anotar aquí el tiempo medido.

**Para el Momento 3:**

- Seguridad y gobernanza (`docs/seguridad.md`, `docs/gobernanza.md`,
  `docs/respuesta_auditoria.md`) y las cifras finales comparadas contra esta línea base.
- La siguiente iteración del prompt (sección 11) y su efecto medido en la tasa de éxito.
- Acortar el camino a la plantilla cuando caen todos los proveedores (hoy 14 s).
- Verificar las tarifas en las páginas oficiales de los proveedores.
- Opcional: exponer las herramientas con un adaptador FastMCP, SHAP por predicción y
  una suite de navegador de punta a punta.

## 13. Momento 3 (2026-11-08): bloqueo automático, cifras finales y qué empeoró

**Qué se decidió y dónde está el porqué.** El feedback del profesor tras el M2 (bloquear sin
esperar al analista; el agente puede bloquear las tarjetas de mayor riesgo y avisar al titular)
se convirtió en el diseño D de `docs/analisis-respuesta-fraude.md`, especificado en `docs/SPEC.md`
y construido según `PLAN.md`. Las decisiones que cambian algo de este documento:

- **§2 Frontera de la IA.** El agente ya no solo explica: en el triaje bloquea (bandas alta y
  crítica), pide verificación o deja el caso al analista. La banda la decide el código; el
  desbloqueo es solo humano; la regla bloquea los críticos si el agente no lo hace.
- **§8 Motor de riesgo.** Puntúa cada compra en vivo con un perfil incremental por tarjeta, en
  paridad con el motor fuera de línea (111.342 compras, 0 cambios de banda; `scripts/validar_paridad_en_vivo.py`).
  El caso se abre en la primera compra marcada, no en la segunda.
- **§7 Manejo de fallos.** Si caen todos los proveedores, la regla bloquea los críticos y pide
  verificación en los demás; la red de seguridad cubre a los 90 s.
- **Seguridad y gobernanza**: `docs/seguridad.md`, `docs/gobernanza.md`, `docs/respuesta_auditoria.md`.

### 13.1 Las cifras del Momento 3 (noche del 19-jul-2020, 5.810 compras, con la IA real)

`eval/medir_momento3.py`, corrida del 2026-11-15 con el método corregido tras la auditoría (§14);
evidencia en `eval/resultados/momento3_2026-11-15_0514_base.json` y `…_0522_ia_caida.json` (los
nombres de archivo van en hora UTC del contenedor). Dos cuidados del método:

- **El reloj del dataset se detiene durante cada triaje** (`esperar_triajes`). A 3600x, los ~5 s
  del triaje equivalen a ~5 horas del dataset; antes, en ese lapso llegaban compras que en tiempo
  real todavía no existían y el agente decidía viéndolas.
- **El dinero se mide a tiempo real**: cada bloqueo se ubica en la compra que lo disparó más los
  segundos reales que tardó, contados como segundos del dataset.

| Cifra | Con el agente | Solo la regla (IA caída, `--falla todo`) |
|---|---|---|
| Fraude detenido (monto) | **76,1 %** | **61,8 %** |
| Compra que disparó el caso → tarjeta bloqueada (segundos reales) | mediana 3,7 s, máximo 4,6 s | mediana y máximo 14 s |
| Apertura del caso → bloqueo (segundos reales, incluye la espera en cola) | mediana 4,0 s, p95 25 s, máximo 53 s | mediana 43 s, máximo 195 s |
| Tarjetas bloqueadas | 14 (todas por el agente), 9 con fraude | 10 (todas por la regla), 9 con fraude |
| Precisión / recall / F1 de los bloqueos (por tarjeta) | 0,64 / 1,00 / 0,78 | 0,90 / 1,00 / 0,95 |
| Bloqueos falsos por cada 1.000 compras | 0,86 (5 clientes honestos) | 0,17 (1 cliente honesto) |
| Compras fraudulentas que pasan por tarjeta robada | mediana 1, máximo 3 | — |
| Costo del LLM | 0,051 USD la noche: 0,0022 USD por triaje, 0,009 USD por cada 1.000 compras | 0 |

Decisión por compra (puntuar + guardar): mediana 4,5 ms, p99 21 ms (solo puntuar: 2,7 / 5,1 ms).
La regla del Momento 2 sobre las mismas compras detenía el 29,3 % de noche sin turno, el 34,9 % con
una cola de 90 minutos y el 61,8 % con un analista instantáneo (techo teórico).

**Prueba de necesidad, sin maquillaje (banda alta, 18 triajes, 9 con fraude).** El agente bloqueó
12 (7 con fraude: precisión 0,58, recall 0,78) y pidió verificación en 6 (2 con fraude, que se
bloquearon en la segunda compra, cuando el caso subió a crítica). "Bloquear siempre en alta" habría tenido precisión 0,50 y recall
1,00: el mismo F1 (0,67), con 9 clientes honestos bloqueados en vez de 5. **Lo que aporta el LLM,
medido: 14,3 puntos más de fraude detenido que la regla sola (76,1 % contra 61,8 %), a cambio de 4
bloqueos de clientes honestos más en la noche (0,69 por cada 1.000 compras).** Cada bloqueo falso se
levanta con una llamada y el desbloqueo es humano; aun así es un costo real y lo decimos.

**Cuánto creerle a estas cifras.** Es una sola noche con 9 tarjetas robadas: el recall 9/9 tiene un
intervalo de Wilson de [0,70; 1,00] y la precisión 9/14, de [0,39; 0,84]. La noche se eligió por tener
varios episodios de fraude. Sobre toda la partición de prueba, bloquear en la segunda compra marcada
detiene el 73,3 % y bloquear en la primera, el 85,8 % (cotas calculadas fuera de línea por la
auditoría del motor, `auditoria/2026-11-14_m3/motor-medicion.md`).

**Cifras retiradas.** Las del 2026-11-09 (71,4 % de fraude detenido; precisión 1,0 del agente en
banda alta; "9,6 puntos del LLM") salieron de una medición en la que el agente podía ver compras
posteriores a la que abrió el caso (§14, H1 y H2). No se deben citar.

### 13.2 Las cuatro cifras contra la línea base (mismo método: `eval/correr_lote.py`, 19 tareas)

| Cifra | 21-oct (línea base) | 31-oct | **08-nov (final)** |
|---|---|---|---|
| Tasa de éxito | 94,7 % (18/19) | 89,5 % | **84,2 % (16/19)** |
| Costo por tarea (mediana, sin caché) | 0,001481 USD | 0,00186 USD | **0,001749 USD** |
| Latencia (mediana, sin caché) | 5,8 s | 5,5 s | **6,8 s** (P90 12,2 s) |
| Recuperación | 100 % (4/4) | 100 % | **100 % (4/4)** |

Evidencia: `eval/resultados/lote_2026-11-08_2100.json`. El lote corrió con el límite de 10
consultas al agente por minuto apagado: mide al agente, no al limitador.

**Qué empeoró y por qué, sin maquillaje.** La caída total forzada termina en la plantilla por
diseño y cuenta como fallo, igual que en la línea base. Las otras dos tareas sin éxito son
explicaciones del **respaldo Gemini 3.5 Flash-Lite** (con 429 y timeout forzados en Claude) que no
citaron cifras del caso dorado. El respaldo cambió de 3.1 a 3.5 Flash-Lite el 31-oct porque 3.1
daba 503. El flujo principal (Claude) pasó todas sus tareas. Con 19 tareas, una tarea mueve la tasa
5,3 puntos: la diferencia está en el respaldo, no en el diseño. La latencia sube ~1 s, que
coincide con la sesión (una consulta por petición) y el pool del rol del agente. Lo dejamos así
porque son controles de seguridad.

### 13.3 Pendiente honesto

- La suite de casos dorados sigue **sin verificación humana** (`verificado_por` vacío).
- Rotar las llaves de IA usadas en el desarrollo (las rota el equipo en las consolas).
- La prueba con alguien ajeno al equipo (protocolo en `docs/presentaciones/prueba-tercero.md`).

## 14. Auditoría del 2026-11-14 y lo que se corrigió

Cinco agentes revisaron el proyecto en paralelo (pruebas en vivo, seguridad en vivo, motor y
medición, agente y backend, documentos y entrega) y un auditor jefe volvió a comprobar lo más
grave. Veredicto: listo con condiciones. Informes en `auditoria/2026-11-14_m3/`. Lo que se corrigió
el 2026-11-15, cada cosa con su prueba automática:

| Hallazgo | Qué pasaba | Corrección |
|---|---|---|
| H1, crítico | El historial que leía el agente en un caso en vivo llegaba hasta el fin de la ventana de 48 h, y la semilla tiene compras del dataset con fecha posterior: el agente veía el futuro | En un caso en vivo, el historial termina en la última compra que el sistema ya recibió (`repositorio.obtener_historial`) |
| H2, crítico | A 3600x, mientras un triaje esperaba, llegaban compras que en tiempo real no existían | Modo medición: el reloj del dataset se detiene durante cada triaje; nuevas cifras en §13.1 |
| C1, crítico | La validación del aviso solo conocía 15 terminaciones de dominio: pasaban `.shop`, `.lat`, `.es` y "banco . com" | Cualquier "palabra.letras" y las formas con espacios, "punto" o "arroba" se rechazan (`avisos.py`) |
| C2, crítico | "Confirmar bloqueo" de un analista en un caso en vivo no bloqueaba la tarjeta | Ahora bloquea, firmado por el analista, con aviso al titular |
| A1, alto | "No fui yo" del titular no hacía nada | Bloquea la tarjeta, aunque el caso estuviera descartado o desbloqueado |
| A2, alto | Un triaje podía dejar dos bloqueos y tres avisos | Un solo bloqueo activo del agente por caso, revisado en la base |
| A3, alto | Descartar un caso crítico apagaba la red de seguridad sin pedir motivo | Descartar un caso en vivo exige motivo, y no se puede descartar uno con la tarjeta bloqueada (para eso está Desbloquear) |
| A6, alto | En el triaje, la recomendación del M2 ("confirmar con el cliente antes de bloquear") sesgaba al agente | Ya no se le muestra en el triaje; al bloquear, la recomendación del caso pasa a ser el bloqueo |
| Límite por IP | Detrás de Docker todos comparten IP: un abusador frenaba a todos | Cupo por sesión y, además, por IP con 5 veces más margen |
| `run.ps1` | En PowerShell 5.1 un aviso de Docker abortaba el script | Probado en 5.1 el 2026-11-15 |
| Interfaz | El diálogo de desbloqueo mostraba "null" | Corregido |
| Documentos | Este documento y `comandos-demo.md` describían el M2 | Actualizados |

Lo que se dejó como está, con su porqué, está en `docs/seguridad.md` §6 y en
`docs/respuesta_auditoria.md`.
