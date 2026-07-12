# Verification Checklist (run before asserting version-sensitive facts)

The cardinal rule: **do not hallucinate.** Never invent configs, parameters, hint names,
storage levels, API signatures, UI paths, or features. When unsure, say so and verify.

## Verify when the claim involves any of these

- **Config defaults & thresholds** — `spark.sql.autoBroadcastJoinThreshold` (10 MB),
  `spark.sql.shuffle.partitions` (200), `spark.memory.fraction` (0.6) /
  `spark.memory.storageFraction` (0.5), reserved 300 MiB, AQE advisory partition size
  (64 MB), skew factor (5) / threshold (256 MB), `spark.driver.maxResultSize` (1g),
  memory overhead factor (0.10; 0.40 for non-JVM Kubernetes), driver/executor minimum
  memory overhead floor (384 MB), `coalesceBucketsInJoin` (false).
- **A config's "Since" vs when its default flipped** — e.g. AQE was introduced in 1.6.0
  but `spark.sql.adaptive.enabled` only defaulted to `true` in **Spark 3.2.0** (SPARK-33679).
  Don't conflate the two.
- **OSS Spark vs Databricks differences** — AQE 10 MB static (OSS) vs 30 MB runtime switch
  (`spark.databricks.adaptive.autoBroadcastJoinThreshold`, Databricks); `shuffle.partitions=200`
  (OSS) vs `auto` (Databricks); OSS lists 3 AQE features, Databricks docs list 4 (adds
  empty-relation propagation); G1GC default-since-Spark-4.0 (JDK 17); Photon ≠ AQE.
- **Storage levels** — the exact `StorageLevel` names; the RDD default (`MEMORY_ONLY`) vs
  DataFrame default (`MEMORY_AND_DISK`); the PySpark "always serialized / `_SER` not
  separately exposed / `DISK_ONLY_3` exists" nuance.
- **Hint names & syntax** — `BROADCAST`/`MERGE`/`SHUFFLE_HASH`/`SHUFFLE_REPLICATE_NL`,
  `COALESCE`/`REPARTITION`/`REPARTITION_BY_RANGE`/`REBALANCE`.
- **API signatures** — `broadcast()`, `df.persist(StorageLevel.…)`, `bucketBy(...).sortBy(...).saveAsTable(...)`,
  `sc.broadcast(...)`/`.value`, `sc.accumulator(...)`/`longAccumulator(...)` — and DBR-version availability.
- **UI navigation / metric names** — the Spark UI tabs (SQL, Stages, Storage, Executors),
  "GC Time", "spill (memory)/(disk)", task-time percentiles — paths/labels drift across versions.
- Anything you "remember" but cannot pin to a current doc page.

## How to verify

1. **`spark-optimization` skill** — the primary grounding skill for this track's engine
   mechanics (shuffle, joins, AQE, memory, skew).
2. **Official Apache Spark docs** (the engine source of truth) — WebFetch the specific page:
   - `sql-performance-tuning.html` (AQE, join strategies/hints, coalesce/skew configs)
   - `tuning.html` (memory management overview, GC tuning)
   - `configuration.html` (every config key + default + "Since")
   - `rdd-programming-guide.html` (persist/storage levels, broadcast vars, accumulators)
   - `sql-ref-syntax-qry-select-hints.html` (hint syntax + aliases)
   - `cluster-overview.html` / `running-on-yarn.html` (deploy modes, edge node)
3. **Azure Databricks docs** for Databricks-specific behavior (this track's user works in
   Azure Databricks): `learn.microsoft.com/azure/databricks` — AQE page, compute/driver
   node, Photon. Cross-check AWS docs (`docs.databricks.com/aws/en`) if needed.
4. **`databricks-docs` skill / llms.txt index**, then WebFetch the specific page.
5. **`spark-api-beta` MCP server** — PySpark/Spark API signatures, Spark Connect/Serverless
   support, Spark/DBR-version availability (`spark_search_apis`, `spark_get_api_info`,
   `spark_get_version_changes`).
6. **`references/fact-sheet.md`** — cached, doc-grounded values for all 11 topics (verified
   June 2026). Prefer it for defaults/versions; re-verify if a claim is newer or borderline.
7. **Cite** the specific doc page URL in the lesson's References section.

## Canonical doc pages for this track

- SQL performance tuning (AQE/joins/hints): `spark.apache.org/docs/latest/sql-performance-tuning.html`
- Tuning (memory, GC): `spark.apache.org/docs/latest/tuning.html`
- Configuration: `spark.apache.org/docs/latest/configuration.html`
- RDD programming guide (persist, shared vars): `spark.apache.org/docs/latest/rdd-programming-guide.html`
- SQL hints: `spark.apache.org/docs/latest/sql-ref-syntax-qry-select-hints.html`
- Cluster overview / YARN (deploy modes): `spark.apache.org/docs/latest/cluster-overview.html`, `.../running-on-yarn.html`
- Azure Databricks AQE: `learn.microsoft.com/en-us/azure/databricks/optimizations/aqe`
- Azure Databricks compute (driver node): `learn.microsoft.com/en-us/azure/databricks/compute/configure`

## Known drift / gotchas to watch for (verify, don't assume)

| Current / correct | Older, wrong, or commonly-confused |
| --- | --- |
| AQE default `true` since **Spark 3.2.0** | "AQE since 1.6" (that's when it was introduced, not default-on) |
| RDD `cache()` = `MEMORY_ONLY`; DataFrame `cache()` = `MEMORY_AND_DISK` | "cache is always MEMORY_ONLY" (true only for RDDs) |
| PySpark always serializes; `_SER` levels not separately exposed; `DISK_ONLY_3` exists | assuming the Scala storage-level list maps 1:1 to PySpark |
| `coalesceBucketsInJoin.enabled` = **false** by default (since 3.1.0) | assuming it's true |
| Databricks runtime broadcast switch = **30 MB** (`spark.databricks.adaptive.autoBroadcastJoinThreshold`) | conflating with the OSS 10 MB static `spark.sql.autoBroadcastJoinThreshold` |
| G1GC is **default since Spark 4.0 (JDK 17)**; opt-in before | "G1GC is always Spark's default" |
| Broadcast **variable** (`sc.broadcast`) ≠ broadcast **join** (strategy) | treating them as the same thing |
| Accumulators are exactly-once **only inside actions** | trusting accumulator counts updated inside lazy transformations |
| Classic `spark.sql.sources.bucketing.enabled` ≠ DSv2 `spark.sql.sources.v2.bucketing.enabled` | conflating file-source bucketing with storage-partition-join |
| "partition" = on-disk Hive partitions **or** in-memory Spark partitions | using "partition" ambiguously in the pruning lessons |

## Items the docs don't state verbatim (present as practice, not a doc quote)

- Driver OOM from **broadcast build** or **too-many-partitions metadata** — operationally
  true; only `collect()`/large-result OOM is doc-quoted (via `maxResultSize`).
- The exact Spark-UI label strings **"spill (memory)" / "spill (disk)"** and per-task
  **"GC Time"** — real UI fields, but not quotable from the config/tuning pages; the
  underlying spill/GC mechanisms ARE doc-grounded.

## If you cannot verify

State plainly: "I can't confirm this is current — here's what I believe, and here's how to
check it in the docs." Do not present unverified specifics as fact.
