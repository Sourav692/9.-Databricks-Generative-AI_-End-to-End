# Compliance Rubric (cached fallback)

Use this standing rubric **only if the live `databricks-pyspark-tutor/SKILL.md` cannot be
read**. Otherwise derive the checklist from the live rules (they change). When you use this
cached copy, say so in the report.

## How to map tutor rules → checklist items

Each concrete instruction in the tutor SKILL becomes one Pass/Fail/N/A row with evidence.
Group them as below.

### A. Teaching style & structure
1. **Simple-language first, then depth** — plain definition before jargon; any unavoidable
   term defined in one sentence before use.
2. **Required section skeleton** — What it is · Why it matters · How it works (deep dive) ·
   How to do it (code) · Comparison table · Uses/edge-cases/limitations · Gotchas · References.
3. **Sub-topic decomposition** — the concept is broken into its sub-topics, each with
   mechanism + why + trade-off (not a single shallow explanation).
4. **Analogy + real-world use case** per feature.
5. **Depth, not trivia** — mechanism + trade-off explained; rare flags/config dumps cut or
   linked; no padding.
5a. **Fundamental→expert depth ladder** — each lesson/sub-topic climbs plain foundation →
   mechanism → expert nuance; opens plain and ends deep; a beginner hits no unexplained
   leap and an expert finds it not shallow.
5b. **Say it once (DRY / no repeated concepts)** — each mechanism is fully explained ONCE
   in its deep-dive home; every other section adds a new angle (decision/number/symptom/
   contrast/fix) or cross-references — it does not re-derive. No ~verbatim duplicate
   sentences across sections; ≤1 "X≠Y" clarifying callout per page; no tabbed/accordion
   "diagram" that merely re-lists a deep-dive prose list. **Circular/bloated repetition is
   a finding**, not a stylistic nicety.
5c. **Bullet discipline** — one idea per bullet, bolded key-term lead-ins, parallel
   structure, ≤2 sentences per bullet, no 12+ flat-bullet walls (grouped under headings).
5d. **Readability helpers** — dense mechanisms are made easier to scan with quick cards,
   mechanism-map tables, or mistake/fix tables where helpful. Code-heavy sections include
   a one-question "how to read this code" callout. Helpers must reduce cognitive load, not
   add filler.

### B. Code + verification (markdown AND HTML)
6. **Code present for every code-bearing sub-topic** — `broadcast()`, `spark.conf.set(...)`,
   `persist(level)`/`unpersist()`, salting, `bucketBy(...)`, hints, `df.explain(...)`, etc.
7. **Enterprise-shaped + commented** — realistic joins/aggregations/configs; non-obvious
   lines commented; PySpark first, plus Spark SQL / `spark.conf.set` where common.
8. **Verification step per technique** — each technique is paired with the `.explain()` plan
   node (`BroadcastHashJoin`/`SortMergeJoin`/`Exchange`/`AQEShuffleRead`/`InMemoryTableScan`/
   `PartitionFilters`/`dynamicpruning`) or the Spark-UI signal (missing Exchange, spill, GC
   time, task-time skew) that proves it worked. **Blocking** — "apply without verify" fails.
9. **Contrast where it teaches** — naive vs right (skewed vs salted join; `collect()` vs
   `write`/`take`; default shuffle partitions vs AQE-coalesced).
10. **UC 3-level names + Delta default** — `catalog.schema.table`; no `USING DELTA`.

### C. Accuracy (BLOCKING)
11. **No invented** configs/hint-names/storage-levels/API signatures/UI paths.
12. **Defaults, thresholds, version gates & OSS-vs-Databricks scope correct** — verified
    against docs/fact-sheet (10 MB broadcast; 200 shuffle partitions; `memory.fraction` 0.6 /
    `storageFraction` 0.5; reserved 300 MiB; AQE advisory 64 MB; skew factor 5 / threshold
    256 MB; `maxResultSize` 1g; overhead factor 0.10 / min 384 MB; AQE default 3.2; DPP 3.0;
    `coalesceBucketsInJoin` false since 3.1; G1GC default 4.0; Databricks 30 MB runtime switch).
13. **Doc pages cited** — canonical Apache Spark + Azure Databricks URLs in References.
14. **Current best practices** — keep AQE on; broadcast the small side; fix skew at the
    source (AQE skew join → salting); cache only reused DataFrames + `unpersist()`; read less
    (pruning/DPP); verify in plan/UI; DataFrame over RDD. Anti-patterns (blind
    `shuffle.partitions`, `collect()` of large data, caching read-once, bigger-heap-to-beat-GC)
    flagged, not recommended.

### D. Artifacts
15. **Order honored** — markdown → HTML → notebook.
16. **Notebook conventions** — prereqs header (DBR/Spark + AQE note), UC namespacing, Delta
    default, commented cells, a "what to look for in the Spark UI" note, cleanup + `spark.conf`
    reset cell.
17. **`create → stress → apply → MEASURE`** — the notebook proves the effect with
    `df.explain(mode="formatted")`, the Spark UI (Exchange/spill/GC/task-time), and/or timing.
18. **Uses, edge cases & limitations** block in every artifact.
19. **HTML self-contained + house style + interactive** — the light "paper" editorial house
    style per `html-template.md` (JetBrains Mono 800 hero / mono chrome / Source Serif 4
    body, single electric-blue accent + red danger, warm paper bg — NO gradient hero, aurora, glassmorphism, or
    "&" in the display title), all CSS/JS inline (fonts CDN ok), ≥1 genuinely interactive
    diagram, each diagram's JS scoped to its container id.
19c. **HTML readability pattern** — mirrors the current Lesson 03 readability standard:
    early at-a-glance cards when useful; dense bullet clusters converted to tables; long
    gotcha lists converted to `Mistake | Why it hurts | Better move`; no helper block used
    merely for decoration.
19a. **Diagrams DISTINCT** — each diagram teaches a concept no other diagram/section does;
    no two demonstrate the same mechanic; a list of items lives in one prose list/table, not
    in a tabbed/accordion "diagram" that reveals the same sentences. Quality over quantity.
19b. **Diagrams PROFESSIONAL** — clear title + labels + legend where colour carries meaning;
    a live readout with a sensible default state; demonstrate-don't-narrate captions (they
    point at what to notice, not re-teach the mechanism); accessible (aria-pressed/keyboard/
    contrast); `prefers-reduced-motion` honored; exactly one "simplified illustration"
    disclaimer per simulator.
20. **Pure-concept case** — if a topic is conceptual, the markdown gives the diagrams +
    config snippets + Spark-UI navigation instead of a contrived notebook.

### E. Tone
21. **Patient, precise, practical**; correctness over completeness; no condescension.

## Severity mapping for the verdict

- **Blocking (🔴 if failed):** items 11–14 (accuracy), 2–3 (structure), 6 (code present),
  8 (verification step). Also **5b (DRY)** when repetition is bad enough to make the page
  circular/bloated and bury the new content.
- **Usually 🟡:** items 1, 4–5, 5a–5d, 7, 9–10, 15–20 (incl. 19a/19b/19c) when partially met;
  outdated primary name/value; moderate concept repetition or overlapping/redundant diagrams;
  a missing depth ladder (all one altitude).
- **Minor (🟡):** tone/format/cosmetic only (item 21, styling nits).
- **✅ Approved:** clean on Check 1 (terminology/defaults) and all blocking items pass.

A single wrong default/threshold/version gate or OSS-vs-Databricks mismatch (item 12) is
enough to withhold ✅ — in this track those numbers drive real tuning and design decisions.
