# Databricks notebook source
# MAGIC %md
# MAGIC # Module 11 lab — Ship and operate the Unity Airways support agent
# MAGIC **Roadmap:** Module 11 (Deployment and serving) · Topics 11.1–11.13 · ★ 11.1 / 11.3 / 11.10 cornerstones · [Theory + Hands-on]
# MAGIC
# MAGIC This is the consolidated lab that takes the **Module 09** agent (`unity_airways.rag.ua_support_agent`, a
# MAGIC `ResponsesAgent`) from "registered in Unity Catalog" to a **governed, metered, versioned, scheduled** production
# MAGIC system. One coherent narrative: package → serve → govern the edge → collect feedback → run at batch scale →
# MAGIC schedule → operate across versions and providers.
# MAGIC
# MAGIC | Step | Topic | What you do |
# MAGIC |---|---|---|
# MAGIC | 1 | **11.4** | A compact **PyFunc** with `load_context` / `predict` pre- and post-processing — the pattern behind custom endpoints; log + register |
# MAGIC | 2 | **11.1** ★ | `agents.deploy()` the ResponsesAgent — read the real endpoint name + Review App URL from the output |
# MAGIC | 3 | **11.2** | The **Review App** + structured **`mlflow.genai.labeling`** feedback loop |
# MAGIC | 4 | **11.3** ★ | **AI Gateway** on the endpoint — rate limits, guardrails, usage + payload logging, fallbacks |
# MAGIC | 5 | **11.6 / 11.7 / 11.9** | Register **v2**, set UC aliases `@champion` / `@challenger`, endpoint **permissions**, auth passthrough |
# MAGIC | 6 | **11.8** | **Champion vs Challenger** rollout — add the challenger as a second served entity with a canary traffic split |
# MAGIC | 7 | **11.5** | Batch **`ai_query`** over `ua_support_tickets` (brief; deep version in `11-10-ai-functions.py`) |
# MAGIC | 8 | **11.11** | Schedule the enrichment as a **Lakeflow Job** via the SDK (notebook task + cron) |
# MAGIC | 9 | **11.12** | **External model** credentials — a Databricks secret + an external-model serving endpoint |
# MAGIC | 10 | **11.13** | Serve an **open-source / Hugging Face** model with the `transformers` flavor |
# MAGIC
# MAGIC **Cornerstone notebooks — do those first for depth, this lab references them and fills in the rest:**
# MAGIC - **`11-1-model-serving.py`** (11.1) — the full deploy walkthrough (`agents.deploy()` internals, endpoint sizing, invocation).
# MAGIC - **`11-10-ai-functions.py`** (11.10) — the full batch AI Functions family (`ai_query` structured output, `ai_classify`, `ai_mask`, `vector_search`).
# MAGIC
# MAGIC ## Prerequisites (read before running)
# MAGIC - **Compute:** **serverless notebook/job**, or a **DBR ML runtime** (15.4 LTS ML or later). The `ai_query` cell needs a
# MAGIC   **serverless or Pro SQL warehouse** (or DBR 15.1+) with AI Functions available.
# MAGIC - **MLflow:** **>= 3.1** (Models-from-Code, `ResponsesAgent`, `mlflow.genai.*`, MLflow 3 logging + UC registry).
# MAGIC - **UC objects (`unity_airways.rag`):** the registered agent `ua_support_agent` (Module 09), plus `CREATE MODEL` rights
# MAGIC   for the extra models this lab registers. The batch step reads `ua_support_tickets` and writes `ua_tickets_enriched`.
# MAGIC - **Serving endpoint:** created by `agents.deploy()` in Step 2 (generated name `agents_unity_airways-rag-ua_support_agent`).
# MAGIC - **Secrets:** only for **11.12** (external provider key) — this lab uses **placeholders**, never a real key.
# MAGIC - **`databricks-sdk`:** several steps rely on `databricks.sdk.service.serving` / `.jobs` class names. They are current as of
# MAGIC   July 2026 but **can shift between SDK versions — confirm against your installed `databricks-sdk`.**
# MAGIC
# MAGIC > 📌 **The one idea of the module — a deployed model is a governed asset, not a script you `curl`.**
# MAGIC > Package (MLflow + UC) → serve (Model Serving) → govern the edge (AI Gateway) → feedback (Review App) →
# MAGIC > batch (`ai_query`) → schedule (Lakeflow Job) → operate (aliases + traffic split + permissions). Never an in-place overwrite.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 0. Install libraries and set variables
# MAGIC `databricks-agents` provides `agents.deploy()`; `transformers` + `torch` are only needed for the 11.13 open-source step.
# MAGIC Keep the `%pip` so versions are predictable across serverless and classic compute.

# COMMAND ----------

# MAGIC %pip install -U "mlflow>=3.1" databricks-agents databricks-sdk transformers torch
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

CATALOG      = "unity_airways"
SCHEMA       = "rag"
UC_MODEL     = f"{CATALOG}.{SCHEMA}.ua_support_agent"        # Module 09 — the ResponsesAgent we deploy + operate
UC_PYFUNC    = f"{CATALOG}.{SCHEMA}.ua_support_pyfunc"       # 11.4 — the pre/post-processing PyFunc this lab registers
UC_HF_MODEL  = f"{CATALOG}.{SCHEMA}.ua_ticket_classifier"   # 11.13 — the open-source classifier this lab registers
LLM_ENDPOINT = "databricks-claude-sonnet-4-5"             # chat model; confirm on the supported-models page
EMB_ENDPOINT = "databricks-gte-large-en"                  # embeddings model (used by retrieval)

# Batch tables (11.5) — raw feedback in, enriched rows out
TICKETS_TABLE  = f"{CATALOG}.{SCHEMA}.ua_support_tickets"
ENRICHED_TABLE = f"{CATALOG}.{SCHEMA}.ua_tickets_enriched"

# The friendly endpoint name we use in narrative. The REAL name agents.deploy() generates is
# agents_<catalog>-<schema>-<model>; we READ it from the deploy output in Step 2 and store it in ENDPOINT_NAME.
FRIENDLY_ENDPOINT = "ua-support-agent"
ENDPOINT_NAME     = f"agents_{CATALOG}-{SCHEMA}-ua_support_agent"   # provisional; overwritten by the deploy output

import mlflow
mlflow.set_registry_uri("databricks-uc")   # register every model to Unity Catalog, not the workspace registry

print("UC agent model :", UC_MODEL)
print("LLM endpoint   :", LLM_ENDPOINT)
print("Tickets table  :", TICKETS_TABLE)
print("Provisional endpoint name:", ENDPOINT_NAME)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 1 — PyFunc structure with pre/post-processing (11.4) · [Hands-on]
# MAGIC Custom-model endpoints run a **`mlflow.pyfunc.PythonModel`**: `load_context` sets up whatever the model needs
# MAGIC (clients, config, prompts), and `predict` runs your logic. The value of the wrapper is the **pre-processing before**
# MAGIC the model call (normalize the passenger question, inject Unity Airways context) and the **post-processing after**
# MAGIC (guard the output, shape the response). A `ResponsesAgent` (Module 09) is a PyFunc under the hood — this compact
# MAGIC example makes the pattern explicit so you can see where pre/post steps live.
# MAGIC
# MAGIC > 💡 **TIP:** for real agents/chains prefer **Models-from-Code** (`mlflow.models.set_model()`) over pickling — it is
# MAGIC > what Module 09 used. A plain `PythonModel` instance (below) is the simplest illustration of the 11.4 pre/post pattern.

# COMMAND ----------

import re
import mlflow
from mlflow.pyfunc import PythonModel

class UASupportPyFunc(PythonModel):
    """Compact custom model: pre-process the question, call the chat endpoint, post-process the answer."""

    def load_context(self, context):
        # Runs once when the endpoint loads. Set up the client + static config here, not per request.
        import mlflow.deployments
        self.client = mlflow.deployments.get_deploy_client("databricks")
        self.llm_endpoint = "databricks-claude-sonnet-4-5"   # self-contained: no notebook globals leak in
        self.system_prompt = (
            "You are the Unity Airways support assistant. Answer only from Unity Airways policy; "
            "if you are unsure, say so plainly. Keep replies under 120 words."
        )

    # --- PRE-processing: clean + frame the request before the model sees it ---
    def _preprocess(self, question: str) -> list:
        q = re.sub(r"\s+", " ", (question or "").strip())          # collapse whitespace
        q = q[:1000]                                               # cap runaway input
        return [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"Passenger question: {q}"},
        ]

    # --- POST-processing: guard + shape the model output before returning it ---
    def _postprocess(self, text: str) -> dict:
        text = (text or "").strip()
        # cheap output guard: never echo a raw booking PNR pattern back to the caller
        text = re.sub(r"\b[A-Z0-9]{6}\b", "[REDACTED-PNR]", text)
        return {"answer": text, "grounded": "policy" in text.lower()}

    def predict(self, context, model_input):
        # model_input is a pandas DataFrame with a "question" column (MLflow passes a DataFrame by default).
        questions = model_input["question"].tolist()
        results = []
        for q in questions:
            messages = self._preprocess(q)
            resp = self.client.predict(
                endpoint=self.llm_endpoint,
                inputs={"messages": messages, "max_tokens": 300, "temperature": 0.0},
            )
            answer = resp["choices"][0]["message"]["content"]
            results.append(self._postprocess(answer))
        return results

print("UASupportPyFunc defined — load_context (setup) + _preprocess + predict + _postprocess (guard).")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Log the PyFunc as code, declare its resource, and register to UC
# MAGIC Declare the chat endpoint as a **resource** so the deployed model gets scoped credentials automatically (auth
# MAGIC passthrough, 11.7). Logging does **not** execute `predict`, so this cell runs offline; the smoke test that follows
# MAGIC needs the live `databricks-claude-sonnet-4-5` endpoint and is guarded.

# COMMAND ----------

import pandas as pd
from mlflow.models.resources import DatabricksServingEndpoint
from mlflow.models.signature import infer_signature

# A signature makes the endpoint contract explicit (question in -> answer/grounded out).
example_in  = pd.DataFrame({"question": ["Can I get a refund on a Basic Economy fare?"]})
example_out = [{"answer": "Basic Economy fares follow the policy...", "grounded": True}]
signature   = infer_signature(example_in, example_out)

with mlflow.start_run(run_name="ua_support_pyfunc"):
    logged_pyfunc = mlflow.pyfunc.log_model(
        name="ua_support_pyfunc",                       # MLflow 3 uses name= (older code used artifact_path=)
        python_model=UASupportPyFunc(),
        signature=signature,
        input_example=example_in,
        resources=[DatabricksServingEndpoint(endpoint_name=LLM_ENDPOINT)],   # auth passthrough to the LLM
        pip_requirements=["mlflow>=3.1"],
    )
print("Logged PyFunc:", logged_pyfunc.model_uri)

# Register the version to Unity Catalog (governed, versioned, deployable the same way as the agent).
registered_pyfunc = mlflow.register_model(model_uri=logged_pyfunc.model_uri, name=UC_PYFUNC)
print("Registered:", registered_pyfunc.name, "v" + str(registered_pyfunc.version))

# COMMAND ----------

# Optional smoke test — needs the live chat endpoint. Guarded so the lab still runs top-to-bottom without it.
try:
    loaded = mlflow.pyfunc.load_model(logged_pyfunc.model_uri)
    print(loaded.predict(pd.DataFrame({"question": ["What is the checked-bag allowance on a Flex fare?"]})))
except Exception as e:
    print("[illustrative] PyFunc predict needs the live chat endpoint + auth. Reason:", repr(e))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 2 — Deploy the agent and read the real endpoint name (11.1 ★) · [Hands-on]
# MAGIC The production artifact is the Module 09 **ResponsesAgent**. `agents.deploy()` is the one call that provisions the
# MAGIC serving endpoint **and** the Review App **and** a feedback model, and turns on tracing + inference tables + monitoring.
# MAGIC **Full walkthrough: `11-1-model-serving.py`.** Here we deploy and, crucially, **read the generated endpoint name and
# MAGIC Review App URL from the output** — never hardcode a guess; the downstream steps use `ENDPOINT_NAME`.

# COMMAND ----------

from databricks import agents

# The version you validated in Module 08. Read your latest with MlflowClient if unsure (shown below, commented).
AGENT_VERSION = 1

try:
    deployment = agents.deploy(
        UC_MODEL,
        AGENT_VERSION,
        scale_to_zero=True,             # dev: cheap idling. Prod latency-critical path: set False (warm replica).
        # environment_vars={"APP_ENV": "dev"},   # config + {{secrets/scope/key}} refs, never plaintext keys
    )
    ENDPOINT_NAME  = deployment.endpoint_name       # e.g. agents_unity_airways-rag-ua_support_agent — the REAL name
    REVIEW_APP_URL = getattr(deployment, "review_app_url", None)
    print("Endpoint  :", ENDPOINT_NAME)
    print("Review App:", REVIEW_APP_URL)
except Exception as e:
    # If the agent is already deployed (or you are running the lab without a registered agent yet), keep going with
    # the provisional name so the governance steps still demonstrate the API. Read the real name from the Serving page.
    print("[illustrative] agents.deploy skipped/failed — using provisional ENDPOINT_NAME:", ENDPOINT_NAME)
    print("Reason:", repr(e))

# To find the latest registered version instead of hardcoding AGENT_VERSION:
#   from mlflow import MlflowClient
#   v = max(int(m.version) for m in MlflowClient().search_model_versions(f"name='{UC_MODEL}'"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 3 — Review App and structured feedback (11.2) · [Hands-on]
# MAGIC The Review App is the chat UI `agents.deploy()` created so support-desk SMEs can try the agent and leave 👍/👎 +
# MAGIC comments — no notebook needed. Their responses land as **MLflow traces / labels**, which become an evaluation set
# MAGIC for the Module 08 harness and the Module 13 improve loop. For a **formal review round**, drive it with
# MAGIC `mlflow.genai.labeling`: create a labeling session over a dataset and hand SMEs the review-app link.
# MAGIC
# MAGIC > ⚠️ **GOTCHA:** the `mlflow.genai.labeling` surface is newer and evolving — treat the exact function/argument names
# MAGIC > as **confirm against your installed mlflow** (some labeling/review features are Beta). The Review App from
# MAGIC > `agents.deploy()` itself is the GA path for casual feedback.

# COMMAND ----------

# Casual feedback path: just share REVIEW_APP_URL from Step 2 with your SMEs. Everything they submit is captured.
print("Share this Review App with SMEs:", locals().get("REVIEW_APP_URL", "<from agents.deploy output>"))

# Structured labeling path (formal review round). API surface is evolving — guarded + flagged to confirm.
try:
    import mlflow.genai.labeling as labeling

    session = labeling.create_labeling_session(
        name="ua-support-review-round-1",
        # assigned_users=["sme1@unity-airways.com", "sme2@unity-airways.com"],  # who labels
        # agent=ENDPOINT_NAME,                                                  # what they chat with
    )
    review_app = labeling.get_review_app()   # the review app for this workspace/experiment
    print("Labeling session:", getattr(session, "name", session))
    print("Review app URL  :", getattr(review_app, "url", review_app))
except Exception as e:
    print("[illustrative] Confirm the mlflow.genai.labeling API against your installed mlflow version.")
    print("Reason:", repr(e))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 4 — AI Gateway on the endpoint (11.3 ★) · [Hands-on]
# MAGIC AI Gateway is a **property of the serving endpoint**, not a separate deployment. One call adds rate limiting,
# MAGIC guardrails (safety + PII), usage tracking, payload logging, and provider fallbacks — governing **every** caller
# MAGIC (the app, the Review App, batch `ai_query`) without touching agent code. **Full deep-dive: `ai-gateway.md`.**
# MAGIC
# MAGIC > ⚠️ **GOTCHA:** **PII detection/redaction is Preview.** The `AiGateway*` dataclass names below are the verified
# MAGIC > `databricks-sdk` signature as of July 2026 — still **confirm against your installed SDK** before asserting to a customer.
# MAGIC >
# MAGIC > ⚠️ **GOTCHA (endpoint type):** the `put_ai_gateway` docstring notes AI Gateway is fully supported on **Foundation
# MAGIC > Model, external-model, provisioned-throughput and pay-per-token** endpoints, while **agent endpoints** (a
# MAGIC > `ResponsesAgent` from `agents.deploy`) **currently support only inference tables** via AI Gateway. If guardrails/
# MAGIC > rate-limits on the agent endpoint are rejected, configure the **Foundation Model endpoint the agent calls** instead.
# MAGIC > This call is already wrapped in try/except so the lab runs regardless. Evolving — verify for your workspace.

# COMMAND ----------

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.serving import (
    AiGatewayGuardrails, AiGatewayGuardrailParameters,
    AiGatewayGuardrailPiiBehavior, AiGatewayGuardrailPiiBehaviorBehavior,
    AiGatewayRateLimit, AiGatewayRateLimitKey, AiGatewayRateLimitRenewalPeriod,
    AiGatewayUsageTrackingConfig, AiGatewayInferenceTableConfig, FallbackConfig,
)

w = WorkspaceClient()

try:
    w.serving_endpoints.put_ai_gateway(
        name=ENDPOINT_NAME,
        # 1) Rate limiting: 100 calls/min per USER (also USER_GROUP, SERVICE_PRINCIPAL, ENDPOINT)
        rate_limits=[
            AiGatewayRateLimit(
                calls=100,
                renewal_period=AiGatewayRateLimitRenewalPeriod.MINUTE,
                key=AiGatewayRateLimitKey.USER,
            ),
        ],
        # 2) Guardrails: safety both ways; block PII on input, mask PII on output (PII = Preview); block keywords in
        guardrails=AiGatewayGuardrails(
            input=AiGatewayGuardrailParameters(
                safety=True,
                invalid_keywords=["internal_fare_class", "competitor_airline"],
                pii=AiGatewayGuardrailPiiBehavior(behavior=AiGatewayGuardrailPiiBehaviorBehavior.BLOCK),
            ),
            output=AiGatewayGuardrailParameters(
                safety=True,
                pii=AiGatewayGuardrailPiiBehavior(behavior=AiGatewayGuardrailPiiBehaviorBehavior.MASK),
            ),
        ),
        # 3) Usage tracking -> system tables (finance-grade attribution)
        usage_tracking_config=AiGatewayUsageTrackingConfig(enabled=True),
        # 4) Payload logging -> a Delta inference table in Unity Catalog (debug trail + eval seed)
        inference_table_config=AiGatewayInferenceTableConfig(
            enabled=True,
            catalog_name=CATALOG,
            schema_name=SCHEMA,
            table_name_prefix="ua_support_gateway",
        ),
        # 5) Fallbacks: retry the next served model on the endpoint if the primary errors
        fallback_config=FallbackConfig(enabled=True),
    )
    print("AI Gateway configured on", ENDPOINT_NAME)
except Exception as e:
    print("[illustrative] Needs the live endpoint + serving admin rights. Reason:", repr(e))

# COMMAND ----------

# MAGIC %md
# MAGIC ### How to verify AI Gateway worked
# MAGIC - **Config readback:** the gateway config comes back on the endpoint object.
# MAGIC - **Rate limit:** loop more than 100 calls in a minute — blocked calls return a rate-limit error.
# MAGIC - **Payload logging:** after a few requests the inference table appears under `unity_airways.rag` (short delay).

# COMMAND ----------

try:
    ep = w.serving_endpoints.get(ENDPOINT_NAME)
    print("AI Gateway on endpoint:", ep.ai_gateway)
except Exception as e:
    print("[illustrative] Reason:", repr(e))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 5 — Access and version control (11.6 / 11.7 / 11.9) · [Hands-on]
# MAGIC What is live must always be **explicit and auditable**. Unity Catalog holds model **versions** and **aliases**
# MAGIC (`@champion` / `@challenger`); the endpoint pins a version; access is controlled by endpoint **permissions** plus
# MAGIC UC grants. Auth (11.7) is handled for you: `agents.deploy()` wires **automatic authentication passthrough** so the
# MAGIC agent's declared `resources` get scoped credentials; a Databricks App (11.9) calls the endpoint as its **own
# MAGIC service principal**, never a personal token.

# COMMAND ----------

from mlflow import MlflowClient

client = MlflowClient(registry_uri="databricks-uc")

# Suppose Module 08 produced a better v2 of the agent (new prompt / new tool). Set aliases so promotion is an
# alias flip, not a code change. Aliases are the stable handles; versions are the immutable artifacts.
try:
    versions = sorted(int(m.version) for m in client.search_model_versions(f"name='{UC_MODEL}'"))
    champion_version   = versions[0]                       # current prod
    challenger_version = versions[-1] if len(versions) > 1 else versions[0]   # newest candidate

    client.set_registered_model_alias(UC_MODEL, "champion",   champion_version)
    client.set_registered_model_alias(UC_MODEL, "challenger", challenger_version)
    print(f"@champion -> v{champion_version}   @challenger -> v{challenger_version}")
    # Resolve an alias to a version any time: client.get_model_version_by_alias(UC_MODEL, "champion")
except Exception as e:
    print("[illustrative] Needs the registered agent in UC. Reason:", repr(e))

# COMMAND ----------

# Endpoint permissions: least-privilege. Grant CAN_QUERY to the callers (app SP, analysts), CAN_MANAGE to the owners.
from databricks.sdk.service.serving import (
    ServingEndpointAccessControlRequest, ServingEndpointPermissionLevel,
)
# NOTE: confirm the set_permissions kwarg name (serving_endpoint_id) against your installed databricks-sdk version.
try:
    ep = w.serving_endpoints.get(ENDPOINT_NAME)
    w.serving_endpoints.set_permissions(
        serving_endpoint_id=ep.id,
        access_control_list=[
            ServingEndpointAccessControlRequest(
                group_name="ua-support-engineers",
                permission_level=ServingEndpointPermissionLevel.CAN_QUERY,   # callers can query, not reconfigure
            ),
        ],
    )
    print("Set CAN_QUERY for group ua-support-engineers on", ENDPOINT_NAME)
except Exception as e:
    print("[illustrative] Needs the live endpoint + manage rights, and the group to exist. Reason:", repr(e))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 6 — Champion vs Challenger rollout (11.8) · [Theory + Hands-on]
# MAGIC Promotion is a **controlled traffic shift plus an alias flip, gated on evaluation** — never an in-place overwrite.
# MAGIC Add the challenger as a **second served entity** on a small canary percentage, watch monitoring (Module 13), then
# MAGIC flip `@champion` to 100%. **Rollback is just keeping the previous champion.**
# MAGIC
# MAGIC > 📌 **IMPORTANT:** for an `agents.deploy()`-managed endpoint, prefer re-running `agents.deploy()` for the new
# MAGIC > version, or manage the split with the serving API as below. Do not overwrite the champion's served entity in place.

# COMMAND ----------

from databricks.sdk.service.serving import (
    EndpointCoreConfigInput, ServedEntityInput, TrafficConfig, Route,
)
# NOTE: confirm these serving class names against your installed databricks-sdk version.

# 90% to the champion, 10% canary to the challenger. served_entity names are what the Route targets.
CHAMPION_ENTITY   = "ua_support_champion"
CHALLENGER_ENTITY = "ua_support_challenger"

try:
    champ_v = client.get_model_version_by_alias(UC_MODEL, "champion").version
    chall_v = client.get_model_version_by_alias(UC_MODEL, "challenger").version

    w.serving_endpoints.update_config(
        name=ENDPOINT_NAME,
        served_entities=[
            ServedEntityInput(
                name=CHAMPION_ENTITY, entity_name=UC_MODEL, entity_version=str(champ_v),
                workload_size="Small", scale_to_zero_enabled=True,
            ),
            ServedEntityInput(
                name=CHALLENGER_ENTITY, entity_name=UC_MODEL, entity_version=str(chall_v),
                workload_size="Small", scale_to_zero_enabled=True,
            ),
        ],
        traffic_config=TrafficConfig(routes=[
            Route(served_entity_name=CHAMPION_ENTITY,   traffic_percentage=90),   # keep prod safe
            Route(served_entity_name=CHALLENGER_ENTITY, traffic_percentage=10),   # canary the candidate
        ]),
    )
    print(f"Canary live: champion v{champ_v} @90% / challenger v{chall_v} @10%")
except Exception as e:
    print("[illustrative] Needs the live endpoint + both versions/aliases. Reason:", repr(e))

# Promote (challenger wins the eval): flip the alias, then shift traffic to 100% champion route.
#   client.set_registered_model_alias(UC_MODEL, "champion", chall_v)
# Rollback (challenger loses): drop the challenger route back to 0% — the old champion never stopped serving.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 7 — Batch inference with `ai_query` (11.5) · [Hands-on]
# MAGIC Real-time serving answers **one request**; batch answers a **whole table**. `ai_query` calls a served model for
# MAGIC every row of `ua_support_tickets`, parallelized by the SQL engine. Always set **`failOnError => false`** so one bad
# MAGIC row never fails the run. **The full AI Functions family (structured JSON, `ai_classify`, `ai_mask`, `vector_search`)
# MAGIC is in `11-10-ai-functions.py`** — this is the one-cell version to keep the lab coherent.

# COMMAND ----------

# MAGIC %sql
# MAGIC -- Seed a tiny tickets table so this lab runs standalone. CREATE IF NOT EXISTS + insert-only-when-empty
# MAGIC -- means it never clobbers a real table (or the richer seed from 11-10-ai-functions.py).
# MAGIC CREATE TABLE IF NOT EXISTS unity_airways.rag.ua_support_tickets (
# MAGIC   ticket_id STRING, channel STRING, language STRING, raw_text STRING
# MAGIC );

# COMMAND ----------

# MAGIC %sql
# MAGIC INSERT INTO unity_airways.rag.ua_support_tickets
# MAGIC SELECT * FROM (VALUES
# MAGIC   ('T-2001','email','en','Flight UA482 was cancelled and I still have not been rebooked. Please help.'),
# MAGIC   ('T-2002','chat','en','How much does an extra checked bag cost on a transatlantic route?'),
# MAGIC   ('T-2003','phone','en','I was double-charged for seat selection on booking ABC123 and need a refund.'),
# MAGIC   ('T-2004','email','es','Mi vuelo se retraso cuatro horas y perdi la conexion. Quiero una compensacion.'),
# MAGIC   ('T-2005','web','en','the app wont let me check in it keeps crashing on the payment screen')
# MAGIC ) AS v(ticket_id, channel, language, raw_text)
# MAGIC WHERE (SELECT count(*) FROM unity_airways.rag.ua_support_tickets) = 0;

# COMMAND ----------

# MAGIC %sql
# MAGIC -- Draft a support reply for each ticket in one pass. failOnError => false is the batch-safety switch:
# MAGIC -- each row returns a STRUCT {response, errorMessage} instead of blowing up the whole job on a single bad row.
# MAGIC CREATE OR REPLACE TABLE unity_airways.rag.ua_tickets_enriched AS
# MAGIC SELECT
# MAGIC   ticket_id,
# MAGIC   channel,
# MAGIC   ai_query(
# MAGIC     'databricks-claude-sonnet-4-5',                       -- confirm on the supported-models page
# MAGIC     CONCAT('Draft a short, policy-grounded Unity Airways reply to: ', raw_text),
# MAGIC     failOnError     => false,
# MAGIC     modelParameters => named_struct('temperature', CAST(0.0 AS DOUBLE), 'max_tokens', 300)
# MAGIC   ) AS ai_reply
# MAGIC FROM unity_airways.rag.ua_support_tickets
# MAGIC WHERE raw_text IS NOT NULL;    -- NULL in => NULL out; filtering also saves the wasted calls

# COMMAND ----------

# MAGIC %sql
# MAGIC -- How to verify it worked: rows have a reply, and any failures are isolated in ai_reply.errorMessage (not fatal).
# MAGIC SELECT ticket_id, ai_reply.response AS reply, ai_reply.errorMessage AS error
# MAGIC FROM   unity_airways.rag.ua_tickets_enriched
# MAGIC LIMIT 10;

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 8 — Schedule the enrichment as a Lakeflow Job (11.11) · [Hands-on]
# MAGIC A notebook cell you run by hand is not a production pipeline. **Lakeflow Jobs** (formerly Databricks Workflows)
# MAGIC schedules the enrichment on a cron trigger with retries and serverless compute, so last night's tickets are scored
# MAGIC unattended. The SDK creates the job below; you can also build the same thing in the **Jobs UI** (Create job →
# MAGIC Notebook task → Schedule/trigger). It is created **PAUSED** so running this cell does not fire a real job.
# MAGIC
# MAGIC > ⚠️ **GOTCHA:** the rebrand is **Workflows → Lakeflow Jobs** (existing jobs run unchanged; system-table schema moved
# MAGIC > `workflow` → `lakeflow`). Confirm `databricks.sdk.service.jobs` class names against your installed SDK.

# COMMAND ----------

from databricks.sdk.service.jobs import (
    Task, NotebookTask, CronSchedule, PauseStatus, Source,
)

# Point the task at the notebook that runs the enrichment SQL. Use THIS notebook's path, or a dedicated one.
ENRICHMENT_NOTEBOOK_PATH = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()

try:
    created = w.jobs.create(
        name="ua-nightly-ticket-enrichment",
        tasks=[
            Task(
                task_key="enrich_tickets",
                description="Batch ai_query enrichment over ua_support_tickets -> ua_tickets_enriched",
                notebook_task=NotebookTask(
                    notebook_path=ENRICHMENT_NOTEBOOK_PATH,
                    source=Source.WORKSPACE,
                ),
                # For serverless jobs compute, leave the cluster fields unset; classic jobs would set new_cluster/job_clusters.
            ),
        ],
        schedule=CronSchedule(
            quartz_cron_expression="0 0 3 * * ?",   # 03:00 daily
            timezone_id="UTC",
            pause_status=PauseStatus.PAUSED,        # created paused so the lab does not launch a real run
        ),
    )
    print("Created Lakeflow Job id:", created.job_id, "(PAUSED — unpause in the Jobs UI when ready)")
except Exception as e:
    print("[illustrative] Needs job-create rights. In the UI: Jobs & Pipelines -> Create job -> Notebook task -> Schedule.")
    print("Reason:", repr(e))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 9 — External model credentials and provider setup (11.12) · [Hands-on]
# MAGIC To fail over to (or A/B against) a third-party provider, store the key in a **Databricks secret** — never plaintext —
# MAGIC and stand up an **external-model serving endpoint** that references it. Apps then call the provider by **endpoint name**,
# MAGIC so swapping providers is a config change. Fronted by AI Gateway (Step 4), it inherits the same governance.
# MAGIC
# MAGIC > ⚠️ **GOTCHA:** the values below are **placeholders**. Never paste a real API key into a notebook. `anthropic_api_key`
# MAGIC > takes a `{{secrets/scope/key}}` reference; `anthropic_api_key_plaintext` (not used here) would take a raw key.

# COMMAND ----------

# 9a) Create a secret scope + secret to hold the provider key (placeholder). Run once; safe to skip if it exists.
SECRET_SCOPE = "ua_ext_models"
SECRET_KEY   = "anthropic_api_key"
try:
    existing = [s.name for s in w.secrets.list_scopes()]
    if SECRET_SCOPE not in existing:
        w.secrets.create_scope(scope=SECRET_SCOPE)
    # Replace "REPLACE_WITH_REAL_KEY" out-of-band (CLI / UI), NOT in this notebook, before creating the endpoint.
    w.secrets.put_secret(scope=SECRET_SCOPE, key=SECRET_KEY, string_value="REPLACE_WITH_REAL_KEY")
    print(f"Secret {SECRET_SCOPE}/{SECRET_KEY} is set (placeholder value).")
except Exception as e:
    print("[illustrative] Needs secret-scope rights. Reason:", repr(e))

# COMMAND ----------

# 9b) Create the external-model endpoint that references the secret (Anthropic Claude as an example provider).
from databricks.sdk.service.serving import (
    EndpointCoreConfigInput, ServedEntityInput, ExternalModel, ExternalModelProvider, AnthropicConfig,
)
# NOTE: confirm ExternalModel / AnthropicConfig fields against your installed databricks-sdk version.

EXT_ENDPOINT = "ua-claude-external"
try:
    w.serving_endpoints.create(
        name=EXT_ENDPOINT,
        config=EndpointCoreConfigInput(
            served_entities=[
                ServedEntityInput(
                    name="claude-external",
                    external_model=ExternalModel(
                        provider=ExternalModelProvider.ANTHROPIC,
                        name="claude-3-5-sonnet-20241022",     # confirm the provider's current model id
                        task="llm/v1/chat",
                        anthropic_config=AnthropicConfig(
                            anthropic_api_key=f"{{{{secrets/{SECRET_SCOPE}/{SECRET_KEY}}}}}",   # secret reference
                        ),
                    ),
                ),
            ],
        ),
    )
    print("External-model endpoint created:", EXT_ENDPOINT)
except Exception as e:
    print("[illustrative] Needs a real key in the secret + serving rights. Reason:", repr(e))

# 9c) Query it exactly like any endpoint — the app never sees the provider key.
try:
    out = w.serving_endpoints.query(
        name=EXT_ENDPOINT,
        messages=[{"role": "user", "content": "One sentence: what is Unity Airways' Flex fare refund window?"}],
    )
    print(out)
except Exception as e:
    print("[illustrative] Query needs the endpoint live with a valid key. Reason:", repr(e))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 10 — Serve an open-source / Hugging Face model (11.13) · [Hands-on]
# MAGIC Some jobs want a specialized model that is not on the Foundation Model APIs — a small classifier, a domain embedder.
# MAGIC Log it with the **`transformers` flavor** (`mlflow.transformers.log_model`), register to UC, then deploy it as a
# MAGIC **custom-model endpoint** (Step 2's serving API). This example uses a tiny sentiment classifier so it runs on CPU;
# MAGIC larger generative models need **GPU** (`workload_type="GPU"`) and often provisioned throughput.
# MAGIC
# MAGIC > ⚠️ **GOTCHA:** the download + log needs `transformers` + `torch` (installed in Step 0) and pulls model weights from
# MAGIC > the Hugging Face hub, so it needs internet egress and a minute or two. Serving a **large** model requires a GPU
# MAGIC > serving workload — size it deliberately. Confirm `mlflow.transformers.log_model` args against your installed mlflow.

# COMMAND ----------

import mlflow

try:
    import transformers

    # A small, CPU-friendly text-classification pipeline — the "specialized OSS model" stand-in.
    hf_pipe = transformers.pipeline(
        task="text-classification",
        model="distilbert-base-uncased-finetuned-sst-2-english",
    )

    with mlflow.start_run(run_name="ua_ticket_classifier"):
        logged_hf = mlflow.transformers.log_model(
            transformers_model=hf_pipe,
            name="ua_ticket_classifier",          # MLflow 3 uses name= (older code used artifact_path=)
            task="text-classification",
            input_example=["My bag never arrived and no one will help me."],
            registered_model_name=UC_HF_MODEL,    # log + register to Unity Catalog in one step
        )
    print("Logged + registered HF model:", logged_hf.model_uri, "->", UC_HF_MODEL)
except Exception as e:
    print("[illustrative] Needs transformers/torch + HF hub egress. Reason:", repr(e))

# COMMAND ----------

# MAGIC %md
# MAGIC ### Deploy the open-source model as a custom endpoint
# MAGIC Same serving API as Step 6 — this time the served entity is the UC-registered `transformers` model. The tiny
# MAGIC classifier runs on **CPU**; for a large generative model set `workload_type="GPU"`.

# COMMAND ----------

from databricks.sdk.service.serving import EndpointCoreConfigInput, ServedEntityInput

HF_ENDPOINT = "ua-ticket-classifier"
try:
    from mlflow import MlflowClient
    hf_version = MlflowClient(registry_uri="databricks-uc").search_model_versions(
        f"name='{UC_HF_MODEL}'")[0].version
    w.serving_endpoints.create(
        name=HF_ENDPOINT,
        config=EndpointCoreConfigInput(
            served_entities=[
                ServedEntityInput(
                    name="classifier",
                    entity_name=UC_HF_MODEL,
                    entity_version=str(hf_version),
                    workload_size="Small",
                    workload_type="CPU",            # small classifier -> CPU; large generative model -> "GPU"
                    scale_to_zero_enabled=True,
                ),
            ],
        ),
    )
    print("Custom-model endpoint created:", HF_ENDPOINT)
except Exception as e:
    print("[illustrative] Needs the registered HF model + serving rights. Reason:", repr(e))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Recap — you shipped it
# MAGIC **What you did in this lab**
# MAGIC - **Packaged (11.4):** a compact **PyFunc** showing `load_context` + pre/post-processing, logged with a `resources` and
# MAGIC   registered to `unity_airways.rag.ua_support_pyfunc` — the pattern behind every custom endpoint.
# MAGIC - **Served (11.1 ★):** `agents.deploy()` the ResponsesAgent and **read the real endpoint name + Review App URL** from the output.
# MAGIC - **Feedback (11.2):** shared the **Review App** and set up a structured `mlflow.genai.labeling` review round.
# MAGIC - **Governed the edge (11.3 ★):** **AI Gateway** — rate limits, guardrails (PII = Preview), usage + payload logging, fallbacks.
# MAGIC - **Operated it (11.6 / 11.7 / 11.9):** UC **aliases** `@champion` / `@challenger`, endpoint **CAN_QUERY** permissions, auth passthrough.
# MAGIC - **Rolled out safely (11.8):** a **Champion-vs-Challenger** canary (90/10 traffic split) with an alias-flip promote and a zero-code rollback.
# MAGIC - **Scaled (11.5):** a batch **`ai_query`** over `ua_support_tickets` with `failOnError => false`.
# MAGIC - **Scheduled (11.11):** a **Lakeflow Job** (created PAUSED) running the enrichment on a nightly cron.
# MAGIC - **Went cross-provider (11.12):** a **secret** + an **external-model endpoint** (placeholder key), queryable by name.
# MAGIC - **Served OSS (11.13):** a Hugging Face model logged with the **`transformers` flavor** and deployed as a custom endpoint.
# MAGIC
# MAGIC **Gotchas to remember**
# MAGIC - **Never hardcode a guessed endpoint name** — read it from the `agents.deploy()` output (`agents_<catalog>-<schema>-<model>`).
# MAGIC - **Promotion is a traffic shift + alias flip, gated on eval** — never overwrite the champion in place.
# MAGIC - **`failOnError => false`** on every batch `ai_query`, and filter `WHERE ... IS NOT NULL` (NULL in => NULL out).
# MAGIC - **PII redaction is Preview**; **Workflows → Lakeflow Jobs**; **provider/served-model names churn** — verify at authoring time.
# MAGIC - **Secrets, never plaintext keys**, for external providers. **Confirm SDK class names against your installed `databricks-sdk`/mlflow.**
# MAGIC
# MAGIC **Next:**
# MAGIC - **Module 12 — Responsible GenAI:** the deep dive on guardrails, PII masking, Unity Catalog data governance, risk frameworks,
# MAGIC   and **deploy-as-service-principal** — making the endpoint you just served safe and accountable.
# MAGIC - **Module 13 — Production monitoring:** read the inference tables and Review App feedback you turned on here, score them with
# MAGIC   MLflow scorers, and close the improve loop that feeds the next Challenger.
