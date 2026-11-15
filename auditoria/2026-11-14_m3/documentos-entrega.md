# Auditoría de documentación, entrega y rúbrica (Momento 3)

Fecha: 2026-11-14 (sábado), a 5 días de la entrega del jueves 19-nov 23:59.
Alcance: rama `main` = `momento3` = `origin/main` = `01c429e`. No se modificó nada del repositorio
salvo este archivo. Las llaves se citan solo como archivo:línea, nunca su valor.

Fuentes contrastadas: rúbrica oficial del Momento 3 (descargada hoy del sitio del curso,
`/momento3_rubrica`, porque el espejo local de `material/` llega solo hasta la semana 10), reto de
la semana 12 (`/semana12/workshop`), `transcript.md` (clase 12), `docs/pendientes-y-momento3.md`
§2, §8 y §9, `PLAN.md`, `docs/SPEC.md` y los documentos que enlaza el README.

---

## 0. Veredicto corto

El producto y los cuatro documentos nuevos (SPEC, seguridad, gobernanza, respuesta a la
auditoría) existen, son concretos y sus cifras cuadran con los JSON de `eval/resultados/`. Lo que
pone puntos en riesgo no es el código, sino tres cosas:

1. **Lo que depende del equipo sigue vacío**: los 8 casos dorados sin firmar, la hoja de la prueba
   con un tercero sin llenar y ninguna evidencia de que las llaves se rotaron.
2. **Documentos del Momento 2 que contradicen al Momento 3 y viajan en el repo y en el ZIP**,
   empezando por `docs/decisiones.md` (el documento donde la rúbrica busca las cifras finales):
   todavía dice que "el agente solo propone" y que "el bloqueo final es humano", que hay seis
   herramientas (el código tiene diez) y que el prompt vigente es `2026-10-21.4` (el código usa
   `2026-11-08.2`). `docs/presentaciones/comandos-demo.md` trae comandos `curl` del M2 que hoy
   responden 401/403.
3. **Huecos frente al formato pedido**: falta la cifra "tiempo hasta el desbloqueo"; la tabla de
   hardening de `seguridad.md` no tiene las filas "Secretos" ni "Salida a internet" que pide el
   reto 12; y la SPEC no declara como renegociación que el viaje imposible (el segundo tipo de
   fraude del alcance inicial) no abre casos en el flujo en vivo.

---

## 1. Matriz rúbrica → evidencia → estado

Rúbrica oficial del M3: Producto 25, Seguridad 20, Gobernanza 20, Medición 15, Sustentación 20.

### 1.1 Entregables obligatorios

| Entregable | Evidencia | Estado | Comentario |
|---|---|---|---|
| Producto completo, corriendo | `docker-compose.yml`, `run.ps1`, `run.sh`, `semilla/` con el modelo (5,2 MB) | CUMPLE (estático) | El clon limpio trae todo lo que la app necesita. No se levantó otro stack (puerto 8000 ocupado); el arranque lo documenta la SPEC §8 (16 s, 2026-11-08) |
| Modelo de amenazas y hardening | `docs/seguridad.md` §1-§3 y §5 | PARCIAL | Concreto y con la tríada evaluada. Al hardening le faltan dos de las cinco filas del reto 12 ("Secretos" y "Salida a internet"); los secretos aparecen solo como riesgo asumido (§6) |
| Prueba de inyección documentada | `docs/seguridad.md` §4, `eval/ataques_momento3.py`, `eval/resultados/ataques_momento3_2026-11-09.json` | CUMPLE con matiz | 12 de 12 verificados en el JSON. La "traza" de A1 es un resumen (secuencia de herramientas y texto final); la traza completa vive solo en la tabla `trazas` de la base, no exportada al repo. No dice "qué cambiaron después" de estos ataques |
| Ficha de gobernanza | `docs/gobernanza.md` | CUMPLE | Las 5 preguntas, con lo que el código hace. Para la pregunta "muéstrenme la línea" conviene citar línea: `app/api/rutas_operacion.py:55-62` (motivo ≥ 10, firma de la sesión) |
| Respuesta a la auditoría cruzada | `docs/respuesta_auditoria.md` | PARCIAL (riesgo de interpretación) | Responde la auditoría **interna** del 31-oct (agentes de IA). La rúbrica dice "cruzada" y "el reporte de auditoría que recibieron". En la clase 12 no se asignó auditoría entre equipos (no aparece en `transcript.md`), así que la decisión es defendible, pero el documento debe decirlo en una frase. Además cita `auditoria/2026-10-31_demo/*.md`, que **no** va en el ZIP |
| Cifras finales contra la línea base | `docs/decisiones.md` §13.1 y §13.2 | CUMPLE | Las cuatro cifras contra el 21-oct y el 31-oct, con fecha y explicación de por qué bajó el éxito (84,2 %). Valores verificados contra `lote_2026-11-08_2100.json` y `momento3_2026-11-09_*.json` |
| Presentación en vivo | guion local (fuera de git, correcto) | NO VERIFICABLE | Depende del ensayo |

### 1.2 Criterios

| Criterio | Evidencia | Estado | Qué falta |
|---|---|---|---|
| Funciona (excelente = lo usa alguien ajeno al equipo en la demo) | `docs/presentaciones/prueba-tercero.md` | NO CUMPLE aún | La hoja de registro está vacía. `docs/decisiones.md` §10 sigue en "PENDIENTE (equipo)" |
| Alcance | `docs/SPEC.md` §2 (9 renegociaciones) | PARCIAL | Faltan dos renegociaciones: (a) el viaje imposible no abre casos en vivo con Sparkov (`app/riesgo/flujo.py:41`, `VIAJE_IMPOSIBLE_ABRE_CASO = {"sparkov": False, ...}`), aunque RF2 lo pone en la banda crítica; (b) Kaggle ULB, que sí estaba en lo declarado (`pendientes` §3). La tabla no cita dónde se declaró la idea inicial (pitch del 9-oct en `docs/presentaciones/presentacion-fraude-bancario.html`, prueba de necesidad en `decisiones.md` raíz) |
| Necesidad del LLM | `docs/decisiones.md` §13.1 (71,4 % contra 61,8 % sin LLM; precisión 1,0 contra 0,385 en banda alta) | CUMPLE con contradicción | La tabla de §2 "Frontera de la IA" no se actualizó: dice "Bloqueo final: Humano; el agente solo propone" |
| Modelo de amenazas | `seguridad.md` §1-§2 | CUMPLE | Opcional: responder las 5 preguntas del reto 12 una por una (falta explícita "¿qué acciones son irreversibles?", que hoy está en gobernanza) |
| Ataque propio | `seguridad.md` §4 | CUMPLE con matiz | Exportar la traza completa de A1 a `eval/resultados/` y anotar qué se cambió después (por ejemplo, la regla 9 del prompt por el resumen en inglés) |
| Hardening (antes y después) | `seguridad.md` §5 | PARCIAL | Filas "Secretos" (llaves en `.env`, escáner del ZIP, `skip-worktree`, rotación pendiente) y "Salida a internet" |
| Ficha (5 preguntas verificables) | `gobernanza.md` | CUMPLE | Verificado: DELETE revocado (`app/db/roles.py:122`), 5 intentos/15 min (`app/api/sesion.py:37-38`), desbloqueo con motivo (`rutas_operacion.py:58`) |
| Supervisión humana exigida | `rutas_operacion.py:55-62`, lista `HERRAMIENTAS` sin desbloqueo (`app/agente/herramientas.py:282-320`) | CUMPLE | Citar las líneas en la ficha |
| Respuesta a la auditoría | `respuesta_auditoria.md` | CUMPLE | Todos los hallazgos con respuesta. El único "falta rotar" (A1) es una promesa abierta: si no se rota antes del 19-nov cae en "prometieron arreglos que no hicieron" |
| Cifras finales | `decisiones.md` §13.2 | CUMPLE | — |
| Uso de la evidencia | §13.2 "qué empeoró y por qué", trazas en los JSON del lote | CUMPLE | — |
| Sustentación | `docs/guia-de-estudio.md` §8 | NO VERIFICABLE | La guía §5 todavía responde con el M2 ("la decisión final es humana", `herramientas.py:211`, que hoy es otra función) |

### 1.3 Reemplazo hacia arriba (M1 y M2)

| Criterio | Sube si… | Estado |
|---|---|---|
| Método de trabajo (M1) | la spec gobernó y el registro de decisiones está vivo | PARCIAL: SPEC y PLAN sí gobernaron, pero `requisitos/`, `diseno/` y `validacion/` no tienen nada del M3 (último cambio 2026-10-21) y `docs/decisiones.md` arrastra contradicciones (§2) |
| Automatización del flujo (M1) | el skill sigue en uso, con historia | CUMPLE en el repo (`.claude/skills/`, `.claude/agents/`), pero **el ZIP no los incluye** |
| El agente (M2) | descripciones iteradas, límites justificados | PARCIAL: §11 de `decisiones.md` se quedó en `2026-10-21.4`; las versiones `2026-11-08.1` y `.2` solo están en `app/agente/prompts.py:25-27` |
| La aplicación (M2) | usable por un tercero sin explicación | NO CUMPLE aún (prueba con tercero vacía) |
| La medición (M2) | cifras finales con método | CUMPLE |

### 1.4 Lo que depende del equipo

| Pendiente | Evidencia hoy | Estado |
|---|---|---|
| Firmar los casos dorados | `eval/casos_dorados.json`: D1 a D8 con `verificado_por` y `como_se_verifico` en `null` | NO CUMPLE |
| Prueba con un tercero | `docs/presentaciones/prueba-tercero.md`: tablas vacías | NO CUMPLE |
| Rotar llaves | La copia local de `docs/prueba-companero-jeison.txt:42` todavía tiene una llave tipo `AQ.Ab…` y una `apikey_…`; `.env:9` (`sk-ant-…`) y `.env:11` (`AQ.Ab…`). Según la memoria del proyecto, la de Google es la misma en los dos archivos. `pendientes` #12 sigue en `[ ]` | NO VERIFICABLE (no hay registro de la rotación; si se rota la de Google hay que actualizar ambos archivos) |
| Prueba en el equipo de Jeison | `PLAN.md` T6.2 `[~]`; no existe `docs/verificacion-jeison.md` | NO VERIFICABLE |
| Tarifas en páginas oficiales | `pendientes` #6 `[ ]`; README §3 dice "hay que verificarlas antes de citarlas" | NO CUMPLE (y la frase deja el README como si estuviera sin terminar) |

---

## 2. Coherencia documentos ↔ código ↔ resultados

### 2.1 Cifras que cuadran (verificadas contra los JSON)

71,4 % / 61,8 % / 29,3 % / 34,9 %; 5,7 s de mediana y 8,2 s de máximo; precisión 0,90, recall 1,00
y 0,17 falsos por cada 1.000; 0,054 USD (0,0538), 0,0023 por triaje; 12 de 12; lote 84,2 %,
0,001749 USD y 6,8 s; umbrales 0,95 y 0,97 (`semilla/metricas_sparkov.json`: 0,948 y 0,966);
tarifas 0,10/0,50 y 0,30/2,50 (`app/config.py:60-61`); 90 s (`config.py:106`); 5 min de meta. En
todos estos valores coinciden el README, la SPEC, `decisiones.md`, seguridad, gobernanza, el PLAN y
la guía de estudio.

### 2.2 Contradicciones

| # | Dato | Ubicación A | Ubicación B (o el código) |
|---|---|---|---|
| C1 | Quién bloquea | `docs/decisiones.md:41` "Bloqueo final: Humano; el agente solo propone"; `:25-26` "la decisión solo existe cuando el analista la confirma" | `docs/SPEC.md:38`, `README.md:9-11`, `gobernanza.md` §1 |
| C2 | Número de herramientas | `docs/decisiones.md:151` "las seis"; `docs/guia-de-estudio.md:165` "Seis herramientas" | `app/agente/herramientas.py:282-320`: diez (4 de lectura, `registrar_decision`, `declarar_fuera_de_alcance` y 4 de triaje) |
| C3 | Prompt vigente | `docs/decisiones.md:291` "La versión vigente es `2026-10-21.4`" | `app/agente/prompts.py:27` `2026-11-08.2` |
| C4 | Supervisión humana en la guía | `docs/guia-de-estudio.md:228` "`registrar_decision` solo propone (`herramientas.py:211`)" y `:230` "por eso la decisión final es humana" | En el M3 la respuesta es el desbloqueo (`rutas_operacion.py:55`); la línea 211 hoy cae en `_obtener_score_y_umbrales` |
| C5 | Pruebas | README:24, `seguridad.md:11`, `SPEC.md:245`: 267 | `pytest --collect-only` en el contenedor (mismos archivos que el repo): **268 recolectadas**. Aclarar si una se salta o actualizar la cifra |
| C6 | Dónde se reportan las cifras | `SPEC.md:212` y `PLAN.md:155`: `docs/decisiones/semana14.md` | Ese archivo no existe; están en `docs/decisiones.md` §13 |
| C7 | Nombres de roles de la base | `SPEC.md:187`: `fraude_admin`, `fraude_app`, `fraude_agente` | `app/db/roles.py:7-11`: el dueño es el usuario `fraude` del compose (sigue siendo superusuario, solo migra); los roles son `<base>_app` y `<base>_agente` |
| C8 | Escáner de llaves | `SPEC.md:191` "ampliado a los formatos `apikey_…` y `AQ.…`" | `scripts/empaquetar_entrega.py:64` solo detecta `AQ.Ab…`; una llave `AQ.` seguida de otra cosa pasa (probado) |
| C9 | Modelo de respaldo | `CLAUDE.md:87`, `docs/guia-del-proyecto.md:86` y `:203`, `diseno/agente.md:6,28`, `validacion/app-analista.md:14`, `plan-construccion.md:446`: Gemini 3.1 Flash-Lite | `app/config.py:42`, README, `decisiones.md` §4: 3.5 Flash-Lite |
| C10 | Estado del plan | `PLAN.md` T6.3: "Falta: fusionar `momento3` en `main`, push"; "ZIP 196 archivos" | Ya está fusionado y subido (`01c429e`); el ZIP de hoy tiene 192 archivos |
| C11 | Decisiones abiertas | `SPEC.md:250-257`: tope por hora, canal y ventana "a cerrar antes del 15-nov" | El código ya las fijó: tope 30/h (`app/db/esquema.sql:291`), canal simulado, 90 s |
| C12 | Tiempo hasta el bloqueo en el JSON | README y `decisiones.md:360`: mediana 5,7 s, máximo 8,2 s (campo `segundos_reales_desde_la_compra_hasta_el_bloqueo`) | El mismo JSON trae `segundos_hasta_bloqueo` con mediana 6,6 s, p95 28 s y máximo 32 s, sin explicar en ningún documento. Una línea en §13.1 evita la pregunta |
| C13 | Métricas prometidas | `SPEC.md:142` "Se mide el tiempo hasta el desbloqueo"; `SPEC.md:220`; `pendientes` §9.3 | No hay valor reportado en `decisiones.md` §13 (la vista Supervisión sí lo calcula: `repositorio_acciones.py:288`). Tampoco se reporta F1 de los bloqueos (CLAUDE.md, condición 4: precisión, recall, F1 y AUC-PR). Con 9 de 10 y recall 1,00, F1 = 0,947 |
| C14 | Puerta de entrada al proyecto | `CLAUDE.md:7-9`: "el contexto completo está en `decisiones.md`" (la bitácora de la raíz) | README:284: "la consolidada está en docs/" |

### 2.3 Documentos desactualizados del M2 que confunden a quien clone

| Documento | Problema | Riesgo | Recomendación |
|---|---|---|---|
| `docs/presentaciones/comandos-demo.md` (31-oct) | `curl -X POST localhost:8000/api/demo/falla` sin sesión ni CSRF (hoy da 401/403), "136 pruebas", `SIN-000018`, "339 casos", ataques por `/preguntas/stream` sin sesión, enlace a `auditoria/` | **Alto**: el README:39 dice que en `docs/presentaciones/` está "el guion de la demo"; el profesor puede correr esto y concluir que la app falla | Reescribirlo para el M3 (con sesión) o sacarlo del repo y del ZIP |
| `docs/decisiones.md` | Título "(Momento 2)", "borrador consolidado del 2026-10-21", C1 a C3, §10 y §12 con "PENDIENTE (equipo)", §12 dice que el ZIP va sin `.joblib` | **Alto**: es el entregable de "cifras finales" | Actualizar encabezado, §1, §2, §6, §11 y §12, o poner al inicio una nota "§1-§12 describen el M2; lo vigente está en §13" |
| `docs/pendientes-y-momento3.md` | "Estado al 2026-10-21"; casillas `[ ]` en tareas ya hechas (login, límite de tasa, roles, SPEC, seguridad); frases como "Hoy la app usa el usuario `fraude`, que es superusuario" y "No hay límite de peticiones por minuto" | **Medio-alto**: contradice `seguridad.md` y está en el ZIP | Marcar lo cerrado con fecha o sacarlo del ZIP |
| `docs/guia-del-proyecto.md` (21-oct) | Se presenta como "la puerta de entrada", pero describe el M2 (sin puntuación en vivo, sin triaje, 3.1 Flash-Lite, §11 "Estado: Momento 2"); enlaza `prueba-companero-jeison.txt`, que no va en el ZIP | Medio: el README la recomienda como guía de arquitectura | Actualizar el diagrama y §11, o advertir en la primera línea que es del M2 |
| `docs/sesion-2026-10-24.md` | Bitácora de una sesión de trabajo; enlaza `guion-sustentacion-*.md` (ya no están en git) y `.claude/agents/` | Bajo-medio: ruido en `docs/` | Moverla a `auditoria/` o sacarla del ZIP |
| `validacion/motor-riesgo.md` | La primera pasada (líneas 1-280) dice que el elegido es Random Forest, con 1 089 casos; la segunda pasada (desde la 281) corrige a HistGB. `pendientes` #14 sigue abierto | Bajo: está explicado, pero hay que leer 300 líneas para saberlo | Una línea al inicio que remita a "Veredicto (segunda pasada)" |
| `decisiones.md` (raíz) y `plan-construccion.md` | Bitácoras históricas (454 y 469 líneas), con `docs/decisiones/semana07..10.md` que nunca existieron | Bajo: el README los marca como históricos | Nada, o una línea de encabezado "histórico, no vigente" |
| `CLAUDE.md` | C9 y C14; "Qué falta" es del M2 | Bajo | Actualizar dos líneas |
| `docs/guia-de-estudio.md` | "Los números de línea son del 2026-10-21"; §5 con respuestas del M2 (C4) | Medio para la sustentación | Corregir §5 o marcarla "M2" |

Enlaces o rutas que no existen en el clon: `docs/verificacion-jeison.md` (citado en `guia-de-estudio.md:267` y en `pendientes`),
`docs/decisiones/semana14.md` (SPEC y PLAN) y `docs/presentaciones/guion-sustentacion-*.md` (`sesion-2026-10-24.md`).
Dentro del ZIP además quedan sin destino: `auditoria/…` (respuesta a la auditoría, pendientes, comandos-demo),
`.claude/skills/` (README:287, guía del proyecto:215) y `prueba-companero-jeison.txt` (guía del proyecto).

---

## 3. Clon limpio (desde GitHub, en el scratchpad)

`git clone https://github.com/JhoanGruezo/deteccion-fraude-bancario-ia.git` → rama `main` en `01c429e`.

| Comprobación | Resultado |
|---|---|
| Tamaño | 19 MB en total; `.git` 9,8 MB (un pack de 9,61 MiB). Razonable |
| `semilla/` | Los 8 archivos, incluido `modelo_riesgo_sparkov.joblib` (5,15 MB; excepción en `.gitignore:13`) |
| `run.sh` | `100755` en git; LF en la copia de trabajo aunque `core.autocrlf=true` (`.gitattributes`: `*.sh eol=lf`) |
| `run.ps1` | CRLF y BOM UTF-8 (necesario para que PowerShell 5.1 lea las tildes) |
| `.gitattributes` | Presente: `.sh`, `.py`, `.sql` en LF; `.ps1` en CRLF; `.gz` y `.jpg` binarios |
| Finales de línea del resto | `docker-compose.yml`, `Dockerfile` y `.env.example` quedan en CRLF en Windows; comprobado que `docker compose config` limpia el `\r` de `.env` (sin efecto) |
| Imágenes | `python:3.12-slim` y `postgres:16-alpine` publican amd64 y arm64 (`docker manifest inspect`); sin `platform:` fijado. Las dependencias de `app/restricciones.txt` tienen ruedas aarch64. **No probado en una Mac real** |
| Lo ignorado que haría falta | Nada: `datos/` no se usa en tiempo de ejecución (`app/config.py:31` lee `semilla/`), `.env` es opcional (`required: false`) |
| Lo ignorado que **no** debe estar | `.env`, guiones y `*.zip` fuera. `docs/prueba-companero-jeison.txt` **sí** está versionado, en su versión sin llaves |

### Siguiendo el README como el profesor: pasos ambiguos

1. **Versión de Compose** (README:45): pide "Compose v2" y dice "probado con Compose v5.6.0". El
   `env_file` con `required: false` exige Compose 2.24 o superior; con uno más viejo el compose ni
   se lee. Escribir "Compose 2.24 o superior".
2. **Puerto ocupado** (README:105-106): sugiere cambiar el lado izquierdo de `ports`, pero
   `run.ps1:10` y `run.sh:12` esperan siempre `http://localhost:8000`: con el puerto cambiado, el
   script espera 180 s y termina en error aunque la app esté arriba.
3. **`run.ps1` en PowerShell 5.1**: `docker info *> $null` (línea 17) con
   `$ErrorActionPreference = "Stop"`. Comprobado en esta máquina: si un comando nativo escribe algo
   en stderr bajo esa combinación, PowerShell 5.1 aborta con `NativeCommandError`. Aquí `docker info`
   no escribe en stderr y el script funciona, pero en un Docker Desktop que imprima un `WARNING`, o
   con Docker apagado, el profesor vería un error rojo en lugar del mensaje amable. Lo mismo vale
   para `docker compose logs app 2>$null` (línea 72). Bajar `ErrorActionPreference` alrededor de
   esas dos líneas lo evita.
4. **Carpeta**: el README dice `cd deteccion-fraude-bancario-ia`; quien llega por el ZIP encuentra
   `fraude-bancario/`. Una línea para cada caso.
5. **Llaves**: "copie `.env.example` a `.env`" no dice el comando por sistema (`copy` en Windows).
   Si el profesor usa solo Gemini (como en clase), conviene decir que basta `GEMINI_API_KEY` y que
   el aviso "se usará solo Gemini" es normal.
6. **Credenciales**: si arrancó con `docker compose up` directo, tiene que ejecutar
   `--restablecer-claves`; está dicho, pero sin decir que la salida trae los dos usuarios.
7. **Demo, paso 3** ("Inyectar una compra: elija una tarjeta"): no dice en qué vista ni con qué botón.
8. **Evaluación** (README:200-206): `EVAL_USUARIO` y `EVAL_CLAVE` "en el entorno" sin la sintaxis
   (`$env:EVAL_USUARIO="supervisor"` en PowerShell, `export` en Bash); en macOS el comando suele ser
   `python3`.
9. **Tarifas** (README:133-136): "hay que verificarlas antes de citarlas como definitivas" queda
   como tarea sin hacer dentro del documento final.

---

## 4. ZIP (`scripts/empaquetar_entrega.py`)

Corrido con `--salida` hacia el scratchpad (el script lo permite):
`C:\Users\Jhoan\AppData\Local\Temp\claude\b3f7846d8f8bead5\39649491-73ed-479e-9412-4797394f9a25\scratchpad\zip\entrega_momento3_2026-11-14.zip`
→ **10,18 MB, 192 archivos, 0 coincidencias de llave, `run.sh` con 0755**, todo bajo `fraude-bancario/`.

| Qué | ¿Entra? |
|---|---|
| `app/`, `src/`, `scripts/`, `semilla/` (con el modelo), `eval/` (con `resultados/`), `docs/`, `requisitos/`, `diseno/`, `validacion/`; README, compose, `run.*`, `.env.example`, `.dockerignore`, `.gitattributes`, `CLAUDE.md`, `PLAN.md`, `decisiones.md`, `plan-construccion.md` | Sí |
| `.env`, `.env.*` (salvo el ejemplo) | No (excluido; además no está en la lista blanca) |
| `docs/prueba-companero-jeison.txt` | No (`ARCHIVOS_EXCLUIDOS`, línea 52): correcto, porque la copia local tiene llaves |
| `docs/presentaciones/guion-*.md` | No (`PREFIJOS_EXCLUIDOS`, línea 54) |
| `datos/`, `.venv/`, `.git/`, `__pycache__/`, `.pytest_cache/`, `*.pyc`, `*.csv`, otros `.joblib` | No |
| `.claude/` (skills y agentes) y `auditoria/` | **No**: el README, la respuesta a la auditoría y `comandos-demo.md` los citan. Para el criterio "Automatización del flujo" convendría incluir `.claude/skills/` y `.claude/agents/` (no tienen secretos) o decir en el README que están solo en el repo |
| `docs/pendientes-y-momento3.md`, `docs/sesion-2026-10-24.md`, `docs/presentaciones/comandos-demo.md` | Sí, y están desactualizados (§2.3) |

**Escáner de llaves.** Probado con cadenas sintéticas: detecta `sk-ant-` (20 o más caracteres
después del prefijo), `apikey_` (20 o más), `AIza` (30 o más) y `AQ.Ab` (20 o más). **No** detecta
`AQ.` seguido de algo distinto de `Ab`, ni un `apikey_` con punto en medio. Sobre los archivos reales,
el escáner sí encuentra las llaves de `.env:9` y `.env:11` y las dos de
`docs/prueba-companero-jeison.txt:42`; no aborta solo porque esos archivos ya quedan excluidos antes.
Sugerencia: `AQ\.[0-9A-Za-z_\-]{30,}`.

**Riesgo de diseño.** El ZIP se arma desde la copia de trabajo, no desde git: cualquier archivo sin
commitear dentro de una carpeta permitida entra. Hoy `git status` está limpio en esas carpetas, así
que el ZIP coincide con `main`. Armarlo justo después de `git status` limpio.

---

## 5. Redacción para el lector (el profesor)

**Lo que funciona.** Las primeras 40 líneas del README responden qué hace (párrafo de arriba), con
qué resultado (tabla de cifras) y dónde está cada cosa (tabla de documentos). La "Demo en tres
minutos" es justo lo que un evaluador necesita. `seguridad.md` y `gobernanza.md` son cortos,
concretos y citan archivos.

**Lo que estorba.**

- **Jerga sin definir en el README**: "banda crítica/alta", "triaje", "red de seguridad", "Sparkov",
  "regla del Momento 2", "IA caída". Una línea que defina las bandas ahorra la pregunta.
- **"29-35 %" sin contexto** (README:20): no dice que son dos escenarios (noche sin turno, cola de
  90 min); `decisiones.md` sí lo explica.
- **Historia de modelos en el README §3** (líneas 116-131): el relato 3.8 → 3.1 → 3.5 está repetido
  casi igual en `decisiones.md` §4. En el README basta una línea y el enlace.
- **Exceso de documentos en `docs/`**: 13 archivos, de los cuales 4 son de trabajo interno
  (`pendientes`, `sesion-2026-10-24`, la guía de estudio y `analisis-respuesta-fraude` mezclado con
  los entregables). Un lector no sabe cuáles son "la entrega". El README sí los ordena; falta marcar
  los internos como tales.
- **Huecos**: no hay una frase sobre qué pasa si el profesor no pone ninguna llave en la demo (la
  app dice "modo regla", pero el README no dice qué se pierde, por ejemplo la banda alta sin agente).

**Tiempo para entenderlo.** Con el README, un tercero entiende en 5 minutos qué hace y cómo
arrancarlo. Lo que no logra en 5 minutos es saber cuál documento es vigente si abre `docs/`
directamente: ahí lo frenan `decisiones.md` §1-§2 y `pendientes-y-momento3.md`.

---

## 6. Estado de git

| Comprobación | Resultado |
|---|---|
| `main` local = `origin/main` | Sí, los dos en `01c429e`; `momento3` también |
| `momento3-respaldo` | Solo local (`7741d81`). **No** está en el remoto (`git ls-remote`: solo `main` y `sesion-2026-10-24`). Es la única rama que contiene `guion-momento3.md` en su historia |
| Rama remota `sesion-2026-10-24` | Sigue publicada (`856aa2e`) y contiene 5 guiones del M2 (`guion-jeison.md`, `guion-jhoan.md`, `guion-pitch-presentacion.md`, `guion-sustentacion-*.md`) más la versión sin llaves del txt de Jeison. No tiene llaves. Si "los guiones no van al repositorio" es la regla, esa rama la contradice |
| Sin commitear | Solo `auditoria/2026-11-14_m3/` (esta auditoría). Ignorados: `.env`, guiones, `datos/`, cachés |
| `skip-worktree` | `docs/prueba-companero-jeison.txt` (marca `S`): la copia local con llaves difiere de la versionada sin llaves. Un `git update-index --no-skip-worktree` seguido de `git add -A` las publicaría |
| Llaves en el historial | `git log --all -p` sin coincidencias de `sk-ant-`, `apikey_`, `AIza` ni `AQ.` largos |

---

## 7. Acciones recomendadas, por prioridad

**Del equipo (no las puede hacer el código):**

1. Rotar las llaves de Anthropic y de Google; actualizar `.env` y la copia local del txt de Jeison;
   marcar `pendientes` #12 y A1 de `respuesta_auditoria.md` con la fecha.
2. Firmar D1 a D8 en `eval/casos_dorados.json` (`verificado_por`, `como_se_verifico`) y volver a correr la suite.
3. Hacer y registrar la prueba con un tercero (`prueba-tercero.md`) y, con los desbloqueos que
   haga, reportar el "tiempo hasta el desbloqueo" en `decisiones.md` §13.1.
4. Probar en el Windows de Jeison y, si se consigue, en una Mac.

**De documentación (menos de una hora en total):**

5. `docs/decisiones.md`: encabezado del M3; §2 (bloqueo), §6 (diez herramientas), §11 (versiones
   `2026-11-08.1` y `.2`), §10 y §12; F1 de los bloqueos; una línea sobre `segundos_hasta_bloqueo`.
6. Reescribir o retirar `docs/presentaciones/comandos-demo.md`.
7. `seguridad.md` §5: filas "Secretos" y "Salida a internet"; exportar la traza completa de A1.
8. `SPEC.md`: renegociación del viaje imposible en vivo; cerrar §9; corregir `semana14.md` y los
   nombres de roles.
9. `respuesta_auditoria.md`: una frase de que no hubo auditoría cruzada asignada y por eso se
   responde la interna.
10. Cerrar o sacar del ZIP `pendientes-y-momento3.md` y `sesion-2026-10-24.md`; incluir `.claude/`
    en el ZIP; ampliar el patrón `AQ.`; 267 → 268 (o explicar la diferencia).
11. `run.ps1`: tolerar stderr en `docker info` y `docker compose logs`; README: Compose ≥ 2.24 y
    advertir que el puerto distinto de 8000 obliga a abrir la URL a mano.
