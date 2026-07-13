# plan.md — Build Plan for the Databricks GenAI Curriculum Artifacts

> **What this is:** the build spec **and** living progress tracker for generating the
> `.md` (explainer) + `.html` (interactive) + `.py` (Databricks notebook) artifacts for every
> module and topic in [`ROADMAP.md`](ROADMAP.md). Work proceeds **phase by phase**; each item is
> authored with the **`genai-teacher`** skill and signed off with the **`genai-teacher-reviewer`**
> skill. This file is the single place that says *what to build, at what granularity, in what order,
> and what's done*.

> 📌 **Decisions locked (2026-07-12):** granularity = **Hybrid** (one MD+HTML per module with a
> numbered entry per topic, **plus** standalone deep-dives for cornerstone topics); notebooks =
> **Hybrid** (one module lab + standalone notebooks for cornerstone hands-on topics); sequencing =
> **level-order with parallel annotations**.

---

## 1. Overview & how to use

1. Pick the current **phase** (§5), then a **module** within it.
2. For each artifact, run the **build loop** (§4): `genai-teacher` authors → `genai-teacher-reviewer`
   runs its 2-check verdict → auto-fix loop (≤3 rounds) → ✅.
3. On sign-off: flip the topic marker in `ROADMAP.md` (⬜→✅, 🔄 if partial) **and** tick the
   checkbox in the **progress tracker** (§8), pasting the file path.
4. Respect dependencies: a module can start once its prerequisites (see `ROADMAP.md` →
   *Module dependencies & parallel tracks*) are ✅. Independent phases may run in parallel (§5).

**Golden rules (from `CLAUDE.md` + skills):**
- Ground every fact in **books → current docs → `naming-conventions.md`**; cite sources; never invent APIs.
- Use the **latest product names** (Step 1b of `genai-teacher`): `mlflow.genai.evaluate`,
  `ResponsesAgent`, Databricks **AI Search** (SDK still `databricks-vectorsearch`), **Genie Agents**, etc.
- HTML must follow the shared **"Databricks Tutor Field Guide"** design system (JetBrains Mono + Source Serif 4, warm paper `#f4f1e8`, single accent `#2b2bf0` — matches the DE/Delta/PySpark/NetSec tutors); apply the
  **`technical-blog-style`** + **`humanize`** passes to all prose.

---

## 2. Artifact model & conventions

### File layout
```
modules/<NN-module-slug>/
  module.md              # module explainer — one numbered entry per topic (T2/T3 topics live here)
  module.html            # interactive tutor-front page — mirrors module.md
  <topic-slug>.md/.html  # cornerstone (T1) deep-dive pair (only for flagged topics)
notebooks/<NN-module-slug>/
  <NN>-module-lab.py     # one consolidated runnable lab for the module's hands-on flow
  <topic-slug>.py        # standalone notebook for a cornerstone hands-on topic
```

### Module slugs
`00-platform-foundations` · `01-genai-llm-fundamentals` · `02-prompt-engineering` ·
`03-data-prep-chunking` · `04-embeddings-ai-search` · `05-building-rag-chain` · `06-mlflow-core` ·
`07-mlflow-tracing` · `08-evaluating-genai` · `09-agent-fundamentals` · `10-agent-bricks` ·
`11-deployment-serving` · `12-responsible-genai` · `13-production-monitoring` · `14-aibi-genie` ·
`15-business-semantics` · `16-cost-performance-scaling` · `17-reference-architectures` ·
`track-c-certification` · `track-d-fde-delivery`

### Formats
- **MD** — the written explainer (skeleton in `genai-teacher` Step 3): TL;DR · Why it matters ·
  Core concepts · 🗺️ Visual map (≥1 Mermaid) · How it works on Databricks · Worked example ·
  IMPORTANT/TIP/GOTCHA · 📝 Notes (+5-question quiz) · cert mapping · Sources.
- **HTML** — self-contained interactive page in the shared **Databricks Tutor Field Guide** front;
  **numbered entry per topic**; mirrors the MD's Mermaid diagram(s); slim sticky topbar; code-rich
  interactive labs/diagrams; light "paper" editorial look (no dark SaaS dashboard).
- **NB** — Databricks source format `.py` (`# Databricks notebook source`, `# COMMAND ----------`,
  `# MAGIC %md`); prereqs header (compute, DBR/MLflow version, UC objects, endpoints, secrets);
  runnable, commented, UC-first, serverless-friendly.

---

## 3. Artifact-tiering rubric (single vs multiple)

| Tier | Which topics | Artifacts produced |
|---|---|---|
| **T1 — Cornerstone** | high complexity + high importance; the module centerpiece | **Standalone MD + HTML** (deep-dive) **+ NB** if hands-on — *and* still summarized as an entry in `module.md/html` |
| **T2 — Standard** | normal depth | Covered as a **numbered entry in `module.md/html`**; hands-on rolled into the **module lab NB** |
| **T3 — Light/related** | short, tightly-coupled sub-topics | Folded into a **module entry** (may share one entry with a sibling) |

**Notebook policy**
- `[T]` (theory) → **no notebook**; put diagrams + config snippets + UI navigation in the MD/HTML.
- `[H]` / `[T+H]` → included in the **module lab NB**; **cornerstone hands-on** topics also get a
  **standalone NB**.
- Pure-concept modules → module MD/HTML only (no lab).

---

## 4. Build loop (per item) & quality gates

```
author (genai-teacher)
   → review (genai-teacher-reviewer): Check 1 terminology/API/version + Check 2 compliance
   → verdict ✅ / 🟡 / 🔴
   → if not ✅: apply targeted fixes → re-review  (cap 3 rounds)
   → ✅ Approved
   → flip ROADMAP.md marker + tick plan.md checkbox + paste path
```

**Quality gates (must all pass to mark ✅):**
- Reviewer verdict **✅ Approved** (no hallucinated/outdated API, product name, or version).
- MD has ≥1 Mermaid diagram; HTML mirrors it and follows the shared Tutor Field Guide design system.
- Sources cite the exact book chapter and/or doc URL actually used.
- Hands-on artifacts are runnable and UC-first; theory artifacts are correctly `[T]`-scoped.
- `technical-blog-style` + `humanize` passes applied.

---

## 5. Phase plan (level-order + parallel annotations)

| Phase | Level → Modules | Depends on | Can run in parallel with | Notes |
|---|---|---|---|---|
| **P0 — Foundation** | L0 (00) · L1 (01, 02) | — | — | Prereq for everything |
| **P1 — RAG Core** | L2 (03, 04, 05) | P0 | **P2, P5** | Sequential spine 03→04→05 |
| **P2 — MLflow MLOps** | L3 (06, 07, 08) | P0 | **P1, P5** | 08 needs an app to score (from P1/P3) |
| **P3 — Agents** | L4 (09, 10) | P1 + P2 | — | 10 (low-code) can start earlier as a quick win |
| **P4 — Production** | L5 (11, 12, 13) | P1/P3 + P2 | 12 partly ‖ | 13 needs 07+08+11 |
| **P5 — Conversational Analytics** | L6 (14, 15) | **P0 only** | **everything** | Fully independent — schedule any time |
| **P6 — Architect & Frontier** | L7 (16, 17) | most modules | — | 17.7 capstone is last |
| **P7 — Cross-cutting** | Track C · Track D | rolling | P1–P6 | Cert map + FDE assets, updated as modules land |

> 💡 **TIP:** the fastest cert-ready path front-loads 00→01→02→03→04→05→06→08→09→11→12; depth
> topics (07, 10, 13, 14, 15, 16, 17) can follow. P5 (Genie + metric views) is the easiest to
> hand to a second person to build in parallel.

---

## 6. Per-module artifact matrix

Legend: **T#** = topic count · **H** = # hands-on topics · **★** = cornerstone (T1) deep-dive ·
**Cert** = on the exam blueprint.

### P0 — Foundation

| Mod | T# (H) | Module MD+HTML | Cornerstone deep-dives (MD+HTML ±NB) | Notebooks | Cert |
|---|---|---|---|---|---|
| **00** Platform foundations | 6 (3) | ✔ | ★ 00.4 Mosaic AI landscape (MD+HTML) | `00-module-lab.py` (workspace/UC/compute/Marketplace) | ✓ |
| **01** GenAI/LLM fundamentals | 6 (1) | ✔ | ★ 01.6 FM APIs & external models (MD+HTML+NB) | `01-module-lab.py` (FM APIs / external models) | ✓ |
| **02** Prompt engineering | 8 (4) | ✔ | ★ 02.5 MLflow Prompt Registry (MD+HTML+NB) | `02-module-lab.py` + `02-5-prompt-registry.py` | ✓ |

### P1 — RAG Core

| Mod | T# (H) | Module MD+HTML | Cornerstone deep-dives | Notebooks | Cert |
|---|---|---|---|---|---|
| **03** Data prep & chunking | 9 (7) | ✔ | ★ 03.2 chunking strategies · ★ 03.8 AI Functions parsing | `03-module-lab.py` + `03-8-ai-parse-extract.py` + `03-9-sdp-ingestion.py` | ✓ |
| **04** Embeddings & AI Search | 9 (7) | ✔ | ★ 04.3 create/query index · ★ 04.9 reranking | `04-module-lab.py` + `04-3-create-query-index.py` | ✓ |
| **05** Building a RAG chain | 7 (5) | ✔ | ★ 05.3 full RAG chain · ★ 05.6 Model-as-Code | `05-module-lab.py` + `05-3-rag-chain.py` + `05-6-model-as-code.py` | ✓ |

### P2 — MLflow MLOps

| Mod | T# (H) | Module MD+HTML | Cornerstone deep-dives | Notebooks | Cert |
|---|---|---|---|---|---|
| **06** MLflow core | 8 (4) | ✔ | ★ 06.2 MLflow 2→3 (MD+HTML) · ★ 06.5 UC Model Registry (+NB) | `06-module-lab.py` + `06-5-uc-model-registry.py` | ✓ |
| **07** MLflow Tracing | 5 (3) | ✔ | ★ 07.2–07.3 auto + manual tracing (MD+HTML+NB) | `07-module-lab.py` (tracing) | ✓ |
| **08** Evaluating GenAI | 10 (6) | ✔ | ★ 08.1 eval harness (MD+HTML) · ★ 08.4 LLM-as-a-judge (+NB) | `08-module-lab.py` + `08-4-llm-as-judge.py` | ✓ |

### P3 — Agents

| Mod | T# (H) | Module MD+HTML | Cornerstone deep-dives | Notebooks | Cert |
|---|---|---|---|---|---|
| **09** Agent fundamentals & tools | 11 (7) | ✔ | ★ 09.3 create tools · ★ 09.6 ResponsesAgent packaging | `09-module-lab.py` + `09-3-create-tools.py` + `09-6-responsesagent.py` | ✓ |
| **10** Agent Bricks (low-code) | 8 (8) | ✔ | ★ 10.2 Knowledge Assistant · ★ 10.5 Databricks Apps | `10-module-lab.py` + `10-5-databricks-apps.py` | ✓ |

### P4 — Production

| Mod | T# (H) | Module MD+HTML | Cornerstone deep-dives | Notebooks | Cert |
|---|---|---|---|---|---|
| **11** Deployment & serving | 13 (8) | ✔ | ★ 11.1 Model Serving · ★ 11.3 AI Gateway (MD+HTML) · ★ 11.10 AI Functions batch (+NB) | `11-module-lab.py` + `11-1-model-serving.py` + `11-10-ai-functions.py` | ✓ |
| **12** Responsible GenAI | 8 (4) | ✔ | ★ 12.2 AI Guardrails (+NB) | `12-module-lab.py` + `12-2-ai-guardrails.py` | ✓ |
| **13** Production monitoring | 7 (4) | ✔ | ★ 13.5 AI/BI monitoring dashboard (+NB) | `13-module-lab.py` + `13-5-aibi-dashboard.py` | ✓ |

### P5 — Conversational Analytics (independent — parallelizable)

| Mod | T# (H) | Module MD+HTML | Cornerstone deep-dives | Notebooks | Cert |
|---|---|---|---|---|---|
| **14** AI/BI Genie | 9 (6) | ✔ | ★ 14.3 curate & tune a Genie Agent (+NB) | `14-module-lab.py` (create/tune/test) + `14-8-genie-api.py` | ✓ |
| **15** Business semantics (metric views) | 7 (6) | ✔ | ★ 15.3 query metric views (joins) (+NB) | `15-module-lab.py` + `15-3-query-metric-views.py` | ✓ |

### P6 — Architect & Frontier

| Mod | T# (H) | Module MD+HTML | Cornerstone deep-dives | Notebooks | Cert |
|---|---|---|---|---|---|
| **16** Cost, performance & scaling | 6 (2) | ✔ | ★ 16.1 Mosaic AI architecture (MD+HTML) | `16-module-lab.py` (perf/batch profiling) | ✓ |
| **17** Reference architectures | 7 (3) | ✔ | ★ 17.7 **Capstone** (MD + HTML + full end-to-end NB) | `17-7-capstone.py` (end-to-end solution) | — |

### P7 — Cross-cutting

| Track | Artifacts | Notes |
|---|---|---|
| **Track C — Certification** | `track-c-certification/module.md` + `module.html` (interactive exam-domain → module map + readiness checklist); `mock-exam.md` (practice Q bank) | No NB; update as modules land |
| **Track D — FDE delivery** | `track-d-fde-delivery/module.md` + reusable one-pagers (`architecture-one-pager.html`, `poc-scorecard.html`, `production-readiness-checklist.html` — use the `databricks-one-pager` skill) | No NB; delivery assets |

**Rough totals:** ~18 module MD+HTML pairs · ~22 cornerstone deep-dive pairs · ~28 notebooks ·
Track C/D materials ≈ **~115 artifacts**.

---

## 7. Definition of Done

**Per artifact:** reviewer ✅ Approved · sources cited · Mermaid present (MD) and mirrored (HTML) ·
shared Tutor Field Guide design + style passes · notebook runnable & UC-first (if hands-on).

**Per module:** module MD+HTML done · all cornerstone deep-dives done · module lab NB done (if any
hands-on) · every topic marker in `ROADMAP.md` flipped · all boxes ticked in §8 · at module boundary,
offer the consolidated module notebook / mini-project (per `genai-teacher`).

**Per phase:** all modules in the phase DoD-complete · dependency-downstream phases unblocked.

---

## 8. Progress tracker

Tick as built; paste the path. `[ ]` todo · `[~]` in progress · `[x]` done (reviewer ✅).

### P0 — Foundation ✅ (built + INDEPENDENTLY reviewed ✅ by genai-teacher-reviewer, 16 artifacts)
- [x] **00** module.md · [x] module.html · [x] 00-module-lab.py · [x] ★00.4 mosaic-ai-landscape (md+html) — `modules/00-platform-foundations/` · `notebooks/00-platform-foundations/`
- [x] **01** module.md · [x] module.html · [x] 01-module-lab.py · [x] ★01.6 foundation-model-apis (md+html) — `modules/01-genai-llm-fundamentals/` · `notebooks/01-genai-llm-fundamentals/`
- [x] **02** module.md · [x] module.html · [x] 02-module-lab.py + 02-5-prompt-registry.py · [x] ★02.5 prompt-registry (md+html) — `modules/02-prompt-engineering/` · `notebooks/02-prompt-engineering/`

### P1 — RAG Core
- [x] **03** module.md · [x] module.html · [x] 03-module-lab.py · [x] ★03.2 chunking-strategies (md+html) · [x] ★03.8 ai-parse-extract (md+html) · [x] 03-8-ai-parse-extract.py · [x] 03-9-sdp-ingestion.py — reviewer ✅ (🟡→fixed) — `modules/03-data-prep-chunking/` · `notebooks/03-data-prep-chunking/`
- [x] **04** module.md · [x] module.html · [x] 04-module-lab.py · [x] ★04.3 create-query-index (md+html) · [x] ★04.9 reranking (md+html) · [x] 04-3-create-query-index.py — reviewer ✅ (content 🟡→fixed; notebooks ✅ first pass) — `modules/04-embeddings-ai-search/` · `notebooks/04-embeddings-ai-search/`
- [x] **05** module.md · [x] module.html · [x] 05-module-lab.py · [x] ★05.3 rag-chain (md+html) · [x] ★05.6 model-as-code (md+html) · [x] 05-3-rag-chain.py · [x] 05-6-model-as-code.py — reviewer ✅ (content 🟡→fixed; notebooks 🟡→fixed) — `modules/05-building-rag-chain/` · `notebooks/05-building-rag-chain/`

### P2 — MLflow MLOps
- [x] **06** module.md · [x] module.html · [x] 06-module-lab.py · [x] ★06.2 mlflow-2-to-3 (md+html) · [x] ★06.5 uc-model-registry (md+html) · [x] 06-5-uc-model-registry.py — reviewer ✅ (content ✅ first pass; notebooks ✅ first pass) — `modules/06-mlflow-core/` · `notebooks/06-mlflow-core/`
- [x] **07** module.md · [x] module.html · [x] 07-module-lab.py · [x] ★07.2–07.3 tracing (md+html) — reviewer ✅ (content 🟡→fixed; notebook 🔴 search_traces bug→fixed) — `modules/07-mlflow-tracing/` · `notebooks/07-mlflow-tracing/`
- [ ] **08** module.md · [ ] module.html · [ ] 08-module-lab.py · [ ] ★08.1 · [ ] ★08.4

### P3 — Agents
- [ ] **09** module.md · [ ] module.html · [ ] 09-module-lab.py · [ ] ★09.3 · [ ] ★09.6
- [ ] **10** module.md · [ ] module.html · [ ] 10-module-lab.py · [ ] ★10.2 · [ ] ★10.5

### P4 — Production
- [ ] **11** module.md · [ ] module.html · [ ] 11-module-lab.py · [ ] ★11.1 · [ ] ★11.3 · [ ] ★11.10
- [ ] **12** module.md · [ ] module.html · [ ] 12-module-lab.py · [ ] ★12.2
- [ ] **13** module.md · [ ] module.html · [ ] 13-module-lab.py · [ ] ★13.5

### P5 — Conversational Analytics
- [ ] **14** module.md · [ ] module.html · [ ] 14-module-lab.py · [ ] ★14.3 · [ ] 14-8-genie-api.py
- [ ] **15** module.md · [ ] module.html · [ ] 15-module-lab.py · [ ] ★15.3

### P6 — Architect & Frontier
- [ ] **16** module.md · [ ] module.html · [ ] 16-module-lab.py · [ ] ★16.1
- [ ] **17** module.md · [ ] module.html · [ ] ★17.7 capstone (md+html+nb)

### P7 — Cross-cutting
- [ ] **Track C** module.md · [ ] module.html · [ ] mock-exam.md
- [ ] **Track D** module.md · [ ] architecture-one-pager.html · [ ] poc-scorecard.html · [ ] production-readiness-checklist.html

---

## 9. Effort estimate & parallelization

- **~115 artifacts** total; pause-friendly after any phase.
- **Parallel opportunities:** P1 (RAG) ‖ P2 (MLflow) ‖ P5 (Analytics) after P0; P7 rolls alongside.
- **Suggested single-builder order:** P0 → (P1 interleaved with P2) → P3 → P4 → P5 → P6, with P7
  updated at each module boundary.
- **Team split:** RAG (03–05) · MLflow (06–08) · Analytics (14–15) in parallel, then converge on
  Agents (09–10) → Production (11–13) → Architect (16–17).

> 📌 **IMPORTANT:** `ROADMAP.md` stays the source of teaching order and progress markers; this
> `plan.md` is the build/execution layer on top of it. Keep the two in sync (flip the ROADMAP marker
> whenever you tick a box here).
