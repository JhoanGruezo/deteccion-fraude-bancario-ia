# Registro de decisiones — Detección de fraude bancario (Momento 2)

**Equipo:** Jhoan David Gruezo Gutiérrez y Jeison Nazarit
**Estado:** borrador consolidado del 2026-10-21. Las secciones marcadas con
"PENDIENTE (equipo):" solo las puede llenar el equipo. La bitácora histórica, con
todas las decisiones en el orden en que se tomaron, está en `../decisiones.md`; este
documento es la versión que se entrega.

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
| Bloqueo final | Humano | Afecta a un cliente real e irreversible; el agente solo propone |

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

**Herramientas**: las seis de la sección 3. Todas validan que el `id_caso` sea el del
caso abierto. En modo explicación el agente solo tiene las cuatro de lectura; en modo
pregunta tiene además `registrar_decision`, que solo crea una propuesta pendiente, y
`declarar_fuera_de_alcance`, que fija el rechazo de forma determinista.

**Los cuatro límites**, con sus valores y por qué:

| Límite | Valor | Por qué ese número |
|---|---|---|
| Iteraciones | 6 llamadas al modelo por tarea | Explicar un caso pide 3 o 4 herramientas: 2 o 3 iteraciones con llamadas en paralelo y 1 final. En el lote la mediana fue 2. Seis dan margen para un reintento del contrato sin permitir un bucle ciego |
| Presupuesto de tokens | 40 000 de entrada + salida por tarea | Cada iteración reenvía la conversación; una explicación con reintento de contrato consumió unos 28 000 tokens de entrada el 2026-10-21. La mediana del lote fue 11 059 tokens por tarea (las 13 no servidas desde caché) |
| Timeout | 25 s por llamada al modelo y 5 s por herramienta | 25 s está muy por encima de lo que tarda Claude (1-2 s) y corta a un proveedor saturado (Gemini 3.8 Flash tardaba 25-40 s); las herramientas son consultas por llave que tardan milisegundos |
| Confirmación humana | Toda escritura es una propuesta | `registrar_decision` escribe en `propuestas_decision`, nunca en `decisiones`; la decisión la crea la API solo cuando el analista confirma con su nombre |

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
La versión vigente es `2026-10-21.4`:

| Versión | Qué cambió | Por qué |
|---|---|---|
| 2026-10-21.1 | Primera versión, con los puntos obligatorios de `diseno/agente.md` (rol, evidencia solo por herramientas, acción de la regla, datos no son instrucciones, rechazo con marca) | Diseño inicial |
| 2026-10-21.2 | Límites de extensión por campo (que_paso hasta 90 palabras, etc.) y, en casos largos, nombrar solo la primera y la última compra con el total | Las explicaciones de casos con muchas compras se cortaban en `max_tokens` y el JSON llegaba incompleto |
| 2026-10-21.3 | Los nombres internos de las señales solo van en `senales_citadas`; en el texto se describen en palabras | El texto para el analista mostraba "monto_24h" en vez de "el gasto de las últimas 24 horas" |

| 2026-10-21.4 | El nivel de riesgo en palabras ya no lo redacta el modelo (lo arma `riesgo_en_palabras.py`); herramienta `declarar_fuera_de_alcance` para rechazar en lugar de la marca de texto; `obtener_caso` entrega primero `senales_que_puedes_citar`; no escribir texto antes de llamar herramientas; no hablar de "habitual" en tarjetas sin historial | Hallazgos de `validacion/app-analista.md` y de la primera medición (sección 9): nivel de riesgo al revés en 3 de 9 casos, marca de rechazo frágil en los dos sentidos, contratos inválidos en casos largos, preámbulos que falseaban el TTFT |

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
