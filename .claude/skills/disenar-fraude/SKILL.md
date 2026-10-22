---
name: disenar-fraude
description: Technical designer for the bank-fraud detection course project (team Jhoan David Gruezo Gutiérrez and Jeison Nazarit). Takes the requirements for one component and designs its concrete implementation — files, functions and signatures, data formats, library or LLM-provider choice, how it plugs into src/ or interfaz/, error handling, and the validation approach — without writing production code. Use this skill whenever the user says "diseño de X del proyecto de fraude", "cómo construimos X" (a specific component, not the whole backlog), "arquitectura interna de X", "qué archivos y funciones lleva X", "con qué librería o LLM hacemos X", or wants the detailed build plan for one fraud-project component already slated for construction — even without the word "diseño".
---

# Diseño técnico — proyecto de fraude bancario

This skill designs the concrete implementation of ONE component whose requirements
already exist. It does not write production code (that is `construir-fraude`) and it
does not decide scope or build order (that is `planear-fraude`).

## Before starting: context check

Read, at the root of `proyecto-fraude-bancario/`:

- `decisiones.md` — necessity proof, six-axes map, scope.
- `CLAUDE.md` — fixed conventions, especially the "Convenciones de código" section
  (column names, routes relative to `src/`, deterministic impossible-travel
  detector, the metrics rule, `groupby` on the data instead of generator columns).
- `requisitos/<componente>.md` — the requirements this design must satisfy.
- `diseno/<componente>.md`, if it exists — say you are revising it.

**If `decisiones.md` or `CLAUDE.md` is missing or unreadable, say so and stop.** If
`requisitos/<componente>.md` does not exist, tell the user that `requisitos-fraude`
should run first; proceed only by writing explicit assumptions into the design doc,
and only if the user agrees.

## Language

Every deliverable is in Spanish (`CLAUDE.md` convention #1): function names,
variable names, column names, printed messages. Only this skill's instructions are
in English; its output is not.

## Flow

### Step 1 — Restate what is being designed

Name the component, link its requirements doc, and list the acceptance criteria the
design has to meet.

### Step 2 — Decide every real alternative with the user

For each design choice with more than one reasonable answer — new folder name,
which dataset, which library, which LLM provider or API, how the piece integrates
with existing code in `src/`, output file format — use `AskUserQuestion` with
concrete options and one recommended. **Never settle an architecture alternative on
your own, however small it looks.** The team decides; this skill organizes and asks.

If a choice is of the form "does this piece need a model or not", argue it first
with the same six axes `decisiones.md` uses (entrada, reglas, determinismo,
volumen, latencia, costo del error), give the user that analysis, and only then
ask.

Apply these fixed conventions without asking: Spanish everywhere; `pandas` and
`scikit-learn` are allowed; routes relative to `src/`; the impossible-travel
detector stays deterministic code; no single global threshold is presented as the
main detector; every performance comparison reports precisión, recall, F1 and
AUC-PR.

### Step 3 — Write the design doc

Create or update `proyecto-fraude-bancario/diseno/<componente>.md`:

```markdown
# Diseño — <componente>

## Decisiones de esta sesión
(cada alternativa resuelta con el usuario, con su justificación breve)

## Dónde vive
(carpeta y archivos nuevos o modificados)

## Módulos y funciones
(por cada función: nombre en español, qué recibe, qué devuelve, qué hace en una
frase)

## Formato de datos
(entradas y salidas: columnas o campos con nombres en español, tipos, separador,
qué se hace con valores faltantes)

## Integración
(cómo se conecta con lo que ya existe en src/ o interfaz/; qué NO se toca)

## Manejo de errores
(entradas inválidas, archivos que faltan, casos borde de requisitos/<componente>.md)

## Cómo se valida
(qué debe comprobar validar-fraude: métricas a reportar, comparaciones, señales de
datos poco realistas)
```

### Step 4 — Hand off

Tell the user the design is written and the next step is `construir-fraude` on the
same component. Give two or three lines on what changed versus any earlier version
of the design doc, or "es la primera versión".

## What this skill must not do

- Does not write or edit production code (`generar_datos.py`, `entrenar_modelo.py`,
  the future interface, any new implementation file).
- Does not decide any real architecture alternative without asking.
- Does not reopen scope or the model / no-model question at the project level.
- Does not set calendar dates or split work by semester weeks.
- Does not invent project context if `decisiones.md` or `CLAUDE.md` cannot be read.

## Boundary with planear-fraude

`planear-fraude` answers "what is missing and in what order" and makes the
project-level model / no-model calls. This skill answers "how is this one
component, already slated for building, actually structured".

## Output format expected on each invocation

1. Which component is being designed and the acceptance criteria it must meet.
2. The `AskUserQuestion` rounds, one alternative at a time, with the six-axes
   analysis first for any model / no-model choice.
3. Confirmation that `diseno/<componente>.md` was created or updated, with a
   two- or three-line summary of what changed.
