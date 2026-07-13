# Databricks notebook source
# MAGIC %md
# MAGIC # 11.1 ★ — Model Serving endpoints for GenAI
# MAGIC **Roadmap:** Module 11 (Deployment and serving) · Topic 11.1 (cornerstone) · [Hands-on] (+ [Theory])
# MAGIC
# MAGIC ## The problem
# MAGIC The Unity Airways support agent from Module 09 answers well **in a notebook** — but a notebook is not a
# MAGIC service. It needs a running cluster, it is tied to your identity, and no downstream app (the booking site,
# MAGIC the IVR phone system, an overnight batch job) can call it. This notebook turns the registered agent
# MAGIC `unity_airways.rag.ua_support_agent` into a **live, governed, autoscaling REST endpoint** with Databricks
# MAGIC Model Serving.
# MAGIC
# MAGIC ## What you will build
# MAGIC 1. Resolve (or, if you skipped Module 09, **stub + register**) the agent in Unity Catalog.
# MAGIC 2. Deploy it with **one call** — `from databricks import agents; agents.deploy(...)` — which also stands up
# MAGIC    the **Review App**, a **feedback model**, and turns on **tracing + inference tables + monitoring**.
# MAGIC 3. See the **alternative custom-model path** (databricks-sdk / mlflow.deployments) for non-agent models.
# MAGIC 4. **Poll** for readiness, then **invoke** the endpoint three ways: programmatic SDK, raw **REST**, and
# MAGIC    SQL **`ai_query`** for batch inference — with `return_trace` turned on while integrating.
# MAGIC
# MAGIC ### Prerequisites (read before running)
# MAGIC - **Compute:** **serverless notebook/job**, or a **DBR ML runtime** (15.4 LTS ML or later; DBR 16.1+ ships
# MAGIC   the GenAI packages pre-installed).
# MAGIC - **MLflow:** **>= 3.1** (`mlflow[databricks]`) — Models-from-Code, `ResponsesAgent`, UC registry.
# MAGIC - **Libraries:** `databricks-agents` (the `agents.deploy` path), `databricks-sdk`, `databricks-langchain`
# MAGIC   (only needed for the Module-09 agent / the stub fallback).
# MAGIC - **Unity Catalog:** the agent registered at **`unity_airways.rag.ua_support_agent`** (from `09-6-responsesagent.py`).
# MAGIC   If it is not there, Section 3 writes a **minimal stub agent** and registers it so this notebook still runs
# MAGIC   end-to-end. Rights needed: `USE CATALOG`/`USE SCHEMA` on `unity_airways.rag`, `CREATE MODEL` (only if you
# MAGIC   register the stub), and permission to **create a serving endpoint**.
# MAGIC - **Chat serving endpoint:** **`databricks-claude-sonnet-4-5`** — confirm on the supported-models page.
# MAGIC - **Secrets:** none required. `environment_vars` may reference `{{secrets/<scope>/<key>}}`; that is shown
# MAGIC   as a commented example so a missing scope does not break your first deploy.
# MAGIC
# MAGIC > 📌 **The one rule of this topic:** for a GenAI **agent**, `agents.deploy(uc_model, version)` is the single
# MAGIC > call that creates the endpoint **and** the Review App **and** the feedback model, and enables tracing,
# MAGIC > inference tables, and monitoring. Read the generated endpoint name from the **deploy output** — never
# MAGIC > hardcode a guess.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Setup — install libraries and restart Python
# MAGIC `mlflow[databricks]` (>= 3.1) for the UC registry + Models-from-Code, `databricks-agents` for
# MAGIC `agents.deploy`, `databricks-sdk` for the `WorkspaceClient`, `databricks-langchain` for the agent's
# MAGIC `ChatDatabricks` client (used by the Module-09 agent and by the stub fallback below).

# COMMAND ----------

# MAGIC %pip install -U "mlflow[databricks]>=3.1" databricks-agents databricks-sdk databricks-langchain
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Identifiers and Unity Catalog registry
# MAGIC Widgets keep the catalog/schema editable without touching code. Point the MLflow registry at Unity
# MAGIC Catalog so every model reference resolves to a governed three-level name.

# COMMAND ----------

dbutils.widgets.text("catalog", "unity_airways", "Catalog")
dbutils.widgets.text("schema", "rag", "Schema")
dbutils.widgets.text("model", "ua_support_agent", "Model name")

CATALOG = dbutils.widgets.get("catalog")
SCHEMA = dbutils.widgets.get("schema")
MODEL = dbutils.widgets.get("model")

UC_MODEL = f"{CATALOG}.{SCHEMA}.{MODEL}"       # three-level name — catalog.schema.model
LLM_ENDPOINT = "databricks-claude-sonnet-4-5"  # the Foundation Model the agent calls; confirm on supported-models
FRIENDLY_NAME = "ua-support-agent"             # friendly name we use for the *custom-model* endpoint path (Section 5)

import mlflow
mlflow.set_registry_uri("databricks-uc")       # models resolve against Unity Catalog, not the workspace registry

print("UC model     :", UC_MODEL)
print("LLM endpoint :", LLM_ENDPOINT)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Resolve the registered agent (or stub + register a minimal one)
# MAGIC The thing we deploy is a **version** of the UC-registered agent. First we look up the latest version. If
# MAGIC the model does not exist yet (you jumped here without running `09-6-responsesagent.py`), the cells below
# MAGIC write a **minimal stub `ResponsesAgent`** and register it, so the deploy path still runs top-to-bottom.
# MAGIC
# MAGIC > 💡 **TIP:** the stub is a single-turn agent that just calls the LLM — no retriever, no tools — so it needs
# MAGIC > only the LLM serving endpoint as a resource. For the *real* tool-using agent (AI Search retriever + UC
# MAGIC > function), run **Module 09.6** first; then this notebook picks up that version automatically.

# COMMAND ----------

from mlflow.tracking import MlflowClient

client = MlflowClient(registry_uri="databricks-uc")


def latest_version(model_name):
    """Return the highest registered version number, or None if the model does not exist yet."""
    try:
        versions = client.search_model_versions(f"name='{model_name}'")
    except Exception as e:
        print("Lookup failed (model may not exist yet):", e)
        return None
    return max((int(v.version) for v in versions), default=None)


EXISTING_VERSION = latest_version(UC_MODEL)
NEED_STUB = EXISTING_VERSION is None
print("Existing version:", EXISTING_VERSION, "| will register stub:", NEED_STUB)

# COMMAND ----------

# MAGIC %md
# MAGIC ### 3a. Write the stub agent file (Models-from-Code)
# MAGIC `%%writefile` drops a self-contained `ua_support_agent_stub.py` next to the notebook. It reloads cleanly at serving time
# MAGIC because it has no notebook globals. This mirrors the 09.6 pattern (`ResponsesAgent` + `set_model`) but
# MAGIC drops the tools so it runs anywhere. **Skip 3a/3b if the model already exists.**

# COMMAND ----------

# MAGIC %%writefile ua_support_agent_stub.py
# MAGIC # ua_support_agent_stub.py — a minimal, self-contained ResponsesAgent for Module 11.
# MAGIC # For the full tool-using agent, see 09-6-responsesagent.py. Loading this file re-executes it.
# MAGIC import uuid
# MAGIC from typing import Generator
# MAGIC
# MAGIC import mlflow
# MAGIC from databricks_langchain import ChatDatabricks
# MAGIC from mlflow.pyfunc import ResponsesAgent
# MAGIC from mlflow.types.responses import (
# MAGIC     ResponsesAgentRequest, ResponsesAgentResponse, ResponsesAgentStreamEvent,
# MAGIC )
# MAGIC
# MAGIC mlflow.langchain.autolog()   # served copies keep emitting traces for every call
# MAGIC
# MAGIC LLM_ENDPOINT = "databricks-claude-sonnet-4-5"   # confirm on the supported-models page
# MAGIC SYSTEM_PROMPT = (
# MAGIC     "You are the Unity Airways support assistant. Answer flight, refund, and baggage questions "
# MAGIC     "concisely and politely. If you are unsure, say so."
# MAGIC )
# MAGIC
# MAGIC
# MAGIC class UASupportAgentStub(ResponsesAgent):
# MAGIC     """Single-turn agent: map Responses input -> chat messages -> ChatDatabricks -> Responses output."""
# MAGIC
# MAGIC     def __init__(self):
# MAGIC         self.llm = ChatDatabricks(endpoint=LLM_ENDPOINT)
# MAGIC
# MAGIC     def _to_messages(self, request: ResponsesAgentRequest):
# MAGIC         messages = [("system", SYSTEM_PROMPT)]
# MAGIC         for item in request.input:
# MAGIC             item = item if isinstance(item, dict) else item.model_dump()
# MAGIC             messages.append((item.get("role", "user"), item.get("content", "")))
# MAGIC         return messages
# MAGIC
# MAGIC     def predict(self, request: ResponsesAgentRequest) -> ResponsesAgentResponse:
# MAGIC         outputs = [e.item for e in self.predict_stream(request)
# MAGIC                    if e.type == "response.output_item.done"]
# MAGIC         return ResponsesAgentResponse(output=outputs, custom_outputs=request.custom_inputs)
# MAGIC
# MAGIC     def predict_stream(
# MAGIC         self, request: ResponsesAgentRequest
# MAGIC     ) -> Generator[ResponsesAgentStreamEvent, None, None]:
# MAGIC         reply = self.llm.invoke(self._to_messages(request)).content
# MAGIC         # IMPORTANT: use the helper, not a raw dict — raw dicts fail the Responses schema.
# MAGIC         item = self.create_text_output_item(text=reply, id=str(uuid.uuid4()))
# MAGIC         yield ResponsesAgentStreamEvent(type="response.output_item.done", item=item)
# MAGIC
# MAGIC
# MAGIC AGENT = UASupportAgentStub()
# MAGIC mlflow.models.set_model(AGENT)   # <-- last line: this object is the model MLflow logs

# COMMAND ----------

# MAGIC %md
# MAGIC ### 3b. Log + register the stub (only if the model does not exist)
# MAGIC Declare the LLM endpoint in `resources=[...]` so deployment mints scoped credentials automatically
# MAGIC (automatic authentication passthrough). Guarded by `NEED_STUB`, so re-running the notebook is idempotent.

# COMMAND ----------

if NEED_STUB:
    from mlflow.models.resources import DatabricksServingEndpoint

    with mlflow.start_run():
        logged = mlflow.pyfunc.log_model(
            python_model="ua_support_agent_stub.py",   # Model-as-Code: log the file, not the object
            name="agent",
            resources=[DatabricksServingEndpoint(endpoint_name=LLM_ENDPOINT)],
            pip_requirements=["mlflow>=3.1", "databricks-langchain"],
        )
    registered = mlflow.register_model(model_uri=logged.model_uri, name=UC_MODEL)
    print("Registered", registered.name, "version", registered.version)
else:
    print("Model already registered — skipping stub. Latest version:", EXISTING_VERSION)

# COMMAND ----------

# MAGIC %md
# MAGIC ### 3c. Pin the version to deploy
# MAGIC Re-resolve the latest version after any registration. The deep-dive uses `VERSION = 7` as an example
# MAGIC ("the version you evaluated in Module 08") — here we **read it at runtime** so we never deploy a stale guess.

# COMMAND ----------

VERSION = latest_version(UC_MODEL)
assert VERSION is not None, f"No registered version of {UC_MODEL} — run Section 3a/3b or Module 09.6 first."
print("Deploying:", UC_MODEL, "version", VERSION)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Path A — deploy the agent with `agents.deploy()` (recommended for agents)
# MAGIC One call does the plumbing teams usually forget: it deploys the agent to a Model Serving endpoint, creates
# MAGIC a **Review App** for SMEs, deploys a **feedback model**, and enables **tracing + inference tables +
# MAGIC monitoring**. The agent runs on **CPU** — the GPU-heavy LLM work happens on the separate
# MAGIC `databricks-claude-sonnet-4-5` Foundation Model endpoint it calls.
# MAGIC
# MAGIC > ⚠️ **This is a long-running cell (~10–20 minutes)** while the endpoint is created and warms up.
# MAGIC > `agents.deploy` returns quickly with the endpoint name; the endpoint itself keeps updating in the
# MAGIC > background — we poll for readiness in Section 6. The generated name looks like
# MAGIC > `agents_<catalog>-<schema>-<model>` — **read it from the output, do not hardcode it.**

# COMMAND ----------

from databricks import agents

deployment = agents.deploy(
    model_name=UC_MODEL,
    model_version=VERSION,
    scale_to_zero=True,          # dev: cheap idling. Flip to False for the latency-critical prod path.
    environment_vars={           # plain config here; secret refs shown below (needs a real scope to work)
        "APP_ENV": "dev",
        # "API_TOKEN": "{{secrets/ua_scope/api_token}}",   # never hardcode a secret — use a {{secrets/...}} ref
    },
    deploy_feedback_model=True,  # also stand up the Review App feedback loop
)

# Read the REAL endpoint name + Review App URL from the output — they are generated, not guessed.
ENDPOINT_NAME = deployment.endpoint_name
print("Endpoint name :", ENDPOINT_NAME)          # e.g. agents_unity_airways-rag-ua_support_agent
print("Review App URL:", getattr(deployment, "review_app_url", "(check the Serving page > Use > Open review app)"))

# COMMAND ----------

# MAGIC %md
# MAGIC ### How to verify it worked
# MAGIC - `agents.deploy()` returned an `endpoint_name` (printed above).
# MAGIC - On the **Serving** page the endpoint appears with **Task = Agent (Responses)**; it flips to **Ready**
# MAGIC   once warm (Section 6 polls for this).
# MAGIC - **Use ▸ Open review app** opens the SME feedback UI.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Path B/C — the custom-model endpoint path (any MLflow model, not just agents)
# MAGIC For a plain `pyfunc` / chain / classical-ML model you create the endpoint yourself. Two equivalent APIs:
# MAGIC the **databricks-sdk** (`EndpointCoreConfigInput` + `ServedEntityInput`) and the framework-agnostic
# MAGIC **mlflow.deployments** client. Both are shown **commented** — you already have an endpoint from Path A, and
# MAGIC creating a second one for the same model is wasteful. Use this shape when the model is *not* an agent.
# MAGIC
# MAGIC > ⚠️ **GOTCHA:** `databricks-sdk` serving classes and enum values (`workload_size`, `workload_type`) can
# MAGIC > shift between SDK versions — **confirm class names against your installed `databricks-sdk` version.**

# COMMAND ----------

# --- Path B: databricks-sdk (confirm class names against your installed databricks-sdk version) ---
# from databricks.sdk import WorkspaceClient
# from databricks.sdk.service.serving import EndpointCoreConfigInput, ServedEntityInput
#
# w = WorkspaceClient()
# w.serving_endpoints.create_and_wait(
#     name=FRIENDLY_NAME,                              # "ua-support-agent"
#     config=EndpointCoreConfigInput(
#         served_entities=[
#             ServedEntityInput(
#                 entity_name=UC_MODEL,
#                 entity_version=str(VERSION),
#                 workload_size="Small",               # concurrency band: Small / Medium / Large
#                 workload_type="CPU",                 # agent orchestration -> CPU (GPU only for in-endpoint inference)
#                 scale_to_zero_enabled=True,
#             )
#         ]
#     ),
# )

# --- Path C: mlflow.deployments client (framework-agnostic) ---
# import mlflow.deployments
# deploy_client = mlflow.deployments.get_deploy_client("databricks")
# deploy_client.create_endpoint(
#     name=FRIENDLY_NAME,
#     config={"served_entities": [{
#         "entity_name": UC_MODEL,
#         "entity_version": str(VERSION),
#         "workload_size": "Small",
#         "scale_to_zero_enabled": True,
#     }]},
# )

print("Path B/C are reference-only. Path A (agents.deploy) already created:", ENDPOINT_NAME)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6. Poll for readiness
# MAGIC After `agents.deploy` the endpoint keeps updating in the background. Poll `serving_endpoints.get(...)`
# MAGIC until `state.ready == "READY"`. (Enum access is version-sensitive — we read defensively.)

# COMMAND ----------

import time
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()


def endpoint_state(name):
    ep = w.serving_endpoints.get(name)
    state = ep.state
    ready = getattr(getattr(state, "ready", None), "value", str(getattr(state, "ready", "UNKNOWN")))
    update = getattr(getattr(state, "config_update", None), "value", str(getattr(state, "config_update", "UNKNOWN")))
    return ready, update


for attempt in range(40):                       # ~20 min ceiling at 30s/attempt
    ready, update = endpoint_state(ENDPOINT_NAME)
    print(f"[{attempt:02d}] ready={ready} config_update={update}")
    if ready == "READY":
        print("Endpoint is READY.")
        break
    time.sleep(30)
else:
    print("Still not READY — check the Serving page; agent endpoints can take a while to warm up.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 7. Invoke the endpoint — three ways
# MAGIC The interface is identical everywhere; only the client changes. A `ResponsesAgent` expects an **`input`**
# MAGIC array of role/content messages (the Responses schema) — **not** the classic chat `messages` schema. While
# MAGIC integrating, add `databricks_options.return_trace` to get the agent's MLflow trace back with the answer.

# COMMAND ----------

# MAGIC %md
# MAGIC ### 7a. Programmatic — the `mlflow.deployments` client
# MAGIC `predict(endpoint=..., inputs=<json body>)` sends the body straight through, so the Responses `input`
# MAGIC schema and `databricks_options` work cleanly.

# COMMAND ----------

import mlflow.deployments

deploy_client = mlflow.deployments.get_deploy_client("databricks")
resp = deploy_client.predict(
    endpoint=ENDPOINT_NAME,
    inputs={
        "input": [{"role": "user", "content": "My flight is at 4pm — what's the check-in cutoff?"}],
        "databricks_options": {"return_trace": True},   # also return the MLflow trace
    },
)
print(resp)

# Alternative (databricks-sdk): w.serving_endpoints.query(name=ENDPOINT_NAME, ...)
# The exact kwarg for a Responses body varies by SDK version — confirm against your installed databricks-sdk.

# COMMAND ----------

# MAGIC %md
# MAGIC ### 7b. Raw REST — `POST /serving-endpoints/<name>/invocations`
# MAGIC The lowest-common-denominator path any external app can use: a bearer token and a JSON body.

# COMMAND ----------

import requests
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
host = w.config.host
token = w.config.token   # NOTE: on serverless/OAuth notebook sessions this may be empty — 7a (mlflow.deployments) is the reliable in-workspace path; 7b models what an EXTERNAL app does with a real token / service-principal creds

rest_resp = requests.post(
    f"{host}/serving-endpoints/{ENDPOINT_NAME}/invocations",
    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    json={
        "input": [{"role": "user", "content": "Can my battery pack go in cabin baggage?"}],
        "databricks_options": {"return_trace": True},
    },
    timeout=120,
)
rest_resp.raise_for_status()
print(rest_resp.json())

# COMMAND ----------

# MAGIC %md
# MAGIC ### 7c. SQL `ai_query` — batch inference at scale (GA)
# MAGIC Call the served agent from SQL, row by row over a Delta table. Below runs a **single inline row** so it
# MAGIC works without any seed table; the commented block shows the real batch shape over `overnight_tickets`.

# COMMAND ----------

single_row = spark.sql(f"""
SELECT ai_query(
  '{ENDPOINT_NAME}',
  request => to_json(named_struct('input',
    array(named_struct('role', 'user', 'content', 'What is the checked-baggage allowance?'))))
) AS agent_reply
""")
single_row.display()

# Batch shape (uncomment when you have a table of questions):
# spark.sql(f'''
# SELECT
#   ticket_id,
#   ai_query(
#     '{ENDPOINT_NAME}',
#     request => to_json(named_struct('input',
#       array(named_struct('role', 'user', 'content', question_text))))
#   ) AS agent_reply
# FROM {CATALOG}.{SCHEMA}.overnight_tickets
# ''').display()

# COMMAND ----------

# MAGIC %md
# MAGIC ### How to verify it worked
# MAGIC - 7a/7b return an assistant **`output`** array (with `return_trace` you also get the MLflow trace).
# MAGIC - 7c returns one `agent_reply` per row.
# MAGIC - Every call lands in the endpoint's **inference table** and shows up as an **MLflow trace** (Module 07).

# COMMAND ----------

# MAGIC %md
# MAGIC ## 8. Inspect the endpoint (schema + served entities)
# MAGIC Confirm what is actually behind the endpoint — the served model version(s) and the readiness state.

# COMMAND ----------

ep = w.serving_endpoints.get(ENDPOINT_NAME)
print("State          :", ep.state)
print("Served entities:", [se.name for se in (ep.config.served_entities if ep.config else [])])

# COMMAND ----------

# MAGIC %md
# MAGIC ## 9. Configuration that matters (and where it goes next)
# MAGIC | Knob | What it does | Field rule |
# MAGIC |---|---|---|
# MAGIC | **`scale_to_zero`** | Scales to zero replicas when idle | **On** in dev (cheap idling); **off** for latency-critical prod (avoids cold starts) |
# MAGIC | **`workload_size`** | Concurrency band (Small / Medium / Large) | Size to observed peak concurrency from the **inference table**, not a guess |
# MAGIC | **`workload_type`** | CPU vs GPU | **CPU** for agents/orchestration; GPU only when the endpoint runs heavy inference in-process |
# MAGIC | **Foundation Model mode** | pay-per-token vs provisioned throughput | Start **pay-per-token**; move to **provisioned throughput** for steady/high load, SLA latency, or custom weights |
# MAGIC | **Inference tables** | Delta log of every request/response | Enabled automatically by `agents.deploy` — the backbone of monitoring (Module 08) |
# MAGIC
# MAGIC **Where this endpoint goes next in Module 11:**
# MAGIC - **11.3 AI Gateway** — attach rate limits, guardrails (PII detection/redaction), usage tracking, fallbacks.
# MAGIC - **11.6 Endpoint version control** — host multiple versions and split **traffic %** for canary / A-B rollout.
# MAGIC - **11.7 Endpoint auth** — control who/what can query the endpoint (service principals, scoped tokens).
# MAGIC - **11.9 / Module 10.5** — front it with a branded chat UI on **Databricks Apps**.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 10. Recap, gotchas, and next step
# MAGIC **What you built**
# MAGIC - Resolved (or stubbed + registered) `unity_airways.rag.ua_support_agent` and read its **latest version** at runtime.
# MAGIC - Deployed it with **`agents.deploy(...)`** — one call gave you the endpoint, the Review App, the feedback
# MAGIC   model, and tracing + inference tables + monitoring. You read the **generated endpoint name** from the output.
# MAGIC - Saw the **custom-model** create path (databricks-sdk / mlflow.deployments) for non-agent models.
# MAGIC - **Polled** for readiness, then invoked the endpoint via the **mlflow.deployments** client, raw **REST**,
# MAGIC   and SQL **`ai_query`** — with `return_trace` on.
# MAGIC
# MAGIC **Gotchas to remember**
# MAGIC - **Don't hardcode the endpoint name** — `agents.deploy` generates `agents_<catalog>-<schema>-<model>`; read it from the output.
# MAGIC - A `ResponsesAgent` uses an **`input`** array (Responses schema), **not** the chat `messages` schema.
# MAGIC - **Leaving scale-to-zero on in prod** and then reporting "the assistant is slow" — that's the cold start.
# MAGIC - **Deploy the version you evaluated** (Module 08), not last night's experiment.
# MAGIC - `databricks-sdk` serving class/enum names shift between versions — **confirm against your installed SDK**.
# MAGIC - The `agents.deploy` doc page is JS-rendered; exact parameter strings are grounded in Book 1 Ch8 + the
# MAGIC   naming cheat-sheet — **re-check against current docs** before asserting them to a customer.
# MAGIC
# MAGIC **Next roadmap topic:** **11.3 — AI Gateway** (rate limits, guardrails, usage tracking, fallbacks) attaches
# MAGIC directly to the endpoint you just created.
