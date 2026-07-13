# Databricks notebook source
# MAGIC %md
# MAGIC # 15.3 ★ — Querying metric views: a joins tutorial
# MAGIC **Roadmap:** Module 15 · Topic 15.3 (cornerstone) · [Hands-on]
# MAGIC
# MAGIC This is the query half of Module 15. It assumes the metric view `unity_airways.analytics.bookings_metrics` already
# MAGIC exists — build it first with **`15-module-lab.py`** (Steps 1–2). Here we drill into the **query grammar**:
# MAGIC `MEASURE()`, `GROUP BY ALL`, time dimensions, star/snowflake **joins** (pulling dimensions from joined tables with
# MAGIC no JOIN in the SELECT), filtering on a measure, and consuming results in BI / Genie.
# MAGIC
# MAGIC ## Prerequisites (read before running)
# MAGIC - **Compute:** a **Pro or Serverless SQL warehouse**, or a cluster on **DBR 17.2+** (nested joins need 17.1+).
# MAGIC - **Unity Catalog:** the metric view `unity_airways.analytics.bookings_metrics` and its source star schema
# MAGIC   (run `15-module-lab.py` first). You need `SELECT` on the view.
# MAGIC - No secrets or endpoints.
# MAGIC
# MAGIC > 📌 **The two rules of querying a metric view:** (1) **name the dimensions** you want; (2) **wrap every measure in
# MAGIC > `MEASURE()`**. `SELECT *` and bare measure references are **not** supported — a measure has no value until you
# MAGIC > pick a grain with `GROUP BY ALL`.

# COMMAND ----------

CATALOG = "unity_airways"
SCHEMA  = "analytics"
MV      = f"{CATALOG}.{SCHEMA}.bookings_metrics"

# Guard: make sure the metric view exists before we query it.
exists = spark.sql(f"SHOW VIEWS IN {CATALOG}.{SCHEMA} LIKE 'bookings_metrics'").count() > 0
assert exists, f"{MV} not found — run 15-module-lab.py (Steps 1-2) first to build it."
print("Querying metric view:", MV)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Walkthrough 1 — the simplest query
# MAGIC Revenue and volume by fare class. `GROUP BY ALL` groups by every non-measure column selected (here, `Fare Class`).

# COMMAND ----------

display(spark.sql(f"""
  SELECT
    `Fare Class`,
    MEASURE(`Total Revenue`) AS total_revenue,
    MEASURE(`Booking Count`) AS bookings
  FROM {MV}
  GROUP BY ALL
  ORDER BY total_revenue DESC
"""))

# COMMAND ----------

# MAGIC %md
# MAGIC #### Verify re-aggregation
# MAGIC The sum of per-fare-class revenue must equal the grand total (same query, no dimension). Equal totals prove the
# MAGIC measure re-aggregates at whatever grain you ask for.

# COMMAND ----------

by_class = spark.sql(f"SELECT `Fare Class`, MEASURE(`Total Revenue`) AS r FROM {MV} GROUP BY ALL")
grand    = spark.sql(f"SELECT MEASURE(`Total Revenue`) AS r FROM {MV} GROUP BY ALL").first()["r"]
summed   = by_class.groupBy().sum("r").first()[0]
print(f"sum of class-level revenue = {summed:.2f}")
print(f"grand total revenue        = {grand:.2f}")
print("match:", round(summed, 2) == round(grand, 2))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Walkthrough 2 — time dimensions
# MAGIC `Booking Month` and `Booking Quarter` are `DATE_TRUNC` dimensions in the YAML, so a trend needs no date math in the
# MAGIC query. Filter the **dimension** in `WHERE` to scope a range.

# COMMAND ----------

# Monthly revenue trend for 2025
display(spark.sql(f"""
  SELECT
    `Booking Month`,
    MEASURE(`Total Revenue`) AS revenue,
    MEASURE(`Booking Count`) AS bookings
  FROM {MV}
  WHERE `Booking Month` >= DATE'2025-01-01'
  GROUP BY ALL
  ORDER BY `Booking Month`
"""))

# COMMAND ----------

# "Total revenue last quarter by fare class" (a Module 14 Genie question)
display(spark.sql(f"""
  SELECT `Fare Class`, MEASURE(`Total Revenue`) AS revenue
  FROM {MV}
  WHERE `Booking Quarter` = DATE'2025-04-01'   -- start of Q2 2025
  GROUP BY ALL
  ORDER BY revenue DESC
"""))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Walkthrough 3 — the joins tutorial (the cornerstone)
# MAGIC `Loyalty Tier` comes from `dim_customers`; `Region` comes from `dim_airports` reached **through** `dim_flights`
# MAGIC (a snowflake join). To the query they are just dimension names — **no JOIN is written**. The YAML resolves the path.

# COMMAND ----------

# Revenue + cancellation rate by region and loyalty tier
display(spark.sql(f"""
  SELECT
    `Region`,
    `Loyalty Tier`,
    MEASURE(`Total Revenue`)     AS revenue,
    MEASURE(`Cancellation Rate`) AS cancel_rate
  FROM {MV}
  GROUP BY ALL
  ORDER BY revenue DESC
"""))

# COMMAND ----------

# MAGIC %md
# MAGIC #### Verify the joins resolved
# MAGIC Every row should have a non-null `Region` and `Loyalty Tier`, and `cancel_rate` between 0 and 1. A null `Region`
# MAGIC means the airport snowflake key is off; an error on `Region` means you are below DBR 17.1 (nested joins) / 17.2 (v1.1).

# COMMAND ----------

check = spark.sql(f"""
  SELECT count(*)                                                     AS rows,
         sum(CASE WHEN `Region` IS NULL THEN 1 ELSE 0 END)            AS null_region,
         min(MEASURE(`Cancellation Rate`))                           AS min_cr,
         max(MEASURE(`Cancellation Rate`))                           AS max_cr
  FROM (
    SELECT `Region`, `Loyalty Tier`, MEASURE(`Cancellation Rate`) AS cr
    FROM {MV} GROUP BY ALL
  )
""").first()
print(check)
print("null regions (should be 0):", check["null_region"])

# COMMAND ----------

# MAGIC %md
# MAGIC ### "Which routes have the highest cancellation rate?"
# MAGIC Group by origin + destination (both from `dim_flights`). To keep low-volume routes off the top on noise, filter on
# MAGIC the measure — which you cannot do in `WHERE`. Wrap the aggregate query and filter the **alias** in an outer `SELECT`.

# COMMAND ----------

display(spark.sql(f"""
  SELECT * FROM (
    SELECT `Origin Airport`, `Dest Airport`,
           MEASURE(`Cancellation Rate`) AS cancel_rate,
           MEASURE(`Booking Count`)     AS bookings
    FROM {MV}
    GROUP BY ALL
  )
  WHERE bookings >= 5          -- filter ON a measure: outer query on the alias
  ORDER BY cancel_rate DESC
  LIMIT 10
"""))

# COMMAND ----------

# MAGIC %md
# MAGIC ### "Compare ancillary attach rate across loyalty tiers"
# MAGIC A ratio measure (`SUM(ancillary)/SUM(base_fare)`) recomputed per tier — the third Module 14 Genie question.

# COMMAND ----------

display(spark.sql(f"""
  SELECT
    `Loyalty Tier`,
    MEASURE(`Ancillary Attach Rate`) AS attach_rate,
    MEASURE(`Total Revenue`)         AS revenue
  FROM {MV}
  GROUP BY ALL
  ORDER BY attach_rate DESC
"""))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Walkthrough 4 — consuming results (BI, alerts, Genie)
# MAGIC The point of the grammar is that every surface uses it, so the numbers agree:
# MAGIC - **SQL Editor / notebooks:** run the queries above (`spark.sql(...)` returns a DataFrame you `display()`).
# MAGIC - **AI/BI dashboards:** add the metric view as a **dataset**; the visual builder emits `MEASURE()` SQL for you.
# MAGIC - **Alerts:** set a threshold on a measure (e.g. weekly `Cancellation Rate` per region > 5%).
# MAGIC - **Genie Agent (Module 14):** add the metric view as a source; "revenue by fare class" is translated into the same
# MAGIC   `MEASURE(Total Revenue) ... GROUP BY Fare Class` — governed, and matching the dashboard.
# MAGIC
# MAGIC **Prove they agree:** run Walkthrough 1 here, chart the same breakdown on a dashboard, and ask Genie the same
# MAGIC question. Identical numbers is the demo that sells the semantic layer. A mismatch means something bypassed the view.

# COMMAND ----------

# The exact SQL a BI tool or Genie would generate for "revenue and cancellation rate by fare class":
sql = f"""
  SELECT `Fare Class`,
         MEASURE(`Total Revenue`)     AS revenue,
         MEASURE(`Cancellation Rate`) AS cancel_rate
  FROM {MV}
  GROUP BY ALL
  ORDER BY revenue DESC
"""
print(sql)
display(spark.sql(sql))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Recap
# MAGIC - **Two rules:** name the dimensions, `MEASURE()` the measures — `SELECT *` never works.
# MAGIC - **Joins are the view's job:** naming `Region` / `Loyalty Tier` is enough; the YAML resolves the star/snowflake path.
# MAGIC - **Ratios are correct at any grain** because they are measures — never average a ratio across groups by hand.
# MAGIC - **Filter a measure** in an outer query on the alias, not in `WHERE`.
# MAGIC
# MAGIC **Next stop:** **Module 14 — AI/BI Genie**, where `bookings_metrics` becomes the Genie Agent's trusted data source.
