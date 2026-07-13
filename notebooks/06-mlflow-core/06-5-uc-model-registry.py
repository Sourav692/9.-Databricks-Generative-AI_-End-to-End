# Databricks notebook source
# MAGIC %md
# MAGIC # 06.5 ★ — Unity Catalog Model Registry: registration, aliases, tags
# MAGIC **Roadmap:** Module 06 (MLflow for GenAI core) · Topic 06.5 (cornerstone) · [Theory + Hands-on]
# MAGIC
# MAGIC ## The problem
# MAGIC In Module 05 you logged the Unity Airways RAG chain. A logged run artifact
# MAGIC (`runs:/<run_id>/chain`) is tied to **one run in one workspace** — it answers "what did this
# MAGIC experiment produce?", not the questions production asks: *which build is approved right now, who
# MAGIC may serve it, and how do I ship a fix without editing every caller?* This notebook promotes that
# MAGIC chain into a **governed, versioned, deployable** object in Unity Catalog.
# MAGIC
# MAGIC ## What you will build
# MAGIC - Point the MLflow registry at Unity Catalog once (`set_registry_uri("databricks-uc")`).
# MAGIC - **Register** the Module 05 chain into `unity_airways.rag.ua_rag_chain` — each register call mints a
# MAGIC   new **immutable version**.
# MAGIC - Set the **`@champion` alias** (the movable "this one is live" pointer — UC has **no stages**).
# MAGIC - Attach **tags** (eval score, approver, ticket on the version; team on the model) as your audit trail.
# MAGIC - **Load by alias** and `.invoke(...)`, resolve the alias with `get_model_version_by_alias`, and
# MAGIC   `GRANT EXECUTE ON MODEL` to a serving service principal.
# MAGIC
# MAGIC ### Prerequisites (read before running)
# MAGIC - **Compute:** **serverless notebook/job**, or a **DBR ML runtime** (15.4 LTS ML or later).
# MAGIC - **MLflow:** **≥ 3.1** (LoggedModel, Models-from-Code, MLflow 3 logging + registry).
# MAGIC - **The registered chain from Module 05:** `unity_airways.rag.ua_rag_chain` — Module 05.6/05.7 logged
# MAGIC   the chain as Model-as-Code and registered **version 1** with a `@champion` alias. This notebook
# MAGIC   re-logs the **same** chain only to obtain a fresh `logged.model_uri`, then registers it as the
# MAGIC   **next** version so you can watch versioning + promotion happen.
# MAGIC - **Vector Search index (Module 04):** `unity_airways.rag.ua_rag_chunks_index` ONLINE on endpoint
# MAGIC   **`unity-airways-vs`**.
# MAGIC - **Chat serving endpoint:** **`databricks-claude-sonnet-4-5`** — confirm on the supported-models page.
# MAGIC - **Unity Catalog:** `USE CATALOG` on `unity_airways`, `USE SCHEMA` on `rag`, and `CREATE MODEL` /
# MAGIC   ownership on `unity_airways.rag` to register versions and move aliases/tags.
# MAGIC - **Secrets:** none — declared `resources=[...]` drive automatic authentication passthrough on deploy.
# MAGIC - **Learner-set identifiers:** edit the constants in Step 0.
# MAGIC
# MAGIC > 📌 **The one rule for this topic (MLflow 3 + UC):** mark "which version is live" with an **alias**,
# MAGIC > never a stage. `transition_model_version_stage(...)` is **legacy** — there is no stage to move to on
# MAGIC > a UC model. Lifecycle = **aliases + tags**.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 0. Install libraries and set variables
# MAGIC `mlflow` (≥ 3.1, for MLflow 3 logging + UC registry), `databricks-langchain`, `databricks-vectorsearch`.

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

EXAMPLE_Q     = "Can I get a refund on a Basic Economy fare?"   # signature sample + smoke test
APPROVER      = "s.banerjee"                                # learner-set: who signs off the promotion
SERVING_SP    = "sp-ua-serving"                             # learner-set: serving service principal

print("UC model      :", UC_MODEL)
print("Chat endpoint :", CHAT_ENDPOINT)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Point the registry at Unity Catalog
# MAGIC One line flips the registry target for the whole session. After this, every `register_model` /
# MAGIC alias / tag call writes to **Unity Catalog**, not the legacy per-workspace registry — so you inherit
# MAGIC RBAC, lineage, and cross-workspace access for free.

# COMMAND ----------

import mlflow
from mlflow import MlflowClient

mlflow.set_registry_uri("databricks-uc")   # registry target = Unity Catalog (do this before any register/alias/tag)
client = MlflowClient()
# Off-platform you would also set mlflow.set_tracking_uri("databricks"); on a Databricks notebook it is already set.
print("Registry URI:", mlflow.get_registry_uri())

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Reuse the Module 05 chain to get a `logged.model_uri`
# MAGIC This is the **same** Model-as-Code chain from 05.6 (self-contained `.py` ending in
# MAGIC `mlflow.models.set_model(chain)`). We re-log it here only so this notebook is runnable end to end and
# MAGIC we have a fresh `logged.model_uri` to register. The registry mechanics — Steps 3+ — are the lesson.

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
from mlflow.models.resources import DatabricksVectorSearchIndex, DatabricksServingEndpoint

signature = infer_signature(model_input=EXAMPLE_Q, model_output="A short grounded answer.")
resources = [
    DatabricksVectorSearchIndex(index_name=INDEX_NAME),      # retrieval (the "R")
    DatabricksServingEndpoint(endpoint_name=CHAT_ENDPOINT),  # generation (the "G")
]

with mlflow.start_run(run_name="ua_rag_chain_registry_demo") as run:
    logged = mlflow.langchain.log_model(
        lc_model="rag_chain.py",                 # Models-from-Code: the FILE PATH, not the object
        name="chain",                            # -> runs:/<run_id>/chain
        signature=signature,
        input_example=EXAMPLE_Q,
        resources=resources,                     # auto-auth on deploy
        pip_requirements=["mlflow>=3.1", "databricks-langchain", "databricks-vectorsearch"],
    )

print("run_id     :", run.info.run_id)
print("model_uri  :", logged.model_uri)   # MLflow 3 -> models:/<model_id>

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Register into Unity Catalog (creates the next version)
# MAGIC `register_model` promotes a **logged** model into UC under the three-level name. Each call mints a new
# MAGIC **immutable** integer version. Module 05 already created v1, so this call produces v2 (then v3, …) —
# MAGIC old versions stay exactly as they were, which is what makes rollback trustworthy.

# COMMAND ----------

# model_uri can be the MLflow 3 LoggedModel URI (models:/<model_id>) or a run artifact URI
# (f"runs:/{run.info.run_id}/chain"). Both resolve to the same stored artifacts.
mv = mlflow.register_model(model_uri=logged.model_uri, name=UC_MODEL)
print(mv.name, "version", mv.version)   # unity_airways.rag.ua_rag_chain <next version>

# COMMAND ----------

# MAGIC %md
# MAGIC ### How to verify it worked
# MAGIC `get_registered_model` returns the model, and the new version appears in Catalog Explorer under
# MAGIC `unity_airways.rag` → Models. Listing versions shows the full immutable history.

# COMMAND ----------

rm = client.get_registered_model(UC_MODEL)
print("Registered model:", rm.name)
versions = client.search_model_versions(f"name='{UC_MODEL}'")
print("Existing versions:", sorted(int(v.version) for v in versions))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Promote — set the `@champion` alias (this replaces stages)
# MAGIC An **alias** is a human-named, movable pointer to exactly one version. Setting `champion` to the new
# MAGIC version *is* the promotion. Repoint it later to roll forward or back — consumers that load `@champion`
# MAGIC follow with **zero code changes**.

# COMMAND ----------

client.set_registered_model_alias(name=UC_MODEL, alias="champion", version=mv.version)
print(f"Alias set: {UC_MODEL}@champion -> version {mv.version}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### How to verify it worked
# MAGIC Resolve the alias back to a concrete version with `get_model_version_by_alias`.

# COMMAND ----------

resolved = client.get_model_version_by_alias(UC_MODEL, "champion")
print("champion currently points at version:", resolved.version)
assert resolved.version == mv.version, "champion did not resolve to the version we just promoted."

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Load by alias — how apps and endpoints should reference the model
# MAGIC Consumers load `models:/<name>@champion`, never a hard-coded version number. `load_model` re-executes
# MAGIC `rag_chain.py`, rebuilding a fresh retriever + LLM client against the live services.
# MAGIC
# MAGIC > ⚠️ **GOTCHA:** three `models:/` shapes, three meanings — `@alias` follows promotions,
# MAGIC > `/version` freezes on one build, and `models:/<model_id>` loads an MLflow 3 LoggedModel by id.
# MAGIC > Serving a `@alias` URI means the endpoint moves when you repoint; serving `/version` pins it.

# COMMAND ----------

champ = mlflow.langchain.load_model(f"models:/{UC_MODEL}@champion")
print(champ.invoke(EXAMPLE_Q)[:300])
print(f"OK — {UC_MODEL}@champion round-trips from Unity Catalog.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6. Tag the version and the model (your audit trail)
# MAGIC Two scopes, two APIs. **Version tags** record one build's facts — the eval score, who approved it, the
# MAGIC change ticket that authorized the promotion. **Registered-model tags** describe the product as a whole
# MAGIC — owning team, project. Tags are the durable link between "we promoted this version" and "here is the
# MAGIC evidence and who signed off."

# COMMAND ----------

# Version-scoped tags — the promotion / audit record for THIS build.
client.set_model_version_tag(UC_MODEL, mv.version, "eval_correctness", "0.91")
client.set_model_version_tag(UC_MODEL, mv.version, "approver", APPROVER)
client.set_model_version_tag(UC_MODEL, mv.version, "change_ticket", "CHG-2187")

# Registered-model-scoped tags — describe the model as a product (do not change per version).
client.set_registered_model_tag(UC_MODEL, "team", "ml-platform")
client.set_registered_model_tag(UC_MODEL, "project", "unity-airways-assistant")

print("Version tags:", client.get_model_version(UC_MODEL, mv.version).tags)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 7. Roll back in one line (no redeploy)
# MAGIC A regression in the live build? Repoint `champion` to a known-good version. Every `@champion` consumer
# MAGIC follows instantly; the bad version is untouched and inspectable. (Runs only if a prior version exists.)

# COMMAND ----------

champ_v = int(client.get_model_version_by_alias(UC_MODEL, "champion").version)
if champ_v > 1:
    client.set_registered_model_alias(UC_MODEL, "champion", champ_v - 1)   # roll back one version
    print(f"Rolled back: {UC_MODEL}@champion -> version {champ_v - 1}")
    # ... put it back on the new build for the rest of the notebook:
    client.set_registered_model_alias(UC_MODEL, "champion", champ_v)
    print(f"Restored:    {UC_MODEL}@champion -> version {champ_v}")
else:
    print("Only version 1 exists — register a second build to practice rollback.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 8. Govern — grant a serving service principal permission to load it
# MAGIC The registered model is a UC securable, so access is **SQL grants**, not code. A serving endpoint's
# MAGIC service principal needs **`EXECUTE`** to load/serve, plus traversal grants on the container objects.
# MAGIC Setting or moving aliases/tags requires ownership or `MANAGE` — keep those separate from serve access.

# COMMAND ----------

# MAGIC %sql
# MAGIC -- Edit `sp-ua-serving` to your serving endpoint's service principal.
# MAGIC GRANT USE CATALOG ON CATALOG unity_airways            TO `sp-ua-serving`;
# MAGIC GRANT USE SCHEMA  ON SCHEMA  unity_airways.rag        TO `sp-ua-serving`;
# MAGIC GRANT EXECUTE     ON MODEL   unity_airways.rag.ua_rag_chain TO `sp-ua-serving`;

# COMMAND ----------

# MAGIC %md
# MAGIC ## 9. Contrast — the legacy stage call you must recognize but never use on UC
# MAGIC Most MLflow tutorials (and Book 2 Ch5) still show `transition_model_version_stage(...)` through the
# MAGIC fixed `None → Staging → Production → Archived` ladder. On a **UC** model those stages were **removed** —
# MAGIC the call has no valid target. The correct UC equivalent is an alias. The cell below is commented on
# MAGIC purpose; it is here so you recognize stage language as legacy.

# COMMAND ----------

# LEGACY / Workspace Model Registry (MLflow 2). Do NOT use on a UC model — there is no stage to move to.
# client.transition_model_version_stage(name="ua_rag_chain", version=mv.version, stage="Production")
#
# Correct UC equivalent — a named, movable pointer (NOT the removed "Production" stage):
client.set_registered_model_alias(UC_MODEL, "production", mv.version)
print(f"UC-native promotion: {UC_MODEL}@production -> version {mv.version} (a string pointer, not a stage)")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 10. Recap, gotchas and next step
# MAGIC **What you built**
# MAGIC - Pointed the registry at UC with `mlflow.set_registry_uri("databricks-uc")`.
# MAGIC - **Registered** the Module 05 chain as a new **version** of `unity_airways.rag.ua_rag_chain`.
# MAGIC - Set the **`@champion` alias**, resolved it with `get_model_version_by_alias`, and **loaded by alias**.
# MAGIC - Tagged the **version** (eval score, approver, ticket) and the **model** (team, project).
# MAGIC - Rolled back by repointing the alias, and `GRANT EXECUTE ON MODEL` to a serving principal.
# MAGIC
# MAGIC **Gotchas to remember**
# MAGIC - The whole lesson is three moves: **name it** (`catalog.schema.model`), **version it** (every register),
# MAGIC   **point at it** (an alias, never a stage). Serving, rollback, and audit all read the alias.
# MAGIC - `transition_model_version_stage(...)` and `Staging`/`Production` **stages** are legacy — removed on UC.
# MAGIC - A `production` **alias** is just a string pointer you set; it is **not** the old Production stage.
# MAGIC - Deploying from `runs:/<run_id>/...` pins prod to a run id with no governance — register and deploy
# MAGIC   `models:/<name>@champion` instead.
# MAGIC - `EXECUTE` (plus `USE CATALOG` / `USE SCHEMA`) is required to load; read access alone is not enough.
# MAGIC
# MAGIC **Next:** the consolidated lab `06-module-lab.py` walks the module's hands-on topics in order —
# MAGIC tracking (06.3), this registry flow (06.5), reproducibility (06.7), and internals/nested runs (06.8).
# MAGIC Then **Module 07** adds tracing and **Module 08** evaluates the chain with `mlflow.genai.evaluate()`.
