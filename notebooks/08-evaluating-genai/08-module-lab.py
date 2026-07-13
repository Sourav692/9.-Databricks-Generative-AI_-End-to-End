# Databricks notebook source
# MAGIC %md
# MAGIC # Module 08 lab — Evaluating the Unity Airways RAG chain end to end
# MAGIC **Roadmap:** Module 08 (Evaluating GenAI applications) · Topics 08.2–08.10 · ★ 08.1 / 08.4 cornerstones · [Theory + Hands-on]
# MAGIC
# MAGIC One runnable lab over the module's hands-on topics, in order, on the Module 05 RAG chain. You build a
# MAGIC versioned eval dataset, write code + judge scorers, run `mlflow.genai.evaluate(...)`, compare the
# MAGIC `rag_chain` against the Module 06 `llm_only` baseline on the SAME dataset, capture human feedback, then
# MAGIC close with calibration + traditional-metric theory and promote the winner `@champion`.
# MAGIC
# MAGIC | Step | Topic | What you do |
# MAGIC |---|---|---|
# MAGIC | 1 | **08.2** | Eval datasets — `create_dataset` / `merge_records` (UC-backed) + a plain-list fallback |
# MAGIC | 2 | **08.3** | Code scorers — `@scorer` -> `Feedback` (deterministic, free) |
# MAGIC | 3 | **08.4** ★ | LLM judges — the scorer set + the ground-truth split; `make_judge` |
# MAGIC | 4 | **08.5** | Compare runs — `rag_chain` vs `llm_only`; change one variable (k=3 -> 5); drill into a trace |
# MAGIC | 5 | **08.6** | Human feedback — `mlflow.log_feedback(...)`; Labeling Sessions |
# MAGIC | 6 | **08.8** | Calibration — thresholds vs human labels (theory) |
# MAGIC | 7 | **08.10** | Traditional metrics — BLEU / ROUGE / perplexity / exact-match vs judges (theory) |
# MAGIC
# MAGIC Cornerstone deep-dives: `eval-harness.md` (08.1) and `llm-as-judge.md` (08.4). The focused 08.4 hands-on is
# MAGIC `08-4-llm-as-judge.py`; this lab layers the full module around it. The chain is from **Module 05**; its
# MAGIC **traces** are from **Module 07**; results anchor to the **LoggedModel** from **Module 06**.
# MAGIC
# MAGIC ## Prerequisites (read before running)
# MAGIC - **Compute:** **serverless notebook/job**, or a **DBR ML runtime** (15.4 LTS ML or later is a safe floor).
# MAGIC - **MLflow:** **>= 3.1** required; **>= 3.4** for `make_judge` (Step 3).
# MAGIC - **The chain from Module 05:** `unity_airways.rag.ua_rag_chain` registered `@champion` in UC. It emits
# MAGIC   RETRIEVER spans (Module 07) that the retrieval judges read. We also **rebuild it locally** so we can vary `k`.
# MAGIC - **Vector Search index (Module 04):** `unity_airways.rag.ua_rag_chunks_index` **ONLINE** on `unity-airways-vs`.
# MAGIC - **Chat + judge endpoint:** **`databricks-claude-sonnet-4-5`** — pinned as the judge model. Confirm on the
# MAGIC   supported-models page.
# MAGIC - **Unity Catalog:** read the index; **write/register to `unity_airways.rag`** (the eval dataset + the alias).
# MAGIC - **Experiment:** a path you can write to (Step 0 `EXPERIMENT_PATH`).
# MAGIC - **Secrets:** none. Managed embeddings + workspace auth need no external key.
# MAGIC - **Learner-set identifiers:** edit the constants in Step 0.
# MAGIC
# MAGIC > 📌 **The one rule of the module:** eval is **`mlflow.genai.evaluate(data=, predict_fn=, scorers=[...])`**
# MAGIC > with `scorers=[...]` **explicit** — never `mlflow.evaluate(model_type="databricks-agent")`, and there is
# MAGIC > no `agents.evaluate()`. Scorers live in `mlflow.genai.scorers`, judges in `mlflow.genai.judges`. It scores
# MAGIC > the **trace**, so the retrieval judges read the Module 07 RETRIEVER span.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 0. Install libraries and set variables
# MAGIC `mlflow[databricks]>=3.4` (the `make_judge` floor), `databricks-langchain` (`ChatDatabricks` +
# MAGIC `DatabricksVectorSearch`), and `databricks-vectorsearch` (the index client). Restart Python so the fresh
# MAGIC installs import.

# COMMAND ----------

# MAGIC %pip install -U "mlflow[databricks]>=3.4" databricks-langchain databricks-vectorsearch
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

import mlflow

CATALOG       = "unity_airways"                            # a catalog you can read from
SCHEMA        = "rag"                                      # the RAG schema from Modules 03/04
UC_MODEL      = f"{CATALOG}.{SCHEMA}.ua_rag_chain"         # three-level UC name — the Module 05 chain
INDEX_NAME    = f"{CATALOG}.{SCHEMA}.ua_rag_chunks_index"  # Module 04 index
VS_ENDPOINT   = "unity-airways-vs"                         # Vector Search endpoint (from Module 04)
CHAT_ENDPOINT = "databricks-claude-sonnet-4-5"            # confirm on the supported-models page

# Pin the JUDGE model so verdicts are stable and comparable across runs. Note the "databricks:/" URI prefix.
EVAL_MODEL    = "databricks:/databricks-claude-sonnet-4-5"

# Learner-set: an experiment path you can write to (usually your own /Users/<you> path).
EXPERIMENT_PATH = "/Users/you@company.com/unity_airways_rag"
APPROVER        = "s.banerjee"                             # who signs off the promotion

mlflow.set_registry_uri("databricks-uc")   # UC-governed registry
mlflow.set_experiment(EXPERIMENT_PATH)      # eval runs + traces attach here

print("UC model    :", UC_MODEL)
print("Judge model :", EVAL_MODEL)
print("Experiment  :", EXPERIMENT_PATH)

# COMMAND ----------

# MAGIC %md
# MAGIC ### Rebuild the Module 05 chain (parameterized by k) and an llm_only baseline
# MAGIC The exact chain shape from `05-3-rag-chain.py`, reassembled here so this lab is self-contained **and** so
# MAGIC we can vary retrieval `k` in Step 4 (a registered model would be pinned to one k). `mlflow.langchain.autolog()`
# MAGIC makes every `.invoke()` emit a trace the retrieval judges can read. The `llm_only` baseline is the bare
# MAGIC model with no retrieval — the Module 06 baseline LoggedModel.

# COMMAND ----------

from databricks_langchain import ChatDatabricks, DatabricksVectorSearch
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough

mlflow.langchain.autolog()   # every .invoke() emits a trace (retrieval judges read the RETRIEVER span)

llm = ChatDatabricks(endpoint=CHAT_ENDPOINT, temperature=0)   # temperature=0 -> reproducible while developing

prompt = ChatPromptTemplate.from_messages([
    ("system",
     "You are the Unity Airways policy assistant. Answer the question using ONLY the "
     "context below. If the context does not contain the answer, say you don't know. "
     "Cite the source_doc you used.\n\nContext:\n{context}"),
    ("human", "{question}"),
])

def format_docs(docs):
    # retriever returns a list[Document]; the prompt slot needs a single string
    return "\n\n".join(d.page_content for d in docs)

def build_rag_chain(k: int):
    # source_doc in columns is what lets the model cite AND lets you debug provenance
    retriever = DatabricksVectorSearch(
        endpoint=VS_ENDPOINT,
        index_name=INDEX_NAME,
        columns=["chunk_id", "content", "source_doc"],
    ).as_retriever(search_kwargs={"k": k})
    # Invoked with a BARE STRING because RunnablePassthrough() forwards the input into {question}.
    return (
        {"context": retriever | format_docs, "question": RunnablePassthrough()}
        | prompt | llm | StrOutputParser()
    )

rag_chain_k5 = build_rag_chain(k=5)   # the current champion config (Module 05 used k=5)
print("Chain rebuilt — same runnable shape Module 06 registered as", UC_MODEL)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 1 · 08.2 — Build and version an evaluation dataset  ·  [Hands-on]
# MAGIC A trustworthy eval starts with a dataset you can version. Schema: `inputs` (required), optional `outputs`
# MAGIC (answer-sheet mode), optional `expectations` (the answer key: `expected_facts` / `expected_response` /
# MAGIC `guidelines`). Some rows carry ground truth (for `Correctness` / `RetrievalSufficiency`), some don't.
# MAGIC
# MAGIC > 💡 **TIP:** Keep the seed set small on purpose — it must be cheap to run often so it catches regressions
# MAGIC > early. Grow it as feedback arrives; retire cases that no longer reflect current policy.

# COMMAND ----------

# The rows the whole lab scores. inputs key "question" -> the predict_fn parameter is named `question`.
eval_rows = [
    {"inputs": {"question": "Can I get a refund on a Basic Economy fare?"},
     "expectations": {"expected_facts": [
         "Basic Economy fares are generally non-refundable.",
         "A full refund is available if cancelled within 24 hours of booking."]}},
    {"inputs": {"question": "Can I change a Lite fare booked yesterday to next Friday?"},
     "expectations": {"guidelines": "Cite the Fare Rules and state that no change is allowed for a Lite fare."}},
    {"inputs": {"question": "My connection was missed — what are my options?"}},
    {"inputs": {"question": "How many carry-on bags are included?"}},
]
print(f"{len(eval_rows)} rows prepared.")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Register it as a UC-backed, versioned dataset (preferred over ad-hoc CSVs)
# MAGIC `create_dataset` makes a governed table; `merge_records` appends rows and auto-creates a new version with
# MAGIC lineage to the experiment.
# MAGIC
# MAGIC > ⚠️ **GOTCHA — limits:** ~**2,000 records** per dataset and **<= 20 expectation fields** per entry; no
# MAGIC > CMEK yet. Prefer archiving over hard-deleting so run lineage stays resolvable. *(Exact limits evolve — verify.)*
# MAGIC >
# MAGIC > 📌 **NOTE — verify the import path:** this lab uses `from mlflow.genai.datasets import create_dataset`.
# MAGIC > Some MLflow builds expose `mlflow.genai.create_dataset` instead — verify against your runtime's docs.
# MAGIC > If the API is unavailable, the plain `eval_rows` list works directly in `mlflow.genai.evaluate(data=...)`.

# COMMAND ----------

UC_DATASET = f"{CATALOG}.{SCHEMA}.eval_dataset"
try:
    from mlflow.genai.datasets import create_dataset, get_dataset
    eval_dataset = create_dataset(name=UC_DATASET)   # governed, versioned UC table
    eval_dataset = eval_dataset.merge_records(eval_rows)   # append rows; auto-versions with lineage
    eval_data = eval_dataset                          # pass the managed dataset straight to evaluate(data=)
    print("Created UC dataset:", UC_DATASET, "| resolve later with get_dataset(name=...)")
except Exception as e:
    # Fallback: the plain list works directly as data= in mlflow.genai.evaluate(...).
    eval_data = eval_rows
    print("Datasets API unavailable here — falling back to the in-memory list.\n", repr(e))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 2 · 08.3 — Code-based scorers (@scorer -> Feedback)  ·  [Hands-on]
# MAGIC Deterministic, free, reproducible — ideal for continuous checks and regression tests. Design principles:
# MAGIC one scorer measures one thing; normalize inputs first; map to a documented 0.0–1.0 scale; prefer code
# MAGIC over an LLM for anything a regex can check.

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

print("Defined code scorer:", response_length_scorer.name)
# Verify later in the eval run: each row shows a response_length value + rationale in the Evaluations UI.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 3 · 08.4 ★ — LLM judges and the ground-truth split  ·  [Theory + Hands-on]
# MAGIC Judges grade meaning where rigid rules run out. Keep the two families separate: **reference-free** run on
# MAGIC any row; **reference-based** need `expectations`. Pin the judge model. (Full deep-dive + a focused notebook:
# MAGIC `08-4-llm-as-judge.py`.)
# MAGIC
# MAGIC > 📌 **IMPORTANT — the split:** `Correctness` and **`RetrievalSufficiency`** need a ground-truth answer
# MAGIC > (`expected_facts` / `expected_response`). `RelevanceToQuery`, `Safety`, `RetrievalGroundedness`,
# MAGIC > `RetrievalRelevance`, and plain `Guidelines` are reference-free.

# COMMAND ----------

from mlflow.genai.scorers import (
    Correctness, RelevanceToQuery, Safety,
    RetrievalGroundedness, RetrievalRelevance, RetrievalSufficiency,
    Guidelines, ExpectationsGuidelines,
)

reference_free = [
    RelevanceToQuery(model=EVAL_MODEL),
    Safety(model=EVAL_MODEL),
    RetrievalGroundedness(model=EVAL_MODEL),
    RetrievalRelevance(model=EVAL_MODEL),
    Guidelines(name="professional_tone",
               guidelines="Professional, courteous airline-support tone; no slang; reference 'Unity Airways'.",
               model=EVAL_MODEL),
]
reference_based = [
    Correctness(model=EVAL_MODEL),            # needs expected_facts / expected_response
    RetrievalSufficiency(model=EVAL_MODEL),   # needs expected_facts / expected_response
    ExpectationsGuidelines(model=EVAL_MODEL), # needs per-row expectations["guidelines"] (scores only rows that define it)
]

# The scorer set the whole lab reuses — code + judges mix freely in one explicit list.
lab_scorers = [response_length_scorer] + reference_free + reference_based
print("Total scorers in lab_scorers:", len(lab_scorers))

# COMMAND ----------

# MAGIC %md
# MAGIC ### Optional — a custom judge with make_judge (MLflow >= 3.4)
# MAGIC Use `make_judge` for a full custom prompt / graded verdict when a built-in doesn't fit.

# COMMAND ----------

from mlflow.genai.judges import make_judge

# NOTE: verify make_judge kwargs vs current docs — young API (needs MLflow >= 3.4); older MLflow used the
# deprecated custom_prompt_judge.
coherence_judge = make_judge(
    name="coherence",
    instructions=(
        "Evaluate if the response is coherent and follows airline policy.\n"
        "Question: {{ inputs }}\nResponse: {{ outputs }}\n"
        "Categorize the response as 'coherent', 'somewhat coherent', or 'incoherent'."
    ),
    model=EVAL_MODEL,
)
print("Defined custom judge:", "coherence")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 4 · 08.5 — Run and compare: rag_chain vs llm_only, and k=3 vs k=5  ·  [Hands-on]
# MAGIC The rule for a fair comparison: **fix the dataset, pin versions, change ONE variable per run, tag it.**
# MAGIC We anchor each run to a **LoggedModel** via `set_active_model` and tag `candidate` / `k` so the runs line
# MAGIC up in the UI. `predict_fn` wraps each chain; the `inputs` key `question` becomes its parameter name.

# COMMAND ----------

def rag_predict_k5(question: str) -> str:
    return rag_chain_k5.invoke(question)          # bare string in -> grounded answer out

def llm_only_predict(question: str) -> str:
    return llm.invoke(question).content           # no retrieval -> nothing to ground in

def evaluate_candidate(predict_fn, candidate, k, run_name):
    mlflow.set_active_model(name=candidate)       # anchor results to a LoggedModel (rag_chain / llm_only)
    with mlflow.start_run(run_name=run_name) as run:
        mlflow.set_tag("candidate", candidate)    # tag so the runs are comparable/filterable in the UI
        mlflow.set_tag("k", str(k))
        result = mlflow.genai.evaluate(data=eval_data, predict_fn=predict_fn, scorers=lab_scorers)
    print(f"[{run_name}] metrics:", result.metrics)
    return run, result

# Baseline: the RAG chain at k=5 (the current champion config).
run_rag5, res_rag5 = evaluate_candidate(rag_predict_k5, "rag_chain", 5, "ua_rag_eval_k5")

# Comparison A — the Module 06 llm_only baseline (no retrieval). Groundedness collapses: no context to
# ground in. This is the evidence that retrieval earns its keep.
run_llm, res_llm = evaluate_candidate(llm_only_predict, "llm_only", 0, "ua_llm_only_eval")

# Comparison B — change ONE variable: k=3 instead of 5. Same dataset, same scorers.
rag_chain_k3 = build_rag_chain(k=3)
def rag_predict_k3(question: str) -> str:
    return rag_chain_k3.invoke(question)
run_rag3, res_rag3 = evaluate_candidate(rag_predict_k3, "rag_chain", 3, "ua_rag_eval_k3")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Compare in the Evaluations UI, then drill from a low score into the trace
# MAGIC In the MLflow UI filter by the `candidate` tag, select the runs, and read the headline metrics side by
# MAGIC side. Expect groundedness to **collapse for `llm_only`** (no context) and the k=5 run to ground at least
# MAGIC as well as k=3. When a metric moves the wrong way, "open the traces that flipped" — the **RETRIEVER span**
# MAGIC shows whether retrieval or generation failed (a baggage chunk pulled for a refund question = fix retrieval,
# MAGIC not the model).

# COMMAND ----------

# Programmatic peek: pull the per-row traces for the k=5 run and eyeball the lowest-scoring rows.
try:
    rag5_traces = mlflow.search_traces(run_id=run_rag5.info.run_id)
except TypeError:
    exp_id = mlflow.get_experiment_by_name(EXPERIMENT_PATH).experiment_id
    rag5_traces = mlflow.search_traces(experiment_ids=[exp_id])

print("rag_chain k=5 rows scored:", len(rag5_traces))
print("Columns:", list(rag5_traces.columns))
rag5_traces.head()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 5 · 08.6 — Capture human-in-the-loop feedback  ·  [Theory + Hands-on]
# MAGIC Scorers miss nuance — tone, empathy, subtle factual gaps. MLflow stores human judgment as an **Assessment**
# MAGIC on a **Trace**, tagged with a `source` (HUMAN / LLM_JUDGE / CODE) so expert sign-off is separable from
# MAGIC noisy thumbs-down clicks. `Feedback` = what the app produced; `Expectations` = what correct looks like
# MAGIC (which becomes the answer key for `Correctness`).

# COMMAND ----------

from mlflow.entities.assessment import AssessmentSource, AssessmentSourceType

# Grab one real trace id from the k=5 run to attach feedback to.
sample_trace_id = None
if len(rag5_traces) and "trace_id" in rag5_traces.columns:
    sample_trace_id = rag5_traces.iloc[0]["trace_id"]

def log_end_user_feedback(trace_id, satisfied, rationale=None, user_id="agent_reviewer"):
    mlflow.log_feedback(
        trace_id=trace_id,
        name="user_feedback",
        value=satisfied,
        rationale=rationale,
        source=AssessmentSource(source_type=AssessmentSourceType.HUMAN, source_id=user_id),
    )

if sample_trace_id:
    log_end_user_feedback(sample_trace_id, satisfied=False,
                          rationale="Missing the 24-hour refund-window detail.")
    print("Logged HUMAN feedback on trace:", sample_trace_id)
else:
    print("No trace_id column found — skipping the feedback demo (open the Traces tab instead).")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Domain-expert review at scale — Labeling Sessions (mention)
# MAGIC For structured expert review, MLflow provides **Labeling Sessions**: a curated queue of traces reviewed
# MAGIC against a **label schema**, each session itself an MLflow Run with a Review App link. Sketch:
# MAGIC ```python
# MAGIC from mlflow.genai.label_schemas import create_label_schema, InputCategorical, InputText
# MAGIC from mlflow.genai.labeling import create_labeling_session
# MAGIC accuracy = create_label_schema(
# MAGIC     name="response_accuracy", type="feedback",
# MAGIC     title="Is the response factually accurate?",
# MAGIC     input=InputCategorical(options=["Accurate", "Partially Accurate", "Inaccurate"]), overwrite=True)
# MAGIC ideal = create_label_schema(
# MAGIC     name="expected_response", type="expectation",
# MAGIC     title="What would be the ideal response?", input=InputText(), overwrite=True)
# MAGIC session = create_labeling_session(name="refund_policy_review",
# MAGIC                                    label_schemas=[accuracy.name, ideal.name])
# MAGIC session.add_traces(mlflow.search_traces(
# MAGIC     filter_string="assessments.user_feedback = false", max_results=20))
# MAGIC print("Share with experts:", session.url)   # Review App link
# MAGIC ```
# MAGIC Expert labels then build the ground-truth `expectations` for future `Correctness` runs.
# MAGIC
# MAGIC > ⚠️ **GOTCHA:** Treat user comments as personal data — if policy forbids storing raw text, record a
# MAGIC > category code + a hashed session id. Developer feedback is advisory until a designated reviewer signs off.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 6 · 08.8 — Calibrating a judge against human labels  ·  [Theory]
# MAGIC A judge is a model with opinions; a threshold is a product decision. Calibrate both with a small human-
# MAGIC labeled slice so "0.9 groundedness" means what you think it means.
# MAGIC 1. Sample traces; get **human** groundedness labels (grounded / not) — e.g. from a Labeling Session (08.6).
# MAGIC 2. Run `RetrievalGroundedness` on the same traces.
# MAGIC 3. Measure **agreement**; if judge and humans diverge, refine the rubric, pin/swap the judge model, or move
# MAGIC    the pass threshold.
# MAGIC 4. Re-check agreement. Version thresholds like code (patch = clearer rationale, minor = adjusted thresholds,
# MAGIC    major = new scale — run old + new in parallel at low sample rate before switching).
# MAGIC
# MAGIC > 💡 **TIP:** For a length scorer the book lands on **Pass = 40–110 words, Review = 25–39 or 111–140,
# MAGIC > Fail = < 25 or > 140** — recorded WITH the scorer version and validated per slice (Lite fares, multi-segment).

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 7 · 08.10 — Traditional text metrics vs LLM judges  ·  [Theory]
# MAGIC Reference-based NLG metrics are cheap, deterministic, and comparable — but blind to grounding and
# MAGIC hallucination.
# MAGIC
# MAGIC | Metric | Measures | Needs | Good for | Blind to |
# MAGIC |---|---|---|---|---|
# MAGIC | **ROUGE** | Recall-oriented n-gram overlap | Reference answer(s) | Summarization | Meaning; paraphrase |
# MAGIC | **BLEU** | Precision-oriented n-gram overlap | Reference answer(s) | Machine translation | Meaning; paraphrase |
# MAGIC | **BERTScore** | Semantic similarity via embeddings | Reference answer(s) | Paraphrase-tolerant comparison | Factual grounding |
# MAGIC | **Perplexity** | How well an LM predicts a text (lower = better) | Token probabilities | Intrinsic fluency | Task correctness; grounding |
# MAGIC | **Exact-match** | Binary string equality | Exact reference | Extractive / closed-form QA | Anything phrased differently |
# MAGIC
# MAGIC - **Use them** for clean-reference tasks near translation/summarization/extractive-QA, or an intrinsic
# MAGIC   fluency signal (perplexity), or a single canonical answer (exact-match).
# MAGIC - **Prefer LLM judges** for open-ended RAG answers where "correct" can be phrased many ways and where
# MAGIC   grounding + safety matter. In MLflow they're ordinary metrics: `mlflow.log_metric("rouge_score", 0.78)`.
# MAGIC
# MAGIC > ⚠️ **GOTCHA:** A high BLEU/ROUGE against one reference can still be a **hallucination** if the reply
# MAGIC > invents a policy the reference happened to phrase similarly. Use these as a cheap first filter, never as
# MAGIC > the promotion gate for a policy-answering RAG app.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Recap, gotchas and next step
# MAGIC **What you built** — the module's hands-on topics, in order, on the Module 05 chain:
# MAGIC - **08.2 datasets:** a small `inputs` / `expectations` set, versioned UC-backed via `create_dataset` /
# MAGIC   `merge_records`, with a plain-list fallback.
# MAGIC - **08.3 code scorers:** `@scorer` -> `Feedback` (deterministic `response_length`).
# MAGIC - **08.4 judges:** reference-free + reference-based lists (the ground-truth split), plus `make_judge`.
# MAGIC - **08.5 compare:** `rag_chain` (k=5) vs `llm_only` vs `rag_chain` (k=3) on the SAME dataset, tagged and
# MAGIC   anchored to LoggedModels; drilled a low score into its trace.
# MAGIC - **08.6 human feedback:** `mlflow.log_feedback(...)` with a HUMAN `AssessmentSource`; Labeling Sessions.
# MAGIC - **08.8 calibration** and **08.10 traditional metrics** (theory).
# MAGIC
# MAGIC **Gotchas to remember**
# MAGIC - `scorers=[...]` is **required** — MLflow 3 auto-selects nothing; no `agents.evaluate()`.
# MAGIC - `RetrievalSufficiency` is **reference-based** (needs `expectations`) — don't file it as reference-free.
# MAGIC - Change **one** variable per run and keep the dataset fixed, or the comparison is meaningless.
# MAGIC - Score the **trace**, not the string — retrieval/groundedness/latency live in spans.
# MAGIC - Don't trust a judge's number until you've **calibrated it against human labels** (08.8).

# COMMAND ----------

# MAGIC %md
# MAGIC ### Promote the winner to @champion (Module 06 mechanics)
# MAGIC Pick the winner from the metrics above (expected: `rag_chain` at k=5). In practice you log/register the
# MAGIC winning config as a **new version** (Module 06 flow), then repoint the `@champion` alias to it — apps and
# MAGIC endpoints reference `models:/{UC_MODEL}@champion`, so promotion is a one-line alias move with no client change.

# COMMAND ----------

from mlflow import MlflowClient
client = MlflowClient()
try:
    champ = client.get_model_version_by_alias(UC_MODEL, "champion")
    print(f"Current champion: {UC_MODEL} v{champ.version} | tags: {champ.tags}")
    # After registering the winning config as a new version (Module 06), promote it:
    # client.set_registered_model_alias(name=UC_MODEL, alias="champion", version="<winning_version>")
    # client.set_model_version_tag(UC_MODEL, "<winning_version>", "eval_passed", "true")
    # client.set_model_version_tag(UC_MODEL, "<winning_version>", "approver", APPROVER)
except Exception as e:
    print("No champion alias resolved yet — register the winning version first (Module 06).\n", repr(e))

# COMMAND ----------

# MAGIC %md
# MAGIC **Next:**
# MAGIC - **Module 11 — deploy** the promoted `@champion` version to a Model Serving endpoint (the same scorers
# MAGIC   travel with it).
# MAGIC - **Module 13 — monitor** production traffic with these exact scorers, so a groundedness drop alerts
# MAGIC   before a customer complains. Evaluation is the instrument you build once and reuse offline **and** online.
