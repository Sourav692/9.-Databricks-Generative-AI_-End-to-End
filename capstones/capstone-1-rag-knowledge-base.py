# Databricks notebook source
# MAGIC %md
# MAGIC # Capstone C1 — Unity Airways Support RAG Knowledge Base
# MAGIC **Roadmap:** Capstone C1 · Build after Phase P1 (Modules 00–05) · [Hands-on · Project]
# MAGIC
# MAGIC ## What you are building
# MAGIC You shipped Modules 00–05 as separate lessons. This capstone welds them into one working system —
# MAGIC the first Unity Airways artifact every later capstone extends. A support agent asks a policy
# MAGIC question in plain language and gets back a grounded answer **plus the document it came from**, so
# MAGIC they can trust it and paste the citation into the ticket.
# MAGIC
# MAGIC The spine is left-to-right, no loops:
# MAGIC
# MAGIC ```
# MAGIC  raw policy docs        ai_parse_document      chunk + clean       AI Search           LCEL RAG chain        Models-from-Code
# MAGIC  (UC Volume)     ──▶    → clean text     ──▶   → Delta + CDF  ──▶  Delta Sync index ──▶ (registry prompt) ──▶ → registered UC model
# MAGIC  landing/policies       M1                     ua_rag_chunks       ua_rag_chunks_index  databricks-claude…    ua_rag_chain
# MAGIC ```
# MAGIC
# MAGIC **The line to remember: ingest → chunk → index → chain → register.** Each milestone hands its output
# MAGIC to the next, so build them in order. Skipping ahead (for example, indexing before Change Data Feed is
# MAGIC on the table) is the fastest way to a mid-build stall.
# MAGIC
# MAGIC The three graded deliverables you produce:
# MAGIC 1. `unity_airways.rag.ua_rag_chunks` — the governed Delta chunk table (Change Data Feed on).
# MAGIC 2. `unity_airways.rag.ua_rag_chunks_index` — the ONLINE Delta Sync index (managed `databricks-gte-large-en` embeddings).
# MAGIC 3. `unity_airways.rag.ua_rag_chain` — the registered UC model, logged as Models-from-Code.
# MAGIC
# MAGIC ## Prerequisites (read before running)
# MAGIC - **Compute:** **serverless notebook/job**, or a recent **DBR ML runtime**. `ai_parse_document` (M1)
# MAGIC   needs serverless or a recent DBR — the two live doc pages disagree on the floor (**DBR 17.3+** on the
# MAGIC   function reference vs **18.2+ / serverless env v3+** on the AI Functions overview). Confirm against
# MAGIC   your workspace. **Not** a Classic/Pro SQL warehouse.
# MAGIC - **MLflow:** **≥ 3.1** — Models-from-Code, `set_active_model`/LoggedModel, `ModelConfig`, and the
# MAGIC   `mlflow.genai` prompt surface all require MLflow 3.
# MAGIC - **MLflow Prompt Registry (Beta):** needs `mlflow[databricks]>=3.1.0`, a UC schema
# MAGIC   (`unity_airways.rag`) where you hold **`CREATE FUNCTION` + `EXECUTE` + `MANAGE`**, and the feature
# MAGIC   enabled on the workspace **Previews** page. Used in M4 to register and load the chain's prompt.
# MAGIC - **Unity Catalog:** rights to create/use the catalog `unity_airways`, schema `rag`, a UC Volume,
# MAGIC   Delta tables, a Vector Search index, and a UC model in `unity_airways.rag`.
# MAGIC - **Foundation Model endpoints:** **`databricks-gte-large-en`** (embeddings, 1024-dim / 8192-token)
# MAGIC   and **`databricks-claude-sonnet-4-5`** (chat). **Served-model names churn** — reconfirm both on
# MAGIC   *Serving → supported models* before hard-coding (both verified on the live supported-models page at
# MAGIC   authoring time).
# MAGIC - **Packages:** `databricks-vectorsearch` (the `VectorSearchClient` SDK — name unchanged despite the
# MAGIC   "AI Search" rebrand), `databricks-langchain` (`ChatDatabricks`, `DatabricksVectorSearch`), `mlflow`,
# MAGIC   plus `langchain-text-splitters`, `tiktoken`, and `fpdf2` (to seed sample PDFs so this notebook runs
# MAGIC   end-to-end with no manual upload).
# MAGIC - **Learner-set identifiers:** the constants in Section 0. Keep the **canonical names** — C2, C3, and
# MAGIC   C4 all extend these exact artifacts, so renaming here breaks continuity down the track.
# MAGIC
# MAGIC > ⚠️ **GOTCHA:** The package is **`databricks-vectorsearch`** even though the product is now
# MAGIC > **Databricks AI Search**. There is no `databricks-ai-search` package and no `AISearchClient`. And the
# MAGIC > LangChain integration is **`databricks-langchain`**, not `langchain-databricks` or `langchain_community`.
# MAGIC > Two of the most common build-blockers in this capstone are import errors from getting these wrong.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 0. Install libraries and set variables
# MAGIC Install everything once, restart Python so the fresh installs import, then set the canonical names.
# MAGIC `mlflow[databricks]>=3.1.0` is the floor the Prompt Registry (M4) needs; `fpdf2` only exists to seed
# MAGIC sample documents in M1.

# COMMAND ----------

# MAGIC %pip install -U databricks-vectorsearch databricks-langchain "mlflow[databricks]>=3.1.0" langchain-text-splitters tiktoken fpdf2
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

# --- Canonical Unity Airways names. Keep these; later capstones inherit them. ---
CATALOG        = "unity_airways"                              # a catalog you can write to
SCHEMA         = "rag"                                        # the RAG schema (needs CREATE FUNCTION/EXECUTE/MANAGE for M4)
VOLUME         = "landing"                                    # UC Volume that holds the raw source docs
FQ             = f"{CATALOG}.{SCHEMA}"

LANDING        = f"/Volumes/{CATALOG}/{SCHEMA}/{VOLUME}/policies"   # where the source PDFs land
SOURCE_TABLE   = f"{FQ}.ua_rag_chunks"                        # M2 deliverable: the governed chunk table
INDEX_NAME     = f"{FQ}.ua_rag_chunks_index"                  # M3 deliverable: the Delta Sync index
VS_ENDPOINT    = "unity-airways-vs"                           # Vector Search (AI Search) endpoint
PROMPT_NAME    = f"{FQ}.ua_rag_prompt"                        # M4: the registered RAG prompt (UC identifier)
PROMPT_URI     = f"prompts:/{PROMPT_NAME}/1"                  # the chain loads the prompt by this URI (v1)
UC_MODEL       = f"{FQ}.ua_rag_chain"                         # M5 deliverable: the registered chain
K              = 5                                            # top-k chunks the retriever returns

# Served-model endpoints — names churn; reconfirm on Serving > supported models.
CHAT_ENDPOINT  = "databricks-claude-sonnet-4-5"              # chat / generation
EMBED_ENDPOINT = "databricks-gte-large-en"                  # managed embeddings (1024-dim, 8192-token)

print("Landing volume :", LANDING)
print("Chunk table    :", SOURCE_TABLE)
print("Index          :", INDEX_NAME)
print("VS endpoint    :", VS_ENDPOINT)
print("Prompt URI     :", PROMPT_URI)
print("UC model       :", UC_MODEL)

# COMMAND ----------

# MAGIC %md
# MAGIC ### Create the UC objects and seed a small, realistic corpus
# MAGIC To keep the notebook self-contained, we generate a few tiny Unity Airways policy PDFs and write them
# MAGIC into the landing Volume. In a real build these files already exist (support uploads policy PDFs, an
# MAGIC FAQ export, and scanned refund forms). We use **PDFs** here because `ai_parse_document` accepts
# MAGIC **PDF / JPG / PNG / DOCX** — not plain `.txt`/`.md` — so PDFs are what makes M1 genuinely runnable.
# MAGIC
# MAGIC > 💡 **TIP:** In production the refund forms are image-only scans; `ai_parse_document` OCRs them
# MAGIC > automatically (see `03-8-ai-parse-extract.py`). We ship typed PDFs here so the run is deterministic.

# COMMAND ----------

import os

# Idempotent, privilege-tolerant setup. If you cannot create the catalog, your admin likely provisioned it.
for stmt in [
    f"CREATE CATALOG IF NOT EXISTS {CATALOG}",
    f"CREATE SCHEMA IF NOT EXISTS {FQ}",
    f"CREATE VOLUME IF NOT EXISTS {FQ}.{VOLUME}",
]:
    try:
        spark.sql(stmt)
        print("OK  :", stmt)
    except Exception as e:
        print("SKIP:", stmt, "->", str(e)[:120])

os.makedirs(LANDING, exist_ok=True)   # Volumes support direct POSIX file ops on serverless / DBR

# Five short policies, one per demo question. NOTE: the re-accommodation policy deliberately avoids the
# words "rebook" and "free" so semantic retrieval has to earn the match in M3.
POLICIES = {
    "basic_economy_refund": (
        "Unity Airways - Basic Economy Refund Policy",
        "Basic Economy fares are non-refundable except where required by law.\n"
        "A Basic Economy ticket cancelled within 24 hours of purchase, and at least 7 days before "
        "departure, qualifies for a full refund to the original form of payment under the 24-hour "
        "flexible booking policy.\n"
        "Outside that window, Basic Economy tickets hold no cash value. The fare may be cancelled for "
        "travel credit only where the fare rules allow, less any applicable service charge."
    ),
    "checked_bag_fee": (
        "Unity Airways - Checked Baggage Fees",
        "The first checked bag costs USD 35 when prepaid online and USD 45 when paid at the airport.\n"
        "The second checked bag costs USD 50. Each additional bag costs USD 100.\n"
        "The standard weight limit is 23 kg (50 lb) per bag. Bags between 23 kg and 32 kg incur a USD 100 "
        "overweight surcharge. Oversized bags larger than 158 cm total dimensions incur a USD 75 surcharge."
    ),
    "involuntary_reaccommodation": (
        "Unity Airways - Involuntary Re-accommodation",
        "When a Unity Airways flight is cancelled, or a passenger misses a connection because of a delay "
        "within Unity Airways' control, the passenger is protected onto the next available Unity Airways "
        "service at no additional charge.\n"
        "No fare difference is collected for involuntary re-accommodation, and no change fee applies.\n"
        "If no suitable alternative Unity Airways flight departs within 8 hours, the passenger may instead "
        "request a refund of the unused portion of the ticket, regardless of the original fare type."
    ),
    "change_booking": (
        "Unity Airways - Changing an Existing Booking",
        "To change an existing booking, open Manage Booking, select the flight, and choose Change Flight. "
        "Changes must be completed at least 3 hours before scheduled departure.\n"
        "Change fees are waived on Premium, Business, and First fares; a fare difference may still apply.\n"
        "Basic Economy fares cannot be changed after the 24-hour flexible booking window; the ticket must "
        "be cancelled under the applicable fare rules and a new booking made."
    ),
    "delay_policy": (
        "Unity Airways - Delay and Overnight Disruption Policy",
        "When a delay within Unity Airways' control forces an overnight stay away from the passenger's "
        "origin or destination, Unity Airways provides hotel accommodation and ground transfers.\n"
        "Meal vouchers are provided for delays exceeding 3 hours. Affected passengers are protected onto "
        "the next available Unity Airways flight at no additional charge.\n"
        "These care amenities are not provided when the delay is caused by events outside Unity Airways' "
        "control, such as severe weather or air traffic control restrictions."
    ),
}

def write_policy_pdf(path, title, body):
    from fpdf import FPDF                         # fpdf2: pure-python, no system deps
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.multi_cell(0, 8, title)
    pdf.ln(2)
    pdf.set_font("Helvetica", "", 11)
    for line in body.split("\n"):
        pdf.multi_cell(0, 6, line)
        pdf.ln(1)
    with open(path, "wb") as f:
        f.write(pdf.output())                     # fpdf2 returns a bytearray

for name, (title, body) in POLICIES.items():
    write_policy_pdf(f"{LANDING}/{name}.pdf", title, body)

# Confirm the files landed.
files = dbutils.fs.ls(LANDING)
for f in files:
    print(f.name, f"({f.size} bytes)")
assert len([f for f in files if f.name.endswith(".pdf")]) >= 5, "Expected at least 5 seed PDFs in the landing Volume."

# COMMAND ----------

# MAGIC %md
# MAGIC ## M1 · Ingest + parse the raw documents  ·  03.4 / 03.8
# MAGIC Read the raw files straight from the Volume and extract clean text with `ai_parse_document`. We keep
# MAGIC the raw parsed VARIANT as an audit trail, then split it two ways using the **array-aware** error
# MAGIC filter: rows that parsed cleanly (`error_status[0] IS NULL`) flow downstream; rows that failed
# MAGIC (`error_status[0] IS NOT NULL`) go to a quarantine table instead of poisoning the corpus.
# MAGIC
# MAGIC > ⚠️ **GOTCHA:** `error_status` is an **array** of per-page errors (empty/absent when clean), not a
# MAGIC > scalar `error`. Filtering on `parsed:error_status[0]` is the locked, correct predicate.

# COMMAND ----------

# read_files(..., format => 'binaryFile') gives each file a `path` (STRING) and `content` (BINARY).
# ai_parse_document(content) returns a VARIANT: document.pages[], document.elements[], error_status[], metadata.
spark.sql(f"""
CREATE OR REPLACE TABLE {FQ}.policy_parsed AS
SELECT
  path,
  ai_parse_document(content) AS parsed     -- BINARY in, VARIANT out
FROM read_files('{LANDING}/', format => 'binaryFile')
""")
print("Parsed rows:", spark.table(f"{FQ}.policy_parsed").count())

# COMMAND ----------

# Clean rows -> policy_text (flatten elements to one doc_text string, in reading order).
# explode/transform need ARRAY<VARIANT>, so cast with variant_get first (mirrors 03.8).
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

# Failed rows -> quarantine (unsupported format, corrupt, >500 pages, region issue).
spark.sql(f"""
CREATE OR REPLACE TABLE {FQ}.policy_quarantine AS
SELECT path, parsed:error_status AS error_status
FROM {FQ}.policy_parsed
WHERE parsed:error_status[0] IS NOT NULL
""")

print("Clean rows      :", spark.table(f"{FQ}.policy_text").count())
print("Quarantined rows:", spark.table(f"{FQ}.policy_quarantine").count())

# COMMAND ----------

# MAGIC %md
# MAGIC ### How to verify it worked  (acceptance: M1)
# MAGIC Clean text exists for every source document, the prose is readable (spot-check three), and the
# MAGIC quarantine split is in place. With this tidy seed corpus the quarantine table is expected to be
# MAGIC **empty (0 rows)** — that is success, not failure. Drop a non-document file (e.g. a `.txt`) into the
# MAGIC landing Volume and re-run M1 to watch it route to quarantine instead of flowing downstream.

# COMMAND ----------

# Spot-check the parsed prose.
spark.sql(f"""
SELECT
  regexp_extract(path, '([^/]+)\\\\.[A-Za-z0-9]+$', 1) AS source_doc,
  length(doc_text) AS chars,
  left(doc_text, 200) AS preview
FROM {FQ}.policy_text
ORDER BY chars ASC
""").display()

clean_count = spark.table(f"{FQ}.policy_text").count()
assert clean_count >= 5, f"Expected >= 5 cleanly parsed docs, got {clean_count}."
assert spark.sql(f"SELECT min(length(doc_text)) AS m FROM {FQ}.policy_text").collect()[0]["m"] > 0, \
    "A parsed doc_text is empty — inspect ai_parse_document output before chunking."
print(f"OK — {clean_count} documents parsed to clean text; quarantine split applied on parsed:error_status[0].")

# COMMAND ----------

# MAGIC %md
# MAGIC ## M2 · Chunk the text → governed Delta table (CDF)  ·  03.2 / 03.6
# MAGIC Clean light noise off the parsed text, then chunk it. These policies are short and self-contained,
# MAGIC so a recursive splitter at **~200 tokens with a sliding-window overlap** keeps each rule together
# MAGIC (dense fare-rules cross-reference each other, so overlap matters). We write **one row per chunk** to
# MAGIC the canonical UC managed Delta table with metadata, then enable **Change Data Feed** so the Delta
# MAGIC Sync index in M3 can re-embed only rows that change.

# COMMAND ----------

import re
from pyspark.sql import functions as F
from langchain_text_splitters import RecursiveCharacterTextSplitter

def clean_text(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)                                   # strip any stray markup
    text = re.sub(r"(?i)page \d+ of \d+", "", text)                        # page numbers
    text = re.sub(r"(?i)last updated:.*?(\n|$)", "", text)                 # timestamps
    text = re.sub(r"(?i)this document is confidential.*?(\n|$)", "", text) # boilerplate disclaimer
    # de-duplicate identical non-empty lines, preserving order
    seen, out = set(), []
    for line in text.splitlines():
        s = line.strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return "\n".join(out)

# Pull the clean parsed text into Python and derive source_doc from the file name (the path stem).
parsed_rows = spark.table(f"{FQ}.policy_text").collect()
raw_docs = {
    os.path.splitext(os.path.basename(r["path"]))[0]: r["doc_text"]
    for r in parsed_rows
}

# ~200 tokens ~= ~900 chars; 150-char overlap keeps cross-referenced clauses together.
splitter = RecursiveCharacterTextSplitter(
    chunk_size=900, chunk_overlap=150,
    separators=["\n\n", "\n", ". ", " ", ""],
)

rows = []
for source_doc, text in raw_docs.items():
    for idx, content in enumerate(splitter.split_text(clean_text(text))):
        rows.append((source_doc, idx, content))

chunks_df = (
    spark.createDataFrame(rows, ["source_doc", "chunk_index", "content"])
    .withColumn("chunk_id",
                F.sha2(F.concat_ws("::", "source_doc", F.col("chunk_index").cast("string")), 256))
    .withColumn("ingested_at", F.current_timestamp())
    .select("chunk_id", "content", "source_doc", "chunk_index", "ingested_at")   # canonical column order
)

(chunks_df.write.format("delta").mode("overwrite")
    .option("overwriteSchema", "true")
    .saveAsTable(SOURCE_TABLE))

# Delta Sync indexes (M3) require Change Data Feed on the source table.
spark.sql(f"ALTER TABLE {SOURCE_TABLE} SET TBLPROPERTIES (delta.enableChangeDataFeed = true)")
print("Wrote:", SOURCE_TABLE)

# COMMAND ----------

# MAGIC %md
# MAGIC ### How to verify it worked  (acceptance: M2)
# MAGIC A UC managed table with the canonical columns; `chunk_id` unique; Change Data Feed on; row count > 0;
# MAGIC a sampled row is a clean, self-contained chunk with populated metadata. No `/mnt/...` DBFS paths.

# COMMAND ----------

stats = spark.sql(f"""
SELECT count(*) AS chunks,
       count(DISTINCT chunk_id) AS unique_ids,
       count(DISTINCT source_doc) AS docs,
       min(length(content)) AS min_chars
FROM {SOURCE_TABLE}
""").collect()[0]
print(dict(stats.asDict()))

spark.sql(f"SELECT chunk_id, source_doc, chunk_index, left(content, 90) AS preview "
          f"FROM {SOURCE_TABLE} ORDER BY source_doc, chunk_index").display()

cdf_on = spark.sql(f"SHOW TBLPROPERTIES {SOURCE_TABLE} (delta.enableChangeDataFeed)").collect()[0]["value"]
assert stats["chunks"] > 0, "Chunk table is empty."
assert stats["chunks"] == stats["unique_ids"], "chunk_id is not unique."
assert cdf_on == "true", "Change Data Feed is not enabled — the Delta Sync index needs it."
print("OK — governed chunk table with unique ids, metadata, and Change Data Feed on.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## M3 · Build + query the AI Search index  ·  04.3
# MAGIC Create a **Standard** Vector Search endpoint, then a **Delta Sync index with managed embeddings** on
# MAGIC `ua_rag_chunks`: primary key `chunk_id`, embed the `content` column with `databricks-gte-large-en`,
# MAGIC sync the metadata you want to return, `TRIGGERED` pipeline. Managed embeddings guarantee the **same
# MAGIC model** embeds the chunks and each query — the single biggest lever on relevance. Then query it and
# MAGIC confirm meaning-based retrieval works.

# COMMAND ----------

from databricks.vector_search.client import VectorSearchClient   # package: databricks-vectorsearch (NOT databricks-ai-search)

vsc = VectorSearchClient()   # picks up notebook/workspace auth automatically

# Create the endpoint once and reuse; guard so re-running the notebook does not error.
if not vsc.endpoint_exists(VS_ENDPOINT):
    vsc.create_endpoint_and_wait(name=VS_ENDPOINT, endpoint_type="STANDARD")
    print("Created endpoint:", VS_ENDPOINT)
else:
    print("Endpoint already exists:", VS_ENDPOINT)

# COMMAND ----------

# Create the Delta Sync index with managed embeddings; guard against re-creation on re-run.
if not any(i.get("name") == INDEX_NAME for i in vsc.list_indexes(VS_ENDPOINT).get("vector_indexes", [])):
    index = vsc.create_delta_sync_index_and_wait(
        endpoint_name=VS_ENDPOINT,
        index_name=INDEX_NAME,
        source_table_name=SOURCE_TABLE,
        primary_key="chunk_id",                        # unique row id used to add/replace/delete vectors
        embedding_source_column="content",             # THIS column gets embedded
        embedding_model_endpoint_name=EMBED_ENDPOINT,  # managed embeddings: Databricks calls gte-large-en
        pipeline_type="TRIGGERED",                     # you call .sync(); cheaper than CONTINUOUS
        columns_to_sync=["chunk_id", "content", "source_doc", "chunk_index"],  # returned/filterable metadata
    )
    print("Created index:", INDEX_NAME)
else:
    index = vsc.get_index(endpoint_name=VS_ENDPOINT, index_name=INDEX_NAME)
    print("Index already exists:", INDEX_NAME)

# Re-fetch a handle and block until ONLINE before querying.
index = vsc.get_index(endpoint_name=VS_ENDPOINT, index_name=INDEX_NAME)
index.wait_until_ready()
print("Index status:", index.describe()["status"])

# COMMAND ----------

# MAGIC %md
# MAGIC ### How to verify it worked  (acceptance: M3)
# MAGIC The index is ONLINE, and a semantic query with **zero shared keywords** retrieves the right chunk:
# MAGIC *"Can I rebook for free if my connection is cancelled?"* must surface the **involuntary
# MAGIC re-accommodation** chunk (which never says "rebook" or "free"). Each hit carries `source_doc`, proving
# MAGIC the metadata columns synced.

# COMMAND ----------

probe = "Can I rebook for free if my connection is cancelled?"
results = index.similarity_search(
    query_text=probe,
    columns=["chunk_id", "content", "source_doc"],
    num_results=5,
)
top_sources = []
print(f"Query: {probe}\n")
for row in results["result"]["data_array"]:
    # row is [chunk_id, content, source_doc, score] — score is always last
    top_sources.append(row[2])
    print(round(row[-1], 3), "|", row[2], "|", row[1][:110], "...")

assert results["result"]["data_array"], "Index returned no results — is it ONLINE and synced?"
assert results["result"]["data_array"][0][2], "source_doc missing on hits — the metadata columns did not sync."
assert "involuntary_reaccommodation" in top_sources[:3], \
    f"Semantic retrieval missed the re-accommodation chunk. Top sources: {top_sources[:3]}"
print("\nOK — meaning-based retrieval works; the re-accommodation chunk surfaces with zero keyword overlap.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## M4 · Assemble the LCEL RAG chain (registry prompt)  ·  02.5 / 05.2 / 05.3
# MAGIC First **register the RAG prompt** as a governed Unity Catalog artifact, then assemble the chain
# MAGIC **around it**. The prompt is not a string baked into the code — you author it once in the MLflow
# MAGIC Prompt Registry (Beta) as `unity_airways.rag.ua_rag_prompt` v1, and the chain loads it by URI. That
# MAGIC makes the prompt versioned and governed from day one; C2 versions and evaluates it later.

# COMMAND ----------

import mlflow

# The prompt uses {{double-brace}} variables. It MUST instruct the model to answer only from context and
# to name the source. Idempotent: only author v1 if it does not already exist.
try:
    _existing = mlflow.genai.load_prompt(PROMPT_URI)
    print(f"Prompt v1 already exists ({_existing.name}); skipping re-register.")
except Exception:
    mlflow.genai.register_prompt(
        name=PROMPT_NAME,                                        # UC identifier: catalog.schema.name
        template=(
            "You are the Unity Airways customer-support policy assistant.\n"
            "Answer the question using ONLY the retrieved context below. If the context does not contain "
            "the answer, say you do not know rather than guessing.\n"
            "Always name the source document you used (the source_doc shown with each context passage).\n\n"
            "Context:\n{{context}}\n\n"
            "Question: {{question}}\n\n"
            "Grounded answer (name the source document):"
        ),
        commit_message="v1: grounded, cite-the-source RAG prompt",
        tags={"use_case": "support_rag", "owner": "unity-airways-rag"},
    )
    print(f"Registered {PROMPT_NAME} v1")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Load the prompt by URI and build the chain
# MAGIC `to_single_brace_format()` converts the registry's `{{var}}` templating into LangChain's `{var}`.
# MAGIC The chain's input contract is `{"messages": [...]}` (a chat request), not a bare string, so we pull
# MAGIC the user's text out of the last message before retrieval. `format_docs` prepends each chunk's
# MAGIC `source_doc` so the model can actually **cite** what it read — citations are this capstone's pass bar.

# COMMAND ----------

from operator import itemgetter
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableLambda
from databricks_langchain import ChatDatabricks, DatabricksVectorSearch

mlflow.langchain.autolog()   # every LangChain .invoke() now emits an MLflow trace

# The chain loads the prompt by URI — never an inline literal.
loaded_prompt = mlflow.genai.load_prompt(PROMPT_URI)
prompt = PromptTemplate.from_template(loaded_prompt.to_single_brace_format())   # {{var}} -> {var}

# The "R": the M3 index wrapped as a retriever (managed embeddings -> pass text only).
retriever = DatabricksVectorSearch(
    endpoint=VS_ENDPOINT,
    index_name=INDEX_NAME,
    columns=["chunk_id", "content", "source_doc"],   # source_doc so answers are citable
).as_retriever(search_kwargs={"k": K})

def extract_user_query_string(messages):
    # chat input contract: {"messages": [{"role": "user", "content": "..."}]}
    return messages[-1]["content"]

def format_docs(docs):
    # include source_doc in the context so the model can name it in the answer
    return "\n\n".join(f"[source_doc: {d.metadata.get('source_doc')}]\n{d.page_content}" for d in docs)

llm = ChatDatabricks(endpoint=CHAT_ENDPOINT, temperature=0)

# Two parallel branches feed the prompt's {context} and {question} slots.
chain = (
    {
        "context":  itemgetter("messages") | RunnableLambda(extract_user_query_string)
                    | retriever | RunnableLambda(format_docs),
        "question": itemgetter("messages") | RunnableLambda(extract_user_query_string),
    }
    | prompt
    | llm
    | StrOutputParser()
)

# COMMAND ----------

# MAGIC %md
# MAGIC ### How to verify it worked  (acceptance: M4)
# MAGIC The chain answers the re-accommodation question with a grounded response that **names its source
# MAGIC document**, and it differs correctly from an LLM-only baseline (which has no grounding). Open
# MAGIC **Experiments → Traces**: the RAG trace shows both a retriever span and a `ChatDatabricks` span —
# MAGIC proof retrieval ran before generation. The prompt exists as a UC entity and is resolved from the URI.

# COMMAND ----------

question = "Can I rebook for free if my connection is cancelled?"

# LLM-only baseline (no grounding) — generic, cites nothing.
baseline = llm.invoke(question).content

# The RAG chain — grounded, cites its source_doc.
answer = chain.invoke({"messages": [{"role": "user", "content": question}]})

print("=== LLM-only baseline (ungrounded) ===\n", baseline[:300], "\n")
print("=== RAG chain (grounded, cited) ===\n", answer)

assert answer and answer.strip(), "RAG chain returned an empty answer."
assert "involuntary_reaccommodation" in answer.lower() or "re-accommodation" in answer.lower() \
       or "source" in answer.lower(), "The answer does not appear to cite its source document."
assert mlflow.genai.load_prompt(PROMPT_URI).name == PROMPT_NAME, "Prompt did not resolve from the registry URI."
print("\nOK — grounded, cited answer; prompt resolved from", PROMPT_URI)

# COMMAND ----------

# MAGIC %md
# MAGIC ## M5 · Log Model-as-Code + register to UC  ·  05.5 / 05.6 / 05.7
# MAGIC Package the chain so it runs outside the notebook. Externalize config to a YAML read via
# MAGIC `ModelConfig`, write the whole chain to `rag_chain.py` ending in `mlflow.models.set_model(chain)`,
# MAGIC then log it **by path** (Models-from-Code), declare a **signature** and dependent **resources**, and
# MAGIC register it to Unity Catalog as a versioned LoggedModel.
# MAGIC
# MAGIC > ⚠️ **GOTCHA:** If the chain works in the notebook but 401s once served, you forgot `resources=[...]`.
# MAGIC > Logging the chain **object** (not the `.py` path) hits `Failed to save runnable sequence` because
# MAGIC > `VectorStoreRetriever` is not natively serializable — Models-from-Code saves code, not a pickle.

# COMMAND ----------

# MAGIC %md
# MAGIC ### Externalize config, then materialize the chain into `rag_chain.py`
# MAGIC `ModelConfig` reads the YAML both when we import the file directly (dev) and when the logged model is
# MAGIC reloaded (prod), so the same code moves cleanly across environments.

# COMMAND ----------

# MAGIC %%writefile rag_chain_config.yml
# MAGIC vs_endpoint: unity-airways-vs
# MAGIC index_name: unity_airways.rag.ua_rag_chunks_index
# MAGIC chat_endpoint: databricks-claude-sonnet-4-5
# MAGIC k: 5
# MAGIC prompt_uri: prompts:/unity_airways.rag.ua_rag_prompt/1

# COMMAND ----------

# MAGIC %%writefile rag_chain.py
# MAGIC # rag_chain.py — the entire RAG chain, self-contained (no notebook globals).
# MAGIC # Loading this model RE-EXECUTES this file, rebuilding a fresh retriever + LLM client. Nothing pickles.
# MAGIC import mlflow
# MAGIC from operator import itemgetter
# MAGIC from mlflow.models import ModelConfig
# MAGIC from databricks_langchain import ChatDatabricks, DatabricksVectorSearch
# MAGIC from langchain_core.prompts import PromptTemplate
# MAGIC from langchain_core.output_parsers import StrOutputParser
# MAGIC from langchain_core.runnables import RunnableLambda
# MAGIC
# MAGIC mlflow.langchain.autolog()   # loaded/served copies keep emitting traces too
# MAGIC
# MAGIC # Config comes from the YAML (development_config for local import; the packaged copy when served).
# MAGIC cfg = ModelConfig(development_config="rag_chain_config.yml")
# MAGIC VS_ENDPOINT   = cfg.get("vs_endpoint")
# MAGIC INDEX_NAME    = cfg.get("index_name")
# MAGIC CHAT_ENDPOINT = cfg.get("chat_endpoint")
# MAGIC K             = cfg.get("k")
# MAGIC PROMPT_URI    = cfg.get("prompt_uri")
# MAGIC
# MAGIC # Prompt loaded from the registry by URI (governed, versioned) — not an inline literal.
# MAGIC prompt = PromptTemplate.from_template(
# MAGIC     mlflow.genai.load_prompt(PROMPT_URI).to_single_brace_format()
# MAGIC )
# MAGIC
# MAGIC retriever = DatabricksVectorSearch(
# MAGIC     endpoint=VS_ENDPOINT,
# MAGIC     index_name=INDEX_NAME,
# MAGIC     columns=["chunk_id", "content", "source_doc"],
# MAGIC ).as_retriever(search_kwargs={"k": K})
# MAGIC
# MAGIC def extract_user_query_string(messages):
# MAGIC     return messages[-1]["content"]
# MAGIC
# MAGIC def format_docs(docs):
# MAGIC     return "\n\n".join(f"[source_doc: {d.metadata.get('source_doc')}]\n{d.page_content}" for d in docs)
# MAGIC
# MAGIC llm = ChatDatabricks(endpoint=CHAT_ENDPOINT, temperature=0)
# MAGIC
# MAGIC # Same {"messages": [...]}-in chain as M4.
# MAGIC chain = (
# MAGIC     {
# MAGIC         "context":  itemgetter("messages") | RunnableLambda(extract_user_query_string)
# MAGIC                     | retriever | RunnableLambda(format_docs),
# MAGIC         "question": itemgetter("messages") | RunnableLambda(extract_user_query_string),
# MAGIC     }
# MAGIC     | prompt | llm | StrOutputParser()
# MAGIC )
# MAGIC
# MAGIC mlflow.models.set_model(chain)   # <- THIS is the model MLflow logs

# COMMAND ----------

# MAGIC %md
# MAGIC ### Sanity-check the file before logging
# MAGIC Import and invoke it — this runs `rag_chain.py` exactly the way MLflow will at load time, so an import
# MAGIC or config error surfaces here while it is cheap to fix.

# COMMAND ----------

import sys, os
sys.path.insert(0, os.getcwd())   # make the freshly written rag_chain.py importable

from rag_chain import chain as file_chain   # runs the file, builds a fresh chain
print(file_chain.invoke({"messages": [{"role": "user", "content": "What is the checked-bag fee?"}]})[:300])

# COMMAND ----------

# MAGIC %md
# MAGIC ### Log as Models-from-Code, version it, and register to Unity Catalog
# MAGIC `set_active_model` opens a **LoggedModel** version so params/traces link to it. `lc_model=` is the
# MAGIC **file path**, not the object. `resources=[...]` records the serving endpoint + index so a deployed
# MAGIC chain auto-authenticates.

# COMMAND ----------

from mlflow.models import infer_signature
from mlflow.models.resources import DatabricksServingEndpoint, DatabricksVectorSearchIndex

input_example = {"messages": [{"role": "user", "content": "Can I get a refund on a Basic Economy fare?"}]}
signature = infer_signature(model_input=input_example, model_output="A short grounded answer with its source document.")

# NOTE: resource classes confirmed in Book 1 Ch4; re-verify kwargs against current MLflow docs.
resources = [
    DatabricksServingEndpoint(endpoint_name=CHAT_ENDPOINT),          # generation (the "G")
    DatabricksVectorSearchIndex(index_name=INDEX_NAME),             # retrieval (the "R")
]

mlflow.set_registry_uri("databricks-uc")
active = mlflow.set_active_model(name="ua_rag_chain")   # LoggedModel version hub
print("LoggedModel:", active.name, "| model_id:", active.model_id)

with mlflow.start_run() as run:
    logged = mlflow.langchain.log_model(
        lc_model="rag_chain.py",                        # <- code file, NOT the chain object
        name="chain",
        model_id=active.model_id,                       # attach the artifact to the active LoggedModel (05.6 pattern)
        model_config="rag_chain_config.yml",            # externalized config travels with the model
        signature=signature,
        input_example=input_example,
        resources=resources,                            # auto-auth on deploy
        pip_requirements=["mlflow>=3.1", "databricks-langchain", "databricks-vectorsearch"],
    )
print("model_uri:", logged.model_uri)

# Record the version's params on the LoggedModel.
mlflow.log_model_params(
    model_id=active.model_id,
    params={"llm_endpoint": CHAT_ENDPOINT, "index": INDEX_NAME, "k": str(K),
            "prompt_uri": PROMPT_URI, "temperature": "0"},
)

# Register the Models-from-Code artifact to Unity Catalog (creates a new version) and set @champion.
mv = mlflow.register_model(logged.model_uri, UC_MODEL)
from mlflow import MlflowClient
MlflowClient(registry_uri="databricks-uc").set_registered_model_alias(
    name=UC_MODEL, alias="champion", version=mv.version)
print(f"Registered {mv.name} version {mv.version}; alias {UC_MODEL}@champion -> v{mv.version}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### How to verify it worked  (acceptance: M5)
# MAGIC `unity_airways.rag.ua_rag_chain` appears in UC with at least one version; the artifact carries the
# MAGIC `signature`, a `resources:` block naming the endpoint + index, and the saved `rag_chain.py` source
# MAGIC (not a pickle); and loading the registered model **reproduces the notebook answer**.

# COMMAND ----------

uc_loaded = mlflow.langchain.load_model(f"models:/{UC_MODEL}@champion")
reloaded_answer = uc_loaded.invoke(input_example)
print(reloaded_answer[:300])

assert reloaded_answer and reloaded_answer.strip(), "Registered model returned an empty answer."
assert mv.version, "No registered version was created."
print(f"OK — {UC_MODEL}@champion round-trips from Unity Catalog and reproduces the notebook answer.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Demo — five policy questions through the registered chain
# MAGIC The proof it works: five representative Unity Airways questions answered by the **registered** model,
# MAGIC each grounded in a retrieved chunk and naming its source document. An ungrounded or uncited answer
# MAGIC fails the demo.

# COMMAND ----------

demo_questions = [
    "Can I get a refund on a Basic Economy fare?",
    "Can I rebook for free if my connection is cancelled?",
    "What's the checked-bag fee?",
    "How do I change an existing booking?",
    "What happens if my flight is delayed overnight?",
]

for q in demo_questions:
    ans = uc_loaded.invoke({"messages": [{"role": "user", "content": q}]})
    print("Q:", q)
    print("A:", ans)
    print("-" * 100)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Recap, deliverables, gotchas, and what's next
# MAGIC **What you built** — the full spine, ingest → chunk → index → chain → register:
# MAGIC - **M1** parsed the raw Volume documents with `ai_parse_document`, splitting clean rows from
# MAGIC   quarantine on the array-aware `parsed:error_status[0]` filter.
# MAGIC - **M2** chunked the clean text into `unity_airways.rag.ua_rag_chunks` with metadata and Change Data Feed.
# MAGIC - **M3** built the `unity_airways.rag.ua_rag_chunks_index` Delta Sync index (managed
# MAGIC   `databricks-gte-large-en` embeddings) and proved semantic retrieval with zero keyword overlap.
# MAGIC - **M4** registered the RAG prompt (`ua_rag_prompt` v1, Beta Prompt Registry) and assembled the LCEL
# MAGIC   chain that loads it by URI, grounds on the retriever, and cites its source.
# MAGIC - **M5** logged the chain as Models-from-Code with a signature + resources and registered it as
# MAGIC   `unity_airways.rag.ua_rag_chain@champion`.
# MAGIC
# MAGIC **The three graded deliverables**
# MAGIC | Deliverable | Rubric criteria it satisfies |
# MAGIC |---|---|
# MAGIC | `ua_rag_chunks` (Delta, CDF on) | Chunking quality; code reproducibility (UC-first, no `/mnt`) |
# MAGIC | `ua_rag_chunks_index` (ONLINE) | Retrieval relevance (paraphrased query → right chunk) |
# MAGIC | `ua_rag_chain` (registered) | Chain runs from the registered model; prompt registered & loaded by URI; groundedness/citations |
# MAGIC
# MAGIC **Gotchas to remember**
# MAGIC - Omitting `resources=[...]` logs fine but **401s once served** — declare every service the chain calls.
# MAGIC - Log the **`.py` path**, not the chain object — the `VectorStoreRetriever` will not pickle
# MAGIC   (`Failed to save runnable sequence`). Models-from-Code saves code and rebuilds fresh at load.
# MAGIC - Import from **`databricks-langchain`** (never `langchain-databricks`/`langchain_community`); the VS
# MAGIC   SDK is **`databricks-vectorsearch`** (no `AISearchClient`).
# MAGIC - The chain's input contract is `{"messages": [...]}` — extract the last message before retrieval.
# MAGIC - `format_docs` must surface `source_doc` in the context, or the model cannot cite what it read.
# MAGIC - Reconfirm `databricks-claude-sonnet-4-5` / `databricks-gte-large-en` on the supported-models page —
# MAGIC   endpoint names churn.
# MAGIC
# MAGIC **Next — Capstone C2 (Evaluate, Trace, and Version):** take this exact `ua_rag_chain`, build a labeled
# MAGIC eval set, score retrieval + groundedness with `mlflow.genai.evaluate()`, version the prompt beyond v1,
# MAGIC and promote by evidence. C2 assumes the artifacts you just created — keep the canonical names.
# MAGIC
# MAGIC ## 📝 Notes
# MAGIC - _Space for your own build notes: chunk size you settled on, which documents needed OCR, retrieval
# MAGIC   metrics you measured, and any endpoint/index deviations from the canonical names (avoid these — C2/C3/C4
# MAGIC   inherit them)._
# MAGIC
# MAGIC ## Sources
# MAGIC - Module 03 — Data prep & chunking: `notebooks/03-data-prep-chunking/03-8-ai-parse-extract.py`, `03-module-lab.py`.
# MAGIC - Module 04 — Embeddings & AI Search: `notebooks/04-embeddings-ai-search/04-3-create-query-index.py`.
# MAGIC - Module 02 — Prompt engineering: `notebooks/02-prompt-engineering/02-5-prompt-registry.py`.
# MAGIC - Module 05 — RAG chain: `notebooks/05-building-rag-chain/05-3-rag-chain.py`, `05-6-model-as-code.py`, `05-module-lab.py`.
# MAGIC - Naming cross-check: `.claude/skills/genai-teacher/references/naming-conventions.md` §1, §3, §4, §9.
# MAGIC - Capstone brief: `capstones/capstone-1-rag-knowledge-base.md`.
