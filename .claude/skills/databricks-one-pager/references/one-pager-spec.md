# One-Pager Content Contract

A one-pager is a **30-second-recall interview aid**, not a tutorial. Target
length: **~1–1.5 printed pages** (roughly 350–550 words of prose + one diagram +
one snippet). If you're writing paragraphs, you've gone too deep — cut to bullets.

## The nine blocks (in order)

| # | Block | Budget | Rule |
|---|-------|--------|------|
| 1 | Hero | — | crumb + eyebrow + h1 (one italic word) + 1-sentence lede + 2–3 pills |
| 2 | In one line | 1 sentence | the elevator definition; bold |
| 3 | Why it matters | 1–2 sentences | the problem solved / when to reach for it |
| 4 | Core concepts | 3–6 items | term + ONE sentence each; cards or arrow-bullets |
| 5 | Interactive diagram | 1 | inline SVG + small JS; ≤ 8 nodes; mandatory |
| 6 | Minimal example | ≤ ~15 lines | ONE snippet; comment the line that matters |
| 7 | Gotchas & limits | 2–4 bullets | defaults, when NOT to use, Preview caveats |
| 8 | Interview soundbites | 2–3 one-liners | "if asked X, say Y"; in a `.callout` |
| 9 | References | — | exact cited doc URLs + "Verified <Month Year>" |

## Good vs bad

**Core concept — good:** "Liquid clustering — `CLUSTER BY` keys you can redefine
with no table rewrite; replaces partitioning + Z-order."
**Bad:** A three-sentence history of how Z-ordering led to clustering.

**Why it matters — good:** "Auto Loader incrementally ingests new files from cloud
storage without you tracking what's already processed — the default for
file-based ingestion."
**Bad:** A paragraph comparing every ingestion option on the platform.

**Soundbite — good:** "Photon is a vectorized C++ engine that's a drop-in
accelerator for SQL and DataFrame workloads — no code change, you just see it in
the query plan."

## Hard rules

- **Every non-obvious fact is grounded** in a `docs.databricks.com` page you
  actually fetched, and the URL appears in References. No memory-only claims.
- **GA vs Preview must be correct** as of the verification date. Pill it.
- **Respect rebrands:** Lakeflow Declarative Pipelines (← Delta Live Tables),
  Lakeflow Jobs (← Workflows). Note the old name once in parentheses.
- **One snippet, one diagram.** Resist adding a second of either.
- **No emojis in body copy.** No filler intros. No "as we can see".
- **Self-contained HTML.** Inline CSS/JS; only the Google Fonts link is external.
- File name: `one-pagers/<NN>-<slug>.html`, where `NN` is the curriculum order.
