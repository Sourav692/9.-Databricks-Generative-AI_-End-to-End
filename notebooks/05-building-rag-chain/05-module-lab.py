# Databricks notebook source
# MAGIC %md
# MAGIC # Module 05 lab — anatomy → integration → chain → memory → package → log-as-code → version
# MAGIC **Roadmap:** Module 05 (Building and versioning a RAG chain) · consolidated hands-on lab · [Theory + Hands-on]
# MAGIC
# MAGIC One runnable, end-to-end lab that walks the module's topics **in order** and finishes with the RAG
# MAGIC chain registered in Unity Catalog and versioned with a `@champion` alias, ready for Module 08
# MAGIC (MLflow evaluation) and deployment (Module 11):
# MAGIC
# MAGIC | Step | Topic | What you do |
# MAGIC |---|---|---|
# MAGIC | 1 | **05.1** | Chain anatomy — what "chain" and LCEL mean (`%md`) |
# MAGIC | 2 | **05.2** | LangChain ↔ Databricks: `ChatDatabricks`, `DatabricksVectorSearch` |
# MAGIC | 3 | **05.3** | Build the RAG chain (LLM-only baseline → full RAG chain) |
# MAGIC | 4 | **05.4** | Memory / context — inject a `{chat_history}` slot (buffer memory) |
# MAGIC | 5 | **05.5** | Packaging — model signature + dependent `resources=[...]` |
# MAGIC | 6 | **05.6** | Log as **Model-as-Code** (`%%writefile` + `set_model` + `log_model`) |
# MAGIC | 7 | **05.7** | Versioning — LoggedModel, register to UC, set a `@champion` alias |
# MAGIC
# MAGIC The cornerstone deep-dives are `05-3-rag-chain.py` (Step 3) and `05-6-model-as-code.py` (Step 6);
# MAGIC this lab reuses the same Module 04 retriever and canonical names and layers the rest on top.
# MAGIC
# MAGIC ## Prerequisites (read before running)
# MAGIC - **Compute:** **serverless notebook/job**, or a **DBR ML runtime** (15.4 LTS ML or later).
# MAGIC - **MLflow:** **≥ 3.1** is **required** — tracing, `set_active_model`/LoggedModel, and
# MAGIC   Models-from-Code are all MLflow 3 features exercised here.
# MAGIC - **Vector Search index (from Module 04):** `unity_airways.rag.ua_rag_chunks_index` ONLINE on endpoint
# MAGIC   **`unity-airways-vs`** (over `content`, keyed on `chunk_id`, `source_doc` synced). The retriever is
# MAGIC   the Module 04 hand-off — this lab consumes it, it does not rebuild it.
# MAGIC - **Chat serving endpoint:** **`databricks-claude-sonnet-4-5`** — confirm on the supported-models page.
# MAGIC - **Unity Catalog:** read access to the index and **write access to `unity_airways.rag`** to register
# MAGIC   the model `unity_airways.rag.ua_rag_chain`.
# MAGIC - **Secrets:** none — declared `resources=[...]` drive automatic authentication passthrough on deploy.
# MAGIC - **Learner-set identifiers:** edit the constants in Step 0.
# MAGIC
# MAGIC > 📌 **Naming trap:** `ChatDatabricks` / `DatabricksVectorSearch` come from **`databricks-langchain`**
# MAGIC > (never `langchain-databricks` / `langchain_community`); resource classes come from
# MAGIC > `mlflow.models.resources`; LCEL primitives from `langchain_core`.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 0. Install libraries and set variables

# COMMAND ----------

# MAGIC %pip install -U databricks-langchain databricks-vectorsearch "mlflow>=3.1"
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

CATALOG       = "unity_airways"
SCHEMA        = "rag"
INDEX_NAME    = f"{CATALOG}.{SCHEMA}.ua_rag_chunks_index"   # from Module 04.3
VS_ENDPOINT   = "unity-airways-vs"                          # Vector Search endpoint (Module 04)
CHAT_ENDPOINT = "databricks-claude-sonnet-4-5"             # confirm on the supported-models page
UC_MODEL      = f"{CATALOG}.{SCHEMA}.ua_rag_chain"          # where we register the chain

EXAMPLE_Q = "Can I get a refund if I miss my connection?"

print("Index         :", INDEX_NAME)
print("Chat endpoint :", CHAT_ENDPOINT)
print("UC model      :", UC_MODEL)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 1 · 05.1 — What is a "chain"? RAG chain anatomy  ·  [Theory]
# MAGIC A **chain** is an ordered set of steps where each step's output feeds the next. LangChain builds them
# MAGIC with **LCEL** — the `|` pipe operator, the same idea as a Unix pipe. A **RAG chain** is a chain with a
# MAGIC retrieval step in the middle. Its anatomy, in order:
# MAGIC
# MAGIC 1. **Input** — the user's question.
# MAGIC 2. **Retrieve** — the Module 04 retriever returns the top-`k` chunks.
# MAGIC 3. **Format context** — `format_docs` flattens those chunks into one context string.
# MAGIC 4. **Prompt** — a template combines `{context}` and `{question}` into one instruction.
# MAGIC 5. **Generate** — `ChatDatabricks` sends the prompt to the model endpoint.
# MAGIC 6. **Parse** — `StrOutputParser` turns the model's message object into a plain string.
# MAGIC
# MAGIC The clever part: build-context and pass-the-question-through run **in parallel** (a parallel dict),
# MAGIC because the prompt needs both. We use the **string-in** form here (bare string in, `RunnablePassthrough`)
# MAGIC so the LCEL wiring is clear; a production chat endpoint receives the `{"messages": [...]}` shape.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 2 · 05.2 — LangChain ↔ Databricks integration
# MAGIC Two classes from **`databricks-langchain`** do all the wiring. `ChatDatabricks` wraps a model-serving
# MAGIC endpoint as a chat model; `DatabricksVectorSearch` wraps the Module 04 index and hands back the
# MAGIC retriever. For our **managed-embeddings** index the retriever just passes query text — no separate
# MAGIC `DatabricksEmbeddings` object needed.

# COMMAND ----------

from databricks_langchain import ChatDatabricks, DatabricksVectorSearch

# The generation half — reused everywhere below. temperature=0 for reproducible dev runs.
llm = ChatDatabricks(endpoint=CHAT_ENDPOINT, temperature=0, max_tokens=1000)
print(llm.invoke("How do I book flights with Unity Airways?").content[:200])

# COMMAND ----------

# The retrieval half — the SAME object Module 04 built. k=5 nearest chunks; source_doc for citation.
vector_store = DatabricksVectorSearch(
    endpoint=VS_ENDPOINT,
    index_name=INDEX_NAME,
    columns=["chunk_id", "content", "source_doc"],
)
retriever = vector_store.as_retriever(search_kwargs={"k": 5})

docs = retriever.invoke(EXAMPLE_Q)
for d in docs:
    print(d.metadata.get("source_doc"), "|", d.page_content[:100], "...")

# COMMAND ----------

# MAGIC %md
# MAGIC ### How to verify it worked
# MAGIC `llm.invoke(...).content` is text; `retriever.invoke(...)` returns `Document`s whose `page_content` is
# MAGIC the chunk and whose `metadata` carries `source_doc`. Empty metadata means those columns weren't synced
# MAGIC (fix in Module 04's index definition).

# COMMAND ----------

assert docs and docs[0].metadata.get("source_doc"), "Retriever metadata empty — check Module 04 sync."
print("OK — ChatDatabricks answers, and the retriever returns cited Documents.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 3 · 05.3 — Build the RAG chain (baseline → full RAG)
# MAGIC Turn on tracing first, then build in two versions so you can *measure* what retrieval buys you. Each
# MAGIC `set_active_model(...)` opens a **LoggedModel** version; every trace after it links to that version, so
# MAGIC `llm_only` and `rag_chain` are comparable in the MLflow Versions/Traces tabs.

# COMMAND ----------

import mlflow
mlflow.langchain.autolog()   # every LangChain .invoke() now emits an MLflow trace

# --- Version A: LLM-only baseline (no grounding) ---
mlflow.set_active_model(name="llm_only")
baseline = llm.invoke(EXAMPLE_Q).content
print("LLM-only (generic, ungrounded):\n", baseline[:250])

# COMMAND ----------

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough

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

# --- Version B: the full RAG chain (string-in LCEL) ---
mlflow.set_active_model(name="rag_chain")
chain = (
    {"context": retriever | format_docs, "question": RunnablePassthrough()}
    | prompt
    | llm
    | StrOutputParser()
)

answer = chain.invoke(EXAMPLE_Q)   # invoke with a BARE STRING (RunnablePassthrough forwards it)
print("RAG chain (grounded, cited):\n", answer[:250])

# COMMAND ----------

# MAGIC %md
# MAGIC ### How to verify it worked
# MAGIC The RAG answer uses Unity Airways' actual language and cites a `source_doc`; the baseline does not.
# MAGIC Open **Experiments → Traces**, enable the **Version** column, and confirm the `rag_chain` trace shows a
# MAGIC retriever span *and* a `ChatDatabricks` span — proof the context step ran before generation.

# COMMAND ----------

assert answer and answer.strip(), "RAG chain returned an empty answer."
print("Baseline length:", len(baseline), "| RAG length:", len(answer))
print("OK — two versions logged. Inspect the retriever span in the rag_chain trace.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 4 · 05.4 — Memory and context management
# MAGIC The chain above is **stateless**. Real conversations need **memory** so a follow-up like "and for a
# MAGIC Basic Economy fare?" builds on the prior turn. The injection pattern: give the prompt a `{chat_history}`
# MAGIC slot and populate it before generation. Here we use simple **buffer memory** (the last N turns,
# MAGIC verbatim). Because the prompt now needs three slots, this chain takes a **dict** input, not a bare string.

# COMMAND ----------

from operator import itemgetter

memory_prompt = ChatPromptTemplate.from_messages([
    ("system",
     "You are the Unity Airways policy assistant. Conversation so far:\n{chat_history}\n\n"
     "Answer the question using ONLY the context below. If it is not there, say you don't know. "
     "Cite the source_doc.\n\nContext:\n{context}"),
    ("human", "{question}"),
])

# Parallel dict reads the "question" key for retrieval, and passes question + chat_history through.
memory_chain = (
    {
        "context":      itemgetter("question") | retriever | format_docs,
        "question":     itemgetter("question"),
        "chat_history": itemgetter("chat_history"),
    }
    | memory_prompt
    | llm
    | StrOutputParser()
)

# COMMAND ----------

# Buffer memory: keep the last N turns verbatim, format them into the {chat_history} slot.
history = []          # list of (role, text)
N_TURNS = 4           # cap the window so tokens/cost/latency don't grow without bound

def ask(question: str) -> str:
    hist = "\n".join(f"{r}: {t}" for r, t in history[-N_TURNS * 2:]) or "(no prior turns)"
    ans = memory_chain.invoke({"question": question, "chat_history": hist})
    history.extend([("user", question), ("assistant", ans)])
    return ans

print("Q1:", ask("Can I get a refund if I miss my connection?")[:200])
print("\nQ2 (follow-up):", ask("And what about for a Basic Economy fare?")[:200])

# COMMAND ----------

# MAGIC %md
# MAGIC ### How to verify it worked
# MAGIC The second answer should make sense as a **follow-up** — it treats "refund" as the ongoing topic
# MAGIC because the first turn is in `{chat_history}`.
# MAGIC
# MAGIC > ⚠️ **GOTCHA:** history affects **retrieval** too. A bare follow-up ("and for Basic Economy?") may
# MAGIC > retrieve off-topic chunks because only `question` is sent to the retriever. In production, fold the
# MAGIC > earlier turn's subject into the retrieval query, and cap/summarize history so it can't overflow the
# MAGIC > context window.

# COMMAND ----------

assert len(history) == 4, "Expected two turns (4 messages) buffered."
print("OK — buffer memory injected via the {chat_history} slot over", len(history)//2, "turns.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 5 · 05.5 — Packaging: model signature + dependent resources
# MAGIC A chain that runs in your notebook won't run on a serving endpoint unless MLflow **packages** what it
# MAGIC needs. Two pieces are mandatory before logging:
# MAGIC - a **signature** (input/output schema — a string in, a string out), and
# MAGIC - **dependent resources** — the services the chain calls, so a *deployed* chain auto-authenticates.
# MAGIC   Forget these and the chain works in the notebook but **401s once served**.

# COMMAND ----------

from mlflow.models import infer_signature
from mlflow.models.resources import DatabricksServingEndpoint, DatabricksVectorSearchIndex

signature = infer_signature(model_input=EXAMPLE_Q, model_output="A short grounded answer.")

# NOTE: resources classes confirmed in Book 1 Ch4; re-verify kwargs against current MLflow docs.
resources = [
    DatabricksServingEndpoint(endpoint_name=CHAT_ENDPOINT),   # generation (the "G")
    DatabricksVectorSearchIndex(index_name=INDEX_NAME),       # retrieval (the "R")
]
print("Signature + resources ready for logging.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 6 · 05.6 — Log as Model-as-Code
# MAGIC A RAG chain holds **live clients** (the VS retriever, the LLM client), so cloudpickling the object
# MAGIC fails with `VectorStoreRetriever ... a loader_fn must be provided`. **Models-from-Code** sidesteps
# MAGIC that: write the chain to a `.py` file ending in `mlflow.models.set_model(chain)`, then log the **file
# MAGIC path**. MLflow stores the code and rebuilds the chain fresh at load time.

# COMMAND ----------

# MAGIC %%writefile rag_chain.py
# MAGIC # rag_chain.py — the entire chain, self-contained (no notebook globals). Loading re-runs this file.
# MAGIC import mlflow
# MAGIC from databricks_langchain import ChatDatabricks, DatabricksVectorSearch
# MAGIC from langchain_core.prompts import ChatPromptTemplate
# MAGIC from langchain_core.output_parsers import StrOutputParser
# MAGIC from langchain_core.runnables import RunnablePassthrough
# MAGIC
# MAGIC mlflow.langchain.autolog()
# MAGIC
# MAGIC INDEX_NAME    = "unity_airways.rag.ua_rag_chunks_index"
# MAGIC VS_ENDPOINT   = "unity-airways-vs"
# MAGIC CHAT_ENDPOINT = "databricks-claude-sonnet-4-5"
# MAGIC
# MAGIC retriever = DatabricksVectorSearch(
# MAGIC     endpoint=VS_ENDPOINT,
# MAGIC     index_name=INDEX_NAME,
# MAGIC     columns=["chunk_id", "content", "source_doc"],
# MAGIC ).as_retriever(search_kwargs={"k": 5})
# MAGIC
# MAGIC def format_docs(docs):
# MAGIC     return "\n\n".join(d.page_content for d in docs)
# MAGIC
# MAGIC prompt = ChatPromptTemplate.from_messages([
# MAGIC     ("system",
# MAGIC      "You are the Unity Airways policy assistant. Answer the question using ONLY the "
# MAGIC      "context below. If the context does not contain the answer, say you don't know. "
# MAGIC      "Cite the source_doc you used.\n\nContext:\n{context}"),
# MAGIC     ("human", "{question}"),
# MAGIC ])
# MAGIC
# MAGIC llm = ChatDatabricks(endpoint=CHAT_ENDPOINT, temperature=0)
# MAGIC
# MAGIC chain = (
# MAGIC     {"context": retriever | format_docs, "question": RunnablePassthrough()}
# MAGIC     | prompt | llm | StrOutputParser()
# MAGIC )
# MAGIC
# MAGIC mlflow.models.set_model(chain)   # ← THIS is the model MLflow logs

# COMMAND ----------

# Sanity-check the file before logging (runs it the way MLflow will at load time).
import sys, os
sys.path.insert(0, os.getcwd())
from rag_chain import chain as file_chain
print(file_chain.invoke(EXAMPLE_Q)[:200])

# COMMAND ----------

# Log as Models-from-Code: lc_model is the FILE PATH, not the object. No cloudpickle.
with mlflow.start_run() as run:
    logged = mlflow.langchain.log_model(
        lc_model="rag_chain.py",
        name="chain",                            # -> runs:/<run_id>/chain
        signature=signature,
        input_example=EXAMPLE_Q,
        resources=resources,                     # auto-auth on deploy
        pip_requirements=["mlflow>=3.1", "databricks-langchain", "databricks-vectorsearch"],
    )
print("model_uri:", logged.model_uri)

# Reload (re-executes the code) to prove the round-trip.
loaded = mlflow.langchain.load_model(logged.model_uri)
print(loaded.invoke("What is the checked baggage allowance on Basic Economy?")[:200])

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 7 · 05.7 — Versioning: LoggedModel, register to UC, set a `@champion` alias
# MAGIC A GenAI app changes constantly; MLflow 3 versions each iteration as a **LoggedModel** via
# MAGIC `mlflow.set_active_model(name=...)` and links its traces, params, and evals automatically. We log the
# MAGIC version's params, **register** the Model-as-Code artifact to Unity Catalog (a new version), and set a
# MAGIC `@champion` **alias** so downstream deployment (Module 11) can pin "the current best" by name.

# COMMAND ----------

# Reuse the "rag_chain" LoggedModel opened in Step 3, and record its parameters.
active = mlflow.set_active_model(name="rag_chain")
print("LoggedModel:", active.name, "| model_id:", active.model_id)

app_params = {
    "llm_endpoint": CHAT_ENDPOINT,
    "index":        INDEX_NAME,
    "k":            5,
    "temperature":  0,
}
mlflow.log_model_params(model_id=active.model_id, params=app_params)

# COMMAND ----------

# Register the Model-as-Code artifact (Step 6) to Unity Catalog — this creates a new model version.
mlflow.set_registry_uri("databricks-uc")
mv = mlflow.register_model(logged.model_uri, UC_MODEL)
print("Registered", mv.name, "version", mv.version)

# Promote it: set the @champion alias to this version.
from mlflow import MlflowClient
client = MlflowClient(registry_uri="databricks-uc")
client.set_registered_model_alias(name=UC_MODEL, alias="champion", version=mv.version)
print(f"Alias set: {UC_MODEL}@champion -> version {mv.version}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### How to verify it worked
# MAGIC In the MLflow UI: the **Versions** tab lists `llm_only` and `rag_chain` with the logged params; the
# MAGIC **Traces** tab shows which version produced each answer. In Unity Catalog, the model
# MAGIC `unity_airways.rag.ua_rag_chain` shows version `1` with a `@champion` alias. Load by alias to confirm.

# COMMAND ----------

champ = mlflow.langchain.load_model(f"models:/{UC_MODEL}@champion")
print(champ.invoke(EXAMPLE_Q)[:200])
print(f"OK — {UC_MODEL}@champion round-trips from Unity Catalog.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Recap, gotchas and next step
# MAGIC **What you built** — end to end over the Module 04 retriever:
# MAGIC - Chain anatomy + LCEL intuition (05.1) and the `databricks-langchain` integration (05.2).
# MAGIC - An LLM-only baseline and a full **RAG chain**, both traced and versioned (05.3).
# MAGIC - **Buffer memory** injected through a `{chat_history}` slot for multi-turn follow-ups (05.4).
# MAGIC - A **signature** + dependent **resources** for a deployable, auto-authenticating chain (05.5).
# MAGIC - The chain logged as **Model-as-Code** (`%%writefile` + `set_model` + `log_model`) (05.6).
# MAGIC - A **LoggedModel** version registered to UC as `unity_airways.rag.ua_rag_chain` with a `@champion`
# MAGIC   alias (05.7).
# MAGIC
# MAGIC **Gotchas to remember**
# MAGIC - Invoke the string-in chain with a **bare string**; the memory chain takes a **dict**.
# MAGIC - `format_docs` must return a string; end the pipe with `StrOutputParser()`.
# MAGIC - `lc_model=chain` (object) fails on the `VectorStoreRetriever` — pass the **file path** instead.
# MAGIC - Missing `resources=[...]` is a silent trap — logs fine, 401s once deployed.
# MAGIC - Cap/summarize memory so it can't overflow the context window; fold history into the retrieval query.
# MAGIC - Import from **`databricks-langchain`**; register to UC with a three-level `catalog.schema.name`.
# MAGIC
# MAGIC **Next:** the registered `unity_airways.rag.ua_rag_chain@champion` is ready for **Module 08** (MLflow
# MAGIC evaluation with `mlflow.genai.evaluate()`) and **deployment (Module 11)** to a Model Serving endpoint.
