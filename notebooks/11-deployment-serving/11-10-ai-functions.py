# Databricks notebook source
# MAGIC %md
# MAGIC # 11.10 — AI Functions for GenAI at scale
# MAGIC **Roadmap:** Module 11 (Deployment and serving) · Topic 11.10 (★ cornerstone) · [Theory + Hands-on]
# MAGIC
# MAGIC ## The problem
# MAGIC Unity Airways collects tens of thousands of support tickets, app-store reviews, and call transcripts
# MAGIC every week. They all land in one Delta table. The ops team wants each ticket **routed** (baggage vs
# MAGIC delay vs billing), **scored for sentiment**, **stripped of PII** before analysts see it, and
# MAGIC **summarized** into one line for the daily queue. Nobody is waiting on the answer — this is a nightly
# MAGIC batch job, not a chatbot. Looping row-by-row through a serving endpoint in Python means you own
# MAGIC batching, retries, checkpointing, and a long-running notebook. That is real infra work for what should
# MAGIC be a `SELECT`.
# MAGIC
# MAGIC ## What you will build
# MAGIC The batch pattern that repeats for every AI Function: **Delta table in → AI Function in the `SELECT` →
# MAGIC Delta table out**, ready to be scheduled by a Lakeflow Job (11.11).
# MAGIC - A seed table `unity_airways.rag.ua_support_tickets` so every cell runs end-to-end.
# MAGIC - `ai_query` as the general workhorse: structured JSON output, batch-safe error handling, and pointing
# MAGIC   it at a custom agent endpoint.
# MAGIC - The task-specific one-liners: `ai_classify`, `ai_analyze_sentiment`, `ai_extract`, `ai_summarize`,
# MAGIC   `ai_mask`, `ai_translate`, `ai_fix_grammar`, `ai_gen`, plus `vector_search` from SQL.
# MAGIC - A single enrichment pass written back to `unity_airways.rag.ua_tickets_enriched` (the table the
# MAGIC   scheduled job in 11.11 re-runs).
# MAGIC
# MAGIC ### Prerequisites (read before running)
# MAGIC - **Compute:** a **Pro or Serverless SQL warehouse**, OR a cluster on **DBR 15.1+**. AI Functions do
# MAGIC   **not** run on Classic/Starter SQL warehouses.
# MAGIC - **Per-argument runtime gates** (confirm for your workspace — minimums have been rising):
# MAGIC   - `responseFormat` needs **DBR 15.4+**
# MAGIC   - `returnType` needs **DBR 15.2+**
# MAGIC   - `failOnError` / `modelParameters` need **DBR 15.3+**
# MAGIC   - `ai_parse_document` needs **DBR 17.3+** (data prep — see Module 03)
# MAGIC   - `ai_forecast` needs a **Pro/Serverless** warehouse
# MAGIC - **Unity Catalog:** write access to a catalog + schema. This notebook uses `unity_airways.rag`.
# MAGIC - **Entitlement:** AI Functions call Databricks-hosted Foundation Models; the workspace must have
# MAGIC   Foundation Model / AI Functions access enabled. Costs land under the `AI_FUNCTIONS` product.
# MAGIC - **Optional endpoints:** a served model endpoint `ua-support-agent` (the agent deployed in 11.1 /
# MAGIC   Module 09) and an AI Search index `unity_airways.rag.ua_rag_chunks_index` (Module 04). The cells that
# MAGIC   use those are clearly marked and can be skipped if you have not built them yet.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 0. Configuration
# MAGIC The SQL cells below use **fully-qualified names** (`unity_airways.rag.<table>`) so they run top-to-bottom
# MAGIC on any warehouse without depending on a session default. Change the catalog/schema here if you own a
# MAGIC different location, then find-and-replace `unity_airways.rag` throughout.

# COMMAND ----------

# MAGIC %sql
# MAGIC CREATE SCHEMA IF NOT EXISTS unity_airways.rag

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Seed a raw feedback table
# MAGIC One Delta table of raw Unity Airways feedback — support tickets, app reviews, and call transcripts.
# MAGIC The `raw_text` column holds the customer's message and **may contain PII**. In production this table is
# MAGIC fed by Auto Loader / Lakeflow Connect; here we insert a handful of realistic rows so every later cell
# MAGIC has something to chew on.

# COMMAND ----------

# MAGIC %sql
# MAGIC CREATE OR REPLACE TABLE unity_airways.rag.ua_support_tickets (
# MAGIC   ticket_id     BIGINT,
# MAGIC   received_at   TIMESTAMP,
# MAGIC   channel       STRING,   -- 'email' | 'chat' | 'app_review' | 'call_transcript'
# MAGIC   language      STRING,   -- ISO code, e.g. 'en','es','fr'
# MAGIC   raw_text      STRING    -- the customer's message / review body (may contain PII)
# MAGIC )

# COMMAND ----------

# MAGIC %sql
# MAGIC -- A varied sample: different intents, channels, languages, and sentiment.
# MAGIC -- Row 1 carries PII (name, email, phone) so ai_mask has something to redact.
# MAGIC -- Row 6 is Spanish (for ai_translate); row 7 has messy grammar (for ai_fix_grammar).
# MAGIC INSERT INTO unity_airways.rag.ua_support_tickets VALUES
# MAGIC   (1001, TIMESTAMP'2026-07-10 08:14:00', 'email',           'en',
# MAGIC    'My name is Sarah Chen and my checked bag never arrived in Seattle. Please reach me at sarah.chen@example.com or 415-555-0142.'),
# MAGIC   (1002, TIMESTAMP'2026-07-10 09:02:00', 'chat',            'en',
# MAGIC    'Flight UA455 out of SFO was delayed almost four hours and I missed my connection in Denver. This is unacceptable.'),
# MAGIC   (1003, TIMESTAMP'2026-07-10 10:47:00', 'email',           'en',
# MAGIC    'I was charged twice for seat selection on booking ABC123. Please refund the duplicate 45 dollar charge.'),
# MAGIC   (1004, TIMESTAMP'2026-07-10 11:20:00', 'app_review',      'en',
# MAGIC    'The crew on my flight were lovely and boarding was quick. Best service I have had in ages, thank you.'),
# MAGIC   (1005, TIMESTAMP'2026-07-10 12:05:00', 'call_transcript', 'en',
# MAGIC    'Caller reports their flight to Boston was cancelled overnight. They were rebooked for the morning but want compensation for the hotel.'),
# MAGIC   (1006, TIMESTAMP'2026-07-10 13:33:00', 'app_review',      'es',
# MAGIC    'Mi maleta llego danada y nadie me ayudo en el aeropuerto. Muy decepcionado con el servicio.'),
# MAGIC   (1007, TIMESTAMP'2026-07-10 14:41:00', 'app_review',      'en',
# MAGIC    'i dont recieve my refund yet its been 3 week and no one answer my emails very frustrating'),
# MAGIC   (1008, TIMESTAMP'2026-07-10 15:58:00', 'app_review',      'en',
# MAGIC    'Boarding was chaos, the gate agent was rude, and no one explained the delay. Do better.')

# COMMAND ----------

# MAGIC %md
# MAGIC ### How to verify it worked
# MAGIC Eight rows, a spread of channels, and one Spanish row.

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT ticket_id, channel, language, left(raw_text, 60) AS preview
# MAGIC FROM unity_airways.rag.ua_support_tickets
# MAGIC ORDER BY ticket_id

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. `ai_query` — the general workhorse
# MAGIC `ai_query(endpoint, request, ...)` calls a served model over a column. Each **row becomes one model
# MAGIC request**; the SQL engine spreads the work across compute and handles distribution and retries. The
# MAGIC `endpoint` is a Foundation Model name (here `databricks-claude-sonnet-4-5`) **or** your own agent
# MAGIC endpoint. `request` is the prompt string.
# MAGIC
# MAGIC > 💡 TIP: Develop on a sample first — add `LIMIT 200`, confirm the output shape and cost, *then* remove
# MAGIC > the `LIMIT` and run the full table.

# COMMAND ----------

# MAGIC %sql
# MAGIC -- Simplest possible call: a free-text prompt per row. Good for a smoke test.
# MAGIC SELECT
# MAGIC   ticket_id,
# MAGIC   ai_query(
# MAGIC     'databricks-claude-sonnet-4-5',
# MAGIC     CONCAT('In one short sentence, what is this airline customer asking for? Ticket: ', raw_text)
# MAGIC   ) AS gist
# MAGIC FROM unity_airways.rag.ua_support_tickets
# MAGIC WHERE raw_text IS NOT NULL
# MAGIC LIMIT 3

# COMMAND ----------

# MAGIC %md
# MAGIC ### Structured JSON output — get columns, not prose
# MAGIC Free text is hard to query. Force JSON so the result parses into fields you can `SELECT`.
# MAGIC - `responseFormat => '{"type":"json_object"}'` is the modern path for chat models (DBR 15.4+).
# MAGIC - `failOnError => false` is the **batch-safety switch**: instead of one bad row killing the whole run,
# MAGIC   each row returns a STRUCT `{response, error}` so you can route failures to a sidecar.
# MAGIC - `modelParameters => named_struct('temperature', 0.0, ...)` makes extraction repeatable and diffable.
# MAGIC
# MAGIC > 📌 IMPORTANT: Always set `failOnError => false` on a scheduled batch `ai_query`. One malformed response
# MAGIC > should never fail two million rows.

# COMMAND ----------

# MAGIC %sql
# MAGIC CREATE OR REPLACE TABLE unity_airways.rag.ua_tickets_structured AS
# MAGIC SELECT
# MAGIC   ticket_id,
# MAGIC   ai_query(
# MAGIC     'databricks-claude-sonnet-4-5',
# MAGIC     CONCAT(
# MAGIC       'Extract as JSON with keys intent, urgency (1-5), refund_requested (bool), ',
# MAGIC       'affected_flight. Ticket: ', raw_text
# MAGIC     ),
# MAGIC     responseFormat => '{"type":"json_object"}',
# MAGIC     failOnError     => false,            -- batch safety: no single row kills the job
# MAGIC     modelParameters => named_struct('temperature', CAST(0.0 AS DOUBLE), 'max_tokens', 300)
# MAGIC   ) AS ai_response
# MAGIC FROM unity_airways.rag.ua_support_tickets
# MAGIC WHERE raw_text IS NOT NULL   -- NULL in => NULL out; filter to skip wasted calls

# COMMAND ----------

# MAGIC %md
# MAGIC With `failOnError => false`, `ai_response` is a STRUCT of `response` (the model's text) and `error`.
# MAGIC Parse the JSON into real columns with `from_json`, and keep the `error` column so failures are visible.
# MAGIC
# MAGIC > ⚠️ GOTCHA: On an older runtime where `responseFormat` is unavailable, fall back to `returnType => '<DDL>'`
# MAGIC > (parses the response like `from_json`, DBR 15.2+) or just prompt for JSON and parse with `from_json`.
# MAGIC > Alternative form of the call above:
# MAGIC > `ai_query('databricks-claude-sonnet-4-5', <prompt>, returnType => 'STRUCT<intent:STRING, urgency:INT, refund_requested:BOOLEAN, affected_flight:STRING>')`

# COMMAND ----------

# MAGIC %sql
# MAGIC -- Parse the JSON into typed columns and split off failures.
# MAGIC SELECT
# MAGIC   ticket_id,
# MAGIC   from_json(
# MAGIC     ai_response.response,
# MAGIC     'STRUCT<intent:STRING, urgency:INT, refund_requested:BOOLEAN, affected_flight:STRING>'
# MAGIC   )                    AS fields,
# MAGIC   ai_response.errorMessage AS error   -- non-null only on rows that failed; route these to a sidecar table
# MAGIC FROM unity_airways.rag.ua_tickets_structured
# MAGIC ORDER BY ticket_id

# COMMAND ----------

# MAGIC %md
# MAGIC ### Point `ai_query` at your own agent endpoint
# MAGIC Same function, custom endpoint name. Here we call the Unity Airways `ResponsesAgent` deployed in 11.1 /
# MAGIC Module 09 (`ua-support-agent`) instead of a Foundation Model, to draft a reply per ticket.
# MAGIC
# MAGIC > This cell needs the `ua-support-agent` endpoint to exist. If you have not deployed it, skip this cell —
# MAGIC > the rest of the notebook runs against Foundation Models.

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT
# MAGIC   ticket_id,
# MAGIC   ai_query(
# MAGIC     'ua-support-agent',                       -- your custom Model Serving endpoint (name from 11.1)
# MAGIC     CONCAT('Draft a short, empathetic reply to this customer: ', raw_text),
# MAGIC     failOnError => false
# MAGIC   ).response AS draft_reply   -- with failOnError => false the call returns a STRUCT; .response is the text
# MAGIC FROM unity_airways.rag.ua_support_tickets
# MAGIC WHERE raw_text IS NOT NULL
# MAGIC LIMIT 3

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Task-specific functions
# MAGIC These are pre-tuned one-liners — no endpoint argument, Databricks picks and tunes the model. **Prefer
# MAGIC them over `ai_query` whenever the task fits**: less prompt engineering, better accuracy, fewer tokens.
# MAGIC Reach for `ai_query` only for a custom endpoint, nested JSON, multimodal input, or explicit sampling
# MAGIC control.

# COMMAND ----------

# MAGIC %md
# MAGIC ### `ai_classify` — route the ticket to a queue
# MAGIC 2–500 labels. Passing labels **with short descriptions** improves accuracy on ambiguous categories.

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT
# MAGIC   ticket_id,
# MAGIC   ai_classify(
# MAGIC     raw_text,
# MAGIC     '{"baggage":"lost, delayed, or damaged luggage",
# MAGIC       "delay":"flight delays, cancellations, missed connections",
# MAGIC       "billing":"refunds, charges, fare disputes",
# MAGIC       "other":"anything else"}'
# MAGIC   ) AS intent
# MAGIC FROM unity_airways.rag.ua_support_tickets
# MAGIC WHERE raw_text IS NOT NULL
# MAGIC ORDER BY ticket_id

# COMMAND ----------

# MAGIC %md
# MAGIC When a single ticket can belong to several buckets (e.g. a delay *and* a refund request), set
# MAGIC `multilabel => 'true'` and pass a plain array of labels. The result is an array of labels per row.

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT
# MAGIC   ticket_id,
# MAGIC   ai_classify(
# MAGIC     raw_text,
# MAGIC     ARRAY('baggage', 'delay', 'billing', 'compensation', 'praise'),
# MAGIC     multilabel => 'true'
# MAGIC   ) AS intents
# MAGIC FROM unity_airways.rag.ua_support_tickets
# MAGIC WHERE raw_text IS NOT NULL
# MAGIC ORDER BY ticket_id

# COMMAND ----------

# MAGIC %md
# MAGIC ### `ai_analyze_sentiment` — score the mood
# MAGIC Returns one of `positive` | `negative` | `neutral` | `mixed`.

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT ticket_id, ai_analyze_sentiment(raw_text) AS sentiment
# MAGIC FROM unity_airways.rag.ua_support_tickets
# MAGIC WHERE raw_text IS NOT NULL
# MAGIC ORDER BY ticket_id

# COMMAND ----------

# MAGIC %md
# MAGIC ### `ai_extract` — pull named entities/fields
# MAGIC Pass the text and a JSON array of field names; get a struct of the values back. (For document-scale
# MAGIC extraction with typed schemas and confidence scores, see the data-prep angle in **Module 03**.)

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT
# MAGIC   ticket_id,
# MAGIC   ai_extract(raw_text, ARRAY('affected_flight', 'booking_reference', 'destination_city')) AS extracted
# MAGIC FROM unity_airways.rag.ua_support_tickets
# MAGIC WHERE raw_text IS NOT NULL
# MAGIC ORDER BY ticket_id

# COMMAND ----------

# MAGIC %md
# MAGIC ### `ai_summarize` — one line for the daily queue
# MAGIC The optional second argument caps the word count (`0` = uncapped).

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT ticket_id, ai_summarize(raw_text, 20) AS one_liner
# MAGIC FROM unity_airways.rag.ua_support_tickets
# MAGIC WHERE raw_text IS NOT NULL
# MAGIC ORDER BY ticket_id

# COMMAND ----------

# MAGIC %md
# MAGIC ### `ai_mask` — redact PII before analysts ever see it
# MAGIC Pass the entity types to hide. Check `ticket_id = 1001` — the name, email, and phone should be gone.

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT
# MAGIC   ticket_id,
# MAGIC   ai_mask(raw_text, ARRAY('person', 'email', 'phone', 'address')) AS safe_text
# MAGIC FROM unity_airways.rag.ua_support_tickets
# MAGIC WHERE raw_text IS NOT NULL
# MAGIC ORDER BY ticket_id

# COMMAND ----------

# MAGIC %md
# MAGIC ### `ai_translate` — normalize the global inbox to one language
# MAGIC The Spanish app review (`ticket_id = 1006`) should come back in English. `ai_translate` supports a fixed
# MAGIC set of common languages — for anything outside it, use `ai_query` with a multilingual model.

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT
# MAGIC   ticket_id,
# MAGIC   language,
# MAGIC   ai_translate(raw_text, 'en') AS text_en
# MAGIC FROM unity_airways.rag.ua_support_tickets
# MAGIC WHERE raw_text IS NOT NULL AND language <> 'en'
# MAGIC ORDER BY ticket_id

# COMMAND ----------

# MAGIC %md
# MAGIC ### `ai_fix_grammar` and `ai_gen` — tidy input, generate output
# MAGIC `ai_fix_grammar` cleans up user-generated text (see the messy review `ticket_id = 1007`); `ai_gen` runs a
# MAGIC free-form generation prompt. Both shown here over app reviews.

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT
# MAGIC   ticket_id,
# MAGIC   ai_fix_grammar(raw_text)                                        AS text_clean,
# MAGIC   ai_gen(CONCAT('Write a one-line apology for this review: ', raw_text)) AS apology_line
# MAGIC FROM unity_airways.rag.ua_support_tickets
# MAGIC WHERE raw_text IS NOT NULL AND channel = 'app_review'
# MAGIC ORDER BY ticket_id

# COMMAND ----------

# MAGIC %md
# MAGIC ### `vector_search` — join retrieval into your data from SQL
# MAGIC Query a Databricks AI Search index inside a SQL query — retrieve the top policy chunks relevant to each
# MAGIC ticket, so retrieval lives next to your data instead of only in Python.
# MAGIC
# MAGIC > This cell needs the AI Search index `unity_airways.rag.ua_rag_chunks_index` (built in Module 04). Skip
# MAGIC > it if you have not created the index yet.

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT
# MAGIC   t.ticket_id,
# MAGIC   vector_search(
# MAGIC     index       => 'unity_airways.rag.ua_rag_chunks_index',
# MAGIC     query_text  => t.raw_text,
# MAGIC     num_results => 3
# MAGIC   ) AS top_policy_chunks
# MAGIC FROM unity_airways.rag.ua_support_tickets t
# MAGIC WHERE t.raw_text IS NOT NULL
# MAGIC LIMIT 3

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Batch enrichment — the write-back
# MAGIC This is the production pattern: run several task functions in **one pass** and land the result in a new
# MAGIC Delta table. Dashboards read `intent` + `sentiment`, analysts see only `safe_text`, and downstream models
# MAGIC train on the structured columns — nobody ever calls a model directly.
# MAGIC
# MAGIC > 📌 IMPORTANT: `unity_airways.rag.ua_tickets_enriched` is exactly the table the scheduled Lakeflow Job in
# MAGIC > **11.11** re-runs against new rows. The whole production loop is: Delta in → AI Function in `SELECT` →
# MAGIC > Delta out → Lakeflow Job on a schedule.

# COMMAND ----------

# MAGIC %sql
# MAGIC CREATE OR REPLACE TABLE unity_airways.rag.ua_tickets_enriched AS
# MAGIC SELECT
# MAGIC   ticket_id,
# MAGIC   received_at,
# MAGIC   channel,
# MAGIC   -- route the ticket to a queue (labels with descriptions = better accuracy)
# MAGIC   ai_classify(
# MAGIC     raw_text,
# MAGIC     '{"baggage":"lost, delayed, or damaged luggage",
# MAGIC       "delay":"flight delays, cancellations, missed connections",
# MAGIC       "billing":"refunds, charges, fare disputes",
# MAGIC       "other":"anything else"}'
# MAGIC   )                                              AS intent,
# MAGIC   ai_analyze_sentiment(raw_text)                 AS sentiment,   -- positive|negative|neutral|mixed
# MAGIC   ai_summarize(raw_text, 20)                     AS one_liner,   -- <=20 words for the queue
# MAGIC   -- redact PII BEFORE analysts or downstream tables ever see it
# MAGIC   ai_mask(raw_text, ARRAY('person','email','phone','address')) AS safe_text
# MAGIC FROM unity_airways.rag.ua_support_tickets
# MAGIC WHERE raw_text IS NOT NULL   -- functions return NULL on NULL input; filter to save calls

# COMMAND ----------

# MAGIC %md
# MAGIC ### How to verify it worked
# MAGIC Sensible buckets (expect several `delay`/`billing` rows and mostly `negative` sentiment), and no raw
# MAGIC names, emails, or phone numbers left in `safe_text`.

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT intent, sentiment, count(*) AS n
# MAGIC FROM unity_airways.rag.ua_tickets_enriched
# MAGIC GROUP BY 1, 2
# MAGIC ORDER BY n DESC

# COMMAND ----------

# MAGIC %sql
# MAGIC -- Spot-check the redaction and the one-line summaries.
# MAGIC SELECT ticket_id, intent, sentiment, one_liner, safe_text
# MAGIC FROM unity_airways.rag.ua_tickets_enriched
# MAGIC ORDER BY ticket_id

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Optional — the same call from PySpark
# MAGIC AI Functions are also callable via `expr()` inside a DataFrame, handy when your pipeline is already
# MAGIC Python. The underlying function is identical; this just wraps it.

# COMMAND ----------

from pyspark.sql.functions import expr

(spark.table("unity_airways.rag.ua_support_tickets")
      .filter("raw_text IS NOT NULL")
      .withColumn("sentiment", expr("ai_analyze_sentiment(raw_text)"))
      .withColumn("intent",    expr("ai_classify(raw_text, array('baggage','delay','billing','other'))"))
      .select("ticket_id", "channel", "sentiment", "intent")
      .display())

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6. Throughput, cost, and when to use batch vs real-time
# MAGIC - **Each row = one model request**, auto-batched and distributed by the SQL engine. Throughput matters,
# MAGIC   per-row latency does not — seconds-to-minutes end-to-end is expected and fine.
# MAGIC - **Cost accumulates on large datasets.** Estimate token usage, filter aggressively (`WHERE ... IS NOT
# MAGIC   NULL`, only new rows), and test on a `LIMIT` sample before the full table.
# MAGIC - **Batch `ai_query` vs a real-time endpoint (11.1)** — the first question is always *"is a human
# MAGIC   waiting?"*
# MAGIC
# MAGIC | | Use AI Functions / `ai_query` | Use Model Serving (11.1) |
# MAGIC |---|---|---|
# MAGIC | Timing | Scheduled / recurring / batch | User-driven, real-time |
# MAGIC | Data size | Large tables, bulk | Small, individual requests |
# MAGIC | Latency | Seconds to minutes OK | Must answer in milliseconds |
# MAGIC | Examples | Enrichment, embeddings, eval pipelines | Chatbots, live RAG, support agents |
# MAGIC
# MAGIC - `ai_query` is **batch inference on tables, not a chat API** — no conversational state, tools, or
# MAGIC   multi-turn. If you need those, call your deployed *agent* endpoint from `ai_query` (as in Section 2).
# MAGIC - For deep cost/throughput tuning (provisioned throughput, concurrency, batching knobs), see **Module 16**.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Recap, gotchas, and next steps
# MAGIC **What you built**
# MAGIC - `unity_airways.rag.ua_support_tickets` — the seed raw-feedback table.
# MAGIC - `unity_airways.rag.ua_tickets_structured` — `ai_query` JSON output (with an `error` column for failures).
# MAGIC - `unity_airways.rag.ua_tickets_enriched` — the one-pass enrichment the **11.11** job re-runs.
# MAGIC
# MAGIC **Gotchas to remember**
# MAGIC - Set `failOnError => false` on every batch `ai_query`, then split `error IS NOT NULL` into a sidecar.
# MAGIC - **NULL in, NULL out** — filter `WHERE raw_text IS NOT NULL` first; it also saves wasted calls.
# MAGIC - Prefer a task-specific function when one fits; drop to `ai_query` only for custom endpoints, nested
# MAGIC   JSON, multimodal, or sampling control.
# MAGIC - `responseFormat` needs DBR 15.4+; fall back to `returnType` (15.2+) or prompt-for-JSON + `from_json`.
# MAGIC - AI Functions want a **Pro or Serverless** warehouse (not Classic/Starter); `ai_forecast` fails on Classic.
# MAGIC - **Model-name drift** — endpoint names churn. Confirm `databricks-claude-sonnet-4-5` (and any embedding
# MAGIC   endpoint) on the supported-models page at authoring time; never guess.
# MAGIC - `ai_parse_document` / `ai_extract` for document **data prep** live in **Module 03** — not duplicated here.
# MAGIC
# MAGIC **Cleanup (optional)**
# MAGIC ```
# MAGIC spark.sql("DROP TABLE IF EXISTS unity_airways.rag.ua_tickets_structured")
# MAGIC spark.sql("DROP TABLE IF EXISTS unity_airways.rag.ua_tickets_enriched")
# MAGIC -- keep ua_support_tickets; 11.11 reuses it
# MAGIC ```
# MAGIC
# MAGIC **Next roadmap topic**
# MAGIC - **11.11 — Schedule the enrichment as a Lakeflow Job:** attach the `ua_tickets_enriched` query to a
# MAGIC   nightly trigger so it re-runs against new tickets and appends to the enriched table. That is the whole
# MAGIC   production loop.
