# DBX Delta Optimization — Curriculum (11-lesson track)

The track teaches the Delta data-layout & maintenance lifecycle as one story:
**a write creates files → layout decides what queries can skip → maintenance keeps
files right-sized → modifications stay cheap → you manage the file history they leave
behind → the platform can do all of it for you.** Teach in this order; each lesson
links forward/back to its neighbors. The track has two halves: **Part A — layout &
file sizing** (01–08) and **Part B — modifications, lifecycle & automation** (09–11).

| # | Folder | Topic | One-line hook | Key doc-grounded facts to nail |
| --- | --- | --- | --- | --- |
| 01 | `01-traditional-writes` | Traditional writes & the small-file problem | Why naive writes make thousands of tiny files and slow reads | per-task file output, file overhead, `coalesce`/`repartition`, AQE, the `_delta_log` |
| 02 | `02-partitioning` | Partitioning (and when NOT to) | The classic layout tool — powerful, rigid, easy to misuse | don't partition < 1 TB; ≥1 GB/partition; over-partitioning; ingestion-time clustering; top-level cols only |
| 03 | `03-data-skipping-and-zorder` | Data skipping & Z-ordering | How min/max stats let queries skip files — and how Z-order helps | per-file min/max/null/count; first 32 cols; `dataSkippingStatsColumns`; `ANALYZE … COMPUTE DELTA STATISTICS`; `ZORDER BY` |
| 04 | `04-optimize-compaction` | OPTIMIZE / compaction (bin-packing) | The manual fix: merge small files into right-sized ones | `OPTIMIZE [WHERE]`, idempotent, target size, `OPTIMIZE FULL` (16.0+), ZORDER integration, daily cadence |
| 05 | `05-optimized-writes` | Optimized writes | Get file sizes right *as you write* (shuffle before write) | `delta.autoOptimize.optimizeWrite`, 128 MB target, on by default for MERGE/UPDATE/DELETE & SQL-warehouse CTAS/INSERT |
| 06 | `06-auto-compaction` | Auto compaction | Compact small files automatically *after* each write | `delta.autoOptimize.autoCompact`, synchronous on write cluster, `auto`/`true`/`false`, background auto compaction |
| 07 | `07-auto-optimize` | Auto optimize (umbrella) & file-size autotuning | The two auto features together + how Databricks picks file size | optimizeWrite + autoCompact; `delta.targetFileSize`; autotune 256 MB→1 GB by table size; not a replacement for OPTIMIZE |
| 08 | `08-liquid-clustering` | Liquid clustering | The modern replacement for partitioning + Z-order; change keys, no rewrite | `CLUSTER BY`/`CLUSTER BY AUTO`, GA DBR 15.4 LTS+, ≤4 keys, `OPTIMIZE`/`OPTIMIZE FULL`, protocol v7/v3, convert from partitioned (18.1+) |
| 09 | `09-deletion-vectors` | Deletion vectors (merge-on-read) | Edit data without rewriting whole Parquet files | `delta.enableDeletionVectors`, soft-deletes, write DBR 14.3 LTS+/read 12.2 LTS+, `REORG … APPLY (PURGE)`, LC enables DVs by default, protocol upgrade |
| 10 | `10-vacuum-time-travel` | VACUUM, time travel & retention | Manage the file history every operation leaves behind | `DESCRIBE HISTORY`, `VERSION/TIMESTAMP AS OF`, `RESTORE`, `VACUUM` (7-day default), the two dials `deletedFileRetentionDuration` (7d) + `logRetentionDuration` (30d) |
| 11 | `11-predictive-optimization` | Predictive optimization | Let Databricks run OPTIMIZE/VACUUM/ANALYZE for you | UC managed only, on by default (accounts ≥ Nov 11 2024), `ALTER CATALOG/SCHEMA … ENABLE PREDICTIVE OPTIMIZATION`, serverless billing, system table |

## Per-lesson artifact set (DBX Delta Optimization library style)

Each `DBX_Delta_Optimization/lessons/<NN-topic>/` folder contains:

- `lesson.md` — the written lesson (created first), with mermaid diagram, deep dive
  per sub-topic, commented SQL/PySpark snippets, comparison table, uses/edge-cases/
  limitations block, gotchas, references.
- `index.html` — self-contained interactive page in the `lc.html` house style
  (≥1 interactive diagram; see `references/html-template.md`).
- `<NN-topic>-demo.py` — runnable Databricks notebook that creates → stresses →
  applies → **measures** (see `references/notebook-conventions.md`).

Plus a track landing page at `DBX_Delta_Optimization/index.html` linking all
lessons, and an optional `learning plan/` (md + html) summarizing the path.

## The decision framework every learner should leave with

> **New table?** Use a Unity Catalog **managed** table with **liquid clustering**
> on your top filter/join columns, and enable **predictive optimization** — done.
> Reach for partitioning, Z-order, manual OPTIMIZE, or explicit `targetFileSize`
> only for **legacy/external** tables or special very-large-table cases.

Teach *why* each older tool existed and what replaced it, so the learner can both
maintain legacy tables and design modern ones.
