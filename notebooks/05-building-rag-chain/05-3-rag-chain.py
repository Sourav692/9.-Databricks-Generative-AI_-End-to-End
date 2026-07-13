# Databricks notebook source
# MAGIC %md
# MAGIC # 05.3 ★ — From an LLM-only app to a full RAG chain
# MAGIC **Roadmap:** Module 05 (Building and versioning a RAG chain) · Topic 05.3 (cornerstone) · [Hands-on]
# MAGIC
# MAGIC ## The problem
# MAGIC A raw foundation model has never read Unity Airways' Conditions of Carriage. Ask it *"Can I get a
# MAGIC refund if I miss my connection?"* and it answers **confidently** in fluent, official-sounding
# MAGIC language — but that policy is a statistical average of every airline it saw in training, not Unity
# MAGIC Airways' actual rule. For a policy assistant, a confident wrong answer is worse than "I don't know."
# MAGIC
# MAGIC ## What you will build
# MAGIC Two versions of the same app, so you can *see* what retrieval buys you:
# MAGIC 1. An **LLM-only baseline** — one line, `ChatDatabricks(...).invoke(...)`, answering from memory.
# MAGIC 2. A **full RAG chain** — the Module 04 retriever feeds top-k Unity Airways chunks into the prompt,
# MAGIC    and the model answers **only** from that context, with a citable `source_doc`.
# MAGIC
# MAGIC You assemble it with **LCEL** (the `|` pipe). The `chain` object you build here is the exact
# MAGIC runnable that Topic 05.6 logs and registers with MLflow — so getting it right now is the foundation
# MAGIC for packaging and deployment later.
# MAGIC
# MAGIC ### Prerequisites (read before running)
# MAGIC - **Compute:** **serverless notebook/job**, or a **DBR ML runtime** (15.4 LTS ML or later is a safe
# MAGIC   floor). Serverless is the simplest default.
# MAGIC - **MLflow:** **≥ 3.1** is required here — `mlflow.langchain.autolog()` and MLflow 3 tracing are what
# MAGIC   make every `chain.invoke(...)` an inspectable trace.
# MAGIC - **Vector Search index (from Module 04):** `unity_airways.rag.ua_rag_chunks_index` must be **ONLINE**
# MAGIC   on endpoint **`unity-airways-vs`** (built over `content`, keyed on `chunk_id`, with `source_doc`
# MAGIC   synced). This notebook does **not** re-create it — it consumes the Module 04 hand-off.
# MAGIC - **Chat serving endpoint:** **`databricks-claude-sonnet-4-5`** (Foundation Model API). Endpoint
# MAGIC   names churn — confirm on the current **supported-models** page before hard-coding it.
# MAGIC - **Secrets:** none. Managed embeddings and workspace auth need no external key.
# MAGIC - **Learner-set identifiers:** edit `CATALOG` / `SCHEMA` / `VS_ENDPOINT` / `CHAT_ENDPOINT` in Step 0.
# MAGIC
# MAGIC > 📌 **Naming trap:** the retriever and chat model come from **`databricks-langchain`**
# MAGIC > (`from databricks_langchain import ChatDatabricks, DatabricksVectorSearch`) — never
# MAGIC > `langchain-databricks` or `langchain_community`. LCEL primitives come from `langchain_core`.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 0. Install libraries and set variables
# MAGIC `databricks-langchain` (`ChatDatabricks` + `DatabricksVectorSearch`), `databricks-vectorsearch`
# MAGIC (the underlying index client), and `mlflow` (tracing). Restart Python so the fresh installs import.

# COMMAND ----------

# MAGIC %pip install -U databricks-langchain databricks-vectorsearch "mlflow>=3.1"
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

CATALOG       = "unity_airways"          # a catalog you can read from
SCHEMA        = "rag"                    # the RAG schema from Modules 03/04
VS_ENDPOINT   = "unity-airways-vs"       # Vector Search endpoint (from Module 04)
INDEX_NAME    = f"{CATALOG}.{SCHEMA}.ua_rag_chunks_index"   # the Module 04 index
CHAT_ENDPOINT = "databricks-claude-sonnet-4-5"             # confirm on the supported-models page

QUESTION = "Can I get a refund if I miss my connection?"   # the running example question

print("Index         :", INDEX_NAME)
print("VS endpoint   :", VS_ENDPOINT)
print("Chat endpoint :", CHAT_ENDPOINT)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Turn on tracing first
# MAGIC Call `mlflow.langchain.autolog()` once, early. From now on **every** LangChain `.invoke()` — even
# MAGIC the bare LLM baseline — emits an MLflow **trace** with nested spans (retriever, prompt, model) you
# MAGIC can open in **Experiments → Traces**. No per-call code.

# COMMAND ----------

import mlflow

mlflow.langchain.autolog()   # every LangChain .invoke() now emits a trace
print("Autolog on. MLflow:", mlflow.__version__)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. The LLM-only baseline — watch it answer without your documents
# MAGIC Prove the problem before fixing it. Instantiate `ChatDatabricks` and ask the policy question
# MAGIC directly. `temperature=0` makes the answer deterministic so runs are reproducible while you develop.

# COMMAND ----------

from databricks_langchain import ChatDatabricks

llm = ChatDatabricks(endpoint=CHAT_ENDPOINT, temperature=0)   # same object we reuse in the RAG chain

baseline = llm.invoke(QUESTION).content
print(baseline)
# Fluent and official-sounding — but it is a GENERIC airline policy, not Unity Airways'.
# This is exactly the hallucination RAG fixes.

# COMMAND ----------

# MAGIC %md
# MAGIC ### How to verify the gap
# MAGIC The answer sounds authoritative yet names **no Unity Airways specifics** — no real fare-class names,
# MAGIC no actual refund window, no source. That absence is your motivation for retrieval. Keep this answer
# MAGIC as your control: you will run the same question through the RAG chain and watch it become grounded.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Build the retriever — the "R", reused not rebuilt
# MAGIC You already created the AI Search index in Module 04. Here you only **wrap** it as a LangChain
# MAGIC retriever. For a **managed-embeddings** index (our case) you pass only text — no separate embeddings
# MAGIC object. `search_kwargs={"k": 5}` asks for the 5 nearest chunks; putting `source_doc` in `columns` is
# MAGIC what lets the model cite and what lets *you* debug which document produced an answer.

# COMMAND ----------

from databricks_langchain import DatabricksVectorSearch

vector_store = DatabricksVectorSearch(
    endpoint=VS_ENDPOINT,
    index_name=INDEX_NAME,
    columns=["chunk_id", "content", "source_doc"],   # source_doc so answers are citable
)
retriever = vector_store.as_retriever(search_kwargs={"k": 5})   # top-5 nearest chunks

# Sanity-check the retriever ALONE before wiring it into a chain (build incrementally):
for d in retriever.invoke(QUESTION):
    print(d.metadata.get("source_doc"), "|", d.page_content[:100], "...")

# COMMAND ----------

# MAGIC %md
# MAGIC ### How to verify it worked
# MAGIC `retriever.invoke(...)` returns LangChain `Document` objects whose `page_content` is the chunk text
# MAGIC and whose `metadata` carries `source_doc` / `chunk_id`. **Empty metadata means those columns were
# MAGIC not synced** into the index (fix in Module 04's index definition).

# COMMAND ----------

docs = retriever.invoke(QUESTION)
assert docs, "Retriever returned no documents — is the index ONLINE and synced? (Module 04)"
assert docs[0].metadata.get("source_doc"), "Metadata empty — source_doc was not synced into the index."
print("OK — retriever returns Documents with populated metadata. This is the Module 04 hand-off object.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Write `format_docs` and the prompt
# MAGIC A retriever returns a `list[Document]`, but a prompt slot needs a single **string**. `format_docs`
# MAGIC bridges that by joining each document's `.page_content`. The prompt is where **grounding is
# MAGIC enforced**: the system message tells the model to answer *only* from the context, say "I don't know"
# MAGIC if it is not there, and cite the `source_doc`.

# COMMAND ----------

from langchain_core.prompts import ChatPromptTemplate

def format_docs(docs):
    # retriever returns Documents; the prompt needs one string
    return "\n\n".join(d.page_content for d in docs)

prompt = ChatPromptTemplate.from_messages([
    ("system",
     "You are the Unity Airways policy assistant. Answer the question using ONLY the "
     "context below. If the context does not contain the answer, say you don't know. "
     "Cite the source_doc you used.\n\n"
     "Context:\n{context}"),
    ("human", "{question}"),
])

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Assemble the RAG chain with LCEL
# MAGIC Read the pipe left to right. The one "trick" is the **parallel dict** — LCEL feeds the *same* input
# MAGIC (the question string) into both branches at once:
# MAGIC - **`"context"`** branch: question → `retriever` → list of Documents → `format_docs` → context string.
# MAGIC - **`"question"`** branch: question → `RunnablePassthrough()` → the same question, untouched.
# MAGIC
# MAGIC The dict `{"context": "...", "question": "..."}` fills the prompt's two slots, the prompt goes to the
# MAGIC model, and `StrOutputParser()` pulls the plain text out of the model's message object.

# COMMAND ----------

from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough

chain = (
    {"context": retriever | format_docs, "question": RunnablePassthrough()}
    | prompt
    | llm
    | StrOutputParser()
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6. Invoke it with a bare string
# MAGIC Because `RunnablePassthrough()` forwards the chain input straight into `{question}`, you call
# MAGIC `chain.invoke("...")` with a **bare string**, not a dict.

# COMMAND ----------

answer = chain.invoke(QUESTION)
print(answer)
# Now grounded in the Conditions-of-Carriage chunks, and it names the source_doc.

# COMMAND ----------

# MAGIC %md
# MAGIC ### How to verify it worked
# MAGIC - The answer now uses Unity Airways' **actual** language and cites a `source_doc` — compare it to the
# MAGIC   generic baseline from Step 2.
# MAGIC - Open the trace in the MLflow UI (**Experiments → your experiment → Traces**): the **retriever span**
# MAGIC   should show the refund / missed-connection chunks. If the answer is still generic, read that span —
# MAGIC   the bug is upstream in retrieval (chunking, `k`, index columns), **not** the model.

# COMMAND ----------

# Programmatic smoke check: the two answers should differ, and the grounded one should be non-empty.
assert answer and answer.strip(), "RAG chain returned an empty answer."
print("Baseline length:", len(baseline), "| RAG length:", len(answer))
print("OK — grounded answer produced. Open Traces to inspect the retriever span for provenance.")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Build incrementally — test each link before piping (field tip)
# MAGIC When something breaks, you want to know *which* link failed. Invoke each stage in isolation:

# COMMAND ----------

# 1) retriever alone -> Documents
print("retriever   ->", type(retriever.invoke(QUESTION)))
# 2) retriever | format_docs -> a context string
ctx = (retriever | format_docs).invoke(QUESTION)
print("format_docs ->", ctx[:80], "...")
# 3) prompt with both slots filled -> a message list
print("prompt      ->", type(prompt.invoke({"context": ctx, "question": QUESTION})))
# 4) the whole chain -> a clean string (Step 6)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 7. Recap, gotchas and next step
# MAGIC **What you built**
# MAGIC - An **LLM-only baseline** that hallucinates a generic policy (the control).
# MAGIC - A **full RAG chain** — `{"context": retriever | format_docs, "question": RunnablePassthrough()} |
# MAGIC   prompt | llm | StrOutputParser()` — that answers from Unity Airways' own documents and cites them.
# MAGIC - Tracing via `mlflow.langchain.autolog()`, so every invoke is an inspectable trace.
# MAGIC
# MAGIC **Gotchas to remember**
# MAGIC - Invoke this chain with a **bare string**; passing `{"question": ...}` lands the whole dict in the
# MAGIC   `{question}` slot because `RunnablePassthrough()` forwards its input.
# MAGIC - `format_docs` must return a **string**; returning the raw `Document` list renders ugly, token-heavy
# MAGIC   context.
# MAGIC - Without the "answer only from context" instruction the model drifts back to hallucinating.
# MAGIC - Forgetting `StrOutputParser()` makes `chain.invoke` return a message object, not text.
# MAGIC - Same **model** in both versions — RAG changes *what the model sees*, not how smart it is. When a
# MAGIC   RAG answer is wrong, suspect retrieval (chunking, `k`, index columns) before the prompt or model.
# MAGIC - Import from **`databricks-langchain`**, not `langchain_community` / `langchain-databricks`.
# MAGIC
# MAGIC **Next:** the `chain` object is a runnable. **Topic 05.6** (`05-6-model-as-code.py`) logs *this exact
# MAGIC chain* as **Model-as-Code** with a signature and dependent resources, then registers it to Unity
# MAGIC Catalog as `unity_airways.rag.ua_rag_chain`. Keep this object shape in mind.
