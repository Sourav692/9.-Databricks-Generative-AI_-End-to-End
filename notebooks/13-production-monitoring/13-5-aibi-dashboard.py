# Databricks notebook source
# MAGIC %md
# MAGIC # NLP analysis on traces and a custom AI/BI monitoring dashboard
# MAGIC **Roadmap:** Module 13 (Production monitoring and continuous improvement) · Topic **13.5 ★** · [Hands-on]
# MAGIC
# MAGIC Your Unity Airways support agent (`ua-support-agent`) is live and answering thousands of traveler
# MAGIC questions a week. Two raw signals are already flowing: **MLflow traces** (Module 07) and the **AI Gateway
# MAGIC inference table** (11.3). This notebook turns that raw, per-request signal into a **dashboard a director can read**.
# MAGIC
# MAGIC ## The pipeline you build here
# MAGIC | Step | What you do | Product |
# MAGIC |---|---|---|
# MAGIC | 1 | Read production traces into a pandas DataFrame | `mlflow.search_traces` |
# MAGIC | 2 | Turn **quality** into columns with scorers running as **production monitors** *(Beta)* | `mlflow.genai.scorers` |
# MAGIC | 3 | Turn **text** into columns (topic, sentiment, summary) | SQL **AI Functions** |
# MAGIC | 4 | Land one flat **per-request metrics Delta table** | `unity_airways.rag.ua_request_metrics` |
# MAGIC | 5 | Build the **AI/BI dashboard** (Lakeview) — dataset SQL + UI tiles | AI/BI dashboards |
# MAGIC
# MAGIC > 📌 **The one idea:** 13.5 is a **pipeline, not a feature.** Raw signal (traces + inference tables) →
# MAGIC > enrich (AI Functions for text, scorers for quality) → a per-request metrics Delta table → an AI/BI dashboard for humans.
# MAGIC
# MAGIC ## Prerequisites (read before running)
# MAGIC - **Compute:** **serverless** notebook/job, or a **DBR ML** runtime. Steps 3–5 (SQL AI Functions) need a
# MAGIC   **serverless or Pro SQL warehouse** (or DBR 15.1+) with AI Functions available.
# MAGIC - **MLflow:** **>= 3.4** (`mlflow[databricks]`). **Production monitoring — scorers as monitors — is Beta.**
# MAGIC - **A deployed agent with traces:** the endpoint + experiment from Module 07 / Module 11 (`agents.deploy()`),
# MAGIC   with **inference tables** turned on (11.3) and traces landing in an MLflow experiment (13.3).
# MAGIC - **A SQL warehouse** (its ID feeds the scorer-monitor job in Step 2 and runs the AI Functions in Steps 3–5).
# MAGIC - **Unity Catalog:** write access to `unity_airways.rag` (this notebook creates two tables there).
# MAGIC - **`mlflow` / `databricks-sdk` names churn between versions.** Where a call is load-bearing, the cell flags
# MAGIC   **"confirm against your installed mlflow/databricks-sdk version"** — some of the monitoring surface is Beta and can shift.
# MAGIC
# MAGIC > ⚠️ **Runnability note:** Steps 1 and 2 depend on a **live experiment + endpoint + warehouse**, so they are wrapped
# MAGIC > in `try/except` with `[illustrative]` fallbacks — the notebook runs top-to-bottom without them. Steps 3–5 run for
# MAGIC > real against a **seeded** trace-text table, so the AI-Function enrichment and the dashboard dataset SQL genuinely execute.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 0. Install libraries and restart Python
# MAGIC `mlflow[databricks] >= 3.4` brings the MLflow 3 GenAI surface: `mlflow.search_traces`, `mlflow.genai.scorers`,
# MAGIC and the production-monitoring helpers. Pin the version so behavior is predictable across serverless and classic compute.

# COMMAND ----------

# MAGIC %pip install -U "mlflow[databricks]>=3.4"
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Set variables
# MAGIC One place for every name the notebook uses. Fill in `EXPERIMENT_ID` and `SQL_WAREHOUSE_ID` with your own — the
# MAGIC rest follow the course conventions (`unity_airways.rag`, endpoint `ua-support-agent`).

# COMMAND ----------

CATALOG    = "unity_airways"
SCHEMA     = "rag"

# The MLflow experiment your endpoint logs traces to (13.3). Read it from the Experiments UI, or resolve a name:
#   mlflow.get_experiment_by_name("/Shared/ua-support-agent").experiment_id
EXPERIMENT_ID   = "0000000000000000"          # <-- REPLACE with your experiment id (a string of digits)
EXPERIMENT_NAME = "/Shared/ua-support-agent"  # used only to set the active experiment for scorer monitors

# The SQL warehouse that (a) runs the scorer-monitor job in Step 2 and (b) runs the AI Functions in Steps 3-5.
SQL_WAREHOUSE_ID = "abcd1234efgh5678"          # <-- REPLACE with your SQL warehouse id

FRIENDLY_ENDPOINT = "ua-support-agent"                 # the deployed agent (Module 11)
JUDGE             = "databricks:/databricks-gpt-oss-120b"   # the LLM that backs the scorer judges; confirm on the supported-models page

# The flat, one-row-per-request contract the dashboard reads. Everything upstream feeds this.
METRICS_TABLE   = f"{CATALOG}.{SCHEMA}.ua_request_metrics"   # unity_airways.rag.ua_request_metrics
TRACE_TEXT_SEED = f"{CATALOG}.{SCHEMA}.ua_trace_text"        # small seeded trace-text table so Steps 3-5 run standalone

import mlflow
print("mlflow version    :", mlflow.__version__)
print("Metrics table     :", METRICS_TABLE)
print("Experiment id     :", EXPERIMENT_ID, "(replace with your own)")
print("SQL warehouse id  :", SQL_WAREHOUSE_ID, "(replace with your own)")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 1 — Read the trace data into a DataFrame · [Hands-on]
# MAGIC `mlflow.search_traces` pulls production traces into a **pandas DataFrame** you can inspect, transform, and write to
# MAGIC Delta. Structured metrics come for free off each trace: **latency** (`trace.info.execution_time_ms`) and **token
# MAGIC counts** (from the LLM span's token-usage attribute).
# MAGIC
# MAGIC > ⚠️ **GOTCHA — the argument is `experiment_ids=` (a list).** There is **no `experiment_names=`** argument on
# MAGIC > `search_traces`; passing it raises a `TypeError`. If you only know the name, resolve it first:
# MAGIC > `mlflow.get_experiment_by_name("/Shared/...").experiment_id`.
# MAGIC >
# MAGIC > ⚠️ **GOTCHA — the `filter_string` grammar is strict.** Prefix fields (`attributes.status`,
# MAGIC > `attributes.timestamp_ms`), use **single quotes** for values, backtick dotted tag names
# MAGIC > (`` tags.`mlflow.traceName` ``), and use `AND` — **`OR` is not supported.** Time is epoch milliseconds.

# COMMAND ----------

import mlflow

try:
    traces_df = mlflow.search_traces(
        experiment_ids=[EXPERIMENT_ID],              # a LIST of experiment IDs — never experiment_names=
        filter_string="attributes.status = 'OK'",    # note the attributes. prefix + single quotes
        order_by=["attributes.timestamp_ms DESC"],   # newest first
        max_results=5000,                            # cap the pull; page for more if needed
    )
    print(len(traces_df), "traces")
    # Typical columns: request, response, trace_id, execution_time_ms, tokens, assessments, request_time, ...
    print(traces_df.columns.tolist())
    display(traces_df.head(10))
except Exception as e:
    # No live experiment yet (or the id above is still the placeholder). Fall back to an illustrative, empty DataFrame
    # with the columns the rest of Step 1 expects, so the notebook keeps running end-to-end.
    import pandas as pd
    print("[illustrative] search_traces needs a live experiment with traces. Reason:", repr(e))
    traces_df = pd.DataFrame(
        columns=["trace_id", "request", "response", "execution_time_ms", "request_time", "tokens", "assessments"]
    )

# COMMAND ----------

# MAGIC %md
# MAGIC ### Pull latency and token counts off each trace object
# MAGIC The DataFrame carries an `execution_time_ms` column, and each row also exposes the underlying **Trace object** (the
# MAGIC `trace` column) so you can read `trace.info.execution_time_ms` and token usage directly.
# MAGIC
# MAGIC > ⚠️ **GOTCHA — token-usage key:** MLflow exposes per-trace usage via a **`token_usage` / `tokenUsage`** attribute
# MAGIC > (on `trace.info` and/or the LLM span), **not** a fixed `mlflow.chat_model.*` key. **Confirm the exact key in your
# MAGIC > own traces** — it varies by autolog integration and mlflow version.

# COMMAND ----------

def latency_and_tokens(trace):
    """Best-effort read of latency + total tokens from a Trace object. Guarded because the exact
    token-usage key varies by integration / mlflow version — confirm against your own traces."""
    latency_ms = getattr(trace.info, "execution_time_ms", None)
    total_tokens = None
    try:
        # MLflow surfaces aggregated usage on trace.info.token_usage on recent versions.
        usage = getattr(trace.info, "token_usage", None) or {}
        # Keys seen in the wild: "total_tokens" / "input_tokens" / "output_tokens" (confirm yours).
        total_tokens = usage.get("total_tokens")
    except Exception:
        pass
    return latency_ms, total_tokens

try:
    if len(traces_df) and "trace" in traces_df.columns:
        sample = traces_df.iloc[0]["trace"]
        lat, tok = latency_and_tokens(sample)
        print(f"[live] first trace  latency_ms={lat}  total_tokens={tok}")
    else:
        print("[illustrative] No live traces to read latency/tokens from — see the seeded table in Step 3.")
except Exception as e:
    print("[illustrative] Could not read latency/tokens off the trace object. Reason:", repr(e))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 2 — Turn quality into columns with scorers running as monitors · [Hands-on] · **Beta**
# MAGIC Latency and tokens are structured. **Quality is not** — "was this answer safe, relevant, grounded?" lives inside
# MAGIC free text. So you let the **same MLflow scorers you used offline in Module 08** run continuously over production
# MAGIC traces. Register each one, start it, and a managed **Lakeflow Job** scores a **sampled** slice on a schedule and
# MAGIC writes the scores back onto the traces.
# MAGIC
# MAGIC > 📌 **IMPORTANT:** these are the **same scorer objects** as offline evaluation (Module 08), reused online. One
# MAGIC > metric definition measures quality in dev *and* prod, so version-over-version comparisons stay honest.
# MAGIC >
# MAGIC > ⚠️ **GOTCHA — Beta + version churn.** Production monitoring (scorers as monitors) is **Beta**. The
# MAGIC > `set_databricks_monitoring_sql_warehouse_id` keyword and the `.register()/.start()` surface can shift between
# MAGIC > mlflow versions — **confirm against your installed mlflow.** This cell uses **`sql_warehouse_id=`**; some
# MAGIC > mlflow builds name it **`warehouse_id=`**. It is wrapped in `try/except`, so a name mismatch fails soft.

# COMMAND ----------

import mlflow
from mlflow.genai.scorers import (
    Safety, RelevanceToQuery, RetrievalGroundedness, ScorerSamplingConfig,
)
from mlflow.tracing import set_databricks_monitoring_sql_warehouse_id

try:
    mlflow.set_experiment(EXPERIMENT_NAME)   # the production experiment the traces land in

    # 1) Point monitoring at a SQL warehouse that will run the scorer job.
    #    NOTE the kwarg name: sql_warehouse_id (NOT warehouse_id). Confirm against your installed mlflow.
    #    Only takes effect for experiments whose trace location is a UC schema.
    set_databricks_monitoring_sql_warehouse_id(
        sql_warehouse_id=SQL_WAREHOUSE_ID,   # <-- kwarg is sql_warehouse_id; some builds use warehouse_id
        experiment_id=EXPERIMENT_ID,         # optional; uses the active experiment if omitted
    )

    # 2) Register AND start each scorer. Registering alone does NOT activate monitoring — you need both calls.
    #    Sampling controls cost: score every trace for safety (1.0), sample the expensive judges lower.
    safety = Safety(model=JUDGE).register(name="prod_safety")
    safety = safety.start(sampling_config=ScorerSamplingConfig(sample_rate=1.0))   # every trace

    relevance = RelevanceToQuery(model=JUDGE).register(name="prod_relevance")
    relevance = relevance.start(sampling_config=ScorerSamplingConfig(sample_rate=0.5))

    grounded = RetrievalGroundedness(model=JUDGE).register(name="prod_groundedness")
    grounded = grounded.start(sampling_config=ScorerSamplingConfig(sample_rate=0.5))

    print("Started monitors: prod_safety (1.0), prod_relevance (0.5), prod_groundedness (0.5)")
    print("A managed Lakeflow Job was provisioned to run these — adjust its schedule in the Jobs UI.")
except Exception as e:
    print("[illustrative] Scorer monitors need a live experiment + SQL warehouse + monitoring (Beta). Reason:", repr(e))
    print("Both .register() AND .start() are required; sampling controls judge cost.")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Manage the monitors later
# MAGIC List what is running, fetch one, dial its sampling up or down, pause it, or remove it. Same objects, managed live.

# COMMAND ----------

from mlflow.genai.scorers import list_scorers, get_scorer, delete_scorer, ScorerSamplingConfig

try:
    # What is registered on the active experiment?
    for s in list_scorers():
        rate = s.sampling_config.sample_rate if getattr(s, "sampling_config", None) else "N/A"
        print(f"  {s.name}: sample_rate={rate}")

    # Fetch one and raise its sampling from 0.5 -> 0.8 (e.g. you want more groundedness coverage).
    g = get_scorer(name="prod_groundedness")
    g = g.update(sampling_config=ScorerSamplingConfig(sample_rate=0.8))

    # Pause monitoring but KEEP the registration (re-.start() later):
    #   g = g.stop()
    # Remove entirely:
    #   delete_scorer(name="prod_groundedness")
    print("Managed prod_groundedness -> sample_rate=0.8 (stop()/delete_scorer() shown, commented).")
except Exception as e:
    print("[illustrative] Managing scorers needs the monitors registered in Step 2. Reason:", repr(e))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 3 — Turn text into columns with AI Functions · [Hands-on]
# MAGIC Scorers cover quality. For **"what are people asking"** and **"how do they feel"**, run **AI Functions** over the
# MAGIC request/response text — plain SQL over the trace/inference Delta table. Prefer the **task-specific** functions:
# MAGIC `ai_classify` for fixed-label topic routing, `ai_analyze_sentiment` for sentiment, `ai_summarize` for a one-line
# MAGIC recap. Reach for `ai_query` only when you need custom structured JSON no task function produces.
# MAGIC
# MAGIC First, seed a small **trace-text table** so this step (and the dashboard) runs **standalone**, without a live agent.
# MAGIC In production you would instead read your real trace/inference table (the fully-qualified name depends on how you
# MAGIC configured payload logging in 11.3 / trace destination in 13.3).

# COMMAND ----------

# MAGIC %md
# MAGIC ### 3a. Seed a tiny trace-text table (idempotent)
# MAGIC `CREATE TABLE IF NOT EXISTS` + insert-only-when-empty means this never clobbers a real table. The columns mirror
# MAGIC what you would pull off traces (Step 1) joined to the scorer results (Step 2): structured fields + text +
# MAGIC placeholder quality scores. The AI Functions in 3b add `topic` / `sentiment` / `answer_summary` on top.

# COMMAND ----------

# MAGIC %sql
# MAGIC -- One row per request. request_time spans a few days so the time-series tiles have something to draw.
# MAGIC CREATE TABLE IF NOT EXISTS unity_airways.rag.ua_trace_text (
# MAGIC   trace_id       STRING,
# MAGIC   request_time   TIMESTAMP,
# MAGIC   user_question  STRING,
# MAGIC   agent_response STRING,
# MAGIC   latency_ms     BIGINT,
# MAGIC   input_tokens   BIGINT,
# MAGIC   output_tokens  BIGINT,
# MAGIC   total_tokens   BIGINT,
# MAGIC   status         STRING,
# MAGIC   relevance      DOUBLE,   -- from the RelevanceToQuery monitor (Step 2)
# MAGIC   safety         DOUBLE,   -- from the Safety monitor
# MAGIC   groundedness   DOUBLE,   -- from the RetrievalGroundedness monitor
# MAGIC   user_feedback  STRING    -- 👍/👎 from the Review App (13.3 / mlflow.log_feedback)
# MAGIC );

# COMMAND ----------

# MAGIC %sql
# MAGIC INSERT INTO unity_airways.rag.ua_trace_text
# MAGIC SELECT * FROM (VALUES
# MAGIC   ('tr-0001', TIMESTAMP'2026-07-06 09:12:00', 'How do I check in online for flight UA482?',                         'You can check in online from 24 hours before departure in the Manage Booking page. Per Unity Airways policy, have your booking reference ready.', 1820,  310, 120, 430, 'OK',    0.97, 0.99, 0.95, 'up'),
# MAGIC   ('tr-0002', TIMESTAMP'2026-07-06 11:40:00', 'My checked bag never arrived in Lisbon, what do I do?',              'I am sorry your bag is delayed. File a report at the Unity Airways baggage desk; per policy delayed bags are traced and delivered to your address.', 2510,  280, 140, 420, 'OK',    0.93, 0.99, 0.90, NULL),
# MAGIC   ('tr-0003', TIMESTAMP'2026-07-07 08:05:00', 'I want to cancel my booking ABC123 and get a refund',                'Basic Economy fares are non-refundable under Unity Airways policy; Flex fares can be cancelled for a full refund within the fare window.',           1990,  305, 150, 455, 'OK',    0.88, 0.98, 0.86, 'down'),
# MAGIC   ('tr-0004', TIMESTAMP'2026-07-07 14:22:00', 'How much does an extra checked bag cost transatlantic?',             'A second checked bag on transatlantic routes is charged per the current Unity Airways baggage fee table shown at booking.',                          1750,  260, 110, 370, 'OK',    0.95, 0.99, 0.94, 'up'),
# MAGIC   ('tr-0005', TIMESTAMP'2026-07-08 10:31:00', 'Can I upgrade my seat to business using loyalty points?',            'Seat upgrades with loyalty points depend on availability and your tier; check the Loyalty page for the points needed on this route.',              2120,  290, 130, 420, 'OK',    0.91, 0.99, 0.88, NULL),
# MAGIC   ('tr-0006', TIMESTAMP'2026-07-08 16:47:00', 'The app keeps crashing on the payment screen at check-in',           'Sorry about that. Try updating the app and clearing its cache; if payment still fails, check in at the airport kiosk per Unity Airways policy.',    3010,  330, 160, 490, 'OK',    0.84, 0.98, 0.80, 'down'),
# MAGIC   ('tr-0007', TIMESTAMP'2026-07-09 09:58:00', 'I was double-charged for seat selection on booking XYZ789',          'I understand the concern. Duplicate seat-selection charges are refunded once verified; our team will review booking XYZ789 under refund policy.',   2280,  300, 145, 445, 'OK',    0.90, 0.99, 0.87, 'down'),
# MAGIC   ('tr-0008', TIMESTAMP'2026-07-09 12:15:00', 'What is the refund window for a Flex fare?',                         'Flex fares can be cancelled for a full refund up to the departure time under Unity Airways policy; taxes are always refunded.',                       1680,  255, 115, 370, 'OK',    0.96, 0.99, 0.93, 'up'),
# MAGIC   ('tr-0009', TIMESTAMP'2026-07-10 08:44:00', 'Do you offer a pet-in-cabin option and how do I add it?',            'Small pets in an approved carrier may travel in cabin on most routes; add the pet option in Manage Booking, subject to Unity Airways policy limits.', 2350,  285, 135, 420, 'OK',    0.92, 0.99, 0.89, NULL),
# MAGIC   ('tr-0010', TIMESTAMP'2026-07-10 15:03:00', 'My flight was cancelled and I have not been rebooked yet',           'I am sorry for the disruption. Cancelled-flight passengers are rebooked on the next available Unity Airways service or refunded per policy.',          2740,  315, 155, 470, 'OK',    0.89, 0.99, 0.85, 'down')
# MAGIC ) AS v(trace_id, request_time, user_question, agent_response, latency_ms, input_tokens, output_tokens, total_tokens, status, relevance, safety, groundedness, user_feedback)
# MAGIC WHERE (SELECT count(*) FROM unity_airways.rag.ua_trace_text) = 0;

# COMMAND ----------

# MAGIC %md
# MAGIC ### 3b. Enrich the text and land the per-request metrics table
# MAGIC One pass of AI Functions adds the text-derived columns, and we write the whole flat row to
# MAGIC **`unity_airways.rag.ua_request_metrics`** — the stable contract the dashboard reads (one row per request, every
# MAGIC metric a column).
# MAGIC
# MAGIC - **`ai_classify`** with an explicit label list is the right tool for intent/topic — keep the list short and add
# MAGIC   **"Other"** on purpose: a rising "Other" bucket is your topic-drift signal (feeds the alert in 13.6).
# MAGIC - **`ai_analyze_sentiment`** returns `positive | neutral | negative | mixed` (and NULL) for the traveler's question.
# MAGIC - **`ai_summarize(text, N)`** gives a short recap for the detail table.

# COMMAND ----------

# MAGIC %sql
# MAGIC -- Build the flat per-request metrics table. Structured + scorer columns pass straight through;
# MAGIC -- the three AI Functions add topic / sentiment / answer_summary. Filter NULL text (NULL in => NULL out).
# MAGIC CREATE OR REPLACE TABLE unity_airways.rag.ua_request_metrics AS
# MAGIC SELECT
# MAGIC   trace_id                              AS request_id,
# MAGIC   request_time                          AS ts,
# MAGIC   user_question,
# MAGIC   agent_response,
# MAGIC   latency_ms,
# MAGIC   input_tokens,
# MAGIC   output_tokens,
# MAGIC   total_tokens,
# MAGIC   status,
# MAGIC   relevance,
# MAGIC   safety,
# MAGIC   groundedness,
# MAGIC   user_feedback,
# MAGIC   -- intent / topic routing: prefer ai_classify over ai_query for a fixed label set. "Other" catches drift.
# MAGIC   ai_classify(
# MAGIC     user_question,
# MAGIC     ARRAY('Check-in', 'Cancellation', 'Baggage', 'Refunds', 'Loyalty', 'Other')
# MAGIC   )                                     AS topic,
# MAGIC   -- sentiment of the traveler's question: positive | neutral | negative | mixed
# MAGIC   ai_analyze_sentiment(user_question)   AS sentiment,
# MAGIC   -- a one-line summary of the answer, for the detail table (second arg = max words)
# MAGIC   ai_summarize(agent_response, 20)      AS answer_summary
# MAGIC FROM unity_airways.rag.ua_trace_text
# MAGIC WHERE user_question IS NOT NULL;

# COMMAND ----------

# MAGIC %md
# MAGIC ### 3c. How to verify the enrichment worked
# MAGIC Every row should have a `topic` from the fixed label set, a `sentiment`, and a short `answer_summary`.

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT request_id, ts, topic, sentiment, latency_ms, total_tokens, relevance, groundedness, answer_summary
# MAGIC FROM   unity_airways.rag.ua_request_metrics
# MAGIC ORDER BY ts
# MAGIC LIMIT 20;

# COMMAND ----------

# MAGIC %md
# MAGIC ### 3d. (Optional) The `ai_query` + `responseFormat` alternative
# MAGIC 📘 B1 Ch9 classifies intent with **`ai_query`** plus a JSON-schema `responseFormat` that forces a `category` field.
# MAGIC It works, but the current best practice is the task-specific **`ai_classify`** above — it is simpler and less
# MAGIC error-prone for fixed labels. Keep `ai_query` for genuinely custom structured output. Shown here for completeness.

# COMMAND ----------

# MAGIC %sql
# MAGIC -- Equivalent intent classification via the general-purpose ai_query.
# MAGIC --   responseFormat => '{"type":"json_object"}' forces JSON output (DBR 15.4+); parse the .response with from_json.
# MAGIC --   failOnError => false isolates bad rows into .errorMessage instead of failing the whole query.
# MAGIC SELECT
# MAGIC   trace_id,
# MAGIC   ai_query(
# MAGIC     'databricks-claude-sonnet-4-5',                          -- confirm on the supported-models page
# MAGIC     CONCAT('Return JSON {"category": <one of Check-in, Cancellation, Baggage, Refunds, Loyalty, Other>} ',
# MAGIC            'for this airline support question: ', user_question),
# MAGIC     responseFormat => '{"type":"json_object"}',              -- documented form; NOT a STRUCT<...> DDL string
# MAGIC     failOnError    => false
# MAGIC   ) AS intent                                                -- STRUCT with .response (JSON string) and .errorMessage
# MAGIC FROM unity_airways.rag.ua_trace_text
# MAGIC WHERE user_question IS NOT NULL
# MAGIC LIMIT 5;

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 4 — The per-request metrics table is your contract
# MAGIC You just built **`unity_airways.rag.ua_request_metrics`** — one row per request, every metric a flat column. This
# MAGIC is the stable surface everything downstream reads: the dashboard (Step 5), the alerts (13.6), and the improve loop
# MAGIC (13.7). Keep it flat and push all business logic into the dataset SQL.
# MAGIC
# MAGIC | Column | Source | Used by tile |
# MAGIC |---|---|---|
# MAGIC | `request_id` | trace `trace_id` | join key, detail table |
# MAGIC | `ts` | trace `request_time` | every time series |
# MAGIC | `user_question`, `agent_response` | trace text | detail table |
# MAGIC | `latency_ms` | `execution_time_ms` | latency p50/p95 |
# MAGIC | `input_tokens`, `output_tokens`, `total_tokens` | span token-usage attribute | cost / volume |
# MAGIC | `status` | trace status | error rate |
# MAGIC | `topic` | `ai_classify` | top topics |
# MAGIC | `sentiment` | `ai_analyze_sentiment` | sentiment mix |
# MAGIC | `relevance`, `safety`, `groundedness` | scorer monitors (Step 2) | quality trend |
# MAGIC | `user_feedback` | `mlflow.log_feedback` (13.3) | satisfaction |
# MAGIC
# MAGIC > 💡 **TIP:** In production, refresh this table with a **MERGE on `request_id`** (incremental) instead of the
# MAGIC > `CREATE OR REPLACE` used here for the seed, and schedule it as a **Lakeflow Job** (same pattern as 11.11).

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 5 — Build the AI/BI dashboard (Lakeview) · [Hands-on] · UI + SQL
# MAGIC A dashboard is mostly **UI plus SQL**: the work lives in the dataset SQL behind each tile; the widgets are
# MAGIC deliberately dumb. There is **no dashboard-creation API to hand-write** here — you build tiles in the UI and let
# MAGIC the queries below do the work.
# MAGIC
# MAGIC **UI flow:**
# MAGIC 1. **New → Dashboard** (AI/BI). Name it, pick your SQL warehouse.
# MAGIC 2. **Data tab → add a dataset per domain.** One SQL query per dataset, always fully-qualified table names
# MAGIC    (`unity_airways.rag.ua_request_metrics`). Put the aggregation **in the query**.
# MAGIC 3. **Canvas tab → drop widgets** and bind each field to a dataset column. Counters for KPIs, line charts for
# MAGIC    trends, a bar for topics, a pie for sentiment, a table for detail.
# MAGIC 4. **Publish.** Published dashboards run on the warehouse and refresh on a schedule; viewers do not need edit rights.
# MAGIC
# MAGIC > 💡 **TIP — widget expressions are limited** (SUM, AVG, COUNT, DATE_TRUNC — **no `CAST`, no `percentile`**).
# MAGIC > Compute anything fancy (percentiles, CASE buckets, ratios) **in the dataset SELECT** and alias it, then point the
# MAGIC > widget at the alias.
# MAGIC >
# MAGIC > ⚠️ **GOTCHA — cardinality.** Keep a chart's color/group dimension to roughly **3–8 distinct values** or it turns
# MAGIC > to mush. That is exactly why `ai_classify` uses a short, fixed label list. High-cardinality columns (`request_id`)
# MAGIC > belong in a **table** widget, not a chart.
# MAGIC
# MAGIC The cells below are the **dataset queries** behind each tile. They run for real against the table you just built,
# MAGIC so you can preview every tile's numbers here before wiring the UI.

# COMMAND ----------

# MAGIC %md
# MAGIC ### Dataset: `daily_volume_latency` — volume + latency p50/p95 + error rate (line charts / counters)
# MAGIC `percentile_approx` is computed **in the dataset SQL** (a widget cannot do it) and aliased for the tile.

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT
# MAGIC   DATE(ts)                                              AS day,
# MAGIC   COUNT(*)                                              AS request_count,
# MAGIC   percentile_approx(latency_ms, 0.5)                    AS p50_latency_ms,
# MAGIC   percentile_approx(latency_ms, 0.95)                   AS p95_latency_ms,
# MAGIC   ROUND(AVG(CASE WHEN status = 'ERROR' THEN 1 ELSE 0 END), 4) AS error_rate
# MAGIC FROM unity_airways.rag.ua_request_metrics
# MAGIC WHERE ts >= date_sub(current_date(), 400)   -- wide window so the seeded sample always renders; tighten to 30 for real data
# MAGIC GROUP BY DATE(ts)
# MAGIC ORDER BY day;

# COMMAND ----------

# MAGIC %md
# MAGIC ### Dataset: `quality_trend` — average scorer scores by day (line chart)
# MAGIC A dip in `avg_groundedness` while `avg_safety` holds flat is the classic retrieval-regression signature.

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT
# MAGIC   DATE(ts)                     AS day,
# MAGIC   ROUND(AVG(relevance), 3)     AS avg_relevance,
# MAGIC   ROUND(AVG(safety), 3)        AS avg_safety,
# MAGIC   ROUND(AVG(groundedness), 3)  AS avg_groundedness
# MAGIC FROM unity_airways.rag.ua_request_metrics
# MAGIC GROUP BY DATE(ts)
# MAGIC ORDER BY day;

# COMMAND ----------

# MAGIC %md
# MAGIC ### Dataset: `top_topics` — request count by topic (bar chart)
# MAGIC Cardinality is capped by design (6 labels + Other), so the bar chart stays readable. Watch the **Other** slice.

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT topic, COUNT(*) AS n
# MAGIC FROM unity_airways.rag.ua_request_metrics
# MAGIC GROUP BY topic
# MAGIC ORDER BY n DESC;

# COMMAND ----------

# MAGIC %md
# MAGIC ### Dataset: `sentiment_mix` — request count by sentiment (pie / donut)

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT sentiment, COUNT(*) AS n
# MAGIC FROM unity_airways.rag.ua_request_metrics
# MAGIC GROUP BY sentiment
# MAGIC ORDER BY n DESC;

# COMMAND ----------

# MAGIC %md
# MAGIC ### Dataset: `request_detail` — the drill-down table
# MAGIC High-cardinality columns belong in a **table** widget (not a chart). This is where a stakeholder reads individual
# MAGIC requests — e.g. filter to `user_feedback = 'down'` to see what earned a thumbs-down.

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT ts, topic, sentiment, latency_ms, relevance, groundedness, user_feedback,
# MAGIC        user_question, answer_summary
# MAGIC FROM   unity_airways.rag.ua_request_metrics
# MAGIC ORDER BY ts DESC
# MAGIC LIMIT 200;

# COMMAND ----------

# MAGIC %md
# MAGIC ## Recap — you built the monitoring pipeline
# MAGIC - **Read the signal (Step 1):** `mlflow.search_traces(experiment_ids=[...])` into a pandas DataFrame; latency from
# MAGIC   `trace.info.execution_time_ms`, tokens from the span token-usage attribute.
# MAGIC - **Quality as columns (Step 2, Beta):** reused the Module 08 scorers (`Safety`, `RelevanceToQuery`,
# MAGIC   `RetrievalGroundedness`) as **production monitors** — `set_databricks_monitoring_sql_warehouse_id(...)` +
# MAGIC   `.register()` **and** `.start()` with `ScorerSamplingConfig(sample_rate=...)`.
# MAGIC - **Text as columns (Step 3):** `ai_classify` (topic) + `ai_analyze_sentiment` + `ai_summarize` over a seeded
# MAGIC   trace-text table.
# MAGIC - **The contract (Step 4):** one flat Delta table, `unity_airways.rag.ua_request_metrics`.
# MAGIC - **The dashboard (Step 5):** AI/BI (Lakeview) — dataset-per-tile SQL for volume, latency p50/p95, quality trend,
# MAGIC   top topics, sentiment mix, and a detail table; built in the UI.
# MAGIC
# MAGIC **Gotchas to remember**
# MAGIC - **`experiment_ids=` (a list), never `experiment_names=`** on `search_traces`.
# MAGIC - **Both `.register()` and `.start()`** — registering alone runs nothing. Sampling controls judge cost.
# MAGIC - **`percentile_approx` goes in the dataset SQL,** not a widget expression.
# MAGIC - **Keep chart dimensions to 3–8 values;** that is why `ai_classify` uses a short, fixed label list + "Other".
# MAGIC - **Production monitoring is Beta** and MLflow/SDK names churn — **confirm against your installed versions**
# MAGIC   (including whether the kwarg is `sql_warehouse_id=` or `warehouse_id=`).
# MAGIC
# MAGIC **Cross-references**
# MAGIC - **13.6 — Alerts and anomaly detection:** put a threshold alert on this metrics table (e.g. the "Other" topic
# MAGIC   share, or a `p95_latency_ms` spike).
# MAGIC - **13.7 — The improve loop:** feed failing/low-score traces from `mlflow.search_traces` into
# MAGIC   `mlflow.genai.datasets` to expand the evaluation set and drive the next Challenger.
# MAGIC - **Module 08 — Scorers and judges:** the *same* scorer objects, run offline; here they run online.
# MAGIC - **11.3 — AI Gateway payload logging → inference tables:** the raw signal this pipeline enriches.
# MAGIC
# MAGIC **Next roadmap topic:** **13.6 — Alerts and anomaly detection.**
