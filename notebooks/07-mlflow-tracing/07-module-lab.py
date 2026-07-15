# Databricks notebook source
# MAGIC %md
# MAGIC # Module 07 lab — MLflow Tracing for the Unity Airways RAG chain
# MAGIC **Roadmap:** Module 07 (MLflow Tracing and observability) · Topics 07.1–07.5 · ★ 07.2–07.3 cornerstone · [Theory + Hands-on]
# MAGIC
# MAGIC One runnable, end-to-end lab over the module's topics, in order, on the Module 05 RAG chain.
# MAGIC You turn on tracing, read the automated trace, add your own spans, query traces at scale, and
# MAGIC close with the trace-first discipline that seeds Module 08 evaluation.
# MAGIC
# MAGIC | Step | Topic | What you do |
# MAGIC |---|---|---|
# MAGIC | 1 | **07.1** | Concepts — `Trace = TraceInfo + TraceData`; nested `Span`s; the special `RETRIEVER` span |
# MAGIC | 2 | **07.2** ★ | Automated tracing — `mlflow.langchain.autolog()`, rebuild the Module 05 chain, one `invoke` = one trace |
# MAGIC | 3 | **07.3** ★ | Manual tracing — `@mlflow.trace`, `mlflow.start_span(...)`, combine auto + manual under one root |
# MAGIC | 4 | **07.4** | Querying traces — `mlflow.search_traces(...)` → pandas DataFrame; filter by status / tags / time |
# MAGIC | 5 | **07.5** | Trace-first development — instrument from the first working path; dev traces seed evaluation |
# MAGIC
# MAGIC The combined cornerstone deep-dive for Steps 2–3 is `modules/07-mlflow-tracing/tracing.md`; this lab
# MAGIC reuses the same Module 04 index, Module 05 chain shape, and canonical names.
# MAGIC
# MAGIC ## Prerequisites (read before running)
# MAGIC - **Compute:** **serverless notebook/job**, or a **DBR ML runtime** (15.4 LTS ML or later is a safe floor).
# MAGIC   > ⚠️ **Serverless requires explicit autolog enablement.** GenAI autologging is **not** auto-enabled on
# MAGIC   > serverless — you must call `mlflow.<library>.autolog()` yourself for every integration you want traced
# MAGIC   > (see Step 2). On classic ML runtimes some flavors auto-enable, but calling it explicitly is the portable habit.
# MAGIC - **MLflow:** **≥ 3.1** is required — MLflow 3 tracing, `SpanType`, `mlflow.entities.Document`, and
# MAGIC   `set_active_model`/LoggedModel are all MLflow 3 features exercised here.
# MAGIC - **Vector Search index (Module 04):** `unity_airways.rag.ua_rag_chunks_index` must be **ONLINE** on endpoint
# MAGIC   **`unity-airways-vs`** (built over `content`, keyed on `chunk_id`, with `source_doc` synced). This lab
# MAGIC   consumes it; it does not rebuild it.
# MAGIC - **Chat serving endpoint:** **`databricks-claude-sonnet-4-5`** (Foundation Model API). Endpoint names churn —
# MAGIC   confirm on the current supported-models page before hard-coding it.
# MAGIC - **Experiment:** a path you can write to (Step 0 `EXPERIMENT_PATH`). Traces attach to the active experiment;
# MAGIC   `mlflow.set_active_model(...)` links them to a **LoggedModel** version (Module 06).
# MAGIC - **Secrets:** none. Managed embeddings and workspace auth need no external key.
# MAGIC - **Learner-set identifiers:** edit `CATALOG` / `SCHEMA` / `VS_ENDPOINT` / `CHAT_ENDPOINT` / `EXPERIMENT_PATH` in Step 0.
# MAGIC
# MAGIC > 📌 **The whole module in two moves:** turn on **`autolog()`** to get the framework spans for free, then
# MAGIC > add **manual spans** (`@mlflow.trace` for a function, `mlflow.start_span` for a block) for the code you wrote.
# MAGIC > MLflow merges both into one trace automatically — you never wire parent to child by hand.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 0. Install libraries and set variables
# MAGIC `databricks-langchain` (`ChatDatabricks` + `DatabricksVectorSearch`), `databricks-vectorsearch` (the
# MAGIC underlying index client), and `mlflow[databricks]>=3.1` (tracing). Restart Python so the fresh installs import.

# COMMAND ----------

# MAGIC %pip install -U "mlflow[databricks]>=3.1" databricks-langchain databricks-vectorsearch
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

CATALOG       = "unity_airways"                            # a catalog you can read from
SCHEMA        = "rag"                                      # the RAG schema from Modules 03/04
VS_ENDPOINT   = "unity-airways-vs"                         # Vector Search endpoint (from Module 04)
INDEX_NAME    = f"{CATALOG}.{SCHEMA}.ua_rag_chunks_index"  # the Module 04 index
CHAT_ENDPOINT = "databricks-claude-sonnet-4-5"            # confirm on the supported-models page

# Learner-set: an experiment path you can write to (usually your own /Users/<you> path).
EXPERIMENT_PATH = "/Users/sourav.banerjee@databricks.com/unity_airways_rag"

# The running example — a policy question the assistant has answered confidently and WRONG.
QUESTION = "Can I get a refund on a Basic Economy fare?"

print("Index         :", INDEX_NAME)
print("VS endpoint   :", VS_ENDPOINT)
print("Chat endpoint :", CHAT_ENDPOINT)
print("Experiment    :", EXPERIMENT_PATH)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 1 · 07.1 — Tracing concepts: Trace, Span, and the special RETRIEVER span  ·  [Theory]
# MAGIC A GenAI app is not one function you can `print()` your way through — it is a tree of calls across
# MAGIC services (retriever → prompt → model). **Tracing** captures that whole tree, per request, with the
# MAGIC parent/child relationships intact. Logging captures discrete *events*; tracing captures the *journey*.
# MAGIC
# MAGIC - A **Trace** is the end-to-end record of one request. Internally **`Trace = TraceInfo + TraceData`**:
# MAGIC   - **`TraceInfo`** — metadata about the whole trace: experiment id, start time, duration, **status**
# MAGIC     (`OK` / `ERROR` / `IN_PROGRESS`), and custom **tags**. This is what you search on later (Step 4).
# MAGIC   - **`TraceData`** — a list of **`Span`** objects linked in a parent–child hierarchy.
# MAGIC - A **`Span`** captures one step: its **inputs**, **outputs**, **attributes** (arbitrary key/values),
# MAGIC   and **events**. Spans nest to form the request tree.
# MAGIC - **Span types** (`CHAIN`, `LLM`, `CHAT_MODEL`, `PARSER`, `RETRIEVER`, `RERANKER`, …) mostly organize
# MAGIC   spans and pick UI icons — **except `RETRIEVER`**, which has a required output schema so retrieved
# MAGIC   documents render as documents *and* can be scored by evaluation (Module 08). Get that one right.
# MAGIC - Tracing is **OpenTelemetry-compatible** with GenAI semantic conventions, so it slots into standard tooling.
# MAGIC
# MAGIC > 📌 **IMPORTANT:** The RETRIEVER span is the one Module 08 evaluation reads retrieved context from.
# MAGIC > Autolog sets it correctly for known retrievers; for a *custom* retriever you output
# MAGIC > `mlflow.entities.Document`s and set `span_type=SpanType.RETRIEVER` (Step 3).

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 2 · 07.2 ★ — Automated tracing: one line, whole chain  ·  [Hands-on]
# MAGIC `mlflow.langchain.autolog()` hooks LangChain's callback system. From that point, **every** runnable
# MAGIC `.invoke()` writes a trace whose spans mirror the chain — a retriever span, a prompt span, and an LLM
# MAGIC span — with **no per-call code**. Best practice (Book 1): start here; it gets you ~80% of the visibility
# MAGIC in one line. You only add manual spans (Step 3) for the parts autolog can't see.
# MAGIC
# MAGIC We point MLflow at an experiment and pin the version *before* invoking, so the traces we generate attach
# MAGIC to the right place.
# MAGIC
# MAGIC > ⚠️ **GOTCHA — serverless requires explicit autolog enablement.** On serverless compute, GenAI
# MAGIC > autologging is **not** turned on for you. You must call `mlflow.langchain.autolog()` explicitly (and a
# MAGIC > sibling `mlflow.openai.autolog()` / `mlflow.anthropic.autolog()` for each other SDK your app calls).
# MAGIC > Enable several at once and MLflow merges their spans into the same traces.

# COMMAND ----------

import mlflow

mlflow.set_experiment(EXPERIMENT_PATH)          # traces attach to the active experiment

mlflow.langchain.autolog()                      # AUTO: every LangChain .invoke() now emits a trace

# Pin the version: link the traces we're about to produce to a LoggedModel (Module 06).
active = mlflow.set_active_model(name="ua_rag_chain")
print("Autolog on. MLflow:", mlflow.__version__)
print("LoggedModel:", active.name, "| model_id:", active.model_id)

# COMMAND ----------

# MAGIC %md
# MAGIC ### Rebuild the Module 05 chain (the artifact we observe)
# MAGIC The exact chain from `notebooks/05-building-rag-chain/05-3-rag-chain.py`, reassembled here so this lab
# MAGIC is self-contained: a managed-embeddings retriever over the Module 04 index → a grounding prompt →
# MAGIC `ChatDatabricks` → `StrOutputParser`. We keep `retriever`, `prompt`, `llm`, and `format_docs` as named
# MAGIC handles because Step 3 calls them explicitly to slot a manual step in the middle.

# COMMAND ----------

from databricks_langchain import ChatDatabricks, DatabricksVectorSearch
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough

# Retriever — wrap the Module 04 index. source_doc in columns is what lets you cite AND debug provenance.
retriever = DatabricksVectorSearch(
    endpoint=VS_ENDPOINT,
    index_name=INDEX_NAME,
    columns=["chunk_id", "content", "source_doc"],
).as_retriever(search_kwargs={"k": 5})           # top-5 nearest chunks

def format_docs(docs):
    # retriever returns a list[Document]; the prompt slot needs a single string
    return "\n\n".join(d.page_content for d in docs)

# Prompt — where grounding is enforced: answer ONLY from context, say "I don't know", cite source_doc.
prompt = ChatPromptTemplate.from_messages([
    ("system",
     "You are the Unity Airways policy assistant. Answer the question using ONLY the "
     "context below. If the context does not contain the answer, say you don't know. "
     "Cite the source_doc you used.\n\nContext:\n{context}"),
    ("human", "{question}"),
])

llm = ChatDatabricks(endpoint=CHAT_ENDPOINT, temperature=0)   # temperature=0 -> reproducible while developing

chain = (
    {"context": retriever | format_docs, "question": RunnablePassthrough()}
    | prompt
    | llm
    | StrOutputParser()
)
print("Chain rebuilt — same runnable shape Module 06 registered as unity_airways.rag.ua_rag_chain.")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Invoke once — read the automated trace to diagnose the wrong answer
# MAGIC A single `chain.invoke(...)` now produces one full trace. Open it and read the **RETRIEVER span first**:
# MAGIC did the refund / fare-rules chunk come back? If it returned baggage-policy chunks instead, the bug is
# MAGIC upstream in retrieval (Modules 03–04), **not** the model.

# COMMAND ----------

answer = chain.invoke(QUESTION)
print(answer)
# In the trace: RETRIEVER span shows the exact chunks + scores + source_doc; the prompt span shows the
# rendered {context}; the LLM span shows the response, token counts, and latency.

# COMMAND ----------

# MAGIC %md
# MAGIC ### How to verify it worked
# MAGIC - The cell renders an inline **MLflow Trace UI** (Summary / Details & Timeline). Expand it: you should see
# MAGIC   nested spans for the retriever, the prompt, and `ChatDatabricks` — with **zero** tracing code in the chain.
# MAGIC - Or open **Experiments → your experiment → Traces**: one trace per `invoke`, each expandable to its spans.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 3 · 07.3 ★ — Manual tracing: your own spans, merged into the same trace  ·  [Hands-on]
# MAGIC Autolog can't see the code *you* wrote — a pre-step that normalizes the question, a re-ranker between
# MAGIC retrieval and generation. Two fluent forms cover them:
# MAGIC - **`@mlflow.trace`** decorator — trace a whole function; its arguments become span inputs and its return
# MAGIC   value becomes span outputs, automatically.
# MAGIC - **`mlflow.start_span(...)`** context manager — trace an arbitrary *block*; you set `set_inputs(...)`,
# MAGIC   `set_outputs(...)`, and `set_attributes(...)` yourself.
# MAGIC
# MAGIC Then the payoff: an outer `@mlflow.trace(span_type=SpanType.CHAIN)` orchestrator calls both your manual
# MAGIC helpers *and* the autolog'd LangChain pieces, and MLflow files everything under one root by call nesting.

# COMMAND ----------

from mlflow.entities import SpanType

# Form 1 — the @mlflow.trace decorator on a whole function (default span type; name = function name).
@mlflow.trace
def preprocess_question(raw: str) -> str:
    # normalize the question before it reaches the chain — expands "BE fare" so retrieval matches
    return raw.strip().replace("BE fare", "Basic Economy fare")

# A custom RETRIEVER span: set span_type=RETRIEVER and return mlflow.entities.Document objects so the docs
# render as documents in the UI AND can be scored by evaluation later (Module 08).
from mlflow.entities import Document

@mlflow.trace(span_type=SpanType.RETRIEVER, name="ua_retriever",
              attributes={"vs_type": "databricks_vector_search"})
def retrieve_as_documents(q: str):
    span = mlflow.get_current_active_span()      # the span this decorator created
    span.set_attributes({"retriever_k": 5})      # add more attributes from inside
    raw = retriever.invoke(q)                    # LangChain Documents
    return [Document.from_langchain_document(d) for d in raw]   # -> MLflow Documents (valid RETRIEVER schema)

# COMMAND ----------

# MAGIC %md
# MAGIC ### Form 2 — `mlflow.start_span(...)` for a block, with explicit inputs / outputs / attributes
# MAGIC Use the context manager when there is no single function to decorate, or you only want to trace part of
# MAGIC one. Here a stand-in re-ranker sits between retrieval and generation.

# COMMAND ----------

def rerank(question, docs):
    with mlflow.start_span(name="rerank", span_type=SpanType.RERANKER) as span:
        span.set_inputs({"question": question, "n_candidates": len(docs)})   # record inputs
        ranked = sorted(docs, key=lambda d: len(d.page_content))[:3]         # stand-in scorer (real: a model)
        span.set_outputs({"kept": [d.metadata.get("source_doc") for d in ranked]})   # record outputs
        span.set_attributes({"reranker": "heuristic", "top_k": 3})           # arbitrary metadata
        return ranked

# COMMAND ----------

# MAGIC %md
# MAGIC ### Combine auto + manual under ONE root span
# MAGIC The outer `@mlflow.trace(span_type=SpanType.CHAIN)` function is the trace **root**. Inside it we call the
# MAGIC manual `preprocess_question`, the autolog'd `retriever`, the manual `rerank`, and the autolog'd
# MAGIC `prompt | llm | parser`. We reuse the **same** Module 05 components — just called explicitly so `rerank`
# MAGIC can sit in the middle. MLflow links parent→child by nesting; you write no wiring code.
# MAGIC
# MAGIC We also set **trace-level tags** with `mlflow.update_current_trace(tags=...)` so Step 4 has something to
# MAGIC filter on. (Tags live on `TraceInfo` and show in the Traces tab — not on individual spans.)

# COMMAND ----------

@mlflow.trace(span_type=SpanType.CHAIN)          # MANUAL outer span = the trace root
def answer_unity_airways(raw_question: str) -> str:
    mlflow.update_current_trace(tags={"app": "ua-policy-bot", "channel": "web"})   # trace-level tags
    q = preprocess_question(raw_question)         # -> manual span (child)
    docs = retriever.invoke(q)                    # -> AUTO RETRIEVER span
    docs = rerank(q, docs)                        # -> manual RERANKER span (child)
    return (prompt | llm | StrOutputParser()).invoke(   # -> AUTO prompt + LLM spans
        {"context": format_docs(docs), "question": q}
    )

print(answer_unity_airways("Can I get a refund on a BE fare?"))

# COMMAND ----------

# MAGIC %md
# MAGIC ### How to verify it worked
# MAGIC Open the newest trace. The tree should read:
# MAGIC `answer_unity_airways (CHAIN)` → `preprocess_question` → retriever `(RETRIEVER)` → `rerank (RERANKER)`
# MAGIC → prompt → `ChatDatabricks (CHAT_MODEL)`. Auto and manual spans sit in **one** tree, and the trace carries
# MAGIC your `app` / `channel` tags.
# MAGIC
# MAGIC > ⚠️ **GOTCHA:** The high-level **Fluent APIs** (`@mlflow.trace`, `mlflow.start_span`) and the low-level
# MAGIC > **Client API** (`MlflowClient().start_span/end_span` with explicit `parent_id`) **cannot be mixed** in
# MAGIC > one trace. Also: if a step fans out with `ThreadPoolExecutor`, copy the context into each worker
# MAGIC > (`contextvars.copy_context().run(fn, ...)`) or the child spans land in the wrong trace.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 4 · 07.4 — Querying traces at scale  ·  [Hands-on]
# MAGIC Once traces are captured, you query them to find the ones worth investigating — the slow, the failed,
# MAGIC the wrong. `mlflow.search_traces(...)` returns a **pandas DataFrame** (one row per trace) you can slice,
# MAGIC group, and export. The UI's **Traces** tab is the visual equivalent.

# COMMAND ----------

# All recent traces for this experiment as a DataFrame — one row per trace.
# Step 2 set the active experiment; resolve its ID for search_traces (param is experiment_ids, not experiment_names).
EXPERIMENT_ID = mlflow.get_experiment_by_name(EXPERIMENT_PATH).experiment_id
traces = mlflow.search_traces(experiment_ids=[EXPERIMENT_ID])
print("Traces found:", len(traces))
print("Columns:", list(traces.columns))
traces.head()

# COMMAND ----------

# MAGIC %md
# MAGIC ### Filter by status, tags, and time
# MAGIC The `filter_string` mirrors the `TraceInfo` schema. Rules that trip people up: **`AND` only** (no `OR`),
# MAGIC string literals in **single quotes**, field names/values are **case sensitive**, and backtick fields with
# MAGIC dots (`` tags.`mlflow.traceName` ``).

# COMMAND ----------

import time

# By status — find failed traces to triage.
errors = mlflow.search_traces(
    experiment_ids=[EXPERIMENT_ID],
    filter_string="attributes.status = 'ERROR'",
)
print("ERROR traces:", len(errors))

# By tag — find only the traces our tagged orchestrator produced (set in Step 3).
tagged = mlflow.search_traces(
    experiment_ids=[EXPERIMENT_ID],
    filter_string="tags.app = 'ua-policy-bot'",
)
print("ua-policy-bot traces:", len(tagged))

# By time — traces from the last hour (timestamp is ms since epoch; supports < <= > >=).
one_hour_ago_ms = int((time.time() - 3600) * 1000)
recent = mlflow.search_traces(
    experiment_ids=[EXPERIMENT_ID],
    filter_string=f"attributes.timestamp_ms > {one_hour_ago_ms}",
)
print("Traces in the last hour:", len(recent))

# NOTE: the filter-string prefix is EVOLVING. The book's inline examples use a `traces.` prefix while its own
# syntax table uses `attributes.` / `tags.` / `metadata.`. The exact search-path prefixes and field set are
# an area MLflow is still refining — VERIFY against current MLflow docs for your runtime before relying on a
# filter in production (mlflow.org/docs/latest/genai/tracing/). `AND` only; no `OR`.

# COMMAND ----------

# MAGIC %md
# MAGIC ### How to verify it worked
# MAGIC `len(traces)` should match the count the UI's Traces tab shows for the same experiment, and the tag
# MAGIC filter should return only the orchestrator runs from Step 3. If a `filter_string` raises, it is almost
# MAGIC always the prefix (see the NOTE above) — check the current docs and adjust the prefix.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 5 · 07.5 — Trace-first development as a discipline  ·  [Theory]
# MAGIC Tracing is not a debugging tool you bolt on at the end — it is a **development discipline** you adopt from
# MAGIC the first working path. The MLflow book frames a five-phase lifecycle — **Develop → Evaluate → Deploy →
# MAGIC Monitor → Improve** — and tracing is what keeps the whole loop honest.
# MAGIC
# MAGIC - **Instrument from the first coherent answer.** The moment the chain returns something sensible, its
# MAGIC   key steps already record inputs, outputs, timing, and metadata — so *"why did it say that?"* has an
# MAGIC   evidence-based answer instead of a guess.
# MAGIC - **Dev traces seed the evaluation set.** The questions you traced while building become the first rows
# MAGIC   of the **Module 08** eval dataset; a `RetrievalGroundedness` / `RetrievalRelevance` scorer reads the
# MAGIC   retrieved context straight from the RETRIEVER span you saw in Step 2.
# MAGIC - **The payoff is cultural:** teams stop arguing from anecdotes and start pointing at trace evidence.
# MAGIC   Adopt the habit — *question any workflow that cannot explain its own results.*
# MAGIC
# MAGIC > 📌 **IMPORTANT:** *"The difference between debugging and guessing is whether those traces exist."*
# MAGIC > Observability gets harder as systems become compound — retrieval returns empty context, a tool throws an
# MAGIC > error the model quietly ignores, an orchestration branch never fires. Trace-first is how these stay
# MAGIC > visible instead of silent.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Recap, gotchas and next step
# MAGIC **What you did** — the module's topics, in order, on the Module 05 chain:
# MAGIC - **07.1 concepts:** `Trace = TraceInfo + TraceData`; `Span`s nest into a tree; the `RETRIEVER` span has a
# MAGIC   required schema so retrieved docs render and can be scored.
# MAGIC - **07.2 automated (★):** `mlflow.langchain.autolog()` → one `chain.invoke(...)` emits a full trace
# MAGIC   (retriever + prompt + LLM spans) with no per-call code.
# MAGIC - **07.3 manual (★):** `@mlflow.trace` on a function, `mlflow.start_span(...)` for a block (with
# MAGIC   `set_inputs`/`set_outputs`/`set_attributes` and a `SpanType`), combined with autolog under one root
# MAGIC   `@mlflow.trace(span_type=SpanType.CHAIN)` orchestrator.
# MAGIC - **07.4 querying:** `mlflow.search_traces(...)` → pandas DataFrame; filter by status / tags / time.
# MAGIC - **07.5 trace-first:** instrument from the first working path; dev traces seed the Module 08 eval set.
# MAGIC
# MAGIC **Gotchas to remember**
# MAGIC - On **serverless**, autolog is **not** automatic — call `mlflow.<library>.autolog()` explicitly.
# MAGIC - A custom retriever span must return `mlflow.entities.Document`s with `span_type=SpanType.RETRIEVER`,
# MAGIC   or retrieval can't be evaluated.
# MAGIC - `set_attributes` = **span**-level; `update_current_trace(tags=)` = **trace**-level (what you search on).
# MAGIC - Don't mix Fluent (`@mlflow.trace` / `start_span`) and low-level Client tracing APIs in one trace.
# MAGIC - `search_traces` filters are **`AND` only**, single-quoted strings, case sensitive; the field **prefix
# MAGIC   is evolving** — verify against current docs.
# MAGIC
# MAGIC > 📌 **The connective tissue:** `mlflow.set_active_model(name="ua_rag_chain")` linked every trace above to
# MAGIC > the **LoggedModel** version. That is the thread **Module 08 evaluation** pulls on — it reads *these*
# MAGIC > traces (the RETRIEVER span especially) to score *that* build and gate its promotion.
# MAGIC
# MAGIC **Next:** **Module 08 — Evaluating GenAI apps** with `mlflow.genai.evaluate()`: turn the traces you just
# MAGIC produced into a scored eval run and gate promotion on the result.
