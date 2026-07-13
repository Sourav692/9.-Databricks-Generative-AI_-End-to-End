# Databricks Generative AI — End-to-End Learning Hub ✈️

> **From fundamentals to architect-level GenAI on Databricks** — theory *and* hands-on, grounded in the official Databricks docs, MLflow docs, and two reference books. Every concept is taught on one running example: **Unity Airways**, a fictional airline you build from a RAG knowledge base all the way to a governed, monitored, multi-surface GenAI platform.

**`18 modules` · `26 cornerstone deep-dives` · `34 hands-on notebooks` · `4 capstones` · `2 delivery tracks`** — Status: **✅ complete**

> 🖥️ **Prefer an interactive homepage?** Open **[`index.html`](index.html)** in a browser — same content with live module filtering and learning-path highlighting.

---

## How to use this hub

- **Every module** ships a **📖 written guide** (`module.md`) and a **🖥️ interactive page** (`module.html` — self-contained, opens in a browser by double-click).
- **★ cornerstone deep-dives** expand the highest-value topics into their own guide + interactive pair.
- **📓 notebooks** are **Databricks-importable** (`.py`, Databricks source format) — runnable, commented, Unity Catalog–first. Import them into a workspace and run top-to-bottom.
- New here? Follow the **level order (0 → 7)**, or jump in via a **learning path** below.
- The full teaching order + progress markers live in **[ROADMAP.md](ROADMAP.md)**; the build/QA tracker is **[plan.md](plan.md)**.

### Legend
📖 written guide (`.md`)  ·  🖥️ interactive page (`.html`)  ·  ★ cornerstone deep-dive  ·  📓 Databricks notebook (`.py`)  ·  `[T]` theory · `[H]` hands-on

---

## 🧭 Recommended learning paths

| Goal | Path |
|---|---|
| 🚀 **Fastest path to a RAG app** | 00 → 01 → 02 → 03 → 04 → 05 → 06 → 11 |
| 🤖 **Agent-focused** | *(after RAG core)* 07 → 08 → 09 → 10 → 11 → 13 |
| 🎓 **Certification** | [Track C](#-track-c--certification-prep) in parallel with Levels 1–6 |
| 🏛️ **Architect (full)** | Level 0 → Level 7 in order, ending at the **[C4 capstone](#-capstone-projects)** |
| 📊 **Conversational analytics** | 00 → 15 → 14 *(independent track — needs only Level 0)* |

---

## 📚 Curriculum

### Level 0 — Orientation & Environment
| Module | Read & explore | Cornerstone deep-dives ★ | Hands-on 📓 |
|---|---|---|---|
| **00 · Platform foundations for GenAI** | [📖](modules/00-platform-foundations/module.md) · [🖥️](modules/00-platform-foundations/module.html) | [Mosaic AI landscape](modules/00-platform-foundations/mosaic-ai-landscape.md) · [🖥️](modules/00-platform-foundations/mosaic-ai-landscape.html) | [module lab](notebooks/00-platform-foundations/00-module-lab.py) |

### Level 1 — GenAI Foundations
| Module | Read & explore | Cornerstone deep-dives ★ | Hands-on 📓 |
|---|---|---|---|
| **01 · GenAI & LLM fundamentals** | [📖](modules/01-genai-llm-fundamentals/module.md) · [🖥️](modules/01-genai-llm-fundamentals/module.html) | [Foundation Model APIs & external models](modules/01-genai-llm-fundamentals/foundation-model-apis.md) · [🖥️](modules/01-genai-llm-fundamentals/foundation-model-apis.html) | [module lab](notebooks/01-genai-llm-fundamentals/01-module-lab.py) |
| **02 · Prompt engineering** | [📖](modules/02-prompt-engineering/module.md) · [🖥️](modules/02-prompt-engineering/module.html) | [MLflow Prompt Registry](modules/02-prompt-engineering/prompt-registry.md) · [🖥️](modules/02-prompt-engineering/prompt-registry.html) | [module lab](notebooks/02-prompt-engineering/02-module-lab.py) · [prompt registry](notebooks/02-prompt-engineering/02-5-prompt-registry.py) |

### Level 2 — RAG Core
| Module | Read & explore | Cornerstone deep-dives ★ | Hands-on 📓 |
|---|---|---|---|
| **03 · Data prep & chunking** | [📖](modules/03-data-prep-chunking/module.md) · [🖥️](modules/03-data-prep-chunking/module.html) | [Chunking strategies](modules/03-data-prep-chunking/chunking-strategies.md) · [🖥️](modules/03-data-prep-chunking/chunking-strategies.html)<br>[AI Functions parsing](modules/03-data-prep-chunking/ai-parse-extract.md) · [🖥️](modules/03-data-prep-chunking/ai-parse-extract.html) | [module lab](notebooks/03-data-prep-chunking/03-module-lab.py) · [ai_parse/extract](notebooks/03-data-prep-chunking/03-8-ai-parse-extract.py) · [SDP ingestion](notebooks/03-data-prep-chunking/03-9-sdp-ingestion.py) |
| **04 · Embeddings & AI Search** | [📖](modules/04-embeddings-ai-search/module.md) · [🖥️](modules/04-embeddings-ai-search/module.html) | [Create & query an index](modules/04-embeddings-ai-search/create-query-index.md) · [🖥️](modules/04-embeddings-ai-search/create-query-index.html)<br>[Reranking](modules/04-embeddings-ai-search/reranking.md) · [🖥️](modules/04-embeddings-ai-search/reranking.html) | [module lab](notebooks/04-embeddings-ai-search/04-module-lab.py) · [create/query index](notebooks/04-embeddings-ai-search/04-3-create-query-index.py) |
| **05 · Building a RAG chain** | [📖](modules/05-building-rag-chain/module.md) · [🖥️](modules/05-building-rag-chain/module.html) | [Full RAG chain](modules/05-building-rag-chain/rag-chain.md) · [🖥️](modules/05-building-rag-chain/rag-chain.html)<br>[Model-as-Code](modules/05-building-rag-chain/model-as-code.md) · [🖥️](modules/05-building-rag-chain/model-as-code.html) | [module lab](notebooks/05-building-rag-chain/05-module-lab.py) · [RAG chain](notebooks/05-building-rag-chain/05-3-rag-chain.py) · [model-as-code](notebooks/05-building-rag-chain/05-6-model-as-code.py) |

### Level 3 — MLOps for GenAI with MLflow
| Module | Read & explore | Cornerstone deep-dives ★ | Hands-on 📓 |
|---|---|---|---|
| **06 · MLflow for GenAI core** | [📖](modules/06-mlflow-core/module.md) · [🖥️](modules/06-mlflow-core/module.html) | [MLflow 2 → 3](modules/06-mlflow-core/mlflow-2-to-3.md) · [🖥️](modules/06-mlflow-core/mlflow-2-to-3.html)<br>[UC Model Registry](modules/06-mlflow-core/uc-model-registry.md) · [🖥️](modules/06-mlflow-core/uc-model-registry.html) | [module lab](notebooks/06-mlflow-core/06-module-lab.py) · [UC Model Registry](notebooks/06-mlflow-core/06-5-uc-model-registry.py) |
| **07 · MLflow Tracing** | [📖](modules/07-mlflow-tracing/module.md) · [🖥️](modules/07-mlflow-tracing/module.html) | [Auto + manual tracing](modules/07-mlflow-tracing/tracing.md) · [🖥️](modules/07-mlflow-tracing/tracing.html) | [module lab](notebooks/07-mlflow-tracing/07-module-lab.py) |
| **08 · Evaluating GenAI** | [📖](modules/08-evaluating-genai/module.md) · [🖥️](modules/08-evaluating-genai/module.html) | [Evaluation harness](modules/08-evaluating-genai/eval-harness.md) · [🖥️](modules/08-evaluating-genai/eval-harness.html)<br>[LLM-as-a-judge](modules/08-evaluating-genai/llm-as-judge.md) · [🖥️](modules/08-evaluating-genai/llm-as-judge.html) | [module lab](notebooks/08-evaluating-genai/08-module-lab.py) · [LLM-as-a-judge](notebooks/08-evaluating-genai/08-4-llm-as-judge.py) |

### Level 4 — Agents
| Module | Read & explore | Cornerstone deep-dives ★ | Hands-on 📓 |
|---|---|---|---|
| **09 · Agent fundamentals & tools** | [📖](modules/09-agent-fundamentals/module.md) · [🖥️](modules/09-agent-fundamentals/module.html) | [Create tools](modules/09-agent-fundamentals/create-tools.md) · [🖥️](modules/09-agent-fundamentals/create-tools.html)<br>[ResponsesAgent packaging](modules/09-agent-fundamentals/responsesagent.md) · [🖥️](modules/09-agent-fundamentals/responsesagent.html) | [module lab](notebooks/09-agent-fundamentals/09-module-lab.py) · [create tools](notebooks/09-agent-fundamentals/09-3-create-tools.py) · [ResponsesAgent](notebooks/09-agent-fundamentals/09-6-responsesagent.py) |
| **10 · Agent Bricks & low-code** | [📖](modules/10-agent-bricks/module.md) · [🖥️](modules/10-agent-bricks/module.html) | [Knowledge Assistant](modules/10-agent-bricks/knowledge-assistant.md) · [🖥️](modules/10-agent-bricks/knowledge-assistant.html)<br>[Databricks Apps](modules/10-agent-bricks/databricks-apps.md) · [🖥️](modules/10-agent-bricks/databricks-apps.html) | [module lab](notebooks/10-agent-bricks/10-module-lab.py) · [Databricks Apps](notebooks/10-agent-bricks/10-5-databricks-apps.py) |

### Level 5 — Production: Deploy, Govern, Monitor
| Module | Read & explore | Cornerstone deep-dives ★ | Hands-on 📓 |
|---|---|---|---|
| **11 · Deployment & serving** | [📖](modules/11-deployment-serving/module.md) · [🖥️](modules/11-deployment-serving/module.html) | [Model Serving](modules/11-deployment-serving/model-serving.md) · [🖥️](modules/11-deployment-serving/model-serving.html)<br>[AI Gateway](modules/11-deployment-serving/ai-gateway.md) · [🖥️](modules/11-deployment-serving/ai-gateway.html)<br>[AI Functions at scale](modules/11-deployment-serving/ai-functions-at-scale.md) · [🖥️](modules/11-deployment-serving/ai-functions-at-scale.html) | [module lab](notebooks/11-deployment-serving/11-module-lab.py) · [Model Serving](notebooks/11-deployment-serving/11-1-model-serving.py) · [AI Functions](notebooks/11-deployment-serving/11-10-ai-functions.py) |
| **12 · Responsible GenAI** | [📖](modules/12-responsible-genai/module.md) · [🖥️](modules/12-responsible-genai/module.html) | [AI Guardrails](modules/12-responsible-genai/ai-guardrails.md) · [🖥️](modules/12-responsible-genai/ai-guardrails.html) | [module lab](notebooks/12-responsible-genai/12-module-lab.py) · [AI Guardrails](notebooks/12-responsible-genai/12-2-ai-guardrails.py) |
| **13 · Production monitoring** | [📖](modules/13-production-monitoring/module.md) · [🖥️](modules/13-production-monitoring/module.html) | [AI/BI monitoring dashboard](modules/13-production-monitoring/aibi-dashboard.md) · [🖥️](modules/13-production-monitoring/aibi-dashboard.html) | [module lab](notebooks/13-production-monitoring/13-module-lab.py) · [AI/BI dashboard](notebooks/13-production-monitoring/13-5-aibi-dashboard.py) |

### Level 6 — Conversational Analytics & the Semantic Layer
| Module | Read & explore | Cornerstone deep-dives ★ | Hands-on 📓 |
|---|---|---|---|
| **14 · AI/BI Genie** | [📖](modules/14-aibi-genie/module.md) · [🖥️](modules/14-aibi-genie/module.html) | [Curate & tune a Genie Agent](modules/14-aibi-genie/curate-tune-genie.md) · [🖥️](modules/14-aibi-genie/curate-tune-genie.html) | [module lab](notebooks/14-aibi-genie/14-module-lab.py) · [Genie Conversation API](notebooks/14-aibi-genie/14-8-genie-api.py) |
| **15 · Business Semantics (metric views)** | [📖](modules/15-business-semantics/module.md) · [🖥️](modules/15-business-semantics/module.html) | [Query metric views](modules/15-business-semantics/query-metric-views.md) · [🖥️](modules/15-business-semantics/query-metric-views.html) | [module lab](notebooks/15-business-semantics/15-module-lab.py) · [query metric views](notebooks/15-business-semantics/15-3-query-metric-views.py) |

### Level 7 — Architect & Frontier
| Module | Read & explore | Cornerstone deep-dives ★ | Hands-on 📓 |
|---|---|---|---|
| **16 · Cost, performance & scaling** | [📖](modules/16-cost-performance-scaling/module.md) · [🖥️](modules/16-cost-performance-scaling/module.html) | [Mosaic AI architecture](modules/16-cost-performance-scaling/mosaic-ai-architecture.md) · [🖥️](modules/16-cost-performance-scaling/mosaic-ai-architecture.html) | [module lab](notebooks/16-cost-performance-scaling/16-module-lab.py) |
| **17 · Reference architectures** | [📖](modules/17-reference-architectures/module.md) · [🖥️](modules/17-reference-architectures/module.html) | *Topic 17.7 = the [C4 capstone](#-capstone-projects) →* | *(hands-on = the C4 capstone notebook)* |

---

## 🏁 Capstone projects

Four integrative projects that turn "topics learned" into "a thing shipped." Each builds on the previous one's Unity Airways artifact. Every capstone = **brief (`.md`) + interactive spec (`.html`) + runnable notebook (`.py`)**.

| # | Capstone | Integrates | Deliverable | Links |
|---|---|---|---|---|
| **C1** | Support RAG Knowledge Base | 00–05 | Ingestion → AI Search index → **registered RAG chain** with citations | [📖](capstones/capstone-1-rag-knowledge-base.md) · [🖥️](capstones/capstone-1-rag-knowledge-base.html) · [📓](capstones/capstone-1-rag-knowledge-base.py) |
| **C2** | Evaluate, Trace & Version the RAG App | 06–08 | Trace-instrumented, **evaluated & versioned** RAG + quality scorecard + `@champion` | [📖](capstones/capstone-2-eval-trace-version.md) · [🖥️](capstones/capstone-2-eval-trace-version.html) · [📓](capstones/capstone-2-eval-trace-version.py) |
| **C3** | Ship a Governed, Monitored Agent | 09–13 | Tool-using agent **deployed behind AI Gateway guardrails**, monitored + Review App | [📖](capstones/capstone-3-governed-agent.md) · [🖥️](capstones/capstone-3-governed-agent.html) · [📓](capstones/capstone-3-governed-agent.py) |
| **C4** ⭐ | Unity Airways GenAI Platform *(= ★17.7)* | all 00–17 | Full reference solution: RAG + agent + eval/monitoring **+ Genie analytics** + cert-readiness map | [📖](capstones/capstone-4-genai-platform.md) · [🖥️](capstones/capstone-4-genai-platform.html) · [📓](capstones/capstone-4-genai-platform.py) |

---

## 🎓 Track C — Certification prep

Cross-cutting prep for the **Databricks Certified Generative AI Engineer Associate** exam — the exam blueprint mapped to every module, a readiness checklist, and an original practice-question bank.

- [📖 Guide](modules/track-c-certification/module.md) · [🖥️ Interactive exam-domain → module map](modules/track-c-certification/module.html)
- [📝 Mock exam — 32 original practice questions](modules/track-c-certification/mock-exam.md)

## 🧰 Track D — FDE delivery toolkit

Cross-cutting delivery assets for Field Engineers — the discovery → POC → pilot → production motion, plus reusable customer-facing one-pagers.

- [📖 Guide](modules/track-d-fde-delivery/module.md)
- [🖥️ Architecture one-pager](modules/track-d-fde-delivery/architecture-one-pager.html) · [🖥️ POC scorecard](modules/track-d-fde-delivery/poc-scorecard.html) · [🖥️ Production-readiness checklist](modules/track-d-fde-delivery/production-readiness-checklist.html)

---

## 📖 Sources & references

- 📘 **B1** — *Practical MLflow for Generative AI on Databricks* (O'Reilly Early Release)
- 📗 **B2** — *Databricks Certified Generative AI Engineer Associate Study Guide*
- 🌐 Latest **[Databricks docs](https://docs.databricks.com)** + **[MLflow docs](https://mlflow.org/docs/latest)** (product behavior always wins over the books where they differ)
- 🗺️ **[ROADMAP.md](ROADMAP.md)** — full teaching order + progress markers · 🛠️ **[plan.md](plan.md)** — build & QA tracker

> **Product names churn fast on Databricks** — many features here are GA, some are Beta/Preview (flagged inline). Re-verify against the live docs before you rely on an exact API, flag, or metric name.

---

<sub>Built with the <code>genai-teacher</code> → <code>genai-teacher-reviewer</code> loop. Running example: <b>Unity Airways</b> ✈️ · catalog <code>unity_airways</code> (schemas <code>rag</code> + <code>analytics</code>).</sub>
