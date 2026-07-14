# Databricks notebook source
# MAGIC %md
# MAGIC # Module 06 lab — tracking → LoggedModel → registry → reproducibility → internals
# MAGIC **Roadmap:** Module 06 (MLflow for GenAI core) · consolidated hands-on lab · [Theory + Hands-on]
# MAGIC
# MAGIC One runnable, end-to-end lab over the module's **hands-on** topics, in order, on the Unity Airways
# MAGIC RAG chain from Module 05. It finishes with the chain tracked, versioned, and aliased `@champion` in
# MAGIC Unity Catalog — ready for Module 07 (tracing) and Module 08 (evaluation).
# MAGIC
# MAGIC | Step | Topic | What you do |
# MAGIC |---|---|---|
# MAGIC | 1 | **06.3** | Tracking — `set_experiment`, `start_run`, `log_params`/`log_metrics`/`log_artifact` |
# MAGIC | 2 | **06.3 / 06.2** | **LoggedModel** — `set_active_model(...)` links a version to its params/metrics |
# MAGIC | 3 | **06.7** | Reproducibility — `infer_signature` + `input_example` + pinned `pip_requirements` |
# MAGIC | 4 | **06.5** | Registry — register + `@champion` alias + tags, load-by-alias (reuse the chain) |
# MAGIC | 5 | **06.7** | Archiving — retire old versions with `lifecycle=archived` tags |
# MAGIC | 6 | **06.8** | Internals — nested runs; backend (tracking) store vs artifact store |
# MAGIC
# MAGIC The cornerstone deep-dive for Step 4 is `06-5-uc-model-registry.py`; this lab reuses the same Module 04
# MAGIC retriever and canonical names and layers the module's tracking, reproducibility, and internals on top.
# MAGIC
# MAGIC ## Prerequisites (read before running)
# MAGIC - **Compute:** **serverless notebook/job**, or a **DBR ML runtime** (15.4 LTS ML or later).
# MAGIC - **MLflow:** **≥ 3.1** is **required** — `set_active_model`/LoggedModel, Models-from-Code, and the
# MAGIC   UC registry flow are MLflow 3 features exercised here.
# MAGIC - **The chain from Module 05:** `unity_airways.rag.ua_rag_chain` (Module 05.6/05.7 logged it as
# MAGIC   Model-as-Code and registered v1 `@champion`). This lab re-logs the **same** chain, then registers the
# MAGIC   **next** version so you can watch tracking → versioning → promotion happen.
# MAGIC - **Vector Search index (Module 04):** `unity_airways.rag.ua_rag_chunks_index` ONLINE on endpoint
# MAGIC   **`unity-airways-vs`**.
# MAGIC - **Chat serving endpoint:** **`databricks-claude-sonnet-4-5`** — confirm on the supported-models page.
# MAGIC - **Unity Catalog:** read access to the index and **write / register access to `unity_airways.rag`**.
# MAGIC - **Secrets:** none — declared `resources=[...]` drive automatic authentication passthrough on deploy.
# MAGIC - **Learner-set identifiers:** edit the constants in Step 0 (including `EXPERIMENT_PATH`).
# MAGIC
# MAGIC > 📌 **MLflow 3 discipline (the whole module in one box):** LoggedModel via `set_active_model()`;
# MAGIC > Models-from-Code via `mlflow.models.set_model()`; register to UC with a three-level name and promote
# MAGIC > with **aliases + tags, not stages**. Evaluation is **`mlflow.genai.evaluate()`** — that is Module 08;
# MAGIC > we only reference it here.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 0. Install libraries and set variables

# COMMAND ----------

# MAGIC %pip install -U "mlflow>=3.1" databricks-langchain databricks-vectorsearch
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

CATALOG       = "unity_airways"
SCHEMA        = "rag"
UC_MODEL      = f"{CATALOG}.{SCHEMA}.ua_rag_chain"          # three-level name — catalog.schema.model
INDEX_NAME    = f"{CATALOG}.{SCHEMA}.ua_rag_chunks_index"   # from Module 04.3
VS_ENDPOINT   = "unity-airways-vs"                          # Vector Search endpoint (Module 04)
CHAT_ENDPOINT = "databricks-claude-sonnet-4-5"             # confirm on the supported-models page

# Learner-set: an experiment path you can write to (usually your own /Users/<you> path).
EXPERIMENT_PATH = "/Users/sourav.banerjee@databricks.com/unity_airways_rag"

EXAMPLE_Q     = "Can I get a refund if I miss my connection?"
APPROVER      = "s.banerjee"                                # who signs off the promotion

print("Experiment    :", EXPERIMENT_PATH)
print("UC model      :", UC_MODEL)
print("Chat endpoint :", CHAT_ENDPOINT)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 1 · 06.3 — Tracking: experiments, params, metrics, artifacts
# MAGIC MLflow's spine is three objects: an **Experiment** (container) holds **Runs** (one execution each);
# MAGIC each run records **params** (inputs like `k`), **metrics** (numbers like groundedness), **tags**
# MAGIC (labels like dataset version), and **artifacts** (files). `log_metric` writes to the **backend store**;
# MAGIC `log_artifact` writes to the **artifact store** (Step 6 explains the split).

# COMMAND ----------

import json
import mlflow

mlflow.set_experiment(EXPERIMENT_PATH)   # container for every Unity Airways RAG iteration

with mlflow.start_run(run_name="rag_chain_k5") as tracking_run:
    # Parameters — the inputs to this run (log_params takes a dict; log_param is the single-value form).
    mlflow.log_params({"k": 5, "temperature": 0, "endpoint": CHAT_ENDPOINT})
    # Metrics — quantitative outputs (placeholder numbers here; real judges arrive in Module 08).
    mlflow.log_metrics({"correctness": 0.86, "groundedness": 0.91})
    # Tags — descriptive labels for organizing / filtering runs.
    mlflow.set_tag("dataset_version", "policies_v3")

    # Artifact — any file produced by the run. We write a tiny eval report and log the file itself.
    with open("eval_report.html", "w") as f:
        f.write("<h3>Unity Airways RAG — smoke eval</h3><p>correctness=0.86, groundedness=0.91</p>")
    mlflow.log_artifact("eval_report.html")

print("Tracked run_id:", tracking_run.info.run_id)

# COMMAND ----------

# MAGIC %md
# MAGIC ### How to verify it worked
# MAGIC Open the Experiment in the MLflow UI → the run shows your **Parameters**, **Metrics**, and the
# MAGIC `eval_report.html` under **Artifacts**. Or read it back programmatically.

# COMMAND ----------

fetched = mlflow.get_run(tracking_run.info.run_id)
print("params :", fetched.data.params)
print("metrics:", fetched.data.metrics)
assert fetched.data.params.get("k") == "5", "Expected param k=5 on the tracked run."
print("OK — params, metrics, tags, and the artifact are recorded.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 2 · 06.3 / 06.2 — LoggedModel: link a version to its params and metrics
# MAGIC **New in MLflow 3:** `mlflow.set_active_model(name=...)` opens a **LoggedModel** — a first-class
# MAGIC version hub. Everything logged while it is active (params, metrics, and, in Step 3, the artifact and
# MAGIC traces) links to *that* version, so iterations are comparable in the **Versions** tab. This is the
# MAGIC object that makes GenAI versioning coherent; runs still exist underneath.

# COMMAND ----------

active = mlflow.set_active_model(name="rag_chain")   # opens (or reuses) the LoggedModel version hub
print("LoggedModel:", active.name, "| model_id:", active.model_id)

# Attach this version's parameters to the LoggedModel (MLflow 3 API).
mlflow.log_model_params(
    model_id=active.model_id,
    params={"llm_endpoint": CHAT_ENDPOINT, "index": INDEX_NAME, "k": "5", "temperature": "0"},
)
print("Params linked to LoggedModel", active.model_id)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 3 · 06.7 — Reproducibility: signature, input example, pinned environment
# MAGIC "Reproducible" is a hope unless you pin the pieces. MLflow logs the **environment** (libraries +
# MAGIC `requirements.txt`) and the **code version**; you add a **signature** (declared input/output schema,
# MAGIC required for served models) and an **input example**, and record the **data (Delta) version** as a tag
# MAGIC so "which data produced this?" has an answer. We reuse the Module 05 Model-as-Code chain so there is a
# MAGIC real artifact to log.

# COMMAND ----------

# MAGIC %%writefile rag_chain.py
# MAGIC # rag_chain.py — the Module 05 RAG chain, self-contained (no notebook globals). Loading re-runs this file.
# MAGIC import mlflow
# MAGIC from databricks_langchain import ChatDatabricks, DatabricksVectorSearch
# MAGIC from langchain_core.prompts import ChatPromptTemplate
# MAGIC from langchain_core.output_parsers import StrOutputParser
# MAGIC from langchain_core.runnables import RunnablePassthrough
# MAGIC
# MAGIC mlflow.langchain.autolog()   # loaded/served copies keep emitting traces
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

from mlflow.models import infer_signature
from mlflow.models.resources import DatabricksServingEndpoint, DatabricksVectorSearchIndex

# Signature: declared input/output shape (string in, string out) — validates requests at load/serve time.
signature = infer_signature(model_input=EXAMPLE_Q, model_output="A short grounded answer.")

# Dependent resources: the services the chain calls, so a DEPLOYED chain auto-authenticates.
resources = [
    DatabricksServingEndpoint(endpoint_name=CHAT_ENDPOINT),   # generation (the "G")
    DatabricksVectorSearchIndex(index_name=INDEX_NAME),       # retrieval (the "R")
]

with mlflow.start_run(run_name="rag_chain_reproducible") as log_run:
    # Record data + code lineage as tags for reproducibility (log the real Delta version in production).
    mlflow.set_tag("delta_source_version", "policies_delta@v7")
    logged = mlflow.langchain.log_model(
        lc_model="rag_chain.py",                 # Models-from-Code: the FILE PATH, not the object
        name="chain",                            # -> runs:/<run_id>/chain
        signature=signature,                     # reproducibility: pinned I/O schema
        input_example=EXAMPLE_Q,                 # reproducibility: a concrete sample request
        resources=resources,                     # auto-auth on deploy
        pip_requirements=[                        # reproducibility: pin the environment
            "mlflow>=3.1", "databricks-langchain", "databricks-vectorsearch",
        ],
    )

print("model_uri:", logged.model_uri)   # MLflow 3 -> models:/<model_id>

# COMMAND ----------

# MAGIC %md
# MAGIC ### How to verify it worked
# MAGIC Open the version's **Artifacts → `MLmodel`** file and confirm it lists your `signature` and the pinned
# MAGIC requirements; the lineage panel shows the source notebook + run. Reloading re-executes the code and
# MAGIC rebuilds the chain — proof nothing was pickled.

# COMMAND ----------

reloaded = mlflow.langchain.load_model(logged.model_uri)
print(reloaded.invoke("Can I get a refund if I cancel my Basic Economy ticket within 24 hours of booking?")[:250])
print("OK — signature + pinned env logged; the chain round-trips from its code.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 4 · 06.5 — Registry: register, `@champion` alias, tags, load-by-alias
# MAGIC Promote the logged chain into Unity Catalog. Point the registry at UC, register (a **new version**),
# MAGIC set the **`@champion` alias** (UC has no stages), tag the version + model, and load by alias — the way
# MAGIC apps and endpoints should reference the model. Full deep-dive: `06-5-uc-model-registry.py`.

# COMMAND ----------

from mlflow import MlflowClient

mlflow.set_registry_uri("databricks-uc")   # registry target = Unity Catalog
client = MlflowClient()

# Register the Model-as-Code artifact — each register call mints a new immutable version.
mv = mlflow.register_model(model_uri=logged.model_uri, name=UC_MODEL)
print("Registered", mv.name, "version", mv.version)

# Promote: set the @champion alias to this version (repoint later to roll forward/back — no client change).
client.set_registered_model_alias(name=UC_MODEL, alias="champion", version=mv.version)

# Tag the version (audit trail) and the model (ownership).
client.set_model_version_tag(UC_MODEL, mv.version, "eval_passed", "true")
client.set_model_version_tag(UC_MODEL, mv.version, "approver", APPROVER)
client.set_registered_model_tag(UC_MODEL, "team", "ml-platform")
print(f"Alias set: {UC_MODEL}@champion -> version {mv.version}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### How to verify it worked
# MAGIC Resolve the alias, then load by alias and invoke. In Unity Catalog the model shows the new version
# MAGIC with a `@champion` alias and your tags.

# COMMAND ----------

resolved = client.get_model_version_by_alias(UC_MODEL, "champion")
print("champion -> version", resolved.version, "| tags:", resolved.tags)

champ = mlflow.langchain.load_model(f"models:/{UC_MODEL}@champion")
print(champ.invoke(EXAMPLE_Q)[:250])
print(f"OK — {UC_MODEL}@champion round-trips from Unity Catalog.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 5 · 06.7 — Archiving: retire old versions with tags
# MAGIC Old versions accumulate. Keep the registry tidy: tag retired versions `lifecycle=archived` so nobody
# MAGIC serves them by accident, and remove aliases from versions you no longer promote. (Deleting truly dead
# MAGIC versions is a separate step; retention is a cost + governance decision, not an afterthought.)

# COMMAND ----------

champ_v = int(client.get_model_version_by_alias(UC_MODEL, "champion").version)
if champ_v > 1:
    prior = champ_v - 1
    client.set_model_version_tag(UC_MODEL, prior, "lifecycle", "archived")
    print(f"Tagged version {prior} as lifecycle=archived (superseded by champion v{champ_v}).")
else:
    print("Only version 1 exists — nothing to archive yet. Register more builds to practice this.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 6 · 06.8 — Internals: nested runs, and the two stores
# MAGIC MLflow separates **metadata** from **files**, which is why it scales and the UI stays fast:
# MAGIC - **Backend (tracking) store** — structured metadata: experiments, runs, params, metrics, tags, and
# MAGIC   (MLflow 3) LoggedModels. On Databricks this is the managed tracking server.
# MAGIC - **Artifact store** — the large files: the model/code, `MLmodel`, signature, `requirements.txt`,
# MAGIC   plots. Backed by cloud object storage (S3 / ADLS / GCS) or a UC Volume.
# MAGIC
# MAGIC `mlflow.log_metric` writes to the **backend**; `log_artifact` / `log_model` write to the **artifact**
# MAGIC store — the run's backend record just *points* at its artifacts. **Nested runs** let one parent group
# MAGIC its children (e.g. a `k`-sweep), which mirrors the nested-spans idea you will meet in tracing (Module 07).

# COMMAND ----------

def evaluate_k(k: int) -> float:
    # Placeholder scoring so the sweep is runnable. REAL judges use mlflow.genai.evaluate() in Module 08.
    return round(0.80 + 0.02 * k, 3)

with mlflow.start_run(run_name="k_sweep") as parent:                 # parent run
    for k in (3, 5, 10):
        with mlflow.start_run(run_name=f"k={k}", nested=True):       # child run
            mlflow.log_param("k", k)
            mlflow.log_metric("groundedness", evaluate_k(k))
print("Parent run:", parent.info.run_id)

# COMMAND ----------

# MAGIC %md
# MAGIC ### How to verify it worked
# MAGIC The MLflow UI shows the three child runs indented under `k_sweep`, each comparable on `groundedness`.
# MAGIC `search_runs` returns them all with a shared `mlflow.parentRunId` tag.

# COMMAND ----------

children = mlflow.search_runs(
    experiment_names=[EXPERIMENT_PATH],
    filter_string=f"tags.mlflow.parentRunId = '{parent.info.run_id}'",
)
print("Nested child runs found:", len(children))
assert len(children) == 3, "Expected 3 nested child runs from the k-sweep."
print("OK — one parent grouped three nested children in the backend store.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Recap, gotchas and next step
# MAGIC **What you built** — the module's hands-on topics, in order, on the Module 05 chain:
# MAGIC - **Tracking (06.3):** an Experiment run with params, metrics, a tag, and an artifact.
# MAGIC - **LoggedModel (06.2/06.3):** `set_active_model()` linking a version to its params/metrics.
# MAGIC - **Reproducibility (06.7):** a signature, an input example, pinned `pip_requirements`, and a data-
# MAGIC   version tag on a Models-from-Code log.
# MAGIC - **Registry (06.5):** registered a new version of `unity_airways.rag.ua_rag_chain`, set `@champion`,
# MAGIC   tagged the version + model, and loaded by alias.
# MAGIC - **Archiving (06.7):** retired the prior version with a `lifecycle=archived` tag.
# MAGIC - **Internals (06.8):** a nested `k`-sweep, and the backend-store vs artifact-store split.
# MAGIC
# MAGIC **Gotchas to remember**
# MAGIC - Promote with **aliases + tags, not stages** — `transition_model_version_stage(...)` is removed on UC.
# MAGIC - Log GenAI chains with **Models-from-Code** (`mlflow.models.set_model()`), never by pickling; pass the
# MAGIC   model **name as a keyword** (`name=`), not the deprecated positional `artifact_path`.
# MAGIC - "Reproducible" needs the **data version** and environment, not just the code.
# MAGIC - A UI-deleted run marks metadata deleted in the **backend** store but does not purge **artifacts** —
# MAGIC   reclaiming that storage is a separate cleanup step.
# MAGIC - Evaluation is **`mlflow.genai.evaluate()`** (Module 08), not `mlflow.evaluate(model_type=...)`.
# MAGIC
# MAGIC **Next:** the chain is tracked, versioned, and aliased `@champion` in Unity Catalog.
# MAGIC **Module 07 adds tracing** (spans over the retriever + LLM steps); **Module 08 evaluates it** with
# MAGIC `mlflow.genai.evaluate()` and gates promotion on the score.
