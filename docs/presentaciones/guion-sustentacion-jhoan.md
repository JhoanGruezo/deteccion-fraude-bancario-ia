# Guion de la sustentación — Jhoan (diapositivas)

**Sábado 31 de octubre de 2026 · 6 minutos en total + 3 de preguntas**
Deck: https://claude.ai/artifact/YW2u8Bnbm4BDuU9PtAqdXo (las notas del orador repiten
este texto).

**Tu papel:** diapositivas de 0:00 a 2:25, le pasas la palabra a Jeison y cierras de 5:45
a 6:00. Una idea por lámina: la dices y pasas.

| Minuto | Lámina | Lo que dices |
|---|---|---|
| 0:00–0:10 | 1 · Portada | «Buenos días, somos Jhoan y Jeison. Hicimos la mesa de trabajo de un analista de riesgo bancario. Les cuento qué es y por qué lo hicimos así, y Jeison les muestra la app.» |
| 0:10–0:25 | 2 · Qué hace | «Al analista no le llega un puntaje: le llega el caso razonado. El modelo marca, una regla decide qué bloquear, el agente lo explica y el analista confirma.» |
| 0:25–0:40 | 3 · Frontera de la IA | «La IA está solo donde hace falta: el puntaje con ML, porque sería una regla distinta por tarjeta, y la explicación con un LLM, porque es lenguaje. Lo exacto o caro va en código, y el bloqueo lo decide una persona.» |
| 0:40–1:00 | 4 · Arquitectura | «El navegador habla con una API en FastAPI que transmite en vivo. El agente solo llega a Postgres por sus herramientas. Los proveedores están aislados: Claude, Gemini de respaldo y una plantilla sin red. El motor de riesgo corre aparte.» |
| 1:00–1:40 | 5 · Decisiones | «Cada decisión con su porqué. FastAPI en vez de Streamlit, para transmitir en vivo por SSE. Postgres, porque casos, trazas y decisiones quedan relacionados y auditados. Docker Compose: un comando, 24 segundos. Agente propio sin LangChain, para controlar sus límites. Claude porque lo medimos: el más rápido y el más barato. Y sin RAG: son tablas que se buscan por id.» |
| 1:40–1:55 | 6 · Agente | «Seis herramientas y cuatro límites: seis vueltas, 40 000 tokens, 25 segundos, y nada se escribe sin el analista. Cada cifra que dice se verifica en código.» |
| 1:55–2:10 | 7 · Motor | «¿Por qué un modelo? En Sparkov, un dataset que no hicimos nosotros, la regla fija acierta 1,4 % de sus alertas; el modelo, 78,6 %, sin ver el futuro.» |
| 2:10–2:25 | 8 · Cifras | «La app, medida: 94,7 % de éxito, una milésima y media de dólar por caso, 5,8 segundos y todas las fallas forzadas recuperadas. Jeison.» |
| 2:25–5:45 | 9 · App en vivo | Jeison |
| 5:45–6:00 | 10 · Cierre | «Lo que todavía no hace: no hay inicio de sesión, con Sparkov no distinguimos tarjeta de cliente y el viaje imposible solo se prueba con sintéticos. Sigue la seguridad: inicio de sesión con roles y volver a medir. Gracias.» |

## Preguntas que te tocan (decisiones, datos, motor y cifras)

- **«¿Por qué FastAPI y no Streamlit?»** Streamlit vuelve a ejecutar todo en cada clic;
  necesitábamos que la explicación y la traza llegaran en vivo, evento por evento, por
  SSE real, y una API con capas separadas.
- **«¿Por qué Postgres y no CSV o SQLite?»** Casos, transacciones, explicaciones, trazas,
  propuestas y decisiones están relacionados; una decisión se registra en una
  transacción y queda auditada. Es la base que trabaja el curso desde la semana 7.
- **«¿Por qué sin LangChain?»** El bucle es un archivo nuestro de unas 250 líneas
  (`app/agente/bucle.py`): controlamos los límites y la traza y lo explicamos línea por
  línea.
- **«¿Por qué no RAG?»** Son tablas en Postgres, el agente ve un solo caso y lo busca por
  id exacto. RAG traería filas parecidas.
- **«¿Por qué Claude y no Gemini?»** Medido el 21 de octubre: Gemini 3.8 Flash tardaba de
  25 a 40 s; Haiku de 1 a 2 s y es el más barato. Hoy el respaldo es Gemini 3.5
  Flash-Lite porque 3.1 estaba saturado.
- **«¿Cómo evitaron la filtración?»** El perfil usa solo compras anteriores de la tarjeta
  y la partición es temporal.
- **«¿Lo volvieron a medir?»** Sí, hoy: 89,5 % de éxito, 5,5 s de mediana, recuperación
  del 100 %.
- **«¿Lo atacaron?»** Sí, hoy: 33 ataques de prompt injection. Ninguno filtró llaves ni
  ejecutó un bloqueo; dos fallas parciales se corrigieron en código (tope de herramientas
  por vuelta y no proponer sin haber leído el caso).

Regla de oro: respuesta directa. Si no lo medimos, se dice «no lo medimos».
