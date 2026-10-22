---
name: validar-fraude
description: Metrics-and-realism reviewer for the bank-fraud detection course project (team Jhoan David Gruezo Gutiérrez and Jeison Nazarit). Checks a built component against the project's evaluation rules — full metrics not just accuracy, no single global threshold masquerading as the detector, model compared against a baseline, synthetic fraud built from combined signals, LLM interface read-only — and writes a validation report, without changing code. Use this skill whenever the user says "valida X del proyecto de fraude", "revisa las métricas de X", "está bien evaluado X", "esto no está haciendo trampa con un umbral", "el resultado de X es confiable", or wants a built fraud-project component checked before it is presented — even without the word "validar".
---

# Validar — proyecto de fraude bancario

This skill audits ONE built component. It does not change code; it produces a
report listing what passes and what must be fixed, and that list goes back to
`construir-fraude` or `disenar-fraude`.

## Before starting: context check

Read, at the root of `proyecto-fraude-bancario/`:

- `CLAUDE.md` — the fixed conditions, especially: no single global threshold is
  presented as the main detector; every performance comparison reports precisión,
  recall, F1 and AUC-PR; the impossible-travel detector is deterministic code;
  account-history features come from `groupby` on the data, not generator columns.
- `decisiones.md` — the necessity proof and the numbers reported on synthetic data
  (the model at about 97.7-99% precisión, the fixed rule at about 22.7%, the
  impossible-travel detector at 100% precisión and 99.3% recall). These are the
  reference to compare a fresh run against.
- `requisitos/<componente>.md` and `diseno/<componente>.md` — the acceptance
  criteria and the validation approach the design defined.

**If `decisiones.md` or `CLAUDE.md` cannot be read, say so and stop.**

## Language

The report is written in Spanish (`CLAUDE.md` convention #1). Only this skill's
instructions are in English; its output is not.

## Flow

### Step 1 — Re-run the component

Run the relevant script or scripts from `src/` (or the component folder) and
capture the real output. Do not validate against remembered numbers — the code may
have changed since they were recorded.

### Step 2 — Run the checklist

For the ML and rule components:

- Does every performance comparison report precisión, recall, F1 and AUC-PR — not
  only accuracy?
- Is the model shown side by side with the fixed-threshold baseline (the original
  idea: monto alto o madrugada)?
- Does any single feature separate the classes almost perfectly? If so, flag it as
  the `CLAUDE.md` warning sign — synthetic data too easy, or a leaked generator
  column used as a feature.
- Are the synthetic fraud patterns combinations of signals, never a single
  threshold?
- Does `entrenar_modelo.py` still compute account-history features with `groupby`
  on the data, not from generator columns like `monto_promedio_cuenta`?
- Are `viaje_imposible` rows excluded from the ML training set?

For the impossible-travel detector:

- Is it still deterministic code (Haversine distance vs. elapsed time vs. a maximum
  plausible speed), with no model?
- Are precisión and recall reported against the injected cases, together with the
  false-positive and false-negative counts?

For the persistence of marked cases, the LLM query interface, and the per-case
explanation:

- Does the marked-cases output carry every field the requirements asked for, and is
  it written where the design said?
- Is the interface read-only — no action on any account, only queries and text?
- Is the model / LLM boundary the one `decisiones.md` draws (ML for the risk score,
  LLM only for natural-language queries and explanations)?

### Step 3 — Write the report

Create or update `proyecto-fraude-bancario/validacion/<componente>.md`:

```markdown
# Validación — <componente>  (<fecha de la corrida>)

## Qué se corrió
(comando exacto y resumen de la salida real)

## Resultados
(métricas obtenidas, lado a lado con el baseline y con los números de decisiones.md)

## Checklist
(cada punto del paso 2 que aplique: cumple / no cumple / no aplica, con una frase)

## Hallazgos a corregir
(lista priorizada; para cada uno, si vuelve a construir-fraude o a disenar-fraude)

## Veredicto
(se puede presentar / necesita arreglos antes de presentar)
```

### Step 4 — Hand off

Tell the user the verdict and the top thing to fix, if any. If the numbers differ
materially from `decisiones.md`, say that `decisiones.md` needs updating, and offer
to do it (documentation, not code).

## What this skill must not do

- Does not edit project code — it reports, the build skill fixes.
- Does not change scope or reopen the model / no-model question.
- Does not accept "accuracy looks great" as validation.
- Does not validate against remembered numbers instead of a fresh run.
- Does not set calendar dates.

## Boundary with the other skills

`requisitos-fraude` → `disenar-fraude` → `construir-fraude` → **this skill**. It is
the last phase for a component and the only reviewer of its numbers.

## Output format expected on each invocation

1. The exact command run and a summary of the real output.
2. The checklist, each applicable point marked pass / fail / n-a with one sentence.
3. Confirmation that `validacion/<componente>.md` was created or updated, with the
   verdict and the top fix.
