# Informe del auditor jefe — Momento 3 (2026-11-14)

Repositorio: rama `momento3` = `main` = `01c429e`. Entrega: jueves 19-nov a las 23:59. El profesor clona y
prueba el 20-nov y hace pruebas de seguridad en la presentación del 21-nov.

Este informe revisa los cinco informes de `auditoria/2026-11-14_m3/` (probador, seguridad, motor y medición,
agente y backend, documentos y entrega), vuelve a ejecutar por cuenta propia lo más importante y dice qué
hay que hacer, quién y en cuánto tiempo. No se modificó código, no se reinició la app, no se usó el simulador
ni se hizo ningún POST. Las consultas a la base fueron de solo lectura (`default_transaction_read_only=on`) y
las pruebas de código corrieron en un contenedor desechable sin dependencias.

## 1. Veredicto

**Listo con condiciones.**

El producto funciona, arranca desde un clon limpio y resistió el pentest en vivo. Lo que impide entregarlo tal
como está es que **la cifra principal del proyecto, "71,4 % de fraude detenido", no es defendible hoy**: el
agente decidió con información que en la vida real no habría tenido (H1 y H2, confirmados abajo con las trazas
de una corrida real). A eso se suman tres defectos baratos de corregir que el profesor puede encontrar en
minutos (C1, C2 y A1) y un `docs/decisiones.md` que todavía describe el Momento 2 en cuatro secciones.

Las condiciones son cuatro, y caben en los cinco días que quedan (unas 14 horas de código y documentos, más
lo que depende del equipo):

1. Corregir la fuga de historial, repetir la medición y reemplazar la cifra en §13.1 y en el README.
2. Corregir C1 (validación del aviso), C2 ("confirmar bloqueo" no bloquea) y A1 ("no fui yo" no hace nada).
3. Poner `docs/decisiones.md` al día y retirar o reescribir `comandos-demo.md`.
4. Lo que solo puede hacer el equipo: firmar los casos dorados, hacer la prueba con un tercero y rotar las llaves.

**Cifra defendible hoy: 61,8 %.** Es lo que detiene el sistema con la regla sola (IA caída), no depende de lo
que haya leído el agente, y se reprodujo tres veces (9-nov, hoy por el probador y fuera de línea por el auditor
del motor). El detalle está en la sección 3.

## 2. Lo que volví a ejecutar

### 2.1 H1 — fuga de información futura al agente: CONFIRMADA

**Un obstáculo primero.** El encargo suponía que la tabla `trazas` guardaba el resultado de
`obtener_historial_reciente` de la medición de hoy. No es así, por dos razones. El probador terminó con
`--reiniciar-en-vivo`, que borra las tareas y trazas de los casos en vivo (`app/db/migrar.py:296-303`). Y la
traza de una herramienta no guarda las filas que devolvió, solo un resumen con el número de transacciones
(`resultado_herramienta.detalle.resumen.n_transacciones`). La salvedad del auditor del motor ("confirmarlo toma
un `SELECT` de las trazas") tampoco se podía cumplir.

**Cómo lo confirmé.** A las 04:06 UTC (23:06 hora local), después de que el probador cerró, alguien volvió a
correr el simulador sobre la noche del 19-jul (yo no fui: ver 2.5). Eso dejó casos en vivo con sus triajes y
sus trazas. Los leí en solo lectura y, para cada triaje, crucé tres cosas:

- la compra que había en el caso cuando el agente lo leyó (`n_transacciones` de `obtener_caso`);
- las filas de `historial` con `origen = 'semilla'` de esa tarjeta, posteriores a esa compra y dentro de
  `fin_ventana`, que son exactamente las que devuelve la consulta de `app/db/repositorio.py:278-281`;
- la etiqueta de fraude de `semilla/simulador_sparkov.json.gz`, que el agente no ve.

El número de filas que el agente leyó coincide con lo que la consulta devuelve hoy (por ejemplo, 23 de 23 en
`VIV-000002`, todas de semilla), así que las filas futuras estaban en lo que leyó.

| Caso | Tarjeta | Banda al empezar | ¿Fraude? | Filas futuras leídas (fraudulentas) | Acción del agente |
|---|---|---|---|---|---|
| VIV-000001 | …0532 | alta | no | 9 (0) | verificación |
| VIV-000002 | …7879 | alta | sí | 9 (3) | **bloqueo** |
| VIV-000003 | …7331 | alta | sí | 7 (6) | **bloqueo** |
| VIV-000004 | …3217 | alta | sí | 2 (2) | **bloqueo** |
| VIV-000005 | …2095 | crítica | sí | 1 (0) | bloqueo |
| VIV-000006 | …3984 | crítica | sí | 17 (10) | bloqueo |
| VIV-000007 | …5498 | media | no | 0 | verificación |
| VIV-000008 | …9419 | crítica | sí | 1 (1) | bloqueo |
| VIV-000009 | …9125 | alta | sí | 6 (6) | verificación |
| VIV-000010 | …9344 | alta | no | 0 | verificación |
| VIV-000011 | …1683 | alta | no | 0 | verificación |
| VIV-000012 | …2797 | alta | no | 0 | verificación |

Lectura de la tabla (12 triajes; la corrida seguía cuando la leí):

- Las 7 tarjetas con fraude tenían filas futuras a la vista; de las 5 honestas, solo 1. La información extra
  está correlacionada con la etiqueta, como dijo el auditor del motor.
- En `VIV-000002` el agente leyó compras de la tarjeta hasta las 21:29 del 20-jul, casi 24 horas después de
  la compra de las 22:00 del 19-jul que abrió el caso.
- Los tres bloqueos en banda alta caen en las mismas tres tarjetas (…7879, …7331 y …3217) que el auditor del
  motor había señalado por aritmética sobre la corrida del 9-nov. Es el resultado que sostiene "precisión 1,0"
  y "9,6 puntos del LLM".
- También recalculé su tabla fuera de línea con el `historial` real de la base y los horarios de apertura de
  su log: coincide fila por fila (9 de 9 tarjetas con fraude con filas futuras; 3 de 12 honestas).

**El matiz que el informe del motor no tiene.** La fuga no decide sola. En `VIV-000009` el agente tenía 6
compras fraudulentas futuras a la vista y aun así pidió verificación. Y cuando bloqueó en alta, lo que escribió
como razón no fueron las filas futuras de la semilla:

- en `VIV-000002` y `VIV-000003` citó "tres compras en línea en menos de 25 minutos". Esas compras ya estaban
  **dentro del caso** cuando leyó, porque a 3600x llegaron mientras el triaje esperaba en la cola. Eso es H2,
  no H1. En `VIV-000003` el propio agente escribió "banda crítica" aunque el triaje empezó en alta;
- en `VIV-000004` citó "siete compras grandes en 30 horas que el sistema no marcó", que son anteriores a la
  ventana (el episodio venía de antes: H6).

Conclusión: H1 está confirmada como exposición (el agente recibe el futuro, y más en las tarjetas con fraude),
pero el peso causal sobre el 71,4 % se reparte con H2. Para la cifra da igual cuál de las dos pesa más: el
script acredita el bloqueo a la **primera** compra en banda alta (`eval/medir_momento3.py:150-158`), y en ese
instante, en tiempo real, el agente habría tenido una sola compra en el caso y ninguna fila futura. Con dos
compras sobre el umbral el caso ya es crítico y lo bloquea la regla, que es justo el escenario del 61,8 %.

**Qué corregir** (hay que cerrar las dos puertas antes de repetir la medición):

1. En `obtener_historial`, para casos con `origen = 'en_vivo'`, cortar en la fecha de la última compra del
   caso, no en `fin_ventana`. Como segunda barrera, que `--reiniciar-en-vivo` borre del `historial` de semilla
   las filas de las tarjetas del simulador con fecha desde el inicio de la ventana.
2. Una prueba que falle si el historial de un caso en vivo trae una fila posterior a su última compra.
3. Repetir la medición a 60x (36 minutos; ahí 5 s de triaje son 5 minutos del dataset) o pausar el simulador
   mientras hay un triaje en curso. Repetirla a 3600x deja H2 intacta.

### 2.2 C1 — la validación del aviso deja pasar dominios: CONFIRMADA

Llamé a `validar_motivo` y a `armar` de `app/riesgo/avisos.py` con el código actual montado en un contenedor
aislado:

| Motivo | Resultado |
|---|---|
| "… Desbloquee en bancodemo-seguro.shop" | **PASA** |
| "… visite banco.lat" | **PASA** |
| "… Entre a bancodemo . com" | **PASA** |
| "… Entre a bancodemo.es/ayuda" | **PASA** |
| "… soporte arroba bancodemo punto com" | **PASA** |
| "… Entre a bancodemo.com" | rechazado |
| "… Entre a http://x.shop" | rechazado |
| "… banco-seguro-co.com llame 300 555 1234" (el del pentest) | rechazado |

Con el primero, `armar` devuelve `autor_motivo = "agente"` y el cuerpo del mensaje al titular incluye
"Desbloquee en bancodemo-seguro.shop" entre la plantilla del banco y la frase "Nunca le enviaremos enlaces". La
causa es la lista de 15 terminaciones de `avisos.py:37`.

**Por qué el pentest en vivo no lo vio.** Por dos razones que se suman. La primera: el modelo no obedeció la
orden inyectada en el comercio, así que el validador nunca recibió un motivo con dominio; lo que resistió fue
el modelo, no el validador. La segunda: aunque hubiera obedecido, el dominio del ataque terminaba en `.com`,
que sí está en la lista, y el validador lo habría rechazado. La prueba solo podía salir bien. Por eso la frase
del informe de seguridad "la salida de la tríada quedó cerrada" es más fuerte que su evidencia: la salida
depende hoy de que el modelo no obedezca.

Sobre la gravedad: para que el enlace llegue al titular hace falta además que la inyección convenza al modelo,
y hoy no lo consiguió ni el probador ni el pentest. Lo mantengo en prioridad crítica porque el profesor anunció
justo esa prueba, `docs/SPEC.md` y `docs/seguridad.md` afirman que un enlace no puede llegar al aviso, y
corregirlo toma una hora.

### 2.3 C2 y A1 — CONFIRMADOS por lectura del código

- **C2.** `registrar_decision` (`app/db/repositorio.py:541-553`) llama a `_insertar_decision` (`:481-497`),
  que inserta en `decisiones` y cambia `casos.estado` a `bloqueo_confirmado`. No crea ninguna fila en
  `bloqueos`. El flujo solo rechaza una compra si existe un bloqueo activo en esa tabla
  (`app/riesgo/flujo.py:138`), y `bloqueo_confirmado` está en `ESTADOS_SIN_TRIAJE` (`app/agente/triaje.py:40`),
  así que el agente tampoco vuelve a mirar el caso. El analista pulsa "Confirmar bloqueo" y la tarjeta sigue
  comprando. No repetí la sonda con base propia del auditor del backend; la lectura no deja otra posibilidad.
- **A1.** `responder_notificacion` (`app/db/repositorio_acciones.py:173-179`) es un único `update` sobre
  `notificaciones`; la ruta (`app/api/rutas_operacion.py:73-80`) no hace nada más. `docs/SPEC.md:134-135` dice
  que "No fui yo" marca el bloqueo como confirmado por el titular. En un caso en verificación, la respuesta
  "no fui yo" no bloquea ni alerta.

Los dos se ven en la demo: son botones de la interfaz.

### 2.4 Una afirmación de seguridad y una del probador

- **Seguridad, "0 llaves en el historial de git": confirmada.** `git log --all -p` con los cuatro patrones
  (incluido `AQ\.` seguido de cualquier cosa, más amplio que el del empaquetador) da 0 coincidencias. También
  confirmé B-1 en el código: el control de rol de `app/api/sesion.py:128` solo se aplica a métodos que
  escriben y `/api/supervision` no está en `SOLO_SUPERVISOR` (`:36`).
- **Probador, "la app quedó lista para la demo": cierta a las 23:03, ya no lo es** (ver 2.5). Su otra cifra
  dudosa, 267 pruebas, sí cuadra: su log dice "267 passed, 1 skipped", que son las 268 recolectadas de los
  otros dos informes. No hay contradicción con los documentos.

### 2.5 Hallazgo propio: el entorno quedó sucio después del probador

Entre las 04:06 y las 04:09 UTC alguien corrió el simulador con la IA real. Cuando lo leí había 15 casos en
vivo, 5 bloqueos activos, 15 avisos y 3.867 compras en el historial en vivo, y la corrida seguía. No fui yo ni
consta en ningún informe. Antes de cualquier demo hay que ejecutar `--reiniciar-en-vivo` y
`docker compose restart app` (por P2).

Además, `logs/seguridad-auditor_idor_cookie.txt` contiene un valor de cookie de sesión. Los archivos
`*.cookies` que mencionó el probador ya no están, pero ese log sí: hay que limpiarlo antes de versionar la
carpeta `auditoria/`.

## 3. Qué cifra decir en la presentación

| Cifra | Valor | ¿Se puede decir? |
|---|---|---|
| Regla del M2 en la práctica | 29,3 % a 34,9 % | Sí. Es un contrafactual sobre las mismas compras y no depende del agente |
| M3 con la IA caída (la regla bloquea en la 2.ª compra sobre el umbral) | **61,8 %** | **Sí, es la cifra defendible.** Reproducida el 9-nov, hoy y fuera de línea |
| M3 con el agente | 71,4 % | No como resultado. Solo como "lo que midió una corrida en la que el agente veía compras posteriores; lo estamos corrigiendo" |
| Aporte del LLM | 9,6 puntos, precisión 1,0 en banda alta | No. Son 3 tarjetas y las 3 decisiones usaron información posterior |
| Techo si se bloqueara en la 1.ª compra marcada | 79,6 % | Sí, como cota superior (cálculo del auditor del motor, no repetido por mí) |

Frase sugerida si no se alcanza a repetir la medición: "El sistema detiene el 61,8 % del fraude de esa noche
aunque la IA esté caída, contra el 29 a 35 % del Momento 2. Con el agente medimos 71 %, pero encontramos que en
esa medición el agente leía compras posteriores; la cifra limpia está entre 61,8 % y 79,6 %". Si se repite
después de corregir, se dice el número nuevo, sea cual sea, con su intervalo: son 9 tarjetas y el intervalo de
la regla va de 42 % a 72 %.

Las demás cifras se sostienen: precisión 0,90 y recall 1,00 de los bloqueos por tarjeta (9 de 10), 0,17
bloqueos falsos por cada 1.000 compras, 0,054 USD la noche. El costo queda firme: la tarifa de Claude Haiku 5.5
(0,10/0,50 USD por millón) la verificó la sesión principal en la tabla oficial. El "5,7 s" hay que decirlo con
su definición (desde la compra que dejó el caso en la banda del bloqueo); desde la apertura del caso la mediana
de hoy fue 7,5 s y el máximo 33,7 s.

## 4. Hallazgos clasificados

Estados: **CONFIRMADO** (lo volví a ejecutar o lo leí en el código), **NO CONFIRMADO** (verosímil y con
evidencia del agente, pero no lo repetí), **REFUTADO**. Responsables: Jhoan (agente, app, frontend, seguridad)
y Jeison (datos, motor, medición).

### 4.1 Corregir en código antes del 19-nov

| # | Hallazgo | Estado | Prioridad | Evidencia | Acción | Quién | Horas |
|---|---|---|---|---|---|---|---|
| 1 | H1: el historial del triaje incluye compras futuras | CONFIRMADO | Crítica | Sección 2.1; `repositorio.py:278-281`, `flujo.py:196` | Cortar el historial en la última compra del caso, prueba que lo vigile, limpiar la semilla al reiniciar | Jhoan | 2 |
| 2 | H2: a 3600x el caso acumula horas de compras antes de que el agente lea | CONFIRMADO | Crítica (va con el 1) | Resúmenes de `VIV-000002` y `VIV-000003`; `medir_momento3.py:143-158` | Medir a 60x o pausar el simulador durante el triaje; repetir `base` e `ia_caida`; actualizar §13.1 y el README | Jeison | 2,5 |
| 3 | C1: dominios fuera de 15 terminaciones pasan la validación del aviso | CONFIRMADO | Crítica | Sección 2.2; `avisos.py:37` | Rechazar cualquier `letra.letra`, `/`, `@`, "arroba", "punto com", "www"; agregar los casos a `test_avisos.py` | Jhoan | 1 |
| 4 | C2: "Confirmar bloqueo" no bloquea en casos en vivo | CONFIRMADO | Crítica | Sección 2.3 | Que la decisión llame a `bloquear` con `actor='analista'` en la misma transacción; prueba "confirmar y luego comprar se rechaza" | Jhoan | 1,5 |
| 5 | A1: "No fui yo" no tiene efecto | CONFIRMADO | Alta | Sección 2.3 | En verificación: bloquear y alertar. Sobre un bloqueo: marcarlo como confirmado por el titular | Jhoan | 1,5 |
| 6 | A6: `obtener_caso` le entrega al triaje "verificar antes de bloquear" | NO CONFIRMADO (visto `nivel_recomendacion` y `motivo_recomendacion` entre los campos de la traza) | Alta | Traza de `VIV-000001`; `flujo.py:186` | No enviar esos dos campos al triaje. Hacerlo **antes** de repetir la medición, porque cambia el comportamiento | Jhoan | 0,5 |
| 7 | A2: un triaje puede dar 2 bloqueos y 3 avisos | NO CONFIRMADO | Alta | Sondas del backend; `bucle.py:270-272` | Tras la primera acción efectiva, responder `accion_ya_tomada` a las demás | Jhoan | 1 |
| 8 | A3: descartar sin motivo apaga la red y deja bloqueos huérfanos | NO CONFIRMADO | Alta | Sondas del backend; `repositorio_acciones.py:29` | En casos en vivo, exigir motivo de 10 caracteres y rechazar el descarte si hay bloqueo activo | Jhoan | 1 |
| 9 | M2 (backend): el límite de peticiones es por IP y, detrás de Docker, global | NO CONFIRMADO (lo dicen dos informes) | Media-alta para el 21-nov | `limites.py:106` y `162-165` | Clave por usuario de la sesión. En las pruebas masivas un evaluador puede dejar con 429 al presentador | Jhoan | 1 |
| 10 | B-1: un analista lee `/api/supervision` y `/api/simulador` | CONFIRMADO | Media | `sesion.py:36` y `128` | Aplicar el rol también a los GET y agregar la ruta a la lista | Jhoan | 0,5 |
| 11 | M7: la regla 7 del prompt base dice que ningún bloqueo se ejecuta sin el analista | NO CONFIRMADO | Media | `prompts.py:44` | Corregir la regla; subir `VERSION_PROMPT` | Jhoan | 0,5 |
| 12 | `run.ps1` aborta en PowerShell 5.1 si Docker escribe en stderr | CONFIRMADO en el código (`run.ps1:8` y `:17`); el fallo lo reprodujo el auditor de documentos | Media | `run.ps1:8,17,72` | Bajar `ErrorActionPreference` alrededor de las dos llamadas a Docker | Jhoan | 0,5 |
| 13 | P2: `--reiniciar-en-vivo` no limpia el simulador en memoria | NO CONFIRMADO | Media | `probador-final.txt` | Documentar el `restart` en el README §2 | Jhoan | 0,2 |
| 14 | M3 (backend): un flujo malformado del proveedor salta el respaldo y la plantilla | NO CONFIRMADO | Media | `claude.py:128-136` | Envolver el recorrido de eventos en `ErrorProveedor` | Jhoan | 1, si sobra tiempo |

Subtotal: unas 11 horas sin la fila 14.

### 4.2 Documentos que hay que corregir antes del 19-nov

| # | Hallazgo | Estado | Prioridad | Evidencia | Acción | Quién | Horas |
|---|---|---|---|---|---|---|---|
| 15 | `docs/decisiones.md` describe el M2 en §1, §2, §6 y §11 | CONFIRMADO | Alta | Título "(Momento 2)"; `:41` "el agente solo propone"; `:151` "las seis"; `:291` versión `2026-10-21.4` frente a `prompts.py:27` | Actualizar título, §2, §6 (10 herramientas) y §11; §10 y §12 | Jhoan | 1,5 |
| 16 | `docs/presentaciones/comandos-demo.md` es del M2 y sus `curl` hoy dan 401/403 | CONFIRMADO (existe y usa `curl` sin sesión) | Alta | `comandos-demo.md:23` | Reescribirlo con sesión o sacarlo del repo y del ZIP | Jhoan | 0,5 |
| 17 | §13.1 y README: cifra, definición del "5,7 s", P5 ("la regla bloqueó" y fue el agente) | CONFIRMADO | Alta | `decisiones.md:360` y `:369`; JSON `bloqueos_por_actor = {"agente": 10}` | Reescribir §13.1 con la medición nueva y sus intervalos | Jeison | 1 |
| 18 | `seguridad.md` §5 sin las filas "Secretos" y "Salida a internet"; SPEC sin la renegociación del viaje imposible, con roles y rutas que no existen | NO CONFIRMADO | Media | Informe de documentos §1 y C6-C8 | Completar las filas y corregir la SPEC | Jhoan | 1 |
| 19 | README: Compose 2.24 o superior, puerto distinto de 8000, tarifas "por verificar" | NO CONFIRMADO, salvo las tarifas, que ya están verificadas | Media | README:45, 105, 133-136 | Tres frases; quitar "hay que verificarlas" y citar la fuente oficial | Jhoan | 0,5 |
| 20 | H4 y H5: la regla de comparación es débil y el 13 % usa la base equivocada | NO CONFIRMADO | Media | `motor-puntuar.txt`, `motor-ritmo.txt` | Agregar la regla de dos umbrales a §8 y corregir la redacción del análisis | Jeison | 1 |
| 21 | `guia-de-estudio.md` §5 responde con el M2; `CLAUDE.md` dice Gemini 3.1 | NO CONFIRMADO | Media para la sustentación | Informe de documentos C4 y C9 | Corregir §5 y dos líneas | Ambos | 0,5 |

Subtotal: unas 6 horas.

### 4.3 Basta declararlo como limitación en §13.3

| Hallazgo | Estado | Prioridad | Qué escribir |
|---|---|---|---|
| H3: una sola noche, 9 tarjetas, ventana elegida mirando la etiqueta | NO CONFIRMADO | Alta para la sustentación | Intervalos junto a cada cifra y la cota poblacional (73,3 % con la regla en todo el tramo de prueba) |
| H6: 4 de los 9 episodios venían de antes de la ventana | CONFIRMADO en parte (`VIV-000004` cita compras previas no marcadas) | Media | Una frase en §13.1 |
| H7 y P4: el "5,7 s" usa la definición más favorable | CONFIRMADO en el JSON de hoy | Media | Nombrar la definición y dar también 7,5 s y 33,7 s |
| P3: dentro de la simulación a 3600x solo se detiene el 29,3 % | CONFIRMADO en el JSON (`fraude_que_paso_medido`) | Media | Tener la explicación lista; mejor aún, hacer la demo a 60x o 300x |
| H8: el tramo de prueba se reutilizó en decisiones de diseño | NO CONFIRMADO | Baja | Una frase |
| H9: la paridad de 111.342 compras no tiene log guardado | NO CONFIRMADO | Baja | Guardar la salida del script (15 minutos) o citar la paridad de la noche |
| H10 y M9: el viaje imposible ignora pares con 0 s y no abre casos con Sparkov | NO CONFIRMADO | Baja | Declararlo en la SPEC como renegociación |
| H11: no se cuentan las verificaciones a clientes honestos | CONFIRMADO en parte (en la corrida que leí, 4 de 4 honestos en alta recibieron aviso) | Baja | Reportar la cifra |
| A4: sin plazo total por tarea, peor caso de 1.284 s | NO CONFIRMADO | Media | Documentar el peor caso en §6; arreglarlo no cabe con seguridad |
| A5: un reinicio pierde los triajes en curso | NO CONFIRMADO | Media | Declararlo; los críticos los cubre la red |
| M5, M6, M8, M10 y B1 a B12 del backend | NO CONFIRMADO | Baja | No tocar antes de la entrega |
| B-2 a B-5 de seguridad (bloqueo de cuenta, cookie `Secure`, contraseña por defecto de Postgres, panel de demo) | NO CONFIRMADO | Baja | Ya son riesgos asumidos; B-4 y B-5 son dos líneas si sobra tiempo |
| P6: una sola compra de casi un millón sale "sin alerta" | NO CONFIRMADO | Media para la demo | En la demo, inyectar dos compras seguidas |

### 4.4 Depende del equipo

| Pendiente | Estado | Prioridad | Quién | Horas |
|---|---|---|---|---|
| Firmar D1 a D8 en `eval/casos_dorados.json` | CONFIRMADO (8 de 8 con `verificado_por` en `null`) | Alta | Ambos | 1 |
| Prueba con alguien ajeno al equipo y llenar `prueba-tercero.md` | NO CONFIRMADO (lo reporta el informe de documentos) | Alta: es lo que separa "funciona" de "excelente" en la rúbrica | Ambos | 1 |
| Rotar las llaves de Anthropic y de Google y anotarlo en `respuesta_auditoria.md` | NO CONFIRMADO (no abrí los archivos con llaves) | Alta: es una promesa abierta de la auditoría anterior | Jhoan | 0,5 |
| Prueba en el equipo de Jeison | Pendiente | Media | Jeison | 1 |
| Reiniciar el flujo en vivo y reconstruir la imagen en la máquina de la presentación | CONFIRMADO que hoy está sucio (2.5) | Alta el día 21 | Jhoan | 0,2 |
| Limpiar la cookie de `logs/seguridad-auditor_idor_cookie.txt` antes de versionar `auditoria/` | CONFIRMADO | Media | Jhoan | 0,1 |

### 4.5 Refutados o corregidos

| Afirmación | De quién | Por qué no se sostiene |
|---|---|---|
| "Los costos podrían estar subestimados 10 veces" (M4b) | Agente y backend | REFUTADO: la tarifa 0,10/0,50 USD es la oficial. La parte (a) de M4, costo 0 si el modelo no está en la tabla, sigue en pie como baja |
| "La salida de la tríada quedó cerrada" | Seguridad | REFUTADO por C1: resistió el modelo, y el ataque usaba `.com`, la única clase de dominio que el validador sí detecta |
| "Confirmar H1 toma un SELECT de las trazas" | Motor | REFUTADO: las trazas no guardan las filas y el reinicio las borra. H1 sí se confirmó por otra vía |
| "267 frente a 268 pruebas" como contradicción (C5, B12) | Documentos y backend | REFUTADO: son 267 aprobadas y 1 omitida |
| "Hay archivos `*.cookies` en `logs/`" (P8) | Probador | Ya no existen; queda la cookie dentro de un log (4.4) |
| "La app quedó lista para la demo" | Probador | Era cierto al terminar; hubo una corrida posterior (2.5) |
| "Lo que aporta el LLM, medido: 9,6 puntos" (`decisiones.md:371`) | Documento del equipo | No demostrado: ver 2.1 |

## 5. Calificación de los cinco agentes

| Agente | Nota | En una frase |
|---|---|---|
| Motor y medición | 5 | Encontró lo más grave del proyecto con un mecanismo exacto y un recálculo que coincide fila por fila con la base real; solo le faltó ver que H2 pesa tanto como H1 |
| Agente y backend | 4,5 | C1, C2 y A1 son reales y están bien explicados con su corrección; exageró la duda de las tarifas y dio por "críticos" hallazgos que piden una condición previa |
| Documentos y entrega | 4 | Matriz de rúbrica útil y contradicciones verificables con archivo y línea; mezcla lo importante con mucho detalle menor y contó como contradicción las 268 pruebas |
| Probador en vivo | 4 | Cobertura amplia y honesta (P3 y P4 apuntan al mismo problema de la cifra), pero repitió la medición sin cuestionarla y borró las trazas que servían para auditarla |
| Seguridad en vivo | 3 | Pentest correcto en lo que probó, pero concluyó "salida cerrada" con un único ataque que no podía fallar y no revisó la expresión regular que tenía delante |

## 6. Orden de trabajo sugerido

1. **Domingo 15 y lunes 16 (Jhoan):** filas 1, 3, 4, 5 y 6 de la tabla 4.1, con sus pruebas. Unas 6,5 horas.
2. **Lunes 16 (Jeison):** repetir `base` e `ia_caida` a 60x con el código corregido; reescribir §13.1 y la
   tabla del README con el número que salga y sus intervalos. Unas 3,5 horas.
3. **Martes 17 (Jhoan):** filas 7 a 13 y `docs/decisiones.md`, `comandos-demo.md`, `seguridad.md` y la SPEC.
4. **Miércoles 18 (ambos):** firmas, prueba con un tercero, rotación de llaves, prueba en el equipo de Jeison.
5. **Jueves 19:** `git status` limpio, pruebas, 12 ataques más los seis motivos de C1, ZIP y entrega.

Si el tiempo no alcanza, lo que no se puede dejar sin hacer es: el filtro del historial con la medición
repetida (o, en su defecto, cambiar la cifra a 61,8 % en el README y en §13.1), C1, C2 y `docs/decisiones.md`.

## 7. Evidencia de esta revisión

Los volcados de solo lectura y los scripts quedaron fuera del repositorio, en el scratchpad de la sesión
(`C:\Users\Jhoan\AppData\Local\Temp\claude\b3f7846d8f8bead5\39649491-73ed-479e-9412-4797394f9a25\scratchpad\`):
`trazas_triaje.json`, `casos_vivo.json`, `hist_db.csv`, `h1.py` y `c1.py`. Los datos de tarjeta son los de
Sparkov (sintéticos). No se copió ninguna llave ni contraseña.
