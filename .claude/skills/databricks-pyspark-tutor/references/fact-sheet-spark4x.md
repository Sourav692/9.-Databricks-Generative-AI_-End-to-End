# Spark 4.x — Verified Fact Sheet (Apache Spark 4.0.0 release notes + Azure Databricks, verified July 2026)

Companion to `references/fact-sheet.md` (the performance track). Facts below were
verified against the **Apache Spark 4.0.0 release notes**
(`spark.apache.org/releases/spark-release-4-0-0.html`), the **Apache Spark `latest`
docs** (the 4.x line), the **`spark-api-beta` MCP** `spark_get_version_changes("4.0")`,
and the **Azure Databricks** docs. Use ONLY these facts; do not invent configs, JIRA
IDs, or version gates. **Always state OSS-Spark vs Databricks scope.**

> **Grounding & honesty notes**
> - The verified major release is **Spark 4.0.0**. The repo venv is on **pyspark 4.1.2**,
>   but the **4.1.0 release notes were not published** at verification time (404) — so
>   anything labeled "4.1" below is **UNVERIFIED — verify at build** and must not be
>   asserted as a confirmed 4.0 fact.
> - **SQL scripting control-flow** (BEGIN/END, IF, WHILE) is the least-settled item:
>   session variables + `EXECUTE IMMEDIATE` are confirmed in 4.0, full procedural blocks
>   are **verify-at-build** (and are more complete on Databricks than in OSS 4.0).
> - Distinguish a feature's **introduction** from when a **default flipped** (e.g. Spark
>   Connect existed pre-4.0; ANSI existed pre-4.0 but its OSS default flipped in 4.0).

------------------------------------------------------------------------
## Canonical doc URLs (cite these)
- Spark 4.0.0 release notes: https://spark.apache.org/releases/spark-release-4-0-0.html
- Spark SQL migration guide (ANSI, behavior changes): https://spark.apache.org/docs/latest/sql-migration-guide.html
- ANSI compliance / `try_*`: https://spark.apache.org/docs/latest/sql-ref-ansi-compliance.html
- Spark Connect overview: https://spark.apache.org/docs/latest/spark-connect-overview.html
- VARIANT / semi-structured: https://spark.apache.org/docs/latest/sql-ref-datatypes.html
- Collation: https://spark.apache.org/docs/latest/sql-ref-collation.html
- Python Data Source API: https://spark.apache.org/docs/latest/api/python/tutorial/sql/python_data_source.html
- Python UDTF: https://spark.apache.org/docs/latest/api/python/user_guide/sql/python_udtf.html
- Arrow-optimized Python UDFs: https://spark.apache.org/docs/latest/api/python/user_guide/sql/arrow_pandas.html
- Structured Streaming — arbitrary state (transformWithState): https://spark.apache.org/docs/latest/structured-streaming-programming-guide.html
- Azure Databricks — Spark Connect / serverless & access modes: https://learn.microsoft.com/en-us/azure/databricks/spark/latest/spark-sql/spark-connect
- Azure Databricks — VARIANT: https://learn.microsoft.com/en-us/azure/databricks/sql/language-manual/data-types/variant-type
> (If a `latest`-docs anchor 404s, fall back to the release-notes JIRA ID and re-verify.)

------------------------------------------------------------------------
## 0. RELEASE BASELINE & BREAKING CHANGES (interviewers probe these)
- **JDK**: **JDK 17 is the default; JDK 8 and 11 are dropped** (SPARK-45315). **Java 21
  supported** (SPARK-43831). This is *why* G1GC is now the default GC (JDK 17) — see the
  perf fact sheet §10.
- **Scala**: **2.13 is the default; Scala 2.12 dropped** (SPARK-45314).
- **Python**: **Python 3.8 dropped → Python ≥ 3.9 required** (SPARK-47993).
- **Cluster managers**: **Mesos removed** (SPARK-44442). **SparkR deprecated** (SPARK-49347).
- **Pandas API on Spark**: multiple deprecated-API removals (SPARK-45550) — check `ps.*`
  behavior-change list before teaching pandas-on-Spark specifics.
- Databricks scope: DBR 15.x/16.x runtimes are built on the Spark 4.x line; several 4.0
  features shipped in DBR **before** the OSS 4.0.0 GA (VARIANT, Python Data Source,
  ANSI-on). State the DBR version prerequisite per lesson.

## 1. SPARK CONNECT (spark-connect-overview, DBX access modes)
- **What it is**: a **decoupled client–server architecture**. The client builds an
  unresolved logical plan and sends it over **gRPC** (protobuf) to a Spark server that
  analyzes, optimizes, and executes it; results stream back as Arrow. The client no
  longer runs in the same JVM/process as the driver.
- **Introduction vs 4.0**: Spark Connect was introduced in **3.4** (experimental) and
  matured in **3.5**. **Spark 4.0 additions**: `spark.api.mode` config to turn Connect
  on/off per application; a **lightweight standalone `pyspark-client`** (~1.5 MB); a
  separate release tarball with Connect enabled by default; **Scala client parity** with
  the Dataset/DataFrame API (SPARK-49248); **ML on Spark Connect**; a **Swift client**.
- **OSS default**: **NOT the default** — opt-in via `spark.api.mode=connect` or a
  `SPARK_REMOTE` / `sc://host:port` connection string.
- **Databricks default (KEY OSS-vs-DBX fact)**: on **serverless compute** and on
  **shared / standard-access-mode** clusters, Databricks runs on **Spark Connect by
  default** (has since DBR 13.3+ for shared access mode). "No-isolation / dedicated"
  legacy clusters use Spark Classic. This is why some RDD/`SparkContext` APIs are
  unavailable on serverless/shared compute.
- **Cross-link**: perf-track Lesson 01 (driver/executor/deploy modes) — Connect changes
  *where the client lives*, not the driver/executor execution model itself.

## 2. ANSI SQL MODE BY DEFAULT (sql-ref-ansi-compliance, sql-migration-guide)
- **`spark.sql.ansi.enabled` = `true` by default in Spark 4.0** (SPARK-44444). Before 4.0
  the OSS default was `false`.
- **Behavior changes**: arithmetic **overflow**, **divide-by-zero**, and **invalid casts**
  now **raise an error** instead of returning `NULL`/silently wrapping; stricter type
  coercion; stricter string→number parsing; reserved-keyword tightening. Errors surface
  as **error classes / SQLSTATE** (Spark 4 error-class framework).
- **The `try_*` escape hatch** (return `NULL` instead of erroring): `try_cast`,
  `try_add`, `try_subtract`, `try_multiply`, `try_divide`, `try_mod`, `try_element_at`,
  `try_sum`, `try_avg`, `try_to_number`, `try_parse_json`, `try_variant_get`,
  `try_reflect`, `try_to_timestamp`, `try_make_timestamp*`, `try_make_interval`,
  `try_parse_url`, `try_url_decode`, `try_validate_utf8`. (`try_cast`, `try_mod`,
  `try_parse_json`, `try_variant_get`, `try_reflect`, `try_make_*`, `try_parse_url`,
  `try_url_decode`, `try_validate_utf8` are confirmed **new in 4.0** by the API changelog.)
- **Databricks scope**: recent DBR already defaulted `spark.sql.ansi.enabled=true`, so on
  Databricks this is often *not* a new behavior — say so. Migration lever: set it `false`
  to restore legacy behavior temporarily (discouraged).

## 3. VARIANT DATA TYPE (sql-ref-datatypes; API changelog; DBX variant)
- **`VariantType`** (SPARK-45827) — a binary-encoded type for **semi-structured** (JSON-
  like) values; preserves structure without a fixed schema, and is faster to read than
  re-parsing a JSON string each query.
- **Functions (all confirmed new in 4.0 via the API changelog)**:
  - Ingest: `parse_json(str)` → VARIANT (errors on invalid JSON); `try_parse_json` → NULL
    on invalid.
  - Read: `variant_get(v, path, type)` extracts + casts (errors on bad cast);
    `try_variant_get` → NULL on missing path / failed cast.
  - Introspect: `schema_of_variant(v)`, `schema_of_variant_agg(v)`, `is_variant_null(v)`.
  - Build: `to_variant_object(col)` (array/map/struct → VARIANT object).
- **When to use**: unpredictable/evolving JSON payloads (events, logs, API blobs) where a
  fixed struct would be brittle. **When a struct wins**: stable schema you query by known
  columns. **When string-JSON wins**: you never query into it (pure passthrough).
- **Databricks**: VARIANT is a Databricks-originated type; note the storage/**shredding**
  optimization angle in the perf discussion (Delta can store VARIANT efficiently).

## 4. STRING COLLATIONS (sql-ref-collation; API changelog)
- **Collation support** (SPARK-46830): attach a **collation** to a `STRING` so `=`,
  `ORDER BY`, `GROUP BY`, `DISTINCT`, and joins become **case-/accent-aware** without
  wrapping every column in `lower()`/`upper()`.
- **Syntax/API**: `col STRING COLLATE UTF8_LCASE` (case-insensitive), `UNICODE`,
  `UNICODE_CI` (case-insensitive), `UNICODE_AI`/`UNICODE_CI_AI` (accent-insensitive);
  functions **`collate(col, 'UTF8_LCASE')`** and **`collation(col)`** (returns the
  collation name) — both confirmed new in 4.0.
- **UTF-8 validation functions (new in 4.0)**: `is_valid_utf8`, `make_valid_utf8`,
  `validate_utf8` (errors on invalid), `try_validate_utf8` (NULL on invalid).
- **Trade-offs**: collation-aware comparison can change join/aggregation results and may
  affect predicate pushdown / data-skipping — flag the correctness-vs-performance angle.
- **Databricks scope**: available on DBR 16.x+ / recent SQL warehouses — state the gate.

## 5. SQL SCRIPTING, SESSION VARIABLES & SUBQUERY DATAFRAME APIs
- **Session variables** (SPARK-42849): `DECLARE VARIABLE name TYPE [DEFAULT expr]`,
  set with `SET VAR name = expr` (or `SET VARIABLE`), referenced in later statements in
  the session. Confirmed in 4.0.
- **`EXECUTE IMMEDIATE`** (SPARK-46246): run a **dynamically-built SQL string**, optionally
  with `USING` args and `INTO` variables. Confirmed in 4.0.
- **Full SQL scripting control-flow** (compound `BEGIN…END`, `IF/ELSE`, `WHILE`, `FOR`,
  handlers): **UNVERIFIED for OSS 4.0 exact gating — verify at build.** The 4.0.0 release
  notes emphasize `EXECUTE IMMEDIATE` + session variables, not full procedural blocks.
  **Databricks** SQL scripting is more complete — cite the Databricks SQL scripting doc
  and note the OSS-vs-DBX difference rather than asserting an OSS version.
- **Subquery DataFrame APIs (new in 4.0, API changelog)**: `DataFrame.scalar` (scalar
  subquery → Column), `DataFrame.exists` (EXISTS subquery → boolean Column),
  `DataFrame.lateralJoin` (correlated/lateral join), and `Column.outer` (mark an outer-
  query column). These close DataFrame-vs-SQL subquery gaps.

## 6. PYTHON DATA SOURCE API (python_data_source tutorial; API changelog)
- **SPIP SPARK-44076** — author a **custom connector in pure Python**, no Scala/JVM.
- **Classes**: subclass `pyspark.sql.datasource.DataSource` (declares `name`, `schema`)
  and provide a `DataSourceReader` (`read` yields rows/tuples/Arrow batches) and/or
  `DataSourceWriter`; streaming via `DataSourceStreamReader` / `DataSourceStreamWriter`.
- **Register & use**: `spark.dataSource.register(MyDataSource)` then
  `spark.read.format("myname").load(...)` / `df.write.format("myname").save(...)`.
  (`SparkSession.dataSource` returns a `DataSourceRegistration` — confirmed new in 4.0.)
- **4.0 enhancements**: Arrow-based writer (SPARK-50471), Python metrics (SPARK-46424),
  DSv2 SQL execution path (SPARK-45597), VARIANT support in UDF/UDTF/data-source
  (SPARK-50238).
- **Ground truth**: use the project's **`spark-python-data-source`** skill for exact
  method signatures and worked examples; don't hand-write the interface from memory.
- **Related — built-in XML** (SPARK-44265): `spark.read.xml(...)` / `df.write.xml(...)`,
  plus `from_xml`, `to_xml`, `schema_of_xml` (all new in 4.0). Fold into this lesson.

## 7. MODERN PYTHON UDFs & UDTFs (arrow_pandas, python_udtf; API changelog)
- **Arrow-optimized Python UDFs**: pass **`useArrow=True`** to `@udf`/`udf(...)`, or set
  `spark.sql.execution.pythonUDF.arrow.enabled=true`, to serialize with Arrow instead of
  pickle → less (de)serialization overhead for many scalar UDFs.
- **Named arguments**: scalar/grouped-agg pandas UDFs and plain UDFs support
  **keyword arguments** in 4.0 (SPARK-44918 / SPARK-44952; `udf`/`pandas_udf`/`udtf`
  "Supports keyword-arguments" per the API changelog).
- **Unified UDF profiling**: `spark.profile.*` configs + **`SparkSession.profile`**
  (new in 4.0) — memory/perf profiling for Python UDFs.
- **Python UDTFs** (SPARK-43797): `@udtf` on a class with an `eval` (and optional class
  `analyze`) method returning **0..N rows** (a table). "Supports Python side analysis"
  and "Supports keyword-arguments" confirmed for `udtf` in 4.0.
- **Table arguments to TVFs/UDTFs**: **`DataFrame.asTable`** → a `TableArg` you can shape
  with `.partitionBy(...)`, `.orderBy(...)`, `.withSinglePartition()`; call TVFs via
  **`SparkSession.tvf`** (all new in 4.0).
- **Arrow group apply**: **`GroupedData.applyInArrow`** and
  **`PandasCogroupedOps.applyInArrow`** (new in 4.0) — `pyarrow.Table`-in/-out group maps.
- **Native PySpark plotting** (SPARK-49530): `df.plot.line()/.bar()/.hist()/.kde()`
  (`DataFrame.plot` new in 4.0; Plotly backend). Works on Classic and Connect. Fold in
  as a "PySpark surface" mention.

## 8. STRUCTURED STREAMING IN 4.x (structured-streaming guide; API changelog)
- **Arbitrary State API v2 — `transformWithState`** (SPARK-46815): a stateful processor
  where you declare typed state — **`ValueState`, `ListState`, `MapState`** — and get
  **timers** (SPARK-49513), **state TTL**, **schema evolution** (SPARK-50573), and
  **batch + streaming** execution (SPARK-46865). It supersedes the older
  `[flat]mapGroupsWithState` for new work.
- **PySpark surface**: **`GroupedData.transformWithStateInPandas`** (new in 4.0, API
  changelog) — implement a `StatefulProcessor` class; needs pandas + pyarrow + protobuf.
- **State Data Source** (SPARK-45511): read a streaming query's **state store as a
  DataFrame** (`spark.read.format("statestore").load(<checkpoint>)`) to inspect/debug
  state — a genuinely new operational capability.
- **`DataStreamWriter.clusterBy`** (new in 4.0): cluster streaming output by columns.
- **Spark 4.1 "real-time mode" / low-latency streaming**: **UNVERIFIED — verify at
  build** (4.1 release notes not yet published). Do not assert as a 4.0 fact.
- **Ground truth**: use the **`databricks-spark-structured-streaming`** skill for exact
  `StatefulProcessor` signatures and DBR gating.

------------------------------------------------------------------------
## Cross-cutting accuracy rules for this track
- **State OSS-vs-Databricks on every version-gated claim.** The two highest-value traps:
  (1) Spark Connect is **opt-in in OSS** but **default on Databricks serverless/shared**;
  (2) ANSI-on is **new in OSS 4.0** but **already default on recent DBR**.
- **Separate "introduced" from "default-flipped"** (Spark Connect 3.4→enhanced 4.0;
  ANSI existed pre-4.0, OSS default flipped in 4.0).
- **Mark 4.1 items and SQL-scripting control-flow "verify at build"** — never assert an
  exact version you could not confirm against a published release note.
- **Use the API-heavy skills as ground truth** for lessons 06/07/08
  (`spark-python-data-source`, `databricks-spark-structured-streaming`) and the
  `spark-api-beta` MCP (`spark_get_version_changes("4.0")`) for signatures/availability.
- On Databricks: UC 3-level names `catalog.schema.table`; Delta is the default table
  format; state the **DBR version prerequisite** per lesson (many 4.0 features are gated).
