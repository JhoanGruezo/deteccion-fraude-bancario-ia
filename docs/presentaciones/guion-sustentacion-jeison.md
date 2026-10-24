# Guion de la sustentación — Jeison

**Sábado 31 de octubre de 2026 · 6 minutos de demo + 3 de preguntas · orden sorteado**
Deck: https://claude.ai/artifact/YW2u8Bnbm4BDuU9PtAqdXo (las notas del orador de cada
lámina repiten este texto).

**Tu papel:** en la demo lees en voz alta la traza mientras Jhoan maneja la app. Después
presentas los datos, el motor de riesgo y las cifras (láminas 7 a 10). En preguntas
respondes todo lo de datos, motor, medición y costo.

## Línea de tiempo (total 5:50, quedan 10 s de margen)

| Minuto | Lámina | Quién |
|---|---|---|
| 0:00–0:30 | 1 y 2 · Portada y qué hace | Jhoan |
| 0:30–3:15 | 3 · Demo en vivo | Jhoan maneja · **Jeison lee la traza** |
| 3:15–4:05 | 4 a 6 · Arquitectura, agente, fallas | Jhoan |
| 4:05–4:25 | 7 · Datos | **Jeison** |
| 4:25–4:45 | 8 · Motor de riesgo | **Jeison** |
| 4:45–5:15 | 9 · Las cuatro cifras | **Jeison** |
| 5:15–5:35 | 10 · Qué cambió al medir | **Jeison** |
| 5:35–5:50 | 11 · Cierre | Jhoan |

Tu entrada es cuando Jhoan diga «Jeison les cuenta los datos y las cifras». Si van
atrasados, recorta la lámina 10 a una frase: «la primera medición dio 84 %, corregimos
tres cosas y subimos a 94,7 %».

## En la demo

Cuando Jhoan da clic en «Regenerar», lee en voz alta la columna «Traza de la tarea»
mientras aparece: «pidió obtener_caso… obtener_perfil_cuenta… obtener_historial_reciente…
obtener_score_y_umbrales… y aquí van los tokens y el costo de esta explicación». En el
429 forzado, lee el estado: «Claude respondió 429… reintenta… se cambia a Gemini». En el
rechazo, señala la herramienta `declarar_fuera_de_alcance`.

## Lo que dices, lámina por lámina

**7 · Datos (20 s).** «No usamos RAG, y lo decidimos con la tabla de la clase. Los datos
ya están en Postgres, el agente solo necesita ver un caso y lo busca por su id exacto. Son
números, no prosa: un buscador vectorial traería filas parecidas y el modelo terminaría
calculando sobre fragmentos. Usamos Sparkov porque trae historial por tarjeta y
ubicación, que es lo que necesita el perfil; PaySim casi no repite cuentas y el de ULB no
tiene cuenta ni ubicación.»

**8 · Motor (20 s).** «Por esto el proyecto necesita un modelo. Nuestra primera idea era
una regla de umbral fijo: monto alto o madrugada. Sobre Sparkov acierta en 1,4 % de sus
alertas: casi setenta falsas alarmas por cada fraude real. El modelo compara cada compra
con el historial previo de esa tarjeta y sube la precisión a 78,6 %, detectando más
fraude. Lo medimos con partición temporal: el modelo nunca ve el futuro.»

**9 · Las cuatro cifras (30 s).** «Así sabemos que funciona. El 21 de octubre corrimos un
lote de 19 tareas contra la app en Docker. Éxito: 94,7 %, y éxito es contrato válido con
los hechos esperados, no que se vea bien. Costo: una milésima y media de dólar por caso.
Latencia: mediana de 5,8 segundos; usamos la mediana porque los 429 tardan unos 18 y
moverían el promedio. Recuperación: las cuatro fallas forzadas terminaron con una
explicación válida.»

**10 · Qué cambió al medir (20 s).** «La primera medición dio 84 % y mostró tres
problemas: los casos con muchas compras rompían el formato, el rechazo dependía de una
frase exacta y el nivel de riesgo a veces salía al revés. Corregimos los tres —el último
quitándoselo al modelo y dándoselo al código— y con el mismo lote subimos a 94,7 %.» →
Jhoan cierra.

## Preguntas que te tocan

- **«¿Por qué esa estrategia de datos y no otra?»** Datos tabulares en una base
  relacional, búsqueda por llave primaria y un solo caso por consulta: consulta directa
  por tool calling. RAG recuperaría parecido, no exacto.
- **«¿Qué pregunta no puede responder su sistema?»** Si el cliente reconoce las compras,
  su saldo, su nombre o su teléfono: no están en la base, y el agente lo dice en «lo que
  no se sabe». Una pregunta sobre otro caso la corta la herramienta.
- **«¿Cuánto cuesta una pregunta? ¿Cómo lo midieron?»** 0,0015 USD de mediana: los
  tokens reales de cada tarea por la tarifa de lista de cada modelo. Se ve en la traza.
  Todo el lote costó 0,022 USD.
- **«Si cambiaran a un modelo más barato, ¿qué pasaría? ¿Lo probaron?»** Haiku 5.5 ya es
  el más barato de los que probamos. Sí probamos el respaldo, Gemini Flash-Lite: cumple el
  contrato, pero tarda más (17,5 s en la recuperación del 429).
- **«Muéstrenme la traza de un caso que falló.»** Caso D1 del lote del 21 de octubre a
  las 21:32 (`eval/resultados/lote_2026-10-21_2132.json`): una ráfaga de 12 compras, dos
  contratos inválidos y plantilla. Esa falla es la que llevó a la primera corrección.
- **«¿Cómo evitaron la filtración?»** El perfil usa solo transacciones anteriores de la
  misma tarjeta y la partición es temporal (entrenamiento hasta marzo de 2020, validación
  hasta junio, prueba el resto del año). La versión anterior calculaba el perfil con
  todos los datos; lo encontramos y lo corregimos el 21 de octubre.
- **«¿Los casos dorados están verificados?»** Si los verificamos antes del 31: «sí, a
  mano por los dos». Si no: «la suite pasa 8 de 8, la verificación humana está
  pendiente». Nunca decir que sí si no se hizo.
- **«Explíquenme esta función.»** Repasa `docs/guia-de-estudio.md`, sobre todo
  `src/perfil_cuenta.py`, `src/motor_riesgo.py`, `src/entrenar_modelo.py` y
  `eval/correr_lote.py`.

Regla de oro: respuesta directa primero, luego muéstrala. Si no lo medimos, se dice «no lo
medimos»; nunca se inventa.
