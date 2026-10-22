# Requisitos — motor-riesgo

## Para qué existe

Es la pieza que convierte transacciones en casos que un analista puede revisar. Hoy
`src/entrenar_modelo.py` solo imprime métricas sobre datos sintéticos y tiene una
filtración: calcula el perfil de cada cuenta con todas sus transacciones, incluida la
fraudulenta y las futuras, y parte al azar (`decisiones.md`, "Actualización
2026-10-21"). El motor corregido debe puntuar el riesgo de **uso no autorizado** con
ML clásico, comparándolo contra la regla de umbral fijo (la prueba de necesidad), y
entregar por cada caso la evidencia que después narra el LLM: score, desviaciones por
feature contra el perfil *previo* de la tarjeta, transacciones involucradas y
recomendación de bloqueo. Construirlo primero fue la decisión de la quinta sesión de
`plan-construccion.md`.

## Entradas

1. **Dataset real Sparkov** en `datos/fraudTrain.csv` y
   `datos/fraudTest.csv` (licencia CC0). Columnas originales relevantes:
   `trans_date_trans_time`, `cc_num`, `category`, `amt`, `merchant`, `lat`, `long`
   (domicilio del cliente, constante por tarjeta), `merch_lat`, `merch_long`
   (ubicación del comercio en cada transacción), `unix_time`, `is_fraud`. Se traducen
   a las columnas del proyecto (`id_cuenta`, `monto`, `fecha_hora`, `hora`,
   `latitud`, `longitud`, `es_fraude`…, ver `CLAUDE.md`) antes de usarse. Las
   columnas que identifican a la persona (`first`, `last`, `street`, `dob`, `job`,
   `trans_num`) no entran como features.
2. **Datos sintéticos** de `datos/transacciones.csv`: el motor tiene que seguir
   corriendo sobre ellos (pruebas rápidas y continuidad con los números ya
   publicados).

Hechos medidos en Sparkov el 2026-10-21 que condicionan el diseño: 1 296 675
transacciones de entrenamiento (2019-01-01 a 2020-06-21, 0,579 % fraude) y 555 719 de
prueba (2020-06-21 a 2020-12-31, 0,386 %); 983 tarjetas, una por cliente; mediana de
1 054 transacciones por tarjeta; el fraude llega en ráfagas (mediana de 10
transacciones por tarjeta en ~45 h), concentrado entre las 22 y las 3 h, con monto
mediano de 396 USD frente a 47 USD legítimo.

## Salidas

1. **Reporte de desempeño** en consola: precisión, recall, F1 y AUC-PR del modelo (o
   modelos comparados) y de la regla de umbral fijo, lado a lado, sobre el tramo de
   prueba.
2. **Score por transacción** del tramo de prueba.
3. **Casos marcados**: un caso agrupa las transacciones marcadas de una misma tarjeta
   dentro de una ventana de tiempo. Cada caso lleva como mínimo:
   - identificador del caso, tarjeta (`id_cuenta`), inicio y fin de la ventana;
   - transacciones involucradas (id, fecha-hora, monto, categoría, comercio, score);
   - score del caso (el máximo de sus transacciones) y nivel de recomendación;
   - desviaciones por feature contra el perfil previo de la tarjeta (por ejemplo:
     monto frente a su promedio y dispersión, hora frente a sus horas habituales,
     categoría frente a sus categorías habituales, distancia del comercio frente a la
     habitual), con el valor observado y el valor de referencia, para que el LLM las
     pueda citar textualmente;
   - tipo de fraude (`uso_no_autorizado` o `viaje_imposible`).
   Dónde quedan (archivo intermedio o directo a Postgres) se decide en diseño; la
   persistencia en Postgres es el componente siguiente.
4. **Recomendación de bloqueo** por caso, con tres niveles decididos por regla
   determinista: `bloquear_tarjeta` (uso no autorizado con score por encima del
   umbral de bloqueo), `bloquear_acceso_cuenta` (viaje imposible), `verificar_cliente`
   (score entre el umbral de verificación y el de bloqueo). Es una recomendación; el
   bloqueo lo decide un humano.

## Criterios de aceptación

1. Ninguna feature de una transacción usa información de esa misma transacción ni de
   transacciones posteriores de la tarjeta. Se verifica recalculando el perfil de una
   tarjeta a mano para dos transacciones elegidas al azar.
2. La partición es temporal: entrenamiento y validación anteriores al tramo de
   prueba; con Sparkov, el tramo de prueba es `fraudTest.csv`.
3. Los umbrales se eligen en un tramo de validación (por fecha, anterior al de
   prueba): el de bloqueo maximizando F1, el de verificación priorizando recall; luego
   se aplican al tramo de prueba sin retocarlos.
4. En el tramo de prueba de Sparkov, el modelo elegido supera a la regla de umbral
   fijo en AUC-PR y en F1. Se reportan precisión, recall, F1 y AUC-PR de todos; no hay
   cifra mínima pactada, el número que salga se reporta tal cual (referencia histórica
   en sintéticos: regla 22,7 % de precisión, modelo 97,7–99 %, calculado con la
   filtración).
5. Si una sola feature separa las clases casi perfectamente, se reporta como señal de
   alerta (`CLAUDE.md`, condición 3), no como buen resultado.
6. Todo caso marcado trae todos los campos de la salida 3; ninguno sin desviaciones ni
   sin recomendación.
7. Sobre Sparkov, el detector de viaje imposible se corre y se reporta su número de
   alertas (falsas alarmas, porque el dataset no trae ese fraude etiquetado).
8. El motor sigue corriendo sobre `datos/transacciones.csv` sin cambios de código,
   solo eligiendo la fuente.
9. Corre en el PC del equipo en un tiempo razonable; si no cabe en memoria, se
   documenta el muestreo.

## Casos borde

- Primeras transacciones de una tarjeta, sin historial previo: el perfil no existe;
  se marca como "sin historial suficiente" en vez de inventar un promedio.
- Tarjetas con dispersión de monto cero o casi cero: la desviación no puede dividir
  por cero.
- Tarjetas que aparecen solo en el tramo de prueba (924 de las 983 están en ambos).
- Transacciones con la misma fecha-hora en una tarjeta.
- Una ráfaga de fraude que cruza el límite entre ventanas.
- Viaje imposible y uso no autorizado en la misma tarjeta y ventana: la recomendación
  más severa manda, y el caso lleva ambos tipos.
- Una tarjeta por cliente en Sparkov: `bloquear_tarjeta` y bloquear al cliente no se
  distinguen con estos datos; se documenta, no se simula.

## Fuera de alcance

- Persistir en Postgres (componente siguiente).
- Llamar al LLM o redactar explicaciones (vista del analista).
- Bloqueo automático: el motor solo recomienda.
- SHAP por predicción (mejora opcional del plan).
- Ajuste fino de hiperparámetros más allá de lo necesario para comparar modelos.

## Preguntas abiertas

- Duración de la ventana del caso: el equipo eligió "tarjeta + ventana" con 24 h como
  ejemplo, pero las ráfagas de Sparkov duran ~45 h; proponer el valor en diseño con
  esa evidencia.
- Qué modelos se comparan contra la regla, y cuál queda como motor.
- Formato y lugar de la salida intermedia de casos antes de Postgres.
- Cómo se toma el tramo de validación dentro de `fraudTrain.csv` (por ejemplo, los
  últimos meses).
