# PySpark Performance — Verified Fact Sheet (Apache Spark + Azure Databricks docs, June 2026)

> **Primary-track fact sheet** (execution engine & tuning). For Spark 4.0/4.1 *feature*
> facts (Spark Connect, ANSI-by-default, VARIANT, collations, SQL scripting, Python Data
> Source API, Arrow UDFs/UDTFs, `transformWithState`) see the companion
> `fact-sheet-spark4x.md`.

All facts below were verified against the official **Apache Spark** docs
(`spark.apache.org/docs/latest`) and **Azure Databricks** docs
(`learn.microsoft.com/azure/databricks`). Use ONLY these facts; do not invent configs,
flags, defaults, hint names, storage levels, or version numbers. Cite the doc URLs in
each lesson's References section. **Always state whether a value is OSS-Spark or
Databricks**, and distinguish a config's "Since" (when introduced) from when its
**default flipped** (e.g. AQE introduced 1.6, default-true 3.2).

> Apache Spark "latest" docs at verification were the 4.x line; defaults below are
> stable across Spark 3.2+→4.x unless flagged. Re-verify version-gated items live.

------------------------------------------------------------------------
## Canonical doc URLs (cite these)
- SQL performance tuning (AQE, joins, hints): https://spark.apache.org/docs/latest/sql-performance-tuning.html
- Tuning guide (memory, GC): https://spark.apache.org/docs/latest/tuning.html
- Configuration (all config keys): https://spark.apache.org/docs/latest/configuration.html
- RDD programming guide (persist, shared vars): https://spark.apache.org/docs/latest/rdd-programming-guide.html
- SQL join/partitioning hints: https://spark.apache.org/docs/latest/sql-ref-syntax-qry-select-hints.html
- Cluster overview / deploy modes: https://spark.apache.org/docs/latest/cluster-overview.html
- Running on YARN (client vs cluster): https://spark.apache.org/docs/latest/running-on-yarn.html
- Azure Databricks AQE: https://learn.microsoft.com/en-us/azure/databricks/optimizations/aqe
- Azure Databricks compute/driver node: https://learn.microsoft.com/en-us/azure/databricks/compute/configure
- Azure Databricks Photon: https://learn.microsoft.com/en-us/azure/databricks/compute/photon

------------------------------------------------------------------------
## 1. ARCHITECTURE & EXECUTION MODEL (cluster-overview, running-on-yarn, DBX compute)
- A Spark application = **1 driver** (runs `main()`/the notebook, holds the `SparkSession`/
  `SparkContext`, builds the plan, schedules tasks) + **N executors** (JVM processes on
  worker nodes that run tasks and hold cached data), coordinated by a **cluster manager**
  (Standalone, YARN, Kubernetes; on Databricks the platform manages it).
- **Edge node / gateway node**: a node that can submit to the cluster but isn't part of
  the worker pool. In **client mode** the driver runs there (or on your laptop / the
  notebook's driver node); in **cluster mode** the driver runs inside the cluster.
  - YARN client mode: "the driver runs in the client process, and the application master
    is only used for requesting resources from YARN."
  - YARN cluster mode: "the Spark driver runs inside an application master process which
    is managed by YARN on the cluster, and the client can go away after initiating."
  - **Databricks notebooks**: the driver runs on the cluster's **driver node** — it
    "maintains the SparkContext, interprets all the commands you run from a notebook…,
    and runs the Apache Spark master that coordinates with the Spark executors." On a
    single-node cluster the driver node is both master and worker.
- **Execution hierarchy**: an **action** triggers a **job**; the job is split at shuffle
  boundaries into **stages**; each stage runs as **tasks** (one task per partition).
- **Lazy evaluation**: transformations (`select`, `filter`, `join`, `groupBy`) only build
  a logical plan; nothing runs until an **action** (`count`, `collect`, `write`, `show`).
- **Narrow dependency** (each input partition → one output partition: `map`, `filter`,
  `union`) runs in a stage with no data movement. **Wide dependency** (`groupBy`, `join`,
  `distinct`, `repartition`) requires a **shuffle**.
- **The shuffle** = redistributing data across the network so rows sharing a key land in
  the same partition/executor. It writes intermediate "shuffle files" to local disk and
  reads them over the network — the most expensive operation (network + disk + serialize
  + a stage boundary). `spark.sql.shuffle.partitions` controls the post-shuffle partition
  count. Minimizing/eliminating shuffles is the core performance goal of this track.

## 2. JOINS (sql-performance-tuning, sql-ref-syntax-qry-select-hints)
- **`spark.sql.autoBroadcastJoinThreshold` = 10485760 (10 MB)** (since 1.1.0). If one
  side's estimated size is below this (and there's an equi-key), Spark uses a Broadcast
  Hash Join. Set to **-1** to disable auto-broadcast.
- **`spark.sql.join.preferSortMergeJoin` = true** (internal SQL conf; default `true`).
  When true, Spark prefers Sort-Merge over Shuffle-Hash for big-vs-big equi-joins.
- **Three strategies** + selection logic:
  - **Broadcast Hash Join (BHJ)** — small side is collected to the driver, broadcast to
    every executor, hash-joined against the big side with **no shuffle of the big side**.
    Chosen when a side is below the threshold (or a `BROADCAST` hint). Fastest when it fits.
  - **Shuffle Sort-Merge Join (SMJ)** — both sides shuffled by key, sorted, merged. The
    **default for large-vs-large** equi-joins (because `preferSortMergeJoin=true`).
  - **Shuffle Hash Join (SHJ)** — both sides shuffled; one side built into a per-partition
    hash table. Used only when neither side is broadcastable **and** `preferSortMergeJoin=false`
    (or a `SHUFFLE_HASH` hint), and one side fits in memory per partition.
- **Force a broadcast in code**: `from pyspark.sql.functions import broadcast` then
  `big.join(broadcast(small), "key")`; SQL hint `SELECT /*+ BROADCAST(small) */ …`.
- **Join hints & priority**: `BROADCAST` (aliases `BROADCASTJOIN`, `MAPJOIN`) > `MERGE`
  (aliases `SHUFFLE_MERGE`, `MERGEJOIN`) > `SHUFFLE_HASH` > `SHUFFLE_REPLICATE_NL`.
- **Read it in the plan/UI**: `df.explain()` shows `BroadcastHashJoin` / `SortMergeJoin` /
  `ShuffleHashJoin`; a `BroadcastExchange` (no big-side `Exchange`) = broadcast worked;
  two `Exchange` nodes + `Sort` + `SortMergeJoin` = a shuffle join. The Spark UI **SQL**
  tab shows the same as a DAG.
- **`spark.sql.shuffle.partitions` = 200** (since 1.1.0). On Azure Databricks can be set
  to `auto` for auto-optimized shuffle.

## 3. DRIVER MEMORY & DRIVER OOM (configuration, cluster-overview)
- **`spark.driver.memory` = 1g** (default). Heap of the driver JVM.
- **`spark.driver.maxResultSize` = 1g** (default). "Limit of total size of serialized
  results of all partitions for each Spark action (e.g. collect). Jobs will be aborted if
  the total size is above this limit. Having a high limit may cause **out-of-memory errors
  in driver**." This is the doc-grounded driver-OOM cause.
- **`spark.driver.memoryOverhead`** = `driverMemory * spark.driver.memoryOverheadFactor`
  (factor **0.10**; 0.40 for Kubernetes non-JVM) with a minimum (`spark.driver.minMemoryOverhead`
  = **384m**, a settable key since Spark 4.0.0; the 384 MB minimum predates it as a
  hardcoded value). Cluster mode only; this is the driver's **side bucket** outside the JVM
  heap — off-heap/native memory, Arrow, and the PySpark driver process.
- **What lives on the driver** (so what causes driver OOM): results of `collect()`/`take`
  of too many rows; **building the small side of a broadcast** join before shipping it;
  the query plan and partition **metadata** of jobs with a huge number of partitions/files;
  large local Python objects. *(The broadcast-build and partition-metadata OOM paths are
  operationally well-known but only `collect()`/large-result OOM is verbatim in the docs —
  present the others as established practice, not a doc quote.)*
- **Fixes**: don't `collect()` large data (write it, or `take(n)`/`limit`); raise
  `spark.driver.memory`/`maxResultSize` deliberately; avoid broadcasting too-large tables;
  reduce partition explosion.

## 4. EXECUTOR MEMORY — UNIFIED MODEL, SPILL, OOM (tuning, configuration)
- **JVM executor heap layout** (UnifiedMemoryManager):
  - **Reserved memory = 300 MiB** (fixed, carved off first).
  - **Unified region `M`** = `spark.memory.fraction` × (heap − 300 MiB). **`spark.memory.fraction`
    = 0.6.** Holds **Execution** (shuffle/sort/aggregation/join buffers) + **Storage**
    (cached blocks + broadcast).
  - **Storage sub-region `R`** = `spark.memory.storageFraction` × M. **`spark.memory.storageFraction`
    = 0.5.** Cached blocks inside `R` are **immune to eviction** by execution.
  - **User memory** = the remaining ~40% outside `M` — user data structures, Spark internal
    metadata, and an OOM safeguard for sparse/large records.
- **Borrow & evict rules**: "When no execution memory is used, storage can acquire all the
  available memory and vice versa." **Execution may evict Storage** down to `R`; **Storage
  may NOT evict Execution** (asymmetry — execution memory always wins).
- **`spark.executor.memory` = 1g** (default).
- **Overhead**: `spark.executor.memoryOverhead` = `executorMemory * spark.executor.memoryOverheadFactor`
  (factor **0.10**; 0.40 for Kubernetes non-JVM), minimum `spark.executor.minMemoryOverhead`
  = **384m** (settable key since 4.0.0). Overhead is the executor's **side bucket**:
  off-heap memory, shuffle/network buffers, and — when `spark.executor.pyspark.memory` is
  unset — the **Python workers**.
- **Off-heap**: `spark.memory.offHeap.enabled` = **false**, `spark.memory.offHeap.size` =
  **0** (must be positive when enabled). Off-heap memory is outside the JVM heap (no GC
  pressure) — "shrink your JVM heap size accordingly."
- **PySpark / Python-worker memory**: `spark.executor.pyspark.memory` = **Not set** by
  default. Python worker processes (for Python UDFs, `mapInPandas`, Pandas UDFs, RDD `map`
  with Python) run **outside the JVM heap**; when unset, Spark does not limit them and they
  count against the container's overhead/limit — a common hidden OOM cause for Python-heavy
  jobs. On YARN/K8s the limit is added to executor resource requests.
- **Spill**: when **Execution** memory is exhausted during a shuffle/sort/aggregation/join,
  Spark **spills** the in-memory data structures to **local disk** ("When data does not fit
  in memory Spark will spill these tables to disk, incurring the additional overhead of disk
  I/O and increased garbage collection"). The Spark UI shows **spill (memory)** and **spill
  (disk)** per task/stage. *(The spill mechanism is doc-grounded; those exact UI label
  strings are real but not quotable from the config/tuning pages.)* Spill = the job still
  finishes but slowly; it is the warning sign before an OOM.
- **Executor OOM** happens when even spilling can't keep a partition within the container
  limit (a single huge/skewed partition, too many cached blocks pinned in `R`, oversized
  Python workers, or too-small `executor.memory`/overhead). Fixes: more/smaller partitions,
  fix skew, cache less / serialized / off-heap, raise overhead for Python jobs.

## 5. ADAPTIVE QUERY EXECUTION — AQE (sql-performance-tuning, DBX aqe)
- **`spark.sql.adaptive.enabled` = true.** Introduced 1.6.0; **default flipped to `true` in
  Spark 3.2.0** (SPARK-33679 — "Enable adaptive query execution by default"). Do NOT
  conflate the "Since 1.6.0" in the config table with the default-true flip.
- AQE re-optimizes the physical plan **at runtime using actual shuffle statistics**, at
  each stage boundary. Three OSS features:
  1. **Coalescing post-shuffle partitions** — `spark.sql.adaptive.coalescePartitions.enabled`
     = **true**; targets `spark.sql.adaptive.advisoryPartitionSizeInBytes` = **64 MB**;
     won't shrink below `spark.sql.adaptive.coalescePartitions.minPartitionSize` = **1 MB**
     (since 3.2). Fixes "too many tiny shuffle partitions" without hand-setting
     `shuffle.partitions`.
  2. **Converting sort-merge join → broadcast hash join** at runtime once a side is found
     small enough (uses a runtime broadcast threshold).
  3. **Optimizing skew joins** — `spark.sql.adaptive.skewJoin.enabled` = **true**; a
     partition is skewed if its size > `skewedPartitionFactor` (**5.0**) × median **and** >
     `skewedPartitionThresholdInBytes` (**256 MB**); AQE **splits** the skewed partition
     into smaller sub-partitions so tasks balance.
- `spark.sql.adaptive.localShuffleReader.enabled` = **true** (since 3.0.0).
- **Azure Databricks**: AQE is **on by default (DBR 7.3 LTS+)**; Databricks also exposes
  `spark.databricks.optimizer.adaptive.enabled` = true and a higher runtime broadcast switch
  `spark.databricks.adaptive.autoBroadcastJoinThreshold` = **30 MB** (vs OSS 10 MB static).
  Databricks docs list a **4th** AQE feature: **dynamically detect & propagate empty
  relations**. Photon is the native **execution** engine; AQE works at the **planning**
  layer — they're complementary; keep AQE on with Photon.

## 6. CACHE & PERSIST (rdd-programming-guide, DataFrame API)
- `df.cache()` = shorthand for `df.persist()` with the **default** storage level.
- **Defaults differ — the most-confused fact**: RDD `cache()` default = **`MEMORY_ONLY`**
  (deserialized); DataFrame/Dataset `cache()`/`persist()` default = **`MEMORY_AND_DISK`**
  (PySpark enum name `MEMORY_AND_DISK_DESER` in Spark 3.0+). Always flag this.
- **StorageLevel options** (Scala/Java full set): `MEMORY_ONLY`, `MEMORY_ONLY_2`,
  `MEMORY_AND_DISK`, `MEMORY_AND_DISK_2`, `DISK_ONLY`, `DISK_ONLY_2`, `MEMORY_ONLY_SER`,
  `MEMORY_AND_DISK_SER`, `OFF_HEAP` (experimental — like `MEMORY_ONLY_SER` but in off-heap
  memory). Suffix `_2` = replicate to two nodes for fault tolerance.
- **PySpark nuance**: "In Python, stored objects will always be serialized with the Pickle
  library, so it does not matter whether you choose a serialized level." Python-exposed
  levels: `MEMORY_ONLY`, `MEMORY_ONLY_2`, `MEMORY_AND_DISK`, `MEMORY_AND_DISK_2`,
  `DISK_ONLY`, `DISK_ONLY_2`, `DISK_ONLY_3`. (`_SER` levels are not separately exposed in
  PySpark; `DISK_ONLY_3` exists in Python.)
- **Lazy**: `persist()`/`cache()` only set the storage level — nothing is stored until the
  **first action** materializes it. The first action is therefore slower (it computes +
  stores); later actions reuse.
- **`unpersist()`**: eager; removes the cached blocks. PySpark `unpersist(blocking=False)`.
  Always unpersist when done — cached blocks pin Storage memory in `R` and pressure GC.
- **When to cache**: a DataFrame **reused across ≥2 actions** (iterative ML, repeated
  exploratory queries, a branch reused by several writes). **When NOT to**: a DataFrame read
  once (caching adds cost for no reuse); when memory is tight (caching can evict execution
  memory and cause spill/GC — prefer `MEMORY_AND_DISK` or recompute).

## 7. PARTITION PRUNING & DYNAMIC PARTITION PRUNING (Spark 3.0 release notes, SQL internals)
- **Two meanings of "partition" — keep them straight**: (a) **on-disk Hive-style table
  partitions** = `PARTITIONED BY (col)` → one directory per value; (b) **in-memory Spark
  partitions** = the chunks of an RDD/DataFrame (`spark.sql.shuffle.partitions`,
  `repartition`/`coalesce`). **Partition pruning / DPP operate on (a), the on-disk
  partitions.**
- **Create on-disk partitions**: `df.write.partitionBy("country").saveAsTable(...)` or SQL
  `CREATE TABLE … PARTITIONED BY (country)`. Each distinct value becomes a scannable
  directory. (Same caution as Delta: don't over-partition high-cardinality columns →
  partition explosion + tiny files; favor low-cardinality columns like date/region.)
- **Static partition pruning**: a literal filter on a partition column
  (`WHERE country = 'US'`) lets Spark scan only the matching directories at plan time —
  the engine reads far fewer files. Confirm in the plan: `PartitionFilters: [country#.. = US]`.
- **Dynamic Partition Pruning (DPP)**: `spark.sql.optimizer.dynamicPartitionPruning.enabled`
  = **true** (default; **since Spark 3.0.0**; a runtime SQL conf, not on the main config
  table). When a **partitioned fact table** is joined to a **filtered dimension table**, the
  dimension-side filter result is pushed at **runtime** (as a subquery/broadcast result)
  onto the fact table's partition column, pruning fact partitions **before/at scan** — even
  though the filter isn't written directly against the fact table. Requirements: the filtered
  (dimension) side must be broadcastable, the fact side partitioned on the join key; not
  applied to streaming queries. Confirm via `dynamicpruningexpression` in the plan.

## 8. DATA SKEW — SALTING & SQL HINTS (sql-ref-syntax-qry-select-hints, practice)
- **Skew** = data unevenly distributed across keys, so after a shuffle a few partitions are
  huge while others are tiny. The huge partitions become **straggler tasks** (one task runs
  for minutes while the rest finished) → spill/OOM. See it in the UI: one stage has a max
  task time ≫ median, or a max shuffle-read size ≫ the 75th percentile.
- **First line of defence is AQE skew join** (Lesson 05) — enable it before salting.
- **Salting (manual skew fix)** — add a random "salt" suffix to the hot key so its rows
  spread across many partitions:
  - *Aggregation*: group by `(key, salt)` (salt = `floor(rand()*N)`), aggregate, then
    re-aggregate by `key` (two-stage agg) so the hot key's work is split across N partitions.
  - *Join*: salt the skewed (large) side's key with a random `0..N-1`, and **explode** the
    other side into N copies (one per salt value) so every salted key still finds its match;
    join on `(key, salt)`. Trade-off: N× blow-up of the exploded side — pick N for the hot
    keys only (or salt only the known-hot keys).
- **SQL hints** (`/*+ … */` immediately after `SELECT`):
  - **Join strategy**: `BROADCAST(t)` / `MERGE(t)` / `SHUFFLE_HASH(t)` / `SHUFFLE_REPLICATE_NL(t)`
    (priority BROADCAST > MERGE > SHUFFLE_HASH > SHUFFLE_REPLICATE_NL).
  - **Partitioning**: `COALESCE(n)`, `REPARTITION(n | col | n,col)`, `REPARTITION_BY_RANGE([n,] col)`,
    `REBALANCE([n][,col])` (REBALANCE is **ignored unless AQE is enabled**).

## 9. BROADCAST VARIABLES & ACCUMULATORS (rdd-programming-guide)
- **Broadcast variable** (read-only, shared): `bv = sc.broadcast([…])`; read on workers via
  `bv.value`. "A read-only variable cached on each machine rather than shipping a copy of it
  with tasks" — sent **once per executor**, reused by all its tasks. Release with
  `.unpersist()` (re-broadcast if reused) or `.destroy()` (permanent). **Do NOT confuse with
  a broadcast JOIN** — a broadcast *variable* is a value you reference in code; a broadcast
  *join* is a join strategy (driven by `autoBroadcastJoinThreshold`/`BROADCAST` hint). Use a
  broadcast variable for a small lookup dict/set/model used inside a UDF or `map`.
- **Accumulator** (write-only on workers, read-only on driver): `acc = sc.accumulator(0)`
  (Python) / `sc.longAccumulator("name")`. Workers only `.add()`; **only the driver reads
  `.value`**. Used for counters/metrics (e.g. bad-record count). **Exactly-once caveat**:
  "For accumulator updates performed inside **actions** only, Spark guarantees each task's
  update is applied once… In **transformations**, each task's update may be applied more than
  once if tasks or stages are re-executed." So only trust accumulators updated inside actions
  (e.g. `foreach`), not inside lazy transformations that may recompute.

## 10. GARBAGE COLLECTION TUNING (tuning.html — "Garbage Collection Tuning")
- **GC** = the JVM automatically reclaiming memory of objects no longer referenced. Cost is
  "proportional to the number of Java objects" — many small objects = expensive GC.
- **Generations**: heap = **Young** (Eden + two Survivor spaces) + **Old**. New objects go to
  Eden; survivors are promoted to Old. **Minor GC** = collecting Young (frequent, cheap);
  **Major/Full GC** = collecting Old (rare, expensive). A GC is **stop-the-world** — all
  application/Spark task threads **pause** during the collection = a **GC pause**.
- **Executor's role**: GC runs inside each executor's JVM; long pauses stall that executor's
  tasks → the whole stage waits on the slowest executor. Heavy caching fills Old gen → more
  full GCs. See per-task **"GC Time"** in the Spark UI; enable
  `-verbose:gc -XX:+PrintGCDetails -XX:+PrintGCTimeStamps` via `spark.executor.extraJavaOptions`
  (logs land in worker `stdout`).
- **Reduce GC time**:
  - **Serialized caching** (`MEMORY_ONLY_SER`) → "only one object (a byte array) per RDD
    partition" — far fewer objects to track.
  - Prefer **fewer, larger objects** (arrays/primitives over many boxed objects / LinkedLists).
  - **Storage-vs-GC trade-off**: if Old gen is near full, **lower `spark.memory.fraction`**
    so less heap is pinned by cache ("better to cache fewer objects than to slow down task
    execution"). Tune the young-gen size (`-Xmn`) when many short-lived objects churn.
  - **G1GC** (`-XX:+UseG1GC`) for large heaps (increase `-XX:G1HeapRegionSize` for very large
    heaps). **Version note**: since **Spark 4.0.0 (JDK 17 default), G1GC is the default GC**;
    on older Spark/JDK 8 ParallelGC was default and G1GC was the recommended opt-in.
  - **Off-heap / Tungsten** keeps data outside the JVM heap (no GC) — mitigates GC pressure,
    though it's covered in memory management, not the GC-tuning section itself.

## 11. BUCKETING (sql-performance-tuning, SQL internals)
- **Bucketing** pre-shuffles data by a key **once, at write time**, so later joins/aggregations
  on that key need **no shuffle**. API: `df.write.bucketBy(numBuckets, "key").sortBy("key").saveAsTable("cat.sch.tbl")`.
  `spark.sql.sources.bucketing.enabled` = **true** (default; since 2.0.0).
- **How it eliminates the shuffle**: both tables bucketed by the join key into the **same
  number of buckets** produce matching `HashPartitioning` → corresponding buckets are
  co-located → the planner omits the `Exchange` (shuffle) before the join. "The number of
  partitions on both sides of a join has to be exactly the same" and "Both join operators
  have to use HashPartitioning." `sortBy` enables an efficient sort-merge within buckets.
- **`spark.sql.bucketing.coalesceBucketsInJoin.enabled` = false** (default; since 3.1.0).
  When true, if bucket counts differ but one is a multiple of the other, the larger side is
  coalesced to match — avoiding a shuffle. (Easy to assume true; it's false by default.)
- **Bucketing vs partitioning**: partitioning splits data into **directories** (good for
  pruning on low-cardinality filter columns); bucketing splits into a **fixed number of
  files by hash** (good for **join/aggregation keys**, often high-cardinality). They're
  complementary, not substitutes.
- **Limitations**: bucketing is "not supported for `DataFrameWriter.save`, `.insertInto`, or
  `.jdbc`" — you must `saveAsTable()` (a **metastore/UC-registered table**, not plain files).
  If bucket counts differ (and coalesce doesn't apply) a shuffle still happens. Bucket
  pruning applies when filtering on the bucket column. Don't confuse the classic
  `spark.sql.sources.bucketing.enabled` with the DataSource-V2 storage-partition-join flag
  `spark.sql.sources.v2.bucketing.enabled` (true, since 3.3.0) — different feature.

------------------------------------------------------------------------
## Cross-cutting current best practices
- **DataFrame API over RDDs** — Catalyst, Tungsten, AQE, and DPP only optimize DataFrames/SQL.
- **Verify every change** in `df.explain(mode="formatted")` and the **Spark UI** (SQL DAG,
  Exchange nodes, spill/GC/shuffle metrics, task-time distribution) — never assume.
- **Read less first** (pruning/DPP, column pruning, pushdown), then **avoid/repair shuffles**
  (broadcast, bucket, AQE coalesce), then **fix skew** (AQE skew join → salting), then
  **reuse** (cache reused DataFrames), then **size memory & GC** (unified model, off-heap, G1GC).
- **Keep AQE on**; let it coalesce/split/switch before hand-tuning `shuffle.partitions`.
- **State OSS-vs-Databricks**: AQE 10 MB (OSS) vs 30 MB runtime switch (DBX);
  `shuffle.partitions=200` (OSS) vs `auto` (DBX); G1GC default-since-4.0; Photon ≠ AQE.
- On Databricks: Unity Catalog 3-level names `catalog.schema.table`; Delta is the default
  table format (don't write `USING DELTA`); store files in UC Volumes.
