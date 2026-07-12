# Compliance Rubric (cached fallback)

Use this standing rubric **only if the live `databricks-delta-tutor/SKILL.md`
cannot be read**. Otherwise derive the checklist from the live rules (they change).
When you use this cached copy, say so in the report.

## How to map tutor rules → checklist items

Each concrete instruction in the tutor SKILL becomes one Pass/Fail/N/A row with
evidence. Group them as below.

### A. Teaching style & structure
1. **Simple-language first, then depth** — plain definition before jargon; any
   unavoidable term defined in one sentence before use.
2. **Required section skeleton** — What it is · Why it matters · How it works (deep
   dive) · How to do it (code) · Comparison table · Uses/edge-cases/limitations ·
   Gotchas · References.
3. **Sub-topic decomposition** — the concept is broken into its sub-topics, each
   with mechanism + why + trade-off (not a single shallow explanation).
4. **Analogy + real-world use case** per feature.
5. **Depth, not trivia** — mechanism + trade-off explained; rare flags/param dumps
   cut or linked; no padding/repetition.

### B. Code (markdown AND HTML)
6. **Code present for every code-bearing sub-topic** — OPTIMIZE, CLUSTER BY,
   TBLPROPERTIES, ANALYZE, ALTER … ENABLE PREDICTIVE OPTIMIZATION, etc.
7. **Enterprise-shaped + commented** — realistic predicates/properties; non-obvious
   lines commented; SQL and PySpark/DeltaTable where both are common.
8. **Contrast where it teaches** — naive vs right (e.g. `repartition(1)` vs optimized
   writes; partition-by-high-cardinality vs cluster-by).
9. **UC 3-level names + Delta default** — `catalog.schema.table`; no `USING DELTA`.

### C. Accuracy (BLOCKING)
10. **No invented** properties/flags/syntax/UI paths.
11. **Defaults, thresholds & version gates correct** — verified against docs/fact-sheet
    (128 MB / 256 MB–1 GB; 32 cols; ≤4 keys; 1 TB; 7-day VACUUM; LC GA 15.4 LTS+;
    OPTIMIZE FULL 16.0+; convert 18.1+; predictive optimization default ≥ Nov 11 2024).
12. **Doc pages cited** — canonical Azure (or AWS) URLs in References.
13. **Current best practices** — liquid clustering for new tables; UC managed +
    predictive optimization; deprecated patterns (over-partitioning, repartition
    before write, ZORDER for new tables) flagged, not recommended.

### D. Artifacts
14. **Order honored** — markdown → HTML → notebook.
15. **Notebook conventions** — prereqs header (DBR/tier), UC namespacing, Delta
    default, commented cells, cleanup cell.
16. **`create → stress → apply → MEASURE`** — the notebook proves the effect with
    `DESCRIBE DETAIL` (numFiles/sizeInBytes), `DESCRIBE HISTORY`, and/or query timing.
17. **Uses, edge cases & limitations** block in every artifact.
18. **HTML self-contained + house style + interactive** — Fraunces/Spline fonts,
    paper-ink palette, all CSS/JS inline (fonts CDN ok), ≥1 genuinely interactive
    diagram (more when the topic warrants), each diagram's JS scoped to its container.
19. **No-notebook case** — if a topic is conceptual/UI-driven, the markdown gives the
    exact Databricks UI steps + equivalent SQL/CLI instead.

### E. Tone
20. **Patient, precise, practical**; correctness over completeness; no condescension.

## Severity mapping for the verdict

- **Blocking (🔴 if failed):** items 10–13 (accuracy), 2–3 (structure), 6 (code present).
- **Usually 🟡:** items 1, 4–5, 7–9, 14–19 when partially met; outdated primary name/value.
- **Minor (🟡):** tone/format/cosmetic only (item 20, styling nits).
- **✅ Approved:** clean on Check 1 (terminology/defaults) and all blocking items pass.

A single wrong default/threshold/version gate (item 11) is enough to withhold ✅ —
in this track those numbers drive real design and tuning decisions.
