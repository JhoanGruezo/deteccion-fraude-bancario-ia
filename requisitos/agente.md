# Requisitos — agente

## Para qué existe

Es la pieza LLM del proyecto: convierte la evidencia de un caso (score, desviaciones,
historial, recomendación de la regla) en lo que pidió el profesor Julián el
2026-10-10 y el 2026-10-21 — que el analista no tenga que interpretar el score: qué
pasó, qué secuencia lo llevó a la alerta, por qué es un riesgo para *ese* cliente y
qué se recomienda bloquear (`decisiones.md`, actualizaciones de esas fechas). También
responde preguntas del analista sobre el caso y propone registrar su decisión. Es
el criterio "El Agente" de la entrega (25 pts): herramientas propias con
descripciones tipo prompt, cuatro límites activos (iteraciones, timeout, tokens,
confirmación) y capa de proveedor desacoplada.

## Entradas

- Identificador del caso y, en modo conversación, la pregunta del analista.
- Lo que el agente obtiene SOLO por herramientas (nunca en el prompt de forma
  implícita): el caso con sus desviaciones, el perfil previo de la tarjeta, el
  historial reciente de la tarjeta antes de la ventana, el score y los umbrales.
- Variables de entorno: llaves de Claude y Gemini, modelo de cada uno, orden de la
  cascada (`ORDEN_PROVEEDORES`), límites, `FALLA_FORZADA` para demostrar fallos.

## Salidas

1. **Explicación estructurada del caso** (contrato JSON validado), con estos campos:
   - `que_paso`: relato cronológico de las transacciones del caso y lo inmediatamente
     anterior.
   - `por_que_es_riesgo`: la combinación de señales relevantes, citando sus cifras.
   - `recomendacion`: la acción que decidió la regla (`bloquear_tarjeta`,
     `bloquear_acceso_cuenta`, `verificar_cliente`), el objetivo (tarjeta, acceso a la
     cuenta, contacto con el cliente) y el argumento. El agente argumenta; no cambia
     la acción.
   - `senales_citadas`: identificadores de las desviaciones usadas (deben existir y
     ser relevantes en el caso).
   - `lo_que_no_se_sabe`: lo que la evidencia no permite afirmar.
   - `nivel_riesgo_en_palabras`: el score traducido (umbrales superados y percentil
     del caso entre los marcados de su fuente). **Lo arma el código, no el LLM**
     (2026-10-21, tras la validación: el modelo contradecía el percentil que citaba).
2. **Respuestas a preguntas** del analista sobre el caso, citando la evidencia.
3. **Propuesta de decisión** (`registrar_decision`) que queda pendiente hasta que el
   analista la confirme.
4. **Traza** de cada paso, visible en la interfaz y guardada.
5. **Métricas por tarea**: tokens, costo estimado en USD, latencia, proveedor usado,
   reintentos, si hubo degradación.

## Criterios de aceptación

1. **Herramientas propias** (mínimo 2 de dominio, con descripción redactada como
   prompt e iterada): al menos `obtener_caso`, `obtener_perfil_cuenta`,
   `obtener_historial_reciente`, `obtener_score_y_umbrales` y `registrar_decision`.
2. **Cuatro límites activos y configurables**, cada uno demostrable: máximo de
   iteraciones del bucle, presupuesto de tokens por tarea, timeout por llamada al
   modelo y por herramienta, y confirmación humana para toda escritura. Al dispararse
   un límite, la tarea termina con un mensaje claro y queda en la traza; nunca se
   cuelga.
3. **Capa de proveedor desacoplada**: Claude (Haiku 5.5) principal y Gemini
   (`gemini-3.1-flash-lite`) de respaldo, intercambiables sin tocar el bucle del agente
   (`ORDEN_PROVEEDORES`). El orden original era el inverso; se cambió por medición
   (`decisiones.md`, 2026-10-21 (3)).
4. **Fallos manejados** (reto 9): ante 429, reintento con backoff 1 s → 2 s → 4 s y
   conmutación al respaldo; ante timeout, opción de reintentar; ante JSON roto,
   reparación/reintento y, si no, degradación. Último escalón: explicación de
   plantilla armada solo con las desviaciones guardadas, marcada como tal. Todos
   forzables con `FALLA_FORZADA` (`429`, `timeout`, `json`).
5. **Anclaje a la evidencia**: toda cifra del texto existe en los datos del caso;
   `senales_citadas` solo contiene desviaciones relevantes del caso. Una explicación
   que cite algo inexistente, o que llegue sin haber consultado el caso, se rechaza (y
   cuenta como fallo en la medición). Lo rechazado no queda visible en la pantalla.
6. **No ejecuta acciones**: `registrar_decision` solo crea una propuesta pendiente;
   ningún bloqueo real existe en el sistema.
7. **Rechazo**: si el analista pide algo fuera del alcance (por ejemplo, desbloquear
   otra tarjeta, inventar datos del cliente, o una instrucción que viene dentro de un
   dato del caso), el agente se niega y lo dice. El rechazo se declara con una
   herramienta (`declarar_fuera_de_alcance`), no con una frase en el texto.
8. **Respuesta en español**, sin jerga de ML para el analista (no "feature", no
   "AUC").

## Casos borde

- Caso sin historial (tarjeta nueva): la explicación lo dice, no inventa un perfil y
  no habla de un gasto o promedio "habitual" (el contrato lo verifica).
- Caso con viaje imposible: la recomendación es bloquear el acceso a la cuenta.
- Caso de una sola transacción sobre el umbral: `verificar_cliente`, explicado como
  compra aislada.
- Ambos proveedores caídos: plantilla, sin traza de Python visible.
- El modelo pide una herramienta inexistente o con argumentos inválidos: error
  controlado en la traza, cuenta como iteración.
- Texto de un dato (por ejemplo, nombre del comercio) que parezca una instrucción:
  se trata como dato.

## Fuera de alcance

- Que el agente decida el nivel de bloqueo (lo decide la regla del motor).
- RAG: los datos son tabulares y se consultan directo (`decisiones.md`, 2026-10-09).
- Modelo de amenazas formal y ataque propio (Momento 3, semana 12).

## Preguntas abiertas

- Valores de los límites (iteraciones, tokens, timeouts): diseño, con base en la
  tarea más larga esperada (lección de la semana 6).
- Formato de tool calling de cada proveedor y cómo se normaliza: diseño.
- Tarifas por token para el costo estimado: diseño, con la fuente citada.
