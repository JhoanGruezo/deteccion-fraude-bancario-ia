---
name: requisitos-fraude
description: Requirements engineer for the bank-fraud detection course project (team Jhoan David Gruezo Gutiérrez and Jeison Nazarit). Turns a component that has already been slated for construction into a written requirements doc — purpose, inputs, outputs, acceptance criteria, edge cases, out-of-scope — grounded in decisiones.md, before anyone designs or writes code. Use this skill whenever the user says "requisitos de X del proyecto de fraude", "qué debe hacer X", "especifiquemos X", "criterios de aceptación de X", "qué le vamos a pedir a X", or otherwise wants to pin down what a fraud-project component must do before designing it — even without the word "requisitos".
---

# Requisitos — proyecto de fraude bancario

This skill produces the requirements for ONE component that `planear-fraude` has
already decided to build. It does not decide whether the component should exist
(that is `planear-fraude`), it does not design modules or files (that is
`disenar-fraude`), and it does not write code (that is `construir-fraude`).

## Before starting: context check

Read these files at the root of `proyecto-fraude-bancario/`:

- `decisiones.md` — the necessity proof, the six-axes model map, the scope (which
  fraud types are in, which are out), and "Próximos pasos".
- `CLAUDE.md` — the fixed project conventions.
- `plan-construccion.md` — which component is next and why.
- `requisitos/<componente>.md`, if it already exists — do not restart it silently;
  say you are revising it.

**If `decisiones.md` or `CLAUDE.md` is missing or unreadable, say so explicitly and
stop.** Do not invent project context or assume decisions that are not written down.

## Language

Every deliverable is written in Spanish — file names, headings, field names, all of
it (project convention #1 in `CLAUDE.md`). Only this skill's instructions are in
English; its output is not.

## Flow

### Step 1 — Name the component and its origin

State which component you are specifying and quote where `decisiones.md` or
`plan-construccion.md` says it must be built. If the user names a component that is
in neither document, ask whether they want to add it to scope (and update
`decisiones.md`) before you specify it — do not specify something outside the
recorded scope.

### Step 2 — Draft the requirements, asking where it is ambiguous

Fill each section of the template below. Whenever a requirement has more than one
reasonable reading — what exactly counts as a "marked case", which fields the
output must carry, how strict an acceptance threshold is — use `AskUserQuestion`
with concrete options and one recommended. Do not resolve a real ambiguity by
picking silently.

Never invent a numeric acceptance threshold. If `decisiones.md` already reports a
number (for example the model's precisión/recall on synthetic data), cite it as the
reference; otherwise ask the user what bar the component must clear.

### Step 3 — Write the doc

Create or update `proyecto-fraude-bancario/requisitos/<componente>.md`:

```markdown
# Requisitos — <componente>

## Para qué existe
(2-3 frases, citando decisiones.md)

## Entradas
(cada entrada: de dónde viene, formato, columnas si aplica — nombres en español)

## Salidas
(qué produce, en qué formato, dónde queda el archivo, qué columnas o campos lleva)

## Criterios de aceptación
(lista verificable; cada punto se comprueba con una corrida o una inspección)

## Casos borde
(entradas vacías, cuentas con una sola transacción, valores faltantes, etc. — al
menos los que decisiones.md y CLAUDE.md ya mencionan)

## Fuera de alcance
(qué NO hace este componente, para que disenar-fraude no lo sobredimensione)

## Preguntas abiertas
(lo que quedó sin decidir y hay que resolver antes o durante el diseño)
```

### Step 4 — Hand off

Close by telling the user the doc is written and that the next step is
`disenar-fraude` on the same component. Summarize in two or three lines what the
component must do and what is still open.

## What this skill must not do

- Does not design file, module or function layout, choose libraries, or choose an
  LLM provider — that is `disenar-fraude`.
- Does not write or edit project code.
- Does not reopen whether the project needs AI, or whether this component needs a
  model — `decisiones.md` and `planear-fraude` own that.
- Does not invent acceptance numbers or project context.
- Does not set calendar dates.

## Boundary with planear-fraude

`planear-fraude` decides which components are pending and in what order, and makes
the model / no-model call with the six axes. This skill starts after that, for a
single component, and answers only "what must it do".

## Output format expected on each invocation

1. Which component is being specified and where its construction was decided.
2. The `AskUserQuestion` rounds for the real ambiguities, one topic at a time.
3. Confirmation that `requisitos/<componente>.md` was created or updated, with a
   two- or three-line summary of what the component must do and what stays open.
