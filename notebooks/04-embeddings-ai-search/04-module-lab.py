# Databricks notebook source
# MAGIC %md
# MAGIC # Module 04 lab — index → filter → retrieve → tune → hybrid → rerank
# MAGIC **Roadmap:** Module 04 (Embeddings and Databricks AI Search) · consolidated hands-on lab · [Theory + Hands-on]
# MAGIC
# MAGIC One runnable, end-to-end lab over a **single endpoint and index**, walking the module's hands-on
# MAGIC topics in order and finishing with a reranked retriever ready for Module 05:
# MAGIC
# MAGIC | Step | Topic | What you do |
# MAGIC |---|---|---|
# MAGIC | 1 | **04.3** | Create the endpoint + Delta Sync index, query it |
# MAGIC | 2 | **04.4** | Metadata filtering on the query |
# MAGIC | 3 | **04.5** | Build the retriever (managed vs self-managed embeddings) |
# MAGIC | 4 | **04.6** | Latency / cost tuning notes (`num_results`, endpoint sizing) |
# MAGIC | 5 | **04.7** | Index and endpoint types (Delta Sync / Direct / Full-text; Standard / Storage-optimized) |
# MAGIC | 6 | **04.8** | Hybrid search (`query_type="HYBRID"`) |
# MAGIC | 7 | **04.9** | Reranking — portable cross-encoder, keep top-N |
# MAGIC
# MAGIC The cornerstone deep-dive for Step 1 lives in `04-3-create-query-index.py`; this lab reuses the
# MAGIC same `unity-airways-vs` endpoint and `ua_rag_chunks_index` index and layers the rest on top.
# MAGIC
# MAGIC ## Prerequisites (read before running)
# MAGIC - **Compute:** **serverless notebook/job**, or a **DBR ML runtime** (15.4 LTS ML or later is a
# MAGIC   safe floor). Serverless is the simplest default.
# MAGIC - **MLflow:** **≥ 3.1** is the project floor (not exercised here — retrieval only — but it is
# MAGIC   what Module 05 logs the chain against, so keep the environment consistent).
# MAGIC - **Unity Catalog source table (from Module 03):** `unity_airways.rag.ua_rag_chunks` must exist
# MAGIC   with **Change Data Feed enabled** (`delta.enableChangeDataFeed = true`). This is a **hard
# MAGIC   requirement** for a Delta Sync Index — Step 1 verifies it.
# MAGIC - **Embedding endpoint:** **`databricks-gte-large-en`** (Foundation Model API, 1024-dim,
# MAGIC   8192-token context). Confirm under **Serving → supported models**.
# MAGIC - **Vector Search endpoint:** this lab **creates** `unity-airways-vs` (Standard) if missing; you
# MAGIC   need permission to create one and write access to `unity_airways.rag`.
# MAGIC - **Secrets:** none. Managed embeddings and the in-process reranker need no external key.
# MAGIC - **Learner-set identifiers:** edit `CATALOG` / `SCHEMA` / `ENDPOINT_NAME` in Step 0.
# MAGIC
# MAGIC > 📌 **Naming trap:** product is **Databricks AI Search**, SDK is still **`databricks-vectorsearch`**
# MAGIC > (`VectorSearchClient`) — never `databricks-ai-search` / `AISearchClient`. Retriever + chat model
# MAGIC > come from **`databricks-langchain`**, never `langchain-databricks` / `langchain_community`.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 0. Install libraries and set variables
# MAGIC `databricks-vectorsearch` (SDK), `databricks-langchain` (retriever + `ChatDatabricks`), and
# MAGIC `sentence-transformers` (the portable cross-encoder reranker in Step 7). Restart Python after install.

# COMMAND ----------

# MAGIC %pip install -U databricks-vectorsearch databricks-langchain sentence-transformers
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

CATALOG = "unity_airways"          # a catalog you can write to
SCHEMA  = "rag"                    # a schema you can write to

SOURCE_TABLE   = f"{CATALOG}.{SCHEMA}.ua_rag_chunks"        # from Module 03
INDEX_NAME     = f"{CATALOG}.{SCHEMA}.ua_rag_chunks_index"  # canonical index name
ENDPOINT_NAME  = "unity-airways-vs"                         # Vector Search endpoint
EMBED_ENDPOINT = "databricks-gte-large-en"                  # 1024-dim, 8192-token context

print("Source table   :", SOURCE_TABLE)
print("Index          :", INDEX_NAME)
print("VS endpoint    :", ENDPOINT_NAME)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 1 · 04.3 — Create the endpoint + index, and query it
# MAGIC Two objects, then a query. First confirm **Change Data Feed** is on the source table (a Delta
# MAGIC Sync index requires it), then create the endpoint and the managed-embeddings index. All create
# MAGIC calls are guarded so the lab is safe to re-run.

# COMMAND ----------

# CDF is a hard requirement for Delta Sync. Idempotent — safe to re-run.
spark.sql(f"ALTER TABLE {SOURCE_TABLE} SET TBLPROPERTIES (delta.enableChangeDataFeed = true)")
spark.sql(f"SHOW TBLPROPERTIES {SOURCE_TABLE} (delta.enableChangeDataFeed)").show(truncate=False)

# COMMAND ----------

from databricks.vector_search.client import VectorSearchClient   # package: databricks-vectorsearch

vsc = VectorSearchClient()   # notebook/workspace auth is picked up automatically

# Endpoint: create once and reuse. STANDARD = low latency for interactive retrieval.
if not vsc.endpoint_exists(ENDPOINT_NAME):
    vsc.create_endpoint_and_wait(name=ENDPOINT_NAME, endpoint_type="STANDARD")
    print("Created endpoint:", ENDPOINT_NAME)
else:
    print("Endpoint already exists:", ENDPOINT_NAME)

# COMMAND ----------

# Delta Sync Index with MANAGED embeddings: Databricks embeds `content` with gte-large-en and syncs from CDF.
if not any(i.get("name") == INDEX_NAME for i in vsc.list_indexes(ENDPOINT_NAME).get("vector_indexes", [])):
    index = vsc.create_delta_sync_index_and_wait(
        endpoint_name=ENDPOINT_NAME,
        index_name=INDEX_NAME,
        source_table_name=SOURCE_TABLE,
        primary_key="chunk_id",                        # unique row id used to add/replace/delete vectors
        embedding_source_column="content",             # THIS column gets embedded
        embedding_model_endpoint_name=EMBED_ENDPOINT,  # managed embeddings: same model for index + query
        pipeline_type="TRIGGERED",                     # you call .sync(); cheaper than CONTINUOUS
    )
    print("Created index:", INDEX_NAME)
else:
    index = vsc.get_index(endpoint_name=ENDPOINT_NAME, index_name=INDEX_NAME)
    print("Index already exists:", INDEX_NAME)

# COMMAND ----------

# MAGIC %md
# MAGIC ### How to verify it worked, then query (SDK `similarity_search`)
# MAGIC Wait until the index is `ONLINE`, then run a semantic (ANN) query. The similarity score is the
# MAGIC **last value** in each result row; only the `columns` you request come back.

# COMMAND ----------

index = vsc.get_index(endpoint_name=ENDPOINT_NAME, index_name=INDEX_NAME)
index.wait_until_ready()                  # blocks until ONLINE
print(index.describe()["status"])

results = index.similarity_search(
    query_text="Can I get a refund on a Basic Economy fare?",
    columns=["chunk_id", "content", "source_doc"],
    num_results=5,
)
for row in results["result"]["data_array"]:
    print(round(row[-1], 3), "|", row[2], "|", row[1][:110], "...")   # [chunk_id, content, source_doc, score]

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 2 · 04.4 — Metadata filtering on the query
# MAGIC Semantic similarity finds the right *kind* of passage; a **metadata filter** restricts *which*
# MAGIC rows are eligible before ranking. For Unity Airways that means "only search the FAQ" so a dense
# MAGIC Conditions-of-Carriage refund chunk can never compete for a baggage how-to question.
# MAGIC
# MAGIC > 💡 **TIP:** filters only work on columns that were synced into the index (here `source_doc`,
# MAGIC > `chunk_index`). Plan filter columns when you build the index, not after.
# MAGIC >
# MAGIC > ⚠️ **GOTCHA:** filter **syntax depends on endpoint type**. On a **Standard** endpoint use a
# MAGIC > dictionary (shown below). On a **Storage-optimized** endpoint use a SQL-like string
# MAGIC > (`filters="source_doc = 'faq' AND chunk_index < 20"`). Mixing them silently returns
# MAGIC > unfiltered results or errors.

# COMMAND ----------

# Standard endpoint: dictionary filter. Only rows where source_doc == 'faq' are eligible.
# ('faq' is a source_doc that actually exists in ua_rag_chunks from Module 03 — along with
#  'conditions_of_carriage' and 'support_transcript'; the FAQ is the doc with baggage content.)
filtered = index.similarity_search(
    query_text="How do I add a checked bag to my booking?",
    columns=["chunk_id", "content", "source_doc"],
    num_results=5,
    filters={"source_doc": "faq"},   # dict filter on a Standard endpoint
)
print("rows after filter:", len(filtered["result"]["data_array"]))
for row in filtered["result"]["data_array"]:
    print(round(row[-1], 3), "|", row[2], "|", row[1][:110], "...")

# --- Storage-optimized endpoint would instead take a SQL-like string ---
# filters="source_doc = 'faq' AND chunk_index < 20"

# COMMAND ----------

# MAGIC %md
# MAGIC ### How to verify it worked
# MAGIC Every returned row's `source_doc` should be `faq` — no Conditions-of-Carriage or transcript chunks
# MAGIC leak through, and the query returns at least one row. If you get zero rows, an error, or unfiltered
# MAGIC rows, you likely filtered on a `source_doc` that does not exist or used the wrong filter syntax for
# MAGIC the endpoint type.

# COMMAND ----------

returned_docs = {row[2] for row in filtered["result"]["data_array"]}
print("source_doc values returned:", returned_docs)
assert returned_docs, \
    "Filter returned zero rows — 'faq' must be a source_doc in ua_rag_chunks (Module 03) and synced into the index."
assert returned_docs <= {"faq"}, \
    "Filter leaked other source_doc values — check filter syntax vs endpoint type (04.4 GOTCHA)."

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 3 · 04.5 — Build the retriever (the hand-off object)
# MAGIC A **retriever** wraps the index behind one method the chain calls, so Module 05 never touches
# MAGIC the raw query API. It comes from **`databricks-langchain`**.
# MAGIC
# MAGIC - **Managed-embeddings index (ours):** the index owns the embedding model, so the retriever just
# MAGIC   passes text — no separate `DatabricksEmbeddings` needed.
# MAGIC - **Self-managed / Direct Vector Access index:** you must embed the query yourself with the same
# MAGIC   model the index used — `DatabricksEmbeddings(endpoint="databricks-gte-large-en")` — so query and
# MAGIC   document vectors live in one space.

# COMMAND ----------

from databricks_langchain import DatabricksVectorSearch   # package: databricks-langchain

vector_store = DatabricksVectorSearch(
    endpoint=ENDPOINT_NAME,
    index_name=INDEX_NAME,
    columns=["chunk_id", "content", "source_doc"],   # what each retrieved Document carries
)
retriever = vector_store.as_retriever(search_kwargs={"k": 5})

docs = retriever.invoke("Can I rebook for free if my connection is cancelled?")
for d in docs:
    print(d.metadata.get("source_doc"), "|", d.page_content[:110], "...")

# COMMAND ----------

# MAGIC %md
# MAGIC ### How to verify it worked
# MAGIC `retriever.invoke(...)` returns LangChain `Document` objects whose `page_content` is the chunk
# MAGIC text and whose `metadata` carries `source_doc` / `chunk_id`. **Empty metadata means those columns
# MAGIC were not synced** (fix in the index definition, Step 1).

# COMMAND ----------

assert docs, "Retriever returned no documents — is the index ONLINE and synced?"
assert docs[0].metadata.get("source_doc"), "Metadata empty — columns were not synced into the index (04.5)."
print("OK — retriever returns Documents with populated metadata. This object is handed to Module 05.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 4 · 04.6 — Tuning for latency and cost  ·  [Theory, mostly notes]
# MAGIC Retrieval sits on the hot path of every RAG answer, so its latency and cost are the app's. The
# MAGIC levers, biggest first:
# MAGIC - **Endpoint type (biggest lever).** **Standard** = low latency for interactive chat;
# MAGIC   **Storage-optimized** holds >1B vectors and costs much less, at higher latency (see Step 5).
# MAGIC - **`num_results` (k).** Return only what the LLM will read. Fetching 50 when the prompt uses 5
# MAGIC   wastes latency and tokens. Common pattern: fetch a wider set *only* to feed a reranker (Step 7),
# MAGIC   then keep the top few.
# MAGIC - **`columns_to_sync` / `columns`.** Sync and return only the columns you query on — a smaller
# MAGIC   index reads faster.
# MAGIC - **Pipeline type.** `TRIGGERED` syncs on demand (cheaper); `CONTINUOUS` keeps the index live
# MAGIC   (higher cost) — use only when staleness is unacceptable.
# MAGIC - **Query mode cost.** `HYBRID` roughly doubles ANN's work (Step 6) — use it where exact terms
# MAGIC   matter, not as a blanket default.
# MAGIC
# MAGIC > 💡 **TIP:** Right-size before you scale. For Unity Airways' modest corpus, a **Standard**
# MAGIC > endpoint with **TRIGGERED** sync and `k=5` is the cheap, fast default.

# COMMAND ----------

# Small illustration: k is a latency/quality dial. Small k = tight, cheap context; large k = wider net for a reranker.
for k in (3, 5, 10):
    r = index.similarity_search(
        query_text="Can I get a refund on a Basic Economy fare?",
        columns=["chunk_id", "source_doc"],
        num_results=k,
    )
    print(f"num_results={k:>2} -> {len(r['result']['data_array'])} rows returned")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 5 · 04.7 — Index and endpoint types  ·  [Theory]
# MAGIC Two independent choices: which **index type** (how vectors get in and stay current) and which
# MAGIC **endpoint type** (the compute that serves them).
# MAGIC
# MAGIC **Index types**
# MAGIC
# MAGIC | Index type | Embeddings | Sync | Status | Best for |
# MAGIC |---|---|---|---|---|
# MAGIC | **Delta Sync (managed)** | Databricks computes from a text column | Auto from Delta CDF | GA | Easiest — the Unity Airways default (this lab) |
# MAGIC | **Delta Sync (self-managed)** | You precompute a vector column | Auto from Delta CDF | GA | Custom / fine-tuned embedding models |
# MAGIC | **Direct Vector Access** | You provide via CRUD API | Manual upsert / delete | GA | Real-time updates, no Delta source |
# MAGIC | **Full-text search** | None (keyword only) | — | **Beta** | Pure keyword lookup without vectors |
# MAGIC
# MAGIC **Endpoint types**
# MAGIC
# MAGIC | Endpoint type | Latency | Capacity | Cost | Status |
# MAGIC |---|---|---|---|---|
# MAGIC | **Standard** | Low (tens of ms) | Up to hundreds of millions of vectors | Higher per query | GA |
# MAGIC | **Storage-optimized** | Higher | **>1B vectors**, faster indexing | Substantially lower | GA |
# MAGIC
# MAGIC > 📌 **IMPORTANT:** **Delta Sync (managed) + Standard** is the "start here" combination for Unity
# MAGIC > Airways. Change either only for a concrete reason: self-managed for a model Databricks doesn't
# MAGIC > host, Direct Vector Access for non-Delta / real-time data, Storage-optimized for billion-scale
# MAGIC > or cost pressure. **Full-text search is Beta — verify status before production.**

# COMMAND ----------

# Inspect what you actually built: index type, endpoint, and status.
d = index.describe()
print("index_type    :", d.get("index_type"))
print("endpoint_name :", d.get("endpoint_name"))
print("primary_key   :", d.get("primary_key"))
print("status.ready  :", d.get("status", {}).get("ready"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 6 · 04.8 — Hybrid search (keyword + vector)
# MAGIC Pure semantic (ANN) search matches meaning but can miss an **exact token** that must appear — a
# MAGIC booking reference like `UA-8842`, a fare class `Q`, an IATA code `SFO`. **Hybrid search** runs ANN
# MAGIC *and* BM25 keyword scoring and merges the results: semantic recall plus exact-term precision.
# MAGIC Hybrid is **GA** and costs roughly **2x** ANN.
# MAGIC
# MAGIC - Use **ANN** (default) for conceptual, paraphrased questions — most support queries.
# MAGIC - Use **`query_type="HYBRID"`** when the query carries identifiers, acronyms, or technical terms
# MAGIC   that must literally match.

# COMMAND ----------

hybrid = index.similarity_search(
    query_text="baggage fee for fare class Q on flight UA-8842",
    columns=["chunk_id", "content", "source_doc"],
    query_type="HYBRID",     # "ANN" (default) or "HYBRID" (semantic + BM25 keyword)
    num_results=10,
)
for row in hybrid["result"]["data_array"][:5]:
    print(round(row[-1], 3), "|", row[2], "|", row[1][:110], "...")

# Note: a managed index takes just query_text for HYBRID. A self-managed index would also need a
# query_vector for the ANN half.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 7 · 04.9 — Reranking (portable cross-encoder, keep top-N)
# MAGIC The embedding retriever is a **bi-encoder**: it optimizes recall but ranks coarsely, so the best
# MAGIC passage is often *not* rank 1. **Reranking** adds a second stage — a **cross-encoder** reads each
# MAGIC `(query, passage)` pair *together* and re-scores it — then keeps the top-N. It fixes **ordering,
# MAGIC not coverage**: it can only reorder what stage 1 already retrieved.
# MAGIC
# MAGIC Two-stage shape: stage 1 = fast bi-encoder recall (top-K, e.g. K=50); stage 2 = cross-encoder
# MAGIC re-scores and keeps top-N (e.g. N=5) for the LLM.

# COMMAND ----------

K = 50   # stage-1 recall depth (cast a wide net — tune for recall, not order)
N = 5    # stage-2 passages that reach the LLM
QUERY = "Can I get a refund on a Basic Economy fare?"

# Stage 1 — bi-encoder recall via the Module 04 retriever. Reuse the retriever, widen k to K.
stage1 = vector_store.as_retriever(search_kwargs={"k": K})
candidates = stage1.invoke(QUERY)     # K LangChain Documents, ordered by similarity
print(len(candidates), "candidates from stage 1")

# COMMAND ----------

from sentence_transformers import CrossEncoder

# NOTE: verify the current Databricks-native reranking option in docs before shipping.
# This is the PORTABLE cross-encoder pattern (works on any stack, matches B2 Ch3). Do NOT assume a
# `databricks-*-reranker` endpoint name exists — confirm the native option on the docs/supported-models
# page and prefer a governed native reranker if one is available.
reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")   # small open cross-encoder, in-process

pairs  = [(QUERY, d.page_content) for d in candidates]   # pair the query with each candidate passage
scores = reranker.predict(pairs)                          # one relevance score per pair

ranked = sorted(zip(candidates, scores), key=lambda x: x[1], reverse=True)   # best first
top_n  = [doc for doc, _ in ranked[:N]]                   # the N passages the LLM will actually see

# COMMAND ----------

# MAGIC %md
# MAGIC ### How to verify it worked (did the ordering improve?)
# MAGIC Compare what the LLM would have seen **before** (naive top-N by similarity) vs **after**
# MAGIC reranking. Success looks like the passage with the full Basic Economy refund rule rising into the
# MAGIC top-N even if it was rank 6–7 before.

# COMMAND ----------

before = [d.page_content[:80] for d in candidates[:N]]        # naive top-N by similarity
after  = [d.page_content[:80] for d, _ in ranked[:N]]         # reranked top-N
for i, (b, a) in enumerate(zip(before, after), 1):
    print(f"{i}. before: {b}\n   after : {a}\n")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Wrap the two stages into one retrieval function (the Module 05 hand-off)
# MAGIC Module 05 plugs this reranked top-N step into an LCEL chain as the context source for
# MAGIC `ChatDatabricks`. Defined here so the hand-off is a single callable.

# COMMAND ----------

def retrieve_and_rerank(question: str):
    cands = stage1.invoke(question)                                        # stage 1: top-K recall
    s = reranker.predict([(question, d.page_content) for d in cands])      # stage 2: score each pair
    order = sorted(zip(cands, s), key=lambda x: x[1], reverse=True)
    return [d for d, _ in order[:N]]                                       # reranked top-N

reranked_docs = retrieve_and_rerank(QUERY)
print(f"retrieve_and_rerank -> {len(reranked_docs)} reranked docs (top-{N}) ready for Module 05")
for d in reranked_docs:
    print(" -", d.metadata.get("source_doc"), "|", d.page_content[:90], "...")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Recap, gotchas and next step
# MAGIC **What you built** — over one `unity-airways-vs` endpoint and one `ua_rag_chunks_index`:
# MAGIC - Created + queried the managed Delta Sync index (04.3)
# MAGIC - Metadata-filtered retrieval on `source_doc` (04.4)
# MAGIC - A LangChain retriever, the module's hand-off object (04.5)
# MAGIC - Latency/cost intuition — `num_results`, endpoint sizing, pipeline type (04.6)
# MAGIC - The index/endpoint type map, and inspected what you actually built (04.7)
# MAGIC - Hybrid (semantic + keyword) search for exact-token queries (04.8)
# MAGIC - Two-stage retrieval with a portable cross-encoder reranker (04.9)
# MAGIC
# MAGIC **Gotchas to remember**
# MAGIC - Source table needs **Change Data Feed**; `TRIGGERED` indexes need an explicit `index.sync()`.
# MAGIC - Match **filter syntax to endpoint type** — dict on Standard, SQL-like string on Storage-optimized.
# MAGIC - Only **synced columns** are filterable/returnable; empty metadata means a column wasn't synced.
# MAGIC - **Hybrid** ≈ 2x ANN cost — use it where exact terms matter, not by default.
# MAGIC - Reranking fixes **ordering, not recall** — if the good passage isn't in the top-K, raise K or
# MAGIC   fix chunking/hybrid first. Keep K several times N (e.g. K=50, N=5).
# MAGIC - **Verify the native reranking option in docs before shipping** — don't hard-code an unverified
# MAGIC   `databricks-*-reranker` endpoint name.
# MAGIC
# MAGIC **Next:** **Module 05** takes the `retrieve_and_rerank` function (the reranked top-N retriever)
# MAGIC and wires it into an LCEL RAG chain with `ChatDatabricks` — the "R" and the "G" of RAG connected.
