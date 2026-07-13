# Databricks notebook source
# MAGIC %md
# MAGIC # Module 14 lab — Build, curate, test and drive the "Unity Airways Revenue Analytics" Genie Agent
# MAGIC **Roadmap:** Module 14 (AI/BI Genie) · Topics 14.1–14.9 · ★ 14.3 cornerstone · [Theory + Hands-on]
# MAGIC
# MAGIC A Genie Agent is a **natural-language interface to structured data in Unity Catalog** — you ask a business
# MAGIC question in English, Genie writes SQL, runs it on a **serverless SQL warehouse**, and answers with a table, a
# MAGIC chart, and the SQL it used. Genie is **UI-first**: you create and curate it in the console. So this lab mixes
# MAGIC `%md` console walkthroughs with the genuinely runnable bits:
# MAGIC 1. **prepare the `unity_airways.analytics` data** (star schema + COMMENTs) and point at the **`bookings_metrics`
# MAGIC    metric view** (built in Module 15) as the trusted Genie data source, and
# MAGIC 2. **create → curate → test** the Agent (console steps, clearly marked), and
# MAGIC 3. exercise what IS programmatic — the **Genie Agents API** round-trip (`w.genie.*`).
# MAGIC
# MAGIC | Step | Topic | Status | What you do |
# MAGIC |---|---|---|---|
# MAGIC | 0–1 | data prep | — | **Runnable SQL/PySpark**: star schema + comments; reference the metric view |
# MAGIC | 2 | **14.2** Create & manage | GA | `%md` console: create the Agent, add data sources, sample questions |
# MAGIC | 3 | **14.3** ★ Curate & tune | GA | `%md` console + **runnable** `COMMENT ON`; the benchmark loop |
# MAGIC | 4 | **14.4** Test & monitor | GA | `%md` console: benchmark, read the SQL, feedback/audit |
# MAGIC | 5 | **14.5** Verified answers | GA | `%md` console: certify a question→SQL pair |
# MAGIC | 6 | **14.6** Agent mode | GA | `%md` console: multi-query deep research |
# MAGIC | 7 | **14.7** Embed | GA | `%md`: iframe vs API |
# MAGIC | 8 | **14.8** Genie Agents API | GA | **Runnable** SDK round-trip (full depth in `14-8-genie-api.py`) |
# MAGIC | 9 | **14.9** Genie One | GA | `%md`: business-user unified UI, budgets |
# MAGIC
# MAGIC Cornerstone deep-dive: `modules/14-aibi-genie/curate-tune-genie.md` (14.3). Standalone API notebook: `14-8-genie-api.py`.
# MAGIC
# MAGIC ## Prerequisites (read before running)
# MAGIC - **Compute:** a **serverless notebook/job** (or DBR 15.4 LTS+). The SQL cells need a **serverless (or Pro) SQL
# MAGIC   warehouse** — Genie and metric views both require Pro/Serverless SQL.
# MAGIC - **Unity Catalog:** `CREATE`/`USE` on catalog `unity_airways`, schema `analytics`. If Module 15 already built the
# MAGIC   star schema + `bookings_metrics`, the `CREATE ... IF NOT EXISTS` cells are idempotent and safe to re-run.
# MAGIC - **Genie Agent:** created in the console (Step 2). For Step 8 you need the Agent's **`space_id`** (from its URL).
# MAGIC - **Auth for the API (Step 8):** default notebook auth works in-workspace; for external clients use a **PAT or
# MAGIC   OAuth** token (see `14-8-genie-api.py`).
# MAGIC - **Learner-set identifiers:** `CATALOG`, `SCHEMA`, `SPACE_ID` in Step 0.
# MAGIC
# MAGIC > 📌 **The one rule of this module — Genie is only as good as the semantic layer you point it at.**
# MAGIC > Accuracy comes from **curation** (comments, a metric view, instructions, verified answers, synonyms), not the model.
# MAGIC > Attaching the **`bookings_metrics` metric view** is the single highest-leverage setup choice.
# MAGIC >
# MAGIC > **Names:** **Genie Agents** (formerly "Genie Spaces"; the REST path still says `spaces`), **Agent mode** (formerly
# MAGIC > "deep research"), **Genie One** (formerly "Databricks One").

# COMMAND ----------

# MAGIC %md
# MAGIC ## 0. Install libraries and set variables
# MAGIC The SDK powers the runnable Genie Agents API round-trip in Step 8. `databricks-sdk` is usually pre-installed on
# MAGIC serverless/DBR ML; the `%pip` keeps the version predictable (0.73.0+ has the full `w.genie.*` surface used here).

# COMMAND ----------

# MAGIC %pip install -U "databricks-sdk>=0.73"
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

# Learner-set variables — LOCKED names from the shared P5 build brief.
CATALOG   = "unity_airways"
SCHEMA    = "analytics"
METRIC_VIEW = f"{CATALOG}.{SCHEMA}.bookings_metrics"   # built in Module 15 (15.x) — the trusted KPI source
GENIE_AGENT_NAME = "Unity Airways Revenue Analytics"    # the Genie Agent you create in Step 2

# For Step 8 (Genie Agents API): read this from the Agent's URL after you create it in the console
# .../genie/rooms/<SPACE_ID>  — the path keeps the legacy "spaces/rooms" noun even though the product is "Genie Agents".
SPACE_ID = "REPLACE-with-your-genie-space-id"

spark.sql(f"CREATE CATALOG IF NOT EXISTS {CATALOG}")
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")
spark.sql(f"USE {CATALOG}.{SCHEMA}")
print("Catalog.schema :", f"{CATALOG}.{SCHEMA}")
print("Metric view    :", METRIC_VIEW)
print("Genie Agent    :", GENIE_AGENT_NAME)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Prepare the `unity_airways.analytics` data — star schema with COMMENTs
# MAGIC Genie reads table/column **comments as ground truth**, so we create the star schema *with* comments. This is the
# MAGIC same star schema Module 15 builds its `bookings_metrics` metric view on — `IF NOT EXISTS` keeps it idempotent.
# MAGIC (Small, deterministic, serverless-friendly seed so the Agent has data to query.)

# COMMAND ----------

# MAGIC %sql
# MAGIC -- Dimension: flights/routes. Comments teach Genie what each column means.
# MAGIC CREATE TABLE IF NOT EXISTS dim_flights (
# MAGIC   flight_id      STRING  COMMENT 'Flight identifier',
# MAGIC   route_id       STRING  COMMENT 'Route identifier (origin-dest pair)',
# MAGIC   origin_airport STRING  COMMENT 'Origin airport IATA code',
# MAGIC   dest_airport   STRING  COMMENT 'Destination airport IATA code',
# MAGIC   aircraft_type  STRING  COMMENT 'Aircraft model',
# MAGIC   distance_miles INT     COMMENT 'Great-circle distance in miles',
# MAGIC   delay_minutes  INT     COMMENT 'Departure delay in minutes (0 = on time)'
# MAGIC ) COMMENT 'Flight dimension: one row per flight, keyed by flight_id.';
# MAGIC
# MAGIC CREATE TABLE IF NOT EXISTS dim_customers (
# MAGIC   customer_id  STRING COMMENT 'Customer identifier',
# MAGIC   loyalty_tier STRING COMMENT 'Loyalty tier: Blue, Silver, Gold, or Platinum',
# MAGIC   home_country STRING COMMENT 'Customer home country',
# MAGIC   segment      STRING COMMENT 'Travel segment: Leisure or Business'
# MAGIC ) COMMENT 'Customer dimension: one row per customer, keyed by customer_id.';
# MAGIC
# MAGIC CREATE TABLE IF NOT EXISTS dim_airports (
# MAGIC   airport_code STRING COMMENT 'Airport IATA code (join to dim_flights origin/dest)',
# MAGIC   city         STRING COMMENT 'Airport city',
# MAGIC   country      STRING COMMENT 'Airport country',
# MAGIC   region       STRING COMMENT 'Geographic region'
# MAGIC ) COMMENT 'Airport dimension.';
# MAGIC
# MAGIC -- Fact: bookings. The COMMENTs encode the business rules Genie must respect (revenue = base + ancillary).
# MAGIC CREATE TABLE IF NOT EXISTS fct_bookings (
# MAGIC   booking_id    BIGINT COMMENT 'Booking identifier (grain: one row per booking)',
# MAGIC   flight_id     STRING COMMENT 'FK to dim_flights.flight_id',
# MAGIC   customer_id   STRING COMMENT 'FK to dim_customers.customer_id',
# MAGIC   route_id      STRING COMMENT 'Route identifier',
# MAGIC   booking_date  DATE   COMMENT 'Date the booking was made',
# MAGIC   travel_date   DATE   COMMENT 'Date of travel',
# MAGIC   fare_class    STRING COMMENT 'Fare class: Economy, Premium, Business, First',
# MAGIC   channel       STRING COMMENT 'Booking channel: direct, ota, agent',
# MAGIC   base_fare_usd DOUBLE COMMENT 'Base fare in USD',
# MAGIC   ancillary_usd DOUBLE COMMENT 'Ancillary spend (bags, seats, upgrades) in USD; part of total revenue',
# MAGIC   seats         INT    COMMENT 'Seats in the booking',
# MAGIC   status        STRING COMMENT 'Booking status: booked, flown, or cancelled. Exclude cancelled from revenue unless asked.'
# MAGIC ) COMMENT 'Booking fact. Revenue = base_fare_usd + ancillary_usd. Exclude status = cancelled from revenue unless asked.';

# COMMAND ----------

# MAGIC %md
# MAGIC ### Seed a small deterministic dataset
# MAGIC Generated from `range()` with modulo expressions so results are reproducible across runs. Enough rows to make
# MAGIC "by fare class" / "by loyalty tier" answers meaningful. Re-running is safe (`INSERT OVERWRITE`).

# COMMAND ----------

from pyspark.sql import functions as F

# Dimensions -------------------------------------------------------------
airports = [("JFK","New York","USA","Americas"),("LHR","London","UK","EMEA"),
            ("NRT","Tokyo","Japan","APAC"),("SFO","San Francisco","USA","Americas"),
            ("SIN","Singapore","Singapore","APAC"),("CDG","Paris","France","EMEA")]
spark.createDataFrame(airports, "airport_code string, city string, country string, region string") \
    .write.mode("overwrite").saveAsTable("dim_airports")

tiers    = ["Blue","Silver","Gold","Platinum"]
segments = ["Leisure","Business"]
countries= ["USA","UK","Japan","France","Singapore"]
cust = (spark.range(200).withColumn("customer_id", F.concat(F.lit("C"), F.col("id").cast("string")))
        .withColumn("loyalty_tier", F.element_at(F.array(*[F.lit(t) for t in tiers]), (F.col("id") % 4 + 1).cast("int")))
        .withColumn("home_country", F.element_at(F.array(*[F.lit(c) for c in countries]), (F.col("id") % 5 + 1).cast("int")))
        .withColumn("segment", F.element_at(F.array(*[F.lit(s) for s in segments]), (F.col("id") % 2 + 1).cast("int")))
        .select("customer_id","loyalty_tier","home_country","segment"))
cust.write.mode("overwrite").saveAsTable("dim_customers")

routes = ["JFK-LHR","SFO-NRT","JFK-CDG","SIN-LHR","SFO-SIN"]
flights = (spark.range(60).withColumn("flight_id", F.concat(F.lit("UA"), (F.col("id")+100).cast("string")))
           .withColumn("route_id", F.element_at(F.array(*[F.lit(r) for r in routes]), (F.col("id") % 5 + 1).cast("int")))
           .withColumn("origin_airport", F.split("route_id","-").getItem(0))
           .withColumn("dest_airport", F.split("route_id","-").getItem(1))
           .withColumn("aircraft_type", F.element_at(F.array(F.lit("B777"),F.lit("A350"),F.lit("B787")), (F.col("id")%3+1).cast("int")))
           .withColumn("distance_miles", (F.lit(3000) + (F.col("id")%9)*450).cast("int"))
           .withColumn("delay_minutes", (F.col("id")%7*8).cast("int"))
           .select("flight_id","route_id","origin_airport","dest_airport","aircraft_type","distance_miles","delay_minutes"))
flights.write.mode("overwrite").saveAsTable("dim_flights")

# Fact: 1500 bookings spread across 4 quarters of 2025 -------------------
fares    = ["Economy","Premium","Business","First"]
channels = ["direct","ota","agent"]
statuses = ["booked","flown","flown","flown","cancelled"]   # ~20% cancelled
bookings = (spark.range(1500).withColumn("booking_id", F.col("id"))
    .withColumn("flight_id", F.concat(F.lit("UA"), ((F.col("id")%60)+100).cast("string")))
    .withColumn("customer_id", F.concat(F.lit("C"), (F.col("id")%200).cast("string")))
    .withColumn("route_id", F.element_at(F.array(*[F.lit(r) for r in routes]), (F.col("id")%5+1).cast("int")))
    .withColumn("booking_date", F.date_add(F.lit("2025-01-01"), (F.col("id")%360).cast("int")))
    .withColumn("travel_date", F.date_add(F.col("booking_date"), 21))
    .withColumn("fare_class", F.element_at(F.array(*[F.lit(f) for f in fares]), (F.col("id")%4+1).cast("int")))
    .withColumn("channel", F.element_at(F.array(*[F.lit(c) for c in channels]), (F.col("id")%3+1).cast("int")))
    .withColumn("base_fare_usd", (F.lit(200.0) + (F.col("id")%4)*350 + (F.col("id")%10)*15).cast("double"))
    .withColumn("ancillary_usd", ((F.col("id")%5)*22.5).cast("double"))
    .withColumn("seats", ((F.col("id")%3)+1).cast("int"))
    .withColumn("status", F.element_at(F.array(*[F.lit(s) for s in statuses]), (F.col("id")%5+1).cast("int")))
    .select("booking_id","flight_id","customer_id","route_id","booking_date","travel_date",
            "fare_class","channel","base_fare_usd","ancillary_usd","seats","status"))
bookings.write.mode("overwrite").saveAsTable("fct_bookings")

print("Seeded:", spark.table("fct_bookings").count(), "bookings,",
      spark.table("dim_customers").count(), "customers,",
      spark.table("dim_flights").count(), "flights.")

# COMMAND ----------

# MAGIC %md
# MAGIC ### The metric view (built in Module 15) is the trusted Genie data source
# MAGIC `bookings_metrics` defines the KPIs **once** — `total_revenue = SUM(base_fare_usd + ancillary_usd)`,
# MAGIC `cancellation_rate`, `ancillary_attach_rate` — with synonyms/display names (15.6). Genie inherits those governed
# MAGIC definitions instead of guessing. If Module 15 hasn't been run yet, build it there first; the cell below just
# MAGIC **checks whether it exists** so you know what to attach as a data source in Step 2.

# COMMAND ----------

exists = spark.sql(f"SHOW VIEWS IN {CATALOG}.{SCHEMA}").where(F.col("viewName") == "bookings_metrics").count() > 0
if not exists:
    # metric views also appear via information_schema.tables with table_type METRIC_VIEW on current DBR — check both
    exists = spark.sql(
        f"SELECT 1 FROM {CATALOG}.information_schema.tables "
        f"WHERE table_schema = '{SCHEMA}' AND table_name = 'bookings_metrics'").count() > 0
print("bookings_metrics present:", exists,
      "\n→ Attach it as a Genie data source in Step 2." if exists
      else "\n→ Build it in the Module 15 lab first, then attach it in Step 2.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 2 — Create & manage the Genie Agent (14.2) · GA · [Hands-on, console]
# MAGIC Genie is **UI-first** — there is no create-agent SDK call. Build it in the console:
# MAGIC
# MAGIC 1. Left nav → **Genie** (SQL / AI-BI section) → **New**.
# MAGIC 2. **Name:** `Unity Airways Revenue Analytics`. **Warehouse:** a running **serverless (or Pro) SQL warehouse**.
# MAGIC 3. **Add data sources (the important step):** the star-schema tables in `unity_airways.analytics`
# MAGIC    (`fct_bookings`, `dim_flights`, `dim_customers`, `dim_airports`) **and** the **`bookings_metrics` metric view**.
# MAGIC    Prefer the metric view for KPIs — it carries the governed definitions.
# MAGIC 4. **Seed sample questions** (teach vocabulary + show users what to ask):
# MAGIC    - *"What was total revenue last quarter by fare class?"*
# MAGIC    - *"Which routes have the highest cancellation rate?"*
# MAGIC    - *"Compare ancillary attach rate across loyalty tiers."*
# MAGIC 5. **Share:** CAN VIEW (ask) / CAN EDIT (curate).
# MAGIC
# MAGIC **How to verify:** ask a sample question in the Agent chat — you should get a number, a chart, and **visible SQL**
# MAGIC that references `bookings_metrics` (or the star tables). Wrong joins/counts = a **curation** signal (Step 3).
# MAGIC
# MAGIC > 💡 **TIP:** Copy the Agent's **`space_id`** from its URL (`.../genie/rooms/<space_id>`) into `SPACE_ID` in Step 0
# MAGIC > so the Step 8 API round-trip works.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 3 — ★ Curate & tune (14.3) · GA · [Theory + Hands-on]
# MAGIC Curation is where the Agent goes from demo to trusted. Full deep-dive: `modules/14-aibi-genie/curate-tune-genie.md`.
# MAGIC **Fix accuracy upstream first**, then add in-Agent curation:
# MAGIC
# MAGIC 1. **Comments (runnable below)** — Genie reads them as ground truth. Already set at table creation; reinforce key ones.
# MAGIC 2. **General instructions (console):** *"Revenue = `total_revenue` from `bookings_metrics`; exclude cancelled
# MAGIC    bookings unless asked; 'last quarter' = previous full calendar quarter (booking_date)."*
# MAGIC 3. **Synonyms (console):** "top cabin" → `fare_class = 'First'`; "attach rate" → `ancillary_attach_rate`;
# MAGIC    "churn/cancellations" → `cancellation_rate`.
# MAGIC 4. **Trusted assets — example SQL (console):** a verified `revenue_by_fare_class` query so Genie reuses the exact
# MAGIC    join + grouping instead of improvising.
# MAGIC 5. **Benchmarks (console):** 15–30 question→expected-answer pairs; run them, read the SQL, fix misses, re-run.
# MAGIC
# MAGIC **How to verify:** re-run your benchmark set after attaching the metric view + adding two verified examples —
# MAGIC the share of questions with the *right SQL and number* should measurably rise.

# COMMAND ----------

# MAGIC %sql
# MAGIC -- Reinforce the highest-value comments (curation Genie reads directly). Runnable and idempotent.
# MAGIC COMMENT ON TABLE unity_airways.analytics.fct_bookings
# MAGIC   IS 'Booking fact (one row per booking). Revenue = base_fare_usd + ancillary_usd. Exclude status = cancelled from revenue unless asked.';
# MAGIC COMMENT ON COLUMN unity_airways.analytics.fct_bookings.ancillary_usd
# MAGIC   IS 'Ancillary spend (bags, seats, upgrades) in USD. Counts toward total revenue.';
# MAGIC COMMENT ON COLUMN unity_airways.analytics.dim_customers.loyalty_tier
# MAGIC   IS 'Loyalty tier: Blue, Silver, Gold, Platinum. "Premium customer" usually means Gold or Platinum.';

# COMMAND ----------

# MAGIC %sql
# MAGIC -- The "verified answer" query pattern you would certify in the console for 14.5.
# MAGIC -- (Direct SQL here mirrors what Genie should generate for "total revenue last quarter by fare class".)
# MAGIC -- NOTE: if bookings_metrics exists, the console version should SELECT MEASURE(total_revenue) from the metric view.
# MAGIC SELECT fare_class,
# MAGIC        ROUND(SUM(base_fare_usd + ancillary_usd), 2) AS total_revenue
# MAGIC FROM unity_airways.analytics.fct_bookings
# MAGIC WHERE status <> 'cancelled'
# MAGIC   AND booking_date >= '2025-10-01' AND booking_date < '2026-01-01'   -- previous full calendar quarter
# MAGIC GROUP BY fare_class
# MAGIC ORDER BY total_revenue DESC;

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 4 — Test & monitor (14.4) · GA · [Hands-on, console]
# MAGIC - **Test before rollout:** run your **benchmark** + adversarial/edge questions (ambiguous phrasing; questions the
# MAGIC   data can't answer). A healthy Agent asks for clarification or declines rather than inventing a join.
# MAGIC - **Read the generated SQL, not just the number** — a right number from wrong SQL is a latent bug.
# MAGIC - **Monitor in production:** Genie surfaces usage + thumbs-up/down + failing queries; every query also lands in
# MAGIC   **UC audit logs / query history** (load, cost, access).
# MAGIC - **Close the loop:** frequent correct questions → **verified answers** (Step 5); frequent wrong ones → new
# MAGIC   instructions/examples (Step 3). Treat each **thumbs-down as a labelled gap**.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 5 — Verified answers & trust/safety (14.5) · GA · [Theory + console]
# MAGIC A **verified answer** is a certified **question → SQL** pair a data owner (CAN EDIT) blesses. Genie **reuses that
# MAGIC exact SQL** for the question (or close paraphrases) and shows a **verified/blue-check** badge — removing model
# MAGIC variance for the numbers that matter.
# MAGIC
# MAGIC **Console:** open a good answer → **Verify** (or add via the curation panel) the question + its SQL.
# MAGIC
# MAGIC Trust/safety layers that make governed self-service safe:
# MAGIC - **Governance:** UC row/column permissions + lineage + audit apply to every query.
# MAGIC - **Transparency:** the SQL is always visible.
# MAGIC - **Determinism where it counts:** verified answers + the metric view pin KPIs to one definition + one query.
# MAGIC - **Graceful failure:** a curated Agent clarifies/declines instead of fabricating SQL.
# MAGIC
# MAGIC > 📌 **IMPORTANT:** verified answers and the **metric view** are complementary — the metric view guarantees the
# MAGIC > *metric definition* is consistent; a verified answer guarantees the *whole query* for a named question is blessed.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 6 — Agent mode (14.6) · GA · [Theory + Hands-on, console]
# MAGIC **Agent mode** turns Genie from one-shot text-to-SQL into a planner: for a broad question it **runs multiple
# MAGIC sub-queries**, reasons over intermediate results, and composes a **cited multi-step report** (each query shown).
# MAGIC It was previously described as **"deep research" / "Research Agent."**
# MAGIC
# MAGIC **Try it:** enable Agent mode → ask *"Why did Gold-tier ancillary revenue drop last quarter?"* → expect a
# MAGIC multi-part analysis (segment → compare → drill down) with **more than one** supporting query.
# MAGIC
# MAGIC > ⚠️ **GOTCHA:** Agent mode runs multiple queries — more warehouse cost + latency. Use it for real investigations,
# MAGIC > not "what was revenue yesterday." Verify its exact label/availability in your workspace.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 7 — Embed a Genie Agent in an external app (14.7) · GA · [Hands-on]
# MAGIC Two paths:
# MAGIC 1. **Iframe embed** — drop the Genie UI (a specific Agent) into an internal web app/portal. Fastest, branded,
# MAGIC    in-context. Requires the workspace to permit embedding for the target domain.
# MAGIC 2. **API integration** — drive Genie with the **Genie Agents API** (Step 8) and render results in your own UI.
# MAGIC    A **Databricks App** (Module 10) is the natural host on Databricks.
# MAGIC
# MAGIC Either way, calls run as an identity (user via SSO/OAuth, or a service principal) and **UC permissions still apply** —
# MAGIC embedding does not bypass governance.
# MAGIC
# MAGIC > 💡 **TIP:** iframe for a fast demo; the **API** for a production, brand-controlled experience.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 8 — Genie Agents API round-trip (14.8) · GA · [Hands-on] — RUNNABLE
# MAGIC The programmatic surface behind embedding + automation. Full REST + SDK depth: `14-8-genie-api.py`.
# MAGIC The `_and_wait` helpers poll the message to a terminal status for you (default 20-min timeout).
# MAGIC
# MAGIC **Verified `w.genie.*` surface (databricks-sdk 0.73.0):** `start_conversation(_and_wait)`,
# MAGIC `create_message(_and_wait)`, `get_message`, `get_message_query_result`, `get_message_attachment_query_result`,
# MAGIC `get_space`, `list_spaces`.

# COMMAND ----------

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.dashboards import MessageStatus

w = WorkspaceClient()

QUESTION = "What was total revenue last quarter by fare class?"

if SPACE_ID.startswith("REPLACE"):
    print("[skipped] Set SPACE_ID (from the Agent URL .../genie/rooms/<space_id>) in Step 0, then re-run.")
else:
    # 1) Start a conversation and wait for the message to reach a terminal status.
    msg = w.genie.start_conversation_and_wait(space_id=SPACE_ID, content=QUESTION)
    print("status         :", msg.status)                 # expect MessageStatus.COMPLETED
    print("conversation_id:", msg.conversation_id)
    print("message_id     :", msg.message_id or msg.id)

    # 2) Pull the generated SQL + rows from the attachments (a query attachment carries the SQL; text carries prose).
    if msg.status == MessageStatus.COMPLETED:
        for att in (msg.attachments or []):
            if att.text:
                print("\nGenie says:", att.text.content)
            if att.query:
                print("\nGenerated SQL:\n", att.query.query)
                res = w.genie.get_message_query_result(
                    space_id=SPACE_ID, conversation_id=msg.conversation_id, message_id=msg.message_id or msg.id)
                sr = res.statement_response
                if sr and sr.result and sr.result.data_array:
                    cols = [c.name for c in sr.manifest.schema.columns]
                    print("\nColumns:", cols)
                    for row in sr.result.data_array[:10]:
                        print(row)
    else:
        print("Non-completed status — inspect msg.error:", getattr(msg, "error", None))

# COMMAND ----------

# MAGIC %md
# MAGIC ### Follow-up in the same conversation (Genie keeps context)

# COMMAND ----------

if not SPACE_ID.startswith("REPLACE"):
    followup = w.genie.create_message_and_wait(
        space_id=SPACE_ID,
        conversation_id=msg.conversation_id,          # reuse the conversation → "that" refers to prior context
        content="Now break that down by loyalty tier.")
    print("follow-up status:", followup.status)
    for att in (followup.attachments or []):
        if att.query:
            print("Follow-up SQL:\n", att.query.query)

# COMMAND ----------

# MAGIC %md
# MAGIC > 📌 **IMPORTANT:** REST path uses **`spaces`** (`/api/2.0/genie/spaces/{space_id}/...`); the SDK namespace is
# MAGIC > **`w.genie`**. Poll the **message** for status; fetch the **query-result** separately for rows. Do not invent
# MAGIC > method names — re-verify `w.genie.*` against your installed SDK version.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 9 — Genie One (14.9) · GA (Domains Preview) · [Theory]
# MAGIC **Genie One** (formerly **"Databricks One"**) is the simplified single front door for **business users**:
# MAGIC - **Discovery (workspace + account level):** surfaces the Genie Agents, AI/BI dashboards, and Databricks Apps a
# MAGIC   user can access — so a business user finds "Unity Airways Revenue Analytics" without the full workspace UI.
# MAGIC - **Domains** *(Preview):* organize discoverable assets by business area (Revenue, Operations, Loyalty).
# MAGIC - **Agent-mode deep research** (14.6) surfaced for business users.
# MAGIC - **Budgets:** spend controls so self-service serverless usage stays bounded.
# MAGIC
# MAGIC **How to verify:** as a scoped/business identity, open Genie One and confirm you can discover + open the Agent and
# MAGIC a dashboard — only the assets you have rights to — without touching the full workspace.
# MAGIC
# MAGIC > ⚠️ **GOTCHA:** it's **Genie One**, not "Databricks One." Core UI is GA; **Domains are Preview** — verify
# MAGIC > per-feature availability in the customer's workspace.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Recap, gotchas and next step
# MAGIC **What you built**
# MAGIC - Prepared `unity_airways.analytics` (star schema + comments) and pointed the **"Unity Airways Revenue Analytics"**
# MAGIC   Agent at it **plus** the governed **`bookings_metrics`** metric view.
# MAGIC - Walked **create → curate → test → verify → Agent mode → embed → Genie One**, and ran the **Genie Agents API**
# MAGIC   round-trip (`w.genie.start_conversation_and_wait` → `get_message_query_result` → follow-up).
# MAGIC
# MAGIC **Gotchas to remember**
# MAGIC - **Accuracy = curation, not the model.** Comments + the metric view + instructions + verified answers are the product.
# MAGIC - **Names:** Genie Agents (not Spaces), Agent mode (not deep research), Genie One (not Databricks One); REST path keeps `spaces`.
# MAGIC - **Governance is inherited** — every query respects UC permissions and lands in the audit log.
# MAGIC - **Don't present console labels / endpoint specifics as fixed** — Genie moves fast; verify live.
# MAGIC
# MAGIC **Next roadmap topic:** **Module 15 — Business Semantics (Unity Catalog metric views)** if you skipped it — that
# MAGIC metric view is the trusted source that makes this Agent's KPI answers consistent (15.6 → 14). Then **Module 16**.
