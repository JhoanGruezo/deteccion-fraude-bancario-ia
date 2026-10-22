# Diseño — vista-analista

Implementa `requisitos/vista-analista.md`. Primera versión (2026-10-21). Elecciones
técnicas delegadas por el usuario; FastAPI + SSE + frontend propio decidido en
`decisiones.md`, "Actualización 2026-10-21 (2)".

## Decisiones de esta sesión

- **FastAPI** (Python 3.12 en el contenedor) con endpoints síncronos: FastAPI los
  corre en su pool de hilos, y el agente, la base y los clientes HTTP son síncronos.
  Un solo modelo mental, sin `async` mezclado.
- **SSE real con `StreamingResponse`** (`text/event-stream`, `Cache-Control:
  no-cache`, `X-Accel-Buffering: no`) alimentada directamente por el generador de
  eventos del agente: cada evento se escribe al socket apenas ocurre.
- **Frontend sin paso de compilación**: `index.html` + `estilos.css` + módulos ES en
  `js/`. Sin React ni bundler: el ZIP no lleva `node_modules`, arranca sin `npm` y el
  equipo puede explicar cada archivo. `EventSource` nativo para SSE.
- **Diseño visual**: interfaz de trabajo para un analista (densa pero legible),
  pensada para proyectarse en el salón. Tema claro por defecto y oscuro opcional,
  tipografía del sistema, color solo con significado (rojo: bloquear; ámbar:
  verificar; violeta: acceso a la cuenta; gris: cerrado).

## Dónde vive

```
app/
  principal.py              — crea la app FastAPI, monta rutas y estáticos, arranque (migrar)
  api/
    sse.py                  — convierte eventos del agente en texto SSE
    rutas_casos.py          — bandeja, detalle, historial, decisiones
    rutas_agente.py         — explicación y preguntas por SSE, propuestas
    rutas_sistema.py        — salud, configuración visible, métricas, trazas, panel de demo
  web/
    index.html
    estilos.css
    js/
      principal.js          — arranque y enrutado simple (#/caso/SPK-000123)
      api.js                — fetch y EventSource
      bandeja.js            — lista, filtros, contadores
      detalle.js            — cabecera, explicación, línea de tiempo, razones, perfil
      json_parcial.js       — parser tolerante para pintar el JSON mientras llega
      conversacion.js       — preguntas al agente
      trazas.js             — panel de trazas y métricas de la tarea
      decision.js           — diálogo de confirmación humana
      formato.js            — moneda, fechas, porcentajes en español
  Dockerfile
  requirements.txt
```

## API

| Método y ruta | Qué hace |
|---|---|
| `GET /` | `index.html` |
| `GET /api/salud` | estado de la base, casos cargados, proveedores con llave, falla forzada activa |
| `GET /api/config` | límites del agente, modelos, si el panel de demo está habilitado |
| `GET /api/casos?fuente=&nivel=&estado=&q=&orden=score\|fecha&limite=` | bandeja (`repositorio.listar_casos`) + contadores |
| `GET /api/casos/{id}` | detalle (`obtener_caso`), propuestas pendientes, decisiones, explicación vigente si existe |
| `GET /api/casos/{id}/historial?dias=30` | línea de tiempo |
| `GET /api/casos/{id}/explicacion/stream?regenerar=0&falla=` | **SSE**: `servicio.explicar_caso` |
| `GET /api/casos/{id}/preguntas/stream?q=...&falla=` | **SSE**: `servicio.responder_pregunta` |
| `POST /api/propuestas/{id}/confirmar` `{analista, comentario}` | confirmación humana → decisión |
| `POST /api/propuestas/{id}/rechazar` `{analista, comentario}` | rechazo de la propuesta |
| `POST /api/casos/{id}/decisiones` `{accion, analista, comentario}` | decisión manual del analista (sin agente) |
| `GET /api/tareas/{tarea_id}/trazas` | traza completa de una tarea |
| `GET /api/metricas` | `repositorio.resumen_metricas()` (las cuatro cifras en vivo) |
| `POST /api/demo/falla` `{tipo: null\|"429"\|"timeout"\|"json"\|"todo"}` | solo si `PERMITIR_FALLAS_DESDE_UI=true`; fija la falla para las siguientes tareas |

Formato SSE: `event: <tipo>\ndata: <json>\n\n`, con `id:` incremental. Comentario
`: ping` cada 15 s mientras el modelo piensa, para que ningún proxy corte. El primer
evento sale antes de llamar al modelo (estado "Consultando el caso…"), así que el
TTFT de la interfaz se mide desde la petición hasta el primer `token`.

Errores HTTP: 404 con `{"error": "Caso no encontrado"}`; 409 si la propuesta ya fue
resuelta; 422 con mensaje en español si falta el nombre del analista. Un manejador
global convierte cualquier excepción en `{"error": "...", "referencia": tarea_o_uuid}`
sin traza de Python; la traza va al log.

## Pantalla

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│ Riesgo · Analista  [fuente ▾] [nivel ▾] [estado ▾] [buscar]   ● Gemini  ⚙ Demo   │
├───────────────┬──────────────────────────────────────────┬──────────────────────┤
│ BANDEJA       │ SPK-000123 · tarjeta ****1234             │ TRAZA DE LA TAREA    │
│ 249 bloquear  │ [BLOQUEAR TARJETA] 5 compras anómalas…    │ ▸ consultando caso   │
│  38 verificar │ ───────────────────────────────────────── │ ▸ obtener_caso  42ms │
│  33 acceso    │ QUÉ PASÓ          (llega en vivo)         │ ▸ gemini · 1.2k tok  │
│ ───────────── │ POR QUÉ ES RIESGO [monto] [monto_24h]     │ ▸ 429 → reintento 1  │
│ ▣ SPK-000123  │ RECOMENDACIÓN     Bloquear la tarjeta…    │ ▸ conmutación→Claude │
│ ▢ SPK-000124  │ LO QUE NO SE SABE …                       │ TTFT 340 ms · 2,1 s  │
│ …             │ [Regenerar] [Confirmar bloqueo] [Descartar]│ $0,0004 · 3 iter     │
│               │ ── Línea de tiempo (historial + caso) ──  │ ─────────────────────│
│               │ ── Razones: rareza y peso en el score ──  │ PREGUNTAR AL AGENTE  │
│               │ ── Perfil habitual de la tarjeta ──       │ [ …              ⏎ ] │
└───────────────┴──────────────────────────────────────────┴──────────────────────┘
```

- **Bandeja**: contadores por nivel; filas con chip de nivel, tarjeta enmascarada,
  fecha, señal principal, número de transacciones y estado; la seleccionada se
  resalta; teclado ↑/↓ para moverse.
- **Explicación**: cuatro bloques del contrato. Mientras llega por SSE, cada bloque
  se rellena a medida que el JSON parcial lo permite (sin animación falsa: solo lo
  que ya llegó), rotulado como borrador. Si llega `contrato_invalido`, `reintento`,
  `conmutacion` o `respaldo`, el borrador se borra y el estado lo dice ("La respuesta
  no pasó la validación contra la evidencia; reintentando…"): nada rechazado queda en
  pantalla. El texto de una llamada que pidió herramientas no se pinta. Las señales citadas son chips que, al pasar el mouse, muestran su
  descripción, percentil y contribución. Si salió de plantilla o de caché, una
  etiqueta lo dice.
- **Línea de tiempo**: el historial de los últimos días con las transacciones del
  caso resaltadas y su score; montos en barras proporcionales.
- **Razones**: tabla de desviaciones relevantes (rareza en percentil y barra de
  contribución al score) y, plegadas, las no relevantes.
- **Decisión**: si el agente propuso algo, aparece un recuadro "Propuesta del
  agente: confirmar bloqueo — porque…" con [Confirmar] y [Rechazar]. Ambos piden el
  nombre del analista (recordado en `localStorage`) en un diálogo modal propio (nunca
  `alert`/`confirm` del navegador). También hay botones de decisión manual.
- **Conversación**: el texto del agente admite **negritas** y saltos de línea,
  armados con nodos (nunca `innerHTML` con texto del modelo).
- **Traza**: lista en vivo de eventos con icono, duración y "Detalles técnicos"
  plegados por defecto (JSON crudo, nombres de excepción, cuerpos del proveedor); pie con
  TTFT, latencia, tokens, costo, iteraciones, proveedor final y motivo de fin.
- **Panel de demo** (⚙, solo si está habilitado): selector de falla forzada y los
  límites vigentes. Sirve para mostrar en vivo 429, timeout, JSON roto y caída total.
- **Mensajes de fallo**: banda superior con texto en español y acción ("Reintentar",
  "Ver explicación guardada"); nunca stack traces.

## Integración

- `principal.py` llama a `app.db.migrar.preparar_base()` al arrancar.
- Las rutas solo usan `app.db.repositorio` y `app.agente.servicio`; no hay SQL ni
  llamadas a proveedores en `api/`.
- `PERMITIR_FALLAS_DESDE_UI` por defecto `true` en `.env.example` (es una demo
  académica), documentado en el README.

## Manejo de errores

- `EventSource` reconecta solo: el frontend cierra la conexión al recibir `fin` para
  evitar regenerar en bucle.
- Si el SSE se corta antes de `fin`, el frontend muestra "Conexión interrumpida" con
  "Reintentar"; el servidor termina la tarea y la guarda igual.
- Sin casos cargados: la bandeja muestra cómo cargar la semilla.

## Cómo se valida

1. DevTools → Network: `explicacion/stream` con tipo `eventsource`, eventos llegando
   antes de terminar la respuesta, TTFT mostrado.
2. Las cuatro fallas forzadas, desde el panel de demo, terminan con mensaje claro.
3. Confirmar y rechazar una propuesta; la decisión solo existe tras confirmar.
4. Prueba del compañero: 3 tareas (abrir el caso de mayor riesgo y decir por qué se
   bloquea; preguntar al agente cuál fue la compra más rara; registrar una decisión)
   con el desarrollador en silencio, documentada en `docs/decisiones.md`.
5. La interfaz no muestra `fraude_confirmado_dataset` ni la tarjeta completa.
