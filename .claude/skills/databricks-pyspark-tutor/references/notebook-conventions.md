# Databricks Notebook Conventions (PySpark Performance track)

PySpark performance is hands-on, so **default to one runnable notebook per topic**. Each
notebook should *demonstrate and measure* the technique — by reading the **query plan**
and the **Spark UI**, not just describing it.

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

- Magic commands as the first line of a cell: `# MAGIC %md` (narration), `# MAGIC %sql`
  (SQL). `%python` is implicit in `.py`.

## Required header cell (every notebook)

Begin with a markdown cell stating:

- **Title** and one-line goal.
- **Prerequisites**: cluster/runtime (e.g. "any DBR LTS; AQE on by default since DBR 7.3";
  note when a demo wants AQE *off* to show the before-state — `spark.conf.set("spark.sql.adaptive.enabled","false")`),
  Unity Catalog enabled, required grants, any source data/volume.
- **What you'll learn** (3–5 bullets).
- **How to read the result**: point the learner at the **Spark UI** (the SQL tab DAG,
  the Stages tab, task-time distribution, shuffle read/write, spill, GC time) and at
  `df.explain(mode="formatted")` — this track is about *seeing* the engine behave.

> For each feature demonstrated, add a brief markdown cell on its **uses, edge cases &
> limitations** (see SKILL.md).

## Namespacing & table format

- Unity Catalog **three-level namespacing**: `catalog.schema.table`.
- Parameterize catalog/schema at the top with widgets or variables:

```python
catalog = "main"
schema  = "pyspark_perf_demo"
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.{schema}")
spark.sql(f"USE {catalog}.{schema}")
```

- **Delta Lake** is the default format — do NOT write `USING DELTA` unless contrasting
  formats. Store files in **UC Volumes**, not DBFS mounts. For pure-DataFrame demos that
  don't need a table (joins, caching, memory), in-memory generated DataFrames are fine.

## The pattern that makes these lessons land: create → stress → apply → MEASURE

Every PySpark performance notebook should let the learner *see the engine react*:

1. **Create** demo DataFrames/tables (use `spark.range(...)` + `withColumn` to generate
   data at a chosen scale; control skew with `when`/`rand`).
2. **Stress** it to create the condition the technique addresses — a big-vs-big join, a
   skewed key, hundreds of tiny shuffle partitions, a memory-pressured aggregation, a
   repeated read.
3. **Inspect the "before"** with the measurement toolkit below (plan + UI + timing).
4. **Apply** the technique (`broadcast()`, a `spark.conf.set(...)`, `persist()`, salting,
   `bucketBy`, a hint, etc.).
5. **Inspect the "after"** and compare — the plan node changed, the Exchange disappeared,
   the spill went away, the wall-clock dropped, task times balanced.

### Measurement toolkit (use these to show the effect)

```python
# 1. The query plan — the primary evidence in this track
df.explain(mode="formatted")     # look for BroadcastHashJoin / SortMergeJoin / Exchange /
                                 # AQEShuffleRead / InMemoryTableScan / PartitionFilters / dynamicpruning

# 2. Partition counts (in-memory partitions)
print(df.rdd.getNumPartitions())

# 3. Wall-clock timing of an action (force materialization with a cheap action)
import time
t0 = time.time(); df.write.format("noop").mode("overwrite").save(); print(time.time() - t0, "s")
#   ^ the "noop" sink runs the full job without writing real output — clean way to time a plan
```

```sql
-- For tables: confirm bucketing / partitioning / stats
DESCRIBE EXTENDED catalog.schema.table;   -- partition cols, bucket spec, properties
```

**Then point at the Spark UI** (the heart of this track): the **SQL/DataFrame** tab shows
the DAG and per-node metrics (rows, shuffle bytes, "spill"); the **Stages** tab shows the
task-time distribution (min/median/max — skew shows as max ≫ median) and **GC Time**; the
**Storage** tab shows cached DataFrames and their storage level/size. Tell the learner
exactly which number to look at for *this* lesson.

## Code quality

- Every non-trivial cell gets a short comment explaining *why*, not just *what*.
- Keep cells small and runnable top-to-bottom.
- Show both the **DataFrame API** and the equivalent **Spark SQL** / `spark.conf.set(...)`
  where both are common (e.g. `broadcast(df)` vs `/*+ BROADCAST(t) */`; `df.persist(level)`
  vs `CACHE TABLE`).
- When a demo needs to show the "before", **temporarily disable the relevant feature**
  (e.g. `spark.conf.set("spark.sql.adaptive.enabled","false")` or
  `spark.conf.set("spark.sql.autoBroadcastJoinThreshold","-1")`) and **re-enable it after**
  — comment loudly that this is for demonstration only.
- Include a **cleanup cell** at the end (drop demo tables/schema, `unpersist()` cached
  DataFrames, reset any changed `spark.conf`) so the notebook is rerunnable and leaves no
  state behind.

## Current vs deprecated patterns

| Use this | Instead of |
| --- | --- |
| `broadcast(df)` / `/*+ BROADCAST(t) */` for big-vs-small joins | letting a huge shuffle-sort-merge join run unforced |
| AQE on (coalesce/skew/switch) | hand-guessing `spark.sql.shuffle.partitions` |
| AQE skew join → then salting for residual skew | bumping executor memory to survive a skewed task |
| `persist(MEMORY_AND_DISK)` + `unpersist()` on a **reused** DataFrame | caching a read-once DataFrame, or never unpersisting |
| Partition pruning / DPP / column pruning (read less) | scanning the whole table then filtering |
| `bucketBy(...).saveAsTable(...)` for repeated joins on a key | re-shuffling the same join every run |
| Serialized / off-heap cache + G1GC on big heaps | fighting full-GC pauses with a bigger heap |
| `df.write.format("noop")` to time/trigger a plan | `df.collect()` (pulls data to the driver — risks driver OOM) |
| DataFrame API | RDDs (no Catalyst/Tungsten/AQE/DPP) |

Verify config keys, defaults, hint names, storage levels, and DBR/Spark-version
availability against the docs (see `references/fact-sheet.md`) before asserting them — and
note OSS-Spark vs Databricks differences (AQE thresholds, `shuffle.partitions=auto`, Photon).
