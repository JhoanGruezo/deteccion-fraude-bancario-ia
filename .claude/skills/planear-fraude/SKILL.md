---
name: planear-fraude
description: Planea la arquitectura y el orden de construcción del proyecto de curso "detección de fraude bancario" (equipo Jhoan David Gruezo Gutiérrez y Jeison Nazarit) — decide junto al equipo qué componente falta construir, dónde va a vivir cada pieza y en qué orden, sin escribir código de producción. Se apoya en decisiones.md (la prueba de necesidad ya resuelta y el mapa de los seis ejes) y en CLAUDE.md (convenciones fijas del proyecto). Usa esta skill SIEMPRE que el usuario diga "planeemos el proyecto de fraude", "qué sigue en el proyecto de fraude", "arquitectura del proyecto de fraude", "cómo construimos lo que falta del proyecto de fraude", "qué toca ahora en el proyecto de fraude", o cuando quiera decidir el siguiente paso de este proyecto antes de escribir código nuevo — incluso si no menciona la palabra "planear".
---

# Planear el proyecto de fraude bancario

Esta skill es solo para la fase de planeación: decidir qué falta, dónde vive y en qué
orden se construye. **No escribe código del proyecto.** La pregunta de si el proyecto
necesita IA ya está resuelta en `decisiones.md` — esta skill no la reabre, arranca
después de ella.

## Antes de empezar: verificación de contexto

Antes de proponer nada, lee estos dos archivos en la raíz de `proyecto-fraude-bancario/`:

- `decisiones.md` — la prueba de necesidad, el mapa de los seis ejes, el alcance
  (qué tipos de fraude, qué queda fuera), y la sección "Próximos pasos".
- `CLAUDE.md` — las convenciones fijas del proyecto (español, ML clásico para el
  motor de riesgo, LLM solo para la interfaz de consultas, nunca solo accuracy, el
  detector de viaje imposible es código determinista).

**Si alguno de los dos no existe o no se puede leer, dilo explícitamente al usuario y
detente ahí.** No inventes el contexto del proyecto ni asumas decisiones que no están
escritas en esos archivos. Si existe `plan-construccion.md` de una sesión anterior,
léelo también antes de continuar — no repitas una decisión ya tomada sin decir que la
estás revisando.

## Flujo

### Paso 1 — Refrescar el estado real

No confíes en lo que recuerdes de conversaciones anteriores: relee los archivos de
este paso cada vez que se invoque la skill, porque el código o las decisiones pueden
haber cambiado desde la última vez. Si algo en `plan-construccion.md` ya no coincide
con el estado real del código (por ejemplo, dice "pendiente" algo que ya existe en
`src/`), señálalo antes de seguir.

### Paso 2 — Identificar qué falta

Compara el estado actual contra "Próximos pasos" y "Qué queda fuera de alcance" de
`decisiones.md`. Preséntale al usuario una lista corta de las piezas pendientes reales
(por ejemplo: validar contra un dataset real, construir la interfaz de lenguaje
natural, agregar el detector de viaje imposible) — no inventes piezas que no estén
respaldadas por esos documentos. Si el usuario menciona una pieza nueva que no está en
`decisiones.md`, primero pregúntale si quiere agregarla al alcance antes de planearla.

### Paso 3 — Decidir cada pieza pendiente, preguntando siempre

Para cada pieza que se vaya a planear en esta sesión:

1. Explica en dos o tres frases qué problema resuelve esa pieza y por qué está en la
   lista de pendientes (cítalo de `decisiones.md` si aplica).
2. Si hay más de una forma razonable de construirla (qué dataset usar, cómo se llama
   la carpeta nueva, qué librería o proveedor para la interfaz de LLM, cómo se
   integra con lo que ya existe en `src/`), usa `AskUserQuestion` con opciones
   concretas y una recomendada. **Nunca decidas sola una alternativa de
   arquitectura, aunque parezca menor** — este es el punto central de la skill: el
   equipo decide, la skill organiza y pregunta.
3. Si la decisión es del tipo "¿esto necesita modelo o no?", arguméntala con el
   mismo marco de los seis ejes que ya usa `decisiones.md` (entrada, reglas,
   determinismo, volumen, latencia, costo del error) antes de preguntar — dale al
   usuario el análisis, no solo las opciones sueltas.
4. Anota la decisión tomada y su justificación a medida que avanzas; las vas a
   necesitar todas juntas en el paso 4.

### Paso 4 — Cerrar la sesión con el plan escrito

Al terminar de decidir las piezas de esta sesión, crea o actualiza
`proyecto-fraude-bancario/plan-construccion.md` con esta estructura:

```markdown
# Plan de construcción — [fecha de la sesión]

## Qué se decidió en esta sesión
(lista de decisiones tomadas, cada una con su justificación breve)

## Arquitectura resultante
| Componente | ¿Dónde vive | ¿Lleva modelo? | Notas |
|---|---|---|---|
(una fila por componente del proyecto, actualizado con lo nuevo de esta sesión)

## Orden de construcción
(lista numerada: qué se construye primero, qué depende de qué)

## Checklist de próximos pasos
- [ ] (accionable, sin fechas de calendario)
```

Si el archivo ya existe, actualízalo — no lo reescribas borrando el historial de
sesiones anteriores; agrega la sesión nueva y actualiza la tabla de arquitectura y el
checklist para reflejar el estado actual.

## Qué NO debe hacer esta skill

- No escribe ni edita código de producción del proyecto (`generar_datos.py`,
  `entrenar_modelo.py`, la futura interfaz, o cualquier archivo nuevo de
  implementación). Si el usuario pide pasar a codear durante la skill, dile que eso ya
  no es el trabajo de esta skill y sugiere salir de ella para empezar a construir con
  el plan ya escrito.
- No reabre la pregunta de si el proyecto necesita IA — eso ya está resuelto en
  `decisiones.md`.
- No fija fechas de calendario ni reparte el trabajo por semanas del semestre; el
  checklist es accionable pero no lleva fechas.
- No decide sola ninguna alternativa de arquitectura real (nombre de carpetas,
  dataset, librería, proveedor de LLM, forma de integración) sin preguntar antes.
- No inventa el contexto del proyecto si `decisiones.md` o `CLAUDE.md` no existen o no
  se pueden leer — lo dice y se detiene.

## Formato de salida esperado en cada invocación

1. Un resumen corto de qué falta por decidir en esta sesión (a partir del paso 2).
2. La conversación de decisiones vía `AskUserQuestion`, una pieza a la vez.
3. Al cerrar, la confirmación de que `plan-construccion.md` quedó creado o
   actualizado, con un resumen de dos o tres líneas de lo que cambió respecto a la
   versión anterior del plan (o "es la primera versión" si no existía antes).
