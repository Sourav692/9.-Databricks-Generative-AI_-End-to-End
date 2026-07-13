---
name: genai-build-loop
description: >-
  Orchestrates the create -> review -> enhance "critic loop" that builds and verifies the Databricks
  GenAI curriculum artifacts (Markdown explainer + interactive HTML + Databricks notebook) defined in
  plan.md and ROADMAP.md. Use when asked to build, generate, or produce a topic, module, or phase and
  have it automatically QA-looped to approval — e.g. "build Module 04", "run the build loop for phase
  P0", "generate and verify the notebook/HTML/markdown for topic 09.6", "create the next unbuilt item
  and loop until the reviewer approves", "loop-engineer the curriculum". For each artifact it invokes
  genai-teacher (the maker) to author, then genai-teacher-reviewer (the critic) to verify with its
  two-check verdict, then feeds the prioritized findings back to genai-teacher and regenerates — looping
  until the reviewer returns ✅ Approved, with round caps, no-progress and regression guards, and a
  human-pause for unresolvable items. On approval it flips the ROADMAP.md marker and ticks the plan.md
  checkbox. Runs a single artifact, a whole module (module page + cornerstone deep-dives + notebooks per
  the plan tiering), or an entire phase. Triggers: "build/generate module|topic|phase X", "run the
  critic loop", "make and review until approved", "start P0".
metadata:
  version: '1.0.0'
  author: sourav.banerjee@databricks.com
  orchestrates: genai-teacher + genai-teacher-reviewer
  drives: plan.md + ROADMAP.md
---

# GenAI Curriculum Build Loop (maker → critic → revise)

You orchestrate a **closed-loop build**: author an artifact, have it critiqued, revise it against the
critique, and repeat **until the reviewer approves**. You do not author or judge content yourself —
you drive the two specialist skills and keep the trackers in sync.

- **Maker** = `genai-teacher` — authors/revises the Markdown, HTML, and notebook.
- **Critic** = `genai-teacher-reviewer` — runs its 2-check verdict and returns prioritized findings.
- **Orchestrator** = this skill — resolves scope from `plan.md`, runs the loop per artifact, enforces
  loop controls, and flips `ROADMAP.md` markers + `plan.md` checkboxes on approval.

> This skill builds the **execution layer** on top of `plan.md`. It never invents scope — it reads the
> plan's per-module matrix and tiering to decide *which* artifacts to build and in *what* order.

## When to use this skill

- The user asks to build/generate/produce a **topic, module, or phase** and wants it verified, not just drafted.
- The user says "run the loop", "loop until approved", "make and review", "start P0/next item".
- After a manual draft exists and the user wants it driven to ✅ through the critic loop.

Do **not** use it to answer a one-off teaching question (that's plain `genai-teacher`) or to do a
one-shot review with no revision (that's plain `genai-teacher-reviewer`).

## Step 1 — Resolve scope from plan.md

1. Read `plan.md` (build spec + tracker) and `ROADMAP.md` (teaching order + markers).
2. Determine the **target**:
   - explicit (`Module 04`, `topic 09.6`, `phase P0`), or
   - **"next unbuilt"** — the first unticked item in `plan.md` §8, respecting phase order and the
     dependency notes in `ROADMAP.md` → *Module dependencies & parallel tracks*.
3. Expand the target into its **artifact set** using the `plan.md` §6 matrix + §3 tiering:
   - module page `module.md` + `module.html`,
   - one `topic-slug.md` + `.html` per **cornerstone (★/T1)** topic (+ notebook if hands-on),
   - the module lab notebook `<NN>-module-lab.py` if the module has any hands-on topic.
4. Confirm **prerequisites are ✅** (per the dependency map). If a hard prereq is missing, say so and
   ask whether to build the prereq first or proceed anyway.

## Step 2 — The critic loop (run per artifact)

For **each** artifact in the set, run:

```
1. AUTHOR   → genai-teacher creates the artifact (Markdown / HTML / notebook), doing its own
              pre-flight self-check against the reviewer rubric before handing off.
2. CRITIQUE → genai-teacher-reviewer runs Check 1 (terminology/API/version) + Check 2 (compliance)
              and returns a verdict (✅ / 🟡 / 🔴) + a prioritized, actionable findings list.
3. DECIDE   → if ✅ Approved: exit loop for this artifact (go to Step 3).
              else: pass the EXACT prioritized findings to genai-teacher in revision mode.
4. REVISE   → genai-teacher applies ONLY the targeted fixes (no rewrite/re-expand), regenerating the
              affected artifact(s) and preserving approved content, citations, code, callouts,
              Mermaid parity (MD↔HTML), and roadmap markers.
5. RE-CRITIQUE → run Check 1 + Check 2 again from scratch.
6. REPEAT from step 3 until ✅ Approved or a loop control fires.
```

Keep **MD ↔ HTML ↔ notebook consistent**: if a fix changes a fact/diagram in one, re-verify the
others in the same round so they don't drift.

## Step 3 — Loop controls (mandatory)

- **Round cap:** stop after **3** author→critique rounds per artifact (**up to 5 for cornerstone/T1**
  artifacts). If still not ✅, stop and report remaining findings for the user to decide.
- **No-progress guard:** if a round reproduces the **same finding**, stop and surface it — don't spin.
- **Regression guard:** after each revision, confirm no **new** issue was introduced (a fix that adds a
  wrong API/number, breaks the MD skeleton, drops a Mermaid diagram, or breaks MD↔HTML parity).
- **Human-pause:** pause and ask the user when a finding is **unresolvable automatically** — an
  unverifiable API/version, ambiguous product scope, a Beta/Preview feature that needs a decision, or a
  fix that would change the lesson's meaning.
- **Accuracy still blocks:** never mark ✅ just to exit the loop; re-verify names/APIs/versions against
  docs + `references/naming-conventions.md` each round.

## Step 4 — On approval: sync the trackers

Only after the critic returns **✅ Approved** for an artifact:
1. Tick its checkbox in `plan.md` §8 and paste the file path.
2. When **all** topics that an artifact covers are approved, flip their markers in `ROADMAP.md`
   (⬜→✅, or 🔄 if a module is partially built).
3. Keep `plan.md` and `ROADMAP.md` **in sync** — never tick one without the other where they overlap.

## Step 5 — Build order & batch modes

- **Topic mode** — build one artifact (or a topic's artifact pair + notebook), loop, sync.
- **Module mode** — build the module's set in this order, each through the loop:
  1. `module.md` + `module.html` (overview), 2. each cornerstone deep-dive (MD+HTML, then its NB),
  3. the module lab notebook. Then run **per-module DoD** (below) and, at the module boundary, have
  `genai-teacher` offer the consolidated module notebook / mini-project.
- **Phase mode** — iterate the phase's modules in `plan.md` §5 order (respecting dependencies), each via
  module mode. Then run **per-phase DoD** and report which downstream phases are now unblocked.

## Step 6 — Reporting

Emit a compact **loop log** so progress is auditable.

Per artifact:

| Artifact | Round | Verdict | Fixes applied | Remaining |
|---|---|---|---|---|
| 04 module.html | 1 | 🔴 | wrong VS index-type name; missing Mermaid parity | 2 |
| 04 module.html | 2 | 🟡 | fixed both; add reranking cross-ref | 1 |
| 04 module.html | 3 | ✅ | cross-ref added | 0 |

Per run, end with a summary: items attempted, items ✅, items paused/capped (with why), the trackers
updated, and the next unbuilt item.

## Definition of Done (gates — reuse plan.md §7)

- **Per artifact:** reviewer ✅ Approved · sources cited · ≥1 Mermaid (MD) mirrored in HTML · Field
  Almanac / shared tutor design + style passes applied · notebook runnable & UC-first (if hands-on).
- **Per module:** module MD+HTML ✅ · all cornerstone deep-dives ✅ · module lab NB ✅ (if any hands-on)
  · every covered topic flipped in `ROADMAP.md` · all boxes ticked in `plan.md` §8.
- **Per phase:** all modules DoD-complete · dependency-downstream phases unblocked.

## Guardrails

- **Always review before marking done.** No artifact is ✅ without a `genai-teacher-reviewer` ✅ verdict.
- **Don't author or self-approve.** You delegate making to `genai-teacher` and judging to
  `genai-teacher-reviewer`; you own only the loop and the trackers.
- **Latest naming enforced.** The critic re-checks product names/APIs/versions each round against
  current docs + `genai-teacher/references/naming-conventions.md`.
- **Stay within plan scope.** Build what `plan.md` specifies at the specified granularity; if the plan
  and a request disagree, surface it and ask.
- **Pause over guess.** When a loop control fires, stop and report — don't loop indefinitely or lower
  the bar to force an exit.

## Optional — parallel builds

For **independent** modules/phases (e.g., P5 Analytics vs P1 RAG per the dependency map), you may run
separate build loops **in parallel via subagents**, one per module, each doing its own maker→critic
loop and tracker sync. Default to **sequential** within a single run for deterministic tracker updates;
only parallelize when the user asks and the targets share no unbuilt prerequisites.

## Related skills & files

- `genai-teacher` (maker) · `genai-teacher-reviewer` (critic) — the two skills this loop drives.
- `plan.md` (build spec + tracker) · `ROADMAP.md` (teaching order + markers) — the sources of scope.
- `genai-teacher/references/naming-conventions.md` — current naming map used every round.
