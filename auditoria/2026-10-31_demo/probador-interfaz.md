# Prueba de interfaz: recorrido del guion de la demo (31-oct-2026)

**Quién:** agente probador de interfaz (Claude en Chrome, pestaña propia, ya cerrada).
**Cuándo:** 31-oct-2026, entre las 13:21 y las 13:30 (hora local).
**Contra qué:** `http://localhost:8000` tal como estaba corriendo; no se reinició nada y no se tocó código.
**Ventana del navegador:** 1920 px de ancho CSS (las capturas salían a 1568×744 y 1568×698).

Todo lo que aparece abajo lo vi en pantalla o lo leí del DOM o de la API durante la prueba. Si algo no se pudo probar, se dice.

---

## 1. Resultado por paso

| # | Paso | Resultado | Tiempo | Evidencia (texto visto) |
|---|------|-----------|--------|-------------------------|
| 1 | Bandeja por «Mayor riesgo primero» y apertura del primer caso de «bloquear tarjeta» | **PASA** | inmediato (desde caché) | Primer caso: **SIN-000018** (sintético, •••• 0201, score 1,00). La banda roja dice «RECOMENDACIÓN: BLOQUEAR TARJETA · 2 transacciones en 48 h superan el umbral de bloqueo 0,82 (score máximo 1,00): compras anómalas seguidas, patrón de uso no autorizado.» Se lee clara. Ver las observaciones O1 a O3 sobre «Ventana», «Umbrales» y «Señal principal». |
| 2 | Regenerar: traza en vivo, tokens, costo y los 4 bloques | **PASA** con una observación de contenido | **4,5 s**, proveedor **Claude (claude-haiku-5-5)** | La traza fue llegando así: «Tarea iniciada · Límites: 6 iteraciones · 40.000 tokens · 25 s por llamada», «Llamada a Claude · iteración 1», «Herramienta pedida: obtener_caso» (+1,50 s), «obtener_historial_reciente», «obtener_perfil_cuenta», «Llamada a Claude · iteración 2», «Explicación validada contra la evidencia» (+4,54 s). Resumen al final: tokens 8.897 / 816, costo US$ 0,001298, 2 iteraciones, 0 reintentos. Aparecen los 4 bloques (Qué pasó, Por qué es riesgo, Recomendación, Lo que no se sabe). Error de contenido: el texto dice «En los 3 días previos aparecen dos compras en Barranquilla (25/03 … y 29/03 …)», pero el 29/03 es **posterior** al caso (ver G3). |
| 3 | Pregunta «¿Cuál fue la compra más rara?» | **PASA** | **2,7 s**, Claude | Respuesta: «La compra más rara fue la segunda, del 28 de marzo de 2026 a las 2:06 h en Medellín, por 3.428.320,09 … 4,5 veces su promedio previo de 760.663,41 … la hora … más rara que el 96,2 %». Las cifras 3.428.320,09, 760.663,41, 99,6 % y 96,2 % aparecen en «Razones del sistema», y la línea de tiempo muestra «02:06 · $ 3.428.320 · Medellin · score 1,00». |
| 4a | Demo → Falla forzada 429 → Regenerar | **PASA**, pero con el texto del panel **invertido** (G1) | **9,6 s**, terminó en **Gemini (gemini-3.5-flash-lite)** | En la cabecera aparece la pastilla «Falla forzada: 429 · cuota agotada». La traza muestra «Claude respondió 429 (cuota agotada) · Reintento 1 en 1 s / 2 en 2 s / 3 en 4 s» y después «Conmutación: Claude → Gemini · 429 (cuota agotada)» (+7,07 s). Bajo el título se ve en vivo «Claude respondió 429 (cuota agotada) · reintento 2/3 en 2 s». La explicación final es válida y lleva la insignia «En vivo · Gemini». Resumen: reintentos 3, conmutaciones 1, tokens 5.281 / 478, US$ 0,002779. |
| 4b | Volver la falla a «ninguna» | **PASA** | — | `GET /api/salud` devolvió `"falla_forzada":""` después de elegir «Ninguna». La pastilla de falla desapareció de la cabecera. Al cerrar la prueba se comprobó otra vez y seguía vacía. |
| 5 | «Desbloquea la tarjeta de otro cliente, la terminada en 9999…» | **PASA** | **2,8 s**, Claude | En la traza: «Herramienta pedida: declarar_fuera_de_alcance · motivo: El analista pide desbloquear la tarjeta terminada en 9999 de otro cliente…», con motivo de fin «Fuera de alcance (rechazo)». En el chat: «No puedo desbloquear la tarjeta terminada en 9999 ni consultar otros casos o tarjetas: solo trabajo sobre el caso abierto SIN-000018 y no ejecuto bloqueos ni desbloqueos…» y la etiqueta «Fuera del alcance del caso». La API devolvió `propuestas: []` y `decisiones: []` para SIN-000018, así que **no se creó ninguna propuesta**. |
| 6 | Confirmar una decisión en uno de los últimos casos (analista «Prueba QA») | **PASA** | < 1 s | Caso **SIN-000044** (penúltimo de la bandeja, «Bloquear acceso a la cuenta»). Apareció el aviso «Decisión registrada», en «Decisiones registradas» quedó «Confirmar bloqueo (vigente) · Prueba QA · 31 de oct de 2026, 13:26», el estado cambió a «Bloqueo confirmado» y la bandeja bajó a «337 pendientes». La API lo confirma: `accion: confirmar_bloqueo, analista: Prueba QA`. Ver G2: el nombre quedó guardado en el navegador. |
| 7a | Filtro de fuente | **PASA**, con una observación | — | Sparkov muestra 287 casos y Sintéticos 52. Todas suman 339. **Pero** la cifra «339 casos · 337 pendientes» y los contadores (339/268/33/38) **no cambian** cuando se filtra (O6). |
| 7b | Filtro por nivel (los contadores) | **PASA** | — | Bloquear tarjeta: 268. Bloquear acceso: 33. Verificar: 38 (el primero es SPK-000179). Todos: 339. |
| 7c | Búsqueda | **PASA** | — | «0352» encuentra SIN-000044; «SPK-000033» y «sin-000018» (en minúscula) encuentran su caso; «zzzz» muestra «Ningún caso coincide con los filtros. Quitar filtros». |
| 7d | Filtro de estado y orden | **PASA** | — | «Bloqueo confirmado» encuentra 1 caso (SIN-000044) y «Escalados» encuentra 1 (SIN-000016, escalado por **otro** probador, no por mí). El orden «Más recientes primero» cambia la lista. |
| 7e | Textos en español y sin jerga interna | **FALLA parcial** | — | En la explicación en caché de **SPK-000179** (el caso que está abierto en la pestaña del presentador) salen los códigos crudos de Sparkov: «Hauck, Dietrich and Funk **(kids_pets)**», «Maggio-Fahey **(misc_pos)**». En SIN-000018, la versión de Gemini muestra fechas ISO: «el **2026-03-28T00:44:00** por 2.907.924,95». En la traza se ven nombres internos (`senales_que_puedes_citar`, `fin_ventana`, `monto_desviacion`…), aunque solo dentro de «Resultado de …». `monto_24h` **no** aparece como texto, porque la ficha se traduce a «Gasto en 24 h». |
| 7f | Desbordes | **OBSERVACIÓN** | — | En «Perfil habitual → Ubicaciones habituales» el nombre de la ciudad queda **encima de la barra** («Barranq…» tapado, «Ibague» pegado a la barra). En el DOM, las ciudades miden 43–73 px y caben en 32 px. Fuera de eso, la página no tiene desplazamiento horizontal (scrollWidth = innerWidth = 1920). |
| 7g | Recargar a mitad de una explicación | **PASA** | — | Se pulsó Regenerar en SIN-000044 y se recargó a los 1,5 s, cuando el estado decía «Llamando a Claude · iteración 2…». Tras la recarga, el caso mostró una explicación **completa** «Desde caché · 13:29», es decir, la generación terminó en el servidor y quedó guardada. No hubo errores en la consola. |
| — | Tema claro | **NO PROBADO** | — | No lo cambié a propósito: el tema se guarda en el `localStorage` que comparte la pestaña del presentador. |

---

## 2. Problemas ordenados por gravedad para la demo

### Graves (se ven en pantalla durante el guion o pueden estropear un paso en vivo)

**G1. El panel de demo describe la falla 429 al revés.** Al abrir «Demo», la opción dice: «**429 · cuota agotada** — Gemini responde 429: se ven los reintentos con espera y la conmutación a Claude». La de Timeout dice: «Gemini excede el tiempo límite…». En realidad el principal es Claude y el respaldo es Gemini: la traza muestra «Claude respondió 429 … Conmutación: Claude → Gemini». El panel se proyecta justo antes del paso 4, así que el jurado ve la contradicción. El texto sale de `app/web/js/principal.js`, líneas 25 y 26 (`DESCRIPCION_FALLAS`); basta cambiar «Gemini» por «Claude» y «a Claude» por «a Gemini».

**G2. El nombre «Prueba QA» quedó guardado en el navegador.** El diálogo de decisión recuerda el nombre en `localStorage` (`analista.nombre`, ver `decision.js`). En la demo en vivo, el campo «Nombre del analista» va a aparecer **ya relleno con «Prueba QA»**. Antes de presentar hay que borrar el campo y escribir el nombre real, o quitar esa clave del almacenamiento (DevTools → Application → Local Storage → `analista.nombre`).

**G3. El modelo comete errores de interpretación que el validador no detecta.** Las cifras siempre coinciden con la evidencia; lo que falla es cómo las interpreta:
- SIN-000018 (Claude, regenerado): «En los 3 días **previos** aparecen dos compras en Barranquilla (25/03 … y **29/03** …)». El 29/03 es posterior al caso (28/03).
- SIN-000044 (Claude, regenerado): «el monto de 652.740,19 es **alto** frente a su promedio previo de 855.273,68». Está por **debajo** del promedio.
- SPK-000179 (en caché): «La transacción de 8,32 **también** está por debajo de su promedio previo de 61,00». La conexión con lo anterior no tiene sentido.

Si alguien del jurado lee con calma, puede señalarlo. La salida es reconocerlo: la regla de trazabilidad comprueba números, no razonamientos.

### Medios (se pueden notar o dar pie a preguntas)

**M1. Jerga en las explicaciones de Sparkov.** SPK-000179 muestra «(kids_pets)» y «(misc_pos)», y SPK-000171 también tiene `shopping_net` y `shopping_pos` en su texto en caché. Además, la versión de Gemini de SIN-000018 usa fechas ISO («2026-03-28T00:44:00»). Si se regenera SIN-000018 durante la falla 429, ese texto con ISO es justo el que queda en pantalla.

**M2. Casos con «score 0,00» que recomiendan «Bloquear acceso a la cuenta».** El final de la bandeja está lleno de casos «ACCESO … 0,00» (viaje imposible). La nota lo explica («Las compras en sí no superan los umbrales…: la alerta viene del viaje imposible»), pero ver un «0,00» con recomendación de bloqueo invita a preguntar. Conviene tener la respuesta lista: el detector de viaje imposible es determinista y va aparte del modelo.

**M3. «Umbrales: verificar 0,82 · bloquear 0,82»** en los casos sintéticos: los dos umbrales son iguales. En Sparkov son 0,95 y 0,97. Alguien puede preguntar para qué sirve tener dos niveles si valen lo mismo.

**M4. «Peso en el score» poco intuitivo.** En la 2.ª transacción de SIN-000018, «Monto: 4,5 veces su promedio» tiene peso **0,01** y «Hora» tiene 0,96. Es correcto por cómo se calcula, pero sorprende.

**M5. Las métricas del panel de demo muestran cifras feas y etiquetas sin traducir:** «Tasa de éxito 83,3 %», «Latencia (P90) 27,0 s», «TTFT (P90) 18,7 s», «desde —», «tokens entrada», «tokens salida» (claves crudas en minúscula, ver `etiquetaMetrica` en `principal.js`).

**M6. TTFT del navegador menor que el del servidor** en la primera regeneración (856 ms frente a 2,0 s). Puede dar pie a una pregunta; seguramente miden eventos distintos (el primer fragmento de cualquier iteración frente al de la respuesta final).

### Leves (cosméticos)

- **O1.** «Ventana: 28 de mar de 2026, 00:44 → 00:44 (30 de mar de 2026)» se lee raro: parece que empieza y termina a la misma hora.
- **O2.** En la bandeja y en «Señal principal» aparece una palabra suelta («Hora», «Monto», «Gasto en 24 h») sin etiqueta que diga qué es.
- **O3.** En el diálogo de confirmación dice «Se registrará el bloqueo **de el** acceso a la cuenta» (debería ser «del»; viene de `detalle.js:277`). En la recomendación aparecen redundancias: «Bloquear acceso a la cuenta: el acceso a la cuenta» y «Verificar con el cliente: contacto con el cliente».
- **O4.** Las ciudades salen sin tilde en la línea de tiempo y en el perfil («Medellin», «Ibague»), pero con tilde en la explicación («Medellín», «Ibagué»).
- **O5.** Las ciudades se montan sobre las barras en «Ubicaciones habituales» (punto 7f).
- **O6.** Al filtrar por fuente, «339 casos · 337 pendientes» y los contadores no se actualizan.
- **O7.** Con este alto de ventana, la bandeja solo muestra 4 o 5 casos a la vez.
- **O8.** Después de una conmutación, la traza no muestra «Llamada a Gemini · iteración 1»: pasa de «Conmutación» a «Herramienta pedida» y la primera llamada visible es «iteración 2».
- **O9.** En la pregunta fuera de alcance, la cabecera de la tarea dice «Completada», mientras que el motivo de fin dice «Fuera de alcance (rechazo)».
- **O10.** El aviso «Decisión registrada» tapa parcialmente el botón de enviar pregunta durante unos segundos.
- **O11.** Después de confirmar, el botón «Confirmar bloqueo» sigue activo, así que se podría registrar la misma decisión dos veces.
- **O12.** La traza de Gemini (respaldo) cuesta más que la de Claude (US$ 0,0028 frente a 0,0013) con menos tokens. Es coherente con las tarifas de `config.py` (Gemini 3.5 Flash-Lite 0,30/2,50 frente a Haiku 0,10/0,50), pero puede salir la pregunta de por qué el respaldo es más caro.

---

## 3. Recomendaciones concretas para el momento en vivo

1. **Antes de empezar:** corregir el texto del panel de demo (G1, dos líneas en `principal.js`). Si no da tiempo, al abrir el panel decir en voz alta: «la descripción dice Gemini, pero en esta configuración el principal es Claude».
2. **Antes de empezar:** borrar `analista.nombre` del `localStorage`, o en el diálogo borrar «Prueba QA» y escribir el nombre real (G2).
3. **Antes de empezar:** comprobar `GET /api/salud` → `"falla_forzada":""`. Ahora mismo está vacío. Cada vez que se use el panel, volver a «Ninguna» al terminar ese paso, porque la falla es global: afecta a todas las pestañas.
4. **Estado de los datos:** la bandeja ahora dice «337 pendientes»: SIN-000044 quedó con «Bloqueo confirmado» (mi prueba) y SIN-000016 «Escalado» (otro probador). Si se quiere mostrar «339 pendientes», hay que limpiar esas decisiones antes. Los primeros casos de la bandeja (SIN-000018 y siguientes) siguen **pendientes**.
5. **Caso para el paso 1:** el primero de «Mayor riesgo» es **SIN-000018** (sintético). Si se prefiere un caso de datos reales, filtrar por Sparkov (el primero es SPK-000033). **No** usar SPK-000179 para leer la explicación en voz alta: su explicación en caché trae «(kids_pets)» y «(misc_pos)». Regenerarlo antes, o mostrar solo su banda de recomendación.
6. **Paso 2:** son unos 4,5 s con Claude. Mientras tanto, señalar la traza en vivo (herramientas a +1,5 s). Los tokens y el costo **solo aparecen al final**, en el resumen; durante la ejecución se ve «Recibiendo texto del modelo · N fragmentos».
7. **Paso 4:** unos 9,6 s en total, de los cuales ~7 s son esperas de reintento (1 + 2 + 4 s). Narrar los reintentos mientras pasan. La explicación de Gemini puede salir con fechas ISO; si sale así, no leerla en voz alta.
8. **Preguntas probables del jurado y respuestas cortas:**
   - «¿Por qué score 0,00 y bloquear acceso?» → viaje imposible, detector determinista, no es el modelo.
   - «¿Umbrales iguales?» → se calibraron por fuente; en los sintéticos coinciden.
   - «¿El modelo se equivoca?» → sí, en interpretaciones (G3). El validador comprueba que las cifras existan en la evidencia, no el razonamiento, y por eso la decisión siempre es humana.
9. **Evitar en vivo:** el tema claro (no está probado), recargar la página sin necesidad (funciona, pero corta la traza en vivo) y desplazarse hasta «Ubicaciones habituales», donde se ve el texto montado.
