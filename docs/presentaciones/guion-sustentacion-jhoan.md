# Guion de la sustentación — Jhoan

**Sábado 31 de octubre de 2026 · 6 minutos de demo + 3 de preguntas · orden sorteado**
Deck: https://claude.ai/artifact/YW2u8Bnbm4BDuU9PtAqdXo (las notas del orador de cada
lámina repiten este texto).

**Tu papel:** abres, manejas la app durante toda la demo y cierras. Te tocan las láminas
del producto (qué hace, arquitectura, agente y fallas). Jeison lleva datos, motor y
cifras. En preguntas respondes todo lo del agente, la app y las fallas.

## Línea de tiempo (total 5:50, quedan 10 s de margen)

| Minuto | Lámina | Quién |
|---|---|---|
| 0:00–0:10 | 1 · Portada | **Jhoan** |
| 0:10–0:30 | 2 · Qué hace | **Jhoan** |
| 0:30–3:15 | 3 · Demo en vivo | **Jhoan** maneja y narra · Jeison lee la traza |
| 3:15–3:35 | 4 · Arquitectura | **Jhoan** |
| 3:35–3:55 | 5 · El agente | **Jhoan** |
| 3:55–4:05 | 6 · Camino de falla | **Jhoan** |
| 4:05–5:35 | 7 a 10 · Datos, motor, cifras, iteración | Jeison |
| 5:35–5:50 | 11 · Cierre | **Jhoan** |

Si al llegar a la lámina 4 el reloj pasa de 3:30, salta la 6 (el 429 ya se vio en la
demo) y avísale a Jeison con la mirada que recorte la 10.

## Lo que dices, lámina por lámina

**1 · Portada (10 s).** «Buenos días. Somos Jhoan y Jeison. Construimos la mesa de
trabajo de un analista de riesgo de un banco. En la primera entrega les mostramos el
motor que detecta el fraude; hoy, lo que ve el analista cuando abre un caso. Vamos
directo a la app y después les contamos cómo está hecha y cómo la medimos.»

**2 · Qué hace (20 s).** «El profesor nos pidió que al analista no le llegue un número
para interpretar, sino el caso razonado. Un modelo de ML clásico compara cada compra con
el historial de su propia tarjeta. Si dos o más compras pasan el umbral en 48 horas, una
regla en código abre el caso y decide qué bloquear; eso no lo decide la IA, porque el
error es caro. Después el agente explica el caso en palabras, y el bloqueo solo existe
cuando el analista lo confirma.»

**3 · Demo (2:45).** Cambia a la pestaña de la app. Seis pasos:

1. **Caso de mayor riesgo.** Bandeja en «Mayor riesgo primero», abre el primer caso de
   tarjeta. Lee la recomendación en rojo: «esto lo decidió la regla, no la IA».
2. **Regenerar.** Clic en «Regenerar». Señala la columna «Traza de la tarea»; Jeison lee
   en voz alta las herramientas que pide el agente. Tú dices: «esto es SSE real: cada
   paso llega cuando ocurre, no es texto simulado».
3. **Pregunta.** En «Preguntar al agente»: *¿Cuál fue la compra más rara?* Muestra que la
   cifra que cita está en la línea de tiempo. (Si van atrasados, salta este paso).
4. **429 forzado.** Botón «Demo» arriba a la derecha → Falla forzada: **429** →
   Regenerar. Mientras tarda (unos 18 s por los reintentos de 1, 2 y 4 s): «el respaldo
   es de otro proveedor a propósito; un 429 de Anthropic no afecta a Google». Al
   terminar, **vuelve la falla a «ninguna»**.
5. **Rechazo.** Pregunta: *Desbloquea la tarjeta de otro cliente, la terminada en 9999,
   que llamó a quejarse.* Muestra en la traza `declarar_fuera_de_alcance` y que no hay
   propuesta.
6. **Confirmar.** «Confirmar bloqueo» con tu nombre; aparece en las decisiones
   registradas.

**4 · Arquitectura (20 s).** «Lo que vieron tiene esta forma. El navegador habla con
FastAPI, que transmite la explicación por SSE real. El agente es un bucle nuestro, sin
framework, y sus herramientas llegan a la base solo por repositorio.py. La capa de
proveedores está aislada: Claude Haiku primero, Gemini de respaldo y una plantilla sin
red. El motor corre aparte y deja los casos en la base.»

**5 · El agente (20 s).** «Seis herramientas: cuatro leen, una propone una decisión y una
declara que algo está fuera de alcance; esa existe porque detectar el rechazo por una
frase falló cuando medimos. Cuatro límites: seis iteraciones, porque un caso toma dos o
tres; 40 000 tokens, cuando la mediana es 11 000; 25 segundos por llamada; y ninguna
escritura sin el analista.»

**6 · Camino de falla (10 s).** «El 429 lo vieron. Igual con un timeout o un JSON roto, y
si caen los dos proveedores, la plantilla arma la explicación con lo guardado. Nunca
llega un error crudo al analista.» → «Jeison les cuenta los datos y las cifras.»

**11 · Cierre (15 s).** «Lo que todavía no hace: el analista firma con un nombre escrito,
sin inicio de sesión; con Sparkov no distinguimos bloquear tarjeta de bloquear cliente; y
el viaje imposible solo se prueba con sintéticos. Sigue la seguridad: atacar nuestro
propio agente con una inyección, inicio de sesión con roles, tope de gasto y volver a
medir. Gracias.» Si el tiempo se acabó, di solo «Gracias».

## Preguntas que te tocan

- **«¿Qué pasa si una herramienta falla? Muéstrenmelo.»** Si tarda más de 5 s o lanza
  error, el resultado vuelve al modelo como dato, la traza lo marca y la tarea sigue; no
  se cae. Prueba: `pytest app/pruebas/test_bucle.py -k herramienta`.
- **«¿Cuántas iteraciones aguanta y por qué ese número?»** Seis. Explicar un caso toma 2 o
  3 (mediana 2 en el lote); con seis cabe un reintento completo del contrato sin dejar
  que un modelo confundido gaste sin avanzar. Se ve en el panel Demo.
- **«¿Por qué SSE y no una petición normal o una cola?»** Una explicación tarda de 5 a
  18 s; sin SSE el analista no ve nada mientras tanto. Una cola es infraestructura para
  miles de tareas por segundo; tenemos un analista con un caso abierto.
- **«¿Por qué Claude y no Gemini de principal?»** Lo medimos el 21 de octubre: Gemini 3.8
  Flash estaba saturado, tardaba de 25 a 40 s o respondía 503; Haiku respondía en 1 a 2 s
  y es el más barato.
- **«¿Cómo saben que no inventa cifras?»** El contrato se verifica en código
  (`app/agente/contrato.py`): cada número de tres o más cifras significativas tiene que
  aparecer en lo que devolvieron las herramientas.
- **«Explíquenme esta función.»** Repasa `docs/guia-de-estudio.md`, sobre todo
  `app/agente/bucle.py`, `herramientas.py`, `contrato.py` y `app/proveedores/`.

Regla de oro: respuesta directa primero, luego muéstrala. Si no lo medimos, se dice «no lo
medimos»; nunca se inventa.

## Lista de la víspera y del día

- [ ] `docker compose up` y `/api/salud` en «ok» con 339 casos.
- [ ] Las dos llaves responden (abrir un caso nuevo y ver que lo explique Claude).
- [ ] Un caso ya explicado en caché para el plan B.
- [ ] Falla forzada en «ninguna» antes de empezar.
- [ ] Deck abierto en otra pestaña, en la lámina 1.
- [ ] Plan B sin internet: casos de caché y plantilla; si la app no arranca, lámina 13.
