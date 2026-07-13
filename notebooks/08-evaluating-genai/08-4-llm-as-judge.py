# Databricks notebook source
# MAGIC %md
# MAGIC # 08.4 ★ — LLM-as-a-Judge scorers, and which judges need ground truth
# MAGIC **Roadmap:** Module 08 (Evaluating GenAI) · Topic 08.4 (cornerstone) · [Theory + Hands-on]
# MAGIC
# MAGIC Focused, runnable lab for the cornerstone: score the Module 05 Unity Airways RAG chain with MLflow 3
# MAGIC **LLM judges**, and prove the one split you must not get wrong — **which judges need a ground-truth
# MAGIC answer (`expectations`) and which are reference-free**.
# MAGIC
# MAGIC | Step | What you do |
# MAGIC |---|---|
# MAGIC | 1 | Load the registered chain (Module 05) and wrap it in a `predict_fn` |
# MAGIC | 2 | Build a small eval dataset — some rows WITH ground truth, some WITHOUT |
# MAGIC | 3 | Split scorers into reference-free vs reference-based (the core 08.4 fact) |
# MAGIC | 4 | Run reference-free judges on EVERY row (no labels) |
# MAGIC | 5 | Run reference-based judges (`Correctness` + `RetrievalSufficiency`) — labeled rows only |
# MAGIC | 6 | One combined run: all built-ins + a global `Guidelines` judge |
# MAGIC | 7 | Custom judge with `make_judge(...)` (MLflow >= 3.4) |
# MAGIC | 8 | Custom CODE scorer with `@scorer` returning a `Feedback` |
# MAGIC | 9 | Read back per-row results (the rationale, not just the number) |
# MAGIC
# MAGIC Deep-dive explainer: `modules/08-evaluating-genai/llm-as-judge.md`. The chain comes from **Module 05**;
# MAGIC its **traces** (the RETRIEVER span the retrieval judges read) come from **Module 07**.
# MAGIC
# MAGIC ## Prerequisites (read before running)
# MAGIC - **Compute:** **serverless notebook/job**, or a **DBR ML runtime** (15.4 LTS ML or later is a safe floor).
# MAGIC - **MLflow:** **>= 3.1** required; **>= 3.4** if you use `make_judge` (Step 7).
# MAGIC - **The chain from Module 05:** `unity_airways.rag.ua_rag_chain` registered in Unity Catalog with a
# MAGIC   `@champion` alias (Module 05.6 / Module 06 lab). It emits **RETRIEVER spans** (Module 07 tracing) — the
# MAGIC   retrieval judges read retrieved context straight from those spans.
# MAGIC - **Vector Search index (Module 04):** `unity_airways.rag.ua_rag_chunks_index` **ONLINE** on endpoint
# MAGIC   **`unity-airways-vs`** (built over `content`, keyed on `chunk_id`, with `source_doc` synced).
# MAGIC - **Judge / chat endpoint:** **`databricks-claude-sonnet-4-5`** (Foundation Model API) — pinned as the
# MAGIC   judge model for stable, comparable scores. Endpoint names churn — confirm on the supported-models page.
# MAGIC - **Experiment:** a path you can write to (Step 0 `EXPERIMENT_PATH`). Eval runs + traces attach there.
# MAGIC - **Secrets:** none. Managed embeddings and workspace auth need no external key.
# MAGIC - **Learner-set identifiers:** edit the constants in Step 0.
# MAGIC
# MAGIC > 📌 **The whole topic in one fork:** does the judge compare against a ground-truth answer?
# MAGIC > **`Correctness`** and **`RetrievalSufficiency`** do (`expected_facts` / `expected_response` in
# MAGIC > `expectations`). Everything else here — `RelevanceToQuery`, `Safety`, `RetrievalGroundedness`,
# MAGIC > `RetrievalRelevance`, plain `Guidelines` — is **reference-free**. Pass `scorers=[...]` explicitly;
# MAGIC > MLflow 3 never auto-selects, and there is **no** `agents.evaluate()`.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 0. Install libraries and set variables
# MAGIC `mlflow[databricks]>=3.4` (the `make_judge` floor) plus `databricks-langchain` / `databricks-vectorsearch`
# MAGIC (the chain's imports). Restart Python so the fresh installs import.

# COMMAND ----------

# MAGIC %pip install -U "mlflow[databricks]>=3.4" databricks-langchain databricks-vectorsearch
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

import mlflow

CATALOG       = "unity_airways"                            # a catalog you can read from
SCHEMA        = "rag"                                      # the RAG schema from Modules 03/04
UC_MODEL      = f"{CATALOG}.{SCHEMA}.ua_rag_chain"         # the Module 05 chain, registered in UC
INDEX_NAME    = f"{CATALOG}.{SCHEMA}.ua_rag_chunks_index"  # Module 04 index (retrieval judges read its spans)
VS_ENDPOINT   = "unity-airways-vs"                         # Vector Search endpoint (from Module 04)
CHAT_ENDPOINT = "databricks-claude-sonnet-4-5"            # confirm on the supported-models page

# Pin the JUDGE model so verdicts are stable and comparable across runs. Note the "databricks:/" URI prefix.
EVAL_MODEL    = "databricks:/databricks-claude-sonnet-4-5"

# Learner-set: an experiment path you can write to (usually your own /Users/<you> path).
EXPERIMENT_PATH = "/Users/you@company.com/unity_airways_rag"

mlflow.set_registry_uri("databricks-uc")   # load the chain from Unity Catalog
mlflow.set_experiment(EXPERIMENT_PATH)      # eval runs + traces attach here

print("UC model    :", UC_MODEL)
print("Judge model :", EVAL_MODEL)
print("Experiment  :", EXPERIMENT_PATH)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 1 — Load the Module 05 chain and wrap it in a predict_fn  ·  [Hands-on]
# MAGIC The harness calls `predict_fn` once per dataset row. Two rules decide whether the run produces any
# MAGIC traces at all:
# MAGIC - The **`inputs` dict keys become the `predict_fn` keyword arguments.** Our rows use `{"query": ...}`,
# MAGIC   so the function parameter is named `query`.
# MAGIC - The Module 05 chain is an **LCEL runnable invoked with a bare string** (see `05-3-rag-chain.py`) — so
# MAGIC   `predict_fn` returns `chain.invoke(query)`, not a `{"messages": [...]}` dict.

# COMMAND ----------

# Load the registered chain by alias — this is the exact artifact Module 08 scores. Loading re-runs the
# Model-as-Code file, so the retriever + LLM are rebuilt (nothing is pickled).
chain = mlflow.langchain.load_model(f"models:/{UC_MODEL}@champion")

def predict_fn(query: str) -> str:
    # inputs keys -> predict_fn kwargs; here each row's inputs = {"query": ...}
    return chain.invoke(query)

# Smoke-test ONE call before evaluating a whole dataset — the #1 way to catch a schema mismatch early.
print(predict_fn("Can I get a refund on a Basic Economy fare?")[:250])

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 2 — Build a small eval dataset (some rows WITH ground truth, some WITHOUT)  ·  [Hands-on]
# MAGIC Ground truth lives in each row's `expectations`. Reference-based judges read it; reference-free judges
# MAGIC ignore it — same dataset, one field decides what you can run. `outputs` are filled in for you because we
# MAGIC pass `predict_fn` (direct mode): MLflow calls the chain per row and records the answer plus the trace.

# COMMAND ----------

eval_df = [
    {   # WITH ground truth (expected_facts) — Correctness + RetrievalSufficiency can score this row
        "inputs": {"query": "Can I get a refund on a Basic Economy fare?"},
        "expectations": {
            "expected_facts": [
                "Basic Economy fares are generally non-refundable.",
                "A full refund is available if cancelled within 24 hours of booking.",
            ],
        },
    },
    {   # WITH ground truth (expected_response) — a gold answer instead of a fact list
        "inputs": {"query": "How many carry-on bags are included?"},
        "expectations": {
            "expected_response": "One personal item plus one carry-on bag are included on all fares.",
        },
    },
    # WITHOUT ground truth — only reference-free judges apply to these two rows
    {"inputs": {"query": "My connection was missed — what are my options?"}},
    {"inputs": {"query": "Can I bring my dog in the cabin?"}},
]

with_gt = sum("expectations" in r for r in eval_df)
print(f"{len(eval_df)} rows | with expectations: {with_gt} | without: {len(eval_df) - with_gt}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 3 — The ground-truth split (the core 08.4 fact)  ·  [Theory + Hands-on]
# MAGIC Keep **two lists** in code. It answers "do I need labels here?" structurally, and it mirrors exactly how
# MAGIC you reuse these scorers in production monitoring (Module 13), where you have no labels.
# MAGIC - **Reference-free** (no `expectations`): `RelevanceToQuery`, `Safety`, `RetrievalGroundedness`,
# MAGIC   `RetrievalRelevance`. Run on any row, including live traffic.
# MAGIC - **Reference-based** (needs `expected_facts` / `expected_response`): `Correctness`,
# MAGIC   **`RetrievalSufficiency`** — the retrieval judge people forget belongs here.
# MAGIC
# MAGIC Pin every judge to `EVAL_MODEL` so verdicts don't drift between runs.

# COMMAND ----------

from mlflow.genai.scorers import (
    Correctness, RelevanceToQuery, Safety,
    RetrievalGroundedness, RetrievalRelevance, RetrievalSufficiency,
    Guidelines,
)

reference_free = [
    RelevanceToQuery(model=EVAL_MODEL),       # does the answer address the question?
    Safety(model=EVAL_MODEL),                 # toxic / harmful / PII content?
    RetrievalGroundedness(model=EVAL_MODEL),  # answer supported by retrieved context? (reads the trace)
    RetrievalRelevance(model=EVAL_MODEL),     # are the retrieved docs relevant? (reads the trace)
]

reference_based = [
    Correctness(model=EVAL_MODEL),            # NEEDS expected_facts / expected_response
    RetrievalSufficiency(model=EVAL_MODEL),   # NEEDS expected_facts / expected_response (reads the trace)
]

print("reference-free:", len(reference_free), "| reference-based:", len(reference_based))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 4 — Run reference-free judges on EVERY row (no labels required)  ·  [Hands-on]
# MAGIC These judge the output/trace as-is, so they score all four rows — including the two with no
# MAGIC `expectations`. That is why they can also run on unlabeled production traffic.

# COMMAND ----------

with mlflow.start_run(run_name="08-4-reference-free") as free_run:
    free_result = mlflow.genai.evaluate(
        data=eval_df,
        predict_fn=predict_fn,
        scorers=reference_free,   # MUST be explicit — MLflow 3 auto-selects nothing
    )

print("Aggregate metrics:", free_result.metrics)

# COMMAND ----------

# MAGIC %md
# MAGIC ### How to verify it worked
# MAGIC Every row got a `Feedback` per judge. Open the run in the MLflow **Evaluations** UI (rendered inline below
# MAGIC the cell) — each row has a score and a written **rationale** you can read.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 5 — Run reference-based judges (labeled rows only)  ·  [Hands-on]
# MAGIC `Correctness` and `RetrievalSufficiency` compare against the answer key. The two rows WITH `expectations`
# MAGIC get a verdict; the two WITHOUT are skipped for these judges. That skip is the visible proof of the
# MAGIC ground-truth requirement.

# COMMAND ----------

with mlflow.start_run(run_name="08-4-reference-based") as gt_run:
    gt_result = mlflow.genai.evaluate(
        data=eval_df,
        predict_fn=predict_fn,
        scorers=reference_based,
    )

print("Aggregate metrics:", gt_result.metrics)
# Verify: the refund (expected_facts) + carry-on (expected_response) rows get Correctness /
# RetrievalSufficiency verdicts; the unlabeled missed-connection + pet rows are skipped for those judges.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 6 — One combined run: all built-ins + a global Guidelines judge  ·  [Hands-on]
# MAGIC In practice you pass one explicit list that mixes both families plus a plain-English `Guidelines` rule.
# MAGIC `Guidelines` is **reference-free** — the rule lives on the scorer, not in the data.

# COMMAND ----------

cites_policy = Guidelines(
    name="cites_policy",
    guidelines=(
        "The answer must cite a specific Unity Airways policy or source document "
        "(fare rules, refund window, rebooking policy, or a source_doc) rather than "
        "giving a generic, unattributed airline answer."
    ),
    model=EVAL_MODEL,
)

all_scorers = [
    Correctness(model=EVAL_MODEL),            # reference-based
    RelevanceToQuery(model=EVAL_MODEL),       # reference-free
    Safety(model=EVAL_MODEL),                 # reference-free
    RetrievalGroundedness(model=EVAL_MODEL),  # reference-free
    RetrievalSufficiency(model=EVAL_MODEL),   # reference-based
    cites_policy,                             # reference-free (global rule)
]

with mlflow.start_run(run_name="08-4-all-judges") as full_run:
    full_result = mlflow.genai.evaluate(
        data=eval_df,
        predict_fn=predict_fn,
        scorers=all_scorers,
    )

print("Aggregate metrics:", full_result.metrics)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 7 — Custom judge with make_judge (MLflow >= 3.4)  ·  [Hands-on]
# MAGIC When no built-in fits, `make_judge` gives you a full custom prompt with `{{ inputs }}` / `{{ outputs }}`
# MAGIC template variables and categorical/graded verdicts. Pass it in `scorers=[...]` like any other judge.

# COMMAND ----------

from mlflow.genai.judges import make_judge

# NOTE: verify make_judge kwargs vs current docs — the API is young (needs MLflow >= 3.4) and kwargs such as
# a value-type constraint for categorical outputs are still evolving. On older MLflow the deprecated
# custom_prompt_judge is the fallback.
policy_citation_judge = make_judge(
    name="policy_citation",
    instructions=(
        "You are grading a Unity Airways support answer.\n"
        "Question: {{ inputs }}\n"
        "Answer: {{ outputs }}\n"
        "Does the answer cite a specific Unity Airways policy (fare rules, refund window, "
        "rebooking policy)? Categorize as 'cited', 'vague', or 'missing'."
    ),
    model=EVAL_MODEL,   # optional; defaults to a Databricks-hosted judge LLM
)

with mlflow.start_run(run_name="08-4-custom-judge") as judge_run:
    judge_result = mlflow.genai.evaluate(
        data=eval_df,
        predict_fn=predict_fn,
        scorers=[policy_citation_judge],
    )

print("Aggregate metrics:", judge_result.metrics)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 8 — Custom CODE scorer with @scorer returning a Feedback  ·  [Hands-on]
# MAGIC Not everything needs an LLM. A **code-based** scorer is deterministic, free, and fast — ideal for
# MAGIC structure / length / format checks. It returns the same `Feedback(value, rationale)` shape as a judge,
# MAGIC so the harness aggregates it uniformly. "A regex should not be replaced by an LLM to find a phone number."

# COMMAND ----------

from mlflow.genai.scorers import scorer
from mlflow.entities import Feedback

@scorer(name="response_length")
def response_length_scorer(outputs) -> Feedback:
    # outputs is whatever predict_fn returned — here a plain string answer
    response = outputs if isinstance(outputs, str) else outputs.get("response", "")
    word_count = len(str(response).split())
    if word_count < 5:
        return Feedback(value=0.0, rationale=f"Response too short ({word_count} words)")
    if word_count > 120:
        return Feedback(value=0.5, rationale=f"Response quite long ({word_count} words)")
    return Feedback(value=1.0, rationale=f"Appropriate length ({word_count} words)")

with mlflow.start_run(run_name="08-4-code-scorer") as code_run:
    code_result = mlflow.genai.evaluate(
        data=eval_df,
        predict_fn=predict_fn,
        scorers=[response_length_scorer],
    )

print("Aggregate metrics:", code_result.metrics)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 9 — Read back per-row results (the rationale, not just the number)  ·  [Hands-on]
# MAGIC The number tells you a row failed; the **rationale** tells you why — off-topic, ungrounded, missed a fact
# MAGIC — so you can fix retrieval or the prompt. Each eval run attaches one trace per row with a `Feedback` per
# MAGIC scorer.

# COMMAND ----------

# Per-row traces + assessments for the combined run (Step 6).
try:
    per_row = mlflow.search_traces(run_id=full_run.info.run_id)
except TypeError:
    # Older signatures don't accept run_id — fall back to the experiment and filter in the UI.
    exp_id = mlflow.get_experiment_by_name(EXPERIMENT_PATH).experiment_id
    per_row = mlflow.search_traces(experiment_ids=[exp_id])

print("Rows scored:", len(per_row))
print("Columns:", list(per_row.columns))
per_row.head()
# NOTE: per-row assessments also render in the MLflow Evaluations UI below each eval cell. The
# EvaluationResult per-row table attribute names are still evolving — the UI + search_traces are the
# stable read paths.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Recap, gotchas and next step
# MAGIC **What you did** — scored the Module 05 chain with MLflow 3 judges and proved the ground-truth split:
# MAGIC - **Reference-free judges** (`RelevanceToQuery`, `Safety`, `RetrievalGroundedness`, `RetrievalRelevance`,
# MAGIC   plain `Guidelines`) scored **every** row — no labels needed.
# MAGIC - **Reference-based judges** (`Correctness`, **`RetrievalSufficiency`**) scored **only** the rows carrying
# MAGIC   `expected_facts` / `expected_response`.
# MAGIC - A **custom judge** via `make_judge(...)` and a **custom code scorer** via `@scorer` -> `Feedback`.
# MAGIC
# MAGIC **Gotchas to remember**
# MAGIC - Pass `scorers=[...]` explicitly — MLflow 3 auto-selects nothing; there is no `agents.evaluate()` and
# MAGIC   `mlflow.evaluate(model_type="databricks-agent")` is the retired MLflow-2 path.
# MAGIC - `RetrievalSufficiency` is **reference-based** — people wrongly file it with the reference-free judges.
# MAGIC - Calling `Correctness` / `RetrievalSufficiency` with no `expectations` scores nothing useful.
# MAGIC - Pin the judge `model=` (the `databricks:/...` URI) or verdicts drift and comparisons get noisy.
# MAGIC - Read the **rationale**, not just the number — that sentence is what turns a red score into a fix.
# MAGIC - Use MLflow-3 class names (`RetrievalGroundedness`, `RelevanceToQuery`, …), never the MLflow-2 names
# MAGIC   (`groundedness`, `chunk_relevance`, `relevance_to_query`, `context_sufficiency`).
# MAGIC
# MAGIC **Next:** the consolidated module lab `08-module-lab.py` runs the full flow — datasets (08.2), code
# MAGIC scorers (08.3), these judges (08.4), comparing `rag_chain` vs `llm_only` (08.5), human feedback (08.6),
# MAGIC calibration (08.8), and traditional metrics (08.10) — then promotes the winner `@champion`. A judge is an
# MAGIC LLM: **calibrate it against human labels (08.8)** before you gate a release on its score.
