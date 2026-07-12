# Databricks Notebook Conventions

Use these conventions when generating runnable hands-on notebooks. They match
the patterns used across the DBX DE library (Autoloader, COPY INTO, bronze/
silver/gold, DLT, governance, Delta optimization, UC functions).

> **Notebook is the last artifact and is conditional.** Create markdown first,
> then HTML, then a notebook only if it genuinely adds value. For a module that
> spans multiple related topics, create **1–2 notebooks covering all topics**
> (e.g. one Python notebook + an optional SQL companion, or basics + advanced) —
> not one notebook per topic. If no notebook is warranted, the markdown lesson
> describes the **step-by-step Databricks UI actions** instead.

## File format

- Prefer a Databricks **source notebook**. Two acceptable forms:
  - `.py` with the Databricks source header (recommended for git-friendly demos).
  - `.ipynb` Jupyter notebook (use the NotebookEdit tool to author cells).
- For `.py` source notebooks, start the file with:

```python
# Databricks notebook source
```

- Separate cells with:

```python
# COMMAND ----------
```

- Use magic commands as the first line of a cell:
  - `# MAGIC %md` for markdown narration cells.
  - `# MAGIC %sql` for Spark SQL cells.
  - `# MAGIC %python` is implicit in `.py`; use explicitly only when mixing.

## Required header cell (every notebook)

Begin with a markdown cell stating:

- **Title** and one-line goal.
- **Prerequisites**: cluster type (e.g. serverless or a specific DBR LTS
  version), Unity Catalog enabled, required permissions/grants, any source data
  or volume needed.
- **What you'll learn** (3–5 bullets).

> For each feature demonstrated, add a brief markdown cell on its **uses, edge
> cases & limitations** (when to use / when not, tricky scenarios, honest
> constraints) — see SKILL.md "Required: uses, edge cases & limitations".

Example:

```python
# Databricks notebook source
# MAGIC %md
# MAGIC # Auto Loader — Incremental Ingestion
# MAGIC **Goal:** Incrementally ingest files from a UC volume into a Delta bronze table.
# MAGIC
# MAGIC **Prerequisites**
# MAGIC - DBR 14.3 LTS+ or Serverless, Unity Catalog enabled
# MAGIC - `USE CATALOG` / `CREATE TABLE` grants on the target schema
# MAGIC - A UC Volume with sample files
# MAGIC
# MAGIC **You'll learn:** cloudFiles source, schema inference & evolution, checkpointing.
```

## Namespacing & table format

- Use Unity Catalog **three-level namespacing** by default: `catalog.schema.table`.
- Parameterize catalog/schema at the top with widgets or variables so the
  notebook is portable:

```python
catalog = "main"
schema  = "de_demo"
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.{schema}")
spark.sql(f"USE {catalog}.{schema}")
```

- **Delta Lake** is the default table format — do not specify `USING DELTA`
  unless contrasting formats (it is the default in Databricks).
- Store files in **UC Volumes** (`/Volumes/<catalog>/<schema>/<volume>/...`),
  not legacy DBFS mounts.

## Code quality

- Every non-trivial cell gets a short comment explaining *why*, not just *what*.
- Keep cells small and runnable top-to-bottom.
- Prefer DataFrame API + Spark SQL; show both `%python` and `%sql` where it aids
  understanding.
- Include a **cleanup cell** at the end (drop demo tables/schema) so the notebook
  is rerunnable.

## Current vs deprecated patterns

| Use this | Instead of |
| --- | --- |
| Auto Loader (`cloudFiles`) / COPY INTO | manual file listing loops |
| Lakeflow Declarative Pipelines (DLT) | hand-rolled job DAGs for ETL |
| Lakeflow Jobs | legacy "Workflows"-only phrasing |
| Unity Catalog `catalog.schema.table` | `hive_metastore` two-level names |
| UC Volumes | DBFS mounts |
| Delta Lake | Parquet/CSV as the table of record |

Verify feature names and availability against the docs before asserting them
(names change — e.g. DLT → Lakeflow Declarative Pipelines).
