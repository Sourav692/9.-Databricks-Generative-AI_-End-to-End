# Compliance Rubric (cached fallback)

Use this standing rubric **only if the live `genai-teacher/SKILL.md` (and project `CLAUDE.md`)
cannot be read**. Otherwise derive the checklist from the live rules + templates (they change).
When you use this cached copy, say so in the report.

## How to map teacher rules → checklist items

Each concrete instruction in the `genai-teacher` SKILL and `CLAUDE.md` becomes one Pass/Fail/N/A
row with evidence. Group them as below.

### A. Roadmap, grounding & no-hallucination
1. **Roadmap positioning** — the artifact states "You are here: Module NN → Topic X.Y", lists
   prereqs, and labels `[Theory]` / `[Hands-on]`.
2. **Book-first grounding** — concepts traceable to 📘 *Practical MLflow for Generative AI on
   Databricks* (Early Release — provisional) and/or 📗 *Databricks Certified Generative AI
   Engineer Associate Study Guide*, then current docs; nothing free-floating.
3. **No-hallucination discipline** — no invented APIs, params, config flags, or metric names;
   uncertainty is surfaced ("need to verify") not guessed; where the Early-Release book conflicts
   with current docs, docs win and a `> ⚠️ GOTCHA:` note flags the difference.

### B. Markdown explainer structure & style
4. **Two-file pair** — a `.md` explainer AND a self-contained interactive `.html` explainer are
   both produced (CLAUDE.md §4).
5. **Required MD skeleton** — TL;DR · Why it matters (for a Databricks FDE) · Core concepts ·
   🗺️ Visual map · How it works on Databricks · Worked example · IMPORTANT/TIP/GOTCHA callouts ·
   📝 Notes (with a 5-question self-check quiz) · How this maps to the certification · Sources.
6. **Simple-language-first** — plain definition before jargon; one idea per bullet; short
   paragraphs; Theory vs Hands-on clearly labeled.
7. **Callout markers** — `> 📌 IMPORTANT`, `> 💡 TIP`, `> ⚠️ GOTCHA` used meaningfully (key
   points, field tips, pitfalls & version differences).
8. **Worked example** — a concrete end-to-end example; the book's "Unity Airways" use case when
   it fits.
9. **Sources** — cites the actual 📘B1 / 📗B2 chapter and/or the exact doc/blog URL used.
10. **Certification mapping** — maps the topic to the relevant exam domain when applicable.

### C. Diagrams (BLOCKING)
11. **≥1 Mermaid diagram in the MD** — a fenced ```mermaid``` block (architecture / flow /
    sequence as fits the topic); labels with special characters quoted; no bare `&` in labels
    (use "and"/"+"). Prefer 2–3 small focused diagrams over one giant one.
12. **Diagram parity** — the same Mermaid diagram(s) are mirrored in the HTML explainer.

### D. Concrete Databricks how-to & code
13. **Concrete steps** — exact UI path / API / SDK named (not vague hand-waving).
14. **Runnable snippets for Hands-on** — short, correct PySpark / Python / SQL where the topic
    is hands-on; UC-first (`catalog.schema.object`), serverless-friendly where relevant.
15. **Accuracy (BLOCKING)** — no invented product names / APIs / flags / metrics / endpoint or
    index types; MLflow-2.x-vs-3.x scope correct; deprecated integrations flagged (e.g.
    `langchain-databricks` → `databricks-langchain`); doc/book pages cited.

### E. HTML explainer — "Databricks Field Almanac" design system
16. **Self-contained** — opens by double-click; all CSS/JS inline; Mermaid via CDN with a
    graceful offline fallback; no build step or local server.
17. **House style** — editorial ink-on-warm-paper; type = **Fraunces** (display) / **Spectral**
    (body) / **IBM Plex Mono** (labels/code); tokens paper `#f5efe4` · ink `#1b1916` · lava
    accent `#d83a17` · rule `#d9cfbc` (+ `html[data-theme="night"]` variants). **Never** Inter/
    Roboto/Arial/system fonts; **never** a generic dark SaaS dashboard or purple gradient.
17a. **Differentiation anchors (all four required)** — oversized **ghost numeral** in the
    masthead; **PLATE/FIG** diagram framing (`.plate` blueprint-grid + `data-fig="Fig. NN — …"`);
    confident **serif voice**; **sticky numbered index rail** with scroll-spy. If it could be
    mistaken for a generic template, it's wrong.
18. **Interactivity** — ≥1 genuine interactive element (collapsibles / tabs / clickable diagram
    nodes / hover tooltips / step-through next-prev); each widget's JS scoped to its container id.
19. **Theme-aware** — day/night toggle persisted to localStorage; Mermaid re-inits with paper/
    night `themeVariables` on toggle; paper-grain SVG overlay; reveal-on-scroll honoring
    `prefers-reduced-motion`.
20. **Callouts as field notes + Notes mirrored** — IMPORTANT (lava) / TIP (green) / GOTCHA
    (amber) colored left-rule + mono tag; the Notes section mirrored from the MD.
21. **Accessibility** — `:focus-visible` lava rings; tabs use `role=tab`/`role=tabpanel`; chips
    use `aria-pressed`; adequate contrast in both themes.

### F. Files, notebook & loop
22. **File locations** — explainer at `modules/<NN-module-slug>/<topic-slug>.{md,html}`; notebook
    (if built) at `notebooks/<NN-module-slug>/<topic-slug>.py`.
23. **Notebook format (if built)** — Databricks source format: first line
    `# Databricks notebook source`, cells split by `# COMMAND ----------`, markdown via
    `# MAGIC %md`; top cell lists prereqs (compute, DBR/MLflow version, UC objects, serving
    endpoints, secrets); runnable, well-commented, UC-first, serverless-friendly.
24. **Loop closed** — chat gives a 2–4 line summary + the file paths created; the ROADMAP.md
    topic marker is updated (⬜→✅, or 🔄 if partial); the notebook is offered; the next roadmap
    topic is pointed to.
25. **Ask-before-assuming** — cloud (AWS/Azure/GCP), LangChain-vs-pure-Python, foundation model,
    or serverless-vs-classic choices were resolved with one concise question, not silently guessed.

### G. Tone
26. **Patient, precise, practical**; correctness over completeness; no condescension.

## Severity mapping for the verdict

- **Blocking (🔴 if failed):** items 3 & 15 (accuracy / no hallucination), 4 (two-file pair),
  5 (MD skeleton), 11–12 (Mermaid present + mirrored), 16–17a (HTML self-contained + house style
  + all four differentiation anchors). A page that reads as a generic dark SaaS template fails 17.
- **Usually 🟡:** items 1–2, 6–10, 13–14, 18–25 when partially met; an outdated primary name/
  value used without noting the current one; missing cert mapping or roadmap positioning
  (🔴 if Sources are absent entirely — grounding is core to this project).
- **Minor (🟡):** tone/format/cosmetic only (item 26, styling nits).
- **✅ Approved:** clean on Check 1 (terminology/APIs/versions) and all blocking items pass.

A single hallucinated API/product/metric, a wrong MLflow-2-vs-3 version gate (item 15), a missing/
un-mirrored Mermaid diagram (items 11–12), or an HTML that abandons the Field Almanac design
system (items 16–17a) is enough to withhold ✅ — in this project accurate grounding and the shared
house style are the contract.
