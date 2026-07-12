# Databricks notebook source
# MAGIC %md
# MAGIC # {{TOPIC_TITLE}}
# MAGIC **Roadmap:** Module {{NN}} · Topic {{X.Y}}
# MAGIC
# MAGIC ## The problem
# MAGIC {{real-world pain this notebook solves}}
# MAGIC
# MAGIC ## What you will build
# MAGIC - {{artifact / workflow}}
# MAGIC - {{verification signal}}
# MAGIC
# MAGIC ### Prerequisites
# MAGIC - Compute: {{serverless | ML runtime version}}
# MAGIC - Libraries: {{mlflow>=3.x, langchain, databricks-vectorsearch, ...}}
# MAGIC - Unity Catalog: catalog/schema = `{{catalog}}.{{schema}}`
# MAGIC - Serving endpoints / secrets: {{list}}

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Setup
# MAGIC Keep setup small and explicit. The goal is to make the later GenAI behavior easy to inspect.

# COMMAND ----------

# %pip install -U mlflow databricks-vectorsearch  # uncomment as needed
# dbutils.library.restartPython()

# COMMAND ----------

CATALOG = "{{catalog}}"
SCHEMA = "{{schema}}"
spark.sql(f"USE CATALOG {CATALOG}")
spark.sql(f"USE SCHEMA {SCHEMA}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. The core idea
# MAGIC {{plain-language concept explanation}}

# COMMAND ----------

# {{runnable, commented code}}

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Run it
# MAGIC Execute the smallest useful version first. Then inspect the result before adding more moving parts.

# COMMAND ----------

# {{focused implementation cell}}

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Verify it worked
# MAGIC - {{trace / table / endpoint / metric / response to check}}
# MAGIC - {{expected signal}}

# COMMAND ----------

# {{verification code or SQL}}

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Recap & next steps
# MAGIC - {{what we built}}
# MAGIC - {{gotcha to remember}}
# MAGIC - Next roadmap topic: {{X.Y+1}}
