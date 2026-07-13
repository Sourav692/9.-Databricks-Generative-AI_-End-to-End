# Databricks notebook source
# MAGIC %md
# MAGIC # Module 16 lab — Cost, performance and scaling (the optimization playbook)
# MAGIC **Roadmap:** Level 7 · Module 16 (Cost, performance and scaling) · Topics 16.1–16.5 · [Hands-on]
# MAGIC
# MAGIC ## What this lab does
# MAGIC You already built and deployed the Unity Airways stack. This lab runs the **Module 16 optimization
# MAGIC playbook** on it — the same levers you would reach for when traffic triples and the bill doubles:
# MAGIC - **A. Batch inference with `ai_query()`** over a Delta table (16.3) — the engine for "no human is waiting."
# MAGIC - **B. High-throughput AI Search retrieval** (16.4) — a batch of queries against the RAG index, timed.
# MAGIC - **C. Latency / throughput profiling** (16.4) — timing cells that turn a stopwatch into rows/sec and
# MAGIC   queries/sec, plus a simple end-to-end breakdown.
# MAGIC - **D. A cost lens** (16.5) — endpoint types, provisioned throughput, and batch-vs-real-time trade-offs,
# MAGIC   with an illustrative token-cost estimator.
# MAGIC
# MAGIC > 📌 IMPORTANT: this lab **does not** re-teach serving (Module 11) or AI Search (Module 04). It profiles
# MAGIC > and tunes what those modules built. `ai_query()` itself is taught in **11.10** — here we use it as the
# MAGIC > batch engine and decide *when* it is the right one.
# MAGIC
# MAGIC ### Prerequisites (read before running)
# MAGIC - **Compute:** a **Pro or Serverless SQL warehouse** for the `ai_query` SQL cells, OR a cluster on
# MAGIC   **DBR 15.3+ ML** (the `failOnError => false` argument used in Section A needs **DBR 15.3+**, per 11.10).
# MAGIC   `ai_query` does not run on Classic/Starter SQL warehouses.
# MAGIC - **Unity Catalog:** write access to a catalog + schema. This lab uses `unity_airways.rag`.
# MAGIC - **Foundation Model access:** the workspace must have Foundation Model APIs / AI Functions enabled.
# MAGIC   Chat model `databricks-claude-sonnet-4-5`, embeddings `databricks-gte-large-en` (confirm names on the
# MAGIC   supported-models page — they churn).
# MAGIC - **Optional (cells are clearly marked and skippable):**
# MAGIC   - the deployed agent endpoint **`ua-support-agent`** (Module 09 / 11) for the real-time comparison,
# MAGIC   - the AI Search index **`unity_airways.rag.ua_rag_chunks_index`** (Module 04) for Section B.
# MAGIC - `%pip install databricks-vectorsearch` is only needed for the Python retrieval cell in Section B.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 0. Configuration
# MAGIC Fully-qualified names so the SQL cells run top-to-bottom on any warehouse. Change the catalog/schema
# MAGIC here if you own a different location.

# COMMAND ----------

CATALOG = "unity_airways"
SCHEMA  = "rag"

CHAT_ENDPOINT      = "databricks-claude-sonnet-4-5"   # Foundation Model (confirm on supported-models page)
EMBED_ENDPOINT     = "databricks-gte-large-en"        # embeddings FM
AGENT_ENDPOINT     = "ua-support-agent"               # deployed agent (Module 09/11) — optional
VS_INDEX           = f"{CATALOG}.{SCHEMA}.ua_rag_chunks_index"  # AI Search index (Module 04) — optional
TICKETS_TABLE      = f"{CATALOG}.{SCHEMA}.ua_support_tickets"   # seeded by 11.10 or below

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")
print("Config set. Catalog/schema:", CATALOG, SCHEMA)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Reuse (or seed) the Unity Airways ticket table
# MAGIC If you ran the **11.10** notebook, `ua_support_tickets` already exists. If not, we seed a compact set so
# MAGIC every cell runs end-to-end. This is our "large Delta table" stand-in for batch inference.

# COMMAND ----------

# Create the table if it does not exist, and seed it only when empty (idempotent, so re-runs are safe).
spark.sql(f"""
CREATE TABLE IF NOT EXISTS {TICKETS_TABLE} (
  ticket_id   BIGINT,
  received_at TIMESTAMP,
  channel     STRING,
  language    STRING,
  raw_text    STRING
)
""")

if spark.table(TICKETS_TABLE).count() == 0:
    spark.sql(f"""
    INSERT INTO {TICKETS_TABLE} VALUES
      (1001, TIMESTAMP'2026-07-10 08:14:00', 'email', 'en',
       'My checked bag never arrived in Seattle and no one at the desk could help.'),
      (1002, TIMESTAMP'2026-07-10 09:02:00', 'chat', 'en',
       'Flight UA455 out of SFO was delayed four hours and I missed my connection in Denver.'),
      (1003, TIMESTAMP'2026-07-10 10:47:00', 'email', 'en',
       'I was charged twice for seat selection on booking ABC123. Please refund the duplicate charge.'),
      (1004, TIMESTAMP'2026-07-10 11:20:00', 'app_review', 'en',
       'The crew were lovely and boarding was quick. Best service I have had in ages.'),
      (1005, TIMESTAMP'2026-07-10 12:05:00', 'call_transcript', 'en',
       'Caller reports their flight to Boston was cancelled overnight and wants hotel compensation.'),
      (1006, TIMESTAMP'2026-07-10 13:33:00', 'chat', 'en',
       'What is the check-in cutoff for a domestic morning flight?'),
      (1007, TIMESTAMP'2026-07-10 14:41:00', 'app_review', 'en',
       'Still no refund after three weeks and no reply to my emails. Very frustrating.'),
      (1008, TIMESTAMP'2026-07-10 15:58:00', 'app_review', 'en',
       'Boarding was chaos, the gate agent was rude, and no one explained the delay.')
    """)
    print("Seeded ua_support_tickets.")
else:
    print("ua_support_tickets already populated — reusing it.")

display(spark.sql(f"SELECT ticket_id, channel, left(raw_text, 55) AS preview FROM {TICKETS_TABLE} ORDER BY ticket_id"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## A. Batch inference with `ai_query()` (16.3)
# MAGIC **The first question is always "is a human waiting?"** For scoring a whole table nightly, the answer is
# MAGIC no — so this is a batch `ai_query()` job on SQL compute, not endpoint traffic.
# MAGIC
# MAGIC A workload suits `ai_query()` when: (1) it is a **large table**, (2) **no synchronous interaction** is
# MAGIC needed, and (3) it has a **consistent schema**. Ticket enrichment fits all three.
# MAGIC
# MAGIC > 💡 TIP: develop on a `LIMIT` sample first to confirm shape and cost, then remove the limit.

# COMMAND ----------

# MAGIC %sql
# MAGIC -- Sample first (16.5 cost discipline): confirm the output shape on 3 rows before the full table.
# MAGIC -- failOnError => false is the batch-safety switch: one bad row must not fail the whole job.
# MAGIC SELECT
# MAGIC   ticket_id,
# MAGIC   ai_query(
# MAGIC     'databricks-claude-sonnet-4-5',
# MAGIC     CONCAT('Classify this airline ticket as baggage, delay, billing, or other. Text: ', raw_text),
# MAGIC     failOnError => false
# MAGIC   ).response AS intent_sample
# MAGIC FROM unity_airways.rag.ua_support_tickets
# MAGIC WHERE raw_text IS NOT NULL
# MAGIC LIMIT 3

# COMMAND ----------

# MAGIC %md
# MAGIC Now the full batch pass, written back to a Delta table. In production this is scheduled by a Lakeflow
# MAGIC Job (11.11) and runs on SQL compute — it never touches the real-time endpoint. The task-specific
# MAGIC functions (`ai_classify`, `ai_analyze_sentiment`) are cheaper and more accurate than a raw `ai_query`
# MAGIC prompt when the task fits (see 11.10).

# COMMAND ----------

# MAGIC %sql
# MAGIC CREATE OR REPLACE TABLE unity_airways.rag.ua_tickets_enriched_16 AS
# MAGIC SELECT
# MAGIC   ticket_id,
# MAGIC   channel,
# MAGIC   ai_classify(
# MAGIC     raw_text,
# MAGIC     ARRAY('baggage', 'delay', 'billing', 'praise', 'other')
# MAGIC   )                              AS intent,
# MAGIC   ai_analyze_sentiment(raw_text) AS sentiment
# MAGIC FROM unity_airways.rag.ua_support_tickets
# MAGIC WHERE raw_text IS NOT NULL   -- NULL in => NULL out; filter to skip wasted (billable) calls

# COMMAND ----------

# MAGIC %sql
# MAGIC -- How to verify it worked: sensible buckets and a sentiment spread.
# MAGIC SELECT intent, sentiment, count(*) AS n
# MAGIC FROM unity_airways.rag.ua_tickets_enriched_16
# MAGIC GROUP BY 1, 2
# MAGIC ORDER BY n DESC

# COMMAND ----------

# MAGIC %md
# MAGIC ### Point `ai_query` at the deployed agent (optional)
# MAGIC Same function, custom endpoint. This calls the Unity Airways `ResponsesAgent` (`ua-support-agent`) in
# MAGIC batch to draft a reply per ticket. Skip if you have not deployed the agent.
# MAGIC
# MAGIC > 📌 IMPORTANT: `ai_query` has **no conversational state, tool-calling, or multi-turn** — it is batch
# MAGIC > inference on a table. When you need the agent's tools, you call the agent endpoint *from* `ai_query`,
# MAGIC > exactly like this.

# COMMAND ----------

try:
    df = spark.sql(f"""
      SELECT
        ticket_id,
        ai_query(
          '{AGENT_ENDPOINT}',
          CONCAT('Draft a short, empathetic reply to this customer: ', raw_text),
          failOnError => false
        ).response AS draft_reply
      FROM {TICKETS_TABLE}
      WHERE raw_text IS NOT NULL
      LIMIT 3
    """)
    display(df)
except Exception as e:
    print(f"Skipped agent batch call (endpoint '{AGENT_ENDPOINT}' not available?): {type(e).__name__}: {e}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## B. High-throughput AI Search retrieval (16.4)
# MAGIC Retrieval scales **independently** of the LLM (16.1). Here we fire a batch of queries at the RAG index
# MAGIC and measure how it holds up — the retrieval half of a load test. Skip if you have not built the index
# MAGIC (Module 04).
# MAGIC
# MAGIC > AI Search endpoints come in **Standard** and **Storage-optimized** (large vector counts, faster
# MAGIC > indexing); **hybrid search** (keyword + vector) trades a little latency for recall. Those are the
# MAGIC > retrieval-layer cost/perf levers.

# COMMAND ----------

# MAGIC %pip install -q databricks-vectorsearch
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

import time
CATALOG, SCHEMA = "unity_airways", "rag"
VS_INDEX = f"{CATALOG}.{SCHEMA}.ua_rag_chunks_index"

# A batch of realistic passenger queries to drive throughput.
QUERIES = [
    "What is the checked baggage allowance?",
    "How late can I check in for a domestic flight?",
    "What is the refund policy for a cancelled flight?",
    "Can I change my seat after booking?",
    "What compensation applies to an overnight cancellation?",
    "How do I report a lost bag?",
    "Are pets allowed in the cabin?",
    "What is the policy for a missed connection?",
]

try:
    from databricks.vector_search.client import VectorSearchClient
    vsc = VectorSearchClient(disable_notice=True)
    index = vsc.get_index(index_name=VS_INDEX)

    latencies = []
    t0 = time.perf_counter()
    for q in QUERIES:
        s = time.perf_counter()
        _ = index.similarity_search(
            query_text=q,
            columns=["id", "content"],   # adjust to your index's columns
            num_results=3,
        )
        latencies.append(time.perf_counter() - s)
    wall = time.perf_counter() - t0

    n = len(QUERIES)
    print(f"AI Search retrieval — {n} queries")
    print(f"  wall time      : {wall:.2f}s")
    print(f"  throughput     : {n / wall:.1f} queries/sec (sequential)")
    print(f"  mean latency   : {1000 * sum(latencies) / n:.0f} ms")
    print(f"  p95 latency    : {1000 * sorted(latencies)[int(0.95 * (n - 1))]:.0f} ms")
    print("  Note: sequential loop. Real high-throughput retrieval fans these out concurrently.")
except Exception as e:
    print(f"Skipped AI Search retrieval (index '{VS_INDEX}' not available?): {type(e).__name__}: {e}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Retrieval from SQL, in one batch pass
# MAGIC `vector_search()` runs retrieval next to your data — one row per ticket, top-k policy chunks each. This
# MAGIC is the batch-retrieval form (contrast with the per-query Python client above). Skip if no index.

# COMMAND ----------

try:
    df = spark.sql(f"""
      SELECT
        t.ticket_id,
        vector_search(
          index       => '{VS_INDEX}',
          query_text  => t.raw_text,
          num_results => 3
        ) AS top_policy_chunks
      FROM {TICKETS_TABLE} t
      WHERE t.raw_text IS NOT NULL
      LIMIT 3
    """)
    display(df)
except Exception as e:
    print(f"Skipped SQL vector_search (index '{VS_INDEX}' not available?): {type(e).__name__}: {e}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## C. Latency / throughput profiling (16.4)
# MAGIC **Always profile before you scale.** A stopwatch on one request tells you almost nothing; splitting the
# MAGIC time and computing rates tells you which lever to move.
# MAGIC
# MAGIC First, the batch path: time an `ai_query` pass over the table and convert wall time into **rows/sec** —
# MAGIC the metric that actually matters for batch (per-row latency does not).

# COMMAND ----------

import time

# Time a full ai_query classification pass over the table (batch throughput, not per-row latency).
t0 = time.perf_counter()
scored = spark.sql(f"""
  SELECT ticket_id,
         ai_query('{CHAT_ENDPOINT}',
                  CONCAT('One word intent for: ', raw_text),
                  failOnError => false).response AS intent
  FROM {TICKETS_TABLE}
  WHERE raw_text IS NOT NULL
""")
row_count = scored.count()   # forces execution
batch_wall = time.perf_counter() - t0

print(f"Batch ai_query — {row_count} rows in {batch_wall:.2f}s")
print(f"  throughput: {row_count / batch_wall:.1f} rows/sec")
print("  Batch cares about rows/sec, not per-row ms. Scale by adding SQL compute, not endpoint replicas.")

# COMMAND ----------

# MAGIC %md
# MAGIC Now the real-time path (optional): time a single call to the deployed agent endpoint. This is the metric
# MAGIC that matters when a **human is waiting** — p50/p95 latency, not throughput. Skip if no agent endpoint.

# COMMAND ----------

import time
try:
    from databricks.sdk import WorkspaceClient
    w = WorkspaceClient()

    prompt = "My flight is at 4pm — what is the check-in cutoff?"
    samples = 3
    lat = []
    # ResponsesAgent speaks the Responses schema — call it through the OpenAI-compatible
    # client the serving endpoint exposes (an "input" array, not "messages").
    client = w.serving_endpoints.get_open_ai_client()
    for _ in range(samples):
        s = time.perf_counter()
        _ = client.responses.create(
            model=AGENT_ENDPOINT,
            input=[{"role": "user", "content": prompt}],
        )
        lat.append(time.perf_counter() - s)

    print(f"Real-time agent endpoint — {samples} calls")
    print(f"  mean latency: {1000 * sum(lat) / len(lat):.0f} ms")
    print(f"  max  latency: {1000 * max(lat):.0f} ms")
    print("  Real-time cares about p50/p95 latency. If cold-start dominates, turn OFF scale_to_zero (16.5).")
except Exception as e:
    print(f"Skipped real-time call (endpoint '{AGENT_ENDPOINT}' not available, or query signature differs): "
          f"{type(e).__name__}: {e}")
    print("  If the query signature differs in your SDK version, call the REST /invocations path instead (see 11.1).")

# COMMAND ----------

# MAGIC %md
# MAGIC ### A simple end-to-end breakdown
# MAGIC Profiling means splitting total time into **vector-search / model-execution / queue-wait / orchestration**
# MAGIC so you fix the true bottleneck. Below is an illustrative breakdown you would populate from real timings
# MAGIC (retrieval from Section B, generation from the endpoint) — the shape of a profiling dashboard.

# COMMAND ----------

import pandas as pd

# Illustrative numbers — replace with the timings you measured above / read from the inference table (13).
profile = pd.DataFrame([
    {"stage": "Vector search (retrieval)", "ms": 120, "bottleneck_if": "index saturation / big embeddings"},
    {"stage": "Orchestration (agent, CPU)", "ms": 40,  "bottleneck_if": "slow routing / middleware"},
    {"stage": "Queue wait (batching)",     "ms": 60,  "bottleneck_if": "batch timeout too long"},
    {"stage": "Model execution (LLM, GPU)", "ms": 900, "bottleneck_if": "context too long / model too big"},
])
profile["pct"] = (100 * profile["ms"] / profile["ms"].sum()).round(1)
print("End-to-end latency breakdown (illustrative):")
print(profile.to_string(index=False))

top = profile.sort_values("ms", ascending=False).iloc[0]
print(f"\nBottleneck: '{top['stage']}' at {top['pct']}% of total.")
print("Fix (Table 9-11): model-execution dominates -> trim context + top-k (16.2), consider provisioned throughput (16.6).")
print("Do NOT add agent-endpoint replicas — that layer is only 4% of the time here.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## D. The cost lens (16.5)
# MAGIC The two questions every customer asks: *make it faster* and *keep the cost sane*. Cost tuning is the same
# MAGIC "is a human waiting?" decision, plus a few Databricks features.

# COMMAND ----------

import pandas as pd

cost_lens = pd.DataFrame([
    {"choice": "Batch ai_query() (SQL)",          "billing": "SQL compute time",          "use_when": "Bulk, scheduled, no human waiting (16.3)"},
    {"choice": "Real-time serving, pay-per-token", "billing": "Per input+output token",     "use_when": "Interactive, bursty / low volume"},
    {"choice": "Real-time, provisioned throughput","billing": "Reserved tokens/sec (compute)","use_when": "Steady high load, SLA latency, custom weights (16.6)"},
    {"choice": "scale_to_zero endpoint",           "billing": "Zero when idle + cold start", "use_when": "Dev / spiky traffic (not latency-critical)"},
    {"choice": "External model endpoint",          "billing": "Provider price + govern",     "use_when": "Mandated OpenAI/Anthropic, centralize keys+spend"},
])
print(cost_lens.to_string(index=False))

# COMMAND ----------

# MAGIC %md
# MAGIC ### An illustrative token-cost estimator
# MAGIC Foundation Models bill **per token** (input + output), so cost scales with prompt length, retrieved
# MAGIC context, and response length. The function below is **illustrative only** — plug in the real per-token
# MAGIC price from your workspace's pricing page; do not treat the constant as accurate.
# MAGIC
# MAGIC > ⚠️ GOTCHA: this shows exactly why 16.2 matters — stuffing 15 retrieved chunks into a 32k context is a
# MAGIC > cost multiplier on **every** call. Trim context and top-k and the whole bill drops.

# COMMAND ----------

def est_token_cost(rows, avg_input_tokens, avg_output_tokens,
                   price_per_1k_input=0.003, price_per_1k_output=0.015):
    """Illustrative only. Replace the price constants with your workspace's real per-token rates."""
    in_cost  = rows * avg_input_tokens  / 1000 * price_per_1k_input
    out_cost = rows * avg_output_tokens / 1000 * price_per_1k_output
    return round(in_cost + out_cost, 2)

ROWS = 2_000_000   # a night's worth of tickets

fat = est_token_cost(ROWS, avg_input_tokens=4000, avg_output_tokens=300)   # 15 chunks, 32k context habit
lean = est_token_cost(ROWS, avg_input_tokens=800,  avg_output_tokens=150)  # top-5 chunks, trimmed context

print(f"Illustrative batch cost over {ROWS:,} rows:")
print(f"  Fat prompt  (4000 in / 300 out): ${fat:,.2f}")
print(f"  Lean prompt (800 in / 150 out) : ${lean:,.2f}")
print(f"  Saving from context/top-k trim : ${fat - lean:,.2f}  ({100 * (fat - lean) / fat:.0f}% lower)")
print("\nNumbers are illustrative. The point: context length and top-k are cost levers on every single call.")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Capping spend with AI Gateway (where it must live)
# MAGIC AI Gateway gives usage tracking, rate limits, provider fallbacks, and budgets. But it matters *which*
# MAGIC endpoint you attach it to.
# MAGIC
# MAGIC > 📌 IMPORTANT: AI Gateway on an **agent** serving endpoint (like `ua-support-agent`) supports
# MAGIC > **inference tables only**. Rate limits, guardrails, and budgets require a **Foundation-Model or
# MAGIC > external-model endpoint**. To cap the agent's spend, put the limit/budget on the **Foundation Model
# MAGIC > endpoint the agent calls**, not on the agent endpoint. (Carried from Modules 11/12.)
# MAGIC
# MAGIC Read real spend from **usage system tables** and **inference tables** (Module 13), then size limits from
# MAGIC data — not a guess.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Recap, gotchas, and next steps
# MAGIC **What you ran**
# MAGIC - **A.** Batch `ai_query()` enrichment over `ua_support_tickets` → `ua_tickets_enriched_16` (16.3).
# MAGIC - **B.** A high-throughput AI Search retrieval pass, Python client + SQL `vector_search` (16.4).
# MAGIC - **C.** Profiling: batch rows/sec, real-time latency, and an end-to-end breakdown that names the
# MAGIC   bottleneck (16.4).
# MAGIC - **D.** A cost lens: endpoint/billing comparison, an illustrative token estimator, and where AI Gateway
# MAGIC   budgets must live (16.5).
# MAGIC
# MAGIC **Gotchas to remember**
# MAGIC - **Profile before scaling.** The bottleneck is usually context length or retrieval, not replica count.
# MAGIC - **"Is a human waiting?"** routes the workload: no → batch `ai_query()`; yes → Model Serving.
# MAGIC - Set `failOnError => false` and filter `WHERE ... IS NOT NULL` on every batch `ai_query`.
# MAGIC - Changing embedding dimension forces a **re-embed + index rebuild** — not a live flag (16.2).
# MAGIC - AI Gateway rate limits/budgets go on the **Foundation Model endpoint**, not the agent endpoint (16.5).
# MAGIC - Provisioned throughput = dedicated capacity for steady load / custom weights (16.6). Fine-tuning is now
# MAGIC   part of **Databricks Model Training** and is **beyond the exam blueprint**.
# MAGIC - Served-model names churn — confirm `databricks-claude-sonnet-4-5` / `databricks-gte-large-en` on the
# MAGIC   supported-models page.
# MAGIC
# MAGIC **Cleanup (optional)**
# MAGIC ```
# MAGIC spark.sql("DROP TABLE IF EXISTS unity_airways.rag.ua_tickets_enriched_16")
# MAGIC # keep ua_support_tickets; other modules reuse it
# MAGIC ```
# MAGIC
# MAGIC **Next roadmap module**
# MAGIC - **Module 17 — Reference architectures and unifying GenAI systems:** the 5-phase lifecycle as an
# MAGIC   architecture, MLflow Traces + OpenTelemetry as the integration fabric, the MLflow Agent Server, MCP,
# MAGIC   and the end-to-end enterprise reference architecture (Capstone C4).
