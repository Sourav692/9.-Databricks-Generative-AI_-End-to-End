# Current Databricks GenAI Naming & Features — teacher cheat-sheet

> **Purpose:** keep `genai-teacher` output on the **latest, official** product names, APIs, and
> features. The project's two books lag the product — especially *Practical MLflow for GenAI*
> (O'Reilly **Early Release, RAW & UNEDITED**). When a book term below is marked "legacy/renamed,"
> teach the **current** name and add a `> ⚠️ GOTCHA:` noting the old one.
>
> **Freshness:** verified against live docs **July 2026**. Product names on Databricks churn fast
> and many items are **Beta/Preview** — **re-verify at authoring time**, don't treat this file as
> eternal truth. Verification path: the **`databricks-docs`** skill → `https://docs.databricks.com/llms.txt`
> → the specific doc page (cite the exact URL). Cross-check MLflow APIs at `mlflow.org/docs/latest`.

---

## 0. How to stay current (do this every lesson)

1. Before writing, **look up the current name/API** for each product you'll mention — use the
   `databricks-docs` skill (fetch `https://docs.databricks.com/llms.txt`, then the topic page) and
   `mlflow.org/docs/latest` for MLflow APIs. Cite the exact URL in the lesson's Sources.
2. If this cheat-sheet and a **live doc** disagree, **the live doc wins** — update the lesson and,
   if you can, fix this file.
3. Prefer **GA** features for the main teaching path; clearly label **Beta/Preview** features as
   such (they can change or require enrollment).
4. Never invent an API/flag/metric/endpoint. Unverifiable ⇒ say "need to verify."

---

## 1. MLflow for GenAI (MLflow 3.x) — the biggest book-vs-product gap

The MLflow book predates much of the `mlflow.genai` surface. Teach the MLflow 3 APIs.

| Current (teach this) | Legacy / replaced | Status | Note + doc |
|---|---|---|---|
| `mlflow.genai.evaluate(data=, predict_fn=, scorers=[...])` | `mlflow.evaluate(model_type="databricks-agent"/"question-answering")` | GA (MLflow 3) | Top-level GenAI eval entry point. `model`→`predict_fn`, `extra_metrics`→`scorers`; `model_type`/`evaluator_config` removed. `mlflow.org/docs/latest/genai/eval-monitor/` |
| Scorers in `mlflow.genai.scorers`; judge fns in `mlflow.genai.judges`; custom via `@scorer` + `make_judge()` | `databricks.agents.evals.metric` / `.judges` | GA | Must pass `scorers=[...]` explicitly (3.x no longer auto-selects). |
| Built-in scorers: `Correctness`, `Guidelines`, `ExpectationsGuidelines`, `RelevanceToQuery`, `Safety`, `RetrievalGroundedness`, `RetrievalRelevance`, `RetrievalSufficiency`, `ToolCallCorrectness/Efficiency`, plus multi-turn (`ConversationCompleteness`, `UserFrustration`, …) | `groundedness`, `chunk_relevance`, `relevance_to_query`, `guideline_adherence`, `context_sufficiency` (old judge names) | GA | `docs.databricks.com/aws/en/mlflow3/genai/eval-monitor/concepts/judges/` |
| Eval-dataset fields: `inputs`, `outputs`, `expectations` | `request`, `response`, `expected_response`, `retrieved_context` | GA | `retrieved_context` now read from **traces**. |
| Datasets: `mlflow.genai.create_dataset/get_dataset/search_datasets` (UC-backed) | ad-hoc DataFrames | GA | |
| Human review: `mlflow.genai.labeling` (`create_labeling_session`, `get_review_app`, `ReviewApp`) | `databricks.agents.review_app` | GA | |
| **Tracing:** `@mlflow.trace`, `mlflow.start_span()`, `mlflow.<lib>.autolog()` (openai/langchain/anthropic/…) | manual logging | GA | OpenTelemetry-compatible; GenAI semantic conventions. `mlflow.org/docs/latest/genai/tracing/` |
| **LoggedModel** + `mlflow.set_active_model()` — links a model/app version to its traces, evals, metrics | (didn't exist) | GA (**new in MLflow 3**) | `docs.databricks.com/aws/en/mlflow/logged-model` |
| **Prompt Registry:** `mlflow.genai.register_prompt/load_prompt/search_prompts/set_prompt_alias`; URIs `prompts:/name/1` or `prompts:/name@alias`; `{{variable}}` templates | prompts as plain strings/params | **Beta on Databricks** (UC schema; `mlflow[databricks]>=3.1`) | `docs.databricks.com/aws/en/mlflow3/genai/prompt-version-mgmt/prompt-registry/` |
| **Models from Code:** `mlflow.models.set_model()` for chains/agents | pickling / cloudpickle | GA (recommended) | Flavor logging (`mlflow.langchain.log_model`, `mlflow.pyfunc.log_model`) still valid. `mlflow.org/docs/latest/ml/model/models-from-code/` |
| **Production monitoring** reuses the same scorers/judges (MLflow 3) | "Lakehouse Monitoring for generative AI (MLflow 2)" | Production monitoring **Beta** | `docs.databricks.com/aws/en/mlflow3/genai/eval-monitor/` |

---

## 2. AI Agents — Agent Framework & Agent Bricks

| Current (teach this) | Legacy / replaced | Status | Note + doc |
|---|---|---|---|
| **`ResponsesAgent`** (MLflow) — recommended authoring interface | `ChatAgent` (being superseded) → `ChatModel` (legacy) | GA/recommended | Framework-agnostic; auto-tracing, streaming, tool/multi-agent history; OpenAI Responses schema. `docs.databricks.com/aws/en/generative-ai/agent-framework/author-agent`. Migration path: `ChatModel`→`ChatAgent`→`ResponsesAgent`. `SplitChatMessagesRequest`/`StringResponse` are deprecated. |
| Register agent to **Unity Catalog** (`mlflow.set_registry_uri("databricks-uc")` → `mlflow.register_model` → `catalog.schema.model`) | Workspace Model Registry | GA | UC governs models, functions/tools, and data. |
| Deploy: `from databricks import agents; agents.deploy(uc_model_name, version)` → creates Serving endpoint + **Review App** + feedback model; enables tracing, inference tables, monitoring | manual endpoint wiring | GA | `docs.databricks.com/aws/en/generative-ai/agent-framework/deploy-agent`. For new use cases, **Databricks Apps** deployment is increasingly recommended. |
| Evaluate agents with **`mlflow.genai.evaluate()`** (§1) | `mlflow.evaluate(model_type="databricks-agent")` ("Agent Evaluation", MLflow 2) | GA | There is **no** function literally named `agents.evaluate` — don't teach that. |
| **Tools:** `UCFunctionToolkit` (`from databricks_langchain import UCFunctionToolkit`); UC functions as tools; built-in `system.ai.python_exec`; retrieval tools via **AI Search** | ad-hoc Python tools only | GA | `docs.databricks.com/aws/en/generative-ai/agent-framework/create-custom-tool` |
| **Managed MCP servers** (Databricks-hosted, UC-governed): Genie, AI Search, Databricks SQL, UC functions; + custom/external MCP | (didn't exist) | **Public Preview** (some surfaces GA) | `docs.databricks.com/aws/en/generative-ai/mcp/managed-mcp` |

### Agent Bricks (launched Beta, June 2025) — the no/low-code agent umbrella
| Component | Status (July 2026) | What it is / doc |
|---|---|---|
| **Knowledge Assistant** | **GA** (Jan 2026) | Cited Q&A chatbot over a UC-volume folder or an AI Search index. `docs.databricks.com/aws/en/generative-ai/agent-bricks/knowledge-assistant` |
| **Multi-Agent Supervisor** (a.k.a. Supervisor Agent) | **GA** (Feb 2026) | Managed orchestration across Genie Agents (structured), Knowledge Assistant (unstructured), MCP servers (tools). `.../agent-bricks/multi-agent-supervisor` |
| **Information Extraction** | **Beta** | Unstructured docs/PDFs/images → structured table via generated JSON schema. `docs.databricks.com/aws/en/agents/agent-bricks/info-extraction` |
| **Custom LLM** | **Beta** | Domain text tasks (summarize/classify/transform/generate). `.../agent-bricks/custom-llm` |
| **Custom Agents** | (no explicit label) | Python `ResponsesAgent` + framework, deployed via `agents.deploy()` or Databricks Apps. |
| **AI Playground** | GA | No-code chat to compare LLMs and **prototype tool-calling agents** (UC functions, AI Search, MCP); "Export to Databricks Apps." `docs.databricks.com/aws/en/large-language-models/ai-playground` |

---

## 3. Databricks AI Search (was Vector Search)

| Current (teach this) | Legacy / replaced | Status | Note + doc |
|---|---|---|---|
| **Databricks AI Search** | "Mosaic AI Vector Search" / "Databricks Vector Search" | GA | Rename confirmed: "Databricks AI Search (formerly Databricks Vector Search)." `docs.databricks.com/aws/en/vector-search/vector-search` |
| ⚠️ **SDK is still `databricks-vectorsearch`** — `from databricks.vector_search.client import VectorSearchClient` (`%pip install databricks-vectorsearch`) | — | GA | **The package name did NOT change** with the rebrand. Do **not** write `databricks-ai-search`/`AISearchClient` — those don't exist. |
| Index types: **Delta Sync Index** (managed or self-managed embeddings), **Direct Vector Access Index**; **Full-text search index** | — | Delta Sync & Direct = GA; Full-text = **Beta** | Distinct types — don't conflate. |
| Endpoint types: **Standard** and **Storage-optimized** (>1B vectors, faster indexing) | — | Both **GA** (storage-optimized was Preview in early 2025) | |
| **Hybrid search** (keyword + vector) | vector-only | GA | |
| Embedding endpoints: `databricks-gte-large-en` (general default), `databricks-bge-large-en`; `databricks-qwen3-embedding-0-6b` emerging (Preview) | — | GA (qwen3 Preview) | Teach gte-large-en as the safe default. |

---

## 4. Model Serving & Foundation Model APIs

| Current (teach this) | Note + doc |
|---|---|
| **Model Serving** — three endpoint families, all GA: **Custom models** (MLflow-packaged), **Foundation Models** (Databricks-hosted), **External Models** (governed proxy to OpenAI/Anthropic/Google/…) | `docs.databricks.com/aws/en/machine-learning/model-serving/` |
| **Foundation Model APIs — two modes:** **pay-per-token** (get started) and **provisioned throughput** (production; custom/fine-tuned weights; perf guarantees) | `docs.databricks.com/aws/en/machine-learning/foundation-model-apis/` |
| **Served-model names churn** — always confirm on the supported-models page before naming an endpoint. Snapshot (mid-2026): `databricks-llama-4-maverick`, `databricks-meta-llama-3-3-70b-instruct`, `databricks-claude-sonnet-4-5`, `databricks-claude-opus-4-5`, `databricks-gpt-oss-120b`, `databricks-gemini-2-5-pro`. **DBRX (`databricks-dbrx-instruct`) is no longer listed** (treat as retired — verify). | `docs.databricks.com/aws/en/machine-learning/foundation-model-apis/supported-models` |

---

## 5. AI Functions (SQL-native GenAI) — under-covered by the books

Overview: **"Enrich data using AI Functions"** — `docs.databricks.com/aws/en/large-language-models/ai-functions`

- **GA:** `ai_query` (general — any served model/prompt), `ai_parse_document`, `ai_extract`,
  `ai_classify`, `ai_gen`, `ai_summarize`, `ai_translate`, `ai_mask`, `ai_similarity`,
  `ai_analyze_sentiment`, `ai_fix_grammar`, `ai_forecast`, `vector_search` (queries an AI Search index).
- **Beta:** `ai_prep_search` (prepares parsed-doc output for RAG).
- Use `ai_parse_document` / `ai_extract` for RAG **data prep** (Module 03) and `ai_query` for
  **batch inference** at scale (Modules 11/16).

---

## 6. AI Gateway

| Current (teach this) | Note + doc |
|---|---|
| **AI Gateway for serving endpoints** (the established feature set on Model Serving) | Rate limiting, **AI guardrails** (safety filtering, **PII detection/redaction** — Preview), usage tracking (system tables), **payload logging → inference tables**, provider **fallbacks**. `docs.databricks.com/aws/en/ai-gateway/` |
| **Unity AI Gateway** — newer, recommended go-forward | **Beta.** Adds richer UI/observability, **MCP-service governance**, and **budget management** (spend thresholds/hard caps). Teach as "the direction of travel," label Beta. |

---

## 7. AI/BI Genie & Genie One

| Current (teach this) | Legacy / renamed | Status | Note + doc |
|---|---|---|---|
| **Genie Agents** | "Genie Spaces" (and earlier "AI/BI Genie") | GA | "Genie Agents were formerly known as Genie Spaces." `docs.databricks.com/aws/en/genie/` |
| **Agent mode** (plans + iterates multiple SQL queries → cited report) | "Research Agent" / "deep research" | GA | `docs.databricks.com/aws/en/genie/agent-mode` |
| **Genie Agents API** (Conversation + Management APIs); iframe embedding | — | GA | `docs.databricks.com/aws/en/genie/conversation-api` |
| **Genie One** — simplified single-entry UI for business users; workspace + account-level discovery; surfaces AI/BI dashboards, Genie Agents, Databricks Apps | **"Databricks One"** | Core GA; "Domains" Preview | `docs.databricks.com/aws/en/genie-one/genie` |
| **Genie Code** (newer) | — | verify | `docs.databricks.com/aws/en/genie-code/` |

---

## 8. Platform rebrands that show up in GenAI lessons

- **Delta Live Tables (DLT) → Lakeflow Declarative Pipelines** (existing code runs unchanged; some
  Python API/SKU names changed; event-log schema still "dlt"). `docs.databricks.com/aws/en/ldp/`
- **Databricks Workflows → Lakeflow Jobs** (Lakeflow suite: Connect, Declarative Pipelines,
  Designer, Jobs; system-table schema `workflow`→`lakeflow`). `docs.databricks.com/aws/en/jobs/`
- **Broad trend:** moving **away from "Mosaic AI"** branding toward "Databricks …" / "Unity …" /
  "AI/BI …". "Mosaic AI Model Serving/Agent Framework" still appear in places — prefer the current
  page title. (Inferred from title changes, not a single retirement notice — verify.)

---

## 9. "Do not get this wrong" — high-risk pitfalls

- ✅ Package is **`databricks-vectorsearch`** even though the product is now **AI Search**. There is
  no `databricks-ai-search` package or `AISearchClient` class.
- ✅ GenAI eval is **`mlflow.genai.evaluate()`**, not `mlflow.evaluate(model_type="databricks-agent")`
  and not `agents.evaluate()`.
- ✅ Agent authoring: **`ResponsesAgent`** (recommended) > `ChatAgent` (legacy) > `ChatModel` (older legacy).
- ✅ LangChain integration import is **`databricks-langchain`** (`from databricks_langchain import ChatDatabricks, DatabricksVectorSearch, DatabricksEmbeddings, UCFunctionToolkit`), **not** `langchain-databricks` or `langchain_community`.
- ✅ **Genie Agents** (not "Genie Spaces"); **Genie One** (not "Databricks One").
- ✅ Mark **Beta/Preview**: Prompt Registry (Databricks), Production monitoring, Unity AI Gateway,
  Full-text search index, Information Extraction, Custom LLM, managed MCP (some surfaces), `ai_prep_search`.
- ✅ **DBRX retirement** and specific served-model endpoint names are **inferred/volatile** — confirm
  on the supported-models page at authoring time.
