# Pre-Ship Verification Checklist

Run this gate before declaring a one-pager done. If any item fails, fix it.

## Grounding & accuracy
- [ ] Fetched `llms.txt` and the 2–4 specific doc pages for this feature.
- [ ] Every non-obvious fact traces to a cited `docs.databricks.com` URL.
- [ ] GA vs Preview status is correct as of the verification date (and pilled).
- [ ] Rebrands handled: Lakeflow Declarative Pipelines (← DLT), Lakeflow Jobs
      (← Workflows); old name shown once in parentheses.
- [ ] Any PySpark/DeltaTable API in the snippet verified via `spark-api-beta`.

## Content contract
- [ ] All nine blocks present and in order (Hero → References).
- [ ] Core concepts = 3–6 items, each a term + ONE sentence (no paragraphs).
- [ ] Exactly ONE snippet, ≤ ~15 lines, the line that matters is commented.
- [ ] Exactly ONE interactive diagram, ≤ 8 nodes, works on click/tab.
- [ ] Diagram renders a sensible default with JS disabled.
- [ ] 2–3 interview soundbites that can be said out loud.
- [ ] Whole page fits ~1–1.5 printed pages. No padding, no filler, no emojis.

## Build & house style
- [ ] Self-contained `.html`; inline CSS/JS; only Google Fonts external.
- [ ] Palette/fonts copied from `style-template.html` (not re-invented).
- [ ] Saved as `one-pagers/<NN>-<slug>.html`.
- [ ] `one-pagers/index.html` updated with a card linking the new page.
- [ ] Opens in a browser with no console errors.

## Report back
- [ ] State what was built, which docs were cited, and what you deliberately cut.
