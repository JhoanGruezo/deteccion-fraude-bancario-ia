# Requisitos — vista-analista

## Para qué existe

Es la aplicación que usa el analista de riesgo: la bandeja de casos, el detalle de
cada uno con la explicación del agente y la conversación. Por pedido del profesor,
el agente vive dentro de esta vista (`decisiones.md`, 2026-10-10) y la explicación
llega razonada, no como un score para interpretar (2026-10-21). Es el criterio "La
Aplicación" de la entrega (20 pts): usable por terceros, con prueba del compañero
documentada y manejo elegante de fallos sin trazas de Python visibles. Se construye
con FastAPI + SSE real + frontend propio (`decisiones.md`, "Actualización 2026-10-21
(2)").

## Entradas

- La base de `persistencia` (casos, transacciones, historial, explicaciones,
  decisiones, trazas).
- El `agente` (explicación por SSE, preguntas, propuesta de decisión).

## Salidas

1. **Bandeja de casos**: lista ordenable y filtrable por fuente, nivel de
   recomendación, estado y score. Cada fila muestra tarjeta (enmascarada), ventana,
   nivel, señal principal, número de transacciones y estado.
2. **Detalle del caso**:
   - cabecera con el nivel de recomendación y su motivo;
   - la explicación del agente (qué pasó, por qué es riesgo, recomendación, lo que no
     se sabe), con las cifras citadas resaltadas y enlazadas a la evidencia;
   - la línea de tiempo de las transacciones del caso y del historial reciente;
   - las razones (desviaciones relevantes) con su rareza y su contribución;
   - el perfil previo de la tarjeta.
3. **Generación en vivo**: la primera apertura de un caso transmite la explicación
   por SSE real (TTFT medible, sin animación falsa) y muestra estados honestos del
   proceso (consultando caso → llamando al proveedor → validando → reintento → respaldo).
   Las aperturas siguientes salen de la caché al instante. Botón "regenerar".
4. **Conversación con el agente** sobre el caso abierto, también por SSE.
5. **Decisión**: el agente puede proponer una acción; el analista la confirma o la
   rechaza en un diálogo explícito. Solo entonces se escribe.
6. **Panel de trazas** visible durante la demo: herramientas pedidas, argumentos,
   tiempos, reintentos, proveedor y costo de la tarea.
7. **Mensajes de fallo** comprensibles para el analista (no stack traces), con la
   acción posible (reintentar, usar explicación guardada).

## Criterios de aceptación

1. Una persona ajena al equipo completa 3 tareas sin ayuda, con el desarrollador en
   silencio (prueba del compañero del reto 9), y queda documentado qué hizo y dónde se
   trabó.
2. La explicación llega por `text/event-stream` real: en DevTools se ven los eventos
   llegando mientras el modelo genera; el TTFT se mide y se muestra.
3. Los tres fallos forzados (`FALLA_FORZADA=429|timeout|json`) se ven manejados en
   pantalla, sin trazas de Python.
4. Ninguna decisión se registra sin la confirmación explícita del analista.
5. La interfaz está en español, es legible en la pantalla del salón y no expone
   `fraude_confirmado_dataset` ni el número completo de la tarjeta.
6. Se levanta con el `docker compose up`/`run.sh` del proyecto, sin pasos manuales.

## Casos borde

- Caso sin historial: la línea de tiempo lo dice.
- Sin llaves de API configuradas: la app arranca igual y usa la plantilla, con un
  aviso visible (útil también para la "prueba del compañero").
- Dos pestañas abriendo el mismo caso a la vez: una sola generación, la otra espera
  o usa la caché.
- El analista cierra el panel mientras llega el stream: la generación termina y se
  guarda.

## Fuera de alcance

- Login y roles (alcance del Momento 3, junto con la seguridad formal).
- Edición de casos o del modelo desde la app.
- Versión móvil dedicada (sí debe verse bien en una ventana angosta).

## Preguntas abiertas

- Estructura de rutas de la API y de eventos SSE: diseño.
- Estilo visual y librerías del frontend (sin paso de compilación): diseño.
