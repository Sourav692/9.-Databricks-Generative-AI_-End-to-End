# Databricks notebook source
# MAGIC %md
# MAGIC # Module 15 lab — Build the Unity Airways semantic layer (metric views)
# MAGIC **Roadmap:** Module 15 (Business Semantics · Unity Catalog metric views) · Topics 15.1–15.7 · ★ 15.3 cornerstone · [Theory + Hands-on]
# MAGIC
# MAGIC This lab builds the **whole P5 semantic layer** end to end: a star schema in `unity_airways.analytics`, one
# MAGIC governed **metric view** `bookings_metrics`, agent metadata for Genie (Module 14), an optional materialization,
# MAGIC and the query patterns from 15.3. It is the trusted KPI source the **Module 14 Genie Agent** queries.
# MAGIC
# MAGIC | Step | Topic | What you do |
# MAGIC |---|---|---|
# MAGIC | 0 | setup | Set catalog/schema variables; create the schema |
# MAGIC | 1 | **15.1 / 15.4** | Seed the star schema (`fct_bookings` + 3 dims) with `COMMENT`s |
# MAGIC | 2 | **15.2 / 15.6** | Create `bookings_metrics` (snowflake join + agent metadata) |
# MAGIC | 3 | **15.2 / 15.7** | Edit the metric view (add a measure); describe + grant |
# MAGIC | 4 | **15.3 ★** | Query it — `MEASURE()`, joins, time, ratios |
# MAGIC | 5 | **15.5** | Materialize a hot slice (optional / experimental) |
# MAGIC
# MAGIC A standalone cornerstone notebook for querying lives in `15-3-query-metric-views.py`.
# MAGIC
# MAGIC ## Prerequisites (read before running)
# MAGIC - **Compute:** a **Pro or Serverless SQL warehouse**, **or** a cluster on **Databricks Runtime 17.2+** (metric-view
# MAGIC   YAML `version: 1.1` needs 17.2+; nested/snowflake joins need 17.1+). Metric views do **not** run on a basic/classic warehouse.
# MAGIC - **Unity Catalog:** the `unity_airways` catalog (shared across the curriculum). You need `CREATE SCHEMA` +
# MAGIC   `CREATE TABLE` in it, and `SELECT` on the source tables. This lab creates schema `analytics`.
# MAGIC - **Secrets / endpoints:** none. Seed data is small, synthetic, and deterministic — safe to re-run.
# MAGIC - **Serverless** must be enabled for the optional materialization step (Step 5).
# MAGIC
# MAGIC > 📌 **The one rule of this module — define each metric once, in YAML, and let every tool re-aggregate it safely.**
# MAGIC > Measures (how to aggregate) live apart from dimensions (how to slice); the grain is a **query-time** choice via
# MAGIC > `MEASURE()`. One definition, many questions, correct ratios at every roll-up.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 0. Set variables and create the schema
# MAGIC The locked P5 names: catalog `unity_airways`, schema `analytics`. All tables and the metric view live here.

# COMMAND ----------

CATALOG = "unity_airways"
SCHEMA  = "analytics"
FQ      = f"{CATALOG}.{SCHEMA}"          # fully-qualified schema prefix

# The catalog is shared across the curriculum and should already exist. If you have privileges and it does not,
# uncomment the next line (needs metastore/catalog CREATE privileges).
# spark.sql(f"CREATE CATALOG IF NOT EXISTS {CATALOG}")

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {FQ} COMMENT 'Unity Airways analytics / semantic layer (P5).'")
spark.sql(f"USE {FQ}")
print("Working in:", FQ)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 1 — Seed the star schema (15.1 / 15.4) · [Hands-on]
# MAGIC One fact + three dimensions. The data is **deterministic** (derived from `range(...)` and `pmod` — no random seed),
# MAGIC so results are reproducible and the module's example numbers are stable. Every table and key column gets a
# MAGIC `COMMENT` — governance, and grounding text the metric view and Genie will read.

# COMMAND ----------

# --- dim_airports: the airport reference (region rolls up from here) ---
spark.sql(f"""
CREATE OR REPLACE TABLE {FQ}.dim_airports (
  airport_code STRING COMMENT 'IATA airport code (primary key)',
  city         STRING COMMENT 'City served by the airport',
  country      STRING COMMENT 'Country of the airport',
  region       STRING COMMENT 'World region: AMER, EMEA, or APAC'
) COMMENT 'Airport dimension for Unity Airways routes.'
""")
spark.sql(f"""
INSERT OVERWRITE {FQ}.dim_airports VALUES
  ('SFO','San Francisco','USA','AMER'),
  ('JFK','New York','USA','AMER'),
  ('LHR','London','UK','EMEA'),
  ('DXB','Dubai','UAE','EMEA'),
  ('NRT','Tokyo','Japan','APAC'),
  ('SIN','Singapore','Singapore','APAC')
""")

# --- dim_flights: one row per scheduled flight (fact joins here on flight_id) ---
spark.sql(f"""
CREATE OR REPLACE TABLE {FQ}.dim_flights (
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
INSERT OVERWRITE {FQ}.dim_flights VALUES
  ('FL001','SFO-JFK','SFO','JFK','A320',2586,TIMESTAMP'2025-03-02 08:00:00', 12),
  ('FL002','JFK-LHR','JFK','LHR','B77W',3451,TIMESTAMP'2025-03-02 21:30:00', 45),
  ('FL003','LHR-DXB','LHR','DXB','A388',3414,TIMESTAMP'2025-03-03 10:15:00',  0),
  ('FL004','DXB-SIN','DXB','SIN','B77W',3630,TIMESTAMP'2025-03-03 23:05:00',  8),
  ('FL005','SIN-NRT','SIN','NRT','A359',3312,TIMESTAMP'2025-03-04 07:40:00', 22),
  ('FL006','NRT-SFO','NRT','SFO','B789',5150,TIMESTAMP'2025-03-04 17:20:00',  5),
  ('FL007','SFO-LHR','SFO','LHR','A359',5367,TIMESTAMP'2025-03-05 13:10:00', 63),
  ('FL008','JFK-DXB','JFK','DXB','B77W',6842,TIMESTAMP'2025-03-05 19:55:00',  0)
""")

# --- dim_customers: the loyalty / segment dimension ---
spark.sql(f"""
CREATE OR REPLACE TABLE {FQ}.dim_customers (
  customer_id  STRING COMMENT 'Customer identifier (primary key)',
  loyalty_tier STRING COMMENT 'Frequent-flyer tier: Blue, Silver, Gold, Platinum',
  home_country STRING COMMENT 'Customer home country',
  segment      STRING COMMENT 'Travel segment: Leisure or Business',
  signup_date  DATE   COMMENT 'Loyalty program signup date'
) COMMENT 'Customer dimension for Unity Airways.'
""")
spark.sql(f"""
INSERT OVERWRITE {FQ}.dim_customers VALUES
  ('CUST01','Platinum','USA','Business', DATE'2019-05-11'),
  ('CUST02','Gold','UK','Leisure',       DATE'2020-02-03'),
  ('CUST03','Silver','Japan','Business', DATE'2021-08-19'),
  ('CUST04','Blue','Singapore','Leisure',DATE'2023-01-27'),
  ('CUST05','Gold','UAE','Business',     DATE'2020-11-30'),
  ('CUST06','Blue','USA','Leisure',      DATE'2022-06-14'),
  ('CUST07','Platinum','UK','Business',  DATE'2018-09-02'),
  ('CUST08','Silver','USA','Leisure',    DATE'2021-03-22'),
  ('CUST09','Gold','Japan','Leisure',    DATE'2022-12-05'),
  ('CUST10','Blue','Singapore','Business',DATE'2023-07-18')
""")

print("Dimensions seeded.")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Seed the fact table
# MAGIC `fct_bookings` — grain = one booking. Rows are generated deterministically from `range(0, 240)` so the data is
# MAGIC reproducible and every `flight_id` / `customer_id` is a valid foreign key. `route_id` is pulled from `dim_flights`
# MAGIC by joining on `flight_id`, so the fact and dimension agree.

# COMMAND ----------

spark.sql(f"""
CREATE OR REPLACE TABLE {FQ}.fct_bookings
COMMENT 'Booking fact for Unity Airways — one row per booking.'
AS
WITH base AS (
  SELECT
    id AS booking_id,
    concat('FL',   lpad(cast(pmod(id, 8)  + 1 AS STRING), 3, '0')) AS flight_id,
    concat('CUST', lpad(cast(pmod(id, 10) + 1 AS STRING), 2, '0')) AS customer_id,
    element_at(array('Economy','Premium','Business','First'),
               cast(pmod(id, 4) + 1 AS INT))                        AS fare_class,
    element_at(array('Direct','OTA','Agent','Mobile'),
               cast(pmod(id * 3, 4) + 1 AS INT))                    AS channel,
    date_add(DATE'2025-01-01', cast(pmod(id * 11, 150) AS INT))     AS booking_date,
    -- base fare: a spread plus a cabin premium, all derived from id (deterministic)
    round(90 + pmod(id * 13, 18) * 22
          + CASE pmod(id, 4) WHEN 0 THEN 0 WHEN 1 THEN 130 WHEN 2 THEN 520 ELSE 1150 END, 2) AS base_fare_usd,
    round(pmod(id * 7, 6) * 24.5, 2)                                AS ancillary_usd,
    cast(pmod(id, 3) + 1 AS INT)                                    AS seats,
    CASE WHEN pmod(id, 17) = 0 THEN 'cancelled'
         WHEN pmod(id, 3)  = 0 THEN 'booked'
         ELSE 'flown' END                                           AS status
  FROM range(0, 240)
)
SELECT
  b.booking_id,
  b.flight_id,
  b.customer_id,
  f.route_id,
  b.booking_date,
  date_add(b.booking_date, cast(14 + pmod(b.booking_id, 30) AS INT)) AS travel_date,
  b.fare_class,
  b.channel,
  b.base_fare_usd,
  b.ancillary_usd,
  b.seats,
  b.status
FROM base b
JOIN {FQ}.dim_flights f USING (flight_id)
""")

print("Fact seeded.")

# COMMAND ----------

# MAGIC %md
# MAGIC #### Verify the seed worked
# MAGIC Row counts, a sample, and a referential-integrity check (every booking's `flight_id` exists in `dim_flights`).

# COMMAND ----------

print("fct_bookings rows :", spark.table(f"{FQ}.fct_bookings").count())   # expect 240
print("dim_flights rows  :", spark.table(f"{FQ}.dim_flights").count())    # expect 8
print("dim_customers rows:", spark.table(f"{FQ}.dim_customers").count())  # expect 10
print("dim_airports rows :", spark.table(f"{FQ}.dim_airports").count())   # expect 6

orphans = spark.sql(f"""
  SELECT count(*) AS orphan_bookings
  FROM {FQ}.fct_bookings b
  LEFT ANTI JOIN {FQ}.dim_flights f USING (flight_id)
""").first()["orphan_bookings"]
print("orphan bookings (should be 0):", orphans)

display(spark.sql(f"SELECT * FROM {FQ}.fct_bookings ORDER BY booking_id LIMIT 8"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 2 — Create the metric view with agent metadata (15.2 / 15.6) · [Hands-on]
# MAGIC One statement, YAML body. Note the shape:
# MAGIC - **`source`** = the fact `fct_bookings`; **`joins`** wire the dimensions (a **snowflake** join reaches
# MAGIC   `dim_airports` *through* `dim_flights` for `Region`).
# MAGIC - **`dimensions`** slice; **`measures`** aggregate. Reference fact columns as `source.<col>` and joined columns as
# MAGIC   `<join_name>.<col>`.
# MAGIC - **Agent metadata (15.6):** business-friendly `name`s (the display names Genie maps questions to) and rich
# MAGIC   `comment`s (meaning, units, **synonyms** as "a.k.a. ...") on the view and every field. This is what makes the
# MAGIC   metric view a trusted Genie source in **Module 14**.
# MAGIC
# MAGIC > ⚠️ **GOTCHA:** the exact YAML keys for a *dedicated* `synonyms:` field and value `format:` are evolving —
# MAGIC > **verify against current docs** before relying on them. Embedding synonyms in `comment` (below) is portable
# MAGIC > and works today.

# COMMAND ----------

spark.sql(f"""
CREATE OR REPLACE VIEW {FQ}.bookings_metrics
WITH METRICS
LANGUAGE YAML
AS $$
  version: 1.1
  comment: "Unity Airways bookings KPIs — the governed semantic layer for revenue analytics. Trusted source for the AI/BI Genie Agent (Module 14). Grain: one booking."
  source: {FQ}.fct_bookings

  joins:
    - name: flights
      source: {FQ}.dim_flights
      on: source.flight_id = flights.flight_id
      joins:
        - name: origin_airport_info
          source: {FQ}.dim_airports
          on: flights.origin_airport = origin_airport_info.airport_code
    - name: customers
      source: {FQ}.dim_customers
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
      comment: "Share of bookings cancelled (0-1). Also known as: cancel rate, cancellation percentage."
    - name: Ancillary Attach Rate
      expr: SUM(source.ancillary_usd) / SUM(source.base_fare_usd)
      comment: "Ancillary revenue as a fraction of base fare. Also known as: attach rate, ancillary ratio."
    - name: Total Seats
      expr: SUM(source.seats)
      comment: "Total seats booked."
$$
""")

print("Metric view created:", f"{FQ}.bookings_metrics")

# COMMAND ----------

# MAGIC %md
# MAGIC #### Verify the metric view works
# MAGIC A one-line `MEASURE()` query should return rows. Remember: **`SELECT *` is not supported** — name the dimension
# MAGIC and wrap the measure in `MEASURE()`.

# COMMAND ----------

display(spark.sql(f"""
  SELECT `Fare Class`,
         MEASURE(`Total Revenue`) AS total_revenue,
         MEASURE(`Booking Count`) AS bookings
  FROM {FQ}.bookings_metrics
  GROUP BY ALL
  ORDER BY total_revenue DESC
"""))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 3 — Edit the metric view; describe and grant (15.2 / 15.7) · [Hands-on]
# MAGIC **Editing = re-issue `CREATE OR REPLACE VIEW`** with the new YAML (or edit visually in Catalog Explorer). There is
# MAGIC no partial in-place patch in SQL. Here we add one filtered measure, **`Cancelled Bookings`**, keeping everything
# MAGIC else. (For brevity we ALTER by re-declaring; in a real repo the full YAML lives in a version-controlled `.sql` file.)

# COMMAND ----------

# Add a filtered measure by appending to the definition. We rebuild from the existing YAML plus one measure.
# (Shown compactly; in practice keep the whole YAML in source control and edit there.)
spark.sql(f"""
CREATE OR REPLACE VIEW {FQ}.bookings_metrics
WITH METRICS
LANGUAGE YAML
AS $$
  version: 1.1
  comment: "Unity Airways bookings KPIs — governed semantic layer. Trusted Genie source (Module 14). Grain: one booking."
  source: {FQ}.fct_bookings
  joins:
    - name: flights
      source: {FQ}.dim_flights
      on: source.flight_id = flights.flight_id
      joins:
        - name: origin_airport_info
          source: {FQ}.dim_airports
          on: flights.origin_airport = origin_airport_info.airport_code
    - name: customers
      source: {FQ}.dim_customers
      on: source.customer_id = customers.customer_id
  dimensions:
    - name: Fare Class
      expr: source.fare_class
      comment: "Cabin / booking class. Also known as: cabin, class."
    - name: Channel
      expr: source.channel
      comment: "Booking channel: Direct, OTA, Agent, Mobile."
    - name: Loyalty Tier
      expr: customers.loyalty_tier
      comment: "Frequent-flyer tier: Blue, Silver, Gold, Platinum."
    - name: Segment
      expr: customers.segment
      comment: "Travel segment: Leisure or Business."
    - name: Origin Airport
      expr: flights.origin_airport
      comment: "IATA code of departure airport."
    - name: Dest Airport
      expr: flights.dest_airport
      comment: "IATA code of arrival airport."
    - name: Region
      expr: origin_airport_info.region
      comment: "World region of the origin airport: AMER, EMEA, APAC."
    - name: Booking Month
      expr: DATE_TRUNC('MONTH', source.booking_date)
      comment: "Calendar month of booking."
    - name: Booking Quarter
      expr: DATE_TRUNC('QUARTER', source.booking_date)
      comment: "Calendar quarter of booking."
  measures:
    - name: Total Revenue
      expr: SUM(source.base_fare_usd + source.ancillary_usd)
      comment: "Base + ancillary revenue, USD. Also known as: revenue, sales."
    - name: Booking Count
      expr: COUNT(source.booking_id)
      comment: "Number of bookings."
    - name: Avg Fare
      expr: AVG(source.base_fare_usd)
      comment: "Average base fare per booking, USD."
    - name: Cancellation Rate
      expr: COUNT(1) FILTER (WHERE source.status = 'cancelled') * 1.0 / COUNT(1)
      comment: "Share of bookings cancelled (0-1). Also known as: cancel rate."
    - name: Ancillary Attach Rate
      expr: SUM(source.ancillary_usd) / SUM(source.base_fare_usd)
      comment: "Ancillary revenue / base fare. Also known as: attach rate."
    - name: Total Seats
      expr: SUM(source.seats)
      comment: "Total seats booked."
    - name: Cancelled Bookings
      expr: COUNT(1) FILTER (WHERE source.status = 'cancelled')
      comment: "Count of cancelled bookings (the numerator behind Cancellation Rate)."
$$
""")
print("Metric view edited — added 'Cancelled Bookings'.")

# COMMAND ----------

# DESCRIBE shows it as a view with its columns (dimensions + measures). GRANT makes it consumable by an analyst group.
display(spark.sql(f"DESCRIBE EXTENDED {FQ}.bookings_metrics"))

# Grant read access to a consumer group (edit the principal to a group that exists in your workspace).
# spark.sql(f"GRANT SELECT ON VIEW {FQ}.bookings_metrics TO `data-consumers`")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 4 — Query the metric view (15.3 ★) · [Hands-on]
# MAGIC The full cornerstone tutorial is in `15-3-query-metric-views.py`. A few highlights here — each maps to a Module 14
# MAGIC Genie question. **Joins are invisible:** we ask for `Region` and `Loyalty Tier` with no JOIN in the SELECT.

# COMMAND ----------

# (a) Revenue + cancellation rate by region and loyalty tier — dimensions from JOINED tables, no JOIN written.
display(spark.sql(f"""
  SELECT `Region`, `Loyalty Tier`,
         MEASURE(`Total Revenue`)     AS revenue,
         MEASURE(`Cancellation Rate`) AS cancel_rate
  FROM {FQ}.bookings_metrics
  GROUP BY ALL
  ORDER BY revenue DESC
"""))

# COMMAND ----------

# (b) "Total revenue last quarter by fare class" — filter on the Booking Quarter dimension.
display(spark.sql(f"""
  SELECT `Fare Class`, MEASURE(`Total Revenue`) AS revenue
  FROM {FQ}.bookings_metrics
  WHERE `Booking Quarter` = DATE'2025-04-01'   -- Q2 2025 (DATE_TRUNC('QUARTER', booking_date))
  GROUP BY ALL
  ORDER BY revenue DESC
"""))

# COMMAND ----------

# (c) "Which routes have the highest cancellation rate" — filter ON a measure via an OUTER query on the alias.
display(spark.sql(f"""
  SELECT * FROM (
    SELECT `Origin Airport`, `Dest Airport`,
           MEASURE(`Cancellation Rate`) AS cancel_rate,
           MEASURE(`Booking Count`)     AS bookings
    FROM {FQ}.bookings_metrics
    GROUP BY ALL
  )
  WHERE bookings >= 5
  ORDER BY cancel_rate DESC
  LIMIT 10
"""))

# COMMAND ----------

# (d) "Compare ancillary attach rate across loyalty tiers"
display(spark.sql(f"""
  SELECT `Loyalty Tier`,
         MEASURE(`Ancillary Attach Rate`) AS attach_rate,
         MEASURE(`Total Revenue`)         AS revenue
  FROM {FQ}.bookings_metrics
  GROUP BY ALL
  ORDER BY attach_rate DESC
"""))

# COMMAND ----------

# MAGIC %md
# MAGIC #### Verify ratios re-aggregate correctly
# MAGIC The grand-total cancellation rate (no dimension) must equal `Cancelled Bookings / Booking Count`. If it does, the
# MAGIC ratio measure is recomputing its numerator and denominator at each grain — the whole point of a metric view.

# COMMAND ----------

display(spark.sql(f"""
  SELECT MEASURE(`Cancellation Rate`)                                   AS cancel_rate,
         MEASURE(`Cancelled Bookings`) * 1.0 / MEASURE(`Booking Count`) AS recomputed,
         MEASURE(`Booking Count`)                                       AS bookings
  FROM {FQ}.bookings_metrics
  GROUP BY ALL
"""))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 5 — Materialize a hot slice (15.5) · [Hands-on] · *(experimental, optional)*
# MAGIC Materialization pre-computes chosen dimension/measure combos on a schedule (via Lakeflow / Spark Declarative
# MAGIC Pipelines) so hot queries hit a cached table. It is a **performance** choice — the metric definition and query
# MAGIC grammar are unchanged. **Requires serverless compute + DBR 17.2+**; `TRIGGER ON UPDATE` is not supported.
# MAGIC
# MAGIC > 💡 **TIP:** Don't materialize first. Ship the view, watch which slices are hot, then materialize *those*.
# MAGIC > Materializing everything re-creates the summary-table sprawl the metric view was meant to replace.
# MAGIC
# MAGIC The YAML below adds a `materialization:` block to the view. Run the cell **only if serverless is enabled** in your
# MAGIC workspace; otherwise read it as the pattern. It is commented out by default so the lab runs anywhere.

# COMMAND ----------

# --- OPTIONAL: uncomment to enable materialization (needs serverless + DBR 17.2+) ---
# spark.sql(f"""
# CREATE OR REPLACE VIEW {FQ}.bookings_metrics
# WITH METRICS
# LANGUAGE YAML
# AS $$
#   version: 1.1
#   comment: "Unity Airways bookings KPIs (materialized hot slice)."
#   source: {FQ}.fct_bookings
#   joins:
#     - name: flights
#       source: {FQ}.dim_flights
#       on: source.flight_id = flights.flight_id
#       joins:
#         - name: origin_airport_info
#           source: {FQ}.dim_airports
#           on: flights.origin_airport = origin_airport_info.airport_code
#     - name: customers
#       source: {FQ}.dim_customers
#       on: source.customer_id = customers.customer_id
#   dimensions:
#     - name: Fare Class
#       expr: source.fare_class
#     - name: Region
#       expr: origin_airport_info.region
#     - name: Booking Month
#       expr: DATE_TRUNC('MONTH', source.booking_date)
#   measures:
#     - name: Total Revenue
#       expr: SUM(source.base_fare_usd + source.ancillary_usd)
#     - name: Booking Count
#       expr: COUNT(source.booking_id)
#   materialization:
#     schedule: every 6 hours
#     mode: relaxed
#     materialized_views:
#       - name: revenue_by_month_class_region
#         type: aggregated
#         dimensions: [Booking Month, Fare Class, Region]
#         measures:   [Total Revenue, Booking Count]
# $$
# """)
# print("Materialization configured — a Lakeflow pipeline now maintains the aggregated slice.")

print("Step 5 is optional — enable it only if serverless materialization is available in your workspace.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Recap, gotchas, and next steps
# MAGIC **What you built**
# MAGIC - A star schema in `unity_airways.analytics` (`fct_bookings` + `dim_flights` / `dim_customers` / `dim_airports`).
# MAGIC - One governed metric view `bookings_metrics` with a snowflake join, six+ measures, and **agent metadata** (names + comments) for Genie.
# MAGIC - Query patterns proving aggregation happens at **query time** and ratios re-aggregate correctly.
# MAGIC
# MAGIC **Gotchas to remember**
# MAGIC - `SELECT *` and bare measure references fail — always `MEASURE()` + `GROUP BY ALL`.
# MAGIC - Backtick-quote names with spaces (`` `Fare Class` ``); put JOINs in the YAML, never in the query.
# MAGIC - Dimensions can't aggregate; measures must. Metric views need a **Pro/Serverless SQL warehouse** (or DBR 17.2+); nested joins need 17.1+.
# MAGIC - Synonyms live in `comment` today; verify any dedicated `synonyms`/`format` YAML key against current docs.
# MAGIC
# MAGIC **Optional cleanup** (uncomment to remove everything this lab created):

# COMMAND ----------

# spark.sql(f"DROP VIEW  IF EXISTS {FQ}.bookings_metrics")
# spark.sql(f"DROP TABLE IF EXISTS {FQ}.fct_bookings")
# spark.sql(f"DROP TABLE IF EXISTS {FQ}.dim_flights")
# spark.sql(f"DROP TABLE IF EXISTS {FQ}.dim_customers")
# spark.sql(f"DROP TABLE IF EXISTS {FQ}.dim_airports")
print("Cleanup is commented out — Module 14 (Genie) reuses these objects.")

# COMMAND ----------

# MAGIC %md
# MAGIC **Next stop:** the cornerstone query notebook `15-3-query-metric-views.py`, then **Module 14 — AI/BI Genie**, where
# MAGIC this metric view becomes the Genie Agent's trusted data source (15.6 → 14). After Genie, **Module 16 — Cost,
# MAGIC performance and scaling**.
