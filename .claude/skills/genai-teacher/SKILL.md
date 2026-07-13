---
name: genai-teacher
description: Teach Databricks Generative AI topics following the project ROADMAP.md. Use whenever the user asks to explain, teach, learn, "go deeper on", or get the "next" item for any GenAI / MLflow / RAG / agents / Genie / vector search / metric-views topic on Databricks. Produces a simple Markdown explainer + an interactive self-contained HTML diagram, grounded in the project's two books and current Databricks docs, then offers to build a Databricks-compatible notebook.
---

# GenAI Teacher (Databricks)

This skill defines the **exact procedure** for explaining any topic in this learning project.
It implements the contract in `CLAUDE.md`. Follow every step.

## Required style stack

Every content artifact produced by this skill must use these style skills:

1. `technical-blog-style` at `.claude/skills/technical-blog-style/SKILL.md` — apply the practical
   technical-blog pattern: real problem first, why the naive path fails, plain-language core idea,
   component breakdown, diagrams, implementation, trade-offs, and field guidance.
2. `fe-workflows:humanize` at
   `/Users/sourav.banerjee/.codex/isaac-plugin-sync/marketplaces/isaac-sync-fe-vibe/plugins/fe-workflows/skills/humanize/SKILL.md`
   — run the final copy pass to remove AI-sounding filler, banned phrases, wall-of-text
   paragraphs, and the "not X, but Y" pattern while preserving factual accuracy, code, citations,
   roadmap markers, and required callouts.

If `fe-workflows:humanize` is unavailable, apply its default behavior manually: short human
paragraphs, concrete wording, natural transitions, no filler, no em dashes unless required by
existing source text, and no banned AI phrasing.

Do **not** remove or weaken the existing GenAI teacher tone rules. The content must still be
educational, beginner-friendly, practical, bullet-heavy, source-grounded, and precise. The shared
front-end rules below standardize the visual format, color palette, section order, and notebook
shape so GenAI lessons feel like the DE, Delta, PySpark, and NetSec tutor outputs.

## Required Databricks feature-skill routing

Before writing a lesson, HTML page, or notebook for a Databricks product feature, load the
feature-specific skill first. These skills contain product workflow rules, CLI/API gotchas,
decision gates, validation steps, and implementation order that generic docs do not capture.

Use this routing table:

| Topic in the GenAI roadmap | Load this skill before authoring | Why |
| --- | --- | --- |
| Databricks Apps, GenAI app deployment, AppKit, dashboards/apps, Genie-powered apps, Model Serving apps | `databricks-apps` at `/Users/sourav.banerjee/.agents/skills/databricks-apps/SKILL.md` | Enforces Databricks Apps scaffolding, data-access decision gate, AppKit docs lookup, validation, smoke-test, and deployment rules. |
| Non-AppKit Python apps on Databricks Apps, Streamlit/FastAPI/Flask/Gradio/Dash apps | `databricks-apps-python` at `/Users/sourav.banerjee/.agents/skills/databricks-apps-python/SKILL.md` when present; otherwise use `databricks-apps` Other Frameworks guidance | Covers Python app packaging and serving patterns. |
| Genie / AI-BI Genie / Genie API / Genie-powered agents or apps | `databricks-genie` at `/Users/sourav.banerjee/.agents/skills/databricks-genie/SKILL.md` | Grounds Genie workspace/table setup, space behavior, APIs, and app integration. |
| Vector Search / AI Search / retrieval indexes / retrievers | `databricks-vector-search` at `/Users/sourav.banerjee/.agents/skills/databricks-vector-search/SKILL.md` | Prevents wrong index types, SDK names, endpoint assumptions, and retrieval patterns. |
| Model Serving, Foundation Model APIs, external models, serving endpoints | `databricks-model-serving` at `/Users/sourav.banerjee/.agents/skills/databricks-model-serving/SKILL.md` | Grounds endpoint types, auth, payloads, deployment, and validation. |
| AI Functions such as `ai_query`, `ai_parse_document`, `ai_extract`, `ai_classify`, `vector_search` | `databricks-ai-functions` at `/Users/sourav.banerjee/.agents/skills/databricks-ai-functions/SKILL.md` | Prevents invented SQL function names and clarifies current function behavior. |
| Agent Bricks, Knowledge Assistant, Supervisor Agent, no/low-code agents | `databricks-agent-bricks` at `/Users/sourav.banerjee/.agents/skills/databricks-agent-bricks/SKILL.md` | Grounds current Agent Bricks workflows and product boundaries. |
| Agent evaluation, MLflow GenAI evaluation, scorers, judges | `databricks-mlflow-evaluation` at `/Users/sourav.banerjee/.agents/skills/databricks-mlflow-evaluation/SKILL.md` and `agent-evaluation` when relevant | Grounds evaluation APIs, metrics/judges, and current MLflow/Databricks evaluation behavior. |
| MLflow tracing and trace analysis | `instrumenting-with-mlflow-tracing`, `retrieving-mlflow-traces`, or `analyze-mlflow-trace` as relevant | Grounds tracing instrumentation, trace retrieval, and debugging workflows. |
| Lakebase or synced tables for apps | `databricks-lakebase` at `/Users/sourav.banerjee/.agents/skills/databricks-lakebase/SKILL.md` | Required when an app needs persistent state or low-latency operational lookup. |
| Metric views / business semantics / semantic layer | `databricks-metric-views` at `/Users/sourav.banerjee/.agents/skills/databricks-metric-views/SKILL.md` | Grounds metric-view YAML, semantics, querying, and Genie/agent metadata. |
| AI/BI dashboards and BI surfaces | `databricks-aibi-dashboards` at `/Users/sourav.banerjee/.agents/skills/databricks-aibi-dashboards/SKILL.md` | Grounds dashboard-specific workflows and BI product behavior. |
| Lakeflow Jobs or Spark Declarative Pipelines | `databricks-jobs` or `databricks-spark-declarative-pipelines` as relevant | Grounds job/pipeline creation, orchestration, and monitoring. |
| Unity Catalog governance, functions, volumes, grants, model/function namespaces | `databricks-unity-catalog` at `/Users/sourav.banerjee/.agents/skills/databricks-unity-catalog/SKILL.md` | Grounds UC permissions, namespaces, governance, and object model. |
| Python SDK examples | `databricks-python-sdk` at `/Users/sourav.banerjee/.agents/skills/databricks-python-sdk/SKILL.md` | Prevents stale SDK signatures and wrong client usage. |

Routing rules:

- Load the feature skill **before** writing the Markdown/HTML/notebook content for that topic.
- If a topic hits multiple products, load the narrowest relevant skills. Example: Topic 10.5
  "Build and deploy a GenAI app on Databricks Apps" must load `databricks-apps` first, and may
  also load `databricks-genie`, `databricks-model-serving`, or `databricks-lakebase` depending on
  the app pattern.
- If the feature skill requires a decision gate, preserve it in the lesson/notebook. For example,
  `databricks-apps` requires the Analytics vs Lakebase synced-tables decision gate before app
  scaffolding when reading Unity Catalog data.
- Do not let a feature skill override the project source hierarchy: books for concepts, current
  Databricks docs for product behavior, feature skills for implementation workflow and gotchas.
- If a named feature skill is missing or unreadable, say so briefly, fall back to `databricks-docs`
  and official docs, and do not invent missing APIs or CLI flags.

## Step 0 — Locate the topic in the roadmap
- Open `ROADMAP.md`. Identify the **Module + Topic** the user asked about (or the next ⬜ topic if they said "next").
- State at the start of your chat reply: *"You are here: Module NN — Topic X.Y"* and whether it's `[Theory]`, `[Hands-on]`, or both.
- If the user jumped ahead and is missing a prerequisite, say so briefly and ask if they want the prerequisite first.

## Step 1 — Ground the content (no hallucination)
- Use sources in priority order: **the two books → latest Databricks docs → official blogs** (see `CLAUDE.md`).
- Then apply the **Required Databricks feature-skill routing** above for product-specific workflows,
  implementation ordering, gotchas, and validation rules.
- To pull book content: the books are PDFs in `books/`. Locate the page(s) for a topic with the helper:
  `python3 .claude/skills/genai-teacher/scripts/pdf_text.py "books/<book>.pdf" "<search term>"`, then
  **Read those page numbers** from the PDF (the Read tool supports a `pages` range) for full context.
  Note: *Practical MLflow…* is an O'Reilly Early Release (RAW & UNEDITED) — content may change; verify against docs.
- For current product behavior/APIs/UI, **fetch the live doc** (WebFetch) rather than trusting memory.
- If books and docs disagree, **prefer docs** and add a `> ⚠️ GOTCHA:` note about the difference.
- If you cannot verify something, **say "I don't know / need to verify"** — never invent API names, params, or metrics.

### Step 1b — Use the LATEST product names & features (mandatory)
Databricks GenAI product names and APIs change fast, and **both books lag the product** (the MLflow
book is an Early Release). Before writing, make sure every product name, API, flag, metric, endpoint,
and index type is the **current** one:
- **Consult `references/naming-conventions.md`** (bundled with this skill) — the current-vs-legacy
  naming map (MLflow 3 `mlflow.genai`, Agent Framework `ResponsesAgent`, Agent Bricks, **Databricks
  AI Search** formerly Vector Search, AI Functions, AI Gateway / Unity AI Gateway, **Genie Agents**
  formerly Genie Spaces, **Genie One** formerly Databricks One, Lakeflow rebrands). Teach the current
  name; when a book uses the old one, add a `> ⚠️ GOTCHA:` noting the rename.
- **Then re-verify live** — the cheat-sheet is dated and many features are **Beta/Preview**. Use the
  **`databricks-docs`** skill (fetch `https://docs.databricks.com/llms.txt`, then the topic page) and
  `mlflow.org/docs/latest` for MLflow APIs. If the live doc disagrees with the cheat-sheet, the **doc
  wins** — teach that, cite the URL in Sources, and update `references/naming-conventions.md`.
- **Label maturity:** prefer **GA** features for the main path; clearly mark **Beta/Preview** ones.
- **Common traps to never get wrong:** eval = `mlflow.genai.evaluate()` (not `mlflow.evaluate(model_type="databricks-agent")`); LangChain import = `databricks-langchain` (not `langchain-databricks`/`langchain_community`); Vector Search SDK is still `databricks-vectorsearch` **despite** the "AI Search" rebrand (no `databricks-ai-search` package); agent authoring `ResponsesAgent` > `ChatAgent` > `ChatModel`.

## Step 2 — Ask clarifying questions if needed
- If the explanation depends on an unknown (cloud = AWS/Azure/GCP, LangChain vs pure Python, which foundation model, serverless vs classic), **ask one concise question with a recommended default** before writing files.

## Step 3 — Write the Markdown explainer
Path: `modules/<NN-module-slug>/<topic-slug>.md`. Structure:

```
# <Topic title>   ·  Module NN · Topic X.Y   ·  [Theory|Hands-on]

> You are here: Roadmap Module NN → X.Y. Prereqs: <list or "none">.

## TL;DR  (3–5 bullets, plain language)

## The problem  (real-world pain this solves)

## Why the naive approach fails  (what breaks, costs too much, or becomes unsafe)

## What it is  (plain-language definition)

## Why it matters (for a Databricks FDE)

## Core concepts  (bullets; one idea per bullet; define jargon inline)

## 🗺️ Visual map  (REQUIRED: >=1 Mermaid diagram, fenced code block tagged `mermaid`)

## How it works — deep dive  (sub-topic sections; mechanism + why + trade-off)

## How to do it on Databricks  (step-by-step, concrete; name exact UI path / API / SDK)
   - For [Hands-on]: include short, runnable code snippets (PySpark/Python/SQL as relevant).

## Worked example  (use the book's "Unity Airways" use case when it fits)

## Uses, edge cases & limitations  (when to use / when not / what to watch)

## Common mistakes / gotchas  (actionable fixes)

## > 📌 IMPORTANT  callouts   (key things they must remember)
## > 💡 TIP   (field/practitioner tips)
## > ⚠️ GOTCHA  (common pitfalls & version differences)

## 📝 Notes  (space for the learner; include a 5-question self-check quiz)

## How this maps to the certification  (if relevant — cite exam domain)

## Sources  (cite: 📘B1 chapter / 📗B2 chapter / doc URL / blog URL actually used)
```

Style: very simple language, heavy bullets, short paragraphs, clearly label Theory vs Hands-on.
Also apply the `technical-blog-style` structure: real problem first, naive failure mode, core idea,
system/component map, implementation, then trade-offs and field guidance.
Match the DE/Delta/PySpark/NetSec tutor markdown format: sectioned lesson, short paragraphs, tables
for comparisons/gotchas when clearer than long bullet lists, and code snippets paired with a
"how to verify it worked" note for hands-on content.

**Diagrams (REQUIRED):** every Markdown explainer must include **at least one Mermaid diagram** — a fenced
code block tagged `mermaid` (architecture / flow / sequence as fits the topic). Prefer 2–3 small, focused
diagrams over one giant one. Quote node labels that contain special characters, and avoid `&` inside labels
(use "and"/"+"). Mirror the same diagram(s) in the HTML explainer for parity.

## Step 4 — Write the interactive HTML explainer
Path: `modules/<NN-module-slug>/<topic-slug>.html`.
- Start from `.claude/skills/genai-teacher/templates/explainer.html` (self-contained: inline CSS/JS, Mermaid via CDN with a graceful fallback).
- It **must be interactive** — use at least one of: collapsible sections, tabbed views, clickable diagram nodes that reveal detail, hover tooltips, or step-through "next/prev" stages.
- Represent the concept visually (flow/architecture/sequence diagram). Keep it openable by double-click (no build step, no local server required).
- Mirror the same callouts (IMPORTANT / TIP / GOTCHA) and a Notes section.

### HTML Design System — shared Databricks Tutor Field Guide (REQUIRED for every HTML explainer)
All HTML explainers share one house style with the DE, Delta, PySpark, and NetSec tutor outputs.
**Always start by copying `templates/explainer.html` (the reference implementation)** and replacing
the `{{placeholders}}` + JS data arrays. Keep the CSS design system intact. Non-negotiables:

- **Aesthetic:** light "paper" editorial / technical-manual look, same front as the tutor tracks:
  restrained, readable, code-rich, educational. **Never** a generic dark SaaS dashboard.
- **Type (Google Fonts + fallbacks):** **JetBrains Mono** for hero, labels, controls, and code;
  **Source Serif 4** for body prose and section headings. This matches the PySpark shared front
  and keeps GenAI pages aligned with the newer tutor format.
- **Color tokens (CSS variables):** warm paper `--bg:#f4f1e8`, card `--card:#fbfaf5`,
  panel `--panel:#efe9d9`, ink `--ink:#17140d`, muted/faint warm grays, hairline `--line`,
  single accent `--accent:#2b2bf0`, danger `--danger:#b91c1c`, ok `--ok:#2f7d55`.
  Use one primary accent. No purple SaaS gradients, aurora backgrounds, glassmorphism, or dark-only themes.
- **Layout:** slim sticky topbar, dotted-paper hero, mono uppercase `h1.display`, `.figstamp`,
  `.subline`, `.lede`, `.spec` chips, then a single readable `.wrap` column with section hairlines.
  Use `.seclabel` section labels and keep the same order as the Markdown.
- **Diagrams:** use `.lab`, `.plate`, `.seg`, `.flowline`, `.stepbox`, `.quickgrid`,
  `.quickcard`, and Mermaid where it adds structure. Mirror the Markdown Mermaid diagram in HTML.
- **Callouts:** use `.callout`, `.callout.warn`, and note variants for IMPORTANT / TIP / GOTCHA.
- **Motion:** subtle reveal/progress only. Honor `prefers-reduced-motion`.
- **Required features:** self-contained, opens by double-click, inline CSS/JS, Mermaid via CDN with
  graceful fallback. A light-only front is preferred so it visually matches the tutor tracks.
- **Accessibility:** `:focus-visible` accent rings; tabs use `role=tab`/`role=tabpanel`; chips use `aria-pressed`; keep contrast.

> 📌 **Differentiation anchor (must be present):** heavy mono hero + warm paper editorial front
> + serif reading face + section hairlines + code-rich interactive labs. If it looks like the old
> GenAI-only Almanac instead of the shared tutor front, revise it.

## Step 5 — Close the loop
- Before finalizing, run a style and humanization pass over the Markdown and HTML visible copy:
  - Apply `technical-blog-style`.
  - Apply `fe-workflows:humanize` or its default behavior if the skill cannot be loaded.
  - Preserve required markers, citations, code blocks, Mermaid syntax, HTML classes/IDs, and factual claims.
- In chat, give a 2–4 line summary and the **file paths** you created.
- Update the topic marker in `ROADMAP.md` (⬜ → ✅) — and 🔄 if partially done.
- **Ask:** *"Would you like me to create a Databricks-compatible notebook for this topic?"*
- Point to the **next** roadmap topic.

## Step 6 — Notebook (only if user says yes)
- Path: `notebooks/<NN-module-slug>/<topic-slug>.py`, **Databricks source format**:
  - First line: `# Databricks notebook source`
  - Cells separated by: `# COMMAND ----------`
  - Markdown cells via: `# MAGIC %md`
- Top cell: prerequisites (compute type, runtime/MLflow version, Unity Catalog objects, serving endpoints, secrets).
- Match the DE/Delta/PySpark/NetSec notebook teaching style:
  - educational `%md` cells before code, using the same section order as the Markdown lesson;
  - short setup cells, then focused runnable cells;
  - code comments explain **why** each non-obvious line exists;
  - include a "how to verify it worked" cell after important operations;
  - end with recap, gotchas, cleanup if relevant, and the next roadmap topic.
- Make cells runnable & well-commented; prefer serverless-friendly, Unity-Catalog-first patterns.
- Note: offer `.ipynb` instead if the user prefers — both import into Databricks.

## Step 7 — Revision (critic-loop) mode
This skill is the **maker** in the `genai-build-loop` critic loop (maker → critic → revise). When you
are invoked with a `genai-teacher-reviewer` findings report (or by `genai-build-loop`), operate in
**revision mode**, not fresh-authoring mode:
- **Apply only the prioritized fixes** the reviewer listed — do not rewrite or re-expand approved
  sections. Preserve factual content, citations, code, callouts, `[Theory]/[Hands-on]` labels, roadmap
  markers, and **MD↔HTML Mermaid parity**.
- **Regenerate only the affected artifact(s)** named in the findings; if a fix changes a fact or diagram
  in one artifact, propagate it to the others (MD / HTML / notebook) so they stay consistent.
- **Re-verify each corrected fact** against current docs + `references/naming-conventions.md` — never
  swap one wrong value for another.
- **Return control to the loop.** Do not self-approve; the critic re-checks and owns the verdict.

**Pre-flight self-check (before first hand-off, to cut loop rounds):** quickly self-audit the draft
against the reviewer's two checks — current product names/APIs/versions (Step 1b), the required MD
skeleton, ≥1 Mermaid mirrored in HTML, the shared tutor HTML design system, hands-on verification steps,
and cited Sources. Fix obvious gaps before submitting for critique.

## Module completion
When all topics in a module are ✅, summarize the module and **ask if they want a consolidated module notebook / mini-project**, then advance to the next module.

## References bundled with this skill
- `references/naming-conventions.md` — **current-vs-legacy Databricks GenAI naming & feature map**
  (consult in Step 1b so lessons use the latest product names/APIs; re-verify live).
- `templates/explainer.html` — interactive HTML starting point.
- `templates/explainer.md` — Markdown skeleton.
- `templates/notebook.py` — Databricks notebook skeleton.
- `scripts/pdf_text.py` — search the project PDF books (via `pdftotext`) to locate pages to Read for grounding.
- `.claude/skills/technical-blog-style/SKILL.md` — practical technical-blog voice and structure.
- `/Users/sourav.banerjee/.codex/isaac-plugin-sync/marketplaces/isaac-sync-fe-vibe/plugins/fe-workflows/skills/humanize/SKILL.md`
  — final humanization pass when available.
