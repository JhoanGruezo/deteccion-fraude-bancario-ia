# Informe del jefe: corrida 2026-10-24_1343

**Fecha:** 2026-10-24 · **Auditor:** agente `jefe-fraude` · **Insumos:** `probador.md` (Sonnet),
`validador.md` (Haiku), `logs/`, `eval/resultados/*_2026-10-24_*`, línea base
`lote_2026-10-21_2158.json` y `suite_2026-10-21_2157.json`, código y git del proyecto.
No se levantó, reinició ni reconstruyó Docker, y no se volvió a correr la suite ni el lote.

## 1. Veredicto

**No listo para sustentar (hoy).** El código está completo y la línea base del 21 de
octubre se sostiene contra su JSON, pero el proveedor principal no autentica: la variable
`ANTHROPIC_API_KEY` del contenedor no tiene formato de llave de Anthropic, así que toda
tarea cae a Gemini y hoy la app no puede mostrar en vivo las cifras que el equipo va a
afirmar (94,7 %, 5,8 s). A eso se suma un riesgo crítico de filtración (llaves reales en
la copia de trabajo de un archivo versionado y enlazado desde el README de un repositorio
público) y tres criterios de la rúbrica todavía abiertos (prueba del compañero, suite
verificada a mano y ZIP final al día). Todo se puede cerrar antes del 31 de octubre; las
condiciones están en la tabla de la sección 3.

## 2. Qué promete el proyecto

En la sustentación el equipo va a afirmar que un agente propio (bucle sin framework, seis
funciones de herramienta registradas aunque el documento diga cinco) explica cada caso
con cifras rastreables y nunca decide solo; que tiene los cuatro límites (6 iteraciones,
40 000 tokens, 25 s por llamada al modelo y 5 s por herramienta, confirmación humana);
que la capa de proveedor está aislada, con Claude Haiku 5.5 de principal, Gemini 3.1
Flash-Lite de respaldo y una plantilla sin red como último escalón; que no usa RAG y lo
justifica con la tabla de la semana 8; y que la línea base del 2026-10-21 21:58 dio
**94,7 % de éxito (18/19), 0,001481 USD de costo mediano, latencia mediana de 5,8 s con
P90 de 17,1 s y TTFT de 0,80 s, y 100 % de recuperación (4/4 fallas forzadas)**, con la
suite dorada en 8 de 8 y dos rechazos resueltos con `declarar_fuera_de_alcance`. En el
motor promete HistGradientBoosting con AUC-PR 0,884 en Sparkov frente a 0,012 de la regla
de umbral, partición temporal y perfil solo con historial previo. Los guiones
(`docs/presentaciones/`) repiten esas cifras y añaden que "sí probamos el respaldo,
Gemini Flash-Lite: cumple el contrato, pero tarda más". Todo lo de abajo se contrasta
contra eso.

## 3. Hallazgos priorizados

| Prioridad | Hallazgo | Evidencia | Estado | Acción y responsable |
|---|---|---|---|---|
| Crítica | Dos llaves reales en la **copia de trabajo** de `docs/prueba-companero-jeison.txt` (línea 42), archivo versionado, enlazado en `README.md:28`, en un repositorio público. **No están en ningún commit**: el riesgo es que un `git commit -a` las publique | `git status` (` M`), `git diff --numstat` (1 inserción, 2 borrados en el bloque `@@ -42,2 +42 @@`); `git show HEAD:` sin patrones; `HEAD` = `origin/main` = `4b0e593` | CONFIRMADO (riesgo); "versionadas" REFUTADO | Jhoan: pasar las llaves a variables de entorno o a `.env` (ignorado por `.gitignore:4`), `git restore docs/prueba-companero-jeison.txt`, y rotar las dos llaves, porque el validador reconoce que su sesión las imprimió |
| Crítica | El proveedor principal no autentica: 401 `invalid x-api-key` en las 8 tareas de la suite y en las 10 tareas del lote que llegaron a llamar a Claude. Causa probable: el valor de `ANTHROPIC_API_KEY` en el contenedor empieza por `apikey_` y mide 31 caracteres, no tiene el prefijo `sk-ant-` de Anthropic; la llave de Gemini (`AQ.Ab`, 53) sí funciona | `logs/app_tras_suite.txt` (8 × `401 Unauthorized`); traza de L01–L06, L13–L15 y L18 del lote nuevo (`conmutacion`, motivo `autenticacion`); `docker compose exec -T app sh -c` con solo prefijo y longitud | CONFIRMADO | Jhoan: conseguir una llave de Anthropic válida (`sk-ant-…`), inyectarla y comprobar con una sola tarea que `proveedor_final` sea `claude` antes de volver a medir |
| Alta | La regresión 8/8 → 5/8 (suite) y 94,7 % → 78,9 % (lote) **no se puede atribuir al sistema**: el código del contenedor es idéntico a `HEAD` y el prompt es el mismo (`2026-10-21.4`); lo único que cambió es el proveedor que respondió. Además, 8/8 frente a 5/8 con una sola corrida de cada una no es una diferencia concluyente (prueba exacta de Fisher bilateral, p = 0,2) | `sha256sum` de los 34 `.py` de `app/` en el contenedor = copia de trabajo; `git diff --stat HEAD -- app eval src` vacío; `app/agente/prompts.py:25`; `proveedor_final` por tarea (sección 4) | CONFIRMADO | Jeison: medir de nuevo con la llave corregida (ver sección 4) antes de citar cualquier cifra nueva |
| Alta | El respaldo es más lento y menos fiable de lo que dicen los documentos: hoy Gemini 3.1 Flash-Lite cortó varias llamadas por `ReadTimeout` a los 25 s, dio dos 503, terminó D1 (suite) y L04 (lote) en plantilla tras 112–123 s y omitió cifras esperadas (D6 falló en las dos corridas con Gemini; D2 en una de tres). `docs/decisiones.md` §4 dice "4 a 17 s" y el guion dice "cumple el contrato" | traza de L04 (tres `reintento` por timeout de 25 s y `limite` timeout); `logs/app_tras_suite.txt` (dos `503`); `suite_2026-10-24_1344.json` D2 y D6 (`hechos`) | CONFIRMADO | Jhoan: actualizar §4 y la respuesta del guion a "¿lo probaron con un modelo más barato?" con esta medición; para la demo, abrir primero casos en caché |
| Alta | Validador: "el ZIP no está generado". Existe `C:\Users\Jhoan\Desktop\clase_sabado\entrega_momento2_2026-10-21.zip` (1,96 MB, 99 archivos, 21-oct 22:00), fuera del proyecto porque el script lo escribe por defecto en la carpeta padre. Está limpio de patrones de llave, pero **desactualizado**: es anterior a los commits `775a704` y `4b0e593` y no trae `docs/pendientes-y-momento3.md` ni `docs/guia-de-estudio.md`. Tampoco coincide con lo que dice §12 (91 archivos, 1,90 MB a las 21:37) | `scripts/empaquetar_entrega.py:58-59` y `:77`; lectura con `zipfile` (nombres y búsqueda de patrones) | REFUTADO (la afirmación); pendiente 9 sigue abierto | Jhoan: regenerar el ZIP después de restaurar el archivo de llaves y actualizar §12 con el número de archivos y el tamaño reales |
| Alta | El escáner de llaves del empaquetador no cubre el formato `apikey_`: sus patrones son `AIza{30,}`, `AQ\.Ab{20,}`, `sk-ant-{20,}` y `gsk_{20,}`. Hoy abortaría con el archivo de llaves solo por la llave de Google (`AQ.Ab` + 48 caracteres); si alguien quitara solo esa, la otra entraría al ZIP | `scripts/empaquetar_entrega.py:53-58` contra el prefijo `apikey_` | CONFIRMADO | Jhoan: agregar el patrón `apikey_` (y, mejor, rechazar cualquier valor no vacío en líneas `*_API_KEY=` de todo archivo de texto, no solo de `.env.example`) |
| Media | `/api/salud` reporta `con_llave: true`, `estado: ok` y `modo_plantilla: false` con una llave que el proveedor rechaza: solo comprueba que la variable no esté vacía | `app/api/rutas_sistema.py:63-64` (`bool(config.ANTHROPIC_API_KEY)`) y `:94-99`; `curl /api/salud` de hoy | CONFIRMADO | Jhoan: ver la valoración de la sección 4.4; al menos un campo con el último error real de cada proveedor |
| Media | La recuperación del lote nuevo (13/13) no usa el mismo método que la línea base (4/4): el script cuenta fallas forzadas **y reales**, y hoy las reales son conmutaciones por 401. Con el método de §9 (solo forzadas, L16–L19) da 4/4. Además L04 cuenta como "recuperada" aunque terminó en plantilla por timeout, lo que es coherente con la definición de §9 pero conviene decirlo | `eval/correr_lote.py:18` y `:96`; `docs/decisiones.md` §9 | CONFIRMADO | Jeison: reportar en §9 las dos lecturas por separado (forzadas y reales) |
| Media | Los informes del lote y la suite encabezan con "Proveedores con llave: Claude (principal), Gemini", que es la configuración, no quién respondió; y `tareas_contaminadas` sale vacío aunque ninguna tarea la sirvió el principal. Un lector del `.md` puede creer que la corrida fue con Claude | `lote_2026-10-24_1351.md:3`; `cifras.tareas_contaminadas = []`; `eval/correr_lote.py:83` | CONFIRMADO | Jeison: que el script avise (o se detenga) cuando el principal falla por autenticación, y que el resumen diga qué proveedor sirvió cada tarea |
| Media | El documento dice cinco herramientas (`docs/decisiones.md:71` y `:141`); el código registra seis (`declarar_fuera_de_alcance` incluida) | `app/agente/herramientas.py:149-227` | CONFIRMADO (validador C2) | Jhoan: corregir §3 y §6 |
| Media | La cifra "mediana del lote 10 993 tokens" de §6 no se reproduce: sale 11 059 (13 tareas sin caché) | recálculo propio de `lote_2026-10-21_2158.json` | CONFIRMADO (validador C4) | Jeison: corregir a 11 059 o explicar el método |
| Media | "Ninguna tarea tuvo contrato inválido" (§9) choca con la traza de L18 de la línea base, que tiene un `contrato_invalido` reparado en el reintento (es la falla `json` forzada) | `lote_2026-10-21_2158.json`, L18, 1 evento `contrato_invalido` | CONFIRMADO (validador C5) | Jeison: decir "0 contratos inválidos sin reparar" |
| Media | `validacion/motor-riesgo.md` describe todavía la corrida anterior del motor (1 089 casos Sparkov) en sus primeras secciones | `validacion/motor-riesgo.md:20` | CONFIRMADO (validador C3, muestra de una línea) | Jeison: marcar esas secciones como superadas o actualizarlas |
| Media | Criterios de la rúbrica abiertos: suite sin verificación humana (0 de 8 `verificado_por`) y prueba del compañero sin hacer (§10 "PENDIENTE") | `suite_2026-10-24_1344.json` (`casos_verificados: 0`); `docs/decisiones.md` §10 | CONFIRMADO | Ambos: pendientes 1 y 3 de `docs/pendientes-y-momento3.md` |
| Baja | Identificadores en inglés (`random_forest`, `features`) contra la condición 1 de `CLAUDE.md` | `src/motor_riesgo.py:97` | CONFIRMADO (validador 7.1, muestra) | Jeison: decidir si se renombran o se justifican |
| Baja | §7 cita el lote `2132` para los fallos forzados mientras §9 usa el `2158` | `docs/decisiones.md` §7 | CONFIRMADO | Jhoan: unificar la fuente |

## 4. Las cuatro afirmaciones disputadas

### 4.1 ¿Las llaves están versionadas?

**No.** `docs/prueba-companero-jeison.txt` está versionado (lo agregó el commit
`775a704`), pero la versión versionada no contiene ningún patrón de llave: `git show
HEAD:docs/prueba-companero-jeison.txt` da 0 líneas con patrón, y una búsqueda de
`apikey_`, `sk-ant-`, `AIza` y `AQ.Ab` con longitud de llave real sobre **todos** los
commits (`git rev-list --all`) solo encuentra las expresiones regulares de
`scripts/empaquetar_entrega.py` y la mención de prefijos en
`diseno/evaluacion-entrega.md`. `HEAD`, `main` y `origin/main` son el mismo commit
(`4b0e593`, comprobado también con `git ls-remote`), los dos blobs colgantes del
repositorio local no tienen patrones y no hay stash. Las llaves están solo en una
modificación sin commitear de la línea 42 (`git diff --numstat`: 1 inserción, 2
borrados). La confusión del validador tiene una causa concreta: `git grep` sin `--cached`
busca en la copia de trabajo de los archivos versionados, no en lo commiteado, y con `-n`
imprime la línea, que es como terminó mostrando las llaves en su sesión. La misma
instrucción está en `.claude/agents/jefe-fraude.md` (§3, "Secretos"); conviene cambiarla
por `git grep -l --cached` para lo versionado y `git grep -l` para la copia de trabajo,
siempre con `-l` para no imprimir contenido. El riesgo sigue siendo crítico: el archivo
está enlazado desde el README y un `git commit -a` lo publicaría.

### 4.2 ¿El ZIP no está generado?

**Refutado.** El script escribe por defecto en la carpeta padre del proyecto
(`--salida` con `default=os.path.dirname(RAIZ)`, línea 58, y nombre
`entrega_momento2_<fecha>.zip`, línea 77), y ahí está
`entrega_momento2_2026-10-21.zip`. Lo abrí con `zipfile` (solo nombres y búsqueda de
patrones, incluido `apikey_`): 99 archivos, sin llaves, sin el archivo de Jeison. Pero es
del 21 de octubre a las 22:00, anterior a los dos últimos commits, así que el pendiente 9
("regenerar el ZIP final") sigue abierto con razón. Sobre el escáner: detectaría el
archivo de llaves actual gracias a la llave de Google, que tiene formato `AQ.Ab` y largo
suficiente para `AQ\.Ab[0-9A-Za-z_\-]{20,}`, pero **no** detectaría la llave con prefijo
`apikey_`, que no está entre sus cuatro patrones. El validador dijo a la vez que "el ZIP
lo incluiría" (C1) y que "el escáner abortaría" (R-E2); lo segundo es lo correcto hoy, y
ninguna de las dos frases advierte el hueco del formato `apikey_`.

### 4.3 ¿Anthropic rechaza la llave y toda la corrida fue con Gemini?

**Confirmado.** En la suite, las 8 tareas tienen `proveedor_final: gemini` y una
conmutación con motivo `autenticacion` cuyo detalle es el 401 `invalid x-api-key`; el log
de la app tiene ocho `POST https://api.anthropic.com/v1/messages "HTTP/1.1 401
Unauthorized"`. En el lote, de las 13 tareas no servidas desde caché, 12 terminaron en
Gemini y una (L19, caída total forzada) en la plantilla; las 6 de caché reutilizan
explicaciones que Gemini acababa de generar en L01–L06. Un matiz que el probador redondeó:
el 401 no está "en la traza de cada tarea", sino en 10 de las 13; en L16, L17 y L19 la
falla forzada se aplicó antes de la llamada real a Claude. El conteo de la línea base es
el contrario: 10 tareas terminaron en Claude, solo las dos fallas forzadas de 429 y
timeout pasaron a Gemini y no hay ninguna conmutación por autenticación. La causa
probable del 401 es el formato del valor inyectado (sección 3, fila 2): no es un problema
de cuota ni de red, porque la respuesta llega en unos 190 ms y es un 401, no un 429.

**Qué sigue siendo válido y qué no.** Siguen en pie, porque no dependen del proveedor:
las pruebas unitarias (136 aprobadas y 1 omitida, re-ejecutado por mí, igual), la API,
los cuatro límites y su valor en el código, el rechazo determinista (D7 y D8 se
rechazaron con `declarar_fuera_de_alcance` también con Gemini, lo cual es una buena
noticia: la defensa no depende del modelo), el manejo de las fallas forzadas sin traza
cruda (L18 incluso ejercitó la reparación del JSON sobre Gemini) y toda la verificación
del validador sobre la línea base, el motor y las contradicciones documento–código, que
se hizo con archivos del 21 de octubre. **No siguen en pie** como juicio sobre el
sistema: la lectura de la tabla del probador como "regresión", porque mide otro
proveedor; la recuperación 13/13, porque mezcla conmutaciones por 401 con fallas
forzadas; y cualquier comparación de costo, porque Gemini Flash-Lite tiene una tarifa de
2,5 a 3 veces la de Haiku (`app/config.py`, 0,25/1,50 frente a 0,10/0,50 USD por
millón): el costo mediano subió un 83 % aunque los tokens medianos bajaron de 11 059 a
7 525. La latencia tampoco la explica el desvío por el 401, que cuesta unos 0,2 s por
tarea: la explican los `ReadTimeout` de 25 s de Gemini y su backoff.

**Qué medición haría falta.** Primero, la misma suite y el mismo lote con la llave de
Anthropic corregida y el mismo código (prompt `2026-10-21.4`): si vuelven 8/8 y cifras
cercanas a 94,7 % y 5,8 s, la regresión era del proveedor; si no, hay un problema del
sistema que hoy no se ve. Segundo, para caracterizar el respaldo sin el desvío del 401,
una corrida con `ORDEN_PROVEEDORES=gemini`. Y como una sola corrida de 8 casos no
distingue 8/8 de 5/8 con confianza (p = 0,2), repetir la suite al menos tres veces por
proveedor y reportar la tasa de éxito por caso (D6 es el candidato a falla sistemática
de Gemini). Esto lo decide y lo paga el equipo; esta auditoría no corrió nada que
cueste.

### 4.4 ¿`/api/salud` dice `con_llave: true` con una llave inválida?

**Confirmado en el código.** `app/api/rutas_sistema.py:63-64` calcula
`"con_llave": bool(config.ANTHROPIC_API_KEY)` y las líneas 94-99 derivan de eso `estado:
"ok"` y `modo_plantilla: false`; ninguna parte de la salud consulta al proveedor. El
nombre del campo es honesto (dice "tiene llave", no "la llave sirve"), así que no es un
error de implementación, pero **sí es un hallazgo de diseño de prioridad media**: el
semáforo que la interfaz y el equipo usan para saber si la app está sana dio verde
durante toda una corrida en la que el principal nunca respondió, y el único aviso fue la
traza de cada tarea. El impacto funcional es pequeño, porque la cascada no reintenta un
401 y conmuta en unos 0,2 s; el impacto en la demo es alto, porque el guion de Jhoan
(`docs/presentaciones/guion-sustentacion-jhoan.md:108`) confía en "abrir un caso nuevo y
ver que lo explique Claude" como única comprobación. Opciones para que el equipo decida:
guardar el último error de cada proveedor (código y hora) y mostrarlo en la salud;
marcar un proveedor como no disponible durante unos minutos tras un 401, en vez de
probarlo en cada tarea; o una comprobación barata de autenticación al arrancar.

## 5. Auditoría de los agentes

**Lo que re-ejecuté y si coincidió:**

1. *Del probador*, pruebas unitarias: `docker compose exec -T app python -m pytest
   app/pruebas -q -rs -p no:cacheprovider` → 136 aprobadas, 1 omitida
   (`test_plantilla.py:93`, "no están los casos_marcados.json del motor"). Coincide.
2. *Del probador*, las cifras nuevas: recálculo propio con `json` y `statistics` sobre
   `lote_2026-10-24_1351.json` → 15/19 (78,9 %), 10/13 sin caché, costo mediano
   0,002714 USD, latencia mediana 26 010 ms, P90 interpolado 54 418 ms, TTFT 16 981,5 ms.
   Coincide. Su "P90 por rango más simple, 43,6 s" no es el rango más cercano estándar:
   con 13 valores el percentil 90 por rango es el valor 12, 57,1 s; 43,6 s es el 11.
3. *Del validador*, las cuatro cifras de la línea base sobre `lote_2026-10-21_2158.json`
   → 18/19, 0,001481 USD, 5 764 ms y P90 17 106,4 ms, TTFT 795,5 ms; tokens medianos
   11 059 (no 10 993); un `contrato_invalido` en L18. Coincide en todo.
4. *Las dudosas*: llaves "versionadas" (refutado, 4.1), ZIP "no generado" (refutado,
   4.2), 401 y proveedor por tarea (confirmado, 4.3), salud (confirmado, 4.4); seis
   funciones de herramienta en `herramientas.py` (coincide con el validador); que el
   código del contenedor es el de `HEAD` (34 hashes iguales); que `falla_forzada` quedó
   vacía (el probador lo afirmó sin log; `curl /api/salud` hoy da `""`, coincide).

**Probador (Sonnet): 4 de 5.** Encontró el hallazgo que cambia la lectura de toda la
corrida, lo dijo en la primera línea, recalculó las medianas en lugar de copiarlas y
advirtió que las cifras no son comparables. Pierde un punto por tres cosas: siguió con
el lote (que cuesta) después de ver los 401 en la suite, sabiendo que la medición no
serviría como comparación; afirmó que el 401 está "en la traza de cada tarea" y que
`falla_forzada` quedó vacía sin dejar log de eso; y no buscó la causa del 401, que
estaba a un comando de distancia (el formato del valor inyectado). Su log de la app
cubre solo la suite, no el lote.

**Validador (Haiku): 2 de 5.** El trabajo numérico es sólido y útil: las cuatro cifras,
la de tokens, el contrato inválido de L18, las seis herramientas y las contradicciones
del motor coinciden con mis comprobaciones. Pero sus dos afirmaciones de mayor peso
están refutadas: dio por "versionadas" unas llaves que solo están en la copia de trabajo
(por usar `git grep` sin `--cached`) y dio por "no generado" un ZIP que está justo donde
el script dice que lo deja. Además imprimió las llaves en su sesión, lo que obliga a
rotarlas, llamó "de Anthropic" a una llave cuyo formato no es el de Anthropic sin
evidencia, se contradijo sobre si el ZIP la incluiría y no vio el hueco del escáner.
Errores menores: dice "2 suites" en `eval/resultados/` cuando la línea base tenía tres.

## 6. Lo que no se pudo verificar y por qué

No se volvió a correr la suite ni el lote (lo prohíbe la consigna y la llave de
Anthropic está en duda), así que no hay ninguna medición con Claude posterior al 21 de
octubre y la pregunta "¿la línea base se reproduce hoy?" queda abierta. No pude
confirmar a qué servicio pertenece el valor con prefijo `apikey_`: solo que no tiene el
formato de Anthropic y que Anthropic lo rechaza. No se probó el arranque desde el ZIP en
una máquina limpia ni la interfaz en el navegador (DevTools, panel de trazas, pantallas
de los fallos), y no se consultaron las tarifas oficiales. Del validador, solo verifiqué
una muestra de sus 77 veredictos (las cifras, las herramientas, el contrato inválido,
una línea de `validacion/motor-riesgo.md` y un identificador en inglés); el resto queda
como lo reportó.

**Desviación de método que declaro.** Para comparar formatos ejecuté una vez un `grep -o`
sobre la copia de trabajo de `docs/prueba-companero-jeison.txt` que imprimió, para cada
llave de la línea 42, el número de línea, los primeros siete caracteres y la longitud.
Eso excede lo que pedía la consigna (inspeccionar el archivo solo vía git). Para la
llave de Google esos siete caracteres incluyen dos que no son del prefijo de formato; no
los reproduzco en este informe ni en ningún archivo, y no se imprimió ningún valor
completo. En el contenedor solo se imprimió el prefijo de formato y la longitud.
