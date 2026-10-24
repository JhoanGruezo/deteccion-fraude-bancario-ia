# Informe del validador: proyecto de fraude bancario

**Corrida:** `auditoria/2026-10-24_1343/`
**Fecha de la validación:** 2026-10-24
**Alcance:** artefactos, agente, proveedores, suite, las cuatro cifras (lote `eval/resultados/lote_2026-10-21_2158.json`), motor de riesgo, condiciones de `CLAUDE.md`, requisitos y pendientes.
**Rúbrica:** `../material/momento2/momento2_rubrica.md`, validada contra el documento único `docs/decisiones.md` (no contra `docs/decisiones/semanaNN.md`).
**No se ejecutó** la app, ni las pruebas, ni `src/` ni `eval/`. No se hicieron peticiones a localhost:8000. No se abrió `docs/prueba-companero-jeison.txt` (ver alerta de seguridad).

## Resumen

- **Veredictos (secciones 1 a 8):** 64 CUMPLE, 7 NO CUMPLE, 6 NO VERIFICABLE. Pendientes (sección 9): 7 casillas correctas, 3 no verificables.
- **Las cuatro cifras recalculadas coinciden con las declaradas** en `docs/decisiones.md` §9 (tasa 94,7 %, costo mediano 0,001481 USD, latencia mediana 5,8 s y P90 17,1 s, TTFT 0,80 s, recuperación 100 %). Hay una cifra de tokens en §6 (10 993) que no se reproduce.
- **Alerta de seguridad, prioridad máxima:** `docs/prueba-companero-jeison.txt`, línea 42, contiene dos llaves de API reales (una de Anthropic y una de Google). Ese archivo está versionado en git, lo enlaza `README.md` línea 28 y el ZIP lo incluiría porque `docs/` está en la lista blanca. Hay que rotar ambas llaves y quitarlas del archivo. Nota: en mi primera búsqueda con `git grep` la salida mostró el contenido de esa línea en esta sesión. No lo escribí en ningún archivo ni lo reproduzco aquí; conviene considerar esas dos llaves como expuestas.
- **Contradicciones importantes:** (a) el agente tiene seis herramientas en el código y los documentos dicen cinco; (b) `validacion/motor-riesgo.md` describe una corrida anterior del motor (1 089 casos Sparkov, 89 casos sintéticos, recall 0,993) que ya no coincide con los datos ni con `docs/decisiones.md`; (c) la prueba del compañero, la verificación de la suite y el ZIP final siguen pendientes, lo que bloquea varios criterios de la rúbrica.

## 1. Artefactos de la entrega

| ID | Criterio | Veredicto | Evidencia | Comentario |
|---|---|---|---|---|
| 1.1 | `README.md` con contrato de arranque y modelo/proveedor justificados | CUMPLE | `README.md` 271 líneas, §2 arranque, §3 modelo y proveedor con medición | |
| 1.2 | `docker-compose.yml` | CUMPLE | `docker-compose.yml` 47 líneas, servicios `db` y `app` | |
| 1.3 | `run.sh` | CUMPLE | `run.sh`: crea `.env`, avisa sin llaves, espera `/api/salud` | El permiso de ejecución no lo pude revisar en Windows |
| 1.4 | `.env.example` sin llaves | CUMPLE | `.env.example:9` y `:11` con valor vacío; búsqueda de patrones de llave sin coincidencias en ese archivo | |
| 1.5 | `docs/decisiones.md` | CUMPLE | 320 líneas, secciones 1 a 12 | |
| 1.6 | `eval/` con casos y resultados | CUMPLE | `eval/casos_dorados.json` (8 casos), `eval/resultados/` (2 suites, 2 lotes con su `.md`) | |
| 1.7 | ZIP reproducible (entregable) | NO VERIFICABLE | No hay ZIP en el árbol; `scripts/empaquetar_entrega.py` existe | Ver 7.2 y la alerta de la sección 0 |

## 2. Agente

| ID | Criterio | Veredicto | Evidencia | Comentario |
|---|---|---|---|---|
| 2.1 | Límite de iteraciones | CUMPLE | `app/config.py:64` (6); `app/agente/bucle.py:185` (`limite_iteraciones`) | |
| 2.2 | Presupuesto de tokens | CUMPLE | `app/config.py:65` (40 000); `app/agente/bucle.py:191` | |
| 2.3 | Timeout por llamada al modelo y por herramienta | CUMPLE | `app/config.py:66-67`; `bucle.py:139-142` (`futuro.result(timeout=...)`); `bucle.py:225` (`timeout`); `app/proveedores/base.py:120-123` | |
| 2.4 | Confirmación humana para toda escritura | CUMPLE | `herramientas.py:217` llama a `crear_propuesta`; `app/db/repositorio.py:424-435` inserta en `propuestas_decision`; la decisión solo se escribe en `resolver_propuesta` | |
| 2.5 | Número de herramientas coherente con los documentos | NO CUMPLE | `app/agente/herramientas.py:245-268` registra **seis** herramientas (incluye `declarar_fuera_de_alcance`). `docs/decisiones.md:71-74` y `:141` dicen **cinco** ("las cinco de la sección 3"). Lo mismo en `docs/decisiones.md` §11 (2026-10-21.4), que sí menciona la sexta | Ver contradicción C2 |
| 2.6 | Descripciones de herramientas escritas como prompt e iteradas | CUMPLE | `app/agente/prompts.py`; `docs/decisiones.md` §11 con cuatro versiones y motivo de cada cambio | |

## 3. Proveedores

| ID | Criterio | Veredicto | Evidencia | Comentario |
|---|---|---|---|---|
| 3.1 | Capa aislada en `app/proveedores/` | CUMPLE | Clientes en `app/proveedores/claude.py`, `gemini.py`, `base.py`, `cascada.py`. Fuera de esa carpeta solo aparecen `config.py`, comentarios en `bucle.py:17` y `contrato.py:11`, y `app/api/rutas_sistema.py:63-64` (etiquetas y estado de los proveedores) | Salvedad menor: `rutas_sistema.py` conoce los nombres de proveedor |
| 3.2 | Modelo principal y de respaldo coinciden con §4 y con `config.py` | CUMPLE | `app/config.py:39` (`claude-haiku-5-5`), `:37` (`gemini-3.1-flash-lite`), `:43` (`claude,gemini`); `docs/decisiones.md` §4; `README.md` §3 | |
| 3.3 | Cambio de proveedor en vivo demostrado | NO VERIFICABLE | El lote muestra la conmutación a Gemini en L16 y L17 (`eval/resultados/lote_2026-10-21_2158.json`) | No se ejecutó la app en esta corrida |

## 4. Suite de evaluación

| ID | Criterio | Veredicto | Evidencia | Comentario |
|---|---|---|---|---|
| 4.1 | Número de casos | CUMPLE | `eval/casos_dorados.json`: 8 casos (D1 a D6 explicación, D7 y D8 rechazo) | |
| 4.2 | Al menos uno de rechazo | CUMPLE | D7 y D8 con `tipo: rechazo`; `eval/resultados/suite_2026-10-21_2157.json`: ambos con `exito: true` y `motivo_fin: rechazo` | |
| 4.3 | Casos con `verificado_por` lleno | NO CUMPLE | 0 de 8 casos con `verificado_por` (todos `null`); el propio JSON de la suite dice `estado_suite: "pendiente de verificación humana"` | Consistente con `docs/decisiones.md` §9 y `docs/pendientes-y-momento3.md` §1 ítem 1, pero es un criterio de la rúbrica ("casos verificados") |

## 5. Las cuatro cifras (lote `lote_2026-10-21_2158.json`, recalculado con `json` y `statistics`)

| Cifra | Declarada (`docs/decisiones.md` §9) | Recalculada desde el JSON | Veredicto | Método verificado |
|---|---|---|---|---|
| Tasa de éxito | 94,7 % (18 de 19) | 18 de 19 = 0,94737 | CUMPLE | `exito == True` por tarea. Sin caché: 12 de 13 = 92,3 %, correcto |
| Costo por tarea (mediana) | 0,001481 USD | 0,001481 (13 tareas sin caché) | CUMPLE | Sin fallas forzadas: 0,001421 (9 tareas), correcto. Total del lote 0,022201 |
| Latencia | mediana 5,8 s; P90 17,1 s | mediana 5 764 ms; P90 17 106,4 ms (interpolación lineal, igual que `eval/correr_lote.py`) | CUMPLE | Sin fallas forzadas: 4 592 ms, correcto. Con el P90 por rango más cercano daría 17 866 ms; el método declarado es interpolación |
| TTFT mediano | 0,80 s | 795,5 ms (12 tareas con TTFT) | CUMPLE | |
| Recuperación | 100 % (4 de 4) | 4 de 4 con `con_fallo` y `recuperada` | CUMPLE | |
| Ahorro por caché | 26 ms vs 5,2 s (99,5 %), 0 USD vs 0,0016 USD | 26,0 ms; 5 202,5 ms; reducción 0,9950; costo frío mediano 0,0016475 | CUMPLE | |
| Iteraciones (§6) | mediana 2 | mediana 2 (sin caché y total) | CUMPLE | |
| Tokens por tarea (§6) | "la mediana del lote fue 10 993 tokens por tarea" | 11 059 (13 tareas sin caché); 9 620 (19 tareas). Ningún cálculo da 10 993. El lote 2132 da 10 710 | NO CUMPLE | Cifra no reproducible. Ver C4 |
| Contratos inválidos (§9 y §11) | "Ninguna tarea tuvo contrato inválido en esta corrida"; "de 3 a 0" | La traza de L18 (falla `json` forzada) contiene un evento `contrato_invalido` (`falta el campo lo_que_no_se_sabe...`), reparado en el reintento | NO CUMPLE | Afirmación imprecisa. Ver C5 |

Las cuatro cifras de la línea base coinciden con el JSON. El detalle del recálculo está en `logs/validador-lote-cifras.txt`.

## 6. Motor de riesgo

| ID | Criterio | Veredicto | Evidencia | Comentario |
|---|---|---|---|---|
| 6.1 | Precisión, recall, F1 y AUC-PR de todos los modelos y de la regla | CUMPLE | `datos/salidas_sparkov/metricas_motor.json` y `datos/salidas_sinteticos/metricas_motor.json`, bloques `validacion` y `prueba` | |
| 6.2 | Las cifras coinciden con `docs/decisiones.md` §8 | CUMPLE | Sparkov prueba: regla 0,014/0,845/0,028/0,012; RL 0,340/0,606/0,436/0,277; RF 0,812/0,779/0,796/0,863; HGB 0,786/0,838/0,811/0,884; sin tarjetas nuevas 0,773/0,832/0,801/0,875; 287 casos, 249/38, 213 de 218 | Todas coinciden con el redondeo declarado. Sintéticos "AUC-PR 0,999" = 0,9985 |
| 6.3 | Partición temporal | CUMPLE | `src/motor_riesgo.py:67-79` (`dividir_temporal`); Sparkov usa `tramo_origen`; sintéticos usa cuantiles de `fecha_hora` | |
| 6.4 | Viaje imposible como código determinista | CUMPLE | `src/detectar_viaje_imposible.py:25-63` (Haversine + 900 km/h, sin modelo) | |
| 6.5 | Número de alertas de viaje imposible en Sparkov reportado | CUMPLE | `validacion/motor-riesgo.md:21` y `:142`: 14 153 alertas en 879 tarjetas; `metricas_motor.json` `alertas_en_prueba: 14153` | Está en `validacion/`, no en `docs/decisiones.md` §8 |
| 6.6 | Recalculo del detector sobre sintéticos | CUMPLE | Recalculado con `csv` y `math` sobre `datos/transacciones.csv`: 145 marcadas, 145 verdaderas, 150 reales, precisión 1,000, recall 0,967, 0 FP, 5 FN. Coincide con `docs/decisiones.md:208` | Coincide con la bitácora, no con `validacion/motor-riesgo.md` (ver C3). Salida en `logs/validador-viaje-imposible.txt` |

## 7. Condiciones fijas de `CLAUDE.md`

| ID | Condición | Veredicto | Evidencia | Comentario |
|---|---|---|---|---|
| 7.1 | Todo en español (archivos, funciones, variables, columnas, mensajes) | NO CUMPLE | Identificadores en inglés: `random_forest` y `gradient_boosting` en `src/motor_riesgo.py:97` y `:101`, en las claves de `metricas_motor.json` y en `docs/decisiones.md` §8; `features` en `src/entrenar_modelo.py:75` y `metricas_motor.json` | Incumplimiento leve. Ver C7 |
| 7.2 | `pandas` y `scikit-learn` permitidos | CUMPLE | `src/motor_riesgo.py` | |
| 7.3 | Ninguna regla de un solo umbral como detector principal; ninguna columna separa las clases casi perfectamente | CUMPLE | La regla de umbral es solo la línea base. AUC-PR por feature en prueba: máximo 0,152 (`monto_24h_previo`, Sparkov) y 0,643 (`monto_24h_previo`, sintéticos) | |
| 7.4 | Toda comparación reporta precisión, recall, F1 y AUC-PR | CUMPLE | `metricas_motor.json` y `docs/decisiones.md` §8 | |
| 7.5 | Viaje imposible como código determinista, no modelo | CUMPLE | `src/detectar_viaje_imposible.py` | |
| 7.6 | Perfil solo con transacciones anteriores; partición temporal | CUMPLE | `src/perfil_cuenta.py:69-70` (suma acumulada menos la fila actual), `:36-56` (ventana de 24 h previa). Recalculo de `monto_24h` en 3 transacciones de sintéticos: coincide exactamente (`logs/validador-features.txt`) | Sparkov no recalculado a mano |
| 7.7 | `entrenar_modelo.py` no lee `monto_promedio_cuenta` y excluye `viaje_imposible` | CUMPLE | Sin referencias a `monto_promedio_cuenta` en `src/entrenar_modelo.py` ni `src/motor_riesgo.py`; `src/entrenar_modelo.py:46-49` y `:77-79` (`solo_uso_no_autorizado`) | |
| 7.8 | `generar_datos.py`: `tiempo_actual` igual al último `fecha_hora` escrito | CUMPLE | `src/generar_datos.py:105` (comentario), `:141`, `:164`, `:192` | Revisión por lectura de las ramas, no exhaustiva |
| 7.9 | Nombres de columnas del CSV | CUMPLE | Cabecera de `datos/transacciones.csv`: `id_transaccion, id_cuenta, monto, fecha_hora, hora, ubicacion, latitud, longitud, monto_promedio_cuenta, ubicacion_habitual_cuenta, tipo_fraude, es_fraude` | |
| 7.10 | Rutas relativas a `src/` | CUMPLE | `src/cargar_datos.py:15-17`, `src/generar_datos.py:25`, `src/detectar_viaje_imposible.py:21` | |

## 8. Requisitos (`requisitos/`, al menos tres criterios por archivo)

### 8.1 `requisitos/agente.md`

| ID | Criterio | Veredicto | Evidencia | Comentario |
|---|---|---|---|---|
| R-A1 | Herramientas propias, con descripción tipo prompt | CUMPLE | Seis en `herramientas.py` (incluye las cinco pedidas) | Ver 2.5 |
| R-A2 | Cuatro límites activos | CUMPLE | Ver 2.1 a 2.4 | |
| R-A3 | Proveedor desacoplado y ordenable con `ORDEN_PROVEEDORES` | CUMPLE | `app/config.py:43`; `app/proveedores/cascada.py` | |
| R-A4 | Fallos: 429 con backoff 1-2-4 s y conmutación; timeout; JSON roto; plantilla | CUMPLE | `app/config.py:73` (`1,2,4`); `base.py:57` (`TIPOS_REINTENTABLES`); lote 2158 L16 a L19 | |
| R-A5 | Anclaje a la evidencia (cifras y señales) | CUMPLE | `app/agente/contrato.py:17` y `:37` (cifras con 3 o más cifras significativas) | |
| R-A6 | No ejecuta acciones | CUMPLE | Ver 2.4 | |
| R-A7 | Rechazo con herramienta `declarar_fuera_de_alcance` | CUMPLE | `herramientas.py:227-234`; suite D7 y D8 | |
| R-A8 | Español sin jerga de ML para el analista | CUMPLE | `app/agente/prompts.py:40` prohíbe "feature" y "AUC" | Prompt verificado; la salida real no revisada |

### 8.2 `requisitos/motor-riesgo.md`

| ID | Criterio | Veredicto | Evidencia | Comentario |
|---|---|---|---|---|
| R-M1 | Ninguna feature usa la transacción actual ni las posteriores | CUMPLE | Recalculo en 3 transacciones de sintéticos (`logs/validador-features.txt`); código en `perfil_cuenta.py` | Sparkov no recalculado a mano |
| R-M2 | Partición temporal | CUMPLE | Ver 6.3 | |
| R-M3 | Umbrales en validación: bloqueo por F1, verificación priorizando recall | CUMPLE | `src/motor_riesgo.py:131-156` (F1 para bloqueo, F2 para verificación) | |
| R-M4 | En Sparkov el modelo supera a la regla en AUC-PR y F1 | CUMPLE | 0,884 frente a 0,012 (AUC-PR); 0,811 frente a 0,028 (F1) | |
| R-M5 | Una feature que separa casi perfecto se reporta como alerta | CUMPLE | Ver 7.3 | |
| R-M6 | Cada caso trae todos los campos de la salida 3 | CUMPLE | `datos/salidas_*/casos_marcados.json`: 287 y 52 casos; todas las transacciones tienen `desviaciones`; todos tienen nivel y motivo | |
| R-M7 | Viaje imposible en Sparkov corrido y reportado | CUMPLE | Ver 6.5 | |
| R-M8 | El motor corre sobre `datos/transacciones.csv` sin cambios de código | NO VERIFICABLE | No se volvió a correr | El JSON sintético es de 2026-10-21 20:25 |
| R-M9 | Tiempo razonable | CUMPLE | `segundos_corrida`: 56,3 (Sparkov), 3,0 (sintéticos) | |

### 8.3 `requisitos/evaluacion-entrega.md`

| ID | Criterio | Veredicto | Evidencia | Comentario |
|---|---|---|---|---|
| R-E1 | ZIP en carpeta limpia, arranque en menos de 5 min (medido) | NO VERIFICABLE | `docs/decisiones.md` §12 reporta 24 s en la máquina de desarrollo, con imágenes ya descargadas | Falta la prueba en máquina limpia (pendiente 5 de `docs/pendientes-y-momento3.md`) |
| R-E2 | ZIP sin llaves reales | NO CUMPLE | `docs/prueba-companero-jeison.txt:42` contiene dos llaves reales. `scripts/empaquetar_entrega.py:40` incluye `docs` en `CARPETAS_PERMITIDAS`, así que el escáner abortaría. No hay ZIP generado | Alerta de seguridad. No se copió ningún valor |
| R-E3 | Suite con un comando y cuatro cifras con fecha | CUMPLE | `eval/correr_lote.py` produce las cuatro cifras; `docs/decisiones.md` §9 sale de `lote_2026-10-21_2158` | La suite sola reporta éxito y latencia, no las cuatro |
| R-E4 | Al menos un rechazo y recuperación con fallos forzados | CUMPLE | D7 y D8; L16 a L19 | |
| R-E5 | `docs/decisiones.md` explica no usar RAG con la tabla de la semana 8 | CUMPLE | `docs/decisiones.md` §3, tabla de cinco ejes | |

### 8.4 `requisitos/persistencia.md`

| ID | Criterio | Veredicto | Evidencia | Comentario |
|---|---|---|---|---|
| R-P1 | `docker compose up` deja la base lista sin pasos manuales | NO VERIFICABLE | `app/db/migrar.py:155-171` (esquema y semilla al arrancar); no se levantó | |
| R-P2 | Número de casos y transacciones igual que los JSON del motor | CUMPLE | `semilla/casos_sparkov.json` 287 casos, `semilla/casos_sinteticos.json` 52 | La carga a Postgres no se verificó |
| R-P3 | Desviaciones guardadas idénticas a las del motor | CUMPLE | Comparación JSON a JSON de los 339 casos (emparejados por tarjeta y ventana): todos idénticos en transacciones, desviaciones, score y nivel | El `id_caso` cambia de `C-` a `SPK-`/`SIN-` a propósito (`scripts/generar_semilla.py:55-63`). A nivel de base no se verificó |
| R-P4 | Volver a levantar no duplica datos | CUMPLE | `app/db/migrar.py:162-163`: solo carga si `casos` está vacía; candado con `pg_advisory_xact_lock` | Por código |
| R-P5 | La semilla cabe en el ZIP | CUMPLE | `semilla/`: 4,9 MB en total | |

### 8.5 `requisitos/vista-analista.md`

| ID | Criterio | Veredicto | Evidencia | Comentario |
|---|---|---|---|---|
| R-V1 | Prueba del compañero con tres tareas, documentada | NO CUMPLE | `docs/decisiones.md` §10: "PENDIENTE (equipo)" | |
| R-V2 | Explicación por `text/event-stream` real con TTFT medido | CUMPLE | `app/api/sse.py`; TTFT mediano 795,5 ms en el lote | DevTools no revisado |
| R-V3 | Los tres fallos forzados se ven manejados, sin trazas de Python | CUMPLE | `app/agente/servicio.py:51-53` (mensajes en español); lote L16 a L19 | Pantalla no revisada |
| R-V4 | Ninguna decisión sin confirmación explícita | CUMPLE | Ver 2.4 | |
| R-V5 | La interfaz no expone `fraude_confirmado_dataset` ni el número completo de la tarjeta | CUMPLE | `app/api/sse.py:41` (`CAMPOS_PROHIBIDOS`); `app/db/repositorio.py:230` y `:235`; ninguna referencia en `app/web/` | |
| R-V6 | Se levanta con `docker compose up` o `run.sh` sin pasos manuales | NO VERIFICABLE | No se levantó | |

## 9. Pendientes (`docs/pendientes-y-momento3.md` §1)

| ID | Ítem | Veredicto | Evidencia | Comentario |
|---|---|---|---|---|
| P-1 | Verificar los 8 casos y firmar `verificado_por` | CUMPLE (casilla correcta) | 0 de 8 firmados | Pendiente real. La casilla `[ ]` es correcta |
| P-2 | `docs/verificacion-jeison.md` | CUMPLE (casilla correcta) | El archivo no existe | Pendiente real. El README y el pendiente lo citan como si existiera en el futuro; ver C8 |
| P-3 | Prueba del compañero | CUMPLE (casilla correcta) | `docs/decisiones.md` §10 "PENDIENTE" | |
| P-4 | Corregir y volver a medir | CUMPLE (casilla correcta) | Sin evidencia | |
| P-5 | Arranque desde ZIP en la máquina de Jeison | CUMPLE (casilla correcta) | `docs/decisiones.md` §12 "PENDIENTE" | |
| P-6 | Confirmar tarifas en páginas oficiales | CUMPLE (casilla correcta) | `app/config.py:46-47` y `docs/decisiones.md` §4 citan agregadores | |
| P-7 | Estudiar la guía de estudio | NO VERIFICABLE | `docs/guia-de-estudio.md` existe (16 KB) | Depende de las personas |
| P-8 | Guion ensayado y plan B con video | NO VERIFICABLE | `docs/presentaciones/guion-sustentacion-jhoan.md` y `guion-sustentacion-jeison.md` existen; no hay video de respaldo en el repositorio | |
| P-9 | ZIP final regenerado | CUMPLE (casilla correcta) | No hay ZIP | |
| P-10 | Agregar a Jeison como colaborador | NO VERIFICABLE | Requiere GitHub | |

## 10. Contradicciones entre documentos y código

| ID | Gravedad | Ubicación A | Ubicación B | Descripción |
|---|---|---|---|---|
| C1 | Crítica | `docs/prueba-companero-jeison.txt:42` (versionado; enlazado desde `README.md:28`) | `scripts/empaquetar_entrega.py:13-57` (el escáner promete abortar) | Dos llaves de API reales en un archivo de `docs/`. El README lo presenta como lista de verificación pública y el ZIP lo incluiría. Rotar las llaves, quitar el valor del archivo y revisar `git log` |
| C2 | Alta | `docs/decisiones.md:71-74` y `:141` ("las cinco de la sección 3") | `app/agente/herramientas.py:245-268` (seis herramientas) y `docs/decisiones.md:288` (menciona `declarar_fuera_de_alcance`) | El número de herramientas es cinco en un párrafo y seis en otro de la misma bitácora. La lista de §3 omite la sexta |
| C3 | Alta | `validacion/motor-riesgo.md:16`, `:20-23`, `:139-140`, `:421-422` (1 089 casos Sparkov; 89 casos sintéticos; viaje imposible 148 de 149 con recall 0,993; 23 alertas en prueba) | `docs/decisiones.md:204-209` y `:208` (287 casos; 52 sintéticos; recall 0,967), `datos/salidas_sinteticos/metricas_motor.json` (`alertas_en_prueba: 33`), `datos/salidas_sparkov/casos_marcados.json` (287) | La validación mezcla dos corridas. Sus primeras secciones describen la corrida anterior, que usaba una regla distinta de casos. Las secciones de la regla de dos transacciones (líneas 487 y siguientes) sí dan 287. Además, `validacion/motor-riesgo.md:140` dice "igual que en `decisiones.md`", pero la bitácora ya tiene 0,967 |
| C4 | Media | `docs/decisiones.md:150` ("mediana del lote fue 10 993 tokens") | `eval/resultados/lote_2026-10-21_2158.json` (11 059 sin caché; 9 620 todas) | Cifra no reproducible |
| C5 | Media | `docs/decisiones.md:225` y `:292` ("Ninguna tarea tuvo contrato inválido en esta corrida"; "de 3 a 0") | Traza de L18 en `lote_2026-10-21_2158.json` (evento `contrato_invalido`) | La afirmación se cumple solo si se cuentan los contratos que no se repararon. Conviene decir "0 contratos inválidos sin reparar" |
| C6 | Media | `requisitos/agente.md:84-85` ("caso de una sola transacción sobre el umbral: `verificar_cliente`") | `docs/decisiones.md:204` ("una compra aislada no abre caso"); datos: los 38 `verificar_cliente` de Sparkov tienen 2 o 3 transacciones | El requisito quedó anterior a la regla de dos transacciones. Es un documento de requisitos, pero hay que actualizarlo o marcarlo como superado |
| C7 | Baja | `CLAUDE.md`: "todo en español" | `src/motor_riesgo.py:97`, `:101`; `metricas_motor.json`; `src/entrenar_modelo.py:75` | Identificadores en inglés. Dato de la condición 1 |
| C8 | Baja | `docs/pendientes-y-momento3.md` §1 ítem 2 (`docs/verificacion-jeison.md`) | Ese archivo no existe | Referencia a un entregable que aún no existe. Está bien como pendiente, pero conviene marcarlo |
| C9 | Baja | `README.md:28` (enlace a `docs/prueba-companero-jeison.txt` como "lista de verificación") | `docs/prueba-companero-jeison.txt:42` | Se relaciona con C1. El enlace expone el archivo en el README público |

## 11. Lo que no pude verificar y por qué

- **Ejecución de la app y de las pruebas**: prohibido por la consigna. Quedan sin verificar: el arranque con Docker (R-P1, R-V6, R-E1), la conmutación en vivo (3.3), la salida real del agente en español (R-A8), la pantalla con los fallos forzados (R-V3) y el comportamiento de DevTools (R-V2).
- **ZIP**: no existe en el árbol. Ni su tamaño ni sus llaves se verificaron (1.7, R-E2 por inspección del origen).
- **Recalculo de Sparkov**: no recalculé a mano ninguna feature sobre `fraudTrain.csv` (R-M1 y 7.6 se verificaron solo en sintéticos). El archivo no se tocó.
- **Base de datos**: la semilla se comparó a nivel de JSON, no en Postgres (R-P3).
- **Tarifas**: no consulté las páginas oficiales de los proveedores.
- **Rúbrica**: se usó el documento único `docs/decisiones.md` como pidió la consigna. La copia de `material/` menciona `docs/decisiones/semana08.md` y `semana10.md`, que ya no existen.
- **Lotes más recientes**: no se usaron, como se pidió. Esto incluye el lote que otro agente pudo estar escribiendo.

## 12. Conteo de veredictos

Conteo sobre las tablas de las secciones 1 a 8 (artefactos, agente, proveedores, suite, cifras, motor, `CLAUDE.md` y requisitos), sin contar la sección 9:

- **CUMPLE:** 64
- **NO CUMPLE:** 7 (2.5, 4.3, cifra de tokens de §6, afirmación de contratos inválidos, 7.1, R-E2, R-V1)
- **NO VERIFICABLE:** 6 (1.7, 3.3, R-M8, R-E1, R-P1, R-V6)

La sección 9 (pendientes) se evalúa aparte: 7 casillas `[ ]` coinciden con el estado real y 3 ítems (P-7, P-8, P-10) no son verificables.

## Notas de método

- Recalculo de cifras: `logs/validador-lote-cifras.txt` (script `json` y `statistics`, sin pandas).
- Detector de viaje imposible recalculado con `csv` y `math`: `logs/validador-viaje-imposible.txt`.
- Recalculo de features previas: `logs/validador-features.txt`.
- Ningún valor de llave se copió en este informe ni en los logs.
