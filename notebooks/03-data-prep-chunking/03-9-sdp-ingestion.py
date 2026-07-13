# Databricks notebook source
# MAGIC %md
# MAGIC # 03.9 — RAG ingestion as a Lakeflow Declarative Pipeline (SDP)
# MAGIC **Roadmap:** Module 03 (Data prep and chunking for RAG) · Topic 03.9 · [Hands-on] · **cornerstone**
# MAGIC
# MAGIC ## What this file is
# MAGIC This is a **pipeline source file**, not a normal notebook. Its cells define declarative datasets with
# MAGIC `@dp.table` decorators; a **Lakeflow Declarative Pipeline** reads the whole file, builds the dependency
# MAGIC graph, and runs the stages incrementally. Lakeflow Declarative Pipelines is built on the open-source
# MAGIC **Spark Declarative Pipelines (SDP)** framework and is the successor to Delta Live Tables (DLT).
# MAGIC
# MAGIC > ⚠️ **Do not `Run All` cell-by-cell in an interactive notebook.** The `@dp.*` decorators only *register*
# MAGIC > datasets; they do nothing useful outside a pipeline run. Attach this file to a pipeline (steps below).
# MAGIC
# MAGIC ## The pipeline (a small medallion flow)
# MAGIC ```
# MAGIC  UC Volume (raw docs)
# MAGIC        │  Auto Loader (binaryFile, incremental)
# MAGIC        ▼
# MAGIC  ua_docs_bronze         ← streaming table: raw bytes + source_path + ingested_at
# MAGIC        │  ai_parse_document(content)
# MAGIC        ▼
# MAGIC  ua_docs_parsed         ← streaming table: VARIANT (pages + elements + error_status)
# MAGIC        ├───────────────► ua_docs_quarantine   (error_status[0] IS NOT NULL  → review)
# MAGIC        ▼  error_status[0] IS NULL (clean)
# MAGIC  ua_docs_text           ← streaming table: flatten elements → doc_text, drop noise elements
# MAGIC        │  chunk (RecursiveCharacterTextSplitter)
# MAGIC        ▼
# MAGIC  ua_rag_chunks          ← EMBED-READY: chunk_id, content, source_doc, chunk_index, ingested_at
# MAGIC                            (Change Data Feed ON → Module 04 Delta Sync index)
# MAGIC ```
# MAGIC
# MAGIC ## Prerequisites (read before attaching)
# MAGIC - **Compute:** this pipeline uses **serverless** — the simplest Lakeflow default. `ai_parse_document`
# MAGIC   (an AI Function) requires **Databricks Runtime 17.3+** (classic DBR clusters at that runtime work too);
# MAGIC   on serverless, the environment version must be **≥ 3** (this enables VARIANT). It's available in
# MAGIC   notebooks, the SQL editor, jobs, and Lakeflow pipelines — but not on **SQL Warehouse Classic**
# MAGIC   (Pro/Serverless SQL warehouses are fine).
# MAGIC - **Runtime:** `ai_parse_document` itself needs **Databricks Runtime 17.3+**; if you run on serverless,
# MAGIC   the serverless **environment version must be ≥ 3** (enables VARIANT). Confirm the minimum for your
# MAGIC   workspace at build time (runtime minimums keep rising).
# MAGIC - **Unity Catalog objects (learner-set identifiers):** catalog **`unity_airways`**, schema **`rag`**,
# MAGIC   and a **Volume** holding raw documents at `/Volumes/unity_airways/rag/landing/policies/`
# MAGIC   (PDF / JPG / PNG / TIFF / DOCX / PPTX). Change these to a location you own.
# MAGIC - **Entitlement:** Foundation Model / AI Functions access enabled (parse cost lands under `AI_FUNCTIONS`).
# MAGIC - **Library:** `langchain-text-splitters` for the chunking stage — installed via the `%pip` cell below,
# MAGIC   which Lakeflow treats as a pipeline dependency.
# MAGIC - **Endpoints:** this pipeline calls **no** embedding endpoint. Embeddings happen in **Module 04**, when a
# MAGIC   Databricks AI Search Delta Sync index reads `ua_rag_chunks` and embeds `content` with
# MAGIC   `databricks-gte-large-en`. That is why we enable Change Data Feed on the final table here.
# MAGIC - **Secrets:** none required.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Pipeline library dependency
# MAGIC A `%pip install` at the top of a pipeline source notebook is picked up as a dependency for the whole
# MAGIC pipeline, so the chunking UDF can import the splitter on every worker. (In a `.py` pipeline file managed
# MAGIC by a bundle, declare the same library under the pipeline's environment/dependencies instead.)

# COMMAND ----------

# MAGIC %pip install -U langchain-text-splitters

# COMMAND ----------

# MAGIC %md
# MAGIC ## Imports and configuration
# MAGIC Set the source volume path to your own location. Table names are written **unqualified**; the pipeline's
# MAGIC configured **default catalog + schema** (`unity_airways` / `rag`) decide where they land, so every table
# MAGIC below resolves to `unity_airways.rag.<name>`.

# COMMAND ----------

from pyspark import pipelines as dp          # modern SDP API — NEVER `import dlt`
from pyspark.sql import functions as F
from pyspark.sql.types import ArrayType, StringType

# Learner-set: the UC Volume folder where raw Unity Airways documents land.
LANDING_PATH = "/Volumes/unity_airways/rag/landing/policies/"

# Chunking knobs (see 03.2 / 03.3). ~1200 chars ≈ ~300 tokens at ~4 chars/token — a balanced default.
CHUNK_SIZE    = 1200
CHUNK_OVERLAP = 200

# Element types that are noise for retrieval — dropped before we build doc_text (03.5).
NOISE_ELEMENT_TYPES = ("page_number", "page_footer", "page_header")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Stage 1 — Bronze: incrementally ingest raw documents
# MAGIC Auto Loader (`cloudFiles`, `binaryFile`) streams **new/changed files only** from the Volume, so re-runs are
# MAGIC cheap and a revised policy re-processes just that one file. Each row carries the file bytes (`content`),
# MAGIC its `source_path`, and an `ingested_at` timestamp. This is append-only — minimal transforms in bronze.

# COMMAND ----------

@dp.table(
    name="ua_docs_bronze",
    comment="Raw Unity Airways documents (binary) streamed from the UC Volume with Auto Loader.",
    cluster_by=["source_path"],
)
def ua_docs_bronze():
    return (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "binaryFile")          # each row: path, modificationTime, length, content
        .load(LANDING_PATH)
        .withColumn("source_path", F.col("_metadata.file_path"))   # _metadata, not the legacy input_file_name()
        .withColumn("ingested_at", F.current_timestamp())
    )

# COMMAND ----------

# MAGIC %md
# MAGIC ## Stage 2 — Parsed: `ai_parse_document` on the raw bytes
# MAGIC `ai_parse_document(content)` is a SQL AI Function; we call it from Python with `F.expr(...)`. It returns a
# MAGIC **VARIANT** describing the document — `document.pages[]`, `document.elements[]` (each with `type`,
# MAGIC `content`, `bbox`), a top-level `error_status[]` array, and `metadata`. We keep the raw VARIANT so it is an
# MAGIC audit trail and so we do not have to re-parse (re-parsing costs money).

# COMMAND ----------

@dp.table(
    name="ua_docs_parsed",
    comment="ai_parse_document output as VARIANT (pages, elements, error_status, metadata).",
)
def ua_docs_parsed():
    return (
        spark.readStream.table("ua_docs_bronze")
        .withColumn("parsed", F.expr("ai_parse_document(content)"))   # BINARY in, VARIANT out
        .select("source_path", "ingested_at", "parsed")
    )

# COMMAND ----------

# MAGIC %md
# MAGIC ## Stage 2b — Quarantine failed parses (array-aware error routing)
# MAGIC > ⚠️ **GOTCHA:** `error_status` is an **array** of per-page `{error_message, page_id}` objects (empty/absent
# MAGIC > when clean), **not** a scalar `error`. Always test the first element: route failures with
# MAGIC > `parsed:error_status[0] IS NOT NULL`; keep clean rows with `parsed:error_status[0] IS NULL`.
# MAGIC
# MAGIC Failures land here (unsupported/corrupt file, over the 500-page cap, region issue) for a human to review —
# MAGIC they never silently poison the chunk table.

# COMMAND ----------

@dp.table(
    name="ua_docs_quarantine",
    comment="Documents ai_parse_document could not parse: error_status[0] IS NOT NULL.",
)
def ua_docs_quarantine():
    return (
        spark.readStream.table("ua_docs_parsed")
        .filter(F.expr("parsed:error_status[0] IS NOT NULL"))              # array element [0], never bare field
        .withColumn("error_message", F.expr("parsed:error_status[0]:error_message::STRING"))
        .select("source_path", "ingested_at", "error_message", "parsed")
    )

# COMMAND ----------

# MAGIC %md
# MAGIC ## Stage 3 — Silver text: keep clean rows, flatten + clean to `doc_text`
# MAGIC Two things happen here:
# MAGIC - **Keep only clean parses** (`parsed:error_status[0] IS NULL`).
# MAGIC - **Flatten elements to text in reading order** while **dropping noise element types** (page numbers,
# MAGIC   headers, footers) — that is the 03.5 filtering step done at the element level, so boilerplate never
# MAGIC   reaches a chunk. `explode`/`transform` cannot take a raw VARIANT, so we cast the elements array with
# MAGIC   `variant_get(..., 'ARRAY<VARIANT>')` first.
# MAGIC
# MAGIC The `@dp.expect_or_drop` expectation drops any row whose text came out empty (e.g. a blank scan), so the
# MAGIC chunk table stays clean and the drop is visible in the pipeline's data-quality metrics.

# COMMAND ----------

_noise_sql_list = ", ".join(f"'{t}'" for t in NOISE_ELEMENT_TYPES)

_flatten_expr = f"""
concat_ws('\\n',
  transform(
    filter(
      variant_get(parsed, '$.document.elements', 'ARRAY<VARIANT>'),
      e -> variant_get(e, '$.type', 'STRING') IS NULL
        OR variant_get(e, '$.type', 'STRING') NOT IN ({_noise_sql_list})
    ),
    e -> variant_get(e, '$.content', 'STRING')
  )
)
"""

@dp.table(
    name="ua_docs_text",
    comment="Clean parses flattened to doc_text in reading order; noise elements removed.",
)
@dp.expect_or_drop("non_empty_text", "length(doc_text) > 0")
def ua_docs_text():
    return (
        spark.readStream.table("ua_docs_parsed")
        .filter(F.expr("parsed:error_status[0] IS NULL"))       # clean rows only
        .withColumn("doc_text", F.expr(_flatten_expr))
        # light boilerplate scrub (03.5): collapse blank runs; drop obvious page markers that survived
        .withColumn("doc_text", F.regexp_replace("doc_text", r"(?i)Page \d+ of \d+", ""))
        .withColumn("doc_text", F.regexp_replace("doc_text", r"\n{3,}", "\n\n"))
        .select("source_path", "ingested_at", "doc_text")
    )

# COMMAND ----------

# MAGIC %md
# MAGIC ## Stage 4 — Gold: chunk `doc_text` into the embed-ready table
# MAGIC A Python UDF wraps `RecursiveCharacterTextSplitter` (biggest natural boundary first: paragraph → line →
# MAGIC sentence → word) with a sliding-window overlap. `posexplode` turns the array of chunks into one row per
# MAGIC chunk and gives us a stable **`chunk_index`**. A deterministic `sha2` of `source_path::chunk_index` is the
# MAGIC primary key. Metadata columns (`source_doc`, `chunk_index`, `ingested_at`) travel with every chunk.
# MAGIC
# MAGIC > 📌 **IMPORTANT:** `delta.enableChangeDataFeed = true` on this table is **required** so Module 04's AI
# MAGIC > Search **Delta Sync** index can track row-level changes and re-embed only what changed. Streaming tables
# MAGIC > written by Lakeflow already support incremental reads; CDF is the extra switch the vector index needs.

# COMMAND ----------

@F.udf(ArrayType(StringType()))
def chunk_text_udf(text):
    # Import inside the UDF so it resolves on serverless workers (installed via the %pip cell above).
    if not text:
        return []
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""],   # paragraph → line → sentence → word
    )
    return splitter.split_text(text)


@dp.table(
    name="ua_rag_chunks",
    comment="Embed-ready RAG chunks: chunk_id, content, source_doc, chunk_index, ingested_at.",
    cluster_by=["source_doc"],
    table_properties={"delta.enableChangeDataFeed": "true"},   # required for the Module 04 Delta Sync index
)
@dp.expect_or_drop("non_empty_chunk", "length(content) > 0")
def ua_rag_chunks():
    return (
        spark.readStream.table("ua_docs_text")
        .withColumn("chunks", chunk_text_udf(F.col("doc_text")))
        .select(
            "source_path",
            "ingested_at",
            F.posexplode("chunks").alias("chunk_index", "content"),   # one row per chunk + its index
        )
        .withColumn("source_doc", F.col("source_path"))
        .withColumn(
            "chunk_id",
            F.sha2(F.concat_ws("::", F.col("source_path"), F.col("chunk_index").cast("string")), 256),
        )
        .select("chunk_id", "content", "source_doc", "chunk_index", "ingested_at")
    )

# COMMAND ----------

# MAGIC %md
# MAGIC ## How to attach and run this as a pipeline
# MAGIC This file does nothing on its own — a Lakeflow pipeline executes it. Fastest path (UI):
# MAGIC
# MAGIC 1. **Workflows → Lakeflow Pipelines → Create pipeline** (or **Pipelines → Create**).
# MAGIC 2. **Pipeline mode:** Triggered (run on demand) is fine for the lab; Continuous keeps it live.
# MAGIC 3. **Source code:** add this notebook/file as the pipeline's source.
# MAGIC 4. **Compute:** leave **Serverless** on (required for `ai_parse_document`).
# MAGIC 5. **Destination:** set **Default catalog = `unity_airways`** and **Default schema = `rag`** so the
# MAGIC    unqualified table names resolve to `unity_airways.rag.*`.
# MAGIC 6. **Create**, then **Start**. Watch the DAG build `ua_docs_bronze → ua_docs_parsed → ua_docs_text →
# MAGIC    ua_rag_chunks`, with `ua_docs_quarantine` branching off the parsed table.
# MAGIC
# MAGIC **CLI / bundle alternative:** scaffold with `databricks pipelines init`, drop this logic into a
# MAGIC `transformations/*.py` file (as a plain file, not a notebook), declare `langchain-text-splitters` as a
# MAGIC pipeline library, then `databricks bundle deploy` and `databricks bundle run <pipeline>`.
# MAGIC
# MAGIC > ⚠️ **GOTCHA:** For file ingestion in a streaming table you must stream the source. In Python that is
# MAGIC > `spark.readStream.format("cloudFiles")...` (above). The SQL equivalent is `FROM STREAM read_files(...)` —
# MAGIC > a plain `FROM read_files(...)` is a batch read and fails with "cannot create streaming table from batch query."

# COMMAND ----------

# MAGIC %md
# MAGIC ## Validate after a run
# MAGIC In a **separate** interactive notebook/SQL editor (not this pipeline file), confirm the outputs:
# MAGIC
# MAGIC ```sql
# MAGIC -- Chunks exist, are non-empty, and carry metadata
# MAGIC SELECT count(*) AS chunks,
# MAGIC        count(DISTINCT source_doc) AS docs,
# MAGIC        min(length(content)) AS min_chars,
# MAGIC        max(length(content)) AS max_chars
# MAGIC FROM unity_airways.rag.ua_rag_chunks;
# MAGIC
# MAGIC -- Anything that failed to parse is quarantined, not dropped silently
# MAGIC SELECT source_path, error_message FROM unity_airways.rag.ua_docs_quarantine;
# MAGIC
# MAGIC -- Change Data Feed is enabled for the Module 04 Delta Sync index
# MAGIC SHOW TBLPROPERTIES unity_airways.rag.ua_rag_chunks;
# MAGIC ```
# MAGIC
# MAGIC **Expect:** `chunks > 0`, `min_chars > 0`, quarantine holds only genuinely bad files, and
# MAGIC `delta.enableChangeDataFeed = true`.

# COMMAND ----------

# MAGIC %md
# MAGIC ## SQL-only variant (reference)
# MAGIC If you prefer a SQL pipeline for the ingest + parse + route stages, the same logic is (chunking still needs
# MAGIC the Python UDF above, so a mixed-language pipeline keeps this part in a `.sql` file):
# MAGIC
# MAGIC ```sql
# MAGIC -- Bronze: incremental file ingest
# MAGIC CREATE OR REFRESH STREAMING TABLE ua_docs_bronze AS
# MAGIC SELECT *, _metadata.file_path AS source_path, current_timestamp() AS ingested_at
# MAGIC FROM STREAM read_files('/Volumes/unity_airways/rag/landing/policies/', format => 'binaryFile');
# MAGIC
# MAGIC -- Parsed: ai_parse_document VARIANT
# MAGIC CREATE OR REFRESH STREAMING TABLE ua_docs_parsed AS
# MAGIC SELECT source_path, ingested_at, ai_parse_document(content) AS parsed
# MAGIC FROM STREAM ua_docs_bronze;
# MAGIC
# MAGIC -- Quarantine: array-aware error routing
# MAGIC CREATE OR REFRESH STREAMING TABLE ua_docs_quarantine AS
# MAGIC SELECT source_path, ingested_at, parsed:error_status[0]:error_message::STRING AS error_message, parsed
# MAGIC FROM STREAM ua_docs_parsed
# MAGIC WHERE parsed:error_status[0] IS NOT NULL;
# MAGIC
# MAGIC -- Silver text: clean rows only, flattened
# MAGIC CREATE OR REFRESH STREAMING TABLE ua_docs_text AS
# MAGIC SELECT source_path, ingested_at,
# MAGIC        concat_ws('\n',
# MAGIC          transform(variant_get(parsed, '$.document.elements', 'ARRAY<VARIANT>'),
# MAGIC                    e -> variant_get(e, '$.content', 'STRING'))) AS doc_text
# MAGIC FROM STREAM ua_docs_parsed
# MAGIC WHERE parsed:error_status[0] IS NULL;
# MAGIC ```
# MAGIC
# MAGIC Note the SDP syntax: **`CREATE OR REFRESH STREAMING TABLE`** (never `CREATE OR REPLACE`), and **`FROM STREAM`**
# MAGIC for both file ingestion (`read_files`) and table-to-table streaming.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Recap, gotchas and next steps
# MAGIC **What the pipeline produces**
# MAGIC - `ua_docs_bronze` — raw bytes, incremental via Auto Loader
# MAGIC - `ua_docs_parsed` — `ai_parse_document` VARIANT (audit trail)
# MAGIC - `ua_docs_quarantine` — failed parses (`error_status[0] IS NOT NULL`)
# MAGIC - `ua_docs_text` — clean, flattened, de-noised text
# MAGIC - **`ua_rag_chunks`** — the embed-ready table Module 04 indexes
# MAGIC
# MAGIC **Gotchas to remember**
# MAGIC - Modern API only: `from pyspark import pipelines as dp` + `@dp.table` — never `import dlt` / `@dlt.table`.
# MAGIC - `CREATE OR REFRESH` (SDP), not `CREATE OR REPLACE` (standard SQL).
# MAGIC - `error_status` is an array — route on `parsed:error_status[0]`, never the scalar `parsed:error`.
# MAGIC - `ai_parse_document` needs DBR 17.3+ (serverless env ≥ 3 for VARIANT); serverless is the simplest default, not mandatory — runtime minimums keep rising, so verify for your workspace.
# MAGIC - File ingestion into a streaming table must stream the source (`readStream cloudFiles` / `FROM STREAM read_files`).
# MAGIC - Enable Change Data Feed on `ua_rag_chunks` so the Module 04 Delta Sync index re-embeds only changed rows.
# MAGIC
# MAGIC **Next roadmap step**
# MAGIC - **Module 04 — Embeddings and Databricks AI Search:** build a Delta Sync index on
# MAGIC   `unity_airways.rag.ua_rag_chunks`, embedding `content` with `databricks-gte-large-en`, then retrieve.
# MAGIC - See also **`03-module-lab.py`** for the interactive, cell-by-cell version of extract → filter → chunk →
# MAGIC   Delta → retrieval sanity check.
