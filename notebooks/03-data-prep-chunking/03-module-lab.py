# Databricks notebook source
# MAGIC %md
# MAGIC # Module 03 lab — extract → filter → chunk → Delta → retrieval check
# MAGIC **Roadmap:** Module 03 (Data prep and chunking for RAG) · consolidated hands-on lab · [Hands-on]
# MAGIC
# MAGIC One runnable, end-to-end lab that walks the module's hands-on topics **in order** and lands the same
# MAGIC embed-ready table the pipeline (`03-9-sdp-ingestion.py`) produces:
# MAGIC
# MAGIC | Step | Topic | What you do |
# MAGIC |---|---|---|
# MAGIC | 1 | **03.4** | Extract text — choose the right package, or `ai_parse_document` |
# MAGIC | 2 | **03.5** | Content filtering — strip noise, drop duplicate boilerplate |
# MAGIC | 3 | **03.2 / 03.3** | Chunk — fixed vs token-precise vs semantic |
# MAGIC | 4 | **03.6** | Convert to a governed Delta table |
# MAGIC | 5 | **03.7** | Quick retrieval-quality sanity check (precision / MRR) |
# MAGIC
# MAGIC Unlike `03-9-sdp-ingestion.py` (a *pipeline* file), **this notebook runs cell-by-cell** on serverless or a
# MAGIC DBR-ML runtime. To keep it self-contained it works on a few in-notebook sample documents; a
# MAGIC `%md` note shows exactly where to swap in real files parsed by `ai_parse_document`.
# MAGIC
# MAGIC ## Prerequisites (read before running)
# MAGIC - **Compute:** **serverless notebook/job**, or a **DBR ML runtime** (15.4 LTS ML or later is a safe floor).
# MAGIC   The optional `ai_parse_document` path in Step 1 needs **Databricks Runtime 17.3+** or a **Pro/Serverless
# MAGIC   SQL warehouse** (on serverless the environment version must be **≥ 3**, which enables VARIANT) — not
# MAGIC   **SQL Warehouse Classic**. Serverless isn't strictly required, just the simplest default.
# MAGIC - **Unity Catalog (learner-set identifiers):** a catalog + schema you can write to — this lab uses catalog
# MAGIC   **`unity_airways`**, schema **`rag`**. A Volume is only needed for the optional real-file path.
# MAGIC - **Serving endpoint:** **`databricks-gte-large-en`** (Foundation Model API, 8192-token context, 1024-dim)
# MAGIC   for semantic chunking (Step 3) and the retrieval check (Step 5). Confirm it under **Serving → supported
# MAGIC   models** for your workspace.
# MAGIC - **Libraries:** installed in the next cell — `langchain-text-splitters`, `langchain-experimental`,
# MAGIC   `databricks-langchain`, `tiktoken`.
# MAGIC - **Secrets:** none. Embeddings use the in-platform endpoint, so no OpenAI key is required.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 0. Install libraries
# MAGIC `langchain-text-splitters` (fixed/token splitters), `langchain-experimental` (`SemanticChunker`),
# MAGIC `databricks-langchain` (`DatabricksEmbeddings`), and `tiktoken` (token counting). Restart Python so the
# MAGIC fresh installs are importable.

# COMMAND ----------

# MAGIC %pip install -U langchain-text-splitters langchain-experimental databricks-langchain tiktoken
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Configuration — set your governed location
# MAGIC Edit these to a catalog/schema you own. `EMBED_ENDPOINT` must be a Foundation Model embedding endpoint.

# COMMAND ----------

CATALOG        = "unity_airways"          # a catalog you can write to
SCHEMA         = "rag"                     # a schema you can write to
EMBED_ENDPOINT = "databricks-gte-large-en" # 8192-token context, 1024-dim (verify under Serving)

FQ          = f"{CATALOG}.{SCHEMA}"
CHUNK_TABLE = f"{FQ}.ua_rag_chunks"        # canonical embed-ready table (same as the SDP pipeline)

# Create the schema if you have privileges (the catalog must already exist).
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {FQ}")
print("Tables prefix :", FQ)
print("Chunk table   :", CHUNK_TABLE)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 1 · 03.4 — Get clean text out of the documents
# MAGIC Unity Airways has three document shapes: a customer **FAQ**, the dense **Conditions of Carriage**, and a
# MAGIC recorded **support-call transcript**. Before chunking we need clean text from each.
# MAGIC
# MAGIC **Two extraction paths — pick by control vs scale:**
# MAGIC - **Open-source libraries (full local control):** text-first with `pdfplumber`, OCR fallback with
# MAGIC   `pytesseract`. The function below is the book's layered pattern (03.4). It is defined for reference; we
# MAGIC   do not run it here because the lab ships no PDF files.
# MAGIC - **`ai_parse_document` (scale, SQL-native):** one function parses PDF/image/Office files straight from a
# MAGIC   UC Volume, OCR included. That is the recommended Databricks path and the full walkthrough is in
# MAGIC   `03-8-ai-parse-extract.py`.
# MAGIC
# MAGIC To stay runnable end-to-end, the rest of the lab uses in-notebook **sample documents** that stand in for
# MAGIC extractor output — deliberately messy, with the noise real documents carry.

# COMMAND ----------

# Reference only: layered text-first / OCR-fallback extraction (book Example 3-10, condensed).
# Not executed here — shown so you can lift it into a job that has real PDFs.
def extract_text_from_pdf(pdf_path):
    import pdfplumber, pytesseract
    text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:                      # digital PDF: keep the clean text layer
                text += page_text + "\n"
        if not text.strip():                   # scanned PDF: no text layer -> OCR fallback
            text = "\n".join(
                pytesseract.image_to_string(page.to_image().original)
                for page in pdf.pages)
    return text

print("extract_text_from_pdf defined (reference). Lab continues on sample documents below.")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Optional — the real Databricks path (needs serverless + a populated Volume)
# MAGIC If you have documents in a Volume, this is the scalable extractor. It mirrors `03-8-ai-parse-extract.py`.
# MAGIC Leave it commented unless your Volume is populated.

# COMMAND ----------

# --- Uncomment to parse real files instead of the sample text ---
# VOLUME_PATH = "/Volumes/unity_airways/rag/landing/policies/"
# parsed = (
#     spark.read.format("binaryFile").load(VOLUME_PATH)
#     .selectExpr(
#         "_metadata.file_path AS source_doc",
#         "ai_parse_document(content) AS parsed",
#     )
# )
# clean_text_df = (
#     parsed.filter("parsed:error_status[0] IS NULL")   # array-aware: keep clean parses only
#     .selectExpr(
#         "source_doc",
#         """concat_ws('\\n',
#              transform(variant_get(parsed, '$.document.elements', 'ARRAY<VARIANT>'),
#                        e -> variant_get(e, '$.content', 'STRING'))) AS raw_text""",
#     )
# )
# raw_docs = {r["source_doc"]: r["raw_text"] for r in clean_text_df.collect()}

# COMMAND ----------

# Sample "extractor output" — three Unity Airways document types, complete with realistic noise.
raw_docs = {
    "faq": """<html><nav>Home | Book | Manage | Help</nav>
Last updated: 2026-03-01
Q: How do I reset my booking password?
A: Go to Manage Booking, choose "Forgot password", and follow the email link. The link expires in 30 minutes.
Q: How do I add a checked bag after booking?
A: In Manage Booking, open Baggage and add bags up to 4 hours before departure. Prices rise at the airport.
Q: Can I change the name on my ticket?
A: Minor spelling fixes are free within 24 hours of booking. Full name changes are not permitted; you must rebook.
Page 1 of 1
This document is confidential and proprietary to Unity Airways.""",

    "conditions_of_carriage": """UNITY AIRWAYS — CONDITIONS OF CARRIAGE
Last updated: 2026-02-14
Section 4. Refunds.
4.1 Basic Economy fares are non-refundable except where required by law. A Basic Economy ticket cancelled
within 24 hours of purchase, and at least 7 days before departure, is eligible for a full refund under the
24-hour flexible booking policy defined in Section 2.3.
4.2 Refundable fares (Premium, Business, First) may be refunded to the original form of payment, less any
applicable service fee, provided the request is made before the scheduled departure of the first segment.
4.3 A refund for a missed connection caused by Unity Airways is provided when the delay exceeds the threshold
in Section 4.4; refunds are not available where the missed connection results from the passenger's failure to
observe published minimum connection times.
Page 12 of 88
This document is confidential and proprietary to Unity Airways.""",

    "support_transcript": """Agent: Thanks for calling Unity Airways, this is Priya. How can I help?
Caller: Hi, I booked a flight last week and my plans changed. First though, do you know if it'll rain in Denver?
Agent: I can't check weather, but let's look at your booking. I see a Basic Economy fare for Friday.
Caller: Right. Can I get money back if I cancel?
Agent: Basic Economy is non-refundable, but since you booked eight days ago you're outside the 24-hour window,
so a refund isn't available. You can cancel for travel credit, minus the fare difference, if you'd prefer.
Caller: Okay. And separately, my checked bag was delayed last month, who do I email about that?
Agent: Baggage claims go to baggage-support at unityairways dot com; include your file reference number.
Caller: Great, thank you.
Agent: You're welcome, safe travels.""",
}

for k, v in raw_docs.items():
    print(f"{k:>24} : {len(v):>4} chars")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 2 · 03.5 — Filter noise and redundancy
# MAGIC If the same nav bar, "Last updated" line, and confidentiality disclaimer appear in every document, they
# MAGIC land in nearly every chunk and retrieval starts matching on boilerplate instead of the answer. We remove:
# MAGIC - **Noise** — HTML tags, page numbers, timestamps.
# MAGIC - **Redundancy** — repeated disclaimers / nav lines, and duplicate lines within a document.
# MAGIC
# MAGIC > 💡 **TIP:** Eyeball a few source documents before writing removal rules — noise is org-specific, and a
# MAGIC > regex tuned to one set can silently delete real content in another. Clean conservatively; check recall.

# COMMAND ----------

import re

def clean_text(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)                                   # strip HTML / nav markup
    text = re.sub(r"(?i)this document is confidential.*?(\n|$)", "", text) # repeated disclaimer
    text = re.sub(r"(?i)page \d+ of \d+", "", text)                        # page numbers
    text = re.sub(r"(?i)last updated:.*?(\n|$)", "", text)                 # timestamps
    # de-duplicate identical non-empty lines while preserving order (redundancy removal)
    seen, out = set(), []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if s not in seen:
            seen.add(s)
            out.append(s)
    return "\n".join(out)

clean_docs = {doc_id: clean_text(t) for doc_id, t in raw_docs.items()}

# COMMAND ----------

# MAGIC %md
# MAGIC ### How to verify it worked
# MAGIC Diff raw vs cleaned on one document — boilerplate should be gone and the substance intact.

# COMMAND ----------

print("=== BEFORE (faq, first 320 chars) ===")
print(raw_docs["faq"][:320])
print("\n=== AFTER (faq) ===")
print(clean_docs["faq"])
print("\nchar counts:", {k: (len(raw_docs[k]), len(clean_docs[k])) for k in raw_docs})

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 3 · 03.2 / 03.3 — Chunk the text
# MAGIC No single strategy fits all three documents. We demo three splitters, then choose per document type:
# MAGIC - **Fixed / recursive** (`RecursiveCharacterTextSplitter`) — the workhorse; paragraph→line→sentence→word
# MAGIC   with a sliding-window overlap.
# MAGIC - **Token-precise** (`TokenTextSplitter`) — sizes against the *token* budget the embedding model measures.
# MAGIC - **Semantic** (`SemanticChunker` + `DatabricksEmbeddings`) — splits where meaning drifts; best for the
# MAGIC   drifting support transcript.
# MAGIC
# MAGIC > ⚠️ **GOTCHA:** The book's semantic examples use LlamaIndex + `OpenAIEmbedding()`. On Databricks, point
# MAGIC > the embedder at the governed endpoint via `DatabricksEmbeddings(endpoint="databricks-gte-large-en")` —
# MAGIC > no external key, everything stays in-platform.

# COMMAND ----------

from langchain_text_splitters import RecursiveCharacterTextSplitter, TokenTextSplitter

# Recursive/fixed: ~1200 chars (~300 tokens) with a 200-char sliding-window overlap.
recursive_splitter = RecursiveCharacterTextSplitter(
    chunk_size=1200, chunk_overlap=200,
    separators=["\n\n", "\n", ". ", " ", ""],
)
# Token-precise: exact token budgeting for FAQ-sized, high-precision chunks.
token_splitter = TokenTextSplitter(chunk_size=180, chunk_overlap=30)

faq_chunks   = token_splitter.split_text(clean_docs["faq"])                 # small facts → token-precise
coc_chunks   = recursive_splitter.split_text(clean_docs["conditions_of_carriage"])  # dense policy → recursive+overlap
print("faq token-chunks           :", len(faq_chunks))
print("conditions recursive-chunks:", len(coc_chunks))

# COMMAND ----------

# MAGIC %md
# MAGIC ### Semantic chunking for the drifting transcript
# MAGIC The support call jumps from weather to refunds to baggage with no clean breaks. `SemanticChunker` embeds
# MAGIC sentences and starts a new chunk when consecutive sentences drift apart in vector space.

# COMMAND ----------

from langchain_experimental.text_splitter import SemanticChunker
from databricks_langchain import DatabricksEmbeddings

embeddings = DatabricksEmbeddings(endpoint=EMBED_ENDPOINT)   # governed, key-free
semantic_splitter = SemanticChunker(embeddings, breakpoint_threshold_type="percentile")

transcript_docs = semantic_splitter.create_documents([clean_docs["support_transcript"]])
transcript_chunks = [d.page_content for d in transcript_docs]
print("transcript semantic-chunks :", len(transcript_chunks))
for i, c in enumerate(transcript_chunks):
    print(f"  [{i}] {c[:90]}...")

# COMMAND ----------

# MAGIC %md
# MAGIC ### How to verify it worked (size check against the 8192 ceiling)
# MAGIC `databricks-gte-large-en` truncates anything over 8192 tokens at embed time, so no chunk should get close.
# MAGIC
# MAGIC `cl100k_base` is an OpenAI tokenizer used only as a *close proxy* — gte-large-en's true tokenizer differs, but chunks (~180–300 tokens) sit far under the 8192 ceiling, so the assertion is safe regardless.

# COMMAND ----------

import tiktoken
enc = tiktoken.get_encoding("cl100k_base")   # close proxy for token budgeting

all_chunks_preview = faq_chunks + coc_chunks + transcript_chunks
lengths = [len(enc.encode(c)) for c in all_chunks_preview]
print("max tokens:", max(lengths), "| avg tokens:", round(sum(lengths) / len(lengths)))
assert max(lengths) < 8192, "chunk exceeds gte-large-en context window; it would be truncated"

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 4 · 03.6 — Convert to a governed Delta table
# MAGIC Assemble every chunk into one row with its metadata (`source_doc`, `chunk_index`, `ingested_at`) and a
# MAGIC deterministic `chunk_id`. This is the **canonical embed-ready table** — the same
# MAGIC `unity_airways.rag.ua_rag_chunks` the SDP pipeline writes, with the same schema.
# MAGIC
# MAGIC > 📌 **IMPORTANT:** Keep source/index metadata on every chunk. It powers metadata-filtered retrieval and
# MAGIC > lets you trace a bad answer back to the exact chunk. We also enable **Change Data Feed** so Module 04's
# MAGIC > AI Search **Delta Sync** index re-embeds only changed rows.

# COMMAND ----------

from pyspark.sql import functions as F

# One (doc_id, chunk_index, content) tuple per chunk, across all three document types.
rows = []
for doc_id, chunks in [
    ("faq", faq_chunks),
    ("conditions_of_carriage", coc_chunks),
    ("support_transcript", transcript_chunks),
]:
    for idx, content in enumerate(chunks):
        rows.append((doc_id, idx, content))

chunks_df = (
    spark.createDataFrame(rows, ["source_doc", "chunk_index", "content"])
    .withColumn("chunk_id",
                F.sha2(F.concat_ws("::", "source_doc", F.col("chunk_index").cast("string")), 256))
    .withColumn("ingested_at", F.current_timestamp())
    .select("chunk_id", "content", "source_doc", "chunk_index", "ingested_at")   # canonical column order
)

(chunks_df.write.format("delta").mode("overwrite")
    .option("overwriteSchema", "true")
    .saveAsTable(CHUNK_TABLE))

# Delta Sync indexes (Module 04) require Change Data Feed on the source table.
spark.sql(f"ALTER TABLE {CHUNK_TABLE} SET TBLPROPERTIES (delta.enableChangeDataFeed = true)")
print("Wrote:", CHUNK_TABLE)

# COMMAND ----------

# MAGIC %md
# MAGIC ### How to verify it worked
# MAGIC Row count > 0, ids unique, content non-empty, metadata populated.

# COMMAND ----------

spark.sql(f"""
SELECT count(*) AS chunks,
       count(DISTINCT chunk_id) AS unique_ids,
       count(DISTINCT source_doc) AS docs,
       min(length(content)) AS min_chars
FROM {CHUNK_TABLE}
""").display()

spark.sql(f"SELECT chunk_id, source_doc, chunk_index, left(content, 90) AS preview FROM {CHUNK_TABLE} ORDER BY source_doc, chunk_index").display()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 5 · 03.7 — Quick retrieval-quality sanity check
# MAGIC The full vector index is Module 04. But we can sanity-check the chunks **now**, offline, without an index:
# MAGIC embed every chunk with the same endpoint, embed a test query, rank chunks by cosine similarity, and score
# MAGIC the ranking with **precision@k** and **MRR** against a hand-labeled relevant chunk.
# MAGIC
# MAGIC This answers the only question that matters here: *does one good chunk actually surface for a real query?*

# COMMAND ----------

import numpy as np

# Pull chunks back deterministically so ids line up with vectors.
pdf = spark.table(CHUNK_TABLE).orderBy("source_doc", "chunk_index").toPandas()
chunk_texts = pdf["content"].tolist()
chunk_ids   = pdf["chunk_id"].tolist()

# Embed all chunks + the query with the governed endpoint.
chunk_vecs = np.array(embeddings.embed_documents(chunk_texts))
query = "Can I get a refund on a Basic Economy fare?"
q_vec = np.array(embeddings.embed_query(query))

# Cosine similarity, then rank.
def cosine(mat, vec):
    mat_n = mat / (np.linalg.norm(mat, axis=1, keepdims=True) + 1e-12)
    vec_n = vec / (np.linalg.norm(vec) + 1e-12)
    return mat_n @ vec_n

scores = cosine(chunk_vecs, q_vec)
order  = np.argsort(-scores)   # highest similarity first

print(f"Query: {query}\n")
for rank, i in enumerate(order[:3], start=1):
    print(f"#{rank}  score={scores[i]:.3f}  [{pdf.iloc[i]['source_doc']}#{pdf.iloc[i]['chunk_index']}]")
    print(f"     {chunk_texts[i][:140]}...\n")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Score the ranking (precision@k and MRR)
# MAGIC We mark the Conditions-of-Carriage refund chunk as the gold-relevant one (it holds the actual Basic
# MAGIC Economy refund rule), then measure how the ranking did. MRR rewards putting the right chunk at the top —
# MAGIC the model usually only sees the first few results.

# COMMAND ----------

# Gold label: the chunk(s) that truly answer the query. Here: the Basic Economy refund rule.
relevant_ids = {
    cid for cid, txt in zip(chunk_ids, chunk_texts)
    if "basic economy" in txt.lower() and "refund" in txt.lower()
}
assert relevant_ids, "No gold chunk matched — check the sample data / cleaning."

k = 3
top_k_ids = [chunk_ids[i] for i in order[:k]]
precision_at_k = sum(1 for cid in top_k_ids if cid in relevant_ids) / k

# MRR: reciprocal rank of the FIRST relevant chunk in the full ranking.
rr = 0.0
for rank, i in enumerate(order, start=1):
    if chunk_ids[i] in relevant_ids:
        rr = 1.0 / rank
        break

print(f"relevant chunks : {len(relevant_ids)}")
print(f"precision@{k}     : {precision_at_k:.2f}")
print(f"MRR             : {rr:.2f}")
print("\nReading it: MRR = 1.00 means the refund chunk ranked #1 — chunking + cleaning are working for this "
      "query. If it were low, revisit chunk size/overlap (03.3) or filtering (03.5) and re-measure.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Recap, gotchas and next step
# MAGIC **What you built**
# MAGIC - Cleaned three messy document types (03.4 → 03.5)
# MAGIC - Chunked each with the fitting strategy — token-precise FAQ, recursive+overlap policy, semantic transcript (03.2/03.3)
# MAGIC - Landed the canonical **`unity_airways.rag.ua_rag_chunks`** Delta table with metadata + Change Data Feed (03.6)
# MAGIC - Sanity-checked retrieval offline with precision@k and MRR (03.7)
# MAGIC
# MAGIC **Gotchas to remember**
# MAGIC - Match the chunking strategy to the document; do not use one splitter for everything.
# MAGIC - Target ~200–500 tokens, well under the 8192 ceiling — oversized chunks blur the embedding (semantic dilution).
# MAGIC - Point semantic chunking at `databricks-gte-large-en`, not OpenAI keys.
# MAGIC - Write to a governed **UC table** (not a DBFS mount) and enable Change Data Feed for the Delta Sync index.
# MAGIC - When parsing real files, route failures on the **array** `parsed:error_status[0]`, never a scalar `error`.
# MAGIC
# MAGIC **Next:** Module 04 builds the AI Search index on this table.
# MAGIC (For the production, incremental version of this flow, see `03-9-sdp-ingestion.py`.)
