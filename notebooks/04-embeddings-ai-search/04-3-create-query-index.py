# Databricks notebook source
# MAGIC %md
# MAGIC # 04.3 ★ — Create and query a Databricks AI Search index
# MAGIC **Roadmap:** Module 04 (Embeddings and Databricks AI Search) · Topic 04.3 (cornerstone) · [Theory + Hands-on]
# MAGIC
# MAGIC ## The problem
# MAGIC Module 03 landed the Unity Airways policy corpus in one governed Delta table,
# MAGIC `unity_airways.rag.ua_rag_chunks` — one row per chunk (`chunk_id`, `content`, `source_doc`,
# MAGIC `chunk_index`, `ingested_at`). A table of text cannot answer *"Can I get a refund on a Basic
# MAGIC Economy fare?"* by meaning: `WHERE content LIKE '%refund%'` misses the chunk that says "money
# MAGIC back within 24 hours". A **Databricks AI Search index** turns that table into a semantic vector
# MAGIC store you query in milliseconds.
# MAGIC
# MAGIC ## What you will build
# MAGIC Two objects, then a query, three ways:
# MAGIC 1. A **Vector Search endpoint** (`unity-airways-vs`) — the compute that serves indexes.
# MAGIC 2. A **Delta Sync Index with managed embeddings** over `ua_rag_chunks` — Databricks embeds the
# MAGIC    `content` column with `databricks-gte-large-en` and keeps the index synced from the table's
# MAGIC    Change Data Feed.
# MAGIC 3. Query it **three ways** — the Python SDK `similarity_search`, a LangChain retriever, and the
# MAGIC    SQL `vector_search()` function.
# MAGIC
# MAGIC The retriever you build in Step 5b is the hand-off artifact for **Module 05** (it becomes the
# MAGIC "R" in the RAG chain).
# MAGIC
# MAGIC ### Prerequisites (read before running)
# MAGIC - **Compute:** **serverless notebook/job**, or a **DBR ML runtime** (15.4 LTS ML or later is a
# MAGIC   safe floor). Serverless is the simplest default.
# MAGIC - **MLflow:** **≥ 3.1** is the project floor (not exercised in this notebook — retrieval only —
# MAGIC   but it is what Module 05 logs the chain against, so keep the environment consistent).
# MAGIC - **Unity Catalog source table (from Module 03):** `unity_airways.rag.ua_rag_chunks` must exist
# MAGIC   with **Change Data Feed enabled** (`delta.enableChangeDataFeed = true`). This is a **hard
# MAGIC   requirement** for a Delta Sync Index — without it, index creation fails. Step 1 verifies it.
# MAGIC - **Embedding endpoint:** **`databricks-gte-large-en`** (Foundation Model API, 1024-dim,
# MAGIC   8192-token context). Confirm it under **Serving → supported models** for your workspace.
# MAGIC - **Vector Search endpoint:** this notebook **creates** `unity-airways-vs` (Standard). You need
# MAGIC   permission to create a Vector Search endpoint and write access to the `unity_airways.rag` schema.
# MAGIC - **Secrets:** none. Managed embeddings use the in-platform endpoint — no external key required.
# MAGIC - **Learner-set identifiers:** edit `CATALOG` / `SCHEMA` / `ENDPOINT_NAME` in Step 0 to objects
# MAGIC   you own.
# MAGIC
# MAGIC > 📌 **Naming trap:** the product is **Databricks AI Search** (formerly Vector Search), but the
# MAGIC > SDK package is still **`databricks-vectorsearch`** — `from databricks.vector_search.client
# MAGIC > import VectorSearchClient`. There is **no** `databricks-ai-search` package or `AISearchClient`
# MAGIC > class. The LangChain retriever comes from **`databricks-langchain`**.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 0. Install libraries and set variables
# MAGIC `databricks-vectorsearch` (the `VectorSearchClient` SDK) and `databricks-langchain` (the
# MAGIC `DatabricksVectorSearch` retriever). Restart Python so the fresh installs are importable.

# COMMAND ----------

# MAGIC %pip install -U databricks-vectorsearch databricks-langchain
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

CATALOG = "unity_airways"          # a catalog you can write to
SCHEMA  = "rag"                    # a schema you can write to

SOURCE_TABLE   = f"{CATALOG}.{SCHEMA}.ua_rag_chunks"        # from Module 03: chunk_id, content, source_doc, chunk_index, ingested_at
INDEX_NAME     = f"{CATALOG}.{SCHEMA}.ua_rag_chunks_index"  # canonical index name
ENDPOINT_NAME  = "unity-airways-vs"                         # Vector Search endpoint (created below)
EMBED_ENDPOINT = "databricks-gte-large-en"                  # 1024-dim, 8192-token context

print("Source table   :", SOURCE_TABLE)
print("Index          :", INDEX_NAME)
print("VS endpoint    :", ENDPOINT_NAME)
print("Embed endpoint :", EMBED_ENDPOINT)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Confirm Change Data Feed is on the source table
# MAGIC A Delta Sync Index reads the source table's **Change Data Feed** to re-embed only the rows that
# MAGIC changed — so CDF must be on **before** you build the index. Module 03 already enabled it on
# MAGIC `ua_rag_chunks`; this cell is defensive and idempotent (safe to re-run).

# COMMAND ----------

# Idempotent: turns CDF on if it is missing, then shows the property.
spark.sql(f"ALTER TABLE {SOURCE_TABLE} SET TBLPROPERTIES (delta.enableChangeDataFeed = true)")
spark.sql(f"SHOW TBLPROPERTIES {SOURCE_TABLE} (delta.enableChangeDataFeed)").show(truncate=False)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Create the Vector Search endpoint (Standard)
# MAGIC An **endpoint** is the compute that hosts one or more indexes — create it once per environment
# MAGIC and reuse it. Creation is **asynchronous**; `create_endpoint_and_wait(...)` blocks until the
# MAGIC endpoint reaches `ONLINE`. `STANDARD` = low latency for interactive retrieval;
# MAGIC `STORAGE_OPTIMIZED` is for >1B vectors (see 04.7).

# COMMAND ----------

from databricks.vector_search.client import VectorSearchClient   # package: databricks-vectorsearch (NOT databricks-ai-search)

vsc = VectorSearchClient()   # picks up notebook/workspace auth automatically

# Create once and reuse; guard so re-running the notebook does not error.
if not vsc.endpoint_exists(ENDPOINT_NAME):
    vsc.create_endpoint_and_wait(name=ENDPOINT_NAME, endpoint_type="STANDARD")
    print("Created endpoint:", ENDPOINT_NAME)
else:
    print("Endpoint already exists:", ENDPOINT_NAME)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Create the Delta Sync Index with managed embeddings
# MAGIC You hand the index four things — the **source table**, the **primary key**, the **text column**
# MAGIC to embed, and the **embedding model endpoint** — and Databricks does the rest: it embeds every
# MAGIC row's `content` with `databricks-gte-large-en` and keeps the vectors synced from CDF. Managed
# MAGIC embeddings guarantee the **same model** embeds the chunks and (later) each query — the single
# MAGIC biggest lever on relevance. `create_delta_sync_index_and_wait(...)` blocks until the first sync
# MAGIC finishes.

# COMMAND ----------

# Guard against re-creation on re-run.
if not any(i.get("name") == INDEX_NAME for i in vsc.list_indexes(ENDPOINT_NAME).get("vector_indexes", [])):
    index = vsc.create_delta_sync_index_and_wait(
        endpoint_name=ENDPOINT_NAME,
        index_name=INDEX_NAME,
        source_table_name=SOURCE_TABLE,
        primary_key="chunk_id",                        # unique row id used to add/replace/delete vectors
        embedding_source_column="content",             # THIS column gets embedded
        embedding_model_endpoint_name=EMBED_ENDPOINT,  # managed embeddings: Databricks calls gte-large-en
        pipeline_type="TRIGGERED",                     # you call .sync(); cheaper than CONTINUOUS
    )
    print("Created index:", INDEX_NAME)
else:
    index = vsc.get_index(endpoint_name=ENDPOINT_NAME, index_name=INDEX_NAME)
    print("Index already exists:", INDEX_NAME)

# COMMAND ----------

# MAGIC %md
# MAGIC ### How to verify it worked (index is ONLINE)
# MAGIC `create_delta_sync_index_and_wait` already blocked until the first sync finished. To re-fetch a
# MAGIC handle later and confirm readiness, use `get_index(...)` + `wait_until_ready()`.

# COMMAND ----------

# Re-fetch a handle and confirm readiness before querying.
index = vsc.get_index(endpoint_name=ENDPOINT_NAME, index_name=INDEX_NAME)
index.wait_until_ready()                  # blocks until ONLINE
print(index.describe()["status"])         # inspect detailed status

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Re-sync after the source table changes (TRIGGERED only)
# MAGIC A `TRIGGERED` index does **not** auto-update. After a nightly re-chunk writes new rows into
# MAGIC `ua_rag_chunks`, call `index.sync()`; it reads the Change Data Feed and re-embeds only the
# MAGIC new/changed rows and applies deletes — never a full rebuild.

# COMMAND ----------

# Run this after the source table changes (safe to run now — it just triggers a sync).
index.sync()
print("Sync triggered. For a TRIGGERED index, schedule this after each batch write to ua_rag_chunks.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5a. Query — Python SDK `similarity_search`
# MAGIC The lowest-level path: returns a dict you parse. Best for notebooks, batch jobs, and custom
# MAGIC Python agents. Only the `columns` you ask for come back; the **similarity score is always the
# MAGIC last value** in each result row.

# COMMAND ----------

results = index.similarity_search(
    query_text="Can I get a refund on a Basic Economy fare?",
    columns=["chunk_id", "content", "source_doc"],   # only requested columns are returned
    num_results=5,
)
for row in results["result"]["data_array"]:
    # row is [chunk_id, content, source_doc, score] — score is always last
    print(round(row[-1], 3), "|", row[2], "|", row[1][:120], "...")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5b. Query — LangChain retriever (the Module 05 hand-off)
# MAGIC For a **managed-embeddings** index, `DatabricksVectorSearch` auto-detects the embed model — you
# MAGIC pass only text, no separate `DatabricksEmbeddings`. `.as_retriever()` returns the standard
# MAGIC LangChain retriever object that Module 05 drops straight into a RAG chain.

# COMMAND ----------

from databricks_langchain import DatabricksVectorSearch   # package: databricks-langchain (NOT langchain-databricks)

vector_store = DatabricksVectorSearch(
    endpoint=ENDPOINT_NAME,
    index_name=INDEX_NAME,
    columns=["chunk_id", "content", "source_doc"],   # what each retrieved Document carries
)
retriever = vector_store.as_retriever(search_kwargs={"k": 5})

docs = retriever.invoke("Can I change my Basic Economy booking?")
for d in docs:
    # page_content is the chunk text; metadata carries source_doc / chunk_id for citation
    print(d.metadata.get("source_doc"), "|", d.page_content[:120], "...")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5c. Query — SQL `vector_search()` function
# MAGIC A table-valued function callable from any SQL surface (a query, a view, a dashboard, an
# MAGIC `ai_query` batch job). Best for analysts and SQL-native pipelines. It hits the **same index** as
# MAGIC 5a and 5b — three doors, one index.

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT *
# MAGIC FROM vector_search(
# MAGIC   index => 'unity_airways.rag.ua_rag_chunks_index',
# MAGIC   query_text => 'What is the checked baggage allowance on Basic Economy?',
# MAGIC   num_results => 5
# MAGIC );
# MAGIC -- Returns your synced columns plus a similarity score column.
# MAGIC -- (Databricks Runtime 15.2 and below use `query =>` instead of `query_text =>`.)

# COMMAND ----------

# MAGIC %md
# MAGIC ### How to verify retrieval is *good* (not just working)
# MAGIC Read the top chunk. If it contains the **whole** answer (the rule plus its condition), your
# MAGIC Module 03 chunking and this index are in good shape. If the top chunks are near-duplicates or
# MAGIC off-topic, the fix is upstream (chunk size/overlap) or the query mode (04.8 hybrid, 04.9
# MAGIC rerank) — the index faithfully returns whatever you indexed.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6. Briefly — the other two index types (contrast)
# MAGIC This lesson used **Delta Sync · managed embeddings** (the default). Two alternatives exist; you
# MAGIC pick the type by **which create method you call**, not by a string flag.
# MAGIC
# MAGIC - **Self-managed embeddings (Delta Sync).** You precompute vectors into an `ARRAY<FLOAT>` column
# MAGIC   (e.g. from a custom or external model) and build the index over that column instead of the
# MAGIC   text column. You own the "same model for index and query" discipline yourself.
# MAGIC - **Direct Vector Access Index.** No Delta table and no sync — you push and delete vectors
# MAGIC   through the API. For real-time or streaming writes where waiting for a Delta sync is too slow.
# MAGIC
# MAGIC The snippets below are **reference only** — leave them commented unless you need that shape.

# COMMAND ----------

# --- Reference: self-managed embeddings (Delta Sync over a precomputed vector column) ---
# vsc.create_delta_sync_index(
#     endpoint_name=ENDPOINT_NAME,
#     index_name=f"{CATALOG}.{SCHEMA}.ua_rag_chunks_sm_index",
#     source_table_name=f"{CATALOG}.{SCHEMA}.ua_rag_chunks_embedded",  # has your embedding column
#     primary_key="chunk_id",
#     embedding_vector_column="embedding",   # you filled this in yourself
#     embedding_dimension=1024,              # must match your model
#     pipeline_type="TRIGGERED",
# )

# --- Reference: Direct Vector Access (no Delta source; you upsert/delete vectors) ---
# dai = vsc.create_direct_access_index(
#     endpoint_name=ENDPOINT_NAME,
#     index_name=f"{CATALOG}.{SCHEMA}.ua_rag_direct_index",
#     primary_key="chunk_id",
#     embedding_dimension=1024,
#     embedding_vector_column="embedding",
#     schema={"chunk_id": "string", "content": "string",
#             "source_doc": "string", "embedding": "array<float>"},
# )
# dai.upsert([
#     {"chunk_id": "c1", "content": "…", "source_doc": "faq", "embedding": [0.01, 0.02]},  # …1024 floats…
# ])

print("Delta Sync · managed embeddings is the Unity Airways default. See 04.7 for when to switch.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Recap, gotchas and next step
# MAGIC **What you built**
# MAGIC - One **Standard** Vector Search endpoint `unity-airways-vs` (create once, reuse).
# MAGIC - One **Delta Sync · managed-embeddings** index `unity_airways.rag.ua_rag_chunks_index` over
# MAGIC   `ua_rag_chunks`, embedding `content` with `databricks-gte-large-en`, keyed on `chunk_id`,
# MAGIC   `TRIGGERED` pipeline.
# MAGIC - The **same index queried three ways** (SDK `similarity_search`, LangChain retriever, SQL
# MAGIC   `vector_search()`).
# MAGIC
# MAGIC **Gotchas to remember**
# MAGIC - The source Delta table **requires Change Data Feed** — enable it before creating the index.
# MAGIC - Don't query before the index is `ONLINE` — use `wait_until_ready()` / the `_and_wait` helpers.
# MAGIC - A `TRIGGERED` index does not auto-update — call `index.sync()` after each batch write.
# MAGIC - Ask only for **synced columns** in `columns`; include `source_doc`/`chunk_id` so results are citable.
# MAGIC - Package is **`databricks-vectorsearch`** / `VectorSearchClient` (never `databricks-ai-search` /
# MAGIC   `AISearchClient`); retriever is from **`databricks-langchain`** (never `langchain-databricks`).
# MAGIC
# MAGIC **Next:** the retriever from **Step 5b** is handed to **Module 05**, where it becomes the "R" in a
# MAGIC RAG chain. The consolidated module lab (`04-module-lab.py`) extends this same endpoint/index with
# MAGIC metadata filtering (04.4), hybrid search (04.8), and reranking (04.9).
