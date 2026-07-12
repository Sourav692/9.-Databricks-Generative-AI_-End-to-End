# DBX PySpark Performance — Curriculum (14-lesson track)

> **This is the PRIMARY track** (execution engine & tuning). Its sibling, the
> **Spark 4.x — What's New** companion track (new 4.0/4.1 *features*: Spark Connect,
> ANSI-by-default, VARIANT, collations, SQL scripting, Python Data Source API, Arrow
> UDFs/UDTFs, `transformWithState`), has its own curriculum at
> `curriculum-spark4x.md` and fact sheet at `fact-sheet-spark4x.md`. Keep *feature*
> material there and *tuning* material here.

The track teaches the Spark **execution & performance** lifecycle as one story:
**your code becomes jobs/stages/tasks across a driver and executors → joins and
wide operations trigger the expensive shuffle → memory decides what runs vs spills
vs OOMs → AQE adapts the plan at runtime → caching reuses work → pruning reads less
→ skew is the recurring villain (salting/hints) → shared variables move data
efficiently → GC and bucketing are the last-mile tuning levers → Spark UI and
plan reading turn symptoms into evidence → partition/cluster sizing maps work to
capacity → Catalyst/Tungsten explain the advanced optimizer/runtime vocabulary.**
Teach in this order; each lesson links forward/back to its neighbors. The track has four arcs:
**Part A — the engine (01–04)**, **Part B — runtime adaptivity & reuse (05–07)**,
**Part C — skew, shared variables & last-mile tuning (08–11)**, and
**Part D — debugging & production readiness (12–14)**.

> The source course groups lectures into 7 sections. This curriculum **resequences**
> them into a beginner→expert arc (per the user's "place lessons where they fit the
> story" preference): the course's *Edge Node* and *Deployment Modes* lectures move
> up into the Lesson 01 foundation; *Memory Management* splits into a driver lesson
> and an executor lesson; *Salting/Broadcast vars/Accumulators* splits into a skew
> lesson and a shared-variables lesson. Every source lecture is covered.

| # | Folder | Topic | One-line hook | Key doc-grounded facts to nail | Source-course lectures covered |
| --- | --- | --- | --- | --- | --- |
| 01 | `01-spark-architecture` | Spark architecture & the execution model | How a PySpark line of code actually runs on a cluster | driver/executor/cluster-manager; edge node; client vs cluster deploy modes; job→stage→task; lazy eval; transformations vs actions; narrow vs wide deps; partitions; **the shuffle** | Edge Node in Spark; Deployment Modes in Spark (+ foundation for beginners) |
| 02 | `02-joins` | Joins: Sort-Merge vs Shuffle-Hash vs Broadcast | Why the same join can be fast or a cluster-killer | 3 strategies; `autoBroadcastJoinThreshold=10MB`; `preferSortMergeJoin=true`; build vs probe; `broadcast()` + `/*+ BROADCAST */`; reading the Spark UI join nodes | Joins Introduction; Shuffle Sort Merge Join; Shuffle Hash Join; Spark UI for Joins; Broadcast Join; Trigger Broadcast Join In Code |
| 03 | `03-driver-memory` | Driver memory & driver OOM | The one node that can sink the whole job | `spark.driver.memory=1g`; `spark.driver.maxResultSize=1g`; what lives on the driver (`collect()`, broadcast build, plan/metadata); why & how driver OOM; fixes | Driver Memory Management; Why & How Driver OOM Error? |
| 04 | `04-executor-memory` | Executor memory: unified model, spill & OOM | Where the data actually lives, and why it spills or dies | reserved 300 MiB; `spark.memory.fraction=0.6`; `storageFraction=0.5`; storage/execution borrow + evict asymmetry; off-heap; PySpark/Python-worker memory & overhead; **spill**; executor OOM | Executor Memory Overview; Executor Memory Management; Executor's Unified Memory; Data Spilling In Spark; Why and How Executor OOM Error?; Offheap & PySpark Memory |
| 05 | `05-aqe` | Adaptive Query Execution (AQE) | The plan rewrites itself once it sees real data | on by default since Spark 3.2 / DBR 7.3+; coalesce partitions (advisory 64MB); skew join (factor 5, threshold 256MB); sort-merge→broadcast switch; OSS 3 features vs Databricks 4 | What is AQE?; AQE Coalesce; AQE Split Partitions; AQE Joins Strategy |
| 06 | `06-cache-persist` | Cache & persist | Stop recomputing the same DataFrame | `cache()`=`persist(default)`; RDD default `MEMORY_ONLY` vs DataFrame `MEMORY_AND_DISK`; storage levels; lazy materialize; `unpersist()`; PySpark always-serialized | Cache Dataframes; Persist Dataframes; Storage Levels; Apply Caching; Apply Persist; Apply Unpersist |
| 07 | `07-partition-pruning` | Partition pruning & dynamic partition pruning | Read the files you need, skip the rest | on-disk vs in-memory partitions; `PARTITIONED BY`; static pruning; DPP `spark.sql.optimizer.dynamicPartitionPruning.enabled=true` (Spark 3.0+); fact↔filtered-dimension join | Introduction; What are partitions in this context?; How to create Partitions?; Why Partition Pruning?; What is Dynamic Partition Pruning? |
| 08 | `08-salting-hints` | Data skew: salting & SQL hints | When one key has all the rows | skew definition; salting aggregations; salting joins (explode the small side); SQL join hints (BROADCAST/MERGE/SHUFFLE_HASH) + partitioning hints (COALESCE/REPARTITION/REBALANCE) | What is Salting?; Apply Salting in Aggregate Functions; What is Salting in Join Operations?; How to apply Salting with JOINS; SQL Hints in Spark |
| 09 | `09-broadcast-vars-accumulators` | Broadcast variables & accumulators | Ship read-only data once; count things safely | `sc.broadcast(v)`/`.value` (read-only, once per executor) ≠ broadcast *join*; `sc.accumulator`/`longAccumulator` (write-only, driver reads); exactly-once only in actions | What is a Broadcast Variable & Why do we need it?; Accumulators in Spark (Write-Only Variable) |
| 10 | `10-garbage-collection` | Garbage-collection tuning | When the JVM pauses, your tasks pause | young/old generations; minor/major/full GC; stop-the-world pauses; executor's role; reduce GC time (serialized cache, fewer/larger objects, G1GC, off-heap, `memory.fraction` trade-off); UI "GC Time" | What is Garbage Collection?; Garbage Collection Pauses; How to reduce Garbage Collection Time?; Executor's role in GC Cycle |
| 11 | `11-bucketing` | Bucketing to eliminate the shuffle | Pre-shuffle once on write, never again on read | `bucketBy(n,col).sortBy(col).saveAsTable()`; `spark.sql.sources.bucketing.enabled=true`; equal buckets → no Exchange; bucketing vs partitioning; `coalesceBucketsInJoin`; metastore-table requirement | Bucketing to eliminate the shuffle |
| 12 | `12-spark-ui-debugging` | Spark UI & query-plan debugging | Turn symptoms into evidence | `df.explain(mode="formatted")`; SQL/DataFrame DAG; Stages task spread, shuffle, spill, GC; Executors driver/worker signals; Storage cache proof; Environment config proof; runbook from symptom → next check → fix | Added from evaluation rubric: Debugging & Troubleshooting |
| 13 | `13-partition-cluster-sizing` | Partition, shuffle & cluster sizing | Match task waves to cluster capacity | task count = partition count; task waves = partitions ÷ executor cores; `repartition()` vs `coalesce()`; `spark.sql.shuffle.partitions` as pre-AQE upper bound; AQE coalescing; executor memory vs overhead; when workers help vs don't | Added from evaluation rubric: Performance Optimization / cluster sizing |
| 14 | `14-catalyst-tungsten-plans` | Catalyst, Tungsten & physical plan nodes | Read optimizer/runtime vocabulary | parsed/analyzed/optimized/physical plans; DataFrame API visibility; common nodes (`Exchange`, joins, `HashAggregate`, `InMemoryTableScan`, `AQEShuffleRead`); whole-stage codegen; Catalyst vs AQE vs Tungsten vs Photon | Added from evaluation rubric: Advanced Concepts |

## Per-lesson artifact set (DBX PySpark Performance library style)

The track lives in the project's `Spark/` folder. Each `Spark/lessons/<NN-topic>/`
folder contains:

- `lesson.md` — the written lesson (created first), with mermaid diagram, deep dive per
  sub-topic, commented PySpark/SQL/config snippets each paired with a `.explain()` /
  Spark-UI verification note, comparison table, uses/edge-cases/limitations block,
  gotchas, references.
- `index.html` — self-contained interactive page in the house style (≥1 interactive
  diagram; see `references/html-template.md`).
- `<NN-topic>-demo.py` — runnable Databricks notebook that builds data → creates the
  condition → applies the technique → **measures** via `.explain()` / Spark UI / timing
  (see `references/notebook-conventions.md`).

Plus a track landing page at `Spark/index.html` linking all lessons, and a
`Spark/learning plan/` (md + html) summarizing the path.

## The decision framework every learner should leave with

> **Slow Spark job?** Read the plan (`.explain()`) and the Spark UI first. Then, in
> order: (1) **read less** — partition pruning/DPP, column pruning, predicate pushdown;
> (2) **avoid/repair the shuffle** — broadcast the small side, bucket repeated joins,
> let AQE coalesce; (3) **fix skew** — AQE skew join, then salting; (4) **reuse work** —
> cache only reused DataFrames with the right storage level; (5) **size memory** —
> understand the unified model, cure spill/OOM at the right region (driver vs executor),
> tune off-heap & GC last. Always **verify the change in the plan/UI** — never assume.

Teach *why* each lever exists and what it costs, so the learner can both tune a real job
and defend the choice in an interview.
