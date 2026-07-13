# Databricks notebook source
# MAGIC %md
# MAGIC # Module 13 lab — Monitor and improve the Unity Airways support agent
# MAGIC **Roadmap:** Module 13 (Production monitoring and continuous improvement) · Topics **13.2 / 13.3 / 13.4 / 13.6 / 13.7** · [Hands-on]
# MAGIC
# MAGIC This is the consolidated lab that closes the loop on the **Unity Airways support agent** (endpoint
# MAGIC `ua-support-agent`). Modules 11–12 got it live, guardrailed, and governed. Here you make it **watched and always
# MAGIC improving**: capture the signal already flowing, score it with the *same* judges from dev, alert on drift, and fold
# MAGIC real failures back into the eval set for the next release. One narrative — **capture → assess → watch → improve**.
# MAGIC
# MAGIC | Step | Topic | What you do |
# MAGIC |---|---|---|
# MAGIC | 1 | **13.3 + 13.2** | Read auto-captured **MLflow traces** (`search_traces`), peek at the **inference table** (AI Gateway 11.3), attach a 👎 with `mlflow.log_feedback` |
# MAGIC | 2 | **13.4** ★ Beta | Reuse the Module 08 scorers as **production monitors** — `set_databricks_monitoring_sql_warehouse_id` → `.register()` → `.start()` |
# MAGIC | 3 | **13.6** | **Metric alerts + anomaly detection** — a Databricks SQL alert (static threshold) + a statistical/baseline check, in plain SQL |
# MAGIC | 4 | **13.7** | The **improve loop** — pull failing traces with `search_traces`, curate them into the Module 08 eval dataset (`mlflow.genai.datasets`) |
# MAGIC
# MAGIC > 📌 **Pointer — the 13.5 cornerstone lives in its own notebook.** The deep **NLP-on-traces + custom AI/BI (Lakeview)
# MAGIC > dashboard** build — syncing traces to Unity Catalog and running `ai_classify` / `ai_analyze_sentiment` / `ai_summarize`
# MAGIC > to land `unity_airways.rag.ua_request_metrics` — is in **`13-5-aibi-dashboard.py`**. This lab **reads** that metrics
# MAGIC > table (and seeds a representative slice so it runs standalone); it does **not** rebuild the enrichment pipeline.
# MAGIC
# MAGIC ## Prerequisites (read before running)
# MAGIC - **Compute:** **serverless** notebook/job, or a **DBR ML** runtime (15.4 LTS ML or later). The SQL cells (Steps 3–4)
# MAGIC   need a **serverless or Pro SQL warehouse** (or DBR 15.1+).
# MAGIC - **MLflow:** **>= 3.4** (`mlflow[databricks]`). **Production monitoring — scorers as monitors — is Beta.**
# MAGIC - **A deployed agent with traces:** the endpoint + experiment from **Module 07 / Module 11** (`agents.deploy()`), which
# MAGIC   auto-captures traces and provisions **inference tables** (via **AI Gateway payload logging, 11.3**).
# MAGIC - **A SQL warehouse** — its ID feeds the scorer-monitor job (Step 2) and runs the alert SQL (Step 3).
# MAGIC - **Unity Catalog:** read/write on `unity_airways.rag` (this lab seeds a metrics table and curates an eval dataset there).
# MAGIC - **`mlflow` / `databricks-sdk` names churn between versions and some monitoring surface is Beta.** Where a call is
# MAGIC   load-bearing the cell flags **"confirm against your installed mlflow/databricks-sdk"**.
# MAGIC
# MAGIC > ⚠️ **Runnability note:** the live-endpoint steps (`search_traces`, scorer `.register()/.start()`, `log_feedback`,
# MAGIC > dataset `merge_records`) are wrapped in `try/except` with `[illustrative]` fallbacks, so the notebook runs
# MAGIC > top-to-bottom **without** a live agent. The alert/anomaly SQL (Step 3) and the improve-loop curation (Step 4) run for
# MAGIC > real against a **seeded** metrics table.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 0. Install libraries and restart Python
# MAGIC `mlflow[databricks] >= 3.4` brings the MLflow 3 GenAI surface used across this lab: `mlflow.search_traces`,
# MAGIC `mlflow.log_feedback`, `mlflow.genai.scorers` (production monitors), and `mlflow.genai.datasets`. `databricks-sdk`
# MAGIC is used only to *read* the endpoint config. Pin versions so behavior is predictable across serverless and classic compute.

# COMMAND ----------

# MAGIC %pip install -U "mlflow[databricks]>=3.4" databricks-sdk
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Set variables
# MAGIC One place for every name the lab uses. Fill in `EXPERIMENT_ID` and `SQL_WAREHOUSE_ID` with your own — the rest follow
# MAGIC the course conventions (`unity_airways.rag`, endpoint `ua-support-agent`, judge `databricks-gpt-oss-120b`).

# COMMAND ----------

CATALOG = "unity_airways"
SCHEMA  = "rag"

# The MLflow experiment your endpoint logs traces to (13.3). Read it from the Experiments UI, or resolve a name:
#   mlflow.get_experiment_by_name("/Shared/ua-support-agent").experiment_id
EXPERIMENT_ID   = "0000000000000000"          # <-- REPLACE with your experiment id (a string of digits)
EXPERIMENT_NAME = "/Shared/ua-support-agent"  # used only to set the active experiment for scorer monitors
# NOTE: EXPERIMENT_NAME and EXPERIMENT_ID must resolve to the SAME experiment (name activates it; id targets monitoring).

# The SQL warehouse that (a) runs the scorer-monitor job in Step 2 and (b) runs the alert SQL in Step 3.
SQL_WAREHOUSE_ID = "abcd1234efgh5678"          # <-- REPLACE with your SQL warehouse id

FRIENDLY_ENDPOINT = "ua-support-agent"                       # the deployed agent (Module 11)
JUDGE             = "databricks:/databricks-gpt-oss-120b"    # LLM that backs the scorer judges; confirm on the supported-models page

# Tables. The metrics table is the CONTRACT built in 13-5-aibi-dashboard.py; we seed a slice so this lab runs standalone.
METRICS_TABLE = f"{CATALOG}.{SCHEMA}.ua_request_metrics"   # unity_airways.rag.ua_request_metrics  (from 13.5)
EVAL_DATASET  = f"{CATALOG}.{SCHEMA}.eval_dataset"         # unity_airways.rag.eval_dataset        (from Module 08)

# AI Gateway payload-logging inference table (11.3 used table_name_prefix="ua_support_gateway" -> <prefix>_payload).
# The exact name depends on how you configured payload logging — confirm in your workspace.
INFERENCE_TABLE = f"{CATALOG}.{SCHEMA}.ua_support_gateway_payload"

import mlflow
print("mlflow version   :", mlflow.__version__)
print("Experiment id    :", EXPERIMENT_ID, "(replace with your own)")
print("SQL warehouse id :", SQL_WAREHOUSE_ID, "(replace with your own)")
print("Metrics table    :", METRICS_TABLE)
print("Eval dataset     :", EVAL_DATASET)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 1 — Capture: real-time traces, inference tables, and feedback (13.3 + 13.2) · [Hands-on]
# MAGIC **No new instrumentation.** The moment a request hits `ua-support-agent`, the Databricks Agent SDK auto-captures an
# MAGIC MLflow **Trace** to the experiment — the *same* traces you wrote in **Module 07**, reused as-is in production. In
# MAGIC parallel, **AI Gateway payload logging** (11.3) writes one row per call to an **inference table** (the primary audit
# MAGIC trail). Together they are the raw signal everything downstream reads.
# MAGIC
# MAGIC > 📌 **IMPORTANT — the trace is the atom.** The same MLflow Trace is the monitoring signal, the scorer input, the
# MAGIC > dashboard row (13.5), the alert trigger (13.6), and — when it fails — the next eval-set record (13.7).

# COMMAND ----------

# MAGIC %md
# MAGIC ### 1a. Read recent traces with `mlflow.search_traces`
# MAGIC `search_traces` pulls production traces into a **pandas DataFrame** you can inspect, filter, and write to Delta.
# MAGIC
# MAGIC > ⚠️ **GOTCHA — the argument is `experiment_ids=` (a LIST).** There is **no `experiment_names=`** argument on
# MAGIC > `search_traces`; passing it raises a `TypeError`. If you only know the name, resolve it first with
# MAGIC > `mlflow.get_experiment_by_name("/Shared/...").experiment_id`.
# MAGIC >
# MAGIC > ⚠️ **GOTCHA — the `filter_string` grammar is strict.** Prefix fields (`attributes.status`, `attributes.timestamp_ms`),
# MAGIC > use **single quotes** for values, and use `AND` — **`OR` is not supported.** Time is epoch milliseconds.

# COMMAND ----------

import mlflow

try:
    traces_df = mlflow.search_traces(
        experiment_ids=[EXPERIMENT_ID],              # a LIST of experiment IDs — never experiment_names=
        filter_string="attributes.status = 'OK'",    # note the attributes. prefix + single quotes
        order_by=["attributes.timestamp_ms DESC"],   # newest first
        max_results=100,                             # cap the pull; page for more if needed
    )
    print(len(traces_df), "traces")
    # Typical columns: request, response, trace_id, execution_time_ms, request_time, tokens, assessments, ...
    print(traces_df.columns.tolist())
    display(traces_df.head(10))
except Exception as e:
    # No live experiment yet (or EXPERIMENT_ID is still the placeholder). Fall back to an illustrative empty DataFrame
    # so the rest of the notebook keeps running end-to-end.
    import pandas as pd
    print("[illustrative] search_traces needs a live experiment with traces. Reason:", repr(e))
    traces_df = pd.DataFrame(
        columns=["trace_id", "request", "response", "execution_time_ms", "request_time", "assessments"]
    )

# COMMAND ----------

# MAGIC %md
# MAGIC ### 1b. Inference tables — the AI Gateway payload log (13.2)
# MAGIC Where they come from: **AI Gateway payload logging** on the endpoint (Module **11.3**) and `agents.deploy()`. **One row
# MAGIC per model invocation** — request/response, token counts, latency, model id, timestamps. It is the audit trail and the
# MAGIC raw material for SQL analysis (the 13.5 dashboard reads it).
# MAGIC
# MAGIC > ⚠️ **GOTCHA — sensitive data.** Inference tables store **raw user content**. Treat them as sensitive: apply
# MAGIC > retention + redaction, and govern access in Unity Catalog.
# MAGIC
# MAGIC We query it **only if present** (the name depends on your 11.3 payload-logging config), guarded so the lab runs without it.

# COMMAND ----------

# Query the inference table if it exists. Guarded with spark.sql (a bare %sql cell errors hard on a missing table).
try:
    if spark.catalog.tableExists(INFERENCE_TABLE):
        print("Inference table found:", INFERENCE_TABLE)
        display(spark.sql(f"""
            SELECT *
            FROM {INFERENCE_TABLE}
            ORDER BY 1 DESC
            LIMIT 20
        """))
    else:
        print(f"[illustrative] {INFERENCE_TABLE} not found — turn on AI Gateway payload logging (11.3) to populate it.")
        print("The AI Gateway inference table is named <catalog>.<schema>.<table_name_prefix>_payload.")
except Exception as e:
    print("[illustrative] Could not query the inference table. Reason:", repr(e))

# COMMAND ----------

# MAGIC %md
# MAGIC ### 1c. Link a traveler's 👎 to the exact request with `mlflow.log_feedback` (13.3)
# MAGIC When a user reacts, the app attaches feedback to that request's trace by `trace_id`. It lands as an **Assessment** on
# MAGIC the trace (tagged `HUMAN`), so expert sign-off stays separable from noisy thumbs-down clicks — and it becomes both a
# MAGIC monitoring signal and an improve-loop candidate (Step 4).
# MAGIC
# MAGIC > 💡 **TIP:** get the `trace_id` back on the chat call with `"databricks_options": {"return_trace": true}`, then feed it here.

# COMMAND ----------

from mlflow.entities.assessment import AssessmentSource, AssessmentSourceType

def log_end_user_feedback(trace_id, satisfied, rationale=None, user_id="traveler_web"):
    """Attach a 👍/👎 to a specific trace. value=False is a thumbs-down. Confirm the log_feedback / AssessmentSource
    signature against your installed mlflow (the assessments API is evolving)."""
    mlflow.log_feedback(
        trace_id=trace_id,
        name="user_feedback",
        value=satisfied,                 # True = thumbs-up, False = thumbs-down
        rationale=rationale,             # optional short comment
        source=AssessmentSource(source_type=AssessmentSourceType.HUMAN, source_id=user_id),
    )

# Grab one real trace id from Step 1a to attach a thumbs-down to.
sample_trace_id = None
if len(traces_df) and "trace_id" in traces_df.columns:
    sample_trace_id = traces_df.iloc[0]["trace_id"]

try:
    if sample_trace_id:
        log_end_user_feedback(sample_trace_id, satisfied=False,
                              rationale="Answer didn't state the baggage overage fee.")
        print("Logged HUMAN thumbs-down on trace:", sample_trace_id)
        print("Verify: open the trace in the MLflow UI — the feedback shows under Assessments.")
    else:
        print("[illustrative] No live trace_id to attach feedback to. With a live endpoint, this logs a 👎 as an Assessment.")
except Exception as e:
    print("[illustrative] log_feedback needs a live trace. Reason:", repr(e))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 2 — Assess: reuse the Module 08 scorers as production monitors (13.4) · [Hands-on] · **Beta**
# MAGIC Latency and tokens are structured. **Quality is not** — "was this answer safe, relevant, grounded?" lives in free text.
# MAGIC So you let the **same MLflow scorers you used offline in Module 08** run continuously over production traces. Register
# MAGIC each one, start it, and a managed **Lakeflow Job** ("Trace Metrics Computation Job") scores a **sampled** slice on a
# MAGIC schedule and writes the scores back onto the traces. MLflow also creates a **default dashboard** in the experiment.
# MAGIC
# MAGIC > 📌 **IMPORTANT:** these are the **same scorer objects** as offline evaluation. One metric definition measures quality
# MAGIC > in dev **and** prod, so version-over-version comparisons stay honest.
# MAGIC >
# MAGIC > ⚠️ **GOTCHA — Beta + version churn.** Production monitoring (scorers as monitors) is **Beta**. This cell uses the
# MAGIC > keyword **`sql_warehouse_id=`** on `set_databricks_monitoring_sql_warehouse_id`; some mlflow builds name it
# MAGIC > `warehouse_id=`. Both `.register()` and `.start()` are required — registering alone runs nothing. **Confirm against
# MAGIC > your installed mlflow.** Wrapped in `try/except` so a name mismatch fails soft.

# COMMAND ----------

import mlflow
from mlflow.genai.scorers import (
    Safety, RelevanceToQuery, RetrievalGroundedness, ScorerSamplingConfig,
)
from mlflow.tracing import set_databricks_monitoring_sql_warehouse_id

try:
    mlflow.set_experiment(EXPERIMENT_NAME)   # the production experiment the traces land in

    # 1) Point monitoring at a SQL warehouse that will run the scorer job.
    #    NOTE the kwarg name: sql_warehouse_id (NOT warehouse_id). Only takes effect for experiments whose
    #    trace location is a UC schema. Confirm against your installed mlflow.
    set_databricks_monitoring_sql_warehouse_id(
        sql_warehouse_id=SQL_WAREHOUSE_ID,   # <-- kwarg is sql_warehouse_id; some builds use warehouse_id
        experiment_id=EXPERIMENT_ID,         # optional; uses the active experiment if omitted
    )

    # 2) Register AND start each scorer. Sampling controls cost: score every trace for safety (1.0),
    #    sample the expensive judges lower.
    safety = Safety(model=JUDGE).register(name="prod_safety")
    safety = safety.start(sampling_config=ScorerSamplingConfig(sample_rate=1.0))   # every trace

    relevance = RelevanceToQuery(model=JUDGE).register(name="prod_relevance")
    relevance = relevance.start(sampling_config=ScorerSamplingConfig(sample_rate=0.5))

    grounded = RetrievalGroundedness(model=JUDGE).register(name="prod_groundedness")
    grounded = grounded.start(sampling_config=ScorerSamplingConfig(sample_rate=0.5))

    print("Started monitors: prod_safety (1.0), prod_relevance (0.5), prod_groundedness (0.5)")
    print("A managed Lakeflow Job was provisioned to run these — adjust its schedule in the Jobs UI.")
    print("MLflow also created a default monitoring dashboard in the experiment.")
except Exception as e:
    print("[illustrative] Scorer monitors need a live experiment + SQL warehouse + monitoring (Beta). Reason:", repr(e))
    print("Recap: set_databricks_monitoring_sql_warehouse_id(sql_warehouse_id=...) then .register() AND .start().")

# COMMAND ----------

# MAGIC %md
# MAGIC ### 2b. Manage the monitors later — list / retune sampling / pause
# MAGIC List what is running, fetch one, dial its sampling up or down, or pause it. Same objects, managed live.

# COMMAND ----------

from mlflow.genai.scorers import list_scorers, get_scorer, delete_scorer, ScorerSamplingConfig

try:
    # What is registered on the active experiment?
    for s in list_scorers():
        rate = getattr(s, "sample_rate", "N/A")   # public property; sampling_config is private (_sampling_config)
        print(f"  {s.name}: sample_rate={rate}")

    # Raise groundedness coverage from 0.5 -> 0.8 (e.g. you want a finer signal on a suspect retrieval path).
    g = get_scorer(name="prod_groundedness")
    g = g.update(sampling_config=ScorerSamplingConfig(sample_rate=0.8))

    # Pause but KEEP the registration (re-.start() later):   g = g.stop()
    # Remove entirely:                                        delete_scorer(name="prod_groundedness")
    print("Managed prod_groundedness -> sample_rate=0.8 (stop()/delete_scorer() shown in comments).")
except Exception as e:
    print("[illustrative] Managing scorers needs the monitors registered in Step 2. Reason:", repr(e))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 3 — Watch: metric alerts and anomaly detection (13.6) · [Hands-on] · SQL + UI
# MAGIC A dashboard is passive — someone has to be looking. **Alerts page you.** A Databricks SQL alert is a **saved query** +
# MAGIC a **condition** (threshold) + a **schedule** + a **notification destination**. Pair two kinds:
# MAGIC - **Static thresholds** — a fixed cap (latency, token, or "Other"-intent count). Catches sudden spikes.
# MAGIC - **Statistical / baseline deviation** — compare today to a rolling mean ± k·stddev. Catches slow drift.
# MAGIC
# MAGIC The alerts run over the **`unity_airways.rag.ua_request_metrics`** table built in **13.5** (`13-5-aibi-dashboard.py`).
# MAGIC We first **seed a representative slice** so these cells run standalone; the queries below are exactly what you would
# MAGIC save behind an alert.

# COMMAND ----------

# MAGIC %md
# MAGIC ### 3a. Seed a representative metrics slice (idempotent)
# MAGIC `CREATE TABLE IF NOT EXISTS` + insert-only-when-empty means this **never clobbers** the real table built by
# MAGIC `13-5-aibi-dashboard.py` — if that notebook already ran, both cells are no-ops. The schema matches the 13.5 contract;
# MAGIC we populate the columns the alerts need (`ts`, `topic`, `latency_ms`, scores, feedback) and leave the rest NULL. The
# MAGIC last day carries a **spike in the "Other" bucket** (new demand) and a **latency spike** so both alert types have
# MAGIC something to fire on.

# COMMAND ----------

# MAGIC %sql
# MAGIC -- One row per request. Same column contract as unity_airways.rag.ua_request_metrics in 13-5-aibi-dashboard.py.
# MAGIC CREATE TABLE IF NOT EXISTS unity_airways.rag.ua_request_metrics (
# MAGIC   request_id      STRING,
# MAGIC   ts              TIMESTAMP,
# MAGIC   user_question   STRING,
# MAGIC   agent_response  STRING,
# MAGIC   latency_ms      BIGINT,
# MAGIC   input_tokens    BIGINT,
# MAGIC   output_tokens   BIGINT,
# MAGIC   total_tokens    BIGINT,
# MAGIC   status          STRING,
# MAGIC   relevance       DOUBLE,   -- from the RelevanceToQuery monitor (Step 2)
# MAGIC   safety          DOUBLE,   -- from the Safety monitor
# MAGIC   groundedness    DOUBLE,   -- from the RetrievalGroundedness monitor
# MAGIC   user_feedback   STRING,   -- 👍/👎 from mlflow.log_feedback (Step 1c)
# MAGIC   topic           STRING,   -- from ai_classify (13.5); "Other" is the drift bucket
# MAGIC   sentiment       STRING,   -- from ai_analyze_sentiment (13.5)
# MAGIC   answer_summary  STRING    -- from ai_summarize (13.5)
# MAGIC );

# COMMAND ----------

# MAGIC %sql
# MAGIC -- Insert only when empty (never clobbers the real 13.5 table). Populate the alert-relevant columns.
# MAGIC INSERT INTO unity_airways.rag.ua_request_metrics
# MAGIC   (request_id, ts, user_question, latency_ms, total_tokens, status, relevance, safety, groundedness, user_feedback, topic, sentiment)
# MAGIC SELECT * FROM (VALUES
# MAGIC   ('tr-0001', TIMESTAMP'2026-07-06 09:12:00', 'How do I check in online for flight UA482?',        1820, 430, 'OK', 0.97, 0.99, 0.95, 'up',   'Check-in',     'neutral'),
# MAGIC   ('tr-0002', TIMESTAMP'2026-07-06 11:40:00', 'My checked bag never arrived in Lisbon?',           2510, 420, 'OK', 0.93, 0.99, 0.90, NULL,   'Baggage',      'negative'),
# MAGIC   ('tr-0003', TIMESTAMP'2026-07-07 08:05:00', 'Cancel booking ABC123 and refund me',               1990, 455, 'OK', 0.88, 0.98, 0.86, 'down', 'Cancellation', 'negative'),
# MAGIC   ('tr-0004', TIMESTAMP'2026-07-07 14:22:00', 'Extra checked bag cost transatlantic?',             1750, 370, 'OK', 0.95, 0.99, 0.94, 'up',   'Baggage',      'neutral'),
# MAGIC   ('tr-0005', TIMESTAMP'2026-07-08 10:31:00', 'Upgrade my seat to business with points?',          2120, 420, 'OK', 0.91, 0.99, 0.88, NULL,   'Loyalty',      'neutral'),
# MAGIC   ('tr-0006', TIMESTAMP'2026-07-08 16:47:00', 'App crashes on the payment screen at check-in',     3010, 490, 'OK', 0.84, 0.98, 0.80, 'down', 'Check-in',     'negative'),
# MAGIC   ('tr-0007', TIMESTAMP'2026-07-09 09:58:00', 'Double-charged for seat selection on XYZ789',       2280, 445, 'OK', 0.90, 0.99, 0.87, 'down', 'Refunds',      'negative'),
# MAGIC   ('tr-0008', TIMESTAMP'2026-07-09 12:15:00', 'What is the refund window for a Flex fare?',         1680, 370, 'OK', 0.96, 0.99, 0.93, 'up',   'Refunds',      'neutral'),
# MAGIC   ('tr-0009', TIMESTAMP'2026-07-10 08:44:00', 'Do you offer a pet-in-cabin option?',                2350, 420, 'OK', 0.92, 0.99, 0.89, NULL,   'Baggage',      'neutral'),
# MAGIC   ('tr-0010', TIMESTAMP'2026-07-10 15:03:00', 'Flight cancelled and not rebooked yet',              2740, 470, 'OK', 0.89, 0.99, 0.85, 'down', 'Cancellation', 'negative'),
# MAGIC   ('tr-0011', TIMESTAMP'2026-07-11 10:05:00', 'How do I check in for a group booking?',             1900, 400, 'OK', 0.94, 0.99, 0.91, 'up',   'Check-in',     'neutral'),
# MAGIC   ('tr-0012', TIMESTAMP'2026-07-11 13:20:00', 'Baggage allowance on a Lite fare?',                  1770, 360, 'OK', 0.95, 0.99, 0.92, NULL,   'Baggage',      'neutral'),
# MAGIC   -- last day (2026-07-12): "Other" bucket SPIKES (seat-upgrade / lounge / wifi demand the FAQ never covered)
# MAGIC   ('tr-0013', TIMESTAMP'2026-07-12 09:10:00', 'Can I buy a lounge pass for my layover?',            2050, 410, 'OK', 0.72, 0.99, 0.70, 'down', 'Other',        'negative'),
# MAGIC   ('tr-0014', TIMESTAMP'2026-07-12 10:35:00', 'Is there in-flight wifi and how much is it?',        1980, 400, 'OK', 0.70, 0.99, 0.68, 'down', 'Other',        'negative'),
# MAGIC   ('tr-0015', TIMESTAMP'2026-07-12 11:50:00', 'How do I request a paid seat upgrade at the gate?',  2200, 430, 'OK', 0.71, 0.99, 0.69, NULL,   'Other',        'neutral'),
# MAGIC   -- and a LATENCY spike on the same day (peak-hour prompt-token inflation, the B2 case-study pattern)
# MAGIC   ('tr-0016', TIMESTAMP'2026-07-12 18:05:00', 'Why was my card declined during booking?',           8200, 900, 'OK', 0.83, 0.99, 0.82, 'down', 'Refunds',      'negative')
# MAGIC ) AS v(request_id, ts, user_question, latency_ms, total_tokens, status, relevance, safety, groundedness, user_feedback, topic, sentiment)
# MAGIC WHERE (SELECT count(*) FROM unity_airways.rag.ua_request_metrics) = 0;

# COMMAND ----------

# MAGIC %md
# MAGIC ### 3b. Static-threshold alert #1 — topic-drift on the "Other" bucket
# MAGIC A rising **"Other"** count is your cheapest early-warning for drift and unmet demand (travelers asking about topics the
# MAGIC agent was never built for). This is the query you save behind the alert; the alert **condition** is
# MAGIC `other_count_latest_day > 2`.

# COMMAND ----------

# MAGIC %sql
# MAGIC -- Alert query: count "Other"-intent requests on the most recent day in the table.
# MAGIC -- Save this query, then Create alert -> condition: value column other_count_latest_day > 2.
# MAGIC SELECT
# MAGIC   COUNT(*) AS other_count_latest_day
# MAGIC FROM unity_airways.rag.ua_request_metrics
# MAGIC WHERE topic = 'Other'
# MAGIC   AND DATE(ts) = (SELECT MAX(DATE(ts)) FROM unity_airways.rag.ua_request_metrics);

# COMMAND ----------

# MAGIC %md
# MAGIC ### 3c. Static-threshold alert #2 — latency spike (p95)
# MAGIC A fixed cap on tail latency catches sudden slowdowns. Alert **condition**: `p95_latency_ms_latest_day > 5000`.

# COMMAND ----------

# MAGIC %sql
# MAGIC -- Alert query: p95 latency on the most recent day. percentile_approx goes in the SQL (a widget/alert cannot do it).
# MAGIC SELECT
# MAGIC   percentile_approx(latency_ms, 0.95) AS p95_latency_ms_latest_day
# MAGIC FROM unity_airways.rag.ua_request_metrics
# MAGIC WHERE DATE(ts) = (SELECT MAX(DATE(ts)) FROM unity_airways.rag.ua_request_metrics);

# COMMAND ----------

# MAGIC %md
# MAGIC ### 3d. Statistical / baseline anomaly check
# MAGIC Static thresholds miss **slow drift**. This computes a per-day baseline (trailing mean ± 2·stddev over the prior 7 days)
# MAGIC and flags any day whose p95 latency **or** "Other" count breaks out. Baselines often come from your controlled MLflow
# MAGIC eval results (Module 08), so you can tell a regression from routine noise. In production you'd save this as its own alert.

# COMMAND ----------

# MAGIC %sql
# MAGIC WITH daily AS (
# MAGIC   SELECT
# MAGIC     DATE(ts)                                    AS day,
# MAGIC     COUNT(*)                                    AS request_count,
# MAGIC     percentile_approx(latency_ms, 0.95)         AS p95_latency_ms,
# MAGIC     SUM(CASE WHEN topic = 'Other' THEN 1 ELSE 0 END) AS other_count
# MAGIC   FROM unity_airways.rag.ua_request_metrics
# MAGIC   GROUP BY DATE(ts)
# MAGIC ),
# MAGIC baseline AS (
# MAGIC   SELECT
# MAGIC     day, request_count, p95_latency_ms, other_count,
# MAGIC     AVG(p95_latency_ms) OVER (ORDER BY day ROWS BETWEEN 7 PRECEDING AND 1 PRECEDING) AS p95_mean,
# MAGIC     STDDEV(p95_latency_ms) OVER (ORDER BY day ROWS BETWEEN 7 PRECEDING AND 1 PRECEDING) AS p95_sd,
# MAGIC     AVG(other_count) OVER (ORDER BY day ROWS BETWEEN 7 PRECEDING AND 1 PRECEDING) AS other_mean,
# MAGIC     STDDEV(other_count) OVER (ORDER BY day ROWS BETWEEN 7 PRECEDING AND 1 PRECEDING) AS other_sd
# MAGIC   FROM daily
# MAGIC )
# MAGIC SELECT
# MAGIC   day, request_count, p95_latency_ms, ROUND(p95_mean, 0) AS p95_baseline, ROUND(p95_sd, 0) AS p95_stddev,
# MAGIC   CASE WHEN p95_latency_ms   > p95_mean   + 2 * COALESCE(p95_sd, 0)   THEN 'ANOMALY' ELSE 'ok' END AS latency_flag,
# MAGIC   other_count,
# MAGIC   CASE WHEN other_count      > other_mean + 2 * COALESCE(other_sd, 0) THEN 'ANOMALY' ELSE 'ok' END AS drift_flag
# MAGIC FROM baseline
# MAGIC ORDER BY day;

# COMMAND ----------

# MAGIC %md
# MAGIC ### 3e. Wire the alert in the UI (there is no invented alert SDK to hand-write)
# MAGIC An alert is built from a **saved query**, not a Python call in this lab:
# MAGIC 1. **SQL editor** → paste an alert query above (e.g. 3b) → **Save**.
# MAGIC 2. **Alerts → Create alert** → pick the saved query → set the **condition** (e.g. `other_count_latest_day` `>` `2`).
# MAGIC 3. Set the **check schedule** (a cron, e.g. hourly) and a **notification destination** (email, Slack, or a webhook).
# MAGIC 4. Keep separate alerts for **performance**, **cost**, and **reliability**.
# MAGIC
# MAGIC > 📌 **IMPORTANT — make alerts actionable.** Each alert should name the **responsible team**, the **expected response
# MAGIC > time**, and the **first investigation step** (e.g. "sample the Other-bucket traces, check for a new route"). An alert
# MAGIC > with no owner or runbook is just noise.
# MAGIC >
# MAGIC > ⚠️ **GOTCHA:** the `databricks-sdk` does expose an Alerts API, but the class/field names churn across versions
# MAGIC > (legacy `alerts` vs newer `alerts_v2`). Prefer the **SQL editor + Alerts UI** path shown here, or confirm the SDK
# MAGIC > surface against your installed `databricks-sdk` before scripting it.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 4 — Improve: curate failing traces into the eval dataset (13.7) · [Hands-on]
# MAGIC The point of monitoring is the **next version**. Real production traces are the best ground truth you'll ever get —
# MAGIC fold the failing/negative-feedback ones into the **Module 08 eval dataset** so v2 is tested against reality, not just
# MAGIC dev fixtures. This is the closed feedback loop: **evaluate in dev → monitor in prod → curate failures → re-evaluate → redeploy.**
# MAGIC
# MAGIC > 💡 **TIP:** filter the improve-loop query on **negative feedback or failed scorers**, not `status='OK'` — you want the
# MAGIC > regressions-in-waiting, not the easy wins.

# COMMAND ----------

# MAGIC %md
# MAGIC ### 4a. Pull the failing / negative-feedback traces
# MAGIC `search_traces` gets you the DataFrame; you then keep the rows that failed. The `filter_string` demonstrated here is the
# MAGIC verified-safe `attributes.status = 'OK'`; the *failure* filter (negative feedback, low groundedness) is applied in pandas,
# MAGIC because assessment-based `filter_string` grammar is stricter and evolving — **confirm it against your installed mlflow**
# MAGIC before relying on `assessments.user_feedback = false`.

# COMMAND ----------

import pandas as pd

curated_rows = []   # what we will merge into the eval dataset (each row: {"inputs": {"question": ...}})

try:
    recent = mlflow.search_traces(
        experiment_ids=[EXPERIMENT_ID],
        filter_string="attributes.status = 'OK'",   # verified-safe filter; failure filtering happens below in pandas
        order_by=["attributes.timestamp_ms DESC"],
        max_results=200,
    )
    # In practice: keep rows with a thumbs-down OR a low groundedness score. Column names vary by mlflow version —
    # inspect recent.columns and adapt. This is the "regressions-in-waiting" slice.
    failing = recent  # <-- replace with your real failure filter, e.g. negative-feedback / low-score rows
    for _, r in failing.iterrows():
        q = r.get("request")
        if q is not None:
            curated_rows.append({"inputs": {"question": str(q)}})
    print(f"[live] {len(curated_rows)} candidate failing traces pulled from the experiment.")
except Exception as e:
    print("[illustrative] search_traces needs a live experiment. Falling back to the seeded metrics table. Reason:", repr(e))

# Standalone fallback: derive "failures" from the seeded metrics table (thumbs-down OR groundedness < 0.85).
if not curated_rows:
    failing_df = spark.sql("""
        SELECT user_question
        FROM unity_airways.rag.ua_request_metrics
        WHERE user_feedback = 'down' OR groundedness < 0.85
    """).toPandas()
    curated_rows = [{"inputs": {"question": q}} for q in failing_df["user_question"].tolist()]
    print(f"[illustrative] Built {len(curated_rows)} curated rows from seeded negative/low-score requests.")

for row in curated_rows[:5]:
    print(" -", row["inputs"]["question"])

# COMMAND ----------

# MAGIC %md
# MAGIC ### 4b. Merge them into the Module 08 eval dataset (`mlflow.genai.datasets`)
# MAGIC `get_dataset` resolves the existing UC-backed eval dataset (create it if this is the first curation); `merge_records`
# MAGIC appends the new rows and auto-versions with lineage. Now every future `mlflow.genai.evaluate()` run tests v2 against
# MAGIC these **real** failures.
# MAGIC
# MAGIC > 📌 **NOTE — confirm the import path against your runtime.** This lab uses `from mlflow.genai.datasets import
# MAGIC > get_dataset, create_dataset`; some builds expose `mlflow.genai.get_dataset`. `merge_records` accepts the
# MAGIC > `search_traces` DataFrame or a list of `{"inputs": ...}` rows — the datasets API is evolving, so verify.

# COMMAND ----------

try:
    from mlflow.genai.datasets import get_dataset, create_dataset

    try:
        ds = get_dataset(name=EVAL_DATASET)          # resolve the existing Module 08 dataset
        print("Resolved existing eval dataset:", EVAL_DATASET)
    except Exception:
        ds = create_dataset(name=EVAL_DATASET)       # first curation -> create the governed, versioned UC table
        print("Created eval dataset:", EVAL_DATASET)

    ds = ds.merge_records(curated_rows)              # append the curated failures; auto-versions with lineage
    print(f"Merged {len(curated_rows)} curated rows into {EVAL_DATASET} — the closed feedback loop.")
except Exception as e:
    print("[illustrative] Needs the mlflow.genai.datasets API + UC write access. Reason:", repr(e))
    print("Fallback: the curated_rows list works directly as data= in mlflow.genai.evaluate(...).")

# COMMAND ----------

# MAGIC %md
# MAGIC ### 4c. Re-evaluate, then redeploy (hand-off to Modules 08 and 11)
# MAGIC The curation is done — the rest of the loop is work you already know:
# MAGIC - **Re-evaluate (Module 08):** run `mlflow.genai.evaluate(data=<this dataset>, predict_fn=<v2>, scorers=[...])` with the
# MAGIC   **same scorers** you monitor with. The new baggage/route/"Other" rows are now permanent regression tests.
# MAGIC - **Redeploy (Module 11):** if v2 clears the bar, promote it by **moving the `@champion` alias** (11.8 / 12.7) so the
# MAGIC   endpoint URL stays stable and the audit trail holds — never an in-place overwrite.
# MAGIC - Then **monitor again** (Steps 1–3). The loop repeats.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Recap — you closed the monitor → improve loop
# MAGIC - **Capture (13.2 / 13.3):** read auto-captured traces with `mlflow.search_traces(experiment_ids=[...])`, peeked at the
# MAGIC   AI Gateway **inference table**, and attached a 👎 with `mlflow.log_feedback(...)` + a HUMAN `AssessmentSource`.
# MAGIC - **Assess (13.4, Beta):** reused the Module 08 scorers (`Safety`, `RelevanceToQuery`, `RetrievalGroundedness`) as
# MAGIC   **production monitors** — `set_databricks_monitoring_sql_warehouse_id(sql_warehouse_id=...)` then `.register()` **and**
# MAGIC   `.start()` with `ScorerSamplingConfig(sample_rate=...)`; managed with `list_scorers` / `get_scorer` / `.stop()`.
# MAGIC - **Watch (13.6):** static-threshold **SQL alerts** (the "Other" drift bucket, p95 latency) plus a
# MAGIC   **statistical/baseline** anomaly check — all in plain SQL over `ua_request_metrics`, wired via the Alerts UI.
# MAGIC - **Improve (13.7):** pulled failing traces with `search_traces` and curated them into the eval dataset with
# MAGIC   `mlflow.genai.datasets` (`get_dataset` / `create_dataset` + `merge_records`).
# MAGIC
# MAGIC **Gotchas to remember**
# MAGIC - **`experiment_ids=` (a list), never `experiment_names=`** on `search_traces`; `filter_string` uses `attributes.` + single quotes, `AND` only.
# MAGIC - **Both `.register()` and `.start()`** — registering alone runs nothing. Sampling controls judge cost. **Production monitoring is Beta.**
# MAGIC - **Inference tables hold raw user content** — retention + redaction; govern in UC.
# MAGIC - **No invented alert SDK** — alerts are a saved SQL query + condition + schedule + destination, wired in the UI; `percentile_approx` goes in the SQL.
# MAGIC - **Curate on negative feedback / failed scorers**, not `status='OK'` — monitoring without the improve loop is just watching.
# MAGIC - **Confirm mlflow/databricks-sdk names against your installed versions** (Beta surface + `sql_warehouse_id=` vs `warehouse_id=`, datasets import path).
# MAGIC
# MAGIC **Cross-references**
# MAGIC - **13.5 ★ (`13-5-aibi-dashboard.py`):** the NLP-on-traces enrichment that *builds* `ua_request_metrics`, plus the custom AI/BI dashboard this lab's alerts sit on top of.
# MAGIC - **Module 08:** the *same* scorer objects, run offline — here they run online.
# MAGIC - **Module 11.3:** AI Gateway payload logging → the inference table this pipeline reads.
# MAGIC
# MAGIC > 📌 **This completes Level 5 (Production).** The Unity Airways agent is now **watched and always improving** — captured,
# MAGIC > scored with the same judges from dev, dashboarded, alerted, and feeding its own failures back into the next release.
# MAGIC
# MAGIC **Next module → Level 6 · Module 14 — AI/BI Genie:** conversational analytics — let business users ask questions of
# MAGIC governed data in natural language (Genie Agents, formerly Genie Spaces).
