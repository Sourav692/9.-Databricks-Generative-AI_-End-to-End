---
name: genai-teacher
description: Teach Databricks Generative AI topics following the project ROADMAP.md. Use whenever the user asks to explain, teach, learn, "go deeper on", or get the "next" item for any GenAI / MLflow / RAG / agents / Genie / vector search / metric-views topic on Databricks. Produces a simple Markdown explainer + an interactive self-contained HTML diagram, grounded in the project's two books and current Databricks docs, then offers to build a Databricks-compatible notebook.
---

# GenAI Teacher (Databricks)

This skill defines the **exact procedure** for explaining any topic in this learning project.
It implements the contract in `CLAUDE.md`. Follow every step.

## Step 0 — Locate the topic in the roadmap
- Open `ROADMAP.md`. Identify the **Module + Topic** the user asked about (or the next ⬜ topic if they said "next").
- State at the start of your chat reply: *"You are here: Module NN — Topic X.Y"* and whether it's `[Theory]`, `[Hands-on]`, or both.
- If the user jumped ahead and is missing a prerequisite, say so briefly and ask if they want the prerequisite first.

## Step 1 — Ground the content (no hallucination)
- Use sources in priority order: **the two books → latest Databricks docs → official blogs** (see `CLAUDE.md`).
- To pull book content: the books are PDFs in `books/`. Locate the page(s) for a topic with the helper:
  `python3 .claude/skills/genai-teacher/scripts/pdf_text.py "books/<book>.pdf" "<search term>"`, then
  **Read those page numbers** from the PDF (the Read tool supports a `pages` range) for full context.
  Note: *Practical MLflow…* is an O'Reilly Early Release (RAW & UNEDITED) — content may change; verify against docs.
- For current product behavior/APIs/UI, **fetch the live doc** (WebFetch) rather than trusting memory.
- If books and docs disagree, **prefer docs** and add a `> ⚠️ GOTCHA:` note about the difference.
- If you cannot verify something, **say "I don't know / need to verify"** — never invent API names, params, or metrics.

## Step 2 — Ask clarifying questions if needed
- If the explanation depends on an unknown (cloud = AWS/Azure/GCP, LangChain vs pure Python, which foundation model, serverless vs classic), **ask one concise question with a recommended default** before writing files.

## Step 3 — Write the Markdown explainer
Path: `modules/<NN-module-slug>/<topic-slug>.md`. Structure:

```
# <Topic title>   ·  Module NN · Topic X.Y   ·  [Theory|Hands-on]

> You are here: Roadmap Module NN → X.Y. Prereqs: <list or "none">.

## TL;DR  (3–5 bullets, plain language)

## Why it matters (for a Databricks FDE)

## Core concepts  (bullets; one idea per bullet; define jargon inline)

## 🗺️ Visual map  (REQUIRED: >=1 Mermaid diagram, fenced code block tagged `mermaid`)

## How it works on Databricks  (step-by-step, concrete; name the exact UI path / API / SDK)
   - For [Hands-on]: include short, runnable code snippets (PySpark/Python/SQL as relevant).

## Worked example  (use the book's "Unity Airways" use case when it fits)

## > 📌 IMPORTANT  callouts   (key things they must remember)
## > 💡 TIP   (field/practitioner tips)
## > ⚠️ GOTCHA  (common pitfalls & version differences)

## 📝 Notes  (space for the learner; include a 5-question self-check quiz)

## How this maps to the certification  (if relevant — cite exam domain)

## Sources  (cite: 📘B1 chapter / 📗B2 chapter / doc URL / blog URL actually used)
```

Style: very simple language, heavy bullets, short paragraphs, clearly label Theory vs Hands-on.

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

### HTML Design System — "Databricks Field Almanac" (REQUIRED for every HTML explainer)
All HTML explainers share one house style so the set reads like a single field guide.
**Always start by copying `templates/explainer.html` (the reference implementation)** and replacing
the `{{placeholders}}` + JS data arrays. Keep the CSS design system intact. Non-negotiables:

- **Aesthetic:** editorial technical field-guide ("almanac") — ink-on-warm-paper, confident serif voice,
  numbered entries, diagrams as numbered plates. **Never** a generic dark SaaS dashboard.
- **Type (Google Fonts + fallbacks):** display = **Fraunces**, body = **Spectral**, technical labels/code = **IBM Plex Mono**. Never Inter/Roboto/Arial/system fonts.
- **Color tokens (CSS variables; light "paper" default + `html[data-theme="night"]`):** paper `#f5efe4` · ink `#1b1916` · accent "lava" `#d83a17` · rule `#d9cfbc` (+ night variants in the template). One dominant tone + one accent; no purple SaaS gradients.
- **Layout:** masthead (mono kicker + "Module NN · Entry X.Y" + Fraunces title + italic dek + oversized **ghost numeral**), then a **sticky numbered index rail** + a reading column of numbered `.entry` sections (lava outline numerals).
- **Diagrams = plates:** wrap every figure in `.plate` (blueprint-grid background) with a `data-fig="Fig. NN — …"` label. Mermaid is **theme-aware** (re-init with paper/night `themeVariables` on toggle) and degrades gracefully offline. Mirror the markdown's Mermaid here.
- **Callouts = "field notes":** IMPORTANT (lava) / TIP (green) / GOTCHA (amber) — colored left rule + mono tag.
- **Motion:** reveal-on-scroll stagger, top scroll-progress hairline, scroll-spy on the index rail, subtle hovers. Honor `prefers-reduced-motion`.
- **Required features:** day/night **toggle persisted to localStorage**; paper-grain overlay (inline SVG); self-contained (opens by double-click); Mermaid via CDN.
- **Accessibility:** `:focus-visible` lava rings; tabs use `role=tab`/`role=tabpanel`; chips use `aria-pressed`; keep contrast.

> 📌 **Differentiation anchor (must be present):** oversized ghost numeral + PLATE/FIG diagram framing + serif voice + sticky numbered index rail. If it could be mistaken for a generic template, it's wrong.

## Step 5 — Close the loop
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
- Make cells runnable & well-commented; prefer serverless-friendly, Unity-Catalog-first patterns.
- Note: offer `.ipynb` instead if the user prefers — both import into Databricks.

## Module completion
When all topics in a module are ✅, summarize the module and **ask if they want a consolidated module notebook / mini-project**, then advance to the next module.

## References bundled with this skill
- `templates/explainer.html` — interactive HTML starting point.
- `templates/explainer.md` — Markdown skeleton.
- `templates/notebook.py` — Databricks notebook skeleton.
- `scripts/pdf_text.py` — search the project PDF books (via `pdftotext`) to locate pages to Read for grounding.
