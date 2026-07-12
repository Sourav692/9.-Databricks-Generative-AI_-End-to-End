# Self-Contained Interactive HTML Lesson Page (Delta Optimization house style)

When the user accepts the HTML offer, produce a single standalone `.html` file
(`index.html` inside the topic folder) that opens directly in a browser with no
build step. **Match the existing `DBX_Delta_Optimization/lc.html` look exactly** —
copy the fonts + CSS from `references/style-template.html` and keep all CSS inline.

## The house style (must match lc.html)

- **Fonts** (one CDN `<link>` allowed): Fraunces (serif headings), Spline Sans
  (body), Spline Sans Mono (code/labels).
- **Palette** via CSS vars: warm `--paper` background, `--ink` text, `--frost`
  teal + `--frost-2` cyan accents, `--amber` for callouts/wins, `--line` borders.
- **Header**: a `.crumb` back-link to the track index, an `.eyebrow` ("Databricks ·
  Delta Optimization · Lesson NN"), a big Fraunces `h1` with one italic `.drip`
  word, a `.lede`, and `.pill` chips (GA/preview status, key default, "Verified
  Jun 2026 docs").
- **Sections**: `<section>` blocks separated by top borders; `h2` in Fraunces,
  `h3` in Spline Sans; `.callout` for the one rule to remember; `.tbl` for tables;
  dark `<pre>` code blocks with `.c`/`.k`/`.s` syntax spans and a `.tag` language label.
- **Footer**: `.doclinks` list of cited Azure Databricks doc URLs + a "verified
  June 2026 / Lakeflow rebrand" note.

## Requirements

- **Deep, enterprise-grade, code-rich** — same depth as the markdown lesson:
  mechanism + why + trade-off per sub-topic. Cut trivia; link the doc for the long tail.
- **Sub-topic sections** mirroring the markdown lesson, each a `<section>` with a
  heading, the mechanism, and a code snippet where it applies.
- **Code snippets are mandatory** for every code-bearing sub-topic — real,
  commented, enterprise-shaped, in dark `<pre><code>` blocks. SQL and/or PySpark.
- **Analogy + real-world use case per feature** — use the `.chip.analogy` and
  `.chip.usecase` labels (or inline) so each carries both.
- **Uses, edge cases & limitations** block for every feature (see SKILL.md).
- **Fully self-contained**: all CSS/JS inline. Only the Google Fonts `<link>` (and
  optionally a single highlighter CDN) may be external.
- **References** section linking the exact cited docs.

## Interactive diagrams — one or more, NOT capped at one

Add a separate interactive diagram for each major sub-concept, placed near the
section it explains. Scope each diagram's JS in an IIFE keyed to a unique container
id so handlers/`querySelector` calls don't collide. Pick the interaction that fits:

| Topic | Strong interactive diagram idea(s) |
| --- | --- |
| Traditional writes / small files | Slider: #rows → #files written; toggle coalesce/repartition; show file-count vs read-time. |
| Partitioning | Cardinality slider: low → healthy partitions, high → partition explosion (tiny files). Tabbed: good vs over-partitioned. |
| Data skipping & Z-order | **File-grid skipping simulator** (reuse lc.html's grid): pick layout (none / Z-order), run a filter, watch files scanned vs skipped + a min/max stats readout. |
| OPTIMIZE / compaction | Before/after bin-packing: click "Run OPTIMIZE" to merge many small file cells into fewer right-sized ones; show numFiles + avg size. |
| Optimized writes vs auto compaction | Timeline step-through: write → (optimized write shuffles) vs write → commit → (auto compaction merges). Side-by-side. |
| Auto optimize / target size | Table-size slider → autotuned target file size (256 MB → 1 GB) curve. |
| Liquid clustering | File-grid skipping simulator (already in lc.html) + a "change keys, no rewrite" step-through. |
| Predictive optimization | Inheritance tree (account → catalog → schema → table) you can toggle ENABLE/DISABLE/INHERIT; a maintenance-queue animation (OPTIMIZE/VACUUM/ANALYZE). |

Reusable building blocks already styled in the template: the `.grid`/`.file`
file-grid simulator, the `.seg` tabbed/segmented toggle, the `.step` clickable
accordion, the `.stat`/`.readout` metric tiles, and the `.verdict` explainer box.
Keep diagrams lightweight and genuinely interactive — not static images. End each
simulator with a one-line disclaimer that it's a simplified illustration.

## Minimal skeleton

Use `references/style-template.html` verbatim for the `<head>` + header/footer
shell, then fill `<main>` with the sub-topic sections and interleave the
interactive diagrams. Example diagram shell (scoped JS):

```html
<section>
  <h2>See it work</h2>
  <div class="lab" id="lab-optimize">
    <div class="lab-head"><span class="lab-title">Bin-packing simulator</span></div>
    <p class="lab-sub">A table of many small files. Click OPTIMIZE to compact them.</p>
    <div class="controls"><div class="seg"><button data-act="run" aria-pressed="false">Run OPTIMIZE</button></div></div>
    <div class="gridwrap"><div class="grid" id="op-grid"></div></div>
    <div class="readout">
      <div class="stat"><div class="big" id="op-files">—</div><div class="lbl">files</div></div>
      <div class="stat win"><div class="big" id="op-avg">—</div><div class="lbl">avg file size</div></div>
    </div>
    <div class="verdict" id="op-verdict"></div>
  </div>
</section>
<script>
(function(){ const root=document.getElementById('lab-optimize'); /* ...scoped... */ })();
</script>
```

## Markdown companion (always, created first)

The `.md` lesson uses the same sections and a **mermaid** diagram. Keep it concise
and bullet-driven, include the uses/edge-cases/limitations block, and put a
commented code snippet under every code-bearing sub-topic. Example diagram:

````markdown
```mermaid
flowchart LR
  A[Many small files] -->|OPTIMIZE bin-packing| B[Few right-sized files]
  B -->|ZORDER / CLUSTER BY| C[Colocated by query keys]
  C -->|data skipping| D[Scan fewer files = faster query]
```
````
