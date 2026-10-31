# Revisión de seguridad de la aplicación: 2026-10-31, día de la sustentación

**Alcance:** la aplicación (API FastAPI, frontend `app/web/`, repositorio de datos, Docker, empaquetado y git). No cubre el prompt del LLM, que revisa otro auditor.
**Método:** lectura del código y pruebas en vivo contra `http://localhost:8000`, sin reiniciar nada ni tocar `.env`. No se modificó ningún archivo del proyecto; este informe es lo único escrito.
**Veredicto corto:** el código de la app está bien defendido: SQL parametrizado, frontend sin `innerHTML` y errores sin trazas. Los riesgos reales están fuera del código: un archivo versionado con llaves en la copia de trabajo de un repo público, y la app expuesta en la red sin autenticación y con el panel de demo encendido.

---

## Huella que dejó esta auditoría (leer antes de la demo)

- **Escribí una sola decisión**, la `id=1` en el **último caso de la bandeja (`SIN-000016`)**, con acción `escalar`:
  - analista: `<img src=x onerror=alert("xss-analista")>`
  - comentario: `AUDITORIA-XSS <script>alert("xss-comentario")</script><b>negrita</b> <a href="javascript:alert(1)">enlace</a>`
  - Efecto: `SIN-000016` pasó de `pendiente` a `escalado`, y los contadores de la cabecera muestran 1 escalado.
- **La decisión `id=2` (`SIN-000044`, `confirmar_bloqueo`, 18:26:54) no es mía:** se creó desde otra pestaña de la app mientras auditaba.
- Para volver `SIN-000016` a su estado original (si lo quieren; no lo ejecuté porque borra un dato):
  ```sql
  delete from decisiones where id = 1;
  update casos set estado = 'pendiente' where id_caso = 'SIN-000016';
  ```
  (con `docker compose exec -T db psql -U fraude -d fraude -c "…"`).
- **Panel de demo:** no lo usé para cambiar el estado. El único POST a `/api/demo/falla` fue con `text/plain` y un tipo inválido, y respondió 422. Al terminar, `/api/salud` muestra `falla_forzada: ""`.

---

## Hallazgos por gravedad

### CRÍTICO

Ninguno. No encontré llaves publicadas, inyección explotable ni ejecución de código.

### ALTO

**A1. Llaves reales en un archivo versionado, modificado y no ignorado, en un repo público.**
- Evidencia: `docs/prueba-companero-jeison.txt` está en el índice (`git ls-files`) y aparece en `git status` como `M`. El repo `origin` es `github.com/JhoanGruezo/deteccion-fraude-bancario-ia`, público.
- En la copia de trabajo, el diff contiene 1 línea con patrón de llave. Los patrones del empaquetador encuentran 1 coincidencia `apikey_…` y 1 `AQ.Ab…`.
- `git check-ignore` no lo ignora: ni `.gitignore` ni `.git/info/exclude` lo cubren, y no hay hook pre-commit.
- Lo que sí está bien hoy: `HEAD:docs/prueba-companero-jeison.txt` tiene 0 coincidencias, y `git log --all -p` también tiene 0 en todo el historial. Las llaves todavía no se publicaron.
- Riesgo: hoy se están haciendo commits (deck, guiones). Un `git add -A`, `git add docs/` o `git commit -a` las publica. El README las enlaza en la línea 28, así que el archivo también se va a querer actualizar.
- Efecto colateral: `scripts/empaquetar_entrega.py` incluye `docs/` y **aborta** mientras ese archivo tenga las llaves. Eso es lo correcto, pero hoy no se puede regenerar el ZIP sin sacarlas. Los ZIP ya armados (`entrega_momento2_2026-10-21.zip` y `…-10-30.zip`) los revisé: no tienen llaves ni `.env`.
- Corrección mínima (hoy, sin tocar código):
  1. `git update-index --skip-worktree docs/prueba-companero-jeison.txt`. Es local, se revierte con `--no-skip-worktree` y hace que git ignore los cambios de ese archivo.
  2. Mejor aún: mover las llaves a un archivo no versionado (por ejemplo `docs/llaves-jeison.local.txt`, más la regla `*.local.txt` en `.gitignore`) y dejar el versionado sin ellas.
  3. Después de la sustentación, rotar las dos llaves. Es el pendiente 12 de `docs/pendientes-y-momento3.md`.

**A2. App publicada en todas las interfaces, sin autenticación y con el panel de demo encendido por defecto.**
- Evidencia:
  - `docker-compose.yml:40` publica `"8000:8000"`, y `netstat` muestra `0.0.0.0:8000` y `[::]:8000` en LISTEN.
  - No hay login (esperado en M2).
  - `app/config.py:83` deja `PERMITIR_FALLAS_DESDE_UI` en `True` por defecto, igual que `.env.example:45`; `/api/salud` responde `"panel_demo": true`.
- Riesgo concreto para hoy: cualquiera en la misma red del aula (Wi-Fi de la universidad) que llegue al puerto 8000 puede hacer cuatro cosas:
  - poner `POST /api/demo/falla {"tipo":"todo"}` a mitad de la demo (`app/api/rutas_sistema.py:145-160`);
  - registrar decisiones con cualquier nombre y cambiar el estado de cualquier caso (`POST /api/casos/{id}/decisiones`);
  - gastar crédito del LLM con `GET /api/casos/{id}/explicacion/stream?regenerar=true` en bucle, porque no hay límite de tasa;
  - leer todos los casos.
- El Firewall de Windows puede estar bloqueando el acceso entrante, pero no lo verifiqué y no conviene depender de eso.
- Corrección mínima (hoy): publicar solo en localhost con `ports: ["127.0.0.1:8000:8000"]` y luego `docker compose up -d`, que recrea solo `app` porque cambió su definición. Hacerlo **antes** de empezar, no durante la demo. Si se presenta desde otro equipo, no aplica y hay que quedarse con el riesgo.

### MEDIO

**M1. CSRF: la API acepta POST sin `Content-Type` como JSON y no revisa `Origin`.**
- Evidencia:
  - `POST /api/casos/SIN-000016/decisiones` con la cabecera `Content-Type:` vacía y el cuerpo JSON se procesa: responde 422 "Elige una acción válida…", lo que prueba que leyó el JSON.
  - Con `text/plain` lo rechaza (422 "revisa: body").
  - Un `fetch(url, {method:"POST", body:new Blob([json])})` desde cualquier página es una petición "simple": no hay preflight y el navegador no manda `Content-Type`.
  - No hay CORS (bien: nadie de afuera lee las respuestas), pero el POST igual se ejecuta.
- Riesgo: aunque el puerto quede solo en 127.0.0.1, una página maliciosa abierta en el navegador del analista puede registrar decisiones o cambiar la falla forzada.
- Corrección (M3): un middleware que rechace con 415 los métodos POST/PUT/DELETE sin `Content-Type: application/json` y con un `Origin` distinto del propio, más tokens de sesión cuando llegue el login.

**M2. Identidad del analista autodeclarada y flujo de decisiones sin reglas de gobernanza.**
- Evidencia:
  - `app/api/rutas_casos.py:59-69` solo exige un texto no vacío de hasta 80 caracteres. Un nombre de solo caracteres invisibles (`"​​"`) o de control (`"\u0007\u001b[31m"`) **pasa la validación**: con un caso inexistente responde 404, no 422.
  - `app/db/repositorio.py:519-531` (`registrar_decision`) permite cualquier número de decisiones por caso; la vigente es la última. Eso es intencional, pero un `bloqueo_confirmado` lo revierte cualquiera con `descartar`, sin rol ni motivo obligatorio.
  - Una decisión manual **no cierra las propuestas pendientes** del agente sobre ese caso. Confirmar después una de esas propuestas pisa la decisión manual sin aviso.
  - La base no tiene `CHECK` de largo ni de nombre no vacío en `decisiones.analista` (`app/db/esquema.sql:124-132`): esas reglas solo viven en la API.
- Corrección (M3):
  - analista tomado de la sesión autenticada, no de un campo libre;
  - en `registrar_decision`, marcar como `rechazada` (o `obsoleta`) las propuestas pendientes del caso dentro de la misma transacción;
  - pedir comentario obligatorio para revertir un bloqueo;
  - `check (length(btrim(analista)) between 1 and 80)`;
  - filtrar las categorías Unicode `Cc` y `Cf` en el nombre.

**M3. Gasto del LLM y fallas forzadas sin límite por cliente.**
- Evidencia:
  - `app/api/rutas_agente.py:48-64`: `regenerar=true` siempre va al proveedor y nada limita las tareas concurrentes ni la tasa.
  - `app/api/rutas_agente.py:33-45`: con el panel activo, cualquier petición puede añadir `?falla=429|timeout|json|todo` a su propio stream.
  - Esa falla queda en `tareas_agente.falla_forzada` y entra en `/api/metricas` (tasa de éxito y recuperación). Las métricas de la sustentación se pueden ensuciar desde afuera.
- Corrección (M3): un semáforo global de tareas del agente (por ejemplo 3), un límite por IP para `regenerar`, `PERMITIR_FALLAS_DESDE_UI=false` por defecto y métricas que excluyan las tareas con falla forzada o las muestren aparte.

### BAJO

**B1. Byte NUL produce 500.** `GET /api/casos/%00`, `GET /api/casos?q=%00`, `GET /api/casos/%00/historial`, `GET …/%00/explicacion/stream` y `POST /api/casos/%00/decisiones` responden 500 con la referencia (`psycopg.DataError: PostgreSQL text fields cannot contain NUL`, visto en el log del contenedor). No filtra nada, pero ensucia el log y la respuesta debería ser 404 o 422. Corrección (M3): `id_caso: str = Path(pattern=r"^[A-Z]{3}-\d{6}$")` y rechazar `\x00` en `q`, `analista`, `comentario` y la pregunta.

**B2. Comodines de `LIKE` sin escapar.** `app/db/repositorio.py:143-151`: `q=%` o `q=_` devuelven todos los casos. Es inofensivo porque la bandeja ya los muestra todos y el oráculo de los 4 dígitos está cerrado (`q=0193` solo hace coincidencia exacta), pero conviene escapar `%`, `_` y `\` y usar `ilike … escape '\'`.

**B3. Documentación de la API pública.** `/docs`, `/redoc` y `/openapi.json` responden 200 (`app/principal.py:334-339`). Corrección (M3): `FastAPI(docs_url=None, redoc_url=None, openapi_url=None)` fuera de desarrollo.

**B4. Sin cabeceras de seguridad.** `GET /` solo trae `server`, `cache-control` y `content-type`: no hay `Content-Security-Policy`, `X-Frame-Options`/`frame-ancestors`, `X-Content-Type-Options` ni `Referrer-Policy`. El diálogo de confirmación de bloqueo se podría enmarcar (clickjacking). Corrección (M3): un middleware de 10 líneas con `default-src 'self'; frame-ancestors 'none'`. Ojo: `index.html` tiene un `<script>` inline de tema, que necesita un hash en la CSP.

**B5. Dependencias.**
- `app/requirements.txt` fija las 6 directas (bien), pero las transitivas no están bloqueadas: dentro del contenedor quedaron `starlette 0.46.2`, `pydantic 2.14.1`, `anyio 4.15.1`, etc. Cada build puede traer otras versiones.
- `starlette 0.46.2` está en el rango afectado por un aviso de denegación de servicio con cabeceras `Range` en `FileResponse`/`StaticFiles`, corregido en 0.49.1 (CVE-2025-62727, según recuerdo; confirmarlo con `pip-audit`). La app usa `StaticFiles` y acepta `Range` (responde 206). Subirlo exige actualizar FastAPI, porque 0.115.x limita Starlette a menos de 0.47.
- `pytest` y `app/pruebas/` entran en la imagen de producción (`app/Dockerfile:16-18`).
- Corrección (M3): `pip-audit -r app/requirements.txt`, un archivo de restricciones o lock (`pip-compile`), FastAPI y Starlette actualizados, y `requirements-dev.txt` para pytest.

**B6. Sin tope de tamaño de cuerpo.** Un POST de 8 MB se lee y se parsea (422 en 35 ms). Riesgo bajo, pero conviene limitarlo en un proxy o middleware (por ejemplo, 64 KB).

**B7. Ignorados incompletos.**
- `.gitignore` y `.dockerignore` cubren `.env`, pero no `.env.*` (por ejemplo `.env.local`); el empaquetador sí los excluye.
- `.dockerignore` no excluye `docs/`: el archivo con llaves viaja en el contexto de build al daemon. **No entra a la imagen:** el Dockerfile solo copia `app/` y `semilla/`, y `find / -name ".env*"` dentro del contenedor no encontró nada.
- Corrección: agregar `.env.*` y `!.env.example` a ambos, y `docs/` a `.dockerignore`.

**B8. Contraseña de Postgres por defecto (`fraude_dev`) en `docker-compose.yml:16`.** Es pública en el repo. El riesgo es bajo porque la base no se publica en el host (5432 no escucha en el anfitrión). Para M3, la contraseña debe salir obligatoriamente de `.env` (`${POSTGRES_PASSWORD:?falta}`).

---

## (a) Arreglar ANTES de la sustentación de hoy (cambios pequeños y seguros)

| # | Qué | Cómo | Riesgo del cambio |
|---|-----|------|-------------------|
| 1 | A1: que el archivo con llaves no se pueda commitear | `git update-index --skip-worktree docs/prueba-companero-jeison.txt`, o mover las llaves a un archivo `.local.txt` ignorado. Antes de cada commit de hoy: `git diff --cached \| grep -cE "apikey_\|AQ\.Ab\|sk-ant-\|AIza"` debe dar 0 | Nulo: no toca la app |
| 2 | A2: no exponer la app al Wi-Fi del aula | `docker-compose.yml:40` → `"127.0.0.1:8000:8000"` y `docker compose up -d` **antes** de la demo (comprobar `/api/salud`). Si no se quiere tocar nada: al menos no conectarse a la red del aula o confirmar que el firewall bloquea el 8000 | Bajo: recrea solo el contenedor `app` |
| 3 | Dejar limpia la bandeja | Decidir si `SIN-000016` (mi prueba) y `SIN-000044` (de otra pestaña) quedan así o se revierten con el SQL de arriba. Los contadores ya no dicen "339 pendientes" | Nulo |

Lo demás no lo cambiaría hoy: cualquier cambio de código obliga a reconstruir la imagen y volver a probar la demo.

## (b) Para el Momento 3 (seguridad y gobernanza)

1. Autenticación y roles (analista o supervisor). El nombre del analista sale de la sesión; revertir un bloqueo exige rol y comentario (M2).
2. CSRF: exigir `Content-Type: application/json` y comprobar `Origin`, más token de sesión (M1).
3. Propuestas pendientes que se cierran al haber decisión manual; `CHECK` en la base para el analista (M2).
4. Límite de tasa y concurrencia del agente; panel de demo apagado por defecto; métricas sin tareas forzadas (M3).
5. Validación estricta de `id_caso` y rechazo de NUL y caracteres de control (B1, M2); escape de `LIKE` (B2).
6. Cabeceras de seguridad y CSP; `docs_url=None` (B3, B4); tope de cuerpo (B6).
7. Cadena de suministro: lock de dependencias, `pip-audit` en CI, FastAPI y Starlette actualizados, imagen sin pytest (B5).
8. Higiene de secretos: rotar las dos llaves (pendiente 12); hook pre-commit o `gitleaks` con los mismos 5 patrones del empaquetador; `.env.*` en los ignorados; `docs/` fuera del contexto de Docker (B7); contraseña de Postgres obligatoria (B8).

## (c) Lo que ya está bien y se puede defender

- **Inyección SQL: no hay.**
  - Todas las consultas de `app/db/repositorio.py` usan `%s` o `%(nombre)s`.
  - Los únicos f-strings interpolan cosas que no vienen del usuario: el `ORDER BY`, elegido de una lista cerrada (línea 155); las columnas de `cerrar_tarea`, que salen de la lista blanca `METRICAS_TAREA` (líneas 322-330); y la constante `_COLUMNAS_PROPUESTA`.
  - Probado: `q=' OR '1'='1`, `q=1'; drop table casos;--`, `orden=score desc; select 1`, `fuente=sparkov' or 1=1--`, `estado=…' or '1'='1`, `limite=1 or 1=1|-1|999999`, ids con comillas y `/api/tareas/1' or 1=1--/trazas`. Todo responde 200 vacío, 404 o 422 en español, y los contadores siguen en 339.
- **Filtros con lista cerrada** (`rutas_casos.py:21-25`, `_validar_opcion`), `limite` entre 1 y 1000, `q` de hasta 100 caracteres, `tarea_id` validado como UUID y `dias` y `limite` del historial acotados.
- **XSS: no hay.**
  - `app/web/` no usa `innerHTML`, `insertAdjacentHTML` ni `eval`. Todo pasa por `el()` y `textoConFormato()` de `app/web/js/dom.js`, que crean nodos de texto; las negritas del LLM se convierten en `<strong>` con `textContent`.
  - Los `href` dinámicos solo apuntan a `#razon-…` (`explicacion.js:103`).
  - **Comprobado en el navegador:** en `SIN-000016`, el nombre y el comentario con `<img onerror>`, `<script>` y `javascript:` se ven como texto literal. El nodo del comentario tiene 0 hijos, hay 0 `img[src=x]` y 0 enlaces `javascript:`.
  - La API responde `application/json`.
- **Errores sin trazas.** Un manejador global (`app/principal.py:303-322`) devuelve un mensaje fijo en español más una referencia de 12 caracteres, y la traza solo queda en el log. La base caída da 503 con mensaje claro, y los 404 y 405 salen en español.
- **Secretos.**
  - `/api/salud` y `/api/config` solo dicen `con_llave: true|false`.
  - Revisé `/api/metricas`, el detalle de los casos y las trazas de 8 tareas buscando `sk-ant-`, `apikey_`, `AQ.Ab`, `AIza`, `postgresql://`, `fraude_dev`, rutas internas y `Traceback`: 0 coincidencias.
  - Las llaves van en cabeceras (`x-api-key`, `x-goog-api-key`), nunca en la URL, así que no aparecen en mensajes de error de httpx ni en el log.
  - `git grep --cached` no encuentra llaves con largo real, y `git log --all -p` tampoco: 0 en el historial.
  - `.env.example` deja las llaves vacías.
  - El empaquetador busca 5 patrones (incluidos `apikey_` y `AQ.Ab`), descomprime los `.gz`, aborta sin escribir el ZIP y nunca imprime la llave.
- **Imagen Docker.** Solo `app/` y `semilla/`, sin `.env` (verificado dentro del contenedor). Corre como `uid=1000(analista)`, no como root. Las llaves llegan por `env_file`.
- **Postgres no se publica en el host**: solo la red interna de compose; en el anfitrión no escucha el 5432.
- **CORS cerrado.** No hay middleware CORS: un origen ajeno no recibe `Access-Control-Allow-Origin` y no puede leer respuestas.
- **Recorrido de rutas.** `/static/../config.py` en sus variantes responde 404.
- **Privacidad.** La tarjeta sale enmascarada; `id_cuenta` y `fraude_confirmado_dataset` no llegan a la interfaz (verificado en el detalle); el oráculo de sufijos de tarjeta está cerrado (solo coincidencia exacta de 4 dígitos).
- **Integridad de decisiones.**
  - La acción se valida en tres capas: la API (`rutas_casos.py:165`), el repositorio (`_validar_accion`) y un `CHECK` en la base.
  - El analista es obligatorio en la API y el repositorio: un nombre vacío o solo de espacios da 422.
  - Los largos están acotados: 80 para el analista, 1000 para el comentario y 500 para la pregunta.
  - Confirmar dos veces la misma propuesta es imposible: `select … for update` más la verificación de `estado = 'pendiente'` hacen que la segunda reciba 409 (`repositorio.py:491-499`).
  - No se puede "confirmar la propuesta de otro caso": la ruta `/api/propuestas/{id}/confirmar` no recibe caso, y la decisión se escribe en el `id_caso` de la propia propuesta, leído bajo bloqueo.
  - El agente nunca escribe decisiones, solo propuestas (`crear_propuesta`).
- **Dependencias directas fijadas** con `==` en `app/requirements.txt`.
