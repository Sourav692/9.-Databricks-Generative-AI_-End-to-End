# Databricks notebook source
# MAGIC %md
# MAGIC # 03.8 — Document parsing and extraction with AI Functions
# MAGIC **Roadmap:** Module 03 (Data prep and chunking for RAG) · Topic 03.8 · [Theory + Hands-on]
# MAGIC
# MAGIC ## The problem
# MAGIC Unity Airways has policy documents in a Unity Catalog volume — native PDFs, DOCX guides, and
# MAGIC scanned fare-rule sheets. The RAG assistant needs clean, chunkable text out of every file, plus a
# MAGIC few structured fields (effective date, fare class, refund window). A `pypdf` loop returns empty
# MAGIC strings for scans, scrambles multi-column reading order, and flattens fee tables into word soup.
# MAGIC
# MAGIC ## What you will build
# MAGIC A four-step, SQL-native pipeline: **volume PDF → `ai_parse_document` → text → `ai_extract` → Delta**.
# MAGIC 1. Parse every document to a `VARIANT` of pages and elements.
# MAGIC 2. Flatten elements to a clean `doc_text` string.
# MAGIC 3. Extract named fields with a typed schema.
# MAGIC 4. Land a Delta table ready for chunking (03.9) and embedding (Module 04).
# MAGIC
# MAGIC ### Prerequisites (read before running)
# MAGIC - **Compute:** a **serverless SQL warehouse**, or **serverless notebook/job** compute. AI Functions
# MAGIC   do **not** run on Pro/Classic SQL warehouses or classic clusters (verified July 2026).
# MAGIC - **Runtime:** the AI Functions overview lists **DBR 18.2+**; the `ai_parse_document` reference page
# MAGIC   lists **17.3+**. Minimums have been rising — confirm on the docs for your workspace.
# MAGIC - **Region:** both functions are available in a subset of regions. Check the feature-region support
# MAGIC   matrix for your workspace before you rely on them.
# MAGIC - **Unity Catalog:** a catalog + schema you can write to, and a **volume containing sample documents**
# MAGIC   (PDF / JPG / PNG / TIFF / DOCX / PPTX). Set the variables in the next cell to your location.
# MAGIC - **Entitlement:** AI Functions call Databricks-hosted Foundation Models; your workspace must have
# MAGIC   Foundation Model / AI Functions access enabled. Costs land under the `AI_FUNCTIONS` product.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 0. Configuration — set your governed location
# MAGIC Edit these to a catalog/schema/volume you own. The volume should already hold a few documents.

# COMMAND ----------

# Learner-set variables. Change these to your own UC location.
CATALOG = "unity_airways"
SCHEMA  = "rag"
VOLUME  = "policy_docs"

FQ          = f"{CATALOG}.{SCHEMA}"                       # fully-qualified schema prefix for tables
VOLUME_PATH = f"/Volumes/{CATALOG}/{SCHEMA}/{VOLUME}/"    # where the source documents live

# Create the schema + volume if you have privileges (catalog must already exist).
# Comment these out if your admin provisions UC objects for you.
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {FQ}")
spark.sql(f"CREATE VOLUME IF NOT EXISTS {FQ}.{VOLUME}")

print("Tables prefix :", FQ)
print("Source volume :", VOLUME_PATH)

# COMMAND ----------

# MAGIC %md
# MAGIC ### Confirm the volume has documents
# MAGIC If this lists no files, upload a few PDFs/images to the volume first (Catalog Explorer → the volume →
# MAGIC Upload, or `dbutils.fs.cp`), then re-run.

# COMMAND ----------

files = dbutils.fs.ls(VOLUME_PATH)
for f in files[:20]:
    print(f.name, f"({f.size} bytes)")
assert len(files) > 0, f"No files in {VOLUME_PATH} — add sample documents and re-run."

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Parse every document — `ai_parse_document`
# MAGIC `read_files(..., format => 'binaryFile')` gives each file a `path` and a `content` (BINARY) column.
# MAGIC `ai_parse_document(content)` returns a `VARIANT`: `document.pages[]`, `document.elements[]` (each with
# MAGIC `type`, `content`, `bbox`), a top-level `error_status[]`, and `metadata`. We keep the raw VARIANT in its
# MAGIC own table so it stays as an audit trail (re-parsing costs money).

# COMMAND ----------

spark.sql(f"""
CREATE OR REPLACE TABLE {FQ}.policy_parsed AS
SELECT
  path,
  ai_parse_document(content) AS parsed     -- BINARY in, VARIANT out
FROM read_files('{VOLUME_PATH}', format => 'binaryFile')
""")

print(f"Parsed rows: {spark.table(f'{FQ}.policy_parsed').count()}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### How to verify it worked
# MAGIC Every row should have an empty `error_status` and real text in the first element. Rows where
# MAGIC `error_status[0]` is non-null failed (unsupported, corrupt, over 500 pages, or region issue) — quarantine those.
# MAGIC
# MAGIC > GOTCHA: `error_status` is an **array** of per-page errors (empty/absent when clean), NOT a scalar `error`.
# MAGIC > Filter on `parsed:error_status[0]` — keep clean rows where it IS NULL; route rows where it IS NOT NULL to quarantine.

# COMMAND ----------

spark.sql(f"""
SELECT
  path,
  parsed:metadata:version::STRING              AS schema_version,
  parsed:error_status                          AS errors,           -- empty/absent array when clean
  parsed:document:pages[0]:id::INT             AS first_page_id,
  parsed:document:elements[0]:content::STRING  AS first_text_block
FROM {FQ}.policy_parsed
LIMIT 10
""").display()

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Flatten elements to clean text
# MAGIC Chunking works on text, so we concatenate element `content` in reading order into one `doc_text`.
# MAGIC `explode()` does not accept a raw VARIANT, so we cast the elements array with
# MAGIC `variant_get(..., 'ARRAY<VARIANT>')` first, then `transform` over it. We keep only rows that parsed cleanly.

# COMMAND ----------

spark.sql(f"""
CREATE OR REPLACE TABLE {FQ}.policy_text AS
SELECT
  path,
  concat_ws('\\n',
    transform(
      variant_get(parsed, '$.document.elements', 'ARRAY<VARIANT>'),
      e -> variant_get(e, '$.content', 'STRING')
    )
  ) AS doc_text
FROM {FQ}.policy_parsed
WHERE parsed:error_status[0] IS NULL
""")

print(f"Text rows: {spark.table(f'{FQ}.policy_text').count()}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### How to verify it worked
# MAGIC `doc_text` should be non-empty and readable — including for scanned files, which is the OCR win over
# MAGIC `pypdf`. Sorting shortest-first surfaces near-empty parses worth inspecting.

# COMMAND ----------

spark.sql(f"""
SELECT path, length(doc_text) AS chars, left(doc_text, 300) AS preview
FROM {FQ}.policy_text
ORDER BY chars ASC
LIMIT 10
""").display()

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Extract structured fields — `ai_extract`
# MAGIC `ai_extract(content, schema)` takes text (or a parsed VARIANT) and a JSON **schema string**, and returns
# MAGIC a VARIANT of the fields you asked for. We start simple (a JSON array of names), then use a typed schema
# MAGIC for cleaner values. The `enum` type keeps `fare_class` inside the four cabins.

# COMMAND ----------

# Simple schema: a JSON array of field names. Quick to prototype.
spark.sql(f"""
SELECT
  path,
  ai_extract(doc_text, '["policy_title", "effective_date", "refund_window_days", "fare_class"]') AS fields
FROM {FQ}.policy_text
LIMIT 5
""").display()

# COMMAND ----------

# Typed schema + instructions for better accuracy.
# NOTE: schema_json is a normal (non-f) string so its { } braces are literal JSON, not Python format fields.
schema_json = """{
  "policy_title":       {"type": "string"},
  "effective_date":     {"type": "string", "description": "effective date as yyyy-mm-dd"},
  "refund_window_days": {"type": "integer"},
  "fare_class":         {"type": "enum", "labels": ["Economy", "Premium", "Business", "First"]},
  "change_fee_usd":     {"type": "number"}
}"""

# schema_json is inserted as a value; the f-string does not re-parse its braces.
spark.sql(f"""
CREATE OR REPLACE TABLE {FQ}.policy_extracted AS
SELECT
  path,
  doc_text,
  ai_extract(
    doc_text,
    '{schema_json}',
    map('instructions', 'These are Unity Airways passenger policy documents.')
  ) AS fields
FROM {FQ}.policy_text
""")

print(f"Extracted rows: {spark.table(f'{FQ}.policy_extracted').count()}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Inspect the raw output before hardcoding paths
# MAGIC > GOTCHA: In the current **v2.1** output, each field is an **object** — `value`, plus optional
# MAGIC > `citation_ids` / `confidence_score`. So the value path is `fields:response:effective_date:value`.
# MAGIC > The legacy **v1** form (a `labels` array) returns flat scalar fields instead. Look at the VARIANT
# MAGIC > once and confirm the path for your version before Step 4.

# COMMAND ----------

spark.sql(f"""
SELECT
  path,
  fields:response                 AS response_struct,
  fields:error_message::STRING    AS extract_error
FROM {FQ}.policy_extracted
LIMIT 5
""").display()

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Land a clean Delta table ready for chunking
# MAGIC Pull the field values into typed columns. Adjust the `:value` path if your inspection above showed a
# MAGIC different shape. The result — `doc_text` plus governed metadata columns — is exactly what 03.9 chunks.

# COMMAND ----------

spark.sql(f"""
CREATE OR REPLACE TABLE {FQ}.policy_structured AS
SELECT
  path,
  doc_text,
  fields:response:policy_title:value::STRING       AS policy_title,
  fields:response:effective_date:value::STRING     AS effective_date,
  fields:response:refund_window_days:value::INT    AS refund_window_days,
  fields:response:fare_class:value::STRING         AS fare_class,
  fields:response:change_fee_usd:value::DOUBLE     AS change_fee_usd,
  fields:error_message::STRING                     AS extract_error
FROM {FQ}.policy_extracted
""")

# COMMAND ----------

# MAGIC %md
# MAGIC ### How to verify it worked
# MAGIC Counts should line up: `got_title` tracks `docs`, and `extraction_errors` is near zero.

# COMMAND ----------

spark.sql(f"""
SELECT
  count(*)                                   AS docs,
  count(policy_title)                        AS got_title,
  count_if(extract_error IS NOT NULL)        AS extraction_errors,
  count_if(refund_window_days IS NOT NULL)   AS got_refund_window
FROM {FQ}.policy_structured
""").display()

# COMMAND ----------

spark.sql(f"SELECT * FROM {FQ}.policy_structured LIMIT 10").display()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Optional — the same call from PySpark
# MAGIC AI Functions are also callable via `expr()` inside a DataFrame, handy when your pipeline is already
# MAGIC Python. This does the parse step in PySpark instead of SQL; the underlying function is identical.

# COMMAND ----------

from pyspark.sql.functions import expr

parsed_py = (
    spark.read.format("binaryFile").load(VOLUME_PATH)
    .withColumn("parsed", expr("ai_parse_document(content)"))
    .selectExpr("path", "parsed:error_status AS errors",
                "parsed:document:elements[0]:content::STRING AS first_text_block")
)
parsed_py.display()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Recap, gotchas and next steps
# MAGIC **What you built**
# MAGIC - `policy_parsed` — raw parsed VARIANT (audit trail)
# MAGIC - `policy_text` — flattened `doc_text` in reading order
# MAGIC - `policy_extracted` / `policy_structured` — named fields as typed columns, ready to chunk
# MAGIC
# MAGIC **Gotchas to remember**
# MAGIC - Serverless only — not Pro/Classic SQL warehouses, not classic clusters; runtime minimums are rising.
# MAGIC - Error field is `error_status` (array) — filter on `parsed:error_status[0]`, not the scalar `error`.
# MAGIC - Cast to `ARRAY<VARIANT>` with `variant_get` before `explode`/`transform` on elements.
# MAGIC - `ai_extract` v2.1 wraps each field as `{value, citation_ids, confidence_score}` — inspect before hardcoding `:value`.
# MAGIC - Limits: `ai_parse_document` max 100 MB / 500 pages; `ai_extract` max 128 fields, 7 levels, 128k-token input.
# MAGIC - Both functions are region-limited — verify availability for the workspace.
# MAGIC
# MAGIC **Cleanup (optional)**
# MAGIC ```
# MAGIC spark.sql(f"DROP TABLE IF EXISTS {FQ}.policy_parsed")
# MAGIC spark.sql(f"DROP TABLE IF EXISTS {FQ}.policy_text")
# MAGIC spark.sql(f"DROP TABLE IF EXISTS {FQ}.policy_extracted")
# MAGIC spark.sql(f"DROP TABLE IF EXISTS {FQ}.policy_structured")
# MAGIC ```
# MAGIC
# MAGIC **Next roadmap topic**
# MAGIC - **03.9 — Build the RAG ingestion pipeline as a Lakeflow Spark Declarative Pipeline (SDP):** turn these
# MAGIC   four steps into declarative stages — `from pyspark import pipelines as dp` with `@dp.table` (or SQL
# MAGIC   `CREATE OR REFRESH STREAMING TABLE`) — with an error sidecar and incremental parsing.

# COMMAND ----------


