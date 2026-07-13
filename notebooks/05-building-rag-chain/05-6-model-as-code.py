# Databricks notebook source
# MAGIC %md
# MAGIC # 05.6 ★ — Logging a chain as Model-as-Code vs the LangChain flavor
# MAGIC **Roadmap:** Module 05 (Building and versioning a RAG chain) · Topic 05.6 (cornerstone) · [Theory + Hands-on]
# MAGIC
# MAGIC ## The problem
# MAGIC The RAG chain from 05.3 runs in your notebook. A chain that only runs in your notebook is not a
# MAGIC product — you need to **log** it so a teammate, a serving endpoint, or next month's you can reload the
# MAGIC exact same chain. But a RAG chain has no weights to freeze; it is a **compound system** of live
# MAGIC connections (a Vector Search index client, a serving-endpoint client) that must be re-established
# MAGIC wherever it runs.
# MAGIC
# MAGIC ## What you will build
# MAGIC The one fork that matters, both ways through the same function `mlflow.langchain.log_model(...)`:
# MAGIC - **The brittle way** (shown, not shipped): pass the **in-memory `chain` object**. MLflow tries to
# MAGIC   cloudpickle it, the `DatabricksVectorSearch` retriever will not serialize, and you hit
# MAGIC   `VectorStoreRetriever ... a loader_fn must be provided`.
# MAGIC - **The recommended way — Models-from-Code:** put the chain in a `.py` file whose last line is
# MAGIC   `mlflow.models.set_model(chain)`, then log with `lc_model="rag_chain.py"`. MLflow stores the
# MAGIC   **code**, not a pickle, and rebuilds the chain fresh at load time. You attach dependent
# MAGIC   **resources** for auto-auth, add a **signature**, and **register to Unity Catalog**.
# MAGIC
# MAGIC ### Prerequisites (read before running)
# MAGIC - **Compute:** **serverless notebook/job**, or a **DBR ML runtime** (15.4 LTS ML or later).
# MAGIC - **MLflow:** **≥ 3.1** is required (Models-from-Code, `mlflow.models.set_model`, MLflow 3 logging).
# MAGIC - **Vector Search index (from Module 04):** `unity_airways.rag.ua_rag_chunks_index` ONLINE on endpoint
# MAGIC   **`unity-airways-vs`**; the retriever the chain calls comes from Module 04.
# MAGIC - **Chat serving endpoint:** **`databricks-claude-sonnet-4-5`** — confirm on the supported-models page.
# MAGIC - **Unity Catalog:** read access to the index and **write access to `unity_airways.rag`** to register
# MAGIC   the model as `unity_airways.rag.ua_rag_chain`.
# MAGIC - **Secrets:** none — declared `resources=[...]` drive automatic authentication passthrough on deploy.
# MAGIC - **Learner-set identifiers:** edit the constants in Step 0.
# MAGIC
# MAGIC > 📌 **Naming trap:** import chain classes from **`databricks-langchain`** and resource classes from
# MAGIC > **`mlflow.models.resources`**. The chain is the same string-in chain from 05.3.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 0. Install libraries and set variables
# MAGIC `mlflow` (≥ 3.1, for Models-from-Code + resources), `databricks-langchain`, `databricks-vectorsearch`.

# COMMAND ----------

# MAGIC %pip install -U "mlflow>=3.1" databricks-langchain databricks-vectorsearch
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

CATALOG       = "unity_airways"
SCHEMA        = "rag"
INDEX_NAME    = f"{CATALOG}.{SCHEMA}.ua_rag_chunks_index"   # from Module 04.3
VS_ENDPOINT   = "unity-airways-vs"                          # Vector Search endpoint (Module 04)
CHAT_ENDPOINT = "databricks-claude-sonnet-4-5"             # confirm on the supported-models page
UC_MODEL      = f"{CATALOG}.{SCHEMA}.ua_rag_chain"          # where we register the chain

EXAMPLE_Q = "Can I get a refund if I miss my connection?"   # input example / signature sample

print("Index         :", INDEX_NAME)
print("Chat endpoint :", CHAT_ENDPOINT)
print("UC model      :", UC_MODEL)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Materialize the chain into `rag_chain.py` (Models-from-Code)
# MAGIC `%%writefile` writes the cell body to a file next to the notebook. This is the **entire chain**, with
# MAGIC no notebook state — the same string-in chain from 05.3, plus `mlflow.langchain.autolog()` so loaded
# MAGIC copies stay traceable, and ending in **`mlflow.models.set_model(chain)`** — the crucial line that
# MAGIC tells MLflow *which* object in the file is the model.
# MAGIC
# MAGIC > 💡 **TIP:** in production, read `index_name` / endpoint names via `mlflow.models.ModelConfig` and
# MAGIC > pass `model_config=` at log time so the same file logs cleanly in dev/stage/prod. We hardcode the
# MAGIC > canonical names here to keep the mechanics front-and-center.

# COMMAND ----------

# MAGIC %%writefile rag_chain.py
# MAGIC # rag_chain.py — the entire RAG chain lives here, self-contained (no notebook globals).
# MAGIC # Loading this model RE-EXECUTES this file, rebuilding a fresh retriever + LLM client. Nothing pickles.
# MAGIC import mlflow
# MAGIC from databricks_langchain import ChatDatabricks, DatabricksVectorSearch
# MAGIC from langchain_core.prompts import ChatPromptTemplate
# MAGIC from langchain_core.output_parsers import StrOutputParser
# MAGIC from langchain_core.runnables import RunnablePassthrough
# MAGIC
# MAGIC mlflow.langchain.autolog()   # loaded/served copies keep emitting traces too
# MAGIC
# MAGIC # Canonical Unity Airways names (in prod: read these via mlflow.models.ModelConfig).
# MAGIC INDEX_NAME    = "unity_airways.rag.ua_rag_chunks_index"
# MAGIC VS_ENDPOINT   = "unity-airways-vs"
# MAGIC CHAT_ENDPOINT = "databricks-claude-sonnet-4-5"
# MAGIC
# MAGIC # The "R": the Module 04 index wrapped as a retriever. k=5 nearest chunks; source_doc for citation.
# MAGIC retriever = DatabricksVectorSearch(
# MAGIC     endpoint=VS_ENDPOINT,
# MAGIC     index_name=INDEX_NAME,
# MAGIC     columns=["chunk_id", "content", "source_doc"],
# MAGIC ).as_retriever(search_kwargs={"k": 5})
# MAGIC
# MAGIC def format_docs(docs):
# MAGIC     # retriever returns Documents; the prompt needs one string
# MAGIC     return "\n\n".join(d.page_content for d in docs)
# MAGIC
# MAGIC prompt = ChatPromptTemplate.from_messages([
# MAGIC     ("system",
# MAGIC      "You are the Unity Airways policy assistant. Answer the question using ONLY the "
# MAGIC      "context below. If the context does not contain the answer, say you don't know. "
# MAGIC      "Cite the source_doc you used.\n\n"
# MAGIC      "Context:\n{context}"),
# MAGIC     ("human", "{question}"),
# MAGIC ])
# MAGIC
# MAGIC llm = ChatDatabricks(endpoint=CHAT_ENDPOINT, temperature=0)
# MAGIC
# MAGIC # The SAME string-in LCEL chain as 05.3 — invoke with a bare string.
# MAGIC chain = (
# MAGIC     {"context": retriever | format_docs, "question": RunnablePassthrough()}
# MAGIC     | prompt
# MAGIC     | llm
# MAGIC     | StrOutputParser()
# MAGIC )
# MAGIC
# MAGIC mlflow.models.set_model(chain)   # ← THIS is the model MLflow logs

# COMMAND ----------

# MAGIC %md
# MAGIC ### How to verify the file works (catch errors before logging)
# MAGIC Import and invoke it. This runs `rag_chain.py` exactly the way MLflow will at load time, so an import
# MAGIC or config error shows up here while it is cheap to fix.

# COMMAND ----------

import sys, os
sys.path.insert(0, os.getcwd())   # make the freshly written rag_chain.py importable

from rag_chain import chain        # runs the file, builds a fresh chain
print(chain.invoke(EXAMPLE_Q)[:300])

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Build the signature and declare dependent resources
# MAGIC The **signature** pins the input/output shape (a string in, a string out) so requests are validated
# MAGIC at load and serve time. **Dependent resources** record which Databricks services the chain calls, so
# MAGIC deployment can mint scoped, short-lived credentials — the "automatic authentication passthrough". Get
# MAGIC this list wrong and the model logs fine but throws an **auth error at inference time**, once deployed.

# COMMAND ----------

from mlflow.models import infer_signature
from mlflow.models.resources import DatabricksVectorSearchIndex, DatabricksServingEndpoint

signature = infer_signature(model_input=EXAMPLE_Q, model_output="A short grounded answer.")

# NOTE: resources classes confirmed in Book 1 Ch4; re-verify kwargs against current MLflow docs.
resources = [
    DatabricksVectorSearchIndex(index_name=INDEX_NAME),      # retrieval (the "R")
    DatabricksServingEndpoint(endpoint_name=CHAT_ENDPOINT),  # generation (the "G")
]

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Log as Models-from-Code
# MAGIC `lc_model=` is the **path to the file**, not the object. MLflow copies `rag_chain.py` into the run and
# MAGIC records a `python_function` loader that re-runs it later — no cloudpickle, nothing fragile to unpickle.

# COMMAND ----------

with mlflow.start_run() as run:
    logged = mlflow.langchain.log_model(
        lc_model="rag_chain.py",                 # ← code file, NOT the chain object
        name="chain",                            # the model's name within the run (MLflow 3)
        signature=signature,
        input_example=EXAMPLE_Q,
        resources=resources,                     # auto-auth on deploy
        pip_requirements=["mlflow>=3.1", "databricks-langchain", "databricks-vectorsearch"],
        # code_paths=["helpers/"],               # add if rag_chain.py imports local helper modules
    )

print("model_uri:", logged.model_uri)   # MLflow 3 -> models:/<model_id>

# COMMAND ----------

# MAGIC %md
# MAGIC ### How to verify it worked (reload and invoke)
# MAGIC `load_model` **re-executes** `rag_chain.py`, rebuilding a fresh retriever + LLM client against the
# MAGIC live services — proof there is no pickle involved. The answer should match the notebook.

# COMMAND ----------

loaded = mlflow.langchain.load_model(logged.model_uri)
print(loaded.invoke("What is the checked baggage allowance on Basic Economy?")[:300])

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Register to Unity Catalog
# MAGIC Point the registry at UC, then register the run's model under a three-level name so it is governed,
# MAGIC versioned, and deployable. Loading the UC model back and invoking it proves the round-trip.

# COMMAND ----------

mlflow.set_registry_uri("databricks-uc")

# Register the logged run's model (logged.model_uri, an MLflow 3 models:/<model_id> URI).
mv = mlflow.register_model(logged.model_uri, UC_MODEL)
print(mv.name, "version", mv.version)   # unity_airways.rag.ua_rag_chain, 1

# One-shot alternative: pass registered_model_name=UC_MODEL straight to log_model(...) to log + register
# in a single call. Use the standalone register_model when you want to log first and register a chosen run.

# COMMAND ----------

# Round-trip proof: load the registered UC version and invoke it.
uc_loaded = mlflow.langchain.load_model(f"models:/{UC_MODEL}/{mv.version}")
print(uc_loaded.invoke(EXAMPLE_Q)[:300])
print("OK — chain registered to UC and round-trips from the registry.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Contrast — the brittle in-memory-object path (so you recognize the error)
# MAGIC This is the path every scikit-learn tutorial teaches: hand `log_model` the **object** and let MLflow
# MAGIC cloudpickle it. That is fine for a bag of numbers. Your `DatabricksVectorSearch` retriever wraps a
# MAGIC **live connection** to the Vector Search endpoint, so LangChain cannot serialize it and MLflow throws.
# MAGIC The cell below is **commented on purpose** — uncomment only to see the failure.

# COMMAND ----------

# DON'T ship this. Shown so you know the failure mode and why Models-from-Code is preferred.
# with mlflow.start_run():
#     mlflow.langchain.log_model(lc_model=chain, name="chain",   # <- the OBJECT, not the path
#                                signature=signature, resources=resources)
# -> MlflowException: Failed to save runnable sequence: ...
#    'VectorStoreRetriever -- For VectorStoreRetriever models, a `loader_fn` must be provided.'
#
# Fix A (messy, does not scale): add loader_fn=load_retriever to rebuild the retriever at load time —
#   you discover each unpicklable piece by trial and error, and every new live client restarts the loop.
# Fix B (do this): log the .py file as in Step 3. Models-from-Code stores the recipe, not a snapshot.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6. Forward-ref to 05.7 — LoggedModel versioning
# MAGIC New in MLflow 3: `mlflow.set_active_model(name=...)` opens a **LoggedModel** (a version hub) so
# MAGIC everything logged after it — traces, params, evals, the artifact — links to that version. The full
# MAGIC treatment (register a new version, set a `@champion` alias) is in the consolidated lab `05-module-lab.py`.

# COMMAND ----------

active = mlflow.set_active_model(name="ua_rag_chain_v1")
print(active.name, active.model_id)
# ...then pass model_id=active.model_id into log_model(...) to link the artifact to this version.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 7. Recap, gotchas and next step
# MAGIC **What you built**
# MAGIC - `rag_chain.py` — the string-in chain from 05.3, ending in `mlflow.models.set_model(chain)`.
# MAGIC - A **Models-from-Code** log (`lc_model="rag_chain.py"`) with a **signature**, an **input example**,
# MAGIC   and dependent **resources** (the index + the serving endpoint) for auto-auth.
# MAGIC - The chain **registered to Unity Catalog** as `unity_airways.rag.ua_rag_chain`, reloaded and invoked
# MAGIC   to prove it round-trips.
# MAGIC
# MAGIC **Gotchas to remember**
# MAGIC - `lc_model=chain` (the object) serializes and fails on the `VectorStoreRetriever` — pass the **file
# MAGIC   path** instead.
# MAGIC - `mlflow.models.set_model(...)` must be the **last executable line** of the file, and the file must
# MAGIC   be **self-contained** (imports + config, no stray notebook globals).
# MAGIC - Omitting `resources=[...]` logs fine but **401s at inference** once deployed — declare every service.
# MAGIC - Register with `mlflow.set_registry_uri("databricks-uc")` and a three-level `catalog.schema.name`.
# MAGIC - Import chain classes from **`databricks-langchain`**, resource classes from `mlflow.models.resources`.
# MAGIC
# MAGIC **Next:** the consolidated lab `05-module-lab.py` walks 05.1–05.7 in order — chain anatomy, memory,
# MAGIC packaging, Model-as-Code, and **LoggedModel versioning with a `@champion` alias** on this same UC model.
