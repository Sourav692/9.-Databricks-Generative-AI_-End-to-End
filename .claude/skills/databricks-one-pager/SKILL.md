---
name: databricks-one-pager
description: >-
  Build clean, single-page HTML "one-pagers" (interview cheat-sheets) on
  individual Databricks platform features — important concepts + small code
  snippets + ONE interactive architecture diagram, deliberately NOT a deep
  dive. Use whenever the user asks to "make a one-pager", "create a cheat
  sheet", "summarize a feature on one page", or "build interview one-pagers"
  for Databricks topics (Unity Catalog, Delta Lake, Auto Loader, Lakeflow
  Declarative Pipelines/DLT, Lakeflow Jobs, Spark architecture, Photon,
  Structured Streaming, Liquid Clustering, Databricks SQL, compute/clusters,
  Mosaic AI / Model Serving, Vector Search, Genie, Delta Sharing, Lakebase,
  Asset Bundles, etc.). Every fact is grounded in the official Databricks
  docs and the page is rendered in the project's warm editorial house style.
metadata:
  version: '1.0.0'
  author: sourav.banerjee@databricks.com
  track: Tech Peer Round — Databricks One-Pagers
---

# Databricks Feature One-Pager Builder

You build **concise, beautiful, single-page HTML one-pagers** about one
Databricks feature at a time, for fast interview revision. A one-pager is the
opposite of the deep lessons in `DBX_Delta_Optimization/`, `Spark/`, etc. —
it is the **scannable summary you'd glance at 10 minutes before the interview**:
the handful of concepts that matter, one tiny code snippet, one interactive
diagram, the gotchas, and the talking points. Nothing more.

> **Golden rule:** if it doesn't help the reader *answer an interview question
> in 30 seconds*, it doesn't belong on the page. Cut depth, keep signal.

## When to use this skill

- The user asks to create / build / generate a **one-pager**, **cheat sheet**,
  **summary page**, or **interview revision page** for a Databricks feature.
- The user runs the `/loop` over `one-pagers/goal.md` (each iteration builds the
  next feature in the backlog using this skill).
- The user wants a quick, doc-accurate refresher on a single platform capability.

Do **not** use this skill to write long-form lessons, runnable notebooks, or
multi-section deep dives — those belong to the `*-tutor` skills in this repo.

## Required style stack

Every one-pager must use:

- `technical-blog-style` at `.claude/skills/technical-blog-style/SKILL.md` for the
  problem-first, diagram-rich, practical technical-blog structure, compressed to one page.
- `fe-workflows:humanize` at
  `/Users/sourav.banerjee/.codex/isaac-plugin-sync/marketplaces/isaac-sync-fe-vibe/plugins/fe-workflows/skills/humanize/SKILL.md`
  for the final copy pass. Preserve code, commands, APIs, citations, diagrams, HTML classes,
  and required blocks while removing AI filler, banned phrases, robotic transitions, and
  wall-of-text paragraphs.

If `fe-workflows:humanize` is not loadable, apply its default behavior manually.

## Skills & tools this skill relies on (load grounding FIRST)

Author every one-pager by grounding it in authoritative sources before writing
a single sentence. Never write Databricks facts from memory.

| Need | Skill / tool | Why |
| --- | --- | --- |
| **Ground every fact** (syntax, defaults, GA/Preview status, limits) | `databricks-docs` | Indexes the official docs via `https://docs.databricks.com/llms.txt`. This is the primary ground truth — fetch the relevant page and cite it. |
| House-style HTML look & component vocabulary | `databricks-editorial-html` | Warm paper editorial theme; pills, callouts, diagram wrappers. |
| PySpark / DataFrame / DeltaTable API signatures + DBR availability | `spark-api-beta` (MCP) | Verify any API used in a snippet actually exists in the stated DBR. |
| Delta layout depth (OPTIMIZE, Z-order, Liquid Clustering) | `delta-table-optimizer` | Backs Delta / optimization one-pagers. |
| Spark execution, shuffle, AQE, Photon | `spark-optimization` | Backs Spark-architecture / performance one-pagers. |
| Warehouse / SQL / BI surface | `databricks-dbsql` | Backs Databricks SQL / Photon / Genie one-pagers. |
| Governance model (UC namespace, lineage, grants) | `databricks-unity-catalog` | Backs the Unity Catalog one-pager. |
| Richer hand-drawn diagram (optional) | `excalidraw-diagram` | Only if an inline SVG can't capture the architecture. |

> If a grounding skill is missing, **do not block** — fall back to
> `databricks-docs` (`llms.txt` → specific page) and proceed. Always re-verify
> version-sensitive claims (GA vs Preview, DBR version, rebrands like
> Lakeflow ← Delta Live Tables / Workflows) against the live doc.

## The grounding workflow (do this for every page)

1. **Fetch the docs index** with WebFetch: `https://docs.databricks.com/llms.txt`.
2. Find the 2–4 doc pages most relevant to the feature; fetch them.
3. Extract: the one-sentence definition, the 3–6 concepts that matter, the
   canonical minimal code/SQL, the current GA/Preview status, and 2–4 real
   limitations/gotchas. Note the exact doc URLs — you will cite them.
4. Verify any API call in the snippet against `spark-api-beta` if it's a
   PySpark/DeltaTable call.
5. Only then write the HTML. If a fact can't be grounded, leave it out rather
   than guess.

## Content contract (every one-pager has exactly these blocks)

Keep the whole page to **~1–1.5 printed pages**. Be ruthless. Order:

1. **Hero** — `.crumb` back-link to `index.html`; an `.eyebrow`
   ("Databricks · One-Pager · <Category>"); a Fraunces `h1` with one italic
   word; a one-sentence `.lede`; status `.pill` chips (e.g. `GA`, key default,
   `Verified <Month Year> docs`).
2. **In one line** — a single bolded sentence defining the feature ("X is …").
   This is the elevator-pitch the interviewer wants first.
3. **Why it matters** — 1–2 sentences on the problem it solves / when to reach
   for it.
4. **Core concepts** — **3–6** items only, as `.card`s or an arrow-bullet
   `<ul class="clean">`. Each item = a term + one tight sentence. No paragraphs.
5. **Interactive diagram** — exactly **one** inline-SVG diagram with a small
   JS interaction (tabs, toggle, or step-through) that explains the
   architecture/flow. See "Interactive diagram" below. This is mandatory.
6. **One small snippet** — a single `<pre><code>` block, **≤ ~15 lines**, the
   canonical minimal example (SQL or PySpark). Comment the one line that
   matters. Do not stack multiple snippets.
7. **Gotchas & limits** — 2–4 short bullets (defaults, when NOT to use it,
   common foot-guns, Preview caveats).
8. **Interview soundbites** — 2–3 crisp one-liners the user can say out loud
   (the "if asked X, say Y" answers). Use a `.callout`.
9. **References** — `.doclinks` list of the exact cited `docs.databricks.com`
   URLs + a "Verified <Month Year>" note.

If a block would be empty or padded, drop it — except the diagram, snippet,
soundbites, and references, which are always present.

## Style & output rules

- **One self-contained `.html` file per feature**, written to
  `one-pagers/<NN-feature-slug>.html` (e.g. `one-pagers/02-unity-catalog.html`).
  Opens directly in a browser, no build step.
- **All CSS and JS inline.** Only the Google Fonts `<link>` may be external.
  Start from `references/style-template.html` — copy its `<head>`, palette,
  and component CSS verbatim, then fill the body. Do **not** re-invent the look.
- **House style** matches the existing project pages (warm `--paper`
  background, `--ink` text, `--flame`/lava + `--violet` accents; Fraunces
  headings, Spline Sans body, Spline Sans Mono code). See `databricks-editorial-html`.
- **Concise prose.** Short sentences. Bullets over paragraphs. No emojis in body
  copy. No filler ("In this document we will…").
- **Snippets are real and minimal.** Enterprise-shaped but tiny. Use `.k`/`.s`/`.c`
  syntax spans like the existing pages.
- After writing, update the one-pager **index** (`one-pagers/index.html`) with a
  card linking the new page (create the index from the same template if absent).

## Interactive diagram (mandatory, exactly one)

Each one-pager carries **one** lightweight interactive diagram that explains the
feature's architecture or data flow. Keep it inline (SVG + a few lines of JS),
self-contained, and on-theme. Pick the simplest interaction that teaches:

- **Tabs / step-through** — reveal stages of a flow (e.g. Auto Loader: discover →
  infer schema → write → checkpoint), highlighting the active node.
- **Toggle / before-after** — compare two states (e.g. partitioning vs liquid
  clustering; classic vs serverless compute).
- **Hover-to-explain** — nodes show a one-line `.diagram-info` hint on hover/click.

Rules: label nodes in plain words; one accent color for the active/highlighted
path; keep it under ~8 nodes; the diagram must still make sense if JS is off
(render a sensible default state). `references/style-template.html` ships a
working tabbed-SVG example you can adapt — change the nodes/labels, keep the
mechanics.

## Procedure (per feature)

1. Read `one-pagers/goal.md` to confirm the feature, its category, and slug.
2. Run the **grounding workflow** above (docs + API verification).
3. Copy `references/style-template.html` → `one-pagers/<NN-slug>.html`.
4. Fill the nine content blocks. Stay within the length budget.
5. Build the one interactive diagram (adapt the template's example).
6. Run the **verification checklist** (`references/verification-checklist.md`):
   facts grounded & cited, snippet ≤15 lines and API-verified, diagram works,
   page fits ~1–1.5 pages, no uncited claims, GA/Preview correct.
7. Add/refresh the card in `one-pagers/index.html`.
8. Report: what you built, which docs you cited, anything you deliberately cut.

## Reference files in this skill

- `references/one-pager-spec.md` — the full content contract + length budget,
  expanded with examples of good vs bad blocks.
- `references/style-template.html` — the self-contained one-pager template
  (head, palette, components, a working interactive tabbed-SVG diagram). Start here.
- `references/curriculum.md` — the candidate feature list with categories,
  slugs, and the 2–3 doc pages to ground each one in.
- `references/verification-checklist.md` — the pre-ship gate every page must pass.
