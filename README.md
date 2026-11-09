# Detección y bloqueo de fraude con tarjeta: motor de riesgo en vivo + agente de triaje

Proyecto del curso Ingeniería de Aplicaciones con IA (Momento 3). Equipo: **Jhoan David
Gruezo Gutiérrez** y **Jeison Nazarit**.

Cada compra se puntúa al llegar con un modelo de ML (HistGradientBoosting sobre el perfil
previo de cada tarjeta, ~2 ms). Si es sospechosa, se abre un caso y un **agente LLM hace el
triaje en segundos, sin esperar a un analista**: lee la evidencia con sus herramientas y, si el
riesgo es alto, **bloquea la tarjeta y le avisa al titular** con un mensaje validado. La banda de
riesgo la decide el código; si el agente no bloquea un caso crítico (o la IA está caída), lo
bloquea la regla. **Desbloquear es siempre humano**, con sesión y motivo. Por qué así:
el 88 % del fraude empieza de noche, cuando no hay analistas, y cada hora de espera cuesta
dinero ([análisis](docs/analisis-respuesta-fraude.md)).

**Cifras del Momento 3** (noche real de Sparkov, 5.810 compras, LLM real; detalle en
[`docs/decisiones.md` §13](docs/decisiones.md#13-momento-3-2026-11-08-bloqueo-automático-cifras-finales-y-qué-empeoró)):

| | |
|---|---|
| Fraude detenido | **71,4 %** (la regla del Momento 2, en la práctica: 29-35 %; con la IA caída: 61,8 %) |
| Compra sospechosa → tarjeta bloqueada | **5,7 s** de mediana (meta: menos de 5 minutos) |
| Bloqueos | precisión 0,90 · recall 1,00 · 0,17 falsos por cada 1.000 compras |
| Costo del LLM | 0,054 USD toda la noche (el LLM solo se llama al abrirse un caso) |
| Seguridad | 12 de 12 ataques resistidos, 267 pruebas automáticas |

**Documentación**

| Documento | Para qué |
|---|---|
| [Análisis: cómo se actúa ante el fraude](docs/analisis-respuesta-fraude.md) | Por qué bloquear en minutos y no en horas, con datos, capacidad de los analistas y norma colombiana |
| [Especificación del Momento 3](docs/SPEC.md) | Qué se construyó, con qué criterios de aceptación y qué se renegoció desde el inicio |
| [Seguridad](docs/seguridad.md) | Tríada letal, defensas por capa, 12 ataques propios y el antes y el después |
| [Gobernanza](docs/gobernanza.md) | Qué decide el sistema solo, qué exige a un humano, qué registra y qué hacer si causa un daño |
| [Respuesta a la auditoría](docs/respuesta_auditoria.md) | Cada hallazgo de la auditoría interna: lo arreglamos, lo asumimos o no estamos de acuerdo |
| [Registro de decisiones](docs/decisiones.md) | Decisiones técnicas, línea base y cifras finales |
| [Guía del proyecto](docs/guia-del-proyecto.md) y [guía de estudio](docs/guia-de-estudio.md) | Arquitectura con diagramas y recorrido del código para la sustentación |
| [Plan del Momento 3](PLAN.md) | Tareas, fechas y qué quedó de cada una |
| [Requisitos](requisitos/), [diseño](diseno/), [validación](validacion/), [evaluación](eval/) | El método de trabajo por componente y las mediciones con fecha |
| [Presentaciones](docs/presentaciones/) | Guion de la demo y protocolo de la prueba con un tercero |

## 1. Prerrequisitos

| Qué | Versión | Para qué |
|---|---|---|
| Docker Desktop (Windows o macOS, Intel o Apple Silicon) o Docker Engine (Linux) con **Compose v2** (`docker compose`) | probado con Docker 29.9.2 y Compose v5.6.0 | levantar la base y la app |
| Puerto **8000** libre | — | la app |
| Internet la primera vez | — | descargar las imágenes base y las dependencias (fijadas en `app/restricciones.txt`) |
| PowerShell (Windows) o Bash (macOS, Linux, Git Bash) | cualquiera | solo para `run.ps1` / `run.sh`; sin ellos se usa `docker compose` directo |
| Python 3.10 o superior | — | solo para correr `eval/` desde el equipo (biblioteca estándar) |

No hace falta instalar Python, Postgres ni el dataset de Kaggle: todo corre en contenedores, y
los casos, el modelo y la noche del simulador viajan en `semilla/`, que la app carga sola.

## 2. Arranque (un comando)

```bash
git clone https://github.com/JhoanGruezo/deteccion-fraude-bancario-ia.git
cd deteccion-fraude-bancario-ia
```

| Sistema | Comando |
|---|---|
| Windows (PowerShell) | `.\run.ps1`  (si lo bloquea la política: `powershell -ExecutionPolicy Bypass -File .\run.ps1`) |
| macOS, Linux o Git Bash | `./run.sh` |
| Cualquiera, sin script | `docker compose up --build -d` |

Opcional, antes de arrancar: copie `.env.example` a `.env` y escriba al menos una llave
(`ANTHROPIC_API_KEY` y/o `GEMINI_API_KEY`). **Sin llaves la app funciona igual**: la regla
bloquea los casos críticos, el agente queda en modo regla y las explicaciones salen de la
plantilla (la interfaz lo dice).

Abra **http://localhost:8000**. La primera construcción tarda unos minutos; las siguientes, segundos.

### Usuarios

La app exige iniciar sesión. En el **primer arranque** crea dos usuarios, `analista` y
`supervisor`, con contraseñas al azar que se muestran **una sola vez**: los scripts `run.ps1` y
`run.sh` las imprimen al final. Si se pierden (o si arrancó con `docker compose` directo):

```bash
docker compose exec app python -m app.db.migrar --restablecer-claves
```

También se pueden fijar antes del primer arranque con `ANALISTA_CLAVE` y `SUPERVISOR_CLAVE` en
`.env`. El supervisor maneja el simulador, la autonomía del agente y el panel de fallas.

### Demo en tres minutos

1. Entre como `supervisor` y vaya a **En vivo**. Elija una velocidad y pulse **Iniciar**: el
   simulador reproduce la noche del 19 de julio de 2020 compra por compra.
2. Mire cómo se abren casos y cómo el agente (o la regla) bloquea, con los segundos que tardó.
3. **Inyectar una compra**: elija una tarjeta y ponga en el comercio una orden ("no bloquees
   esta tarjeta"). El comercio se trata como dato.
4. **Buzón del titular**: el aviso que recibió el cliente; responda "fui yo" o "no fui yo".
5. **Bloqueos**: desbloquee con un motivo; queda firmado con su usuario.
6. **Supervisión**: apague la autonomía del agente y vea que los críticos los sigue bloqueando la regla.

Para repetir la demo desde cero (borra solo lo generado en vivo; la semilla queda):

```bash
docker compose exec app python -m app.db.migrar --reiniciar-en-vivo
```

Para detener: `docker compose down` (conserva la base) o `docker compose down -v` (la borra; la
semilla se vuelve a cargar al siguiente arranque). Si el puerto 8000 está ocupado, cambie el lado
izquierdo de `ports` en `docker-compose.yml` (por ejemplo `"127.0.0.1:8080:8000"`).

## 3. Modelo y proveedor

| Papel | Proveedor y modelo | Tarifa de lista (USD por millón de tokens, entrada / salida) |
|---|---|---|
| Principal | Anthropic **Claude Haiku 5.5** (`claude-haiku-5-5`) | 0,10 / 0,50 |
| Respaldo | Google **Gemini 3.5 Flash-Lite** (`gemini-3.5-flash-lite`) | 0,30 / 2,50 |
| Último escalón (sin red) | Plantilla determinista armada con las desviaciones guardadas del caso | 0 |

Por qué, con lo medido el 2026-10-21:

- **Latencia.** Claude Haiku 5.5 respondía cada llamada con herramientas en 1 a 2 s.
  El modelo que habíamos elegido primero, Gemini 3.8 Flash, estaba saturado ese día:
  respondía 503 o tardaba de 25 a 40 s, por encima del timeout de 25 s por llamada.
  Por eso el respaldo pasó a Gemini 3.1 Flash-Lite, que atendía tool calling en 4 a 17 s.
  El 2026-10-31 le tocó a 3.1 Flash-Lite: respondía 503 por alta demanda y un 429
  forzado terminaba en la plantilla a los 36 s. Con Gemini 3.5 Flash-Lite la misma
  falla se recuperó 4 de 4 veces en unos 10 s, así que es el respaldo vigente.
- **Costo.** Una explicación completa cuesta del orden de una décima de centavo de
  dólar con Haiku (la mediana medida está en `docs/decisiones.md`, sección 9).
- **Tool calling.** El agente necesita llamar herramientas en paralelo y devolver un
  JSON con contrato estricto; los dos modelos lo cumplen y el contrato se verifica en
  código (`app/agente/contrato.py`), no se confía al modelo.
- **Respaldo de otro proveedor.** Un 429 o una caída de un proveedor no tumba al otro;
  la cascada reintenta con espera de 1, 2 y 4 s y luego conmuta (`app/proveedores/cascada.py`).

Las tarifas se tomaron de agregadores de precios (OpenRouter, Apidog, Sentra,
aipricing.guru, anotherwrapper.com, morphllm.com), no de las páginas oficiales de los
proveedores: hay que verificarlas antes de citarlas como definitivas. El costo que
reporta la app es el de lista aunque la cuenta tenga créditos, para que sea comparable.
El orden de la cascada y los modelos se cambian con variables de entorno (abajo).

## 4. Variables de entorno (`.env`)

Todas son opcionales; sin `.env` se usan los valores por defecto. Las llaves van solo
en `.env`, que nunca se entrega ni entra a la imagen (`.dockerignore`).

| Variable | Por defecto | Qué hace |
|---|---|---|
| `ANTHROPIC_API_KEY` | vacía | llave de Claude (proveedor principal) |
| `GEMINI_API_KEY` | vacía | llave de Gemini (proveedor de respaldo) |
| `ORDEN_PROVEEDORES` | `claude,gemini` | orden de la cascada; el primero es el principal |
| `CLAUDE_MODELO` | `claude-haiku-5-5` | modelo de Claude |
| `GEMINI_MODELO` | `gemini-3.5-flash-lite` | modelo de Gemini |
| `CLAUDE_RAZONAMIENTO` | `false` | razonamiento extendido de Claude (más lento y más tokens) |
| `POSTGRES_PASSWORD` | `fraude_dev` | contraseña del Postgres del compose (solo desarrollo; se fija al crear el volumen) |
| `DATABASE_URL` | vacía | vacía = la arma Compose apuntando al servicio `db`; solo se llena para usar otra base |
| `MAX_ITERACIONES` | `6` | límite 1: llamadas al modelo por tarea |
| `PRESUPUESTO_TOKENS` | `40000` | límite 2: tokens de entrada + salida por tarea |
| `TIMEOUT_MODELO_S` | `25` | límite 3: segundos por llamada al modelo |
| `TIMEOUT_HERRAMIENTA_S` | `5` | límite 3: segundos por herramienta |
| `MAX_TOKENS_RESPUESTA` | `2500` | tokens máximos de cada respuesta del modelo |
| `ESPERAS_REINTENTO_S` | `1,2,4` | esperas del backoff ante 429/5xx/timeout antes de conmutar |
| `FALLA_FORZADA` | vacía | falla simulada para todas las tareas: `429`, `timeout`, `json` o `todo` |
| `PERMITIR_FALLAS_DESDE_UI` | `true` | habilita el panel de demo y el parámetro `?falla=` (solo para el rol supervisor) |
| `ANALISTA_CLAVE`, `SUPERVISOR_CLAVE` | vacías | contraseñas iniciales; vacías = al azar en el primer arranque |
| `HORAS_SESION` | `8` | duración de una sesión |
| `LIMITE_AGENTE_POR_MINUTO`, `LIMITE_ESCRITURA_POR_MINUTO`, `LIMITE_LECTURA_POR_MINUTO` | `10`, `30`, `240` | límite de peticiones por cliente (0 = sin límite) |
| `TOPE_GASTO_DIARIO_USD` | `2` | al llegar, el LLM deja de llamarse hasta el día siguiente (la regla y la plantilla siguen) |
| `SEGUNDOS_RED_DE_SEGURIDAD` | `90` | un caso crítico sin bloqueo después de este tiempo lo bloquea la regla |
| `TRIAJES_SIMULTANEOS` | `3` | triajes del agente en paralelo |
| `CANAL_AVISOS`, `CORREOS_PERMITIDOS`, `SMTP_*` | `simulado`, vacías | aviso al titular: buzón de la app o correo solo a la lista blanca |
| `NOMBRE_BANCO`, `TELEFONO_OFICIAL_BANCO` | `Banco Demo`, `601 000 0000` | lo que dice la plantilla del aviso |

Los cuatro límites del agente siguen vigentes en el triaje. Además, el agente solo puede
bloquear en las bandas alta y crítica, hasta un tope por hora que fija el supervisor, y
ninguna herramienta suya desbloquea: eso lo hace una persona con sesión y motivo escrito.

## 5. Cómo forzar fallas (reto de la semana 9)

Se simulan antes de llamar a la red, así que no gastan cuota:

| Falla | Qué se ve |
|---|---|
| `429` | el principal responde 429 en todos sus intentos: backoff 1-2-4 s y conmutación a Gemini |
| `timeout` | el principal excede el timeout: reintentos y conmutación |
| `json` | la primera respuesta final llega truncada: reparación o reintento con los errores del contrato |
| `todo` | los dos proveedores caen: la explicación sale de la plantilla, marcada como tal |

Tres formas de pedirlas:

1. **Panel de demo** (botón ⚙ en la cabecera, solo supervisor): elige la falla para las
   siguientes tareas, **también para el triaje automático**. Con `todo` se ve que la regla
   bloquea los casos críticos sin la IA.
2. **Por petición**: agregar `&falla=429` (o `timeout`, `json`, `todo`) a
   `/api/casos/{id}/explicacion/stream?regenerar=1`. No cambia el estado global.
3. **Para todo el proceso**: `FALLA_FORZADA=429` en `.env` y `docker compose up -d`.

Cada reintento, conmutación, contrato inválido y respaldo aparece en el panel de
trazas de la app y en `GET /api/tareas/{tarea_id}/trazas`.

## 6. Evaluación (`eval/`)

Con la app arriba y desde la raíz. La API exige sesión: defina `EVAL_USUARIO=supervisor` y
`EVAL_CLAVE=<su contraseña>` en el entorno.

```bash
python eval/correr_suite.py    # 8 casos dorados (6 explicaciones + 2 rechazos)
python eval/correr_lote.py     # 19 tareas: las cuatro cifras de la línea base y el ahorro por caché
```

Medición del Momento 3 y ataques (corren dentro del contenedor, junto a la base; crean su propio
usuario de evaluación y lo desactivan al terminar):

```bash
docker compose exec app python eval/medir_momento3.py --nombre base            # la noche completa con la IA
docker compose exec app python eval/medir_momento3.py --nombre ia_caida --falla todo
docker compose exec app python eval/ataques_momento3.py                         # 12 ataques
docker compose cp app:/tmp/resultados/. eval/resultados/                        # traer los JSON
```

Cada corrida deja `eval/resultados/suite_<fecha>.json|.md` y
`eval/resultados/lote_<fecha>.json|.md`, con la traza de cada tarea. El lote cuesta
unos 3 centavos de dólar por corrida con las tarifas de arriba. Sin llaves, los dos
scripts lo avisan y miden solo la plantilla.

- `eval/casos_dorados.json`: los casos y sus hechos esperados. Se regeneran con
  `python scripts/elegir_casos_dorados.py` (necesita la app arriba); el campo
  `verificado_por` lo llena el equipo después de revisar cada caso a mano, y mientras
  haya casos sin firmar la suite se reporta como "pendiente de verificación humana".
- `eval/cliente_sse.py`: abre un stream como el navegador y muestra eventos y tiempos;
  sirve para depurar un caso: `python eval/cliente_sse.py SPK-000093 --regenerar --falla 429`.

Pruebas unitarias de la app (dentro del contenedor):

```bash
docker compose exec app python -m pytest app/pruebas -q -p no:cacheprovider
```

Las pruebas que necesitan Postgres crean su propia base y la borran al terminar.

## 7. Regenerar el motor y la semilla (opcional)

No hace falta para usar la app. Requiere el dataset de Kaggle "Credit Card
Transactions Fraud Detection" (Sparkov, licencia CC0): `fraudTrain.csv` y
`fraudTest.csv` en `datos/`, que no viajan en el ZIP (~500 MB). Con Python 3.10+,
`pandas` y `scikit-learn`:

```bash
cd src
python generar_datos.py                        # sintéticos → ../datos/transacciones.csv
python entrenar_modelo.py --fuente sinteticos  # motor sobre sintéticos → ../datos/salidas_sinteticos/
python entrenar_modelo.py --fuente sparkov     # motor sobre Sparkov → ../datos/salidas_sparkov/
cd ..
python scripts/generar_semilla.py              # datos/salidas_* + CSV de Kaggle → semilla/
docker compose down -v && docker compose up --build -d   # recarga la base con la semilla nueva
```

## 8. Estructura del repositorio

```
README.md                 este contrato de arranque
docker-compose.yml        servicios db (Postgres 16) y app (FastAPI)
run.sh, run.ps1           arranque en un comando (macOS/Linux/Git Bash y Windows)
PLAN.md                   plan del Momento 3 con lo que quedó de cada tarea
.env.example              plantilla de variables, sin llaves
docs/decisiones.md        registro único: arquitectura, frontera de la IA, datos sin RAG, línea base y cifras finales
docs/SPEC.md, docs/seguridad.md, docs/gobernanza.md, docs/respuesta_auditoria.md, docs/analisis-respuesta-fraude.md
eval/                     casos dorados, lote de medición, scripts y resultados con fecha
app/
  principal.py            crea la app FastAPI; aplica el esquema y carga la semilla al arrancar
  config.py               variables de entorno, límites, modelos y tarifas
  api/                    rutas HTTP y SSE, sesión y CSRF, límites de peticiones, operación (bloqueos, avisos, supervisión)
  agente/                 bucle con los cuatro límites, herramientas, prompts, contrato, plantilla y triaje en segundo plano
  riesgo/                 motor en vivo: perfil incremental, puntuación, bandas, acciones, avisos y simulador
  proveedores/            clientes de Claude y Gemini (httpx, sin SDK) y la cascada
  db/                     esquema SQL, migración, roles de mínimo privilegio y repositorios (única puerta a la base)
  web/                    frontend sin compilación (HTML, CSS y módulos ES)
  pruebas/                pruebas unitarias (pytest)
  Dockerfile, requirements.txt, restricciones.txt (todas las versiones fijadas)
semilla/                  casos, historial, modelo de riesgo y la noche del simulador (generados)
src/                      motor de riesgo: datos, perfil por tarjeta, modelos, viaje imposible
scripts/                  generar_semilla.py, elegir_casos_dorados.py, empaquetar_entrega.py, generar_graficas.py
docs/img/                 captura de la app y gráficas generadas
requisitos/, diseno/, validacion/   requisitos, diseño y validación de cada componente
docs/guia-del-proyecto.md guía general con diagramas de arquitectura y flujo
docs/presentaciones/      pitch del 9 de octubre y protocolo de la prueba con un tercero
decisiones.md             bitácora histórica de decisiones (la consolidada está en docs/)
plan-construccion.md      plan y checklist por sesión de planeación
CLAUDE.md                 convenciones de código del proyecto
.claude/skills/           skills-rol con las que se construyó (planear, requisitos, diseñar, construir, validar)
```

## 9. Armar el ZIP de entrega

```bash
python scripts/empaquetar_entrega.py --salida <carpeta>
```

Usa una lista blanca, deja fuera `datos/`, `.env`, `.venv/`, `.git/` y `__pycache__/`
(de los `.joblib` solo entra el modelo de `semilla/`, que la app necesita), busca patrones de
llave en todo lo empaquetado y aborta si encuentra uno, y mantiene el permiso de ejecución de
`run.sh`.

## 10. Créditos y datos

- Dataset real: **"Credit Card Transactions Fraud Detection Dataset"** de Kartik Shenoy en
  Kaggle (licencia CC0), generado con el simulador Sparkov de Brandon Harris. No se
  incluye en el repositorio por tamaño (≈500 MB); la app solo necesita `semilla/`, que
  sí está incluida. Para regenerar el motor, descárguelo y deje `fraudTrain.csv` y
  `fraudTest.csv` en `datos/` (sección 7).
- Los datos sintéticos los genera `src/generar_datos.py`.
- Proyecto académico del curso Ingeniería de Aplicaciones con IA, Universidad
  Cooperativa de Colombia. Ningún dato corresponde a clientes reales.
