# Databricks notebook source
# MAGIC %md
# MAGIC # Capstone C4 (FINAL) — Unity Airways GenAI Platform
# MAGIC **Roadmap:** = ★ 17.7 · integrates Modules 00–17 · build at end · [Theory + Hands-on]
# MAGIC
# MAGIC This is the last thing you build. Unity Airways has three GenAI proofs-of-concept that each work alone and none
# MAGIC of which a review board trusts: a support RAG chatbot, a tool-using support agent, and a pile of dashboards ops
# MAGIC and finance keep asking data engineering to re-slice by hand. The board will not sign off on three disconnected
# MAGIC demos. It wants **one governed platform** — and this notebook assembles it.
# MAGIC
# MAGIC ### The one idea: two planes, two front doors
# MAGIC - **Two shared planes.** A **governance plane** (Unity Catalog — catalogs, schemas, grants, lineage, the model
# MAGIC   registry, the prompt registry) and an **observability / integration plane** (MLflow 3 — one trace per request,
# MAGIC   one eval loop, production monitoring). Everything sits on both.
# MAGIC - **Two application paths (front doors).** A **support agent** (RAG + UC-function tools) for customers and agents,
# MAGIC   and a **self-serve analytics** experience (Genie over governed metric views) for ops and finance. Different
# MAGIC   paths, same two planes. That sharing is what turns three demos into one platform.
# MAGIC
# MAGIC ### You assemble, you do not rebuild
# MAGIC - **C1** gave you retrieval + a registered `ua_rag_chain`.
# MAGIC - **C2** gave you tracing, an eval scorecard, and a `@champion` version.
# MAGIC - **C3** gave you the deployed, guardrailed, monitored `ua_support_agent`.
# MAGIC - **C4 wires them together and adds the missing layers:** Genie analytics (14), metric views (15), a cost /
# MAGIC   scaling pass (16), and the reference architecture (17), then packages it for the exam (Track C) and a customer
# MAGIC   hand-over (Track D).
# MAGIC
# MAGIC ### Prerequisites (read before running)
# MAGIC - **Compute:** a **serverless notebook/job** or **DBR 15.4 LTS ML+** for the Python cells; a **Pro or Serverless
# MAGIC   SQL warehouse** (or **DBR 17.2+**) for the metric-view cells in M2 (YAML `version: 1.1` needs 17.2+, nested
# MAGIC   joins need 17.1+). Metric views and Genie both require Pro/Serverless SQL.
# MAGIC - **MLflow:** **>= 3.4** (`mlflow[databricks]`) for `mlflow.genai.evaluate`, tracing, prompt registry, datasets.
# MAGIC - **The C1–C3 artifacts (this capstone assembles them — it does not re-derive them):**
# MAGIC   - Chunked policy data + retrieval index — `unity_airways.rag.ua_rag_chunks_index` (C1, Modules 03–04).
# MAGIC   - Registered RAG chain with a live alias — `unity_airways.rag.ua_rag_chain` → `@champion` (C1/C2, Modules 05–06).
# MAGIC   - Prompt governed in the registry — `prompts:/unity_airways.rag.ua_rag_prompt@champion` (Beta, Module 02.5).
# MAGIC   - Trace instrumentation + an eval scorecard — MLflow 3 traces + an `mlflow.genai.evaluate` run (C2, Modules 07–08).
# MAGIC   - Deployed, guardrailed, monitored agent — `unity_airways.rag.ua_support_agent` via `agents.deploy` on endpoint
# MAGIC     `ua-support-agent`, fronted by the FM endpoint `ua-support-llm` (C3, Modules 09–13).
# MAGIC - **Operational data in Unity Catalog** for the analytics path — the star schema + metric view under
# MAGIC   `unity_airways.analytics.*`. **This notebook seeds a small, deterministic copy inline (M2)** so the analytics
# MAGIC   milestone runs standalone; if Module 15 already built it, the `CREATE ... IF NOT EXISTS` / `CREATE OR REPLACE`
# MAGIC   cells are safe to re-run.
# MAGIC - **All Modules 00–17 marked ✅** in the ROADMAP.
# MAGIC
# MAGIC > 📌 **IMPORTANT — schema reconciliation.** The original C4 brief wrote operational data under `unity_airways.ops.*`.
# MAGIC > That is **outdated**. The analytics build (Module 15 / P5) locked the schema as **`unity_airways.analytics`** —
# MAGIC > star schema `unity_airways.analytics.fct_bookings` (+ `dim_flights` / `dim_customers` / `dim_airports`) and the
# MAGIC > metric view **`unity_airways.analytics.bookings_metrics`**. This notebook uses `analytics` everywhere. Do **not**
# MAGIC > use `ops`.
# MAGIC
# MAGIC > ⚠️ **Runnability note.** Every step that needs a live C1–C3 artifact (the deployed endpoint, the registered
# MAGIC > agent, AI Gateway config, the champion alias) is wrapped in `try/except` with an `[illustrative]` fallback, so
# MAGIC > the notebook runs top-to-bottom on a fresh workspace. The analytics layer (M2), the cost math (M3), and the
# MAGIC > `%md` deliverables (M4/M5) run for real. Serving / model / provider names churn — confirm the ones you assert.

# COMMAND ----------

# MAGIC %md
# MAGIC ### 🗺️ Target architecture — the whole platform on one diagram
# MAGIC Two planes wrapping two application paths. Reconciled to `unity_airways.analytics.*` for the metric views.
# MAGIC
# MAGIC ```mermaid
# MAGIC flowchart TB
# MAGIC   subgraph GOV["Governance plane · Unity Catalog (grants, lineage, model + prompt registry)"]
# MAGIC     direction TB
# MAGIC     subgraph DATA["Data + retrieval · Modules 03-04 (C1)"]
# MAGIC       src["Policy PDFs<br/>unity_airways.raw"] --> ingest["RAG ingestion (Lakeflow SDP)<br/>parse, chunk, embed"]
# MAGIC       ingest --> idx["Databricks AI Search<br/>unity_airways.rag.ua_rag_chunks_index"]
# MAGIC       opsraw["Operational data<br/>flights, bookings, revenue"] --> mv["Metric views (semantic layer)<br/>unity_airways.analytics.* · Module 15"]
# MAGIC     end
# MAGIC     subgraph SUPPORT["Support path · Modules 05-13 (C1-C3)"]
# MAGIC       idx --> chain["ua_rag_chain (retriever + LLM)<br/>databricks-claude-sonnet-4-5"]
# MAGIC       prompt["Prompt Registry · Beta<br/>prompts:/unity_airways.rag.ua_rag_prompt@champion"] --> chain
# MAGIC       chain --> agent["ua_support_agent (ResponsesAgent + UC tools)"]
# MAGIC       agent --> gw["AI Gateway on ua-support-llm<br/>guardrails, rate limits, fallbacks + payload logging"]
# MAGIC       gw --> serve["Model Serving endpoint ua-support-agent<br/>agents.deploy(...) + Review App"]
# MAGIC     end
# MAGIC     subgraph ANALYTICS["Analytics path · Modules 14-15 (new)"]
# MAGIC       mv --> genie["Genie Agent 'Unity Airways Revenue Analytics'<br/>conversational analytics over metric views"]
# MAGIC       genie --> mas["Multi-Agent Supervisor (optional, GA)<br/>routes support + analytics"]
# MAGIC     end
# MAGIC     subgraph SURFACE["Surfaces · Modules 10-11 + Genie One"]
# MAGIC       serve --> app["Databricks App (chat UI)"]
# MAGIC       genie --> one["Genie One (business users)"]
# MAGIC       mas --> app
# MAGIC     end
# MAGIC   end
# MAGIC   subgraph OBS["Observability plane · MLflow 3 (Modules 07-08-13)"]
# MAGIC     direction TB
# MAGIC     trace["Tracing (spans on every call)"]
# MAGIC     eval["mlflow.genai.evaluate scorecard (gates promotion)"]
# MAGIC     mon["Production monitoring + inference tables + alerts"]
# MAGIC   end
# MAGIC   agent -.emits.-> trace
# MAGIC   serve -.logs.-> mon
# MAGIC   chain -.scored by.-> eval
# MAGIC   cost["Cost + scaling pass · Module 16<br/>endpoint sizing, batch vs real-time, Unity AI Gateway budgets"] -.governs.-> gw
# MAGIC ```
# MAGIC
# MAGIC *The two application paths are different, but the governance plane (Unity Catalog) and the observability plane
# MAGIC (MLflow 3) are shared. That sharing is the whole point.*

# COMMAND ----------

# MAGIC %md
# MAGIC ## 0. Install and set variables
# MAGIC `mlflow[databricks]>=3.4` (eval + tracing + prompt registry), `databricks-agents` (`agents.deploy`),
# MAGIC `databricks-sdk>=0.73` (the verified `w.genie.*` + serving surface). All names are the **locked canonical names** —
# MAGIC do not rename them, or the platform stops being one coherent thing.

# COMMAND ----------

# MAGIC %pip install -U "mlflow[databricks]>=3.4" databricks-agents "databricks-sdk>=0.73"
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

import mlflow

CATALOG          = "unity_airways"
RAG_SCHEMA       = "rag"           # support / RAG path
ANALYTICS_SCHEMA = "analytics"     # locked semantic-layer schema (NOT "ops")

# --- Support path (C1-C3) — assemble, do not rebuild ---
UC_RAG_CHAIN   = f"{CATALOG}.{RAG_SCHEMA}.ua_rag_chain"           # C1/C2 registered chain -> @champion
UC_AGENT       = f"{CATALOG}.{RAG_SCHEMA}.ua_support_agent"       # C3 ResponsesAgent (Module 09)
RAG_INDEX      = f"{CATALOG}.{RAG_SCHEMA}.ua_rag_chunks_index"    # C1 AI Search index (Module 04)
PROMPT_ALIAS   = f"prompts:/{CATALOG}.{RAG_SCHEMA}.ua_rag_prompt@champion"   # Prompt Registry (Beta)
AGENT_ENDPOINT = "ua-support-agent"                              # the deployed agent endpoint
LLM_ENDPOINT   = "ua-support-llm"                                # FM/external endpoint the agent calls (gateway lives here)
CHAT_MODEL     = "databricks-claude-sonnet-4-5"                  # confirm on the supported-models page
JUDGE          = "databricks:/databricks-claude-sonnet-4-5"     # scorer judge model

# --- Analytics path (new — Modules 14-15) ---
FQ_ANALYTICS   = f"{CATALOG}.{ANALYTICS_SCHEMA}"
METRIC_VIEW    = f"{FQ_ANALYTICS}.bookings_metrics"              # the governed semantic layer
GENIE_AGENT    = "Unity Airways Revenue Analytics"              # the Genie Agent (created UI-first)
# Read this from the Agent URL after you create it in the console: .../genie/rooms/<SPACE_ID>
SPACE_ID       = "REPLACE-with-your-genie-space-id"

# --- Cost / batch (Module 16) ---
TICKETS_TABLE  = f"{CATALOG}.{RAG_SCHEMA}.ua_support_tickets"

mlflow.set_registry_uri("databricks-uc")   # every model/alias resolves against Unity Catalog

print("Support agent   :", UC_AGENT, "on endpoint", AGENT_ENDPOINT)
print("Gateway endpoint:", LLM_ENDPOINT)
print("Metric view     :", METRIC_VIEW)
print("Genie Agent     :", GENIE_AGENT)

# COMMAND ----------

# MAGIC %md
# MAGIC ## M1 · Assemble the platform from C1–C3
# MAGIC **[Hands-on]** Stand up the support experience end to end from artifacts you already have: ingestion →
# MAGIC `ua_rag_chunks_index` → `ua_rag_chain` → `ua_support_agent` → `agents.deploy` behind AI Gateway, with MLflow 3
# MAGIC tracing, an eval scorecard, and monitoring live. The chain loads its prompt from the **Prompt Registry**
# MAGIC (`@champion` alias), not a hardcoded string, so prompt changes are versioned and promoted the same way models
# MAGIC are — one change-management story for both.
# MAGIC
# MAGIC This milestone is mostly **assembly and verification**. It resolves the champion version, confirms the prompt
# MAGIC alias, (re-)deploys the agent, reasserts the gateway, runs the promotion-gate scorecard, and queries the live
# MAGIC endpoint. It does **not** re-create the index, the chain, or the agent — those are C1–C3.
# MAGIC
# MAGIC **Acceptance criteria (checked at the end of M1):**
# MAGIC - The deployed `ua_support_agent` answers policy questions **with citations** and calls at least one UC-function tool.
# MAGIC - The agent version is registered in UC and promoted via the **`@champion`** alias (no run URIs in production).
# MAGIC - Prompts are governed via the **Prompt Registry** (`@champion`) — the chain loads `prompts:/...@champion`.
# MAGIC - An `mlflow.genai.evaluate(...)` scorecard (Correctness, RetrievalGroundedness, Safety) clears a promotion threshold.
# MAGIC - Tracing is on; **AI Gateway** guardrails/rate limits/payload logging are configured; monitoring reads inference tables.

# COMMAND ----------

# MAGIC %md
# MAGIC ### M1.1 — Resolve the governed handles (agent `@champion` + prompt `@champion`)
# MAGIC Production references **aliases**, never run URIs. Resolve the agent's `@champion` version and confirm the prompt
# MAGIC alias loads. If the C1–C3 artifacts are not in this workspace, the cell falls back so the rest of M1 still
# MAGIC demonstrates the API.

# COMMAND ----------

from mlflow import MlflowClient

client = MlflowClient(registry_uri="databricks-uc")
CHAMPION_VERSION = None

try:
    champ = client.get_model_version_by_alias(UC_AGENT, "champion")
    CHAMPION_VERSION = champ.version
    print(f"[live] {UC_AGENT}@champion -> v{CHAMPION_VERSION}  (tags: {champ.tags})")
except Exception as e:
    print("[illustrative] No @champion alias resolved for the agent. Finish C3 first (agents.deploy + alias).")
    print("Reason:", repr(e))
    # Fall back to the latest registered version if any exist, else stay None.
    try:
        versions = sorted(int(m.version) for m in client.search_model_versions(f"name='{UC_AGENT}'"))
        CHAMPION_VERSION = versions[-1] if versions else None
        print("Falling back to latest registered version:", CHAMPION_VERSION)
    except Exception:
        pass

# Confirm the chain's prompt is governed in the Prompt Registry (Beta), not hardcoded.
try:
    prompt = mlflow.genai.load_prompt(PROMPT_ALIAS)
    print("[live] Prompt Registry alias resolves:", PROMPT_ALIAS)
    print("       template head:", (prompt.template or "")[:120].replace("\n", " "), "...")
except Exception as e:
    print("[illustrative] Prompt Registry (Beta) alias not resolvable here. The chain should load:", PROMPT_ALIAS)
    print("Reason:", repr(e))

# COMMAND ----------

# MAGIC %md
# MAGIC ### M1.2 — Deploy the agent behind Model Serving (managed serving contract)
# MAGIC `agents.deploy()` is the one call that provisions the serving endpoint **and** the Review App **and** a feedback
# MAGIC model, and turns on tracing + inference tables + monitoring. We read the **real** endpoint name from the output —
# MAGIC never hardcode a guess (the generated name is `agents_<catalog>-<schema>-<model>`; the friendly name is
# MAGIC `ua-support-agent`). Deep walkthrough: `notebooks/11-deployment-serving/11-module-lab.py`.

# COMMAND ----------

from databricks import agents

ENDPOINT_NAME = f"agents_{CATALOG}-{RAG_SCHEMA}-ua_support_agent"   # provisional; overwritten by the deploy output

if CHAMPION_VERSION is not None:
    try:
        deployment = agents.deploy(
            UC_AGENT,
            int(CHAMPION_VERSION),
            scale_to_zero=True,   # dev: cheap idling. Prod latency-critical path -> False (warm replica), see M3.
        )
        ENDPOINT_NAME  = deployment.endpoint_name
        REVIEW_APP_URL = getattr(deployment, "review_app_url", None)
        print("Endpoint  :", ENDPOINT_NAME)
        print("Review App:", REVIEW_APP_URL)
    except Exception as e:
        print("[illustrative] agents.deploy skipped/failed (already deployed, or no agent registered). Reason:", repr(e))
        print("Using provisional endpoint name:", ENDPOINT_NAME, "— read the real one from the Serving page.")
else:
    print("[illustrative] No agent version to deploy. Provisional endpoint name:", ENDPOINT_NAME)

# COMMAND ----------

# MAGIC %md
# MAGIC ### M1.3 — Reassert AI Gateway (guardrails + rate limits on the FM endpoint; payload logging on the agent)
# MAGIC AI Gateway levers live on the **Foundation-Model endpoint the agent calls** (`ua-support-llm`) — that endpoint
# MAGIC supports safety guardrails, PII handling (Preview), rate limits, usage tracking, and fallbacks. The **agent
# MAGIC endpoint** supports **inference tables only** via AI Gateway, so payload logging goes there (it feeds Module 13
# MAGIC monitoring). This split is by design, not a workaround.

# COMMAND ----------

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.serving import (
    AiGatewayGuardrails, AiGatewayGuardrailParameters,
    AiGatewayGuardrailPiiBehavior, AiGatewayGuardrailPiiBehaviorBehavior,
    AiGatewayRateLimit, AiGatewayRateLimitKey, AiGatewayRateLimitRenewalPeriod,
    AiGatewayUsageTrackingConfig, AiGatewayInferenceTableConfig, FallbackConfig,
)

w = WorkspaceClient()

# The four gateway levers on the FM/external endpoint the agent calls.
try:
    w.serving_endpoints.put_ai_gateway(
        name=LLM_ENDPOINT,
        rate_limits=[
            AiGatewayRateLimit(
                calls=100,
                renewal_period=AiGatewayRateLimitRenewalPeriod.MINUTE,
                key=AiGatewayRateLimitKey.USER,
            ),
        ],
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
        usage_tracking_config=AiGatewayUsageTrackingConfig(enabled=True),
        fallback_config=FallbackConfig(enabled=True),
    )
    print("AI Gateway levers set on", LLM_ENDPOINT, "(rate limits, guardrails, usage, fallbacks).")
except Exception as e:
    print("[illustrative] Needs the FM endpoint live + serving-admin rights. Reason:", repr(e))

# Payload logging (inference tables) on the AGENT endpoint — the one gateway lever it supports.
try:
    w.serving_endpoints.put_ai_gateway(
        name=ENDPOINT_NAME,
        inference_table_config=AiGatewayInferenceTableConfig(
            enabled=True,
            catalog_name=CATALOG,
            schema_name=RAG_SCHEMA,
            table_name_prefix="ua_support_agent_payload",
        ),
    )
    print("Payload logging (inference tables) set on", ENDPOINT_NAME)
except Exception as e:
    print("[illustrative] Needs the live agent endpoint + serving-admin rights. Reason:", repr(e))

# COMMAND ----------

# MAGIC %md
# MAGIC ### M1.4 — The promotion gate: the C2 eval scorecard, run as a gate
# MAGIC Promotion is gated on an `mlflow.genai.evaluate(...)` scorecard — the **same** scorers you monitor with in prod
# MAGIC (Module 13), so dev and prod stay comparable. A regression must not reach `@champion`. Here we run a compact
# MAGIC scorecard (Correctness, RetrievalGroundedness, Safety) against the deployed endpoint and check a threshold. This
# MAGIC reuses the C2 harness — it does not invent a new one.

# COMMAND ----------

from mlflow.genai.scorers import Correctness, RetrievalGroundedness, Safety

PROMOTION_THRESHOLD = 0.80   # a run must clear this on every gated scorer to be promotable

# A tiny, policy-grounded gate set. In practice this is the versioned C2 eval dataset with ground truth.
gate_rows = [
    {"inputs": {"question": "Can I get a refund on a Basic Economy fare?"},
     "expectations": {"expected_facts": [
         "Basic Economy fares are generally non-refundable.",
         "A full refund is available if cancelled within 24 hours of booking."]}},
    {"inputs": {"question": "What compensation applies to an overnight cancellation?"}},
    {"inputs": {"question": "Is flight UA123 on 2026-07-20 on time?"}},   # exercises the flight-status UC tool
]

def agent_predict(question: str) -> str:
    """Call the deployed ResponsesAgent through the OpenAI-compatible client (Responses schema: an `input` array)."""
    oai = w.serving_endpoints.get_open_ai_client()
    resp = oai.responses.create(model=AGENT_ENDPOINT, input=[{"role": "user", "content": question}])
    return resp.output_text

try:
    result = mlflow.genai.evaluate(
        data=gate_rows,
        predict_fn=agent_predict,
        scorers=[Correctness(model=JUDGE), RetrievalGroundedness(model=JUDGE), Safety(model=JUDGE)],
    )
    print("Scorecard metrics:", result.metrics)
    # Gate: every mean score at/above threshold. (Metric keys are like '<scorer>/mean'.)
    gated = {k: v for k, v in result.metrics.items() if k.endswith("/mean")}
    passed = all(v >= PROMOTION_THRESHOLD for v in gated.values()) if gated else False
    print(f"Gate {'PASSED' if passed else 'FAILED'} at threshold {PROMOTION_THRESHOLD}:", gated)
    print("On PASS, promote by moving the alias:  client.set_registered_model_alias(UC_AGENT, 'champion', <ver>)")
except Exception as e:
    print("[illustrative] The gate needs a live agent endpoint + judge model. Reason:", repr(e))
    print("Recap: mlflow.genai.evaluate(data=, predict_fn=, scorers=[...]) -> compare each */mean to the threshold.")

# COMMAND ----------

# MAGIC %md
# MAGIC ### M1.5 — Query the live agent (citations + a tool call) and read its trace
# MAGIC A policy question should come back **grounded with a citation**; a booking / flight-status question should
# MAGIC trigger a **UC-function tool call**. Every call auto-emits an MLflow Trace (the atom the whole observability
# MAGIC plane reads). This is the smoke test behind M1's first acceptance criterion.

# COMMAND ----------

try:
    oai = w.serving_endpoints.get_open_ai_client()

    policy_q = "What is the checked baggage allowance on a Basic Economy fare, and where is that stated?"
    tool_q   = "Is flight UA123 on 2026-07-20 running on time?"

    for q in (policy_q, tool_q):
        resp = oai.responses.create(model=AGENT_ENDPOINT, input=[{"role": "user", "content": q}])
        print("\nQ:", q)
        print("A:", resp.output_text[:600])
    print("\nVerify: open the two traces in the MLflow UI — the policy answer shows a RETRIEVER span + citation,")
    print("the flight-status answer shows a TOOL span (get_flight_status).")
except Exception as e:
    print("[illustrative] Querying the agent needs the live endpoint. Reason:", repr(e))

# COMMAND ----------

# MAGIC %md
# MAGIC ### ✅ How to verify M1 worked
# MAGIC | Acceptance criterion | Where it is proven above |
# MAGIC |---|---|
# MAGIC | Agent answers with citations + calls a UC tool | M1.5 — policy answer cites a source; flight-status answer hits the tool |
# MAGIC | Version registered in UC + promoted via `@champion` (no run URIs) | M1.1 resolves `@champion`; M1.2 deploys that version |
# MAGIC | Prompt governed in the Prompt Registry (`@champion`) | M1.1 loads `prompts:/unity_airways.rag.ua_rag_prompt@champion` |
# MAGIC | `mlflow.genai.evaluate` scorecard clears the promotion threshold | M1.4 — Correctness/RetrievalGroundedness/Safety vs 0.80 |
# MAGIC | Tracing on; AI Gateway guardrails + rate limits + payload logging | M1.3 sets levers on `ua-support-llm`, inference tables on the agent |
# MAGIC
# MAGIC > 📌 **The support path is now one governed, observed, gated system** — not three scripts you `curl`. Next, give
# MAGIC > ops and finance their own front door.

# COMMAND ----------

# MAGIC %md
# MAGIC ## M2 · Add the Genie analytics layer (Modules 14–15)
# MAGIC **[Hands-on]** The second front door. Build **metric views** over Unity Airways operational data (the governed
# MAGIC semantic layer from Module 15), then point a **Genie Agent** (Module 14) at them so ops and finance can ask
# MAGIC business questions in English — and get the *same* number the finance dashboard shows, because both read the
# MAGIC metric view. One source of truth, not a second query path.
# MAGIC
# MAGIC We seed a small, deterministic `unity_airways.analytics` star schema and create `bookings_metrics` **inline** so
# MAGIC this milestone runs standalone. Genie Agent creation is **UI-first** (walkthrough below); we drive it with the
# MAGIC SDK. Deep dives: `notebooks/15-business-semantics/15-module-lab.py` and `notebooks/14-aibi-genie/14-8-genie-api.py`.
# MAGIC
# MAGIC **Acceptance criteria (checked at the end of M2):**
# MAGIC - At least two **metric views' worth of measures** exist under `unity_airways.analytics.*` (revenue + on-time /
# MAGIC   cancellation), each with measures, dimensions, and **agent metadata** (display names + synonyms in comments).
# MAGIC - A **Genie Agent** answers ops/finance questions grounded in those metric views, and the numbers **reconcile**
# MAGIC   with the metric-view definitions.
# MAGIC - **Verified answers** configured for the highest-value questions; access governed by Unity Catalog grants.
# MAGIC - *(Optional)* a Multi-Agent Supervisor routes a mixed support + analytics question.

# COMMAND ----------

# MAGIC %md
# MAGIC ### M2.1 — Seed the `unity_airways.analytics` star schema (idempotent, deterministic)
# MAGIC One fact + three dimensions, with `COMMENT`s (governance, and grounding text Genie reads). Rows are generated
# MAGIC from `range(0, 240)` with `pmod` — no random seed — so the numbers are reproducible and the reconciliation in
# MAGIC M2.4 is stable. This mirrors the Module 15 lab exactly.

# COMMAND ----------

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {FQ_ANALYTICS} COMMENT 'Unity Airways analytics / semantic layer.'")
spark.sql(f"USE {FQ_ANALYTICS}")

spark.sql(f"""
CREATE TABLE IF NOT EXISTS {FQ_ANALYTICS}.dim_airports (
  airport_code STRING COMMENT 'IATA airport code (primary key)',
  city         STRING COMMENT 'City served by the airport',
  country      STRING COMMENT 'Country of the airport',
  region       STRING COMMENT 'World region: AMER, EMEA, or APAC'
) COMMENT 'Airport dimension for Unity Airways routes.'
""")
spark.sql(f"""
INSERT OVERWRITE {FQ_ANALYTICS}.dim_airports VALUES
  ('SFO','San Francisco','USA','AMER'),('JFK','New York','USA','AMER'),
  ('LHR','London','UK','EMEA'),('DXB','Dubai','UAE','EMEA'),
  ('NRT','Tokyo','Japan','APAC'),('SIN','Singapore','Singapore','APAC')
""")

spark.sql(f"""
CREATE TABLE IF NOT EXISTS {FQ_ANALYTICS}.dim_flights (
  flight_id      STRING    COMMENT 'Flight identifier (primary key)',
  route_id       STRING    COMMENT 'Route code, origin-dest (e.g. SFO-JFK)',
  origin_airport STRING    COMMENT 'IATA code of departure airport (joins dim_airports)',
  dest_airport   STRING    COMMENT 'IATA code of arrival airport',
  aircraft_type  STRING    COMMENT 'Aircraft type / equipment',
  distance_miles INT       COMMENT 'Great-circle distance in miles',
  scheduled_dep  TIMESTAMP COMMENT 'Scheduled departure timestamp',
  delay_minutes  INT       COMMENT 'Departure delay in minutes (0 = on time)'
) COMMENT 'Flight dimension for Unity Airways.'
""")
spark.sql(f"""
INSERT OVERWRITE {FQ_ANALYTICS}.dim_flights VALUES
  ('FL001','SFO-JFK','SFO','JFK','A320',2586,TIMESTAMP'2025-03-02 08:00:00', 12),
  ('FL002','JFK-LHR','JFK','LHR','B77W',3451,TIMESTAMP'2025-03-02 21:30:00', 45),
  ('FL003','LHR-DXB','LHR','DXB','A388',3414,TIMESTAMP'2025-03-03 10:15:00',  0),
  ('FL004','DXB-SIN','DXB','SIN','B77W',3630,TIMESTAMP'2025-03-03 23:05:00',  8),
  ('FL005','SIN-NRT','SIN','NRT','A359',3312,TIMESTAMP'2025-03-04 07:40:00', 22),
  ('FL006','NRT-SFO','NRT','SFO','B789',5150,TIMESTAMP'2025-03-04 17:20:00',  5),
  ('FL007','SFO-LHR','SFO','LHR','A359',5367,TIMESTAMP'2025-03-05 13:10:00', 63),
  ('FL008','JFK-DXB','JFK','DXB','B77W',6842,TIMESTAMP'2025-03-05 19:55:00',  0)
""")

spark.sql(f"""
CREATE TABLE IF NOT EXISTS {FQ_ANALYTICS}.dim_customers (
  customer_id  STRING COMMENT 'Customer identifier (primary key)',
  loyalty_tier STRING COMMENT 'Frequent-flyer tier: Blue, Silver, Gold, Platinum',
  home_country STRING COMMENT 'Customer home country',
  segment      STRING COMMENT 'Travel segment: Leisure or Business',
  signup_date  DATE   COMMENT 'Loyalty program signup date'
) COMMENT 'Customer dimension for Unity Airways.'
""")
spark.sql(f"""
INSERT OVERWRITE {FQ_ANALYTICS}.dim_customers VALUES
  ('CUST01','Platinum','USA','Business', DATE'2019-05-11'),('CUST02','Gold','UK','Leisure', DATE'2020-02-03'),
  ('CUST03','Silver','Japan','Business', DATE'2021-08-19'),('CUST04','Blue','Singapore','Leisure',DATE'2023-01-27'),
  ('CUST05','Gold','UAE','Business', DATE'2020-11-30'),('CUST06','Blue','USA','Leisure', DATE'2022-06-14'),
  ('CUST07','Platinum','UK','Business', DATE'2018-09-02'),('CUST08','Silver','USA','Leisure', DATE'2021-03-22'),
  ('CUST09','Gold','Japan','Leisure', DATE'2022-12-05'),('CUST10','Blue','Singapore','Business',DATE'2023-07-18')
""")

spark.sql(f"""
CREATE OR REPLACE TABLE {FQ_ANALYTICS}.fct_bookings
COMMENT 'Booking fact for Unity Airways — one row per booking.'
AS
WITH base AS (
  SELECT
    id AS booking_id,
    concat('FL',   lpad(cast(pmod(id, 8)  + 1 AS STRING), 3, '0')) AS flight_id,
    concat('CUST', lpad(cast(pmod(id, 10) + 1 AS STRING), 2, '0')) AS customer_id,
    element_at(array('Economy','Premium','Business','First'), cast(pmod(id, 4) + 1 AS INT)) AS fare_class,
    element_at(array('Direct','OTA','Agent','Mobile'),        cast(pmod(id * 3, 4) + 1 AS INT)) AS channel,
    date_add(DATE'2025-01-01', cast(pmod(id * 11, 150) AS INT)) AS booking_date,
    round(90 + pmod(id * 13, 18) * 22
          + CASE pmod(id, 4) WHEN 0 THEN 0 WHEN 1 THEN 130 WHEN 2 THEN 520 ELSE 1150 END, 2) AS base_fare_usd,
    round(pmod(id * 7, 6) * 24.5, 2) AS ancillary_usd,
    cast(pmod(id, 3) + 1 AS INT)     AS seats,
    CASE WHEN pmod(id, 17) = 0 THEN 'cancelled' WHEN pmod(id, 3) = 0 THEN 'booked' ELSE 'flown' END AS status
  FROM range(0, 240)
)
SELECT b.booking_id, b.flight_id, b.customer_id, f.route_id, b.booking_date,
       date_add(b.booking_date, cast(14 + pmod(b.booking_id, 30) AS INT)) AS travel_date,
       b.fare_class, b.channel, b.base_fare_usd, b.ancillary_usd, b.seats, b.status
FROM base b
JOIN {FQ_ANALYTICS}.dim_flights f USING (flight_id)
""")

print("Seeded analytics star schema. fct_bookings rows:", spark.table(f"{FQ_ANALYTICS}.fct_bookings").count())

# COMMAND ----------

# MAGIC %md
# MAGIC ### M2.2 — Create the `bookings_metrics` metric view (semantic layer + agent metadata)
# MAGIC One `CREATE OR REPLACE VIEW ... WITH METRICS LANGUAGE YAML`. The shape: `source` = the fact, `joins` wire the
# MAGIC dimensions (a **snowflake** join reaches `dim_airports` *through* `dim_flights` for `Region`), `dimensions` slice,
# MAGIC `measures` aggregate. **Agent metadata (15.6)** is business-friendly `name`s + rich `comment`s (meaning, units,
# MAGIC synonyms as "Also known as ...") — this is what makes it a trusted Genie source. It carries **both** required
# MAGIC metric families: revenue and cancellation/on-time.
# MAGIC
# MAGIC > ⚠️ **GOTCHA:** there is **no** dedicated `synonyms:` or `format:` YAML key — synonyms live inside `comment`.
# MAGIC > `version: 1.1` needs DBR 17.2+; nested joins need 17.1+; metric views need a Pro/Serverless SQL warehouse.

# COMMAND ----------

spark.sql(f"""
CREATE OR REPLACE VIEW {METRIC_VIEW}
WITH METRICS
LANGUAGE YAML
AS $$
  version: 1.1
  comment: "Unity Airways bookings KPIs — the governed semantic layer for revenue + on-time analytics. Trusted source for the Genie Agent 'Unity Airways Revenue Analytics'. Grain: one booking."
  source: {FQ_ANALYTICS}.fct_bookings
  joins:
    - name: flights
      source: {FQ_ANALYTICS}.dim_flights
      on: source.flight_id = flights.flight_id
      joins:
        - name: origin_airport_info
          source: {FQ_ANALYTICS}.dim_airports
          on: flights.origin_airport = origin_airport_info.airport_code
    - name: customers
      source: {FQ_ANALYTICS}.dim_customers
      on: source.customer_id = customers.customer_id
  dimensions:
    - name: Fare Class
      expr: source.fare_class
      comment: "Cabin / booking class: Economy, Premium, Business, First. Also known as: cabin, class, service class."
    - name: Channel
      expr: source.channel
      comment: "Booking channel: Direct, OTA, Agent, Mobile. Also known as: sales channel, booking source."
    - name: Loyalty Tier
      expr: customers.loyalty_tier
      comment: "Frequent-flyer tier: Blue, Silver, Gold, Platinum. Also known as: status, membership tier."
    - name: Segment
      expr: customers.segment
      comment: "Customer travel segment: Leisure or Business. Also known as: traveler type."
    - name: Origin Airport
      expr: flights.origin_airport
      comment: "IATA code of the departure airport. Also known as: from, departure."
    - name: Dest Airport
      expr: flights.dest_airport
      comment: "IATA code of the arrival airport. Also known as: to, destination, arrival."
    - name: Region
      expr: origin_airport_info.region
      comment: "World region of the origin airport: AMER, EMEA, APAC."
    - name: Booking Month
      expr: DATE_TRUNC('MONTH', source.booking_date)
      comment: "Calendar month the booking was made."
    - name: Booking Quarter
      expr: DATE_TRUNC('QUARTER', source.booking_date)
      comment: "Calendar quarter the booking was made."
  measures:
    - name: Total Revenue
      expr: SUM(source.base_fare_usd + source.ancillary_usd)
      comment: "Base fare plus ancillary revenue, in USD. Also known as: revenue, sales, total sales."
    - name: Booking Count
      expr: COUNT(source.booking_id)
      comment: "Number of bookings. Also known as: bookings, volume."
    - name: Avg Fare
      expr: AVG(source.base_fare_usd)
      comment: "Average base fare per booking, in USD."
    - name: Cancellation Rate
      expr: COUNT(1) FILTER (WHERE source.status = 'cancelled') * 1.0 / COUNT(1)
      comment: "Share of bookings cancelled (0-1). Also known as: cancel rate, cancellation percentage, churn."
    - name: Cancelled Bookings
      expr: COUNT(1) FILTER (WHERE source.status = 'cancelled')
      comment: "Count of cancelled bookings (the numerator behind Cancellation Rate)."
    - name: Ancillary Attach Rate
      expr: SUM(source.ancillary_usd) / SUM(source.base_fare_usd)
      comment: "Ancillary revenue as a fraction of base fare. Also known as: attach rate, ancillary ratio."
$$
""")

print("Metric view created:", METRIC_VIEW)

# COMMAND ----------

# MAGIC %md
# MAGIC ### M2.3 — Query the metric view (the two rules: name the dimensions, `MEASURE()` the measures)
# MAGIC A revenue-by-fare-class query and a cancellation-rate-by-region query — the two required metric families. Joins
# MAGIC are invisible: we ask for `Region` (from `dim_airports` through `dim_flights`) with no JOIN in the SELECT.

# COMMAND ----------

display(spark.sql(f"""
  SELECT `Fare Class`,
         MEASURE(`Total Revenue`) AS total_revenue,
         MEASURE(`Booking Count`) AS bookings
  FROM {METRIC_VIEW}
  GROUP BY ALL
  ORDER BY total_revenue DESC
"""))

display(spark.sql(f"""
  SELECT `Region`, `Loyalty Tier`,
         MEASURE(`Total Revenue`)     AS revenue,
         MEASURE(`Cancellation Rate`) AS cancel_rate
  FROM {METRIC_VIEW}
  GROUP BY ALL
  ORDER BY revenue DESC
"""))

# COMMAND ----------

# MAGIC %md
# MAGIC ### M2.4 — Reconcile: the metric view is the single source of truth
# MAGIC The acceptance criterion is that Genie's numbers **reconcile with the metric-view definition** — one source of
# MAGIC truth, not a second query path. Genie is UI-gated, so the runnable proof here is the equivalence that Genie
# MAGIC inherits: **`MEASURE(Total Revenue)` from the metric view must equal the hand SQL of its definition** on the same
# MAGIC data. If a dashboard, Genie, and a notebook all go through the metric view, they cannot disagree.

# COMMAND ----------

mv_rev = {r["Fare Class"]: round(r["revenue"], 2) for r in spark.sql(f"""
  SELECT `Fare Class`, MEASURE(`Total Revenue`) AS revenue
  FROM {METRIC_VIEW} GROUP BY ALL
""").collect()}

raw_rev = {r["fare_class"]: round(r["revenue"], 2) for r in spark.sql(f"""
  SELECT fare_class, SUM(base_fare_usd + ancillary_usd) AS revenue
  FROM {FQ_ANALYTICS}.fct_bookings GROUP BY fare_class
""").collect()}

print("Metric view (MEASURE):", mv_rev)
print("Raw definition (SUM) :", raw_rev)
print("Reconciles exactly    :", mv_rev == raw_rev)
assert mv_rev == raw_rev, "Metric view and its raw definition disagree — the semantic layer is not the single source of truth."
print("\n[OK] The metric view equals its definition. Genie querying bookings_metrics returns this same governed number.")

# COMMAND ----------

# MAGIC %md
# MAGIC ### M2.5 — Create the Genie Agent (UI-first) and drive it with the SDK
# MAGIC Genie is **UI-first** — there is no create-agent SDK call. Build it in the console, then query it programmatically.
# MAGIC
# MAGIC **Console walkthrough (Module 14.2 / 14.3 / 14.5):**
# MAGIC 1. Left nav → **Genie** → **New**. **Name:** `Unity Airways Revenue Analytics`. **Warehouse:** a running
# MAGIC    **serverless (or Pro) SQL warehouse**.
# MAGIC 2. **Add data sources (the important step):** attach the **`unity_airways.analytics.bookings_metrics` metric
# MAGIC    view** (preferred — it carries governed KPI definitions) plus the star tables if you want row-level drill-down.
# MAGIC 3. **General instructions:** *"Revenue = `Total Revenue` from `bookings_metrics`; exclude cancelled bookings only
# MAGIC    when asked; 'last quarter' = previous full calendar quarter (`Booking Quarter`)."*
# MAGIC 4. **Seed sample questions:** *"What was total revenue last quarter by fare class?"*, *"Which routes have the
# MAGIC    highest cancellation rate?"*, *"Compare ancillary attach rate across loyalty tiers."*
# MAGIC 5. **Verified answers (14.5):** certify the question → SQL for the highest-value questions (the blue-check badge).
# MAGIC 6. **Share + govern:** CAN VIEW (ask) / CAN EDIT (curate). UC grants on the metric view govern who sees what —
# MAGIC    the API does **not** bypass governance.
# MAGIC 7. Copy the Agent's **`space_id`** from its URL (`.../genie/rooms/<space_id>`) into `SPACE_ID` in Step 0.
# MAGIC
# MAGIC The cell below runs the **Genie Agents API round-trip** (`w.genie.*`) once `SPACE_ID` is set. Full depth:
# MAGIC `notebooks/14-aibi-genie/14-8-genie-api.py`.

# COMMAND ----------

from databricks.sdk.service.dashboards import MessageStatus

GENIE_QUESTION = "What was total revenue last quarter by fare class?"

if SPACE_ID.startswith("REPLACE"):
    print("[skipped] Create the Genie Agent in the console, then set SPACE_ID (from .../genie/rooms/<space_id>) and re-run.")
    print("Expected: Genie's SQL should SELECT MEASURE(`Total Revenue`) FROM", METRIC_VIEW, "GROUP BY `Fare Class`,")
    print("and its numbers should match M2.4 exactly — that is the reconciliation the board wants to see.")
else:
    try:
        space = w.genie.get_space(space_id=SPACE_ID)
        print("Genie Agent:", space.title, "| warehouse:", space.warehouse_id)

        msg = w.genie.start_conversation_and_wait(space_id=SPACE_ID, content=GENIE_QUESTION)
        print("status:", msg.status, "| conversation:", msg.conversation_id)

        if msg.status == MessageStatus.COMPLETED:
            for att in (msg.attachments or []):
                if att.text:
                    print("\nGenie says:", att.text.content)
                if att.query:
                    print("\nGenerated SQL:\n", att.query.query)
                    res = w.genie.get_message_query_result(
                        space_id=SPACE_ID, conversation_id=msg.conversation_id,
                        message_id=msg.message_id or msg.id)
                    sr = res.statement_response
                    if sr and sr.result and sr.result.data_array:
                        cols = [c.name for c in sr.manifest.schema.columns]
                        print("\nColumns:", cols)
                        for row in sr.result.data_array[:10]:
                            print(row)
        else:
            print("Non-completed status — inspect msg.error:", getattr(msg, "error", None))
    except Exception as e:
        print("[illustrative] Genie round-trip needs the Agent live + SDK >= 0.73. Reason:", repr(e))

# COMMAND ----------

# MAGIC %md
# MAGIC ### M2.6 — (Optional) one entry point via a Multi-Agent Supervisor (GA)
# MAGIC A **Multi-Agent Supervisor** (Agent Bricks, GA) can route a mixed question across both paths — e.g. *"Why was the
# MAGIC Denver hub delayed last week, and what is our refund policy for delays?"* The supervisor sends the analytics half
# MAGIC to the **Genie Agent** (structured data) and the policy half to the **`ua_support_agent`** (unstructured RAG), then
# MAGIC composes one answer. It is created in the console (Agent Bricks → Multi-Agent Supervisor); register the Genie
# MAGIC Agent and the support agent as its two sub-agents. This is the "single supervised entry point" that scores
# MAGIC **Exceeds** on end-to-end coherence.

# COMMAND ----------

# MAGIC %md
# MAGIC ### ✅ How to verify M2 worked
# MAGIC | Acceptance criterion | Where it is proven above |
# MAGIC |---|---|
# MAGIC | Metric views under `unity_airways.analytics.*` w/ measures, dimensions, agent metadata | M2.2 — `bookings_metrics` (revenue + cancellation + attach rate, synonyms in comments) |
# MAGIC | Genie answers reconcile with the metric-view definitions | M2.4 asserts `MEASURE(Total Revenue) == SUM(...)`; M2.5's Genie SQL uses the same view |
# MAGIC | Verified answers configured; access governed by UC grants | M2.5 console steps 5–6 (verified answers + CAN VIEW/EDIT + UC grants) |
# MAGIC | (Optional) Multi-Agent Supervisor routes a mixed question | M2.6 |
# MAGIC
# MAGIC > 📌 **Both front doors are now live and governed.** Before the board asks, make the platform affordable and predictable.

# COMMAND ----------

# MAGIC %md
# MAGIC ## M3 · Cost, performance and scaling pass (Module 16)
# MAGIC **[Theory + Hands-on]** Right-size the serving endpoints, decide batch vs real-time per workload, set
# MAGIC concurrency/scaling, and put a spend budget on it — with numbers, not vibes. Deep dive:
# MAGIC `notebooks/16-cost-performance-scaling/16-module-lab.py`.
# MAGIC
# MAGIC **Acceptance criteria:**
# MAGIC - A documented **endpoint-sizing decision** per served workload (pay-per-token vs provisioned throughput, and why).
# MAGIC - A **batch vs real-time** call per workload: interactive support → real-time; bulk enrichment → `ai_query(...)` batch.
# MAGIC - Measured **p50/p95 latency + cost-per-1k** against a target, plus autoscaling/concurrency that holds under load.
# MAGIC - A **budget with alerts**; note **Unity AI Gateway** budgets / hard caps as the go-forward control (Beta).

# COMMAND ----------

# MAGIC %md
# MAGIC ### M3.1 — Endpoint-sizing decisions (the "is a human waiting?" table)
# MAGIC The first question is always *is a human waiting?* — it routes the workload. Interactive support is real-time;
# MAGIC nightly enrichment is batch. Sizing follows from traffic shape + latency target + cost.

# COMMAND ----------

import pandas as pd

sizing = pd.DataFrame([
    {"workload": "ua-support-agent (interactive Q&A)", "human_waiting": "yes", "mode": "Real-time serving",
     "endpoint": "provisioned throughput (or pay-per-token in dev)",
     "why": "Steady interactive load + p95 latency SLA. Turn OFF scale_to_zero on the prod path to kill cold starts."},
    {"workload": "ua-support-llm (FM the agent calls)", "human_waiting": "yes", "mode": "Real-time serving",
     "endpoint": "provisioned throughput",
     "why": "Predictable tokens/sec under load; this is where AI Gateway rate limits + budgets live."},
    {"workload": "Nightly ticket enrichment", "human_waiting": "no", "mode": "Batch ai_query()",
     "endpoint": "SQL compute (no serving replicas)",
     "why": "Large table, no synchronous user, consistent schema -> scale by adding SQL compute, not replicas."},
    {"workload": "Genie analytics (ops/finance)", "human_waiting": "yes", "mode": "Serverless SQL warehouse",
     "endpoint": "serverless SQL (auto-stop)",
     "why": "Spiky human-driven queries; serverless auto-stop keeps idle cost near zero. Agent mode costs more — reserve for real investigations."},
])
print(sizing.to_string(index=False))

# COMMAND ----------

# MAGIC %md
# MAGIC ### M3.2 — Batch: enrich a whole ticket table on SQL compute (the "no human waiting" engine)
# MAGIC Score a whole table of tickets in one pass on SQL compute — it never touches the real-time endpoint. Use the
# MAGIC **cheaper task-specific AI Functions** where the task fits (`ai_classify` for intent, `ai_analyze_sentiment` for
# MAGIC tone). For **free-form generation** at scale, use the general **`ai_query(..., failOnError => false)`** path — it
# MAGIC returns a struct where `.response` holds the answer and `.errorMessage` the per-row error, so one bad row can't
# MAGIC fail the whole run (Module 16 / 11.10). Filter `WHERE ... IS NOT NULL` either way. We seed a tiny tickets table
# MAGIC idempotently so this runs standalone.

# COMMAND ----------

spark.sql(f"""
CREATE TABLE IF NOT EXISTS {TICKETS_TABLE} (
  ticket_id STRING, channel STRING, language STRING, raw_text STRING
)
""")
if spark.table(TICKETS_TABLE).count() == 0:
    spark.sql(f"""
    INSERT INTO {TICKETS_TABLE} VALUES
      ('T-3001','email','en','Flight UA482 was cancelled and I have not been rebooked. Please help.'),
      ('T-3002','chat','en','How much does an extra checked bag cost on a transatlantic route?'),
      ('T-3003','phone','en','I was double-charged for seat selection on booking ABC123 and need a refund.'),
      ('T-3004','app_review','en','Crew were lovely and boarding was quick. Best service in ages.'),
      ('T-3005','email','en','My connection was missed after a four-hour delay in Denver.')
    """)
    print("Seeded", TICKETS_TABLE)
else:
    print(TICKETS_TABLE, "already populated — reusing it.")

# COMMAND ----------

# MAGIC %sql
# MAGIC -- Batch enrichment: cheaper task-specific functions where the task fits; ai_query for free-form.
# MAGIC CREATE OR REPLACE TABLE unity_airways.rag.ua_tickets_enriched_c4 AS
# MAGIC SELECT
# MAGIC   ticket_id,
# MAGIC   channel,
# MAGIC   ai_classify(raw_text, ARRAY('baggage','delay','billing','praise','other')) AS intent,
# MAGIC   ai_analyze_sentiment(raw_text)                                             AS sentiment
# MAGIC FROM unity_airways.rag.ua_support_tickets
# MAGIC WHERE raw_text IS NOT NULL;   -- NULL in => NULL out; filtering also saves the wasted (billable) calls

# COMMAND ----------

# MAGIC %sql
# MAGIC -- How to verify: sensible buckets + a sentiment spread.
# MAGIC SELECT intent, sentiment, count(*) AS n
# MAGIC FROM unity_airways.rag.ua_tickets_enriched_c4
# MAGIC GROUP BY 1, 2 ORDER BY n DESC

# COMMAND ----------

# MAGIC %md
# MAGIC ### M3.3 — Real-time: measure p50/p95 latency on the agent endpoint
# MAGIC When a human is waiting, **latency** is the metric that matters (not throughput). A `ResponsesAgent` speaks the
# MAGIC Responses schema — call it through the OpenAI-compatible client (`responses.create(model=..., input=[...])`),
# MAGIC **not** `query(extra_body=...)`. Skip cleanly if the endpoint is not live.

# COMMAND ----------

import time

try:
    oai = w.serving_endpoints.get_open_ai_client()
    prompt = "My flight is at 4pm — what is the check-in cutoff?"
    lat = []
    for _ in range(5):
        s = time.perf_counter()
        _ = oai.responses.create(model=AGENT_ENDPOINT, input=[{"role": "user", "content": prompt}])
        lat.append(time.perf_counter() - s)
    lat.sort()
    p50 = lat[len(lat) // 2] * 1000
    p95 = lat[max(0, int(0.95 * (len(lat) - 1)))] * 1000
    print(f"Real-time agent endpoint — {len(lat)} calls")
    print(f"  p50 latency: {p50:.0f} ms   p95 latency: {p95:.0f} ms   target: < 3000 ms p95")
    print("  (5 samples — illustrative only; measure p50/p95 over a real load test for a defensible number.)")
    print("  If cold-start dominates p95, turn OFF scale_to_zero on the prod path (M3.1).")
except Exception as e:
    print("[illustrative] Real-time timing needs the live endpoint. Reason:", repr(e))
    print("  Target to document: p95 < 3000 ms for interactive support; measure against your SLA under a load test.")

# COMMAND ----------

# MAGIC %md
# MAGIC ### M3.4 — Cost-per-1k lens and where the budget lives
# MAGIC Foundation Models bill **per token**, so cost scales with prompt length, retrieved context, and response length.
# MAGIC The estimator is **illustrative** — plug in your workspace's real per-token price. The lesson (16.2): context
# MAGIC length and top-k are cost levers on **every** call.

# COMMAND ----------

def est_cost_per_1k(avg_input_tokens, avg_output_tokens,
                    price_per_1k_input=0.003, price_per_1k_output=0.015):
    """Illustrative cost for 1,000 requests. Replace the price constants with your real per-token rates."""
    reqs = 1000
    return round(reqs * (avg_input_tokens/1000*price_per_1k_input + avg_output_tokens/1000*price_per_1k_output), 2)

fat  = est_cost_per_1k(4000, 300)   # 15 chunks stuffed into a 32k context
lean = est_cost_per_1k(800, 150)    # top-5 chunks, trimmed context
print(f"Illustrative cost per 1,000 requests:")
print(f"  Fat prompt  (4000 in / 300 out): ${fat}")
print(f"  Lean prompt (800 in / 150 out) : ${lean}")
print(f"  Saving from context/top-k trim : ${round(fat - lean, 2)}  ({round(100*(fat-lean)/fat)}% lower)")
print("\nNumbers are illustrative — the point is that context + top-k are per-call cost levers.")

# COMMAND ----------

# MAGIC %md
# MAGIC ### M3.5 — Budgets and alerts (where spend control must live)
# MAGIC - **AI Gateway rate limits + budgets go on the FM/external endpoint** (`ua-support-llm`), **not** the agent
# MAGIC   endpoint — the agent endpoint supports inference tables only. To cap the agent's spend, cap the FM endpoint it calls.
# MAGIC - **Unity AI Gateway budgets** (Beta) are the go-forward control: spend thresholds + **hard caps** per team, plus
# MAGIC   MCP-service governance. Label it Beta in the one-pager and confirm availability in the customer's workspace.
# MAGIC - Read **real** spend from **usage system tables** + **inference tables** (Module 13), then size limits from data —
# MAGIC   not a guess. Keep separate alerts for **performance**, **cost**, and **reliability** (Module 13.6), each with an
# MAGIC   owner and a first investigation step.
# MAGIC
# MAGIC ### ✅ How to verify M3 worked
# MAGIC | Acceptance criterion | Where it is proven above |
# MAGIC |---|---|
# MAGIC | Endpoint-sizing decision per workload, justified | M3.1 sizing table |
# MAGIC | Batch vs real-time chosen per workload | M3.1 (choice) + M3.2 (batch AI Functions; `ai_query` for free-form) + M3.3 (real-time timing) |
# MAGIC | Measured p50/p95 + cost-per-1k vs target | M3.3 (p50/p95) + M3.4 (cost-per-1k) |
# MAGIC | Budget with alerts; Unity AI Gateway hard caps noted (Beta) | M3.5 |

# COMMAND ----------

# MAGIC %md
# MAGIC ## M4 · Reference architecture + one-pager (Module 17)
# MAGIC **[Theory + Hands-on]** Turn the running system into something a review board can read and challenge: the
# MAGIC end-to-end reference architecture, the single-page diagram, and the written-down trade-offs. Grounding:
# MAGIC `modules/17-reference-architectures/module.md`.
# MAGIC
# MAGIC **Acceptance criteria:**
# MAGIC - A **reference architecture** showing the 5-phase lifecycle (Develop → Evaluate → Deploy → Monitor → Improve) as
# MAGIC   structure, with **MLflow Traces as the shared integration artifact** across support and analytics.
# MAGIC - The **architecture one-pager** shows both planes + the data → index → agent → serving → monitor flow + the
# MAGIC   parallel Genie analytics path — on one page, legible from across a room.
# MAGIC - **Trade-offs written down** (real-time vs batch, alias vs pinned version, provisioned vs pay-per-token,
# MAGIC   Knowledge Assistant vs custom `ResponsesAgent`, single agent vs Multi-Agent Supervisor).
# MAGIC - You can survive a mock **architecture-review Q&A** (governance, failure modes, cost, rollback).

# COMMAND ----------

# MAGIC %md
# MAGIC ### M4.1 — The 5-phase lifecycle IS the architecture
# MAGIC Develop → Evaluate → Deploy → Monitor → Improve is not a slideware pipeline — it is a **loop**, and every module
# MAGIC you built slots into exactly one phase. The Improve phase feeds production evidence back into Develop, and the
# MAGIC **same trace schema and scorers run in every phase** so dev and prod stay comparable.
# MAGIC
# MAGIC ```mermaid
# MAGIC flowchart LR
# MAGIC   DEV["1 · Develop<br/>Modules 01-05, 09-10<br/>trace-first, minimum evaluable product"]
# MAGIC   EVAL["2 · Evaluate<br/>Module 08<br/>scorers: groundedness, safety, correctness"]
# MAGIC   DEP["3 · Deploy<br/>Modules 11-12<br/>versioned app behind serving + AI Gateway"]
# MAGIC   MON["4 · Monitor<br/>Module 13<br/>traces + inference tables + online scorers"]
# MAGIC   IMP["5 · Improve<br/>Module 13.7<br/>curate prod failures into the eval set"]
# MAGIC   DEV --> EVAL --> DEP --> MON --> IMP
# MAGIC   IMP -->|"re-evaluate, then redeploy"| DEV
# MAGIC ```

# COMMAND ----------

# MAGIC %md
# MAGIC ### M4.2 — The architecture one-pager (recap, board-ready)
# MAGIC **Unity Airways GenAI Platform — one platform, two front doors, two shared planes.**
# MAGIC
# MAGIC - **Governance plane — Unity Catalog.** Catalogs/schemas (`unity_airways.rag`, `unity_airways.analytics`), grants
# MAGIC   (least-privilege on models, functions, data, and the metric view), lineage, the **Model Registry** (`@champion`),
# MAGIC   and the **Prompt Registry** (`prompts:/...@champion`, Beta). Everything the platform serves is a governed asset.
# MAGIC - **Observability / integration plane — MLflow 3.** One **Trace** per request (the system of record), one
# MAGIC   **eval loop** (`mlflow.genai.evaluate`) that gates promotion, and **production monitoring (Beta)** reading inference
# MAGIC   tables. MLflow is the integration plane: the trace, the serving contract, and the eval loop all live here.
# MAGIC - **Support path (front door 1).** Policy PDFs → RAG ingestion → **`ua_rag_chunks_index`** (AI Search) →
# MAGIC   **`ua_rag_chain`** (retriever + `databricks-claude-sonnet-4-5`, prompt from the registry) →
# MAGIC   **`ua_support_agent`** (`ResponsesAgent` + UC-function tools) → **AI Gateway on `ua-support-llm`** →
# MAGIC   **Model Serving `ua-support-agent`** + Review App → **Databricks App** chat UI.
# MAGIC - **Analytics path (front door 2).** Operational data → **metric views** (`unity_airways.analytics.bookings_metrics`,
# MAGIC   the semantic layer) → **Genie Agent** "Unity Airways Revenue Analytics" → **Genie One** for business users.
# MAGIC - **The wires between the boxes.** The agent **emits** one MLflow Trace per call; serving **logs** to inference
# MAGIC   tables that monitoring reads; the eval scorecard **gates** promotion; the cost/scaling pass **governs** the
# MAGIC   gateway budget. Same two planes under both paths — that is what makes it one platform, not three demos.
# MAGIC
# MAGIC The full architecture diagram is at the top of this notebook (Target architecture) and mirrored in
# MAGIC `modules/17-reference-architectures/module.md` (Diagram 2). Put that single page in front of the board.

# COMMAND ----------

# MAGIC %md
# MAGIC ### M4.3 — Trade-offs, written down (the board will ask)
# MAGIC | Decision | Option A | Option B | Platform choice + why |
# MAGIC |---|---|---|---|
# MAGIC | Serving mode | Real-time serving | Batch `ai_query()` | **Both, by "is a human waiting?"** — support real-time, nightly enrichment batch (M3.1) |
# MAGIC | Version reference | `@champion` alias | Pinned version number | **Alias** in production — promotion is a one-line alias flip, rollback keeps the old version serving (M1) |
# MAGIC | FM billing | Pay-per-token | Provisioned throughput | **Provisioned** for steady prod load + latency SLA; pay-per-token for dev/spiky (M3.1) |
# MAGIC | Agent build | Knowledge Assistant (low-code) | Custom `ResponsesAgent` | **Custom `ResponsesAgent`** — needs UC-function tools (booking + flight status) beyond cited Q&A |
# MAGIC | Orchestration | Single agent | Multi-Agent Supervisor | **Single agent** to ship; **Supervisor (GA)** when one entry point must route support + analytics (M2.6) |
# MAGIC | Semantic layer | Genie over raw tables | Genie over **metric views** | **Metric views** — one definition of "revenue", numbers reconcile with the dashboard (M2.4) |
# MAGIC
# MAGIC ### M4.4 — Mock architecture-review Q&A (be ready for these)
# MAGIC - **"When a request goes wrong, where do I look?"** → One MLflow Trace with `AGENT`/`TOOL`/`RETRIEVER` spans and
# MAGIC   `session_id` / `app_version` tags. Same trace for product, platform, and agent developers.
# MAGIC - **"A regression reached prod — walk the rollback."** → Repoint the `@champion` alias to the previous version;
# MAGIC   the endpoint URL and clients are unchanged; the old version never stopped serving. Monitoring (the observability
# MAGIC   plane) is what told you it happened. Nothing in the governance plane is edited in place.
# MAGIC - **"How is cost bounded?"** → AI Gateway rate limits + budget on `ua-support-llm`; Unity AI Gateway hard caps
# MAGIC   (Beta); serverless auto-stop for Genie; batch for enrichment; context/top-k trimmed (M3).
# MAGIC - **"How does analytics stay consistent with finance?"** → Genie answers off `bookings_metrics`; the metric view
# MAGIC   equals its definition (M2.4), so Genie and the dashboard cannot drift.
# MAGIC
# MAGIC > 💡 **TIP:** On a whiteboard, draw the **two planes first** (UC + MLflow), then hang the boxes on them. It reframes
# MAGIC > "which product?" into "how does it stay coherent?" — the architect-level conversation.

# COMMAND ----------

# MAGIC %md
# MAGIC ### M4.5 — Cross-stack: OTel dual export + the MCP bridge (code where an API exists)
# MAGIC The integration plane reaches beyond Databricks. Two reference snippets from Module 17 (run against your own
# MAGIC collector / assistant — shown as the verified mechanism, not executed here so tracing is not redirected).
# MAGIC
# MAGIC **17.3 — OTel dual export** (send the *same* trace to both MLflow and your org's OTel collector). There is **no**
# MAGIC `MLFLOW_ENABLE_DUAL_EXPORT` flag — point OTel at your collector, hand it the tracer provider, and register MLflow
# MAGIC as a destination:
# MAGIC
# MAGIC ```python
# MAGIC import os, mlflow
# MAGIC from mlflow.entities.trace_location import MlflowExperimentLocation
# MAGIC
# MAGIC os.environ["OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"] = "<collector-endpoint-url>"
# MAGIC os.environ["OTEL_SERVICE_NAME"] = "unity-airways-support"       # groups traces in the OTel backend
# MAGIC os.environ["MLFLOW_USE_DEFAULT_TRACER_PROVIDER"] = "false"      # let OTel own the tracer provider
# MAGIC mlflow.set_tracking_uri("databricks")
# MAGIC mlflow.tracing.set_destination(MlflowExperimentLocation(experiment_id="<experiment-id>"))
# MAGIC ```
# MAGIC
# MAGIC **17.5 — MLflow MCP server** (let a coding assistant operate on your trace data directly). Launch:
# MAGIC `pip install 'mlflow[mcp]>=3.5.1'`, then in the assistant's MCP config:
# MAGIC
# MAGIC ```jsonc
# MAGIC {
# MAGIC   "mcpServers": {
# MAGIC     "mlflow": {
# MAGIC       "command": "uv",
# MAGIC       "args": ["run", "--with", "mlflow[mcp]>=3.5.1", "mlflow", "mcp", "run"],
# MAGIC       "env": { "MLFLOW_TRACKING_URI": "databricks",
# MAGIC                "DATABRICKS_HOST": "https://<your-workspace-host>",
# MAGIC                "DATABRICKS_TOKEN": "<token>" }
# MAGIC     }
# MAGIC   }
# MAGIC }
# MAGIC ```
# MAGIC
# MAGIC > ⚠️ **GOTCHA:** OTel semantic-convention field names evolve — read current docs, don't hardcode from a book.
# MAGIC > The MLflow MCP server is **experimental** and (at time of writing) does **not** reach UC-stored traces; managed
# MAGIC > MCP servers on Databricks are **Public Preview**. Confirm maturity before a customer commitment. **⚠️ live
# MAGIC > re-check pending** on both.

# COMMAND ----------

# MAGIC %md
# MAGIC ## M5 · Cert-readiness map + FDE delivery kit + demo script (Tracks C/D)
# MAGIC **[Theory + Hands-on]** Prove exam-readiness and package the platform for a customer hand-over. Largely `%md`
# MAGIC deliverables — that is expected and correct for M5.
# MAGIC
# MAGIC **Acceptance criteria:**
# MAGIC - A **cert-domain readiness map**: each of the 8 exam domains points to a concrete platform component; no domain unbacked.
# MAGIC - The FDE delivery assets exist and are usable: **architecture one-pager**, **POC scorecard**,
# MAGIC   **production-readiness checklist** (Track D / `databricks-one-pager`).
# MAGIC - A **stakeholder demo script**: a 10-minute walk — a support answer with citations, a Genie answer that matches
# MAGIC   the dashboard, a trace, an eval scorecard, and the cost budget.
# MAGIC - The production-readiness checklist is all-green, or every red item has a named owner and date.

# COMMAND ----------

# MAGIC %md
# MAGIC ### M5.1 — Cert-domain readiness map (all 8 domains → a real component)
# MAGIC C4 is the integrative capstone: it does not add a domain, it demonstrates **all 8** at once against a running
# MAGIC system. Walk the board along this table in order — each row is a live artifact you can click into.
# MAGIC
# MAGIC | Exam domain | Modules | Where it lives in the platform (exact name) |
# MAGIC |---|---|---|
# MAGIC | **1 — Designing GenAI applications** | 01, 02, 09 | Support-agent design: prompt templates, tool selection, `ResponsesAgent` + supervisor topology (M1, M4) |
# MAGIC | **2 — Data prep for RAG** | 03, 04 | Ingestion → chunking → embeddings → `unity_airways.rag.ua_rag_chunks_index` on Databricks AI Search (M1, from C1) |
# MAGIC | **3 — Building applications** | 05, 09 | `unity_airways.rag.ua_rag_chain` (`databricks-langchain`) + the `ua_support_agent` UC-function tools (M1) |
# MAGIC | **4 — Deploying + integrating** | 11, 04 | `agents.deploy(...)`, AI Gateway, Model Serving, batch `ai_query`, Genie/App surfaces (M1, M2, M3) |
# MAGIC | **5 — Models with MLflow + Unity Catalog** | 06, 07 | UC Model Registry (`@champion`), MLflow 3 tracing + LoggedModel across the platform (M1, M4) |
# MAGIC | **6 — Governance** | 12, 02.5 | AI Gateway guardrails + PII, UC grants + lineage on models/functions/data/metric views, prompt versions in the Prompt Registry (M1, M2) |
# MAGIC | **7 — Monitoring + evaluation** | 08, 13 | `mlflow.genai.evaluate` scorecard, production monitoring (Beta), inference tables, alerts, the Improve loop (M1, M5) |
# MAGIC | **8 — Scaling (Vector Search + Mosaic AI)** | 04, 16 | Index + endpoint sizing, provisioned throughput, batch inference, budgets (M3) |
# MAGIC
# MAGIC > 💡 **TIP:** If a row has no component behind it, that is your remaining study gap — the capstone doubles as your
# MAGIC > readiness self-check.

# COMMAND ----------

# MAGIC %md
# MAGIC ### M5.2 — Production-readiness checklist (all-green, or owner + date on every red)
# MAGIC | Area | Check | Status | Owner / date |
# MAGIC |---|---|---|---|
# MAGIC | **Governance** | UC grants least-privilege on models, functions, data, metric view | 🟢 | Platform |
# MAGIC | **Governance** | Prompt versioned in the Prompt Registry (`@champion`, Beta) | 🟢 | Platform |
# MAGIC | **Security** | AI Gateway guardrails (safety) on `ua-support-llm`; PII handling **Preview** | 🟡 | Security · confirm PII GA date |
# MAGIC | **Observability** | MLflow 3 trace on every call; `session_id`/`app_version` tags | 🟢 | App team |
# MAGIC | **Observability** | Production monitoring reads inference tables **(Beta)**; alerts have owners | 🟡 | SRE · monitoring Beta |
# MAGIC | **Quality** | `mlflow.genai.evaluate` scorecard gates every promotion | 🟢 | ML team |
# MAGIC | **Cost** | Endpoint sizing justified; budget + alerts on the FM endpoint | 🟡 | FinOps · Unity AI Gateway budgets Beta |
# MAGIC | **Analytics** | Genie answers off metric views; numbers reconcile (M2.4) | 🟢 | Analytics |
# MAGIC | **Rollback** | Promotion = alias flip; documented one-line rollback | 🟢 | ML team |
# MAGIC | **On-call** | Each alert names a team + first investigation step | 🟢 | SRE |
# MAGIC
# MAGIC No red items; three yellows are Beta/Preview dependencies with named owners — acceptable to ship with the maturity
# MAGIC labelled. Build the polished one-pager + POC scorecard with the `databricks-one-pager` skill (Track D).

# COMMAND ----------

# MAGIC %md
# MAGIC ### M5.3 — Stakeholder demo script (10 minutes)
# MAGIC 1. **(1 min) Frame it.** "Three demos became one platform on two shared planes." Show the one-pager (M4.2).
# MAGIC 2. **(2 min) Support answer with citations.** Ask the Databricks App / `ua-support-agent` a refund question →
# MAGIC    grounded answer **with a source citation**. Then a flight-status question → watch it **call the UC tool** (M1.5).
# MAGIC 3. **(2 min) Analytics answer that matches finance.** Ask Genie "total revenue last quarter by fare class" → show
# MAGIC    the number equals the metric-view / dashboard number (M2.4). One source of truth.
# MAGIC 4. **(2 min) The trace.** Open the support request's MLflow Trace — `AGENT` / `TOOL` / `RETRIEVER` spans, latency,
# MAGIC    tokens. "This one artifact is read by product, platform, and eval."
# MAGIC 5. **(1 min) The eval scorecard.** Show the `mlflow.genai.evaluate` scorecard that gates promotion (M1.4) — a
# MAGIC    regression cannot reach `@champion`.
# MAGIC 6. **(1 min) The cost budget.** Show the sizing decision + the AI Gateway budget/alert on `ua-support-llm` (M3).
# MAGIC 7. **(1 min) Close on the loop.** A production failure → curated into the eval set → re-evaluated → promoted by
# MAGIC    alias flip. Develop → Evaluate → Deploy → Monitor → Improve, back to Develop (M4.1).
# MAGIC
# MAGIC ### ✅ How to verify M5 worked
# MAGIC | Acceptance criterion | Where it is proven above |
# MAGIC |---|---|
# MAGIC | 8-domain cert map, no domain unbacked | M5.1 |
# MAGIC | FDE assets exist + usable (one-pager, scorecard, checklist) | M4.2 (one-pager) + M5.2 (checklist) + `databricks-one-pager` (scorecard) |
# MAGIC | 10-minute stakeholder demo script | M5.3 |
# MAGIC | Readiness checklist all-green or every red owned + dated | M5.2 (no red; yellows owned) |

# COMMAND ----------

# MAGIC %md
# MAGIC ## Closing — deliverables, rubric self-score, and the finish line
# MAGIC
# MAGIC ### The five deliverables (all present in this notebook)
# MAGIC 1. **The running platform** — deployed `ua_support_agent` behind AI Gateway (M1) + a Genie Agent over
# MAGIC    `unity_airways.analytics.*` metric views (M2), both governed and observed, inside a budget (M3).
# MAGIC 2. **Architecture one-pager** — the whole platform on one page (M4.2 + the Target architecture diagram up top).
# MAGIC 3. **Production-readiness checklist** — governance, security, observability, cost, rollback, on-call, with owners (M5.2).
# MAGIC 4. **Cert-readiness map** — 8 exam domains → the component that proves each (M5.1).
# MAGIC 5. **Stakeholder demo script** — the 10-minute narrated walk-through (M5.3).
# MAGIC
# MAGIC ### Grading rubric — self-score
# MAGIC | Criterion | Target: Meets | This build |
# MAGIC |---|---|---|
# MAGIC | **End-to-end coherence** | One platform on shared `unity_airways` names; support + analytics both live | ✅ Meets (Exceeds with the M2.6 Supervisor) |
# MAGIC | **Governance + observability** | UC least-privilege; MLflow 3 traces on every call; monitoring reads inference tables | ✅ Meets |
# MAGIC | **Analytics correctness (metric views)** | Genie answers off metric views; numbers reconcile | ✅ Meets — reconciliation asserted in M2.4 |
# MAGIC | **Cost-awareness** | Endpoint sizing justified; batch vs real-time chosen; a budget with alerts | ✅ Meets |
# MAGIC | **Architecture clarity** | One-pager shows both planes + both paths; trade-offs written | ✅ Meets |
# MAGIC | **Cert-domain coverage** | All 8 domains mapped to a real component | ✅ Meets — with exact API/name per row (Exceeds) |
# MAGIC
# MAGIC ### Self-check (answer these to prove you can walk the platform)
# MAGIC 1. Name the two shared planes and one component on each.
# MAGIC 2. Why must Genie answer off **metric views** rather than raw tables? What breaks if it doesn't?
# MAGIC 3. Support endpoint vs nightly enrichment: which is real-time, which is batch `ai_query`, and why?
# MAGIC 4. Which exam domain do the `@champion` alias + MLflow 3 tracing demonstrate, and where do you point to prove it?
# MAGIC 5. A regression reaches production — walk the rollback: what do you repoint, what stays untouched, which plane tells you?
# MAGIC
# MAGIC > 📌 **This is the roadmap's final artifact.** The stack is complete: built (00–10), productionized (11–13), made
# MAGIC > conversational (14–15), right-sized (16), unified into one reference architecture (17), and here **assembled,
# MAGIC > defended, and packaged** for the exam and a customer hand-over. If you can point at a component for every one of
# MAGIC > the 8 domains and follow a single trace across both front doors, you can pass the exam — and you can ship the platform.
