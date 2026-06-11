# Databricks notebook source
# MAGIC %md
# MAGIC # {{TOPIC_TITLE}}
# MAGIC **Roadmap:** Module {{NN}} · Topic {{X.Y}}
# MAGIC
# MAGIC ### Prerequisites
# MAGIC - Compute: {{serverless | ML runtime version}}
# MAGIC - Libraries: {{mlflow>=3.x, langchain, databricks-vectorsearch, ...}}
# MAGIC - Unity Catalog: catalog/schema = `{{catalog}}.{{schema}}`
# MAGIC - Serving endpoints / secrets: {{list}}

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Setup

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
# MAGIC ## 2. {{Section}}

# COMMAND ----------

# {{runnable, commented code}}

# COMMAND ----------

# MAGIC %md
# MAGIC ## Recap & next steps
# MAGIC - {{what we built}}
# MAGIC - Next roadmap topic: {{X.Y+1}}
