# Delta Optimization — Verified Fact Sheet (Azure Databricks docs, June 2026)

All facts below were verified against learn.microsoft.com/azure/databricks docs
(pages updated 2026-06-11 to 2026-06-23). Use ONLY these facts; do not invent
APIs, flags, defaults, or version numbers. Cite the doc URLs in each lesson's
References section. Naming reflects the Lakeflow rebrand (DLT → Lakeflow Spark
Declarative Pipelines).

------------------------------------------------------------------------
## Canonical doc URLs (cite these)
- Liquid clustering:      https://learn.microsoft.com/en-us/azure/databricks/tables/clustering
- Data skipping & ZORDER: https://learn.microsoft.com/en-us/azure/databricks/tables/data-skipping
- OPTIMIZE (compaction):  https://learn.microsoft.com/en-us/azure/databricks/tables/operations/optimize
- Control file size:      https://learn.microsoft.com/en-us/azure/databricks/tables/tune-file-size
- When to partition:      https://learn.microsoft.com/en-us/azure/databricks/tables/partitions
- Predictive optimization:https://learn.microsoft.com/en-us/azure/databricks/optimizations/predictive-optimization
- OPTIMIZE SQL ref:        https://learn.microsoft.com/en-us/azure/databricks/sql/language-manual/delta-optimize
- Best practices (Delta):  https://learn.microsoft.com/en-us/azure/databricks/delta/best-practices

------------------------------------------------------------------------
## 1. TRADITIONAL WRITES / small-file problem (baseline; synthesized from tune-file-size + Spark)
- Default Spark write produces ~1 output file per writing task/partition. With the
  default shuffle parallelism (`spark.sql.shuffle.partitions`, historically 200;
  AQE can coalesce), a write can emit many small files = the "small file problem".
- Each file carries fixed overhead: file open, footer read, min/max stats, task
  scheduling. Thousands of tiny files = slow listing + slow scans + metadata bloat.
- Old manual controls: `df.coalesce(n)` (no shuffle, merges partitions) and
  `df.repartition(n)` (full shuffle, even sizes) before `.write`. Brittle: you must
  guess n. Databricks says DO NOT use coalesce/repartition before a write when
  optimized writes is enabled.
- Delta stores data as Parquet files + a transaction log (_delta_log). A "write"
  appends new Parquet files and commits a JSON log entry; no automatic sizing
  happens without optimized writes / auto compaction / OPTIMIZE.
- AQE (Adaptive Query Execution, on by default) coalesces post-shuffle partitions
  at runtime, partially mitigating tiny files but not a layout solution.
- `spark.sql.files.maxRecordsPerFile` caps rows per file (0/neg = no limit).

## 2. PARTITIONING (/tables/partitions, updated 2026-06-11)
- Databricks recommends LIQUID CLUSTERING for ALL new Delta + managed Iceberg tables.
- Do NOT partition tables smaller than 1 TB. Most tables <1 TB need no partitions.
- Minimum partition size: at least 1 GB per partition. Fewer, larger partitions
  outperform many small partitions.
- Syntax: `CREATE TABLE t (...) PARTITIONED BY (col)`. Partition cols must be
  TOP-LEVEL columns. Cannot partition by complex types (Struct/Map/Array/Variant)
  or struct fields (`struct_col.field`). Use liquid clustering for struct fields.
- Supported partition types: Date, Timestamp, TimestampNTZ, Interval, String,
  Binary, Boolean, Integer/Long/Short/Byte, Float/Double/Decimal.
- Over-partitioning on high-cardinality cols (timestamp, customer_id) creates a
  partition explosion → tiny files → slow. Partition only low/known-cardinality
  fields (date, region).
- Ingestion time clustering (DBR 11.3 LTS+): UNPARTITIONED tables are auto-clustered
  by ingestion time, giving date-partition-like benefits with no tuning.
- Convert partitioned → liquid: `ALTER TABLE ... REPLACE PARTITIONED BY WITH CLUSTER BY` (DBR 18.1+).
- Z-order + partitions: Z-order only within a partition (can't combine files across
  partition boundaries); cannot Z-order on partition columns.
- Hive-style partitioning is NOT part of the Delta protocol; don't rely on directory layout.

## 3. DATA SKIPPING & Z-ORDERING (/tables/data-skipping, updated 2026-06-18)
- Per-file statistics collected automatically on write: MIN, MAX, NULL counts,
  total record count. At query time the engine reads stats and skips files whose
  min/max range can't match the predicate.
- Stats columns: first 32 columns by default (UC EXTERNAL tables). UC MANAGED tables
  use predictive optimization for intelligent stats — NO 32-column limit; PO runs ANALYZE.
- `delta.dataSkippingNumIndexedCols` (all DBR) — number of leading columns to index
  (order-dependent). `delta.dataSkippingStatsColumns` (DBR 13.3 LTS+) — explicit
  column list; SUPERSEDES dataSkippingNumIndexedCols.
- Changing these props does NOT recompute existing stats; affects future writes.
- Recompute manually (DBR 14.3 LTS+): `ANALYZE TABLE t COMPUTE DELTA STATISTICS`.
- Long strings are truncated during stats collection — consider excluding long
  string cols from stats.
- Z-ORDER: `OPTIMIZE t [WHERE ...] ZORDER BY (colA, colB)` colocates related rows
  using a space-filling (Z-order) curve so data skipping works on those columns.
  Use for high-cardinality columns common in predicates. Multiple cols allowed but
  effectiveness drops per extra column. ZORDER cols MUST have stats collected.
  Z-order is NOT idempotent (re-running may rewrite). Cannot Z-order partition cols.
- Since DBR 13.3+, Databricks recommends LIQUID CLUSTERING instead of Z-order.
  ZORDER is NOT compatible with liquid clustering.

## 4. OPTIMIZE / COMPACTION (bin-packing) (/tables/operations/optimize, updated 2026-06-18)
- `OPTIMIZE table_name` — compacts many small files into fewer right-sized files
  (bin-packing). `OPTIMIZE t WHERE date >= '2022-11-18'` — only a partition subset.
- Python: `DeltaTable.forName(spark,"t").optimize().executeCompaction()`;
  `.where("date='2021-11-18'")`. Scala equivalent exists.
- Bin-packing is IDEMPOTENT (second run = no-op). Balances by file SIZE in storage
  (not tuple count). Snapshot isolation → readers/streams not interrupted; no data change.
- For LIQUID CLUSTERING tables, OPTIMIZE groups data by clustering keys (incremental).
  For PARTITIONED tables, compaction happens within each partition.
- `OPTIMIZE t ZORDER BY (col)` — combine compaction with Z-order (non-LC tables only).
- `OPTIMIZE table_name FULL` (DBR 16.0+) — force full reclustering for LC tables.
- Predictive optimization runs OPTIMIZE automatically on UC managed tables.
- Frequency: start daily, then tune for cost/perf. Compute-optimized instances + SSDs.
- Returns file stats (min/max/total, Z-order stats, #batches, partitions optimized).

## 5. OPTIMIZED WRITES (/tables/tune-file-size, updated 2026-06-18)
- Improves file size AS data is written (write-time) by SHUFFLING data before write
  so each partition gets fewer, larger files. Most effective for PARTITIONED tables.
- Target file size when enabled: 128 MB.
- Table property: `delta.autoOptimize.optimizeWrite` (true/false).
  Session: `spark.databricks.delta.optimizeWrite.enabled`.
- Enabled BY DEFAULT for: MERGE, UPDATE with subqueries, DELETE with subqueries.
  Also for CTAS + INSERT on SQL warehouses. DBR 13.3 LTS+: all UC-registered tables
  have optimized writes for CTAS + INSERT on PARTITIONED tables.
- Trade-off: extra shuffle = some added write latency, but far fewer small files.
- Do NOT run `coalesce(n)`/`repartition(n)` just before a write when using optimized writes.

## 6. AUTO COMPACTION (/tables/tune-file-size)
- Combines small files WITHIN partitions AFTER a write succeeds. Runs SYNCHRONOUSLY
  on the write cluster, post-commit. Only compacts files not previously compacted.
- Table property: `delta.autoOptimize.autoCompact`.
  Session: `spark.databricks.delta.autoCompact.enabled`.
- Values: `auto` (recommended; autotunes target size), `true` (128 MB target, no
  dynamic sizing), `legacy` (alias for true), `false` (off).
- `spark.databricks.delta.autoCompact.maxFileSize`, `...autoCompact.minNumFiles`
  (min small files in a partition/table to trigger).
- Auto compaction + optimized writes are ALWAYS ON for MERGE/UPDATE/DELETE (can't disable).
- Background auto compaction: for UC managed tables, doesn't require predictive
  optimization. To migrate legacy: remove `spark.databricks.delta.autoCompact.enabled`
  config and `ALTER TABLE t UNSET TBLPROPERTIES (delta.autoOptimize.autoCompact)`.
- Auto compaction (on write cluster) and predictive optimization (async, serverless)
  are INDEPENDENT — can be used separately or together.

## 7. AUTO OPTIMIZE (umbrella) + target file size / autotuning (/tables/tune-file-size)
- "Auto optimize" = the two settings together: `autoOptimize.optimizeWrite`
  (write-time) + `autoOptimize.autoCompact` (post-write). Legacy umbrella term.
- Auto compaction & optimized writes REDUCE but don't REPLACE OPTIMIZE. For tables
  > 1 TB, schedule OPTIMIZE to further consolidate. Prefer liquid clustering for skipping.
- `delta.targetFileSize` — explicit target (e.g. `'100mb'` or bytes `104857600`).
  Default: None. Honored by OPTIMIZE, liquid clustering, auto compaction, optimized writes.
  (On UC managed tables w/ SQL warehouse or DBR 11.3 LTS+, only OPTIMIZE respects targetFileSize.)
- AUTOTUNING by table size (when no explicit target):
    * < 2.56 TB  → 256 MB target
    * 2.56–10 TB → grows linearly 256 MB → 1 GB
    * > 10 TB    → 1 GB target
  Growing target does NOT re-optimize existing files; large tables may keep some
  small files unless you set a fixed `targetFileSize`.
- `delta.tuneFileSizesForRewrites` exists to bias toward rewrite-friendly sizes.
- UC managed tables: automatic file size tuning by default (DBR 11.3 LTS+ / SQL warehouse).

## 8. LIQUID CLUSTERING (/tables/clustering, updated 2026-06-23)  [lc.html already exists]
- GA for Delta Lake: **DBR 15.4 LTS and above** (NOT 15.2 — correct lc.html).
  Public Preview for managed Iceberg: DBR 16.4 LTS+. DataFrame/DeltaTable API: DBR 14.3 LTS+.
- REPLACES partitioning AND ZORDER. NOT compatible with either — use instead of, never alongside.
- Up to **4 clustering keys**. (For tables <10 TB, more keys can hurt single-column filters.)
- Redefine keys anytime WITHOUT rewriting existing data (the headline benefit).
- SQL:
    CREATE TABLE t (col0 INT, col1 STRING) CLUSTER BY (col0);
    CREATE TABLE t2 CLUSTER BY (col0) AS SELECT * FROM t1;     -- CLUSTER BY before AS
    ALTER TABLE t CLUSTER BY (c1, c2);     -- change keys (existing data not rewritten)
    ALTER TABLE t CLUSTER BY NONE;         -- stop clustering
    CREATE OR REPLACE TABLE t (...) CLUSTER BY AUTO;   -- automatic key selection
    ALTER TABLE t CLUSTER BY AUTO;
- Python (DBR 14.3 LTS+): DeltaTable.create()...clusterBy("col0").execute();
  df.write.clusterBy("col0").saveAsTable("t"); option("clusterByAuto","true").
- Trigger clustering: `OPTIMIZE t` (INCREMENTAL — only rewrites what's needed).
  `OPTIMIZE t FULL` (DBR 16.0/16.4 LTS+) reclusters ALL data (run after first enabling
  or changing keys; can take hours on big tables). `OPTIMIZE t FULL WHERE <pred>` (DBR 18.1+) partial.
- Convert partitioned → LC: `ALTER TABLE t REPLACE PARTITIONED BY WITH CLUSTER BY [(cols)|AUTO]` (DBR 18.1+).
- Keys must have STATS collected (first 32 cols by default). Supported types: Date,
  Timestamp, TimestampNTZ (14.3+), String, Integer/Long/Short/Byte, Float/Double/Decimal,
  and struct fields via dot notation `CLUSTER BY (struct_col.field)`. NOT complex types.
- AUTOMATIC liquid clustering (`CLUSTER BY AUTO`): DBR 15.4 LTS+, UC MANAGED tables only,
  REQUIRES predictive optimization; analyzes query history, cost-aware key changes.
- Clustering-on-write size thresholds (UC managed / other Delta):
    1 key 64MB/256MB · 2 keys 256MB/1GB · 3 keys 512MB/2GB · 4 keys 1GB/4GB.
  Because not all writes cluster, run OPTIMIZE frequently (every 1–2 h for high-churn tables).
- Ops that cluster on write: INSERT INTO, CTAS, RTAS, COPY INTO from Parquet, append.
- Uses Delta WRITER v7 / READER v3 (deletion vectors, row tracking, checkpoint V2 by default).
  Old Delta clients can't read; CANNOT downgrade protocol.
- Inspect: `DESCRIBE DETAIL t` (clusteringColumns), `SHOW TBLPROPERTIES t` (clusterByAuto=true).
- Works with streaming tables & materialized views. Create-with-LC via Structured Streaming: DBR 16.4 LTS+.

## 9. PREDICTIVE OPTIMIZATION (/optimizations/predictive-optimization, updated 2026-06-18)
- Automatically runs OPTIMIZE, VACUUM, and ANALYZE on UC MANAGED tables (Delta + Iceberg).
  Collects stats on write. Eliminates manual maintenance.
- Enabled BY DEFAULT for accounts created on/after Nov 11, 2024; gradual rollout to
  existing accounts (expected complete ~Aug 2026).
- Prereqs: workspace on PREMIUM plan, supported region, SQL warehouse or DBR 12.2 LTS+,
  UC MANAGED tables only.
- Enable/disable inheritance model: account (accounts console → Settings → Feature
  enablement) → catalog → schema → table (tables inherit).
    ALTER CATALOG [name] { ENABLE | DISABLE | INHERIT } PREDICTIVE OPTIMIZATION;
    ALTER { SCHEMA | DATABASE } name { ENABLE | DISABLE | INHERIT } PREDICTIVE OPTIMIZATION;
- Privileges: account admin (account), catalog owner (catalog), schema owner (schema).
- OPTIMIZE run by PO does NOT run ZORDER (it ignores Z-ordered files) — use liquid clustering.
  PO drives automatic liquid clustering key selection.
- VACUUM retention = `delta.deletedFileRetentionDuration` (default 7 days); raise BEFORE
  enabling PO if you need longer time travel:
    ALTER TABLE t SET TBLPROPERTIES ('delta.deletedFileRetentionDuration' = '30 days');
- Runs on SERVERLESS compute (serverless jobs SKU billing).
- Monitor: system table `system.storage.predictive_optimization_operations_history`.
- Verify: `DESCRIBE (CATALOG | SCHEMA | TABLE) EXTENDED name` → "Predictive Optimization" field.
- Does NOT run on: OpenSharing recipient tables, EXTERNAL tables.

## 10. DELETION VECTORS — merge-on-read (/tables/features/deletion-vectors, updated 2026-06-11)
- A storage optimization that accelerates table MODIFICATIONS. By default, deleting
  one row rewrites the ENTIRE Parquet file holding it (copy-on-write). With deletion
  vectors, `DELETE`/`UPDATE`/`MERGE` mark rows as modified (a "soft delete") WITHOUT
  rewriting the Parquet file; reads apply the deletion vector to resolve current
  state. This is **merge-on-read**.
- Enable: `delta.enableDeletionVectors = true` (Delta) / `iceberg.enableDeletionVectors`
  (Iceberg). `CREATE TABLE ... TBLPROPERTIES ('delta.enableDeletionVectors' = true);`
  or `ALTER TABLE t SET TBLPROPERTIES ('delta.enableDeletionVectors' = true);`.
  Can't ALTER-enable/remove on a materialized view or streaming table.
- All Apache Iceberg v3 tables include DVs by default; Delta tables must opt in.
  Auto-enable on new Delta tables is governed by a workspace setting (SQL warehouse
  or DBR 14.3 LTS+); default varies by region. Liquid clustering enables DVs by
  default (its v7/v3 protocol) — ties to Lesson 08.
- Versions: WRITE with all optimizations = DBR **14.3 LTS+**; READ = DBR **12.2 LTS+**.
  Row-level concurrency with DVs = DBR 14.2+. (Non-Photon write support: DELETE 12.2 LTS+,
  UPDATE 14.1+, MERGE 14.3 LTS+. Photon: all three from 12.2 LTS+.)
- Enabling DVs UPGRADES the table protocol → clients without DV support can't read.
  Drop the feature (DBR 14.1+): `ALTER TABLE t DROP FEATURE deletionVectors` to downgrade.
- Soft-deletes are physically applied (files rewritten) when: `OPTIMIZE` runs, auto
  compaction rewrites a file with a DV, or `REORG TABLE t APPLY (PURGE)` (rewrites all
  files with DV-recorded changes). To then physically remove old data (GDPR/storage),
  run `VACUUM` after the retention window. `spark.databricks.delta.reorg.purgeMode`:
  `all` (default, scans all footers) vs `rows` (only files with soft-deletes; faster on large tables).
- Photon uses DVs for **predictive I/O** to accelerate DELETE/UPDATE/MERGE.
- Trade-off: cheap writes (no full-file rewrite) in exchange for a small read-time
  cost (apply the DV). Limitations: UniForm Iceberg v2 unsupported (v3 OK); GENERATE
  manifest needs a REORG PURGE first; no incremental manifest generation with DVs;
  can't downgrade protocol after enabling on an MV/streaming table.

## 11. VACUUM (/tables/operations/vacuum, updated 2026-06-18)
- Removes data files NO LONGER referenced by the table AND older than the retention
  threshold. Two reasons to run it: cut cloud storage cost, and permanently purge
  modified/deleted records (compliance).
- Default retention = **7 days**, governed by `delta.deletedFileRetentionDuration`
  (default `interval 7 days`).
- Syntax: `VACUUM table_name` · `VACUUM table_name RETAIN 168 HOURS` ·
  `VACUUM table_name DRY RUN` (preview files to delete, deletes nothing).
- LITE vs FULL (LITE = **Public Preview, DBR 16.4 LTS+**): `VACUUM t LITE` uses the
  transaction log to find expired files (avoids listing every file; faster on big
  tables; won't delete files not referenced in the log, e.g. from aborted txns; needs
  a prior successful VACUUM within the 30-day log retention). `VACUUM t FULL` is the default.
- Safety check: RETAIN < 7 days is BLOCKED unless you set
  `spark.databricks.delta.retentionDurationCheck.enabled = false` — strongly
  discouraged (a too-short window can delete uncommitted files from long-running jobs).
- VACUUM ⇄ TIME TRAVEL: after VACUUM you LOSE the ability to query versions older than
  the retention window (their data files are gone). Log retention (default 30 days) is
  separate — but VACUUM removing data files is what actually caps time travel.
- Predictive optimization runs VACUUM automatically on UC managed tables.
- For deletion-vector / column-mapping soft-deletes: `REORG TABLE t APPLY (PURGE)`
  then VACUUM (after older files expire) to remove data physically.
- Ignores dirs starting with `_`/`.` (e.g. `_delta_log`, `_checkpoints`). Audit via
  `DESCRIBE HISTORY`. Cluster sizing: phase 1 lists files (workers, parallel), phase 2
  deletes from the DRIVER (single node) — size the driver up for large deletes.

## 12. TIME TRAVEL & TABLE HISTORY (/tables/history, updated 2026-06-12)
- Every table-modifying operation creates a new **version**. Inspect: `DESCRIBE HISTORY
  table_name` (reverse chronological; columns include version, timestamp, operation,
  operationMetrics, isolationLevel, isBlindAppend) and `DESCRIBE HISTORY t LIMIT 1`.
- Query a past version:
    SELECT * FROM t TIMESTAMP AS OF '2018-10-18T22:15:12.013Z';
    SELECT * FROM t VERSION AS OF 123;
    -- @ syntax: t@20190101000000000  (yyyyMMddHHmmssSSS)  or  t@v123
  Python: `spark.read.option("timestampAsOf","2019-01-01").table("t")` /
  `spark.read.option("versionAsOf", 123).table("t")`.
- Roll back: `RESTORE TABLE t TO VERSION AS OF <v>;` / `RESTORE TABLE t TO TIMESTAMP
  AS OF <ts>;` (needs MODIFY; data-changing — downstream streaming may reprocess; can't
  restore to a version whose files were vacuumed/deleted).
- TWO independent retention dials:
    * `delta.logRetentionDuration` — how long history (log) is kept; default `interval 30 days`.
    * `delta.deletedFileRetentionDuration` — VACUUM's data-file threshold; default `interval 7 days`.
  To time-travel N days back you must retain BOTH the log AND the data files → raise both
  (e.g. both to 30 days). DBR 18.0+: logRetentionDuration must be ≥ deletedFileRetentionDuration;
  time-travel requests older than deletedFileRetentionDuration are blocked.
- Databricks does NOT recommend time travel as long-term backup — use only the past 7
  days unless you raised both retentions. `spark.databricks.delta.lastCommitVersionInSession`
  returns the last commit version in the session.
- Uses: re-create analyses/reports, audit, fix accidental deletes/updates
  (`INSERT`/`MERGE` from a past version), snapshot isolation for fast-changing tables.

------------------------------------------------------------------------
## Cross-cutting current best practices
- Delta Lake is the default table format (don't write `USING DELTA`).
- Unity Catalog 3-level names `catalog.schema.table`; store files in UC Volumes.
- For NEW tables: prefer UC MANAGED tables + liquid clustering + predictive optimization;
  let the platform manage layout. Reach for partitioning/ZORDER/manual OPTIMIZE only
  for legacy/external tables or special cases.
- Decision ladder to teach: traditional write (problem) → partitioning (old layout) →
  data skipping (why layout matters) → OPTIMIZE (manual fix) → optimized writes +
  auto compaction (auto file sizing) → auto optimize (umbrella) → liquid clustering
  (modern layout) → predictive optimization (fully managed).
