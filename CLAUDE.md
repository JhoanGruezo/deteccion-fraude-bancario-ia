# Detección de fraude bancario

## Qué es esto

Proyecto de curso (no un reto semanal): detección de fraude transaccional bancario.
El contexto completo — qué tipo de fraude, por qué hace falta un modelo y dónde va
cada componente — está en `decisiones.md`. Léelo antes de tocar código nuevo: cambiar
el enfoque sin actualizar ese documento deja la justificación del proyecto
desactualizada, y esa justificación es la parte que el profesor va a revisar primero.

## Condiciones fijas (no se negocian)

1. Todo en español: nombres de archivos, funciones, variables, columnas de datos,
   mensajes impresos.
2. `pandas` y `scikit-learn` sí están permitidos aquí (a diferencia de los retos
   semanales de CRUD, este proyecto necesita un pipeline de ML real).
3. Ninguna regla de un solo umbral global se presenta como si fuera el detector
   principal — si alguna vez una sola columna separa las clases casi perfectamente
   en `entrenar_modelo.py`, es una señal de que los datos sintéticos quedaron poco
   realistas (ver el caso ya corregido en el historial: la ubicación no puede ser
   un predictor perfecto por sí sola, porque en la vida real la gente viaja).
4. Toda comparación de desempeño reporta precisión, recall, F1 y AUC-PR — nunca
   solo accuracy, porque el fraude es una clase minoritaria y accuracy es engañoso.
5. El detector de viaje imposible (distancia/tiempo entre transacciones) se
   implementa como código determinista, no como modelo — está documentado en
   `decisiones.md` por qué esa pieza específica no necesita IA.

## Convenciones de código

- **Nombres de columnas del CSV**: `id_transaccion`, `id_cuenta`, `monto`,
  `fecha_hora` (timestamp completo `AAAA-MM-DD HH:MM`, necesario para calcular
  tiempo transcurrido entre transacciones), `hora` (entero 0-23, extraído de
  `fecha_hora`, se mantiene por compatibilidad con las features del modelo),
  `ubicacion`, `latitud`, `longitud` (coordenadas de la ciudad de `ubicacion`),
  `monto_promedio_cuenta`, `ubicacion_habitual_cuenta`, `tipo_fraude` (`"normal"`,
  `"uso_no_autorizado"` o `"viaje_imposible"`), `es_fraude` (0/1, derivado de
  `tipo_fraude`). Columnas que solo trae Sparkov (`src/cargar_datos.py` las
  traduce desde `fraudTrain.csv`/`fraudTest.csv`): `categoria`, `comercio`,
  `latitud_domicilio`, `longitud_domicilio` (domicilio del cliente; `latitud` y
  `longitud` son las del comercio), `tramo_origen` (`"entrenamiento"`/`"prueba"`); en
  Sparkov `ubicacion` es la ciudad del domicilio, no la de la transacción. Si se
  agrega una columna nueva, documentarla aquí.
- **Regla de oro del perfil (desde 2026-10-21):** toda feature de historial usa
  solo transacciones *anteriores* de la misma tarjeta (`src/perfil_cuenta.py`), y la
  partición es temporal (`motor_riesgo.dividir_temporal`), nunca al azar. La
  versión anterior calculaba el perfil con todas las filas y eso era filtración.
- **Motor de riesgo** (`src/cargar_datos.py`, `src/perfil_cuenta.py`,
  `src/motor_riesgo.py`, punto de entrada `src/entrenar_modelo.py --fuente
  sinteticos|sparkov`): compara regresión logística, Random Forest y
  HistGradientBoosting contra la regla de umbral fijo y escribe en
  `datos/salidas_<fuente>/` los casos (`casos_marcados.json`/`.csv`), las métricas
  con fecha (`metricas_motor.json`) y el modelo (`modelo_riesgo.joblib`). Diseño
  completo en `diseno/motor-riesgo.md`.
- **`generar_datos.py`**: la generación es cronológica por cuenta —
  `generar_transacciones_cuenta` mantiene `tiempo_actual` como el `fecha_hora`
  exacto de la última fila escrita para esa cuenta (nunca una fecha base que se
  desvíe de lo realmente guardado; ver el comentario en esa función sobre por qué
  eso rompió el detector de viaje imposible una vez). Cualquier patrón de fraude o
  de ruido nuevo se agrega dentro de esa función, siguiendo el mismo criterio: debe
  declarar qué combinación de señales usa y por qué no es trivialmente separable
  por una regla de un solo umbral.
- **`entrenar_modelo.py`**: las features derivadas de historial de cuenta se
  calculan con `groupby` sobre los datos mismos (no se leen columnas que vengan del
  generador como `monto_promedio_cuenta`, porque eso sería hacer trampa: un sistema
  real no conoce el promedio "verdadero", solo puede estimarlo de las transacciones
  que ha visto). Esto ya está resuelto en `construir_perfil_por_cuenta`. Este script
  excluye explícitamente las filas con `tipo_fraude == "viaje_imposible"`: ese tipo
  no es el patrón que estas features buscan, lo cubre el detector determinista.
- **`detectar_viaje_imposible.py`**: código determinista, no modelo (ver
  `decisiones.md`, "Prueba de necesidad"). Calcula distancia entre coordenadas con
  la fórmula de Haversine y la compara contra el tiempo transcurrido entre
  transacciones consecutivas de una misma cuenta; si la velocidad implícita supera
  `VELOCIDAD_MAXIMA_PLAUSIBLE_KMH` (900 km/h, velocidad de crucero comercial), lo
  marca. No usar un modelo aquí — los seis ejes ya lo descartaron.
- **Rutas**: relativas a `src/` (`../datos/...`), porque los scripts se corren desde
  ahí. Si se agrega un script en otra carpeta, ajustar las rutas, no mover los datos.

## Qué falta (ver "Próximos pasos" en decisiones.md)

- ~~Validar contra un dataset de fraude real~~: hecho con Sparkov (`fraudTrain.csv` /
  `fraudTest.csv`), ver "Resultado del motor sobre Sparkov" en `decisiones.md`.
- La **vista del analista ya está construida** en `app/` (no en `interfaz/` ni con
  Streamlit: se cambió a FastAPI + SSE real + frontend propio + Postgres en
  `docker-compose`, ver `decisiones.md` 2026-10-21 (2)). Capas: `app/db/` (única
  puerta a Postgres), `app/agente/` (bucle, herramientas, contrato, plantilla,
  `riesgo_en_palabras.py`), `app/proveedores/` (Claude Haiku 5.5 principal, Gemini
  3.1 Flash-Lite de respaldo, ver 2026-10-21 (3)), `app/api/` y `app/web/`. Pruebas en
  `app/pruebas/`; validación en `validacion/app-analista.md`.
- `app/` va separada de `src/` (que se queda dedicada al motor de riesgo: ML clásico
  + el detector determinista) para no mezclar ese pipeline con el código que llama al
  LLM.
- El **nivel de riesgo en palabras** de cada explicación lo arma el código
  (`app/agente/riesgo_en_palabras.py`), nunca el LLM: no volver a pedírselo al modelo.
- Regla de trazabilidad para cualquier explicación del agente: solo puede citar el
  score y las desviaciones guardadas del caso (obtenidas vía sus herramientas),
  nunca redactar causas que no estén en esos datos.
