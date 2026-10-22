# Guía de estudio del código

Para que **cada integrante pueda explicar cualquier parte del código** que el profesor
señale al azar. La rúbrica lo dice sin rodeos: "Lo hizo la IA y no sé qué hace" anula
la sustentación de ese integrante en el Momento 2, y en el Momento 3 la sustentación
vale 20 puntos. Escrita pensando en Jeison, pero sirve para los dos.

Los números de línea son del 2026-10-21; si cambian, busque el nombre de la función.

---

## Cómo estudiar con esta guía

1. **Tres sesiones de ~1,5 h**, en este orden: (1) la idea general y el recorrido de una
   petición, (2) el motor de riesgo, (3) el agente y la app.
2. Por cada archivo: lea primero el **docstring de arriba** (dice *por qué* existe),
   luego las funciones de la ficha, y después **explíquelo en voz alta en 30 segundos**
   sin mirar.
3. Al final, responda la **autoevaluación** (sección 7) sin mirar el código. Lo que no
   sepa responder es lo que va a repasar.
4. Ensaye con el otro integrante: uno abre un archivo al azar y el otro lo explica.

**Reparto sugerido para profundizar** (los dos deben saber lo básico de todo):
Jeison el motor de riesgo, los datos y la medición (como en el pitch: números, mapa de
la IA y alcance); Jhoan el agente y la app.

---

## 1. El proyecto en tres frases

1. Un **modelo de ML clásico** compara cada compra con el pasado de su propia tarjeta y
   le da un score; un **detector determinista** marca los viajes imposibles.
2. Una **regla** agrupa las compras marcadas en casos de 48 h y decide qué recomendar:
   bloquear la tarjeta, bloquear el acceso a la cuenta o verificar con el cliente.
3. Un **agente LLM** consulta la evidencia con herramientas propias y le explica el caso
   al analista; **solo el analista** puede confirmar una decisión.

Dónde va cada cosa:

| Carpeta | Qué hay | Corre |
|---|---|---|
| `src/` | Motor de riesgo (pandas + scikit-learn) | Una vez, fuera de la app |
| `semilla/` | Los casos ya calculados, listos para la base | Se carga al arrancar |
| `app/db/` | Postgres: esquema, carga, consultas | Dentro de Docker |
| `app/proveedores/` | Clientes HTTP de Claude y Gemini, y la cascada | Dentro de Docker |
| `app/agente/` | Bucle, herramientas, prompt, contrato, plantilla | Dentro de Docker |
| `app/api/`, `app/web/` | API con SSE y la pantalla del analista | Dentro de Docker |
| `eval/` | Suite de casos dorados y lote de medición | Desde su computador |

## 2. El recorrido de una explicación (apréndalo de memoria)

Es la pregunta más probable: "¿qué pasa cuando el analista abre un caso?"

1. **Navegador** (`app/web/js/explicacion.js`, `crearExplicacion`) abre un
   `EventSource` a `GET /api/casos/{id}/explicacion/stream`.
2. **API** (`app/api/rutas_agente.py`, `explicacion_en_vivo`) responde con
   `text/event-stream` y manda de inmediato un evento `estado` ("Consultando el
   caso…"), antes de llamar al modelo. `app/api/sse.py` (`transmitir`) convierte cada
   evento del agente en texto SSE y manda un `: ping` cada 15 s.
3. **Servicio** (`app/agente/servicio.py`, `explicar_caso` → `_explicar`): toma un
   candado por caso (para no generar dos veces lo mismo), revisa la **caché**
   (`repositorio.explicacion_vigente`) y, si no hay, crea la tarea y corre el bucle.
4. **Bucle** (`app/agente/bucle.py:167`, `ejecutar`): llama al modelo; si el modelo
   pide herramientas, las ejecuta (`_ejecutar_llamada`) y vuelve a llamar; si responde
   sin pedir herramientas, esa es la respuesta final. Aquí viven los límites.
5. **Cascada** (`app/proveedores/cascada.py:105`, `generar`): intenta con Claude; si da
   429, 5xx o timeout, espera 1, 2 y 4 s y reintenta; si sigue fallando, **conmuta** a
   Gemini.
6. **Contrato** (`app/agente/contrato.py:291`, `validar_explicacion`): revisa la
   respuesta. Si falla, un reintento; si vuelve a fallar, **plantilla**
   (`app/agente/plantilla.py`).
7. **Nivel de riesgo en palabras** (`app/agente/riesgo_en_palabras.py`): lo escribe el
   código, no el modelo.
8. **Persistencia** (`app/db/repositorio.py`): guarda la explicación, la tarea con sus
   métricas y cada paso en `trazas`.
9. **Navegador**: `app/web/js/json_parcial.js` (`parsearJsonParcial`) lee el JSON
   incompleto mientras llega y va llenando los cuatro bloques; al recibir `fin`, cierra
   la conexión.

## 3. Fichas del motor de riesgo (`src/`)

### `cargar_datos.py` (87 líneas)
**Qué hace:** lee los sintéticos o Sparkov y los deja con las columnas del proyecto.
**Funciones:** `cargar_sparkov` traduce `cc_num → id_cuenta`, `amt → monto`, etc., le
quita el prefijo `fraud_` a los comercios (Sparkov se lo pone a todos: sería una pista
falsa) y no lee nombres, direcciones ni fechas de nacimiento. `cargar(fuente)` elige.
**Pregunta probable:** "¿Por qué no leen el nombre del cliente?" → No es una señal de
fraude y no hace falta para explicar un caso: no tocar datos personales innecesarios.

### `perfil_cuenta.py` (151 líneas) — el más importante del motor
**Qué hace:** calcula las *features* de cada compra **solo con las compras anteriores
de su tarjeta**.
**Clave:** `agregar_features` ordena por tarjeta y fecha y usa sumas acumuladas
**menos la fila actual** (`suma_previa = cumsum - monto`, línea 69;
`n_previas = cumcount`, línea 64). Así el promedio de una compra nunca incluye esa
compra ni las futuras.
**Por qué importa:** la primera versión calculaba el perfil con *todas* las
transacciones (filtración de datos: el modelo veía el futuro). La validación lo
detectó y se corrigió.
**Otras funciones:** `_ventana_24h_previa` cuenta compras y dinero de las 24 h
anteriores con un `searchsorted` sobre una llave (tarjeta, segundos); allí hubo un
error de unidades (pandas 3 guarda fechas en microsegundos) que convertía la ventana
en ~1 000 días, y por eso hoy hay una comprobación que falla si no cuadra.
`perfil_al_momento` arma el perfil que ve el agente.
**Pregunta probable:** "¿Qué es filtración de datos y cómo la evitaron?"

### `motor_riesgo.py` (430 líneas)
**Qué hace:** partición temporal, tres modelos, umbrales, casos y recomendación.
**Funciones en orden:**
- `dividir_temporal`: entrenamiento hasta el 20-mar-2020, validación hasta el
  21-jun-2020, prueba después. **Nunca al azar**: en la vida real se predice el futuro.
- `entrenar_modelos`: regresión logística, Random Forest e HistGradientBoosting.
  `elegir_modelo` se queda con el de mejor AUC-PR **en validación** (ganó HistGB).
- `elegir_umbrales`: el de bloqueo maximiza F1 y el de verificación maximiza F2 (pesa
  más el recall), ambos sobre validación; en prueba no se tocan.
- `regla_umbral_fijo`: la idea original ("monto alto o madrugada"), para comparar.
- `contribuciones_por_oclusion`: cuánto baja el score si una señal toma su valor
  típico. Así se sabe qué pesó en *ese* caso.
- `percentil_rareza`: qué tan rara es la señal frente a compras normales.
- `recomendar` (línea 211): la **regla del nivel**. Viaje imposible → bloquear el
  acceso a la cuenta; 2 o más compras sobre el umbral → bloquear la tarjeta; si no →
  verificar.
- `construir_casos`: agrupa por tarjeta en ventanas de 48 h; una compra aislada no
  abre caso (línea 352).
**Pregunta probable:** "¿Por qué AUC-PR y no accuracy?" → Con 0,4 % de fraude, decir
siempre "no es fraude" da 99,6 % de accuracy y es inútil.

### `detectar_viaje_imposible.py` (90 líneas)
**Qué hace:** distancia (Haversine) entre dos compras seguidas de la misma cuenta,
dividida por el tiempo; si supera 900 km/h, alerta.
**Pregunta probable:** "¿Por qué esto no es un modelo?" → Es física exacta: no hay
nada que aprender, y un modelo agregaría error a algo que la fórmula hace perfecto.
"¿Por qué no se usa en Sparkov?" → Allí los comercios están ubicados al azar a ~100 km
del domicilio: da 14 153 falsas alarmas. Solo se mide.

### `entrenar_modelo.py` (223 líneas)
El punto de entrada: `python entrenar_modelo.py --fuente sparkov`. Imprime la tabla de
los tres modelos contra la regla y escribe los casos y las métricas.

## 4. Fichas del agente y la app (`app/`)

### `config.py`
Todo lo configurable sale del entorno: modelos, orden de proveedores (`claude,gemini`,
línea 43), **los límites** (líneas 64-66: 6 iteraciones, 40 000 tokens, 25 s por
llamada), tarifas y fallas forzadas. **Las llaves nunca se escriben aquí.**

### `proveedores/base.py`, `claude.py`, `gemini.py`
**Qué hacen:** cada cliente traduce un formato **neutro** (mensajes y herramientas en
español, definidos en `base.py`) al formato de su API, y de vuelta. Sin SDK: `httpx`
directo.
**Por qué importa:** el bucle no sabe si habla con Claude o con Gemini. Eso es la
"capa de proveedor desacoplada" de la rúbrica.
**Detalles defendibles:** Claude va con el razonamiento apagado
(`cuerpo["thinking"]`), porque gastaba ~1 400 tokens invisibles y subía la espera a
9 s. Gemini 3 exige devolver la "firma" de cada llamada a herramienta (campo `firma`).

### `proveedores/cascada.py`
`generar` (línea 105): por cada proveedor, hasta 4 intentos con esperas 1-2-4 s si el
error es pasajero (`cuota`, `servidor`, `timeout`); si no responde, evento
`conmutacion` y pasa al siguiente. Las **fallas forzadas** se simulan aquí *antes* de
llamar a la red (no gastan cuota). Si todo cae → error `agotados` → el servicio usa la
plantilla.

### `agente/herramientas.py`
Seis herramientas, cada una con descripción escrita como prompt (en `prompts.py`):
`obtener_caso`, `obtener_perfil_cuenta`, `obtener_historial_reciente`,
`obtener_score_y_umbrales`, `registrar_decision` y `declarar_fuera_de_alcance`.
**Todas solo ven el caso abierto** (`_fuera_de_alcance`). `_registrar_decision`
(línea 211) **solo crea una propuesta pendiente**: nunca una decisión.

### `agente/bucle.py` — el que más van a señalar
`ejecutar` (línea 167). **Los cuatro límites:**
1. **Iteraciones**: si ya hizo 6 llamadas al modelo → `limite_iteraciones`.
2. **Tokens**: si ya gastó 40 000 → `limite_tokens`. Se revisa *antes* de cada
   llamada.
3. **Timeout**: cada llamada al modelo tiene 25 s y cada herramienta 5 s; si todos los
   proveedores se agotan por tiempo → `timeout`.
4. **Confirmación humana**: no es un número. Vive en `registrar_decision`, que solo
   propone.

Además: si el modelo intenta responder sin haber consultado `obtener_caso`, no se le
acepta y se le pide consultar primero.

### `agente/contrato.py`
`validar_explicacion` (línea 291) hace 8 comprobaciones numeradas en comentarios:
(0) consultó la evidencia; (1) repara el JSON (quita cercos, cierra llaves);
(2) forma; (3) **la acción es la de la regla**; (4) **solo cita señales relevantes**;
(5) **toda cifra existe en la evidencia** (con formato 1.234,56 y tolerancia de
redondeo); (6) sin jerga interna; (7) no habla de "habitual" si no hay historial.
**Frase para la sustentación:** "El prompt le dice al modelo cómo acertar; el contrato
rechaza la respuesta si no acierta. El prompt solo no basta."

### `agente/plantilla.py` y `agente/riesgo_en_palabras.py`
La plantilla arma la explicación **sin IA**, solo con la evidencia: es el último
escalón cuando todo falla. `nivel_riesgo_en_palabras` usa el score, los umbrales y el
percentil del caso; antes lo escribía el LLM y salía al revés en 3 de 9 casos.

### `agente/servicio.py`
El orquestador: caché → bucle → contrato (con un reintento) → plantilla → guardar.
Nunca deja salir una excepción al usuario: la convierte en un evento `error` en
español.

### `db/repositorio.py` y `db/migrar.py`
**Única puerta a la base**: nadie más escribe SQL. `obtener_caso` **nunca** devuelve
`fraude_confirmado_dataset` y enmascara la tarjeta. `resolver_propuesta` (línea 478)
es donde la confirmación humana se vuelve decisión; resolverla dos veces da error 409.
`migrar.preparar_base` aplica el esquema y carga la semilla si la base está vacía (no
duplica al reiniciar).

### `api/` y `principal.py`
Rutas delgadas: no tienen SQL ni llamadas a modelos. `principal.py` crea la app, carga
la base al arrancar y tiene el manejador global: cualquier error sale como JSON en
español con una referencia, sin traza de Python; si la base cae, responde 503 en ~3 s.

### `web/` (frontend sin compilación)
HTML, CSS y módulos de JavaScript, sin React ni `npm`. `json_parcial.js` lee el JSON a
medio llegar; `explicacion.js` pinta los bloques y enlaza cada cifra a su evidencia;
`decision.js` es el diálogo de confirmación propio (nunca `alert`).

## 5. Preguntas incómodas, con respuesta corta

| Pregunta | Respuesta |
|---|---|
| ¿Por qué necesita un LLM? | Para traducir evidencia estructurada a un relato para el analista. El score, la regla y el viaje imposible **no** llevan LLM, a propósito |
| ¿Por qué no RAG? | Los datos son tabulares; se consultan directo con herramientas. Montar vectores sería IA innecesaria |
| ¿Cómo saben que el LLM no inventa? | El contrato verifica cada cifra contra lo que devolvieron las herramientas; si no cuadra, se rechaza |
| ¿Qué pasa si se cae Claude? | Reintentos 1-2-4 s, conmutación a Gemini y, si todo cae, plantilla. Se demuestra con el panel Demo |
| ¿Dónde exige el sistema la supervisión humana? | `registrar_decision` solo propone (`herramientas.py:211`); la decisión solo se escribe en `resolver_propuesta` (`repositorio.py:478`), que llama la ruta de confirmar |
| ¿Por qué Claude y no Gemini? | Medido el 21 de octubre: Gemini 3.8 Flash daba 503 y 25-40 s; Claude respondía en 1-2 s y su tarifa es menor |
| ¿Por qué el 86 % y no el 100 %? | Un 14 % de los casos de bloqueo son falsas alarmas: por eso la decisión final es humana |
| ¿Por qué sus sintéticos dan 99,9 %? | Son demasiado fáciles; solo prueban la tubería. La evidencia del modelo es Sparkov |
| ¿Qué fue lo más difícil? | La filtración del perfil y el error de unidades de fecha: los dos los encontró la validación independiente y se corrigieron con la evidencia a la vista |
| ¿Qué harían distinto? | Escribir la spec y la partición temporal desde el día uno, y medir con datos reales antes de presentar cifras |
| ¿Usaron IA para programar? | Sí, con Claude Code y una cadena de skills-rol (requisitos → diseño → construcción → validación). Las decisiones las tomó el equipo y cada pieza se validó volviendo a correr la evidencia |

## 6. Datos que conviene saber de memoria

- Sparkov: 1 852 394 transacciones, 999 tarjetas, 0,4–0,6 % de fraude; prueba de
  junio a diciembre de 2020.
- Modelo HistGB en prueba: precisión 0,786, recall 0,838, F1 0,811, AUC-PR 0,884.
  Regla: F1 0,028, AUC-PR 0,012.
- Casos: 339 (287 Sparkov + 52 sintéticos); 249 de bloquear tarjeta con 86,3 % de fraude.
- Agente: éxito 94,7 %, 0,0015 USD por tarea, mediana 5,8 s, caché 26 ms,
  recuperación 100 %; suite 8 de 8.
- Límites: 6 iteraciones, 40 000 tokens, 25 s por llamada, 5 s por herramienta,
  confirmación humana.

## 7. Autoevaluación (responda sin mirar)

1. ¿Por qué la partición es por fecha y no al azar?
2. Muestre la línea que evita que el promedio de una compra se incluya a sí misma.
3. ¿Qué es la ventana de 48 h y por qué 48 y no 24?
4. ¿Qué decide la regla y qué decide el modelo?
5. ¿Por qué una compra aislada no abre caso?
6. ¿Qué diferencia hay entre la contribución por oclusión y el percentil de rareza?
7. Nombre los cuatro límites y dónde vive cada uno.
8. ¿Qué pasa, paso a paso, si Claude responde 429?
9. ¿Qué comprueba el contrato y qué hace si falla dos veces?
10. ¿Qué ve el analista si no hay llaves de IA?
11. ¿Dónde se convierte una propuesta en decisión, y qué pasa si se confirma dos veces?
12. ¿Por qué la explicación llega por SSE y no en una sola respuesta?
13. ¿Qué datos salen hacia Claude o Gemini, y cuáles nunca salen?
14. ¿Qué mide la tasa de éxito y por qué la plantilla no cuenta como éxito?
15. Si el profesor señala `parsearJsonParcial`, ¿qué dice?

Si alguna no le sale, vuelva a la ficha correspondiente y anote la duda en
`docs/verificacion-jeison.md` (sección "Dudas sobre el código") para resolverla juntos.
