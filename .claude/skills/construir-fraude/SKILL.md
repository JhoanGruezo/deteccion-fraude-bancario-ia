---
name: construir-fraude
description: Implementer for the bank-fraud detection course project (team Jhoan David Gruezo Gutiérrez and Jeison Nazarit). Takes an existing design doc for one component and writes the actual Python in src/ or interfaz/, following every CLAUDE.md convention, then runs the scripts to verify they work and reports the real output. Use this skill whenever the user says "construye X del proyecto de fraude", "implementa X", "codea X", "pasemos a código X", "escribe el script de X", or wants a designed fraud-project component turned into working code — even without the word "construir". This is the only fraud-project skill that writes production code.
---

# Construir — proyecto de fraude bancario

This skill writes the code for ONE component whose design doc already exists. It
does not choose architecture, libraries, or scope — those come from
`diseno/<componente>.md` and `planear-fraude`. If something needed to build is
missing or contradicts `CLAUDE.md`, it stops and flags it instead of guessing.

## Before starting: context check

Read, at the root of `proyecto-fraude-bancario/`:

- `CLAUDE.md` — every convention here is binding. In particular: Spanish for all
  file names, functions, variables, column names and printed messages; `pandas` and
  `scikit-learn` are allowed; account-history features are computed with `groupby`
  on the data itself, never read from generator columns like `monto_promedio_cuenta`;
  routes are relative to `src/`; the impossible-travel detector is deterministic
  code, never a model; every performance comparison reports precisión, recall, F1
  and AUC-PR, never only accuracy.
- `decisiones.md` — for the scope and the necessity argument the code must not
  undermine.
- `diseno/<componente>.md` — the design this code implements.
- `requisitos/<componente>.md` — the acceptance criteria the code must meet.

**If `diseno/<componente>.md` is missing, stop and tell the user to run
`disenar-fraude` first.** If `decisiones.md` or `CLAUDE.md` cannot be read, stop.

## Flow

### Step 1 — Confirm the design is buildable

Summarize what the design says to build. If any decision is missing (a library not
chosen, an output format undefined, an integration point unspecified) or
contradicts `CLAUDE.md`, list the gap and stop — do not fill it yourself. Send the
user back to `disenar-fraude` for that point.

### Step 2 — Write the code

Implement exactly what the design specifies, in `src/` or `interfaz/` as the design
says. Match the style of the existing scripts (`generar_datos.py`,
`entrenar_modelo.py`, `detectar_viaje_imposible.py`): a module docstring explaining
why the piece exists, `sys.stdout.reconfigure(encoding="utf-8")` before printing,
functions with Spanish names, comments in Spanish where the existing files have
them.

Do not add scope the design did not ask for. Do not introduce a library the design
did not choose.

### Step 3 — Run it and report the truth

Run the script or scripts from `src/` (or the component's folder). Paste the real
output. If it fails, show the error and fix the code — never describe what it
"should" print. For anything that reports metrics, show precisión/recall/F1/AUC-PR
side by side with the baseline, per `CLAUDE.md`.

If a single feature separates the classes almost perfectly, treat it as the warning
sign `CLAUDE.md` describes (unrealistic synthetic data, or a leaked generator
column used as a feature) and say so — do not present it as a good result.

### Step 4 — Hand off

Tell the user what was built, what the run showed, and that the next step is
`validar-fraude` on this component. If a new column or file was added, note that
its documentation in `CLAUDE.md` needs updating, and offer to do it (that is
documentation, allowed here).

## What this skill must not do

- Does not decide architecture, libraries, folder names, or LLM provider — it reads
  those from the design doc.
- Does not change project scope or reopen the model / no-model question.
- Does not present a fixed single-threshold rule as the main detector.
- Does not report only accuracy.
- Does not invent output — every result shown is from a real run.
- Does not fill a gap in the design silently; it stops and asks.

## Boundary with the other skills

`requisitos-fraude` → `disenar-fraude` → **this skill** → `validar-fraude`. This is
the only one that creates or edits code under `src/` or `interfaz/`.

## Output format expected on each invocation

1. A summary of what the design says to build, and any gap that blocks it.
2. The code, written to the files the design names.
3. The real output of running it, with full metrics where they apply.
4. The hand-off line to `validar-fraude`, plus any `CLAUDE.md` doc update needed.
