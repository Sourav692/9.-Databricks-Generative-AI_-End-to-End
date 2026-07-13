# Databricks notebook source
# MAGIC %md
# MAGIC # Module 00 Lab — Platform Foundations for GenAI
# MAGIC **Roadmap:** Module 00 · Topics 00.1, 00.2, 00.3, 00.6 (hands-on)
# MAGIC
# MAGIC ## The problem
# MAGIC Before any RAG, agent, or evaluation work, you need a governed footprint: a workspace you can
# MAGIC run code in, Unity Catalog objects (a catalog, a schema, a **volume** for files, a Delta table),
# MAGIC and a way to pull in ready-made data via **Databricks Marketplace**. This lab stands that up.
# MAGIC
# MAGIC ## What you will build
# MAGIC - A verified compute + notebook environment (00.1 / 00.3).
# MAGIC - Unity Catalog objects for the **Unity Airways** use case: a schema, a **managed volume**
# MAGIC   (`faq_docs`) for RAG PDFs, and a `bookings` Delta table (00.2).
# MAGIC - A Marketplace walkthrough to attach a public dataset (e.g. NOAA / weather) as a read-only
# MAGIC   catalog and query it (00.6).
# MAGIC - A "how to verify it worked" check after every step.
# MAGIC
# MAGIC ### Prerequisites
# MAGIC - **Compute:** Serverless is fine (recommended). A classic **ML runtime** cluster also works.
# MAGIC - **Workspace:** Unity Catalog enabled (Premium tier or above). No extra libraries required.
# MAGIC - **Unity Catalog privileges:** `USE CATALOG` on the target catalog and `CREATE SCHEMA` /
# MAGIC   `CREATE VOLUME` / `CREATE TABLE` within it. If you cannot create a catalog, point `CATALOG`
# MAGIC   at one you already have (for example your personal or workspace catalog).
# MAGIC - **Marketplace (00.6):** access to Databricks Marketplace in the workspace sidebar.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Setup — name your governed objects
# MAGIC Keep setup small and explicit. We use the three-level namespace `catalog.schema.object` for
# MAGIC everything. Change `CATALOG` to a catalog you have privileges on.

# COMMAND ----------

CATALOG = "main"          # <-- change to a catalog you can write to
SCHEMA  = "airways"       # Unity Airways use-case schema
VOLUME  = "faq_docs"      # managed volume for unstructured RAG source files
TABLE   = "bookings"      # structured booking records (Delta)

print(f"Target namespace: {CATALOG}.{SCHEMA}")
print(f"  volume: {CATALOG}.{SCHEMA}.{VOLUME}")
print(f"  table : {CATALOG}.{SCHEMA}.{TABLE}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Verify the environment (00.1 / 00.3)
# MAGIC The book's Step 13 check, plus a couple of signals that confirm compute + Unity Catalog are live.

# COMMAND ----------

# The book's environment_check (Ch1, Step 13)
print("Databricks environment is ready")

# Extra signals: who am I, and what Spark/compute am I on?
print("Current user :", spark.sql("SELECT current_user()").first()[0])
print("Spark version:", spark.version)

# COMMAND ----------

# MAGIC %md
# MAGIC **How to verify it worked**
# MAGIC - The message prints with no error and you see your username + a Spark version.
# MAGIC - If a cell hangs, confirm the notebook is attached to **running** compute (top-right selector).

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Create Unity Catalog objects (00.2)
# MAGIC The core idea: tables, **volumes**, functions, models, and vector indexes all live at
# MAGIC `catalog.schema.object` and inherit UC permissions, lineage, and audit.
# MAGIC
# MAGIC > If `CREATE CATALOG` fails on privileges, skip it and set `CATALOG` (cell 1) to an existing catalog.

# COMMAND ----------

# Catalog is optional to create — comment out if you lack the privilege and reuse an existing catalog.
spark.sql(f"CREATE CATALOG IF NOT EXISTS {CATALOG}")

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")
spark.sql(f"USE CATALOG {CATALOG}")
spark.sql(f"USE SCHEMA {SCHEMA}")

# A managed VOLUME governs non-tabular files (PDFs, images, JSON) for RAG.
spark.sql(f"CREATE VOLUME IF NOT EXISTS {CATALOG}.{SCHEMA}.{VOLUME}")

print("Schema and volume ready.")

# COMMAND ----------

# MAGIC %md
# MAGIC **How to verify it worked** — the schema and volume show up in Unity Catalog.

# COMMAND ----------

display(spark.sql(f"SHOW VOLUMES IN {CATALOG}.{SCHEMA}"))

# COMMAND ----------

# MAGIC %md
# MAGIC ### 3a. Write a file into the volume
# MAGIC Volumes are reachable at the path `/Volumes/<catalog>/<schema>/<volume>/...`. This is where a
# MAGIC customer's FAQ PDFs would land before chunking (Module 03). Here we drop a small text FAQ.

# COMMAND ----------

volume_path = f"/Volumes/{CATALOG}/{SCHEMA}/{VOLUME}"
faq_file = f"{volume_path}/policy_faq.txt"

faq_text = (
    "Q: Can I change my flight to a later date?\n"
    "A: Yes. Change fees depend on your fare class; refundable fares change free of charge.\n\n"
    "Q: What is the checked-baggage allowance?\n"
    "A: One checked bag up to 23 kg is included on standard economy fares.\n"
)

# Volumes support standard Python file IO on the /Volumes path.
with open(faq_file, "w") as f:
    f.write(faq_text)

print("Wrote:", faq_file)

# COMMAND ----------

# MAGIC %md
# MAGIC **How to verify it worked** — the file is listed in the volume and reads back.

# COMMAND ----------

display(dbutils.fs.ls(volume_path))
print(open(faq_file).read())

# COMMAND ----------

# MAGIC %md
# MAGIC ### 3b. Create the structured `bookings` Delta table
# MAGIC The Unity Airways use case pairs unstructured FAQ files (above) with structured booking records.
# MAGIC Columns mirror the book's Table 1-1 (`booking_id`, `pnr`, `status`, travel dates).

# COMMAND ----------

spark.sql(f"""
CREATE TABLE IF NOT EXISTS {CATALOG}.{SCHEMA}.{TABLE} (
  booking_id        STRING,
  pnr               STRING,
  status            STRING,           -- e.g. TICKETED / REFUNDED
  travel_start_date DATE,
  travel_end_date   DATE
) USING DELTA
""")

spark.sql(f"""
INSERT INTO {CATALOG}.{SCHEMA}.{TABLE} VALUES
  ('BK1001', 'PNRAAA', 'TICKETED', DATE'2026-08-01', DATE'2026-08-10'),
  ('BK1002', 'PNRBBB', 'REFUNDED', DATE'2026-07-15', DATE'2026-07-20')
""")

print("bookings table populated.")

# COMMAND ----------

# MAGIC %md
# MAGIC **How to verify it worked** — the query returns the two rows via the three-level namespace.

# COMMAND ----------

display(spark.sql(f"SELECT * FROM {CATALOG}.{SCHEMA}.{TABLE}"))

# COMMAND ----------

# MAGIC %md
# MAGIC ### 3c. Governance in one line (RBAC)
# MAGIC UC governs who can see or use each object. This grant lets a group read files in the volume.
# MAGIC It is commented out because it needs a **real group name** you can grant to.

# COMMAND ----------

# Replace `data-scientists` with a group that exists in your account, then run.
# spark.sql(f"GRANT READ VOLUME ON VOLUME {CATALOG}.{SCHEMA}.{VOLUME} TO `data-scientists`")
# spark.sql(f"GRANT SELECT ON TABLE {CATALOG}.{SCHEMA}.{TABLE} TO `data-scientists`")
print("Governance grants are illustrative — uncomment with a real group to apply.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Discover data via Databricks Marketplace (00.6)
# MAGIC Marketplace is an open exchange built on **Delta Sharing**. A listing installs as a **read-only
# MAGIC catalog** — no ingestion pipeline. Do this part in the UI, then run the query cell below.
# MAGIC
# MAGIC **UI steps (verified in docs):**
# MAGIC 1. Sidebar **Marketplace** (or `marketplace.databricks.com`).
# MAGIC 2. Filter for **Free** / **Instantly available**; search e.g. *NOAA* or *weather*.
# MAGIC 3. Open the listing → **Get instant access** → accept terms. Under **More options** you can
# MAGIC    rename the catalog it installs into (note that name).
# MAGIC 4. **Get instant access** again → **Open**. The data appears as a read-only catalog in
# MAGIC    **Catalog Explorer**.
# MAGIC 5. Query it with the three-part namespace `catalog.schema.table|volume|view`.
# MAGIC
# MAGIC > ⚠️ Exact listing and catalog/schema/table names vary by provider and region — confirm them in
# MAGIC > the live Marketplace. The names below are placeholders.

# COMMAND ----------

# See which catalogs you can reach (a newly installed Marketplace catalog should appear here).
display(spark.sql("SHOW CATALOGS"))

# COMMAND ----------

# After installing a Marketplace listing, set these to the actual names it created, then run.
MKT_CATALOG = "weather_data"   # <-- replace with your installed Marketplace catalog
MKT_SCHEMA  = "noaa"           # <-- replace with the actual schema
MKT_TABLE   = "daily_summaries"  # <-- replace with the actual table

try:
    display(spark.sql(f"SELECT * FROM {MKT_CATALOG}.{MKT_SCHEMA}.{MKT_TABLE} LIMIT 10"))
except Exception as e:
    print("Install a Marketplace listing first, then update MKT_CATALOG/SCHEMA/TABLE above.")
    print("Details:", str(e).splitlines()[0])

# COMMAND ----------

# MAGIC %md
# MAGIC **How to verify it worked** — the installed catalog shows in `SHOW CATALOGS` / Catalog Explorer,
# MAGIC and the `SELECT` returns rows. Because it is shared read-only, you cannot write to it.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Recap, gotchas, cleanup & next steps
# MAGIC **What we built**
# MAGIC - Verified compute + notebook (00.1 / 00.3).
# MAGIC - UC objects at `catalog.schema.object`: a schema, a **managed volume** with an FAQ file, and a
# MAGIC   `bookings` Delta table (00.2) — the Unity Airways footprint.
# MAGIC - Walked the Marketplace **Get instant access** flow to attach public data read-only (00.6).
# MAGIC
# MAGIC **Gotchas to remember**
# MAGIC - `CREATE CATALOG` needs metastore privileges; reuse an existing catalog if it fails.
# MAGIC - Put RAG files in a **volume**, not DBFS root — governance, lineage, and audit come for free.
# MAGIC - Marketplace data is **shared read-only** via Delta Sharing; you query it in place.
# MAGIC - Product names churn — "Vector Search" is surfaced as **AI Search** (SDK still
# MAGIC   `databricks-vectorsearch`). Verify live names before quoting them.
# MAGIC
# MAGIC **Optional cleanup** (uncomment to remove what this lab created):

# COMMAND ----------

# spark.sql(f"DROP TABLE IF EXISTS {CATALOG}.{SCHEMA}.{TABLE}")
# spark.sql(f"DROP VOLUME IF EXISTS {CATALOG}.{SCHEMA}.{VOLUME}")
# spark.sql(f"DROP SCHEMA IF EXISTS {CATALOG}.{SCHEMA}")
print("Uncomment the DROP statements above to clean up.")

# COMMAND ----------

# MAGIC %md
# MAGIC **Next roadmap topic:** Module 01 — GenAI & LLM fundamentals (01.1 What is Generative AI vs
# MAGIC traditional ML). You now have the governed workspace + Unity Catalog footprint the rest of the
# MAGIC roadmap builds on.
