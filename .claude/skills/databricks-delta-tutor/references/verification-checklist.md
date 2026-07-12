# Verification Checklist (run before asserting version-sensitive facts)

The cardinal rule: **do not hallucinate.** Never invent APIs, parameters, table
properties, config flags, UI paths, or features. When unsure, say so and verify.

## Verify when the claim involves any of these

- Feature **availability / GA vs Preview** and the DBR version that gates it
  (e.g. liquid clustering GA = DBR 15.4 LTS+, `OPTIMIZE FULL` = DBR 16.0+,
  `REPLACE PARTITIONED BY WITH CLUSTER BY` = DBR 18.1+).
- **Syntax** of a SQL command, table property, session config, or DataFrame/DeltaTable API.
- **Defaults & thresholds** — file-size targets (128 MB / 256 MB–1 GB autotuning),
  the 32-column stats default, ≤4 clustering keys, clustering-on-write size
  thresholds, 1 TB partitioning guidance, 7-day VACUUM retention.
- **Managed vs external** behavior differences (stats, autotuning, predictive optimization).
- **UI navigation** (account console → Settings → Feature enablement, etc.) — paths change.
- Anything you "remember" but cannot pin to a current doc page.

## How to verify

1. **`databricks-docs` skill / llms.txt index**, then WebFetch the specific page.
   This track's primary source is the **Azure** docs:
   `https://learn.microsoft.com/en-us/azure/databricks/`. AWS docs
   (`https://docs.databricks.com/aws/en/`) are equivalent and may be cross-checked.
2. **`references/fact-sheet.md`** — the cached, doc-grounded values for all 9 topics
   (verified June 2026). Prefer it for defaults/versions; re-verify if a claim is
   newer or borderline.
3. **`spark-api-beta` MCP server** — PySpark/Spark/DeltaTable API signatures,
   Spark Connect/Serverless support, DBR-version availability
   (`spark_search_apis`, `spark_get_api_info`, `spark_get_version_changes`).
4. **`WebSearch` / `WebFetch`** — for the latest docs or official Databricks blog.
5. **Cite** the specific doc page URL in the lesson's References section.

## Canonical doc pages for this track

- Liquid clustering: `.../azure/databricks/tables/clustering`
- Data skipping & Z-order: `.../azure/databricks/tables/data-skipping`
- OPTIMIZE: `.../azure/databricks/tables/operations/optimize`
- Control file size (optimized writes, auto compaction, autotuning):
  `.../azure/databricks/tables/tune-file-size`
- When to partition: `.../azure/databricks/tables/partitions`
- Predictive optimization: `.../azure/databricks/optimizations/predictive-optimization`

## Known drift / rebrands to watch for (verify, don't assume)

| Current | Older / informal |
| --- | --- |
| Liquid clustering GA = **DBR 15.4 LTS+** | "GA on 15.2" (early-preview phrasing — outdated) |
| "Auto optimize" = optimizeWrite + autoCompact (table props) | treating it as one toggle |
| Lakeflow Spark Declarative Pipelines | Delta Live Tables (DLT) |
| Predictive optimization on by default (accounts ≥ Nov 11 2024) | "opt-in only" (was true earlier) |
| Unity Catalog managed tables + auto file tuning | manual `targetFileSize` everywhere |

## If you cannot verify

State plainly: "I can't confirm this is current — here's what I believe, and here's
how to check it in the docs." Do not present unverified specifics as fact.
