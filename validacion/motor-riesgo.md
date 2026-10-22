# Validación — motor-riesgo  (corrida del 2026-10-21)

Componente revisado contra `CLAUDE.md`, `decisiones.md` (sobre todo la "Actualización
2026-10-21"), `requisitos/motor-riesgo.md` y las siete comprobaciones de "Cómo se valida"
de `diseno/motor-riesgo.md`. No se modificó código: los scripts auxiliares de
verificación quedaron fuera del proyecto (scratchpad de la sesión: `v1_filtracion_y_scores.py`,
`v2_casos.py`, `v3_que_pasa_si_24h.py`, con sus salidas en texto).

## Qué se corrió

Desde `src/`, con pandas 3.0.1, numpy 2.4.2 y scikit-learn 1.8.0:

1. `python entrenar_modelo.py` (sintéticos): 16 000 transacciones, 400 cuentas, 2,9 s.
   Tramos 60/20/20 por fecha. Elige `random_forest`; umbral de verificación y de bloqueo
   iguales (0,7354). 89 casos (66 `bloquear_tarjeta`, 23 `bloquear_acceso_cuenta`), los 89
   con fraude confirmado. Viaje imposible en prueba: 23 alertas, 23 de 23 reales.
2. `python entrenar_modelo.py --fuente sparkov`: 1 852 394 transacciones, 999 tarjetas,
   53,8 s. Entrenamiento submuestreado (todo el fraude + 20 % de normales: 219 193 filas).
   Elige `random_forest`; umbral de verificación 0,8051 (F2) y de bloqueo 0,8632 (F1).
   1 089 casos (702 `bloquear_tarjeta`, 387 `verificar_cliente`), 216 con fraude
   confirmado. Viaje imposible: 14 153 alertas en 879 tarjetas, que no generan casos.
3. `python detectar_viaje_imposible.py` (sintéticos, conjunto completo): 148 marcadas,
   148 verdaderas de 149 reales, precisión 1,000, recall 0,993, 0 falsos positivos y 1
   falso negativo.
4. Verificación independiente: recálculo a mano de features desde los CSV crudos,
   prueba de perturbación del futuro, recálculo de métricas con `modelo_riesgo.joblib`
   (coinciden exactamente con `metricas_motor.json`), revisión de los 1 089 casos y sus
   11 417 desviaciones, y un "qué pasa si" con la ventana de 24 h corregida, hecho
   solo en el scratchpad para medir el efecto del hallazgo 1.

## Resultados

### Tramo de prueba de Sparkov (`fraudTest.csv`, 555 719 filas, 0,386 % fraude)

Cada modelo con su umbral de mejor F1 elegido en validación y aplicado sin retocar.

| | Precisión | Recall | F1 | AUC-PR |
|---|---|---|---|---|
| Regla de umbral fijo (monto > 196,45 USD o antes de las 6 h) | 0,014 | 0,845 | 0,028 | 0,012 |
| Regresión logística | 0,282 | 0,457 | 0,349 | 0,149 |
| **Random Forest (elegido)** | **0,726** | **0,616** | **0,666** | **0,698** |
| HistGradientBoosting | 0,715 | 0,595 | 0,649 | 0,672 |

En validación (2020-03-21 a 2020-06-21) el Random Forest obtuvo AUC-PR 0,771 contra
0,765 del gradient boosting, por eso quedó elegido. El Random Forest supera a la regla
por un factor de 58 en AUC-PR y de 24 en F1: la prueba de necesidad se sostiene sobre un
dataset que no generamos nosotros.

### Tramo de prueba de sintéticos (3 177 filas, 2,1 % fraude)

| | Precisión | Recall | F1 | AUC-PR |
|---|---|---|---|---|
| Regla de umbral fijo | 0,272 | 1,000 | 0,428 | 0,272 |
| Regresión logística | 0,930 | 0,985 | 0,957 | 0,998 |
| Random Forest (elegido) | 1,000 | 1,000 | 1,000 | 1,000 |
| HistGradientBoosting | 1,000 | 1,000 | 1,000 | 1,000 |

### Comparación con los números históricos de `decisiones.md`

| | Histórico (sintéticos, con filtración, partición al azar) | Hoy, sintéticos (sin filtración, temporal) | Hoy, Sparkov |
|---|---|---|---|
| Modelo: precisión / recall / AUC-PR | 97,7 % / 98,8 % / 0,998 | 100 % / 100 % / 1,000 | 72,6 % / 61,6 % / 0,698 |
| Regla: precisión / recall / AUC-PR | 22,7 % / 100 % / 0,227 | 27,2 % / 100 % / 0,272 | 1,4 % / 84,5 % / 0,012 |

Cómo se explica la diferencia:

- **Quitar la filtración no bajó los sintéticos; los dejó perfectos.** El fraude
  sintético se genera como monto 4 a 10 veces el promedio de la cuenta, a una hora entre
  las 0 y las 5. Esa señal es tan fuerte que el perfil *previo* de la cuenta la separa
  igual de bien que el perfil con filtración, así que el 97,7 % histórico no venía de la
  filtración sino de que los datos son fáciles. Lo que sí deja claro esta corrida es que
  los sintéticos ya no sirven como evidencia del modelo: solo prueban que la tubería
  corre de punta a punta.
- **La caída a 0,70 de AUC-PR es el efecto del dataset real.** En Sparkov el fraude es
  más escaso (0,39 % frente a 2,1 %), lo generó un simulador ajeno, y sus montos y
  horas se traslapan con los legítimos; además, la feature de ráfagas está rota (hallazgo
  1), así que el modelo hoy no ve el rasgo más característico del fraude de Sparkov. Con
  la ventana de 24 h corregida (prueba en el scratchpad, sin tocar el proyecto) el
  gradient boosting llega a AUC-PR 0,884 y F1 0,811, y el Random Forest a 0,863 y 0,796.
- **La regla se desploma a 1,4 % de precisión** porque con 0,39 % de prevalencia casi
  todo lo que marca "madrugada o monto alto" es legítimo: en Sparkov muchas compras
  normales ocurren de noche y el percentil 95 del monto es solo 196 USD.

`decisiones.md`, sección "Resultado del prototipo", queda desactualizada. Conviene
reemplazar sus cifras **después** de arreglar el hallazgo 1, porque ese arreglo cambia
las métricas y el modelo elegido.

## Checklist

### Las 7 comprobaciones del diseño (más las del pedido de validación)

1. **Sin filtración — cumple; recálculo de `conteo_24h_previo` — no cumple.** Se tomaron
   cuatro transacciones con al menos 10 previas (una de entrenamiento, una normal de
   prueba y dos fraudes de prueba) y se recalcularon a mano desde `fraudTrain.csv` /
   `fraudTest.csv`, con solo las filas anteriores de la tarjeta. `n_previas`,
   `monto_promedio_previo`, `frecuencia_hora_previa` y `frecuencia_categoria_previa`
   coinciden exactamente en las cuatro. Además, multiplicar por 100 los montos futuros
   de una tarjeta y cambiar sus categorías futuras no altera ninguna feature de las
   2 874 filas anteriores (diferencia máxima 0,0): ninguna feature mira hacia adelante.
   En cambio `conteo_24h_previo` y `monto_24h_previo` no coinciden: por ejemplo, el
   fraude de la tarjeta 370612217861404 del 2020-11-05 01:38 tiene 6 transacciones en
   las 24 h previas, y el motor dice 1 923, que son todas sus transacciones previas. En
   una muestra de 1 000 filas de prueba el conteo del motor no coincide con la ventana
   real en ninguna y es igual a `n_previas` en las 1 000 (mediana real 4, mediana del
   motor 2 122). No es filtración (solo usa el pasado), pero la ventana es de unos 1 000
   días, no de 24 h. Ver hallazgo 1.
2. **Tramos sin solapamiento — cumple.** Entrenamiento 2019-01-01 00:00:18 a 2020-03-20
   23:58:44; validación 2020-03-21 00:00:20 a 2020-06-21 12:13:37; prueba 2020-06-21
   12:14:25 a 2020-12-31 23:59:34. Sin identificadores compartidos. El tramo de prueba
   es exactamente `fraudTest.csv`. En sintéticos la partición es por cuantiles de fecha.
3. **Tres modelos y regla lado a lado; el elegido supera a la regla — cumple.** Tablas de
   arriba, con precisión, recall, F1 y AUC-PR. Los umbrales se eligen en validación
   (bloqueo por F1, verificación por F2) y no se retocan en prueba. El percentil 95 de la
   regla sale del entrenamiento, ya no de prueba.
4. **Ninguna feature sola separa casi perfecto — cumple, con dos alertas.** En Sparkov la
   mejor feature sola es `monto` con AUC-PR 0,137 (con la ventana corregida,
   `monto_24h_previo` llega a 0,152). En sintéticos `razon_monto` sola da 0,895: no es
   separación perfecta, pero confirma que esos datos son demasiado fáciles. La segunda
   alerta es un artefacto de Sparkov: las 91 tarjetas con 20 transacciones o menos son
   100 % fraude, y en prueba las 149 filas `sin_historial = 1` son todas fraude (142
   quedan marcadas, con score mediano 0,996). El modelo puede estar aprendiendo "tarjeta
   nueva = fraude", que en un banco real sería falso. Sin esas filas el AUC-PR del Random
   Forest en prueba baja de 0,698 a 0,668. Ver hallazgo 4.
5. **Integridad de los casos — cumple en forma; el contenido de `ritmo_24h` es falso.**
   Los 1 089 casos traen todos los campos de requisitos y diseño (identificador, tarjeta,
   ventana, tipos, score máximo, nivel, motivo, señal principal, perfil previo,
   transacciones con id, fecha, monto, categoría, comercio, score, viaje imposible y
   desviaciones, y `fraude_confirmado_dataset`); ninguna transacción sin desviaciones.
   Las 2 397 transacciones de prueba con score ≥ umbral de verificación están cada una
   en exactamente un caso. Ningún caso supera 48 h (el mayor lapso es 47 h 45 min) y
   todos tienen `fin = inicio + 48 h`. La recomendación es coherente con los umbrales en
   los 1 089 casos. Se revisaron las **11 417** desviaciones (no solo una muestra de 20):
   en todas, las cifras de `descripcion` coinciden con `valor_observado` y
   `valor_referencia`, y la razón "N veces su promedio" cuadra con observado/referencia.
   `fraude_confirmado_dataset` coincide con la etiqueta en todos los casos. El problema
   es que en `ritmo_24h` texto y campo coinciden entre sí pero ambos son falsos ("hizo
   2251 transacciones por 216.114,96 en las 24 h anteriores"; mediana narrada 1 365), y
   esa es la `senal_principal` de 973 de los 1 089 casos (89 %).
6. **Viaje imposible — cumple.** Sobre sintéticos sigue en 148 de 149 (precisión 1,000,
   recall 0,993, 0 falsos positivos), igual que en `decisiones.md`, y en el tramo de
   prueba marca los 23 de 23. Sobre Sparkov se corre con `comparar_por="coordenadas"`,
   se reportan 14 153 alertas en 879 tarjetas y ningún caso las incluye (los 1 089 son
   `uso_no_autorizado`). El diseño esperaba falsas alarmas "cerca de cero" y salieron
   muchas: el simulador ubica los comercios al azar a unos 100 km del domicilio, así
   que dos compras seguidas "exigen" velocidades imposibles. La decisión de no generar
   casos es correcta; la expectativa escrita en el diseño no (hallazgo 6).
7. **Calidad a nivel de caso — no cumple.** Detalle en la sección siguiente.
8. **Comparación con el histórico — hecha** (sección anterior).

### Checklist general de la skill

- **Precisión, recall, F1 y AUC-PR en toda comparación — cumple.** Consola y
  `metricas_motor.json` reportan las cuatro para los tres modelos y la regla, en
  validación y en prueba.
- **Modelo lado a lado con la regla de umbral fijo — cumple.** La regla sigue siendo la
  idea original (monto alto o madrugada) y solo aparece como línea base, nunca como
  detector.
- **Fraude sintético como combinación de señales — cumple.** `generar_datos.py` no
  cambió: el uso no autorizado combina hora 0 a 5 con monto 4 a 10 veces el promedio y,
  la mitad de las veces, ciudad distinta; el ruido legítimo imita cada señal por separado.
- **Features de historial con `groupby` sobre los datos, no columnas del generador —
  cumple.** La lista de features no incluye `monto_promedio_cuenta` ni
  `ubicacion_habitual_cuenta`; todo sale de sumas y conteos acumulados desplazados en
  `perfil_cuenta.py`.
- **Filas `viaje_imposible` excluidas del entrenamiento ML — cumple.**
  `solo_uso_no_autorizado` las quita de los tres tramos antes de entrenar y medir.
- **Viaje imposible determinista, sin modelo — cumple.** Haversine contra tiempo
  transcurrido y 900 km/h, con precisión, recall, falsos positivos y falsos negativos
  reportados contra los casos inyectados.
- **Casos con todos los campos y donde dijo el diseño — cumple.**
  `datos/salidas_<fuente>/` con los cuatro archivos, uno por fuente.
- **Frontera modelo / LLM y solo lectura — no aplica** a este componente: el motor no
  llama a ningún LLM y la recomendación es una regla determinista, que es lo que pide
  `decisiones.md`.

## Calidad a nivel de caso (lo que ve el analista)

La observación previa se **confirma con números**.

| Nivel | Casos | Con fraude confirmado | Precisión por caso |
|---|---|---|---|
| `bloquear_tarjeta` | 702 | 210 | 29,9 % |
| `verificar_cliente` | 387 | 6 | 1,6 % |
| **Total** | **1 089** | **216** | **19,8 %** |

- **Los falsos positivos son casos de una sola transacción.** De los 873 casos sin
  fraude, 853 (97,7 %) tienen una sola transacción, 19 tienen dos y uno tiene tres. Los
  casos con fraude tienen mediana de 7 transacciones (media 7,0, rango 1 a 15) y solo 8
  de los 216 son de una transacción. En total hay 861 casos de una transacción (79 % de
  todos) y apenas 8 tienen fraude.
- **La aparente contradicción con el 72,6 % de precisión por transacción** se explica por
  las ráfagas: los 1 502 fraudes marcados se amontonan en unos 216 casos de ~7
  transacciones, mientras que las ~895 transacciones legítimas marcadas quedan sueltas y
  cada una abre su propio caso. El analista ve casos, no transacciones, y por cada caso
  real recibe cuatro falsos.
- **Recall por tarjeta: 215 de las 218 tarjetas con fraude en prueba (98,6 %)** tienen al
  menos un caso que contiene alguno de sus fraudes, casi siempre uno solo por tarjeta.
  Por transacción, 1 502 de los 2 145 fraudes (70 %) quedan dentro de algún caso. Los
  873 casos falsos se reparten en 490 tarjetas distintas.

### Reglas a nivel de caso que mejorarían la precisión (propuesta, no implementada)

Para no hacer trampa con el tramo de prueba, se reconstruyeron los casos también en
validación con el mismo algoritmo (627 casos, 135 con fraude, 482 de una transacción de
los cuales solo 2 con fraude), el parámetro de la regla agregada se eligió ahí y luego se
midió en prueba.

| Regla (prueba) | Casos | Precisión por caso | Casos `bloquear_tarjeta` | Precisión de `bloquear_tarjeta` | Tarjetas con fraude cubiertas / con bloqueo |
|---|---|---|---|---|---|
| Actual: bloquear si score máximo ≥ 0,863 | 1 089 | 19,8 % | 702 | 29,9 % | 215 / 209 de 218 |
| A. Bloquear solo si el caso tiene ≥ 2 transacciones marcadas; las de una sola pasan a `verificar_cliente` | 1 089 | 19,8 % | 223 | 91,9 % | 215 / 204 |
| B. Bloquear si ≥ 2 transacciones del caso superan el umbral de bloqueo | 1 089 | 19,8 % | 206 | 97,6 % | 215 / 200 |
| C. Bloquear si la suma de scores del caso ≥ 1,9 (k elegido en validación) | 1 089 | 19,8 % | 205 | 98,5 % | 215 / 201 |
| D. No abrir caso con una sola transacción (bloqueo como hoy) | 228 | 91,2 % | 223 | 91,9 % | 207 / 204 |

Lectura: A, B y C no esconden nada al analista (los 1 089 casos siguen existiendo) pero
reservan el bloqueo para las ráfagas; suben la precisión del bloqueo de 30 % a 92–98 % a
cambio de que 5 a 9 tarjetas con fraude bajen de "bloquear" a "verificar". D es la única
que sube la precisión por caso (a 91 %), pero pierde 8 tarjetas con fraude y descarta
transacciones sueltas sin que nadie las vea. **Advertencia importante:** estas reglas
están calibradas sobre el fraude en ráfaga de Sparkov. En los sintéticos 88 de los 89
casos son de una sola transacción y todos son fraude, así que D borraría casi todos los
casos sintéticos y A los mandaría a verificar. Por eso la variante más defendible parece
C o B con una excepción por score muy alto, y nunca descartar casos (dejar las
transacciones sueltas como `verificar_cliente`). Con la ventana de 24 h corregida el
patrón se mantiene (870 casos, 25,3 % con fraude, 583 de una transacción de los cuales
solo 3 con fraude), así que la regla habrá que recalibrarla después de ese arreglo.
**Elegir la regla le corresponde al equipo vía `disenar-fraude`**; si cambia el criterio
de la salida 4 de los requisitos, pasa antes por `requisitos-fraude`.

## Hallazgos a corregir

1. **Crítico — la ventana de 24 h no es de 24 h (vuelve a `construir-fraude`).** En
   `perfil_cuenta._ventana_24h_previa`, `datos["fecha_hora"].astype("int64") // 10**9`
   supone nanosegundos, pero pandas 3 lee las fechas como `datetime64[us]`; el resultado
   queda en unidades de 1 000 s y la ventana efectiva es de unos 1 000 días.
   `conteo_24h_previo` termina igual a `n_previas` y `monto_24h_previo` igual a la suma
   acumulada. Dos consecuencias: el modelo no ve las ráfagas (con la ventana correcta el
   AUC-PR en prueba sube de 0,698 a 0,86–0,88 y el elegido pasa a ser el gradient
   boosting), y el texto que va a citar el LLM es falso en el 89 % de los casos ("2 251
   transacciones en las 24 h anteriores"), lo que rompe la regla de trazabilidad de
   `decisiones.md`. El arreglo debe convertir a segundos sin depender de la resolución
   (por ejemplo, restar la época y dividir por `pd.Timedelta(seconds=1)`) y dejar una
   comprobación que lo detecte si vuelve a pasar. Después hay que volver a correr las
   dos fuentes y esta validación.
2. **Alto — precisión por caso de 19,8 % (vuelve a `disenar-fraude`).** El 97,7 % de los
   casos falsos son de una sola transacción y el 70 % de los `bloquear_tarjeta` son
   falsos. Hace falta una regla de nivel a nivel de caso (tabla de arriba), elegida por
   el equipo y calibrada en validación después del hallazgo 1.
3. **Medio — la `senal_principal` y el orden de las desviaciones no reflejan lo que pesó
   en el modelo (vuelve a `disenar-fraude`).** El orden usa pesos ad hoc: la hora pesa
   `2 × (1 − frecuencia)`, casi siempre ≈ 1,9, y el monto solo la supera con z > 5,7.
   Hoy gana `ritmo_24h` por el bug; con la ventana corregida gana `hora` en 561 de 870
   casos aunque el monto y las ráfagas sean lo que separa. `decisiones.md` pide
   trazabilidad "score → features que pesaron → explicación", así que el criterio de
   orden debe definirse en el diseño (por ejemplo, rareza en percentiles comparables o
   importancia del modelo).
4. **Medio — artefacto de Sparkov "tarjeta nueva = fraude" (vuelve a `disenar-fraude`,
   y se documenta en `decisiones.md`).** Las 91 tarjetas con 20 transacciones o menos son
   todas fraude, y las 149 filas sin historial del tramo de prueba también. Hay que
   decidir si `sin_historial` sigue como feature y reportar las métricas también sin esas
   filas (AUC-PR 0,668 frente a 0,698), para no vender un rasgo del simulador como
   capacidad del modelo.
5. **Bajo — los sintéticos quedaron perfectos (documentación en `decisiones.md`).**
   Random Forest y gradient boosting dan 1,000 en todo y `razon_monto` sola da AUC-PR
   0,895. En la presentación, Sparkov debe ser la evidencia del modelo y los sintéticos
   solo la de que la tubería y el detector de viaje imposible funcionan.
6. **Bajo — expectativa equivocada sobre viaje imposible en Sparkov (vuelve a
   `disenar-fraude`).** El diseño dice "falsas alarmas esperadas cerca de cero" y salen
   14 153 en 879 tarjetas. El código lo maneja bien (no genera casos); hay que corregir
   el texto del diseño y explicarlo en `decisiones.md`.
7. **Bajo — redacción de las descripciones (vuelve a `construir-fraude`).** 16
   descripciones dicen "solo el X %" con X de 20 % o más; "A las 1 h" en lugar de "A la
   1 h"; y el monto movido en 24 h aparece en el texto de `ritmo_24h` sin campo propio,
   así que esa cifra no se puede rastrear a un valor guardado.
8. **Documentación — `decisiones.md` y `requisitos/motor-riesgo.md`.** Reemplazar los
   números de "Resultado del prototipo" por los de Sparkov una vez cerrado el hallazgo 1,
   dejando los históricos como referencia. En requisitos, "983 tarjetas" es el conteo de
   `fraudTrain.csv`; el total es 999, con 16 que solo aparecen en prueba.

## Veredicto

**Necesita arreglos antes de presentar.** La partición temporal, la ausencia de
filtración del futuro, la comparación contra la regla y la estructura de los casos están
bien, y el modelo le gana a la regla con claridad sobre un dataset real. Pero el
hallazgo 1 hace que la evidencia que leería el analista (y citaría el LLM) sea falsa en
casi nueve de cada diez casos, y además subestima al modelo. El hallazgo 2 hace que
cuatro de cada cinco casos que recibe el analista sean falsas alarmas. Lo primero que
hay que arreglar es la ventana de 24 h (`construir-fraude`); luego el equipo elige la
regla a nivel de caso (`disenar-fraude`), se vuelve a correr todo y se repite esta
validación antes de actualizar `decisiones.md`.

---

# Segunda pasada (2026-10-21, después de la revisión del diseño)

Esta pasada valida otra vez el motor después de los arreglos de `construir-fraude`
(hallazgos 1 y 7) y de las decisiones de la sección "Revisión 2026-10-21 — tras
`validacion/motor-riesgo.md`" de `diseno/motor-riesgo.md`:

- `bloquear_tarjeta` exige 2 o más transacciones del caso sobre el umbral de bloqueo.
- Cada desviación trae `contribucion_modelo` (oclusión con las medianas de las normales del
  entrenamiento), `percentil_rareza` y `relevante`.
- `metricas_motor.json` reporta `prueba_sin_tarjetas_nuevas`.

La primera pasada queda arriba como registro. Los scripts de esta pasada
(`p2_v4_verificacion.py` y las salidas `p2_*.txt`) quedaron en el scratchpad de la sesión,
fuera del proyecto. No se tocó código ni otros documentos.

## Qué se corrió (segunda pasada)

1. `python entrenar_modelo.py` (sintéticos), 3,2 s. Elige `random_forest`, con el umbral
   de verificación igual al de bloqueo (0,7178). Genera 89 casos: 66 `verificar_cliente` y
   23 `bloquear_acceso_cuenta`, todos con fraude confirmado y **ningún
   `bloquear_tarjeta`**. Viaje imposible en prueba: 23 de 23.
2. `python entrenar_modelo.py --fuente sparkov`, 59,7 s. Ahora elige
   **`gradient_boosting`** (AUC-PR en validación 0,925 frente a 0,908 del Random Forest),
   con umbral de verificación 0,9477 (F2) y de bloqueo 0,9664 (F1). Genera 870 casos: 249
   `bloquear_tarjeta` (215 con fraude) y 621 `verificar_cliente` (5 con fraude). Cubre
   215 de las 218 tarjetas con fraude. Viaje imposible: 14 153 alertas en 879 tarjetas, que
   no abren casos.
3. Verificación independiente:
   - la ventana de 24 h, recalculada a mano desde los CSV crudos;
   - las medianas y los percentiles, recalculados contra todas las normales del
     entrenamiento;
   - la oclusión, recalculada con `modelo_riesgo.joblib`;
   - las 15 026 desviaciones de los 870 casos, revisadas una por una;
   - los casos reconstruidos en validación, para calibrar las opciones de la cola
     `verificar_cliente` sin mirar el tramo de prueba.

## Resultados (segunda pasada)

### Prueba Sparkov (555 719 filas, 0,386 % fraude), con el umbral de mejor F1 de cada modelo

| | Precisión | Recall | F1 | AUC-PR |
|---|---|---|---|---|
| Regla de umbral fijo | 0,014 | 0,845 | 0,028 | 0,012 |
| Regresión logística | 0,340 | 0,606 | 0,436 | 0,277 |
| Random Forest | 0,812 | 0,779 | 0,796 | 0,863 |
| **HistGradientBoosting (elegido)** | **0,786** | **0,838** | **0,811** | **0,884** |
| Elegido sin las 149 filas de tarjetas nuevas | 0,773 | 0,832 | 0,801 | 0,875 |
| Regla sin tarjetas nuevas | 0,013 | 0,841 | 0,026 | 0,011 |

Con la ventana de 24 h arreglada, el AUC-PR del motor sube de 0,698 a 0,884 y el F1 de
0,666 a 0,811, como anticipó la primera pasada. Sin las tarjetas nuevas (el artefacto del
simulador) el AUC-PR solo baja a 0,875, así que el modelo no depende de ese rasgo.

### Sintéticos

Nada cambia de fondo:

- Random Forest y gradient boosting: 1,000 en las cuatro métricas.
- Regresión logística: 0,985 / 0,985 / 0,985 / 0,997.
- Regla: 0,272 / 1,000 / 0,428 / 0,272.
- `razon_monto` sola sigue en AUC-PR 0,895.

### Frente al histórico de `decisiones.md`

| | Precisión | Recall | AUC-PR |
|---|---|---|---|
| Histórico (sintéticos, con filtración): modelo / regla | 97,7 % / 22,7 % | 98,8 % / 100 % | 0,998 / 0,227 |
| Hoy, sintéticos: modelo / regla | 100 % / 27,2 % | 100 % / 100 % | 1,000 / 0,272 |
| Hoy, Sparkov: modelo / regla | 78,6 % / 1,4 % | 83,8 % / 84,5 % | 0,884 / 0,012 |

La lectura de la primera pasada se mantiene:

- La filtración nunca fue lo que sostenía los números sintéticos. Siguen perfectos porque
  esos datos son fáciles.
- La distancia con el 97,7 % la explica el dataset real.
- La regla se hunde en Sparkov por la baja prevalencia del fraude.

## Comprobaciones (segunda pasada)

- **(a) Ventana de 24 h a mano — cumple.** Se recalcularon cinco transacciones desde
  `fraudTrain.csv`/`fraudTest.csv`, con solo las filas anteriores de cada tarjeta: una de
  entrenamiento, una normal de prueba y tres fraudes de prueba. Entre los fraudes está el
  de la tarjeta 370612217861404 del 2020-11-05, que en la primera pasada daba 1 923
  transacciones previas. Las seis cifras coinciden en las cinco transacciones; ese fraude
  ahora da 6 transacciones y 1 144,10 USD, igual que el recálculo. En una muestra de 1 000
  filas de prueba, `conteo_24h_previo` y `monto_24h_previo` coinciden en las 1 000
  (mediana: 4 transacciones). `n_previas`, el promedio previo y las frecuencias de hora y
  categoría siguen exactos.
- **(b) Percentil y contribución — cumple.**
  - Las medianas guardadas en el `.joblib` son idénticas a las recalculadas sobre las
    normales del entrenamiento.
  - En 67 desviaciones de 12 transacciones al azar, `percentil_rareza` coincide
    exactamente con la muestra de referencia guardada. Contra *todas* las normales del
    entrenamiento difiere como máximo 0,37 puntos, así que la muestra de 50 000 es
    representativa.
  - La oclusión recalculada a mano para 3 transacciones coincide con
    `contribucion_modelo` en todas sus señales (diferencia 0,00000). Por ejemplo, en la
    transacción `18908053fc` (score 0,9619), llevar `monto_24h` a su valor típico baja el
    score 0,937, la hora lo baja 0,846 y el monto 0,253; el ritmo de 24 h aporta −0,012.
- **(c) Señales completas y relevantes coherentes — cumple.**
  - Las 2 621 transacciones de los casos traen las seis señales de Sparkov (monto, hora,
    ritmo_24h, monto_24h, categoría y distancia), o solo `historial` si la tarjeta no tiene
    historia. A ninguna desviación le falta alguno de sus siete campos.
  - **Ninguna desviación `relevante` tiene contribución ≤ 0**, salvo `historial`. Todas
    siguen la regla del diseño: contribución > 0 y percentil ≥ 90, o contribución ≥ 0,05.
  - Todas las transacciones están ordenadas por contribución. En los 870 casos, la
    `senal_principal` coincide con la primera razón de la transacción de mayor score, y
    ninguna transacción se queda sin razones relevantes.
  - Las 2 288 contribuciones negativas (de 14 886) se conservan en el JSON, marcadas como
    no relevantes.
  - En las 15 026 descripciones:
    - las cifras cuadran con `valor_observado` y `valor_referencia`;
    - el conteo y el monto de 24 h coinciden con las features;
    - el gasto diario habitual es el promedio por el ritmo diario;
    - "solo el" aparece únicamente por debajo de 20 %;
    - la frase "Más inusual que el X %" aparece solo en las relevantes y con el percentil
      correcto.
  - La `senal_principal` es ahora `monto_24h` en 445 casos, `monto` en 408, `historial` en
    16 y `hora` en 1. Refleja lo que separa en Sparkov (gasto en ráfaga y monto), no un peso
    fijo.
- **Ventanas y recomendación — cumple.** Ningún caso supera 48 h. El nivel es coherente con
  la regla nueva en los 870 casos. El único desajuste aparente (C-000501) es redondeo: el
  JSON guarda el score con 4 decimales y muestra 0,9664, pero el caso cuenta como "sobre el
  umbral" de 0,96641.
- **Ninguna feature sola separa casi perfecto — cumple.** El máximo en Sparkov es
  `monto_24h_previo`, con 0,152.
- **Viaje imposible — cumple.** En sintéticos marca 23 de 23 en prueba; en el conjunto
  completo eran 148 de 149 en la primera pasada, y el detector no cambió. En Sparkov hay
  14 153 alertas y ningún caso.
- **(d) Calidad por caso — cumple para el bloqueo.**

  | Nivel | Casos | Con fraude | Precisión por caso |
  |---|---|---|---|
  | `bloquear_tarjeta` | 249 | 215 | 86,3 % |
  | `verificar_cliente` | 621 | 5 | 0,8 % |
  | Total | 870 | 220 | 25,3 % |

  - Recall por tarjeta: 215 de las 218 tarjetas con fraude tienen algún caso con fraude;
    212 con `bloquear_tarjeta` y 3 solo con `verificar_cliente`.
  - 1 864 de los 2 145 fraudes del tramo (87 %) quedan dentro de un caso; en la primera
    pasada eran 1 502.
  - Los casos sin fraude siguen siendo casi todos de una sola transacción: 580 de 650.
- **(e) Cola `verificar_cliente` — no cumple su propósito en Sparkov.** El detalle está en
  la sección siguiente.
- **(f) Regla de ≥ 2 en sintéticos — es un problema para la demo, no para las métricas.**
  - En sintéticos, el fraude de uso no autorizado es de una sola transacción. Las 78
    cuentas que tienen dos o más lo reciben separado por días, nunca dentro de 48 h.
  - Por eso los 66 casos de uso no autorizado salen como `verificar_cliente`, con el motivo
    "una compra aislada se confirma con el cliente". Todos son fraude real y casi todos
    tienen score de 0,97 a 1,00. No hay ni un `bloquear_tarjeta` en los sintéticos.
  - Si la demo usa sintéticos, el nivel `bloquear_tarjeta` no aparece y el analista ve
    casos clarísimos rebajados a verificación.
  - Una excepción por score muy alto no se puede justificar con datos. En Sparkov, los
    casos de una sola transacción con score ≥ 0,99 tienen 0 fraudes de 32 en validación y
    2 de 70 en prueba.
  - Recomendación para la presentación: mostrar `bloquear_tarjeta` y `verificar_cliente`
    sobre Sparkov y `bloquear_acceso_cuenta` sobre sintéticos (en Sparkov el viaje
    imposible no abre casos), y contar que
    en los sintéticos la regla es conservadora a propósito. Si el equipo quiere que la demo
    sintética bloquee, la salida es cambiar el generador para que el uso no autorizado
    llegue en ráfaga (`construir-fraude`, documentándolo en `decisiones.md`), no ablandar la
    regla.

## Cola `verificar_cliente`: de dónde sale y qué hacer con ella

| Origen | Casos | Con fraude | Casos de 1 transacción |
|---|---|---|---|
| Una transacción sobre el umbral de bloqueo (rebajada por la regla ≥ 2) | 402 | 4 | 371 |
| Ninguna sobre el bloqueo, score entre 0,9477 (F2) y 0,9664 (F1) | 219 | 1 | 212 |
| **Total** | **621** | **5 (0,8 %)** | **583** |

De dónde sale la cola:

- Dos tercios vienen de la regla nueva.
- El tercio restante viene del margen entre los dos umbrales. Ese margen es muy angosto
  (0,019) porque F2 y F1 se calculan por transacción y no dicen nada del caso.
- Solo 3 tarjetas con fraude dependen de la cola: `2254799658404120`, `4514242065619750` y
  `676314217768`. Los demás casos con fraude de la cola son de tarjetas que además tienen
  un `bloquear_tarjeta`.
- Ordenar por score casi no ayuda. El top 50 de la cola trae 2 fraudes y el top 100 trae 3;
  el tramo de score más alto (> 0,995) tiene 2 fraudes en 29 casos.

Opciones propuestas, sin implementar. Las cifras son del tramo de prueba, con el umbral o
el criterio fijado en validación:

| Opción | Casos totales | `verificar_cliente` (precisión) | Tarjetas con fraude cubiertas | Tarjetas perdidas frente a hoy |
|---|---|---|---|---|
| Hoy | 870 | 621 (0,8 %) | 215 de 218 | — |
| 1. No abrir casos sin ninguna transacción sobre el umbral de bloqueo | 651 | 402 (1,0 %) | 214 | 1 |
| 2a. Umbral de verificación = primer score con precisión ≥ 70 % en validación (0,9003) | 1 330 | 1 081 (0,5 %) | 215 | 0 |
| 2b. Ídem con precisión ≥ 50 % (0,7511) | 2 515 | 2 265 (0,3 %) | 217 | +2 ganadas |
| 3. Mantener la cola, ordenada por score (top 100) | 349 visibles | 100 (3 %) | 215 si se recorre toda | 0 (2 si solo se mira el top 100) |
| 4. Cola solo con casos de 2 o más transacciones | 287 | 38 (5,3 %) | 213 | 2 |
| 5. Sin cola: solo `bloquear_tarjeta` | 249 | 0 | 212 | 3 |

Lectura:

- Bajar el umbral de verificación (2a y 2b) solo agrega ruido. En validación, ninguna
  variante deja una cola con más de 0,7 % de fraude.
- En Sparkov lo que separa es la ráfaga, no el score. Por eso las opciones útiles son dos:
  - la 4: la cola queda 16 veces más chica y 6 veces más precisa, a costa de 2 tarjetas;
  - la 5: una lista limpia de 249 casos con 86 % de precisión, a costa de 3 tarjetas
    (1,4 % de las tarjetas con fraude).
- La opción 1 apenas mejora.
- Cualquier opción choca con lo visto en (f): en sintéticos todo fraude es de una sola
  transacción, así que según la variante la cola quedaría vacía o igual que hoy.

**Elegirla le corresponde al equipo vía `disenar-fraude`.**

## Hallazgos de la segunda pasada

Quedan **cerrados** los hallazgos 1, 2, 3, 4, 6 y 7 de la primera pasada:

- la ventana de 24 h es correcta;
- el bloqueo tiene 86 % de precisión por caso;
- las razones están ordenadas por su contribución real;
- las métricas sin tarjetas nuevas están reportadas;
- la expectativa sobre viaje imposible ya está corregida en el diseño;
- la redacción está arreglada.

Quedan abiertos:

1. **Medio — la cola `verificar_cliente` es casi ruido en Sparkov (vuelve a
   `disenar-fraude`).** Son 621 casos con 0,8 % de fraude: el 71 % de lo que vería el
   analista. Las opciones y sus costos están en la tabla de arriba; la recomendación
   técnica es la 4 o la 5.
2. **Medio — en sintéticos no hay ningún `bloquear_tarjeta` (vuelve a `disenar-fraude`
   para decidir; si se cambia el generador, a `construir-fraude`).** Es un problema de
   demo, no de métricas: los 66 casos de uso no autorizado, todos fraude, se rebajan a
   verificación.
3. **Bajo — en las tarjetas sin historial, la única razón citada pesa 0 (vuelve a
   `disenar-fraude`).** Las 140 transacciones sin historial traen solo la señal
   `historial`, con contribución 0,0000; se marca relevante por excepción, aunque esas
   transacciones tienen score cercano a 0,99. El analista no ve qué empujó de verdad el
   score: el monto y el gasto de 24 h se calculan, pero no se listan. Afecta a 16 casos.
4. **Bajo — redondeo del score en el JSON.** El score se guarda con 4 decimales y el umbral
   completo, así que un caso (C-000501) muestra 0,9664 y cuenta como "sobre el umbral"
   de 0,96641. Es inofensivo, pero el LLM podría citar "0,9664 supera 0,9664". Vuelve a
   `construir-fraude` si se quiere guardar el umbral con el mismo redondeo.
5. **Documentación — `decisiones.md` sigue con los números del prototipo.** Ya se pueden
   reemplazar:
   - motor: `gradient_boosting` en Sparkov, con precisión 78,6 %, recall 83,8 %, F1 0,811 y
     AUC-PR 0,884 (0,875 sin tarjetas nuevas);
   - regla: 1,4 % / 84,5 % / 0,028 / 0,012;
   - por caso: 86,3 % de precisión del bloqueo, con 212 de 218 tarjetas con fraude
     bloqueadas.

   También hay que corregir en requisitos "983 tarjetas": es el conteo de
   `fraudTrain.csv`, y el total es 999.

## Veredicto (segunda pasada)

**Se puede presentar el motor de riesgo**, con una condición de documentación: actualizar
`decisiones.md` con los números de arriba antes de la asesoría, porque es lo primero que se
revisa.

No queda ningún error de cálculo ni de trazabilidad. La ventana, los percentiles, la
oclusión y las cifras de las descripciones cuadran a mano, y el bloqueo es preciso y cubre
casi todas las tarjetas con fraude.

Faltan dos decisiones de diseño que conviene tomar antes de construir la vista del
analista, no antes de mostrar el motor:

- qué hacer con la cola `verificar_cliente` (hallazgo 1);
- cómo mostrar los niveles en la demo sintética (hallazgo 2).

Mientras tanto, `bloquear_tarjeta` y `verificar_cliente` se demuestran sobre Sparkov y
`bloquear_acceso_cuenta` sobre los sintéticos.
