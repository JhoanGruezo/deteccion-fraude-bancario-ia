# Auditoría de datos, motor de riesgo y medición del Momento 3 (2026-11-14)

Alcance: filtraciones, cifras del M3 y del análisis de ritmo, métricas del motor, paridad en vivo, viaje
imposible. Todo se recalculó desde los CSV de Sparkov, la semilla y los JSON de `eval/resultados/`, nunca
desde los `.md`. No se tocó la base en vivo ni el código del proyecto. Scripts y salidas en
`auditoria/2026-11-14_m3/logs/motor-*` (cada `.py` tiene su `.txt` al lado). El caché de scores fuera de línea
(1,85 M filas puntuadas con `semilla/modelo_riesgo_sparkov.joblib`) quedó en el scratchpad de la sesión, no en
el repo; se regenera con `motor-puntuar.py` en unos 80 s.

## Tabla de cifras

| Cifra | Declarada | Recalculada | ¿Coincide? | Fuente del recálculo |
|---|---|---|---|---|
| Motor HistGB en prueba (P / R / F1 / AUC-PR) | 0,786 / 0,838 / 0,811 / 0,884 | 0,7864 / 0,8378 / 0,8113 / 0,8841. IC 95 % por bootstrap de tarjetas: AUC-PR [0,867; 0,901], F1 [0,792; 0,829] | Sí | `motor-puntuar.txt` |
| Regla de umbral fijo (P / R / F1 / AUC-PR) | 0,014 / 0,845 / 0,028 / 0,012 | Idéntica, pero marca el 23,3 % de todas las compras. Una regla de dos umbrales ajustada en validación (monto > 277,54 y hora 22–04) llega a 0,326 / 0,604 / **0,424** / 0,199 | Sí la cifra; la comparación es débil (H4) | `motor-puntuar.txt` |
| Partición temporal y umbrales | Entrenamiento hasta el 20-mar-2020, validación hasta el 21-jun, prueba después; umbrales elegidos en validación | Confirmado. UV 0,9477 (F2) y UB 0,9664 (F1) salen de la validación; el modelo de `semilla/` es el mismo archivo que el de `datos/salidas_sparkov/` (md5 aa8c2fb9…) | Sí | `motor-puntuar.txt`, `src/entrenar_modelo.py:104-106` |
| La noche del 19-jul-2020 está en prueba | Sí | Sí (la prueba empieza el 21-jun-2020 12:14). Ojo: la ventana se eligió por tener muchos episodios de fraude, es decir, mirando la etiqueta (H3) | Sí | `motor-puntuar.txt`, `scripts/generar_semilla_simulador.py:11-14` |
| Ventana: compras / fraudes / USD / tarjetas con fraude | 5.810 / 54 / 28.367 / 9 | 5.810 / 54 / 28.367,23 / 9. De los 9 episodios, solo 5 empiezan dentro de la ventana; 4 venían de antes | Sí | `motor-noche.txt` [1], [2] |
| Paridad en vivo contra el motor por lotes | 111.342 compras, 0 cambios de banda | No hay un log guardado de esa corrida. Recálculo propio en la noche medida: 5.810 compras, diferencia máxima 5·10⁻⁷, **0 cambios de banda** | Sí en la noche; las 111.342 no se pueden comprobar | `motor-paridad_noche.txt` |
| Fraude detenido, M3 | 71,4 % | La aritmética cuadra: 1 − 8.114,82 / 28.367,23 = 71,4 %. Queda entre una cota inferior de 61,8 % (bloquear en la 2.ª marca) y una superior de 79,6 % (en la 1.ª). Está **inflada por una fuga de información futura** (H1, H2) | La aritmética sí; la validez no | JSON base; `motor-noche.txt` [3] |
| M2: analista al instante / cola de 90 min / de noche sin turno | 61,8 / 34,9 / 29,3 % | 61,8 / 34,9 / 29,3 % con scores fuera de línea | Sí | `motor-noche.txt` [3] |
| Fraude detenido con la IA caída | 61,8 % | 61,8 %, que es exactamente la regla de la 2.ª marca. IC 95 % por tarjeta (n = 9): [42,0; 72,4]. En toda la población de prueba, la misma regla detiene **73,3 %** [71,1; 75,3] | Sí | `motor-ic_noche.txt`, `motor-noche.txt` [5] |
| Compra sospechosa → bloqueo | Mediana 5,7 s, máximo 8,2 s | 5,734 / 8,245 s en el JSON (`segundos_reales…`), contados desde la compra que disparó la **banda final**. Desde la apertura del caso (`segundos_hasta_bloqueo`): mediana 6,6 s, p95 28,1 s, máximo 32,2 s. n = 10 | Sí, con otra definición (H7) | JSON base |
| Bloqueos por tarjeta: precisión / recall | 0,90 / 1,00 | 9/10 y 9/9. Wilson: [0,60; 0,98] y [0,70; 1,00]. En la población, la banda crítica da 0,898 / 0,972 por tarjeta | Sí | `motor-viaje.txt`, `motor-noche.txt` [5] |
| Bloqueos falsos por cada 1.000 compras | 0,17 | 1/5.810 = 0,17; IC Poisson [0,004; 0,96]. En la población, la banda crítica da 0,043 | Sí | ídem |
| Agente en banda alta: precisión de sus bloqueos | 1,0 (3/3) | Wilson [0,44; 1,00]; recall 3/5. La diferencia de 2.729,56 USD con la IA caída solo cuadra al centavo con las tarjetas …7879, …2579 y …7331, y las tres tenían compras futuras a la vista (H1) | La aritmética sí; la validez no | `motor-ic_noche.txt` |
| "Bloquear siempre en alta": precisión | 0,385 (5/13 triajes) | 5/13, Wilson [0,18; 0,65]. En la población, 0,476 por tarjeta | Sí | ídem |
| Costo del LLM | 0,054 USD; 0,0023 por triaje; 0,009 por cada 1.000 compras | 0,0538 / 23 = 0,00234; 0,0093 | Sí | JSON base |
| Episodios de fraude que empiezan entre 22:00 y 06:00 | 88 % | 88,2 % de los episodios. Por compras es 86,1 % y por monto 85,3 %. La frase "el 88 % del fraude es nocturno" (`analisis…:137`) estira la cifra | Sí | `motor-ritmo.txt` |
| Pérdida al bloquear a los 0 / 5 / 60 min / 8 h / 24 h | 7,5 / 7,8 / 11,6 / 21,2 / 58,2 % | 7,5 / 7,8 / 11,6 / 21,2 / 58,2 %; a los 90 min, 13,4 % | Sí | `motor-ritmo.txt` |
| Regla del M2: entre la 1.ª y la 2.ª marca | Mediana 100 min; 148.267 USD (13,0 % del monto marcado) | 100,4 min y 148.267 USD, pero **146.311 USD son la propia 2.ª compra marcada**; sin ella queda 0,2 %. Sobre la base correcta (todo el fraude de la tarjeta, marcado o no) la espera cuesta 12,5 puntos del monto fraudulento en prueba (85,8 % contra 73,3 %) | El número sí; el método no (H5) | `motor-ritmo.txt`, `motor-noche.txt` [5] |
| Alertas de viaje imposible en la prueba de Sparkov | 14.153 | 14.153, en 879 tarjetas (2,55 % de las compras; 190 caen en fraude). En la noche medida serían 200 alertas en 162 tarjetas | Sí | `motor-viaje.txt` |

## Hallazgos priorizados

### H1 — Crítico: en el triaje, el agente ve compras futuras de la tarjeta, sobre todo las fraudulentas

**Mecanismo.** Para un caso en vivo, `fin_ventana` es la apertura del caso más 48 h
(`app/riesgo/flujo.py:196`). `obtener_historial` devuelve las filas de `historial` con
`fecha_hora <= caso.fin_ventana` (`app/db/repositorio.py:278-281`), ordenadas de la más reciente a la más
antigua y con tope de 40 (`:295-296`), así que da prioridad a las filas futuras. Al reiniciar, solo se borran
las filas con `origen = 'en_vivo'` (`app/db/migrar.py:307`). Las filas de `semilla/historial.csv.gz`, la
semilla del M2, se quedan, y cubren las ventanas de los casos del M2 de esas mismas tarjetas, que se cruzan con
la noche del 19-jul. Además, el prompt de triaje pide `obtener_historial_reciente` (`app/agente/prompts.py:84`)
y manda bloquear ante "varias compras seguidas" (`:87`).

**Medido (`motor-noche.txt` [6]).**

- Abren caso 21 tarjetas, y 12 tienen filas futuras a la vista.
- Las **9** tarjetas con fraude las tienen: de 2 a 19 filas, casi todas fraudulentas (por ejemplo, …3984: 19 filas, 12 fraudulentas; …8262: 15 filas, 12 fraudulentas).
- De las 9 honestas que llegan a banda alta, 7 no tienen ninguna fila futura.
- Las tres tarjetas que la aritmética señala como bloqueadas por el agente en banda alta tenían a la vista 11 filas (5 fraudulentas), 8 (7) y 9 (8).
- La información extra está correlacionada con la etiqueta. Eso invalida la precisión de 1,0 del agente, el 71,4 % y la frase "lo que aporta el LLM: 9,6 puntos" (`docs/decisiones.md:371`).

**Salvedad.** No se leyeron las `trazas`, porque no se tocó la base. Confirmarlo toma un `SELECT` del
resultado de `obtener_historial_reciente` en las trazas de los triajes de la corrida del 9-nov.

**Mitigación (factible antes del 19-nov).**

1. Para casos `en_vivo`, limitar `obtener_historial` a `fecha_hora <=` la compra que disparó el triaje, y/o
   borrar en el reinicio las filas de semilla de las tarjetas del simulador con fecha desde el inicio de la
   ventana.
2. Agregar una prueba que falle si el historial de un caso en vivo trae filas posteriores al disparo.
3. Repetir `medir_momento3.py` (base e `ia_caida`, unos 10 minutos cada una) y reemplazar §13.1.

### H2 — Alto: a 3600x, el agente también decide con horas de futuro

`medir_momento3.py:143-149` traslada el **dinero** a tiempo real, pero no la **información**. Un triaje de unos
5 s equivale a unas 5 h del dataset: mientras el triaje espera en la cola, el caso y el historial en vivo ya
acumulan las compras siguientes. Hay una señal de que importa: con la misma noche, la corrida base tuvo 13
triajes en alta con 5 fraudes y la de `ia_caida` 11 con 3, así que la composición de la banda depende del reloj.

**Mitigación.** Después de H1, medir a 60x (36 min para la noche completa) o pausar el simulador mientras
corre un triaje. Si no da el tiempo, declararlo como limitación.

### H3 — Alto: una sola noche, nueve tarjetas, y la ventana se eligió mirando la etiqueta

- Los 9,6 puntos atribuidos al LLM son 3 tarjetas (2.729,56 USD).
- El IC por tarjeta de la regla de la 2.ª marca en esa noche va de 42 % a 72 %.
- La ventana se eligió por "la que más episodios ve empezar" (`scripts/generar_semilla_simulador.py:11-14`):
  2 ventanas tienen más, 11 empatan y la noche queda por encima de la mediana de las 184 ventanas de 36 h
  (regla de la 2.ª marca: 61,8 % contra una mediana de 55,6 %; `motor-ventanas_36h.csv`).
- No es un sesgo grave, porque la selección no miró el desempeño del sistema, pero hay que declararlo.

**Mitigación.** Agregar a §13 la cota poblacional fuera de línea (`motor-noche.txt` [5]): regla de la 2.ª marca
73,3 % [71,1; 75,3], bloquear en la 1.ª marca 85,8 % [84,3; 87,3]. El M3 real queda entre las dos, según
cuántas banda alta bloquee el agente. Mostrar ICs junto a toda cifra de la noche.

### H4 — Medio: la línea base de la prueba de necesidad es un hombre de paja

- "Monto > p95 **o** antes de las 6 h" (`src/motor_riesgo.py:105-107`) marca el 23,3 % de las compras.
- El AUC-PR de una predicción binaria es degenerado, así que el "factor 58" no compara lo mismo.
- Una regla de dos umbrales ajustada en validación logra F1 0,424 (`motor-puntuar.txt`).

La necesidad del modelo se sostiene: 0,811 contra 0,424 en F1 y 0,884 contra 0,137 en AUC-PR (el monto como
score continuo). La diferencia real ronda 2x en F1, no 29x.

**Mitigación.** Agregar esa fila a la tabla de §8 y quitar "70 falsas alarmas por fraude" como argumento
principal.

### H5 — Medio: el 13 % del análisis está calculado sobre la base equivocada

`scripts/analisis_ritmo_fraude.py:66-80` solo recorre las transacciones **marcadas** de cada caso. El monto
"entre marcas" es casi entero la 2.ª compra marcada, y deja fuera las compras fraudulentas no marcadas que hay en
medio. Calculado sobre todo el fraude de la tarjeta, el costo de esperar la 2.ª marca es 12,5 puntos: la
conclusión se mantiene por coincidencia.

**Mitigación.** Corregir la redacción de `docs/analisis-respuesta-fraude.md:74-77` y citar 12,5 puntos con su
método.

### H6 — Medio: episodios truncados en la ventana

- 4 de las 9 tarjetas llevaban horas o días robadas antes de las 20:00: 12.642 USD de fraude previo que no se
  cuenta, y su perfil ya incluye esas compras, por eso puntúan 0,998–0,999 en su primera compra de la ventana.
- Otros 5.260 USD del mismo episodio ocurren después del cierre (`motor-noche.txt` [2]).

**Mitigación.** Declararlo en §13.1, o medir sobre episodios completos (lo hace la cota de H3).

### H7 — Medio-bajo: el "5,7 s" usa la definición más favorable

Se cuenta desde la compra que disparó la banda final. Para las 2 tarjetas con fraude a las que el agente pidió
verificación, el tiempo real desde la primera compra sospechosa hasta el bloqueo es el intervalo del dataset
hasta la 2.ª marca (mediana de 100 min en el M2). Desde la apertura del caso, el p95 es 28 s y el máximo 32 s.

**Mitigación.** Nombrar la definición en §13.1 y reportar también `segundos_hasta_bloqueo`.

### H8 — Bajo-medio: el tramo de prueba se reutilizó para decisiones de diseño

- La regla de "2 marcas para abrir caso" se escogió comparando opciones con cifras de prueba
  (`validacion/motor-riesgo.md:477`).
- La corrección de la ventana de 24 h se observó en prueba.
- El rediseño del M3 sale del 13 %, calculado sobre la semilla, que es de prueba.

Los umbrales sí son de validación. El 0,884 ya no es un hold-out virgen.

**Mitigación.** Declararlo como limitación; no da tiempo de rehacerlo.

### H9 — Bajo: la paridad de 111.342 compras no tiene evidencia guardada

El script existe (`scripts/validar_paridad_en_vivo.py`). Hay que guardar su salida en `eval/resultados/` y
dejar dicho que la muestra fue de 200 tarjetas (`PLAN.md:66`). La paridad es significativa: compara el perfil
incremental con `agregar_features` y el modelo real. Mi recálculo independiente en la noche medida da 0 cambios.

### H10 — Bajo: viaje imposible

- Es determinista y no abre casos en Sparkov (`app/riesgo/flujo.py:41`), así que la red no lo prueba en vivo.
- Ignora los pares con 0 s entre compras (`src/detectar_viaje_imposible.py:55`,
  `app/riesgo/perfil_incremental.py:169`), justo el caso más imposible. Hay 44 en Sparkov.
- El 23/23 de los sintéticos es circular: el generador usa la misma regla.

**Mitigación.** Tratar 0 s con distancia > umbral como velocidad infinita y declarar la circularidad.

### H11 — Bajo: no se cuentan las verificaciones a clientes honestos

En la noche hubo 8 triajes honestos en alta que terminaron en verificación (avisos a titulares honestos), más
los de banda media. Reportar "verificaciones honestas por cada 1.000 compras" junto a los bloqueos falsos.

## Qué se comprobó y está bien

- El perfil por lotes usa solo historia previa (sumas desplazadas en `src/perfil_cuenta.py`).
- En vivo, el perfil se actualiza después de puntuar (`app/riesgo/flujo.py:132-149`) y la semilla del simulador
  solo trae historia anterior a la ventana (máximo 19-jul 19:59:47).
- La etiqueta del dataset no llega al agente: hay roles y pruebas para eso (`app/db/roles.py:44`,
  `test_repositorio.py:381`).
- El contrafactual del M2 no se contamina por los bloqueos de la corrida: fuera de línea da las mismas cifras.

## Para antes del 19-nov (en orden)

1. H1: el filtro de fecha en el historial, su prueba y repetir las dos mediciones.
2. H3 y H4: agregar a §8 y §13 la cota poblacional, los ICs y la línea base de dos umbrales.
3. H5, H7 y la frase del 88 %: correcciones de redacción.
4. H9: guardar el log de paridad.
5. H2, H6, H8 y H10: declararlos como limitaciones en §13.3.
