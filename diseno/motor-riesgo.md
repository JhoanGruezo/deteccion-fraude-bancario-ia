# Diseño — motor-riesgo

Implementa `requisitos/motor-riesgo.md`. Primera versión (2026-10-21).

## Decisiones de esta sesión

- **Ventana del caso: 48 h**, anclada en la primera transacción marcada de la
  tarjeta. Las ráfagas de fraude de Sparkov duran unas 45 h (p90: 47 h); con 24 h la
  misma ráfaga se partiría en dos alertas. Resuelve la primera pregunta abierta de
  los requisitos.
- **Modelos comparados: regresión logística, Random Forest e
  HistGradientBoosting**, contra la regla de umbral fijo. Queda como motor el de
  mejor AUC-PR en validación; los cuatro se reportan en prueba.
- **Código en módulos separados**: `cargar_datos.py`, `perfil_cuenta.py`,
  `motor_riesgo.py`, y `entrenar_modelo.py` como punto de entrada. `perfil_cuenta.py`
  queda reutilizable por la vista del analista.
- **Salidas: JSON + CSV + métricas.** El usuario pidió JSON y CSV y aceptó un tercer
  archivo si aportaba. Se suma `metricas_motor.json` para que la validación y
  `decisiones.md` comparen contra un número guardado con fecha, no contra la consola.
- **Tramo de validación**: los últimos 3 meses de `fraudTrain.csv` (desde
  2020-03-21). Entrenamiento: lo anterior. Prueba: `fraudTest.csv` completo.
- **Umbral de verificación por F2** (pesa el recall el doble que la precisión). Así
  se concreta "priorizar recall" sin inventar una cifra mínima. El umbral de bloqueo
  es el de mejor F1 en validación (decidido en requisitos).

## Dónde vive

```
src/
  cargar_datos.py          — NUEVO: lee sintéticos o Sparkov y los deja en las columnas del proyecto
  perfil_cuenta.py         — NUEVO: features contra el perfil PREVIO de cada tarjeta (sin filtración)
  motor_riesgo.py          — NUEVO: partición temporal, modelos, umbrales, casos y recomendación
  entrenar_modelo.py       — REESCRITO como punto de entrada: python entrenar_modelo.py --fuente sparkov|sinteticos
  detectar_viaje_imposible.py — se reutiliza su función detectar(); su main() no cambia
datos/
  fraudTrain.csv, fraudTest.csv     — Sparkov (no se versionan)
  salidas_<fuente>/
    casos_marcados.json    — casos completos, con transacciones y desviaciones anidadas
    casos_marcados.csv     — una fila por caso, para revisar a mano o en Excel
    metricas_motor.json    — métricas de la corrida, con fecha, fuente y umbrales
    modelo_riesgo.joblib   — modelo elegido + lista de features + umbrales
```

Cada fuente escribe en su propia carpeta para que la corrida de sintéticos no pise la
de Sparkov.

## Módulos y funciones

### `cargar_datos.py`

- `cargar_sinteticos(ruta) -> DataFrame`: lee `transacciones.csv`, convierte
  `fecha_hora` a fecha y devuelve las columnas del proyecto tal cual.
- `cargar_sparkov(ruta_entrenamiento, ruta_prueba) -> DataFrame`: lee los dos CSV
  con solo las columnas necesarias, los concatena con una columna `tramo_origen`
  (`"entrenamiento"`/`"prueba"`) y los traduce (tabla en "Formato de datos").
- `cargar(fuente) -> DataFrame`: elige entre las dos según `fuente`.

### `perfil_cuenta.py`

Todas las features usan solo transacciones **anteriores** de la misma tarjeta. Se
ordena por `id_cuenta, fecha_hora, id_transaccion` y se usan sumas y conteos
acumulados desplazados una posición. Es vectorizado, sin `iterrows`.

- `agregar_features(datos) -> (DataFrame, list[str])`: agrega las columnas de abajo
  y devuelve la lista de features que existen para esa fuente (las de categoría y
  distancia al domicilio solo existen en Sparkov).
  - `n_previas`: transacciones anteriores de la tarjeta.
  - `sin_historial`: 1 si `n_previas < MINIMO_HISTORIAL` (10). En ese caso las
    desviaciones toman valores neutros (z = 0, razón = 1, frecuencias = 0,5) y la
    salida del caso dice "sin historial suficiente" en vez de citar un promedio.
  - `monto_promedio_previo`, `monto_desv_previa` (con piso de 1,0 para no dividir
    por cero), `z_monto`, `razon_monto` (monto / promedio previo, la cifra que se
    puede narrar: "6,4 veces su promedio").
  - `frecuencia_hora_previa`: fracción de sus transacciones anteriores hechas en esa
    misma hora.
  - `frecuencia_categoria_previa` (Sparkov): fracción anterior en esa categoría.
  - `frecuencia_ubicacion_previa` (sintéticos): fracción anterior en esa ciudad.
    Reemplaza a `ubicacion_distinta_habitual`, que usaba la moda de toda la serie.
  - `distancia_domicilio_km` (Sparkov): Haversine entre domicilio y comercio, y
    `distancia_vs_habitual_km` = esa distancia menos su promedio previo.
  - `conteo_24h_previo` y `monto_24h_previo`: cuántas transacciones y cuánto dinero
    movió la tarjeta en las 24 h anteriores (ventana que no incluye la transacción
    actual). Captura las ráfagas.
  - `tasa_diaria_previa`: transacciones por día de su historial, la referencia contra
    la cual se narra el `conteo_24h_previo`.
  - `hora`, `monto`: en crudo, como en la versión actual.
- `perfil_al_momento(datos, id_cuenta, fecha) -> dict`: perfil de una tarjeta con
  todo lo anterior a `fecha`: monto promedio y desviación, las 3 horas y las 3
  categorías más frecuentes con su porcentaje, transacciones por día. Lo usa
  `motor_riesgo.py` para el resumen del caso, y más adelante el agente.

### `motor_riesgo.py`

- `dividir_temporal(datos, fuente) -> (entrenamiento, validacion, prueba)`: Sparkov
  según las fechas de arriba; sintéticos por cuantiles de fecha 60/20/20.
- `submuestrear_entrenamiento(entrenamiento, proporcion_normales=0.2, semilla=7)`:
  conserva todo el fraude y el 20 % de las normales, solo para entrenar (con 1 M de
  filas el Random Forest se vuelve lento en el PC del equipo). Los umbrales se eligen
  sobre validación completa, así que el submuestreo no sesga los cortes. Queda
  documentado en las métricas.
- `entrenar_modelos(entrenamiento, features) -> dict[str, modelo]`:
  - `regresion_logistica`: `StandardScaler` + `LogisticRegression(class_weight="balanced", max_iter=1000)`.
  - `random_forest`: `RandomForestClassifier(n_estimators=200, max_depth=12, min_samples_leaf=20, class_weight="balanced_subsample", n_jobs=-1, random_state=7)`.
  - `gradient_boosting`: `HistGradientBoostingClassifier(class_weight="balanced", random_state=7)`.
- `regla_umbral_fijo(datos, umbral_monto) -> Series`: la idea original (monto por
  encima del percentil 95 **del entrenamiento**, o hora < 6). Antes el percentil se
  sacaba del tramo de prueba.
- `metricas(y, prediccion, score) -> dict`: precisión, recall, F1 y AUC-PR (con
  score continuo cuando existe; para la regla, la predicción binaria, como hoy).
- `elegir_modelo(modelos, validacion, features) -> nombre`: mejor AUC-PR en
  validación.
- `elegir_umbrales(y_validacion, score_validacion) -> (umbral_verificacion, umbral_bloqueo)`:
  barre la curva precisión-recall; bloqueo = mejor F1; verificación = mejor F2. Si
  el de verificación sale mayor que el de bloqueo, se igualan y se avisa.
- `recomendar(tipos_fraude, score_maximo, umbrales) -> str`: la regla
  determinista. `bloquear_acceso_cuenta` si el caso trae viaje imposible;
  `bloquear_tarjeta` si `score_maximo >= umbral_bloqueo`; si no,
  `verificar_cliente`. Gana el nivel más severo.
- `desviaciones(fila) -> list[dict]`: por cada señal, un registro con `senal`,
  `valor_observado`, `valor_referencia` y `descripcion` en español, armado con plantilla
  y cifras reales. Ejemplo: `{"senal": "monto", "valor_observado": 902.15,
  "valor_referencia": 64.10, "descripcion": "Monto 14,1 veces su promedio previo
  (64,10)"}`. Las señales se ordenan por cuánto se alejan de su referencia. El LLM
  citará estas descripciones; no redacta cifras propias.
- `construir_casos(prueba, umbrales, alertas_viaje, datos_completos) -> list[dict]`:
  marca las transacciones con `score >= umbral_verificacion` o con alerta de viaje
  imposible. Las agrupa por tarjeta en ventanas de 48 h (la ventana arranca en la
  primera marcada; la siguiente fuera de esas 48 h abre un caso nuevo) y arma cada
  caso con los campos de "Formato de datos".
- `guardar_salidas(casos, metricas, modelo, carpeta)`: escribe los cuatro archivos.

### `entrenar_modelo.py`

`main()` con `argparse` (`--fuente`, por defecto `sinteticos` para que el README
siga valiendo). Pasos: cargar → features → dividir → entrenar los tres → elegir →
umbrales → reportar en consola los cuatro (tres modelos + regla) lado a lado en
prueba → detectar viaje imposible en prueba → casos → guardar. Imprime al final
cuántos casos hay por nivel y dónde quedaron los archivos.

## Formato de datos

### Traducción de Sparkov a las columnas del proyecto

| Sparkov | Proyecto | Nota |
|---|---|---|
| `trans_num` | `id_transaccion` | |
| `cc_num` | `id_cuenta` | Como texto. Una tarjeta = un cliente en este dataset |
| `trans_date_trans_time` | `fecha_hora` | `hora` se extrae de aquí |
| `amt` | `monto` | USD |
| `category` | `categoria` | **Columna nueva**, documentar en `CLAUDE.md` |
| `merchant` | `comercio` | **Nueva**; se le quita el prefijo `fraud_` que trae el dataset en todos los comercios |
| `merch_lat`, `merch_long` | `latitud`, `longitud` | Dónde ocurrió la transacción (lo que usa viaje imposible) |
| `lat`, `long` | `latitud_domicilio`, `longitud_domicilio` | **Nuevas** |
| `city` | `ubicacion` | Ciudad del domicilio. Sparkov no trae la ciudad del comercio, así que viaje imposible compara coordenadas, no nombres |
| `is_fraud` | `es_fraude` | `tipo_fraude` = `uso_no_autorizado` si 1, `normal` si 0 |

Las columnas personales (`first`, `last`, `street`, `dob`, `job`, `gender`, `zip`,
`city_pop`) no se leen.

Ajuste necesario en `detectar_viaje_imposible.detectar()`: hoy solo compara pares
con `ubicacion` distinta. En Sparkov la ubicación es la del domicilio (siempre la
misma), así que no evaluaría nada. Se agrega un parámetro
`comparar_por="ubicacion"|"coordenadas"`: por defecto `"ubicacion"` (comportamiento
actual intacto) y `"coordenadas"` para Sparkov. La fórmula y los 900 km/h no
cambian.

### `casos_marcados.json`

Lista de casos. Cada uno:

```json
{
  "id_caso": "C-000123",
  "id_cuenta": "2703186189652095",
  "inicio_ventana": "2020-07-02 22:14:03",
  "fin_ventana": "2020-07-04 22:14:03",
  "tipos_fraude": ["uso_no_autorizado"],
  "score_maximo": 0.97,
  "nivel_recomendacion": "bloquear_tarjeta",
  "motivo_recomendacion": "Score 0,97 por encima del umbral de bloqueo 0,81",
  "perfil_previo": {"monto_promedio": 64.1, "monto_desviacion": 40.2,
                    "horas_habituales": [{"hora": 12, "porcentaje": 9.1}],
                    "categorias_habituales": [{"categoria": "grocery_pos", "porcentaje": 21.0}],
                    "transacciones_por_dia": 2.1, "sin_historial": false},
  "transacciones": [
    {"id_transaccion": "...", "fecha_hora": "...", "monto": 902.15,
     "categoria": "shopping_net", "comercio": "...", "score": 0.97,
     "viaje_imposible": false,
     "desviaciones": [{"senal": "monto", "valor_observado": 902.15,
                       "valor_referencia": 64.10,
                       "descripcion": "Monto 14,1 veces su promedio previo (64,10)"}]}
  ],
  "fraude_confirmado_dataset": 6
}
```

`fraude_confirmado_dataset` (transacciones del caso que el dataset etiqueta como
fraude) **no se le muestra al analista**. Sirve para validar y para armar la suite de
evaluación. Números con punto decimal en el JSON; la coma decimal solo aparece en
los textos de `descripcion`.

### `casos_marcados.csv`

Una fila por caso: `id_caso, id_cuenta, inicio_ventana, fin_ventana,
n_transacciones, monto_total, score_maximo, nivel_recomendacion, tipos_fraude,
senal_principal, fraude_confirmado_dataset`. Separador coma, UTF-8.

### `metricas_motor.json`

`fecha_corrida`, `fuente`, tamaños de cada tramo y su % de fraude, proporción del
submuestreo, por modelo y para la regla `{precision, recall, f1, auc_pr}` en
validación y en prueba, modelo elegido, umbrales, conteo de alertas de viaje
imposible y casos por nivel.

## Integración

- `detectar_viaje_imposible.py`: se agrega el parámetro `comparar_por`; su `main()`
  sigue funcionando igual sobre sintéticos.
- `generar_datos.py`: no se toca.
- La persistencia en Postgres (siguiente componente) leerá `casos_marcados.json`.
- `CLAUDE.md`: documentar las columnas nuevas (`categoria`, `comercio`,
  `latitud_domicilio`, `longitud_domicilio`, `tramo_origen`) y la regla de que las
  features de historial se calculan solo con transacciones previas.

## Manejo de errores

- Si faltan los CSV de la fuente pedida, el script avisa qué archivo falta y dónde
  ponerlo, y termina sin traza de Python.
- Tarjetas sin historial: `sin_historial = 1` y valores neutros; en el caso,
  `perfil_previo.sin_historial = true`.
- Desviación cero: piso de 1,0 en `monto_desv_previa`.
- Fechas duplicadas en una tarjeta: el orden se desempata por `id_transaccion`, para
  que sea reproducible.
- Validación sin fraude (puede pasar en sintéticos chicos): se avisa y se usa 0,5
  como umbral, dejando constancia en las métricas.
- Memoria: se leen solo las columnas usadas, con tipos compactos (`float32`,
  `category`). Si aun así no cabe, se documenta el muestreo; no se falla en silencio.

## Cómo se valida

`validar-fraude` debe comprobar:

1. Ausencia de filtración: para dos transacciones al azar, recalcular a mano
   `monto_promedio_previo` y `frecuencia_hora_previa` con solo las filas anteriores de
   la tarjeta y comparar.
2. Las fechas de los tramos no se solapan (entrenamiento < validación < prueba).
3. Precisión, recall, F1 y AUC-PR de los tres modelos y de la regla, lado a lado en
   prueba, y que el elegido supere a la regla en AUC-PR y F1.
4. Que ninguna feature por sí sola separe las clases casi perfectamente (AUC-PR de
   cada feature como score individual). Si `conteo_24h_previo` o `monto` lo hacen,
   discutir si es un rasgo real de las ráfagas de Sparkov o un artefacto del
   simulador.
5. Que cada caso traiga todos los campos y que las cifras de `descripcion`
   coincidan con `valor_observado` y `valor_referencia`.
6. Alertas de viaje imposible en Sparkov (falsas alarmas esperadas cerca de cero) y
   que el detector siga dando sus números de siempre sobre sintéticos.
7. Comparación con los números históricos de `decisiones.md`: si los sintéticos
   bajan al quitar la filtración, se reporta como corrección, no como regresión.

## Revisión 2026-10-21 — tras `validacion/motor-riesgo.md`

Decisiones tomadas con el equipo después de la primera validación:

- **Nivel a nivel de caso (hallazgo 2):** `bloquear_tarjeta` exige **2 o más
  transacciones del caso por encima del umbral de bloqueo** dentro de las 48 h. Un
  caso con una sola transacción sobre ese umbral baja a `verificar_cliente`. Ningún
  caso se descarta. `bloquear_acceso_cuenta` (viaje imposible) no cambia. El motivo
  se le explica al analista en una frase ("dos o más compras anómalas seguidas").
- **Orden de las razones (hallazgo 3), con las dos vías a la vez y sin tocar el
  modelo:**
  - *Contribución del modelo por oclusión:* para cada transacción marcada y cada
    señal, se reemplazan las features de esa señal por su mediana en las
    transacciones normales del entrenamiento y se mide cuánto baja el score
    (`contribucion_modelo` = score real − score con la señal en su valor típico).
    Es fiel al modelo en *ese* caso, no instala dependencias (sin SHAP) y solo cuesta
    unas miles de predicciones extra sobre las marcadas. No cambia el score ni las
    métricas.
  - *Rareza en percentiles:* el valor principal de cada señal se compara contra las
    transacciones normales del entrenamiento (`percentil_rareza`, 0–100, en la
    dirección de riesgo: monto alto, frecuencia baja, ráfaga alta…). Escala comparable
    entre señales y narrable: "más alto que el 99 % de las compras normales".
  - Cada desviación guarda los dos números y un `relevante` (contribución positiva y
    percentil ≥ 90, o contribución ≥ 0,05). Se ordenan por contribución;
    `senal_principal` es la de mayor contribución. El LLM solo cita las relevantes,
    pero el JSON conserva todas.
  - Grupos de features por señal: monto (`monto`, `z_monto`, `razon_monto`), hora
    (`hora`, `frecuencia_hora_previa`), ritmo_24h (`conteo_24h_previo`,
    `tasa_diaria_previa`), monto_24h (`monto_24h_previo`), categoria
    (`frecuencia_categoria_previa`), distancia (`distancia_domicilio_km`,
    `distancia_vs_habitual_km`), ubicacion (`frecuencia_ubicacion_previa`), historial
    (`sin_historial`).
  - Las medianas y las distribuciones de referencia se guardan en
    `modelo_riesgo.joblib` para que la vista del analista explique casos nuevos igual.
- **Artefacto "tarjeta nueva = fraude" (hallazgo 4):** `sin_historial` **se queda**
  como feature (un banco real sí trata con más cuidado las tarjetas nuevas), pero se
  documenta en `decisiones.md` y `metricas_motor.json` reporta también las métricas de
  prueba **sin** las filas sin historial, para no vender el rasgo del simulador como
  capacidad del modelo.
- **Viaje imposible en Sparkov (hallazgo 6):** se corrige la expectativa. No son
  "casi cero" falsas alarmas sino 14 153 en 879 tarjetas, porque el simulador ubica
  los comercios al azar a ~100 km del domicilio. Por eso solo se mide y no genera
  casos (decisión del equipo).
- Hallazgos 1 y 7 (ventana de 24 h y redacción) ya se corrigieron en
  `construir-fraude`: conversión de fechas independiente de la resolución, con una
  comprobación que falla si no cuadra, y la señal nueva `monto_24h` con su propio
  valor de referencia (gasto diario habitual).
