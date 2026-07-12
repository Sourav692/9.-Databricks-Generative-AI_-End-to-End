# Compliance Rubric — derived from databricks-de-tutor

This is the standing checklist the reviewer uses for **Check 2**. Always prefer
the **live** `databricks-de-tutor/SKILL.md` (rules change); use this file as the
mapping guide and as a fallback when the tutor skill can't be located. When you
fall back to this cached rubric, say so in the report.

## How to use

1. Read the tutor `SKILL.md` + its `references/`.
2. For each rule below, decide **Pass / Fail / N/A** against the artifact.
3. Give evidence (a quote or `file:line`) for Pass; a precise gap for Fail.
4. Mark **N/A** with a reason when a rule doesn't apply to the artifact type
   (e.g. notebook-convention rules when reviewing a concept-only lesson).

## Rubric items

### A. Teaching style & structure
- **A1 — Simple-first:** plain-language explanation precedes technical depth.
- **A2 — Jargon defined:** each unavoidable technical term gets a one-sentence
  plain definition before use.
- **A3 — Required sections:** What it is → Why it matters → How it works → How to
  do it → comparison table (where useful) → common mistakes/gotchas → references.
- **A4 — Bullets & headings:** clear headings/subheadings; bullets used where
  they improve clarity.
- **A5 — Comparison table and/or gotchas** present when the topic warrants.
- **A6 — Sub-topic decomposition & depth:** the topic is broken into its
  sub-topics, each with its own subheading and a genuine deep dive (mechanism +
  *why* + trade-off), not a one-line skim. A shallow lesson that only states
  definitions without explaining how the feature actually works → Fail.
- **A7 — Trivia pruned:** depth is spent on enterprise-relevant mechanics, not
  exhaustive parameter dumps, deprecated options, or academic minutiae.

### B. Accuracy (BLOCKING)
- **B1 — No invented APIs/params/flags/UI paths/features.**
- **B2 — Doc grounding:** version-sensitive claims cite a specific
  `docs.databricks.com` (or learn.microsoft.com/azure/databricks) page.
- **B3 — Uncertainty flagged:** anything unconfirmed is explicitly marked, not
  asserted as fact.
- **B4 — Sources distinguished:** official docs vs. third-party clearly labeled.

### C. Current best practices & naming
- **C1 — Delta Lake** is the default table format.
- **C2 — Unity Catalog 3-level namespace** `catalog.schema.table` used.
- **C3 — Current Lakeflow naming** (Connect / Spark Declarative Pipelines (SDP) /
  Designer / Jobs); deprecated names flagged or mapped.
- **C4 — Auto Loader / COPY INTO / medallion** used over deprecated patterns;
  UC Volumes over DBFS mounts.

### CC. Code examples (BLOCKING for teaching artifacts) — see SKILL.md "Required: code examples"
- **CC1 — Code present:** every markdown and HTML teaching artifact includes real
  code snippets; every sub-topic with a code surface (SQL/PySpark/config) shows
  it rather than describing it in prose only. Missing code on a code-bearing
  topic → Fail.
- **CC2 — Enterprise-shaped & commented:** snippets use production patterns
  (predicates, options, checkpoints, ZORDER/clustering, etc.), not bare toy
  one-liners, and comment the non-obvious lines.
- **CC3 — Both languages where common:** Spark SQL and PySpark/DataFrame variants
  shown when both are commonly used for the task.
- **CC4 — Code accuracy:** no invented options/signatures; snippets use UC
  3-level names and Delta defaults; APIs verifiable against docs (ties to B1).
- **CC5 — UI/no-code topics:** still show the equivalent CLI / Asset Bundle /
  JSON-YAML / REST-SDK config alongside the click-path.

### D. Scope
- **D1 — On-topic:** content matches the requested DE topic; no out-of-scope
  filler. (If the request defined exclusions — e.g. "no Spark core", "no
  workspace basics" — confirm they're respected.)

### E. Artifact order & format (per the tutor's "Artifact creation order")
- **E1 — Order:** markdown first → HTML second → notebook last.
- **E2 — Notebook conditional:** notebook created only when it adds value; the
  decision is stated.
- **E3 — Module-level notebooks:** for a multi-topic module, 1–2 notebooks cover
  all topics — NOT one per topic.
- **E4 — No-notebook fallback:** when no notebook is warranted, the markdown lays
  out step-by-step **Databricks UI** actions instead.

### F. Notebook conventions (N/A if no notebook) — see notebook-conventions.md
- **F1 — Header cell:** title, goal, prerequisites (cluster/DBR/permissions),
  "what you'll learn".
- **F2 — Namespacing:** `catalog.schema.table`, parameterized catalog/schema.
- **F3 — Delta default; UC Volumes** for files (not DBFS mounts).
- **F4 — Commented, runnable** top-to-bottom; small cells; `%sql`/`%python`
  magics used appropriately.
- **F5 — Cleanup cell** at the end so it's rerunnable.

### G. HTML conventions (N/A if no HTML) — see html-template.md
- **G1 — Self-contained:** inline CSS/JS, opens standalone in a browser.
- **G2 — Interactive diagram(s):** at least one, and more when the concept
  warrants (per-sub-concept/stage/comparison); not capped at one.
- **G3 — Multiple-diagram hygiene:** each diagram's CSS/JS scoped to its own
  container (no ID/handler collisions).
- **G4 — Matches lesson sections; references section links cited docs.**

### H. Markdown conventions (N/A if no markdown)
- **H1 — Headings/sections** mirror the lesson.
- **H2 — Mermaid diagram** included where possible (or UI steps when no notebook).

### I. Tone
- **I1 — Patient, precise, practical; correctness over completeness; not
  condescending, not oversimplified-to-wrong.**

## Severity mapping (feeds the verdict)
- **Blocking (→ 🔴 Needs revision):** any B-item failure; A3 (required structure)
  failure on a teaching lesson; **A6 (no sub-topic depth — shallow/skim lesson);
  CC1 (no code on a code-bearing topic) or CC4 (inaccurate/invented code).**
- **Major (→ 🟡 at least):** outdated primary product name unflagged (C3);
  E-item failures; missing interactive diagram in an HTML artifact (G2);
  **A7 (trivia bloat), CC2/CC3/CC5 (toy/one-language/missing-config code).**
- **Minor (→ 🟡):** tone (I1), bullets/headings (A4), cosmetic gaps.
- **Clean on Check 1 + Check 2 ⇒ ✅ Approved.**
