# Requisitos — evaluacion-entrega

## Para qué existe

Cubre los dos criterios que más pesan junto al agente: "Medición y Trazas" (25 pts) y
la reproducibilidad del ZIP, cuya falla anula la nota (`decisiones.md`, "Actualización
2026-10-21 (2)"). También cubre "Los Datos" (20 pts): justificar en
`docs/decisiones.md` por qué no se usa RAG.

## Entradas

- La app funcionando (persistencia + agente + vista).
- Casos de la base con respuesta verificable a mano.
- `decisiones.md` y los documentos de `requisitos/`, `diseno/` y `validacion/`.

## Salidas

1. **`eval/`**:
   - suite de casos dorados (5 a 10, al menos uno de rechazo), cada uno con la
     respuesta esperada verificada a mano por el equipo y cómo se verificó;
   - un script que corre la suite contra el agente y la marca como éxito o fallo;
   - un lote de al menos 15 consultas para medir latencia P50 y P90, costo en USD y
     ahorro por caché (reto 9);
   - las trazas de cada corrida guardadas.
2. **`docs/decisiones.md`** (registro único): arquitectura, frontera de la IA (qué
   hace el LLM, qué hace el ML clásico, qué es código determinista), estrategia de
   datos sin RAG con su argumento, proveedor y modelo justificados, manejo de fallos,
   y la **línea base con las cuatro cifras con fecha**: tasa de éxito, costo por
   tarea, latencia mediana y recuperación.
3. **Paquete de entrega**: `README.md` (contrato de arranque: versiones, variables,
   un comando, modelo y proveedor justificados), `docker-compose.yml`, `run.sh`,
   `.env.example` sin llaves, y un script que arma el ZIP sin `.venv/`, `.git/`,
   `__pycache__/` ni los CSV de Kaggle.
4. **Prueba del compañero** documentada (resultado de las 3 tareas).

## Criterios de aceptación

1. Desde el ZIP descomprimido en una carpeta limpia, siguiendo solo el README, la app
   queda arriba con un comando en menos de 5 minutos (medido).
2. El ZIP no contiene llaves reales (verificado con una búsqueda de patrones de llave
   antes de empaquetar).
3. La suite corre con un comando y reporta las cuatro cifras; los números de
   `docs/decisiones.md` salen de esa corrida, con fecha.
4. Al menos un caso de rechazo, y la recuperación medida con fallos forzados.
5. `docs/decisiones.md` explica la decisión de no usar RAG con la tabla de la
   semana 8.

## Casos borde

- La suite corre sin llaves: debe decirlo y medir solo la plantilla, sin fallar en
  silencio.
- Cuota agotada a mitad del lote: queda registrado como fallo de proveedor, no como
  éxito.

## Fuera de alcance

- Medición de seguridad y gobernanza (Momento 3: `docs/seguridad.md`,
  `docs/gobernanza.md`, `docs/respuesta_auditoria.md`, cifras finales contra la línea
  base).
- Suite E2E de navegador (opcional si sobra tiempo).

## Preguntas abiertas

- Qué casos componen la suite dorada y quién los verifica a mano (el equipo debe
  hacerlo para poder sustentarlos): diseño.
- Cómo se cuenta un "éxito" del agente (contrato válido + citas correctas +
  recomendación igual a la de la regla): diseño.
