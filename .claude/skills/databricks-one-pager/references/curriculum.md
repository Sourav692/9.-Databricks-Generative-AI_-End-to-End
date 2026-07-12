# One-Pager Curriculum — candidate features

The authoritative backlog lives in `one-pagers/goal.md` (status-tracked). This
file is the **reference menu**: category, slug, and the doc pages to ground each
one in. `goal.md` decides which are in scope and their order.

Ground every page by fetching `https://docs.databricks.com/llms.txt` first, then
the specific pages below (paths are relative to `https://docs.databricks.com/`).

## Core platform (recommended interview set)

| # | Feature | slug | Ground in |
|---|---------|------|-----------|
| 01 | Lakehouse & Medallion architecture | `lakehouse-medallion` | `/lakehouse/medallion.html`, `/lakehouse/index.html` |
| 02 | Unity Catalog | `unity-catalog` | `/data-governance/unity-catalog/index.html` |
| 03 | Delta Lake (ACID, log, time travel) | `delta-lake` | `/delta/index.html`, `/delta/history.html` |
| 04 | Auto Loader | `auto-loader` | `/ingestion/cloud-object-storage/auto-loader/index.html` |
| 05 | Lakeflow Declarative Pipelines (DLT) | `lakeflow-declarative-pipelines` | `/dlt/index.html` |
| 06 | Lakeflow Jobs (Workflows) | `lakeflow-jobs` | `/jobs/index.html` |
| 07 | Spark architecture & execution | `spark-architecture` | `/spark/index.html`, `/compute/index.html` |
| 08 | Performance: AQE, shuffle, skew, caching | `spark-performance` | `/optimizations/index.html` |
| 09 | Delta optimization & Liquid Clustering | `delta-optimization` | `/delta/clustering.html`, `/delta/optimize.html` |
| 10 | Structured Streaming | `structured-streaming` | `/structured-streaming/index.html` |
| 11 | Databricks SQL & Photon | `dbsql-photon` | `/sql/index.html`, `/compute/photon.html` |
| 12 | Compute & cluster types | `compute-clusters` | `/compute/index.html`, `/compute/configure.html` |

## AI / ML & data sharing (optional extension)

| # | Feature | slug | Ground in |
|---|---------|------|-----------|
| 13 | Mosaic AI Model Serving + MLflow | `model-serving-mlflow` | `/machine-learning/model-serving/index.html`, `/mlflow/index.html` |
| 14 | Vector Search | `vector-search` | `/generative-ai/vector-search.html` |
| 15 | Genie / AI/BI | `genie-aibi` | `/genie/index.html`, `/dashboards/index.html` |
| 16 | Delta Sharing & Marketplace | `delta-sharing` | `/delta-sharing/index.html` |
| 17 | Lakebase (managed Postgres / OLTP) | `lakebase` | `/oltp/index.html` |
| 18 | Databricks Asset Bundles (DABs) | `asset-bundles` | `/dev-tools/bundles/index.html` |

## Agent & GenAI

| # | Feature | slug | Ground in |
|---|---------|------|-----------|
| 19 | Agent Bricks | `agent-bricks` | `/generative-ai/agent-bricks/index.html` (skill: `databricks-agent-bricks`) |
| 20 | Mosaic AI Agent Framework | `agent-framework` | `/generative-ai/agent-framework/build-genai-apps.html`, `/generative-ai/agent-framework/author-agent.html` |
| 21 | GenAI evaluation (MLflow 3 / Agent Evaluation) | `genai-evaluation` | `/mlflow3/genai/eval-monitor/index.html`, `/generative-ai/agent-evaluation/index.html` (skill: `databricks-mlflow-evaluation`) |
| 22 | LLMOps on Databricks | `llmops` | `/machine-learning/mlops/mlops-workflow.html`, `/generative-ai/tutorials/ai-cookbook/index.html` |

> Doc paths drift — if a path 404s, search `llms.txt` for the feature name and
> use the current canonical page. Always cite the URL you actually fetched.
