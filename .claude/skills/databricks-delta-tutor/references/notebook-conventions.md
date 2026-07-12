# Databricks Notebook Conventions (Delta Optimization track)

Delta optimization is hands-on, so **default to one runnable notebook per topic**.
Each notebook should *demonstrate and measure* the technique, not just describe it.

## File format

- Prefer a Databricks **source notebook** as `.py` (git-friendly), or `.ipynb`.
- For `.py` source notebooks, the first line must be:

```python
# Databricks notebook source
```

- Separate cells with:

```python
# COMMAND ----------
```

- Magic commands as the first line of a cell: `# MAGIC %md` (narration),
  `# MAGIC %sql` (SQL). `%python` is implicit in `.py`.

## Required header cell (every notebook)

Begin with a markdown cell stating:

- **Title** and one-line goal.
- **Prerequisites**: cluster/runtime (e.g. "DBR 15.4 LTS+ for liquid clustering",
  "Premium + serverless for predictive optimization", "DBR 16.0+ for `OPTIMIZE FULL`"),
  Unity Catalog enabled, required grants, any source data/volume.
- **What you'll learn** (3–5 bullets).

> For each feature demonstrated, add a brief markdown cell on its **uses, edge
> cases & limitations** (see SKILL.md).

## Namespacing & table format

- Unity Catalog **three-level namespacing**: `catalog.schema.table`.
- Parameterize catalog/schema at the top with widgets or variables:

```python
catalog = "main"
schema  = "delta_opt_demo"
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.{schema}")
spark.sql(f"USE {catalog}.{schema}")
```

- **Delta Lake** is the default format — do NOT write `USING DELTA` unless
  contrasting formats. Store files in **UC Volumes**, not DBFS mounts.

## The pattern that makes these lessons land: create → stress → apply → MEASURE

Every Delta optimization notebook should let the learner *see the numbers move*:

1. **Create** a small demo table.
2. **Stress** it to create the condition the technique fixes — e.g. write data in
   many tiny batches to produce small files, generate skewed/high-cardinality data,
   or over-partition.
3. **Inspect the "before"** with the measurement toolkit below.
4. **Apply** the technique (`OPTIMIZE`, `CLUSTER BY` + `OPTIMIZE FULL`, set
   `TBLPROPERTIES`, enable optimized writes, etc.).
5. **Inspect the "after"** and compare.

### Measurement toolkit (use these to show the effect)

```sql
DESCRIBE DETAIL catalog.schema.table;   -- numFiles, sizeInBytes, clusteringColumns, partitionColumns
DESCRIBE HISTORY catalog.schema.table;  -- see OPTIMIZE / WRITE / CLUSTER operations + metrics
DESCRIBE EXTENDED catalog.schema.table; -- table properties, predictive optimization status
SHOW TBLPROPERTIES catalog.schema.table;
```

```python
# Programmatic before/after file count + size
detail = spark.sql(f"DESCRIBE DETAIL {catalog}.{schema}.t").select("numFiles","sizeInBytes").first()
print(detail["numFiles"], detail["sizeInBytes"])
```

Optionally time a query before/after to show the read-side win.

## Code quality

- Every non-trivial cell gets a short comment explaining *why*, not just *what*.
- Keep cells small and runnable top-to-bottom.
- Show both `%sql` and `%python`/DeltaTable API where both are common (e.g.
  `OPTIMIZE t` vs `DeltaTable.forName(spark,"t").optimize().executeCompaction()`).
- Include a **cleanup cell** at the end (drop demo tables/schema) so it's rerunnable.

## Current vs deprecated patterns

| Use this | Instead of |
| --- | --- |
| Liquid clustering (`CLUSTER BY`) | partitioning + `ZORDER` for new tables |
| Predictive optimization (auto OPTIMIZE/VACUUM/ANALYZE) | hand-scheduled maintenance jobs |
| Optimized writes + auto compaction | `repartition(n)`/`coalesce(n)` before write |
| `OPTIMIZE … FULL` to recluster after key change | rewriting the whole table |
| `delta.dataSkippingStatsColumns` | relying only on column order for stats |
| Unity Catalog `catalog.schema.table` + UC Volumes | `hive_metastore` two-level names / DBFS mounts |

Verify feature names, defaults, and DBR-version availability against the docs
(see `references/fact-sheet.md`) before asserting them — they drift.
