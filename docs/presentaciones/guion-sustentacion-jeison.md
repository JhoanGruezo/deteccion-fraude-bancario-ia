# Guion de la sustentación — Jeison (diapositivas)

**Sábado 31 de octubre de 2026 · 6 minutos en total + 3 de preguntas**
Deck: https://claude.ai/artifact/YW2u8Bnbm4BDuU9PtAqdXo (5 láminas; las demás son de
respaldo para preguntas). Repo: https://github.com/JhoanGruezo/deteccion-fraude-bancario-ia

**Tu papel:** presentas las 4 primeras láminas (0:00–1:45) y le das la palabra a Jhoan,
que muestra la app en su portátil hasta el final.

| Minuto | Lámina | Lo que dices |
|---|---|---|
| 0:00–0:15 | 1 · Qué es | «Buenos días, somos Jeison y Jhoan. Nuestro proyecto es la mesa de trabajo de un analista de riesgo de un banco: detecta fraude con tarjetas y le explica cada caso al analista para que decida qué bloquear.» |
| 0:15–0:40 | 2 · Qué hace | «Funciona en cuatro pasos. Un modelo de ML compara cada compra con el historial de su propia tarjeta. Si dos o más compras pasan el umbral en 48 horas, una regla abre el caso y decide qué bloquear. Un agente de IA lo explica en palabras. Y el analista confirma: sin él no hay bloqueo.» |
| 0:40–1:05 | 3 · Arquitectura | «Así está armada. El navegador habla con una API en FastAPI que transmite en vivo. El agente solo llega a la base, Postgres, a través de sus herramientas. Los proveedores de IA están aislados: Claude primero, Gemini de respaldo y una plantilla si no hay red. El modelo de riesgo corre aparte.» |
| 1:05–1:45 | 4 · Tecnología y por qué | «Por qué esta tecnología. ML clásico, porque la regla fija acertaba 1,4 % de sus alertas y el modelo 78,6 %. FastAPI en vez de Streamlit, para que la explicación llegue en vivo. Postgres, porque casos, trazas y decisiones quedan relacionados y auditados. Docker: un comando y está arriba. Agente propio, sin LangChain, para controlar sus límites. Claude porque lo medimos: el más rápido y el más barato. Y sin RAG, porque son tablas que se buscan por id. Jhoan les muestra la app.» |
| 1:45–6:00 | 5 · App en vivo | Jhoan |

## Preguntas que te tocan (tecnología, datos y modelo)

- **«¿Por qué FastAPI y no Streamlit?»** Streamlit vuelve a ejecutar todo en cada clic;
  necesitábamos que la explicación y la traza llegaran en vivo, evento por evento (SSE),
  y una API con capas separadas.
- **«¿Por qué Postgres y no CSV o SQLite?»** Casos, transacciones, explicaciones, trazas
  y decisiones están relacionados; una decisión se registra en una transacción y queda
  auditada. Es la base que trabaja el curso desde la semana 7.
- **«¿Por qué Docker Compose?»** Un comando levanta la base y la app igual en cualquier
  máquina: 24 segundos desde el ZIP limpio.
- **«¿Por qué sin LangChain?»** El bucle del agente es un archivo nuestro de unas 250
  líneas: controlamos los límites y la traza y lo explicamos línea por línea.
- **«¿Por qué no RAG?»** Son tablas en Postgres, el agente ve un solo caso y lo busca por
  su id exacto. RAG traería filas parecidas, no las exactas.
- **«¿Por qué Claude y no Gemini?»** Lo medimos el 21 de octubre: Gemini 3.8 Flash tardaba
  de 25 a 40 s; Claude Haiku de 1 a 2 s y es el más barato. El respaldo es Gemini 3.5
  Flash-Lite, de otra empresa, para que una caída no tumbe a las dos.
- **«¿Qué datos usaron?»** Sparkov, de Kaggle: 1,85 millones de transacciones con
  historial por tarjeta, hora y ubicación. No lo generamos nosotros. PaySim casi no repite
  cuentas y el de ULB no trae ni cuenta ni ubicación.
- **«¿Cómo evitaron la filtración?»** El perfil usa solo compras anteriores de la tarjeta
  y la partición es temporal: el modelo nunca ve el futuro.
- **«¿Cuánto cuesta?»** Una milésima y media de dólar por explicación (mediana medida).

Regla de oro: respuesta directa. Si no lo sabes, «eso lo responde Jhoan» o «no lo
medimos». Nunca inventar.
