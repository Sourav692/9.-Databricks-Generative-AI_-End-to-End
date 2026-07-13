# Databricks notebook source
# MAGIC %md
# MAGIC # Capstone C2 — Evaluate, Trace & Version the RAG App
# MAGIC **Build after P2 / Modules 06–08 · extends C1 · [Hands-on]**
# MAGIC
# MAGIC The Unity Airways support bot from **Capstone C1** works in a demo. A passenger asks *"Can I get a
# MAGIC refund on a Basic Economy fare?"* and it answers. Then your lead asks the two questions you can't
# MAGIC answer yet:
# MAGIC
# MAGIC - **Is it actually good?** Not "did it reply" — is the answer correct, grounded in real policy,
# MAGIC   on-topic, and safe, across the *whole* set of questions people ask?
# MAGIC - **Did the last change make it better or worse?** Someone edited the prompt last week. Did quality
# MAGIC   go up, or did you just change wording and hope?
# MAGIC
# MAGIC C2 closes that gap. It does **not** rebuild the C1 chain — it wraps MLOps rigor around
# MAGIC `unity_airways.rag.ua_rag_chain`: tracing, an evaluation dataset, a scorer suite, a fair v1-vs-v2
# MAGIC prompt comparison, and a defensible promotion behind a `@champion` alias you can roll back in one line.
# MAGIC You finish with evidence, not vibes.
# MAGIC
# MAGIC | Milestone | What you do |
# MAGIC |---|---|
# MAGIC | **M1** | Instrument tracing — `autolog()` + manual spans + `set_active_model`; one invoke = one trace |
# MAGIC | **M2** | Build a UC-backed, versioned evaluation dataset — labeled + deliberately unlabeled rows |
# MAGIC | **M3** | Assemble the scorer suite — the ground-truth vs reference-free split, in two lists |
# MAGIC | **M4** | Register prompt **v2**, evaluate v1 vs v2 on the same dataset, diagnose a regression via a trace |
# MAGIC | **M5** | Promote `@champion` on **both** the model and the prompt; write the quality scorecard |
# MAGIC
# MAGIC The through-line: Module 05 *built* the chain, Module 07 made it *observable*, Module 06 gave it a
# MAGIC *version*, and Module 08 makes every change **decidable**. C2 wires those four together on one artifact.
# MAGIC
# MAGIC ## Prerequisites (read before running)
# MAGIC - **Compute:** **serverless notebook/job**, or a **DBR ML runtime** (15.4 LTS ML or later is a safe floor).
# MAGIC   > ⚠️ On **serverless**, GenAI autologging is **not** auto-enabled — you call `mlflow.langchain.autolog()`
# MAGIC   > yourself (M1). That is the portable habit anyway.
# MAGIC - **MLflow:** **≥ 3.1** required (`mlflow.genai.evaluate`, tracing, LoggedModel, Prompt Registry).
# MAGIC   Use **≥ 3.4** only if you add a custom judge with `make_judge()` (optional, noted in M3).
# MAGIC - **The C1 chain registered:** `unity_airways.rag.ua_rag_chain` in Unity Catalog, loadable via
# MAGIC   `models:/...@champion` or a pinned version. M1 loads it defensively.
# MAGIC - **The C1 prompt registered:** `unity_airways.rag.ua_rag_prompt` (**v1**) in the MLflow Prompt Registry,
# MAGIC   with `{{context}}` / `{{question}}` variables. C2 adds **v2** on top. If this is a fresh workspace,
# MAGIC   Section 0 seeds the same v1 so the notebook runs end to end. The Prompt Registry is **Beta** on
# MAGIC   Databricks — `mlflow[databricks]>=3.1.0` and a UC schema where you hold `CREATE FUNCTION` / `EXECUTE` / `MANAGE`.
# MAGIC - **Vector Search index (Module 04):** `unity_airways.rag.ua_rag_chunks_index` **ONLINE** on endpoint
# MAGIC   **`unity-airways-vs`** (built over `content`, keyed on `chunk_id`, with `source_doc` synced).
# MAGIC - **Judge / chat endpoint:** **`databricks-claude-sonnet-4-5`** — pinned as the judge model for stable,
# MAGIC   comparable scores. Endpoint names churn — confirm on the supported-models page.
# MAGIC - **Unity Catalog rights:** read the index; create a dataset and register a model version + move
# MAGIC   aliases/tags in `unity_airways.rag`.
# MAGIC - **Learner-set identifiers:** edit the constants in Section 0.
# MAGIC
# MAGIC > 📌 **The single rule of this capstone:** MLflow 3 evaluation is
# MAGIC > **`mlflow.genai.evaluate(data=, predict_fn=, scorers=[...])`** with an **explicit** scorer list.
# MAGIC > Never `mlflow.evaluate(model_type="databricks-agent")` (retired MLflow-2 path), and there is **no**
# MAGIC > `agents.evaluate()`. `Correctness` and `RetrievalSufficiency` are the two **reference-based** built-ins;
# MAGIC > UC promotion is an **alias**, never a stage.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 0. Install & set variables
# MAGIC `mlflow[databricks]>=3.4` (a safe floor that also covers the optional `make_judge`), `databricks-langchain`
# MAGIC (`ChatDatabricks` + `DatabricksVectorSearch`), and `databricks-vectorsearch` (the index client). Restart
# MAGIC Python so the fresh installs import.

# COMMAND ----------

# MAGIC %pip install -U "mlflow[databricks]>=3.4" databricks-langchain databricks-vectorsearch
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

import mlflow

# --- Canonical Unity Airways names (do not rename — C1/C2 share these) ---
CATALOG       = "unity_airways"                            # a catalog you can read/write
SCHEMA        = "rag"                                      # the RAG schema from Modules 03/04
UC_MODEL      = f"{CATALOG}.{SCHEMA}.ua_rag_chain"         # the C1 chain, registered in UC
UC_PROMPT     = f"{CATALOG}.{SCHEMA}.ua_rag_prompt"        # the C1 prompt (v1); C2 registers v2 under this name
UC_DATASET    = f"{CATALOG}.{SCHEMA}.eval_dataset"         # the versioned eval dataset we build in M2
INDEX_NAME    = f"{CATALOG}.{SCHEMA}.ua_rag_chunks_index"  # Module 04 index (retrieval judges read its spans)
VS_ENDPOINT   = "unity-airways-vs"                         # Vector Search endpoint (from Module 04)
CHAT_ENDPOINT = "databricks-claude-sonnet-4-5"            # confirm on the supported-models page

# Pin the JUDGE model so verdicts are stable and comparable across runs. Note the "databricks:/" URI prefix.
EVAL_MODEL    = "databricks:/databricks-claude-sonnet-4-5"

# Learner-set: an experiment path you can write to (usually your own /Users/<you> path).
EXPERIMENT_PATH = "/Users/you@company.com/unity_airways_rag"
APPROVER        = "s.banerjee"                             # who signs off the promotion
CHANGE_TICKET   = "CHG-2187"                               # the ticket that authorized the promotion

# The running example — a policy question the assistant has answered confidently and WRONG before.
QUESTION = "Can I get a refund on a Basic Economy fare?"

mlflow.set_registry_uri("databricks-uc")   # UC-governed registry (models AND prompts live here)
mlflow.set_experiment(EXPERIMENT_PATH)      # eval runs + traces attach here

print("UC model    :", UC_MODEL)
print("UC prompt   :", UC_PROMPT)
print("Eval dataset:", UC_DATASET)
print("Judge model :", EVAL_MODEL)
print("Experiment  :", EXPERIMENT_PATH)

# COMMAND ----------

# MAGIC %md
# MAGIC ### Self-containment — make sure prompt **v1** exists
# MAGIC C1 registered `ua_rag_prompt` v1. If you're on a fresh workspace, seed the **same** v1 (same
# MAGIC `{{context}}` / `{{question}}` variables) so the rest of C2 runs. Registering under an existing name
# MAGIC would mint a new version, so we only seed when v1 is genuinely missing.

# COMMAND ----------

# The C1 v1 template — grounded, cite-the-source. Double-brace {{var}} is the Prompt Registry syntax.
V1_TEMPLATE = (
    "You are a customer-support assistant for Unity Airways. "
    "Answer ONLY from the retrieved context; if it is missing, say you don't know. "
    "Always name the source document.\n\n"
    "Context:\n{{context}}\n\nQuestion: {{question}}\n\nGrounded answer:"
)

V1_VERSION = 1   # the C1 baseline version we compare against in M4
try:
    mlflow.genai.load_prompt(f"prompts:/{UC_PROMPT}/{V1_VERSION}")
    print(f"Prompt v1 already registered (from C1): prompts:/{UC_PROMPT}/{V1_VERSION}")
except Exception as e:
    seeded = mlflow.genai.register_prompt(
        name=UC_PROMPT,
        template=V1_TEMPLATE,
        commit_message="v1: grounded, cite-the-source RAG prompt (seeded for C2 self-containment)",
        tags={"use_case": "support_rag", "owner": "unity-airways-rag"},
    )
    V1_VERSION = seeded.version
    print(f"Seeded prompt v1: {seeded.name} v{seeded.version}\n(reason it wasn't found: {e!r})")

# COMMAND ----------

# MAGIC %md
# MAGIC ## M1 · Instrument tracing  ·  (07.2 / 07.3)
# MAGIC Make every request observable and pin it to a version. Two moves cover most of it: turn on
# MAGIC **`autolog()`** for the framework spans, then add **manual spans** for the code autolog can't see.
# MAGIC MLflow merges both into one trace — you never wire parent to child by hand. `set_active_model(...)`
# MAGIC binds the traces we produce to a **LoggedModel** version, which is the thread M3/M4 evaluation pulls on.
# MAGIC
# MAGIC The chain we observe **loads its prompt from the registry by URI** (the C1 discipline) rather than
# MAGIC holding an inline string. Building it around a prompt URI is also what lets M4 swap v1 for v2 with
# MAGIC nothing else changing — a *registered* chain is pinned to one prompt, so it can't do the comparison alone.

# COMMAND ----------

mlflow.langchain.autolog()   # AUTO: every LangChain .invoke() now emits a trace (retriever + prompt + LLM spans)

# Pin the version: bind the traces we're about to produce to a LoggedModel (Module 06). Name it after the
# prompt version under test so results are attributable.
active = mlflow.set_active_model(name="ua_rag_chain_v1")
print("Autolog on. MLflow:", mlflow.__version__)
print("LoggedModel:", active.name, "| model_id:", active.model_id)

# COMMAND ----------

# MAGIC %md
# MAGIC ### Build the chain we observe (loads the registry prompt by URI)
# MAGIC The same runnable shape C1 registered: a managed-embeddings retriever over the Module 04 index → the
# MAGIC **registry** prompt → `ChatDatabricks` → `StrOutputParser`. `build_rag_chain(prompt_uri)` is the factory
# MAGIC M3/M4 reuse — pass a different prompt URI and everything else stays fixed. The chain is invoked with a
# MAGIC **bare string** (`RunnablePassthrough` forwards it into `{question}`), so `predict_fn` returns
# MAGIC `chain.invoke(question)`.

# COMMAND ----------

from databricks_langchain import ChatDatabricks, DatabricksVectorSearch
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough

llm = ChatDatabricks(endpoint=CHAT_ENDPOINT, temperature=0)   # temperature=0 -> reproducible, comparable runs

def format_docs(docs):
    # retriever returns a list[Document]; the prompt slot needs a single string
    return "\n\n".join(d.page_content for d in docs)

def build_rag_chain(prompt_uri: str, k: int = 5):
    """Assemble the C1 chain around a SPECIFIC registry prompt version. The prompt URI is the only knob M4 turns."""
    loaded = mlflow.genai.load_prompt(prompt_uri)                 # governed, versioned UC artifact
    prompt = PromptTemplate.from_template(loaded.to_single_brace_format())  # {{var}} -> {var} for LangChain
    retriever = DatabricksVectorSearch(
        endpoint=VS_ENDPOINT,
        index_name=INDEX_NAME,
        columns=["chunk_id", "content", "source_doc"],           # source_doc lets the model cite AND lets you debug
    ).as_retriever(search_kwargs={"k": k})
    return (
        {"context": retriever | format_docs, "question": RunnablePassthrough()}
        | prompt | llm | StrOutputParser()
    )

V1_URI  = f"prompts:/{UC_PROMPT}/{V1_VERSION}"
chain_v1 = build_rag_chain(V1_URI)
print("Chain built around", V1_URI)

# COMMAND ----------

# MAGIC %md
# MAGIC ### (Defensive) load the registered C1 chain by alias
# MAGIC C2 is meant to wrap rigor around the *registered* C1 artifact. Confirm it exists and round-trips. If it
# MAGIC isn't in this workspace, we fall back to the factory chain above — same canonical names, so the eval still
# MAGIC runs end to end. (The C1 registered chain takes `{"messages":[...]}`; the factory takes a bare string.)

# COMMAND ----------

registered_chain = None
try:
    registered_chain = mlflow.langchain.load_model(f"models:/{UC_MODEL}@champion")
    print(f"Loaded registered C1 chain: models:/{UC_MODEL}@champion")
except Exception as e:
    print(f"Registered C1 chain not loadable here — using the factory chain for C2.\n  reason: {e!r}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Manual spans — the pre-step and a custom RETRIEVER span
# MAGIC Autolog can't see code *you* wrote. `@mlflow.trace` traces a whole function (its args become span inputs,
# MAGIC its return becomes span outputs). A custom retriever must set `span_type=SpanType.RETRIEVER` and return
# MAGIC `mlflow.entities.Document`s so retrieved docs **render as documents** — which is exactly what lets the M3
# MAGIC retrieval scorers read context. (For the built-in `DatabricksVectorSearch` retriever, autolog already
# MAGIC emits a correct RETRIEVER span; this shows the pattern for a hand-written one.)

# COMMAND ----------

from mlflow.entities import SpanType, Document

@mlflow.trace   # a manual pre-step span autolog would otherwise miss
def preprocess_question(raw: str) -> str:
    # normalize before the chain sees it — expands "BE fare" so retrieval matches "Basic Economy fare"
    return raw.strip().replace("BE fare", "Basic Economy fare")

@mlflow.trace(span_type=SpanType.RETRIEVER, name="ua_retriever",
              attributes={"vs_type": "databricks_vector_search"})
def retrieve_as_documents(q: str, k: int = 5):
    span = mlflow.get_current_active_span()
    span.set_attributes({"retriever_k": k})
    raw = DatabricksVectorSearch(
        endpoint=VS_ENDPOINT, index_name=INDEX_NAME,
        columns=["chunk_id", "content", "source_doc"],
    ).as_retriever(search_kwargs={"k": k}).invoke(q)             # LangChain Documents
    return [Document.from_langchain_document(d) for d in raw]     # -> MLflow Documents (valid RETRIEVER schema)

print("Manual span helpers defined.")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Invoke once — one request, one trace
# MAGIC A single `chain.invoke(...)` produces one full trace. Open it and read the **RETRIEVER span first**: did the
# MAGIC refund / fare-rules chunk come back? If it returned baggage chunks instead, the bug is upstream in retrieval,
# MAGIC not the model.

# COMMAND ----------

clean_q = preprocess_question(QUESTION)   # -> its own manual span
answer  = chain_v1.invoke(clean_q)        # -> AUTO retriever + prompt + LLM spans, all under one trace
print(answer[:400])

# COMMAND ----------

# MAGIC %md
# MAGIC ### How to verify it worked  *(M1 acceptance)*
# MAGIC - The cell above renders an inline **MLflow Trace UI**: one trace with nested retriever / prompt / LLM spans,
# MAGIC   and the retrieved docs render **as documents** (not a raw JSON blob).
# MAGIC - The trace is attributed to the `ua_rag_chain_v1` LoggedModel and is findable with `search_traces(...)`.
# MAGIC - `search_traces` takes **`experiment_ids=[...]`** — there is **no `experiment_names=`** argument (it raises `TypeError`).
# MAGIC - The `filter_string` prefix grammar (`attributes.` / `tags.`) is still evolving — verify against current MLflow docs if a filter returns nothing.

# COMMAND ----------

EXPERIMENT_ID = mlflow.get_experiment_by_name(EXPERIMENT_PATH).experiment_id
ok_traces = mlflow.search_traces(
    experiment_ids=[EXPERIMENT_ID],
    filter_string="attributes.status = 'OK'",   # single quotes, AND-only, case sensitive
)
print("OK traces in this experiment:", len(ok_traces))
print("Columns:", list(ok_traces.columns))
# Trace export can lag the invoke on a cold run — treat 0 as "re-run", not a hard failure.
if len(ok_traces) == 0:
    print("⚠️  0 traces yet — export can lag the invoke; wait a few seconds and re-run this cell.")
ok_traces.head()

# COMMAND ----------

# MAGIC %md
# MAGIC ## M2 · Build the evaluation dataset  ·  (08.2)
# MAGIC A trustworthy eval starts with a dataset you can **version**. Assemble it from three sources: replayed C1
# MAGIC traces (real questions), expert-labeled policy answers (the gold standard), and hand-written edge cases
# MAGIC (ambiguous, multi-part, conflicting-policy).
# MAGIC
# MAGIC Schema per row: `inputs` (required; the `question` key becomes the `predict_fn` parameter), optional
# MAGIC `expectations` (the answer key: `expected_facts` / `expected_response`). **Refund and fare-rules rows carry
# MAGIC `expected_facts`; some rows are deliberately left unlabeled** — that is how we later prove the reference-free
# MAGIC scorers still run on rows with no ground truth.
# MAGIC
# MAGIC > 💡 **TIP:** Keep the seed set small on purpose so it's cheap to run after every change. Grow it as
# MAGIC > feedback arrives; retire cases that no longer reflect current policy.

# COMMAND ----------

# ~24 Unity Airways rows across refund / rebooking / baggage / fare-rules, easy + hard.
# LABELED rows (expected_facts / expected_response) -> Correctness + RetrievalSufficiency can score them.
# UNLABELED rows -> only reference-free scorers apply (that skip is the visible proof in M3).
eval_rows = [
    # --- refund · labeled (expected_facts) ---
    {"inputs": {"question": "Can I get a refund on a Basic Economy fare?"},
     "expectations": {"expected_facts": [
         "Basic Economy fares are generally non-refundable.",
         "A full refund is available if cancelled within 24 hours of booking."]}},
    {"inputs": {"question": "Can I cancel a Basic Economy ticket 30 minutes after booking without a fee?"},
     "expectations": {"expected_facts": [
         "Cancellation within 24 hours of booking is free.",
         "A full refund is issued to the original form of payment."]}},
    {"inputs": {"question": "Is Basic Economy refundable after the 24-hour window has passed?"},
     "expectations": {"expected_facts": [
         "After 24 hours a Basic Economy fare is non-refundable.",
         "Government taxes and fees may still be refundable on request."]}},
    {"inputs": {"question": "I have a Flex fare — can I get a full refund if I cancel?"},
     "expectations": {"expected_facts": [
         "Flex fares are fully refundable before departure.",
         "The refund goes to the original form of payment."]}},
    {"inputs": {"question": "Are taxes and fees refunded on an unused non-refundable ticket?"},
     "expectations": {"expected_facts": [
         "Government-imposed taxes and fees are refundable on an unused ticket.",
         "The base fare on a non-refundable ticket is not refunded."]}},
    # --- refund · conflicting policy (planted regression / diagnosis candidate) ---
    {"inputs": {"question": "My Basic Economy flight was cancelled by Unity Airways — refund or rebook?"},
     "expectations": {"expected_facts": [
         "When Unity Airways cancels the flight, a full refund is available regardless of fare type.",
         "The passenger may instead choose free rebooking on the next available flight."]}},
    # --- fare-rules · labeled ---
    {"inputs": {"question": "What are the change rules for a Lite fare?"},
     "expectations": {"expected_facts": [
         "Lite fares do not permit changes.",
         "To travel on a different flight the passenger must buy a new ticket."]}},
    {"inputs": {"question": "Does a Standard fare allow date changes?"},
     "expectations": {"expected_facts": [
         "Standard fares allow date changes.",
         "A fare difference and possibly a change fee apply."]}},
    # --- baggage · labeled (expected_response — a single gold answer) ---
    {"inputs": {"question": "How many carry-on bags are included?"},
     "expectations": {"expected_response":
         "One personal item plus one carry-on bag are included on all fares."}},
    {"inputs": {"question": "Is a checked bag included on a Basic Economy fare?"},
     "expectations": {"expected_response":
         "Basic Economy does not include a checked bag; checked bags are available for a fee."}},
    # --- rebooking · unlabeled (reference-free only) ---
    {"inputs": {"question": "My connection was missed — what are my options?"}},
    {"inputs": {"question": "How do I change an existing booking?"}},
    {"inputs": {"question": "What happens if my flight is delayed overnight?"}},
    {"inputs": {"question": "Can I rebook for free if my connection is cancelled?"}},
    # --- baggage / services · unlabeled ---
    {"inputs": {"question": "Can I bring my dog in the cabin?"}},
    {"inputs": {"question": "Do you offer wheelchair assistance at the gate?"}},
    {"inputs": {"question": "Can I select seats for free on a Lite fare?"}},
    # --- edge cases · ambiguous / multi-part / vague (unlabeled on purpose) ---
    {"inputs": {"question": "Can I get a refund and rebook on a Lite fare after a missed connection?"}},
    {"inputs": {"question": "Refund policy?"}},                                   # too vague
    {"inputs": {"question": "Change my Basic Economy flight and add a checked bag."}},  # multi-part
    {"inputs": {"question": "Can I get a refund on an award (points) booking?"}},
    {"inputs": {"question": "What's the fare difference if I upgrade Lite to Flex mid-trip?"}},
    {"inputs": {"question": "What's the checked-bag fee?"}},
    {"inputs": {"question": "If Unity Airways delays my flight 6 hours, am I owed compensation?"}},
]

labeled = sum("expectations" in r for r in eval_rows)
print(f"{len(eval_rows)} rows | labeled: {labeled} | unlabeled: {len(eval_rows) - labeled}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Register it as a UC-backed, versioned dataset
# MAGIC `create_dataset` makes a governed table; `merge_records` appends rows and auto-creates a new version with
# MAGIC lineage to the experiment. Prefer this over ad-hoc CSVs so a future incident review can answer "which
# MAGIC dataset version produced these scores?".
# MAGIC
# MAGIC > ⚠️ **GOTCHA — limits (verify against your runtime):** ~2,000 records per dataset and ≤ 20 expectation
# MAGIC > fields per entry. Prefer archiving over hard-deleting so run lineage stays resolvable. If the datasets
# MAGIC > API isn't available, the plain `eval_rows` list works directly as `data=` in `mlflow.genai.evaluate(...)`.

# COMMAND ----------

DATASET_VERSION = "unversioned"
try:
    from mlflow.genai.datasets import create_dataset, get_dataset
    try:
        eval_dataset = get_dataset(name=UC_DATASET)          # reuse if it already exists (re-runs)
        print("Reusing existing dataset:", UC_DATASET)
    except Exception:
        eval_dataset = create_dataset(name=UC_DATASET)       # governed, versioned UC table
        print("Created UC dataset:", UC_DATASET)
    eval_dataset = eval_dataset.merge_records(eval_rows)      # append rows; auto-versions with lineage
    eval_data = eval_dataset                                  # pass the managed dataset straight to evaluate(data=)
    DATASET_VERSION = str(getattr(eval_dataset, "version", "latest"))
    print("Dataset version:", DATASET_VERSION)
except Exception as e:
    eval_data = eval_rows                                     # fallback: the in-memory list works directly
    print("Datasets API unavailable here — falling back to the in-memory list.\n", repr(e))

# COMMAND ----------

# MAGIC %md
# MAGIC ### How to verify it worked  *(M2 acceptance)*
# MAGIC - The dataset is UC-backed and **versioned** — visible under `unity_airways.rag` → the dataset resolves via
# MAGIC   `get_dataset(name=...)`.
# MAGIC - ~20–40 rows spanning refund / rebooking / baggage / fare-rules across easy and hard.
# MAGIC - Refund and fare-rules rows carry `expected_facts`; some rows are deliberately **unlabeled**.

# COMMAND ----------

print(f"Rows: {len(eval_rows)} | labeled: {labeled} | unlabeled: {len(eval_rows) - labeled}")
print("Dataset name   :", UC_DATASET)
print("Dataset version:", DATASET_VERSION)

# COMMAND ----------

# MAGIC %md
# MAGIC ## M3 · Assemble the scorer suite  ·  (08.3 / 08.4)
# MAGIC One explicit `scorers=[...]` list that covers the quality dimensions and makes the **ground-truth split
# MAGIC structural** — two lists in code, so "does this scorer need a label?" is answered by which list it's in.
# MAGIC
# MAGIC | Bucket | Scorers | Needs a labeled answer? |
# MAGIC |---|---|---|
# MAGIC | **Reference-free** | `RelevanceToQuery`, `Safety`, `RetrievalGroundedness`, `RetrievalRelevance`, plain `Guidelines` | No — runs on every row and on live traffic |
# MAGIC | **Reference-based** | `Correctness`, **`RetrievalSufficiency`** | Yes — `expected_facts` / `expected_response` |
# MAGIC | **Code metric** | one `@scorer` (deterministic, no tokens) | No — pure Python |
# MAGIC
# MAGIC > ⚠️ **GOTCHA:** `RetrievalSufficiency` is the one people misfile. It is **reference-based** — it checks
# MAGIC > whether retrieval fetched enough to support the *expected* facts, so it needs `expectations` just like
# MAGIC > `Correctness`. Pin every judge to `EVAL_MODEL` or verdicts drift and the v1-vs-v2 comparison gets noisy.

# COMMAND ----------

from mlflow.genai.scorers import (
    Correctness, RetrievalSufficiency,           # reference-based — need expectations
    RelevanceToQuery, RetrievalGroundedness,     # reference-free
    RetrievalRelevance, Safety, Guidelines,      # reference-free
    scorer,
)
from mlflow.entities import Feedback

@scorer(name="cites_policy")                      # deterministic code metric — no tokens, reproducible
def cites_policy(outputs) -> Feedback:
    text = outputs if isinstance(outputs, str) else outputs.get("response", "")
    hit = any(k in str(text) for k in ("Fare Rules", "fare rules", "policy", "source", "§"))
    return Feedback(value=1.0 if hit else 0.0,
                    rationale="cites a policy / source reference" if hit else "no policy citation found")

# The split, kept structural — the reference-free list is exactly what you reuse for production monitoring (Module 13).
reference_free = [
    RelevanceToQuery(model=EVAL_MODEL),       # does the answer address the question?
    Safety(model=EVAL_MODEL),                 # toxic / harmful / PII content?
    RetrievalGroundedness(model=EVAL_MODEL),  # answer supported by retrieved context? (reads the trace)
    RetrievalRelevance(model=EVAL_MODEL),     # are the retrieved docs relevant? (reads the trace)
    Guidelines(name="professional_tone",      # a plain-English global rule (reference-free)
               guidelines="Professional, courteous Unity Airways support tone; no invented policy.",
               model=EVAL_MODEL),
]
reference_based = [
    Correctness(model=EVAL_MODEL),            # NEEDS expected_facts / expected_response
    RetrievalSufficiency(model=EVAL_MODEL),   # NEEDS expected_facts / expected_response (reads the trace)
]

# One explicit list the whole capstone reuses — code + reference-free + reference-based mix freely.
ua_scorers = [cites_policy] + reference_free + reference_based
print("reference-free:", len(reference_free),
      "| reference-based:", len(reference_based),
      "| total in ua_scorers:", len(ua_scorers))

# COMMAND ----------

# MAGIC %md
# MAGIC ### Validate ONE row before scoring the whole set
# MAGIC The #1 eval failure is a run that finishes with **zero traces** because the row schema doesn't match what
# MAGIC `predict_fn` expects. The `inputs` key is `question`, so the parameter must be named `question`. Smoke-test
# MAGIC one call first — cheap insurance.

# COMMAND ----------

def make_predict_fn(prompt_uri: str, k: int = 5):
    chain = build_rag_chain(prompt_uri, k=k)
    def predict_fn(question: str) -> str:      # inputs key "question" -> this parameter name
        return chain.invoke(question)          # bare string in -> grounded answer out
    return predict_fn

predict_v1 = make_predict_fn(V1_URI)
print(predict_v1("Can I get a refund on a Basic Economy fare?")[:250])   # one row, validated

# COMMAND ----------

# MAGIC %md
# MAGIC ### Prove the split — reference-based scorers skip unlabeled rows
# MAGIC Run the full suite on a **small 3-row slice** (one labeled refund row + two unlabeled). The reference-free
# MAGIC scorers score all three; `Correctness` / `RetrievalSufficiency` score only the labeled one. That skip is the
# MAGIC visible proof of the requirement — and it's cheap, so you can run it after every change.

# COMMAND ----------

split_slice = [
    {"inputs": {"question": "Can I get a refund on a Basic Economy fare?"},
     "expectations": {"expected_facts": [
         "Basic Economy fares are generally non-refundable.",
         "A full refund is available if cancelled within 24 hours of booking."]}},   # labeled
    {"inputs": {"question": "My connection was missed — what are my options?"}},      # unlabeled
    {"inputs": {"question": "Can I bring my dog in the cabin?"}},                     # unlabeled
]

with mlflow.start_run(run_name="m3-split-proof"):
    split_result = mlflow.genai.evaluate(
        data=split_slice,
        predict_fn=predict_v1,
        scorers=ua_scorers,     # MUST be explicit — MLflow 3 auto-selects nothing
    )
print("Aggregate metrics:", split_result.metrics)

# COMMAND ----------

# MAGIC %md
# MAGIC ### How to verify it worked  *(M3 acceptance)*
# MAGIC - The suite runs through `mlflow.genai.evaluate(...)`; every applicable scorer writes a per-row `Feedback`
# MAGIC   with a rationale (open the inline **Evaluations** UI and read the rationales, not just the numbers).
# MAGIC - `Correctness` / `RetrievalSufficiency` scored **only the labeled row**; the two unlabeled rows are skipped
# MAGIC   for them but still scored by the reference-free judges and `cites_policy`.
# MAGIC - `cites_policy` shows up as a per-row numeric column with a rationale.
# MAGIC
# MAGIC > 💡 Want a per-row, per-scorer criterion (not a gold answer)? Add `ExpectationsGuidelines(model=EVAL_MODEL)`
# MAGIC > and give those rows `expectations.guidelines`. It scores only rows that define one. For a full custom
# MAGIC > prompt/verdict, `make_judge(...)` (MLflow ≥ 3.4) fits — both pass in the same `scorers=[...]` list.

# COMMAND ----------

# MAGIC %md
# MAGIC ## M4 · Register prompt v2, evaluate v1 vs v2, diagnose a regression  ·  (08.5 · 02.5)
# MAGIC The one variable you move is the **prompt version**. Register a refined **v2** of `ua_rag_prompt` under the
# MAGIC **same name** (so it becomes a new version, not a new prompt), keeping the `{{context}}` / `{{question}}`
# MAGIC variables. Then evaluate v1 and v2 against the **same dataset version** with the **same scorers**, in named,
# MAGIC tagged runs — so the score delta is attributable to the prompt change alone.
# MAGIC
# MAGIC The intentional change in v2: **require the fare type before making any refund-eligibility statement.** The
# MAGIC hypothesis is that it reduces overconfident refund promises without hurting groundedness.

# COMMAND ----------

V2_TEMPLATE = (
    "You are a customer-support assistant for Unity Airways. "
    "Answer ONLY from the retrieved context; if it is missing, say you don't know. "
    "Before making ANY statement about refund or change eligibility, first state which fare type the answer "
    "depends on (e.g. Basic Economy, Lite, Standard, Flex). Do not promise a refund or a free change without "
    "naming the fare type it applies to. Always name the source document.\n\n"
    "Context:\n{{context}}\n\nQuestion: {{question}}\n\nGrounded answer:"
)

v2 = mlflow.genai.register_prompt(
    name=UC_PROMPT,                                   # SAME name -> new version, not a new prompt
    template=V2_TEMPLATE,
    commit_message="v2: require fare type before any refund-eligibility statement",
    tags={"change_type": "behavior", "risk": "medium",
          "hypothesis": "reduces overconfident refund promises; groundedness flat"},
)
V2_VERSION = v2.version
V2_URI     = f"prompts:/{UC_PROMPT}/{V2_VERSION}"
print(f"Registered refined prompt: {UC_PROMPT} v{V2_VERSION}")
print("Comparing:", V1_URI, "vs", V2_URI)

# COMMAND ----------

# MAGIC %md
# MAGIC ### Evaluate each version — same dataset, same scorers, one variable, tagged
# MAGIC A helper keeps the two runs symmetric: anchor each to its own LoggedModel with `set_active_model`, tag the
# MAGIC `prompt_version` and the pinned `dataset_version`, then run the identical scorer suite. Nothing differs
# MAGIC between the runs except the prompt URI.

# COMMAND ----------

def evaluate_prompt_version(version: int, prompt_uri: str):
    mlflow.set_active_model(name=f"ua_rag_chain_v{version}")     # results attach to a per-version LoggedModel
    with mlflow.start_run(run_name=f"m4-eval-prompt-v{version}") as run:
        mlflow.set_tag("prompt_version", str(version))          # the one variable
        mlflow.set_tag("dataset_version", DATASET_VERSION)      # pinned so only the prompt moves
        mlflow.log_param("prompt_uri", prompt_uri)
        result = mlflow.genai.evaluate(
            data=eval_data,
            predict_fn=make_predict_fn(prompt_uri),
            scorers=ua_scorers,
        )
    print(f"[prompt v{version}] metrics:", result.metrics)
    return run, result

run_v1, res_v1 = evaluate_prompt_version(V1_VERSION, V1_URI)
run_v2, res_v2 = evaluate_prompt_version(V2_VERSION, V2_URI)

# COMMAND ----------

# MAGIC %md
# MAGIC ### Build the v1-vs-v2 comparison table (one row per scorer)
# MAGIC Line the aggregate means up side by side. The `delta` column is the score change **attributed to the prompt
# MAGIC version** — nothing else changed. A positive delta on `correctness` / `retrieval_sufficiency` with `safety`
# MAGIC flat is the evidence you promote on.

# COMMAND ----------

import pandas as pd

def mean_metrics(metrics: dict) -> dict:
    # keep only aggregate means (keys look like "correctness/mean", "safety/mean", ...)
    return {k.rsplit("/", 1)[0]: v for k, v in metrics.items() if k.endswith("/mean")}

m1, m2 = mean_metrics(res_v1.metrics), mean_metrics(res_v2.metrics)
rows = []
for name in sorted(set(m1) | set(m2)):
    a, b = m1.get(name), m2.get(name)
    delta = (b - a) if (a is not None and b is not None) else None
    rows.append({"scorer": name, "v1": a, "v2": b, "delta (v2-v1)": delta})

comparison = pd.DataFrame(rows)
print("=== v1 vs v2 · same dataset version:", DATASET_VERSION, "· only the prompt changed ===")
comparison

# COMMAND ----------

# MAGIC %md
# MAGIC ### Diagnose a regression through a trace (not the aggregate)
# MAGIC When a metric moves the wrong way, open the **traces that flipped** and name the failing span — don't argue
# MAGIC from the mean. Pull the v2 run's per-row traces, sort by a suspect score, and read the RETRIEVER span on the
# MAGIC lowest row. Typical finding: *"v2 tightened refund wording, but the retriever still pulled a baggage chunk on
# MAGIC this refund row"* — which localizes the fault to retrieval, not the prompt.

# COMMAND ----------

# Pull per-row traces for the v2 run (module-08 pattern, with the older-signature fallback).
try:
    v2_traces = mlflow.search_traces(run_id=run_v2.info.run_id)
except TypeError:
    v2_traces = mlflow.search_traces(
        experiment_ids=[EXPERIMENT_ID],
        filter_string="attributes.status = 'OK'",
    )

print("v2 rows scored:", len(v2_traces))
print("Columns:", list(v2_traces.columns))

# Surface a candidate to open in the Trace UI: prefer a groundedness-style assessment column if present.
score_cols = [c for c in v2_traces.columns if "groundedness" in c.lower() or "correctness" in c.lower()]
if score_cols and len(v2_traces):
    col = score_cols[0]
    worst = v2_traces.sort_values(col, na_position="last").head(1)
    print(f"\nOpen this trace and read its RETRIEVER span first (lowest '{col}'):")
    print(worst[[c for c in ("trace_id", "request", col) if c in worst.columns]].to_string(index=False))
else:
    print("\nNo score column surfaced here — open the v2 run in the Evaluations UI, sort by "
          "retrieval_groundedness, and expand the lowest row's RETRIEVER span.")

# COMMAND ----------

# MAGIC %md
# MAGIC ### (Optional) persist the failure so the fix is tracked
# MAGIC "Exceeds" on the rubric means the diagnosed failure lands in a table with the proposed fix (retriever vs
# MAGIC prompt), not just a comment. A one-row Delta append is enough to start.

# COMMAND ----------

# Uncomment to persist a diagnosed failure row (edit trace_id / diagnosis to the one you opened above).
# import pandas as pd
# failure = pd.DataFrame([{
#     "prompt_version": V2_VERSION,
#     "dataset_version": DATASET_VERSION,
#     "trace_id": "<paste from the row above>",
#     "symptom": "low retrieval_groundedness on a refund row",
#     "root_cause_span": "RETRIEVER pulled a baggage chunk instead of the fare-rules chunk",
#     "proposed_fix": "retriever (improve chunking / filter by intent), not the prompt",
# }])
# spark.createDataFrame(failure).write.mode("append").saveAsTable(f"{CATALOG}.{SCHEMA}.eval_failures")
# print("Logged the diagnosed failure to", f"{CATALOG}.{SCHEMA}.eval_failures")

# COMMAND ----------

# MAGIC %md
# MAGIC ### How to verify it worked  *(M4 acceptance)*
# MAGIC - **Two comparable eval runs**, each pinned to a prompt version (`prompts:/ua_rag_prompt/1` vs the refined
# MAGIC   version), tagged `prompt_version` and `dataset_version`, run on **one** dataset version.
# MAGIC - The **comparison table** shows one row per scorer with the delta attributed to the prompt version.
# MAGIC - At least **one regression diagnosed through a trace** — named down to the span (e.g. retriever pulled the
# MAGIC   wrong chunk), not argued from the aggregate.

# COMMAND ----------

# MAGIC %md
# MAGIC ## M5 · Promote @champion (model + prompt), write the scorecard  ·  (06.5 · 02.5)
# MAGIC Turn the evidence into a governed promotion on **both** movable pointers. First pick the winner from the
# MAGIC comparison, with a **stop-the-line** check: never promote a version whose `safety` regressed. Then move the
# MAGIC prompt `@champion` alias, register the winning chain (which loads the prompt **by alias**), move the model
# MAGIC `@champion` alias, and write the scorecard as version tags.

# COMMAND ----------

# Decide the winner: higher correctness wins, tie-broken by groundedness; block on a safety regression.
def score(m, key, default=float("nan")):
    return m.get(key, default)

safety_ok = True
try:
    s1, s2 = score(m1, "safety"), score(m2, "safety")
    # stop-the-line: v2 may not be meaningfully less safe than v1
    if s1 == s1 and s2 == s2:               # both non-NaN
        safety_ok = s2 >= s1 - 1e-9
    corr1, corr2 = score(m1, "correctness"), score(m2, "correctness")
    gnd1, gnd2   = score(m1, "retrieval_groundedness"), score(m2, "retrieval_groundedness")
    v2_better = (corr2, gnd2) > (corr1, gnd1) if (corr2 == corr2 and corr1 == corr1) else True
    WINNER_VERSION = V2_VERSION if (safety_ok and v2_better) else V1_VERSION
    reason = (f"correctness {corr1:.2f}->{corr2:.2f}, groundedness {gnd1:.2f}->{gnd2:.2f}, "
              f"safety_ok={safety_ok}")
except Exception as e:
    WINNER_VERSION = V2_VERSION
    reason = f"metrics unavailable ({e!r}); defaulting to the refined prompt — replace with a real decision"

WINNER_URI = f"prompts:/{UC_PROMPT}/{WINNER_VERSION}"
print(f"Winner: prompt v{WINNER_VERSION}  ({reason})")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Promote the winning **prompt** by alias
# MAGIC The shipped chain loads `prompts:/ua_rag_prompt@champion`, so promoting or rolling back the prompt is a
# MAGIC one-line pointer move — no redeploy, no hard-coded version number.

# COMMAND ----------

mlflow.genai.set_prompt_alias(name=UC_PROMPT, alias="champion", version=WINNER_VERSION)
resolved_prompt = mlflow.genai.load_prompt(f"prompts:/{UC_PROMPT}@champion")
print(f"Prompt @champion -> v{resolved_prompt.version}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Register the winning **chain** as a new UC version — loads the prompt by alias
# MAGIC Package the chain with **Models-from-Code** (`mlflow.models.set_model` in a `.py` file, logged by path, not
# MAGIC pickled). The file loads `prompts:/ua_rag_prompt@champion` — so the shipped chain follows prompt promotions
# MAGIC automatically. Declare `resources=[...]` so a served copy auto-authenticates to the index and the endpoint.

# COMMAND ----------

# MAGIC %%writefile ua_rag_chain_champion.py
# MAGIC # The C1 chain, self-contained, loading its prompt by ALIAS (no notebook globals; loading re-runs this file).
# MAGIC import mlflow
# MAGIC from databricks_langchain import ChatDatabricks, DatabricksVectorSearch
# MAGIC from langchain_core.prompts import PromptTemplate
# MAGIC from langchain_core.output_parsers import StrOutputParser
# MAGIC from langchain_core.runnables import RunnablePassthrough
# MAGIC
# MAGIC mlflow.langchain.autolog()   # loaded/served copies keep emitting traces
# MAGIC
# MAGIC CATALOG, SCHEMA = "unity_airways", "rag"
# MAGIC UC_PROMPT     = f"{CATALOG}.{SCHEMA}.ua_rag_prompt"
# MAGIC INDEX_NAME    = f"{CATALOG}.{SCHEMA}.ua_rag_chunks_index"
# MAGIC VS_ENDPOINT   = "unity-airways-vs"
# MAGIC CHAT_ENDPOINT = "databricks-claude-sonnet-4-5"
# MAGIC
# MAGIC # Load the prompt by ALIAS — promotion/rollback is a one-line pointer move, not a redeploy.
# MAGIC loaded = mlflow.genai.load_prompt(f"prompts:/{UC_PROMPT}@champion")
# MAGIC prompt = PromptTemplate.from_template(loaded.to_single_brace_format())
# MAGIC
# MAGIC retriever = DatabricksVectorSearch(
# MAGIC     endpoint=VS_ENDPOINT, index_name=INDEX_NAME,
# MAGIC     columns=["chunk_id", "content", "source_doc"],
# MAGIC ).as_retriever(search_kwargs={"k": 5})
# MAGIC
# MAGIC def format_docs(docs):
# MAGIC     return "\n\n".join(d.page_content for d in docs)
# MAGIC
# MAGIC llm = ChatDatabricks(endpoint=CHAT_ENDPOINT, temperature=0)
# MAGIC
# MAGIC chain = (
# MAGIC     {"context": retriever | format_docs, "question": RunnablePassthrough()}
# MAGIC     | prompt | llm | StrOutputParser()
# MAGIC )
# MAGIC mlflow.models.set_model(chain)   # <- the model MLflow logs

# COMMAND ----------

from mlflow import MlflowClient
from mlflow.models import infer_signature
from mlflow.models.resources import DatabricksVectorSearchIndex, DatabricksServingEndpoint

client = MlflowClient()
signature = infer_signature(model_input=QUESTION, model_output="A short grounded answer.")
resources = [
    DatabricksVectorSearchIndex(index_name=INDEX_NAME),       # retrieval (the "R")
    DatabricksServingEndpoint(endpoint_name=CHAT_ENDPOINT),   # generation (the "G")
]

with mlflow.start_run(run_name="m5-register-champion") as run:
    logged = mlflow.langchain.log_model(
        lc_model="ua_rag_chain_champion.py",     # Models-from-Code: the FILE PATH, not the object
        name="chain",
        signature=signature,
        input_example=QUESTION,
        resources=resources,                     # auto-auth on deploy
        pip_requirements=["mlflow>=3.1", "databricks-langchain", "databricks-vectorsearch"],
    )

mv = mlflow.register_model(model_uri=logged.model_uri, name=UC_MODEL)
print(f"Registered {mv.name} version {mv.version}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Promote the model by alias + write the scorecard
# MAGIC Setting `champion` to the new version *is* the promotion. Then attach the scorecard as **version tags**: the
# MAGIC eval scores, the eval **dataset version**, the **winning prompt version**, the approver, and the change
# MAGIC ticket. A future incident review can answer "which version, who approved, and why" from the registry alone.

# COMMAND ----------

client.set_registered_model_alias(name=UC_MODEL, alias="champion", version=mv.version)

# Scorecard — the audit trail for THIS build (values pulled from the winning run's metrics).
winner_metrics = m2 if WINNER_VERSION == V2_VERSION else m1
def fmt(x):
    return f"{x:.3f}" if isinstance(x, (int, float)) and x == x else "n/a"

client.set_model_version_tag(UC_MODEL, mv.version, "eval_correctness",  fmt(winner_metrics.get("correctness")))
client.set_model_version_tag(UC_MODEL, mv.version, "eval_groundedness", fmt(winner_metrics.get("retrieval_groundedness")))
client.set_model_version_tag(UC_MODEL, mv.version, "eval_safety",       fmt(winner_metrics.get("safety")))
client.set_model_version_tag(UC_MODEL, mv.version, "dataset_version",   DATASET_VERSION)
client.set_model_version_tag(UC_MODEL, mv.version, "prompt_version",    str(WINNER_VERSION))
client.set_model_version_tag(UC_MODEL, mv.version, "approver",          APPROVER)
client.set_model_version_tag(UC_MODEL, mv.version, "change_ticket",     CHANGE_TICKET)

print(f"{UC_MODEL}@champion -> v{mv.version}")
print("Scorecard tags:", client.get_model_version(UC_MODEL, mv.version).tags)

# COMMAND ----------

# MAGIC %md
# MAGIC ### Confirm the champion loads, and its prompt is by alias
# MAGIC Load the model by alias and confirm it round-trips. Because `ua_rag_chain_champion.py` loads
# MAGIC `prompts:/ua_rag_prompt@champion`, the shipped chain resolves its prompt by **alias** — not a pinned number
# MAGIC or an inline string.

# COMMAND ----------

champ = mlflow.langchain.load_model(f"models:/{UC_MODEL}@champion")
print(champ.invoke(QUESTION)[:300])
print(f"\nOK — {UC_MODEL}@champion round-trips; prompt resolves via prompts:/{UC_PROMPT}@champion")

# COMMAND ----------

# MAGIC %md
# MAGIC ### One-line rollback (no redeploy)  *(M5 acceptance)*
# MAGIC Rollback is a single alias move on either pointer. Repoint the **prompt** alias to the previous version and
# MAGIC every `@champion` consumer follows instantly; the bad version is untouched and inspectable. We roll back,
# MAGIC then restore.

# COMMAND ----------

prev_prompt = V1_VERSION if WINNER_VERSION != V1_VERSION else WINNER_VERSION
mlflow.genai.set_prompt_alias(UC_PROMPT, "champion", version=prev_prompt)
print(f"Rolled back prompt @champion -> v{prev_prompt}")
mlflow.genai.set_prompt_alias(UC_PROMPT, "champion", version=WINNER_VERSION)
print(f"Restored   prompt @champion -> v{WINNER_VERSION}")

# The model pointer rolls back the same way (repoint to a known-good version):
#   client.set_registered_model_alias(UC_MODEL, "champion", <previous_version>)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Recap — deliverables, gotchas, next stop
# MAGIC You turned the C1 chain into a **measured, versioned** asset with a promotion trail:
# MAGIC
# MAGIC | # | Deliverable | Where | Maps to rubric |
# MAGIC |---|---|---|---|
# MAGIC | **D1** | UC-backed, versioned `unity_airways.rag.eval_dataset` (labeled + unlabeled) | M2 | Dataset quality & coverage |
# MAGIC | **D2** | one explicit `scorers=[...]` mixing reference-based, reference-free, `Guidelines`, one `@scorer` | M3 | Ground-truth vs reference-free choice |
# MAGIC | **D3** | v1-vs-v2 comparison table, one row per scorer, same dataset version — only the prompt changed | M4 | Defensible promotion + prompt versioning |
# MAGIC | **D4** | quality scorecard (scores + dataset version + prompt version + approver + ticket) as version tags | M5 | Reproducibility |
# MAGIC | **D5** | `ua_rag_chain@champion` **and** `ua_rag_prompt@champion`, both loadable and rollback-able in one line | M5 | Governance / MLOps |
# MAGIC
# MAGIC **Gotchas to carry forward**
# MAGIC - Eval is **`mlflow.genai.evaluate(data=, predict_fn=, scorers=[...])`** with an **explicit** list — never
# MAGIC   `mlflow.evaluate(model_type="databricks-agent")`, and there is no `agents.evaluate()`.
# MAGIC - **`RetrievalSufficiency` is reference-based** — it needs `expected_facts` / `expected_response`, same as
# MAGIC   `Correctness`. Filing it with the reference-free judges is the classic mistake.
# MAGIC - A run that finishes with **zero traces** almost always means the row schema didn't match `predict_fn`
# MAGIC   (the `inputs` key must equal the parameter name). **Validate one row first** — we did, in M3.
# MAGIC - `mlflow.search_traces(experiment_ids=[...], filter_string="attributes.status = 'OK'")` — there is **no**
# MAGIC   `experiment_names=` argument.
# MAGIC - UC lifecycle is **aliases + tags**, never stages. Promotion and rollback are one-line alias moves — on the
# MAGIC   model **and** on the prompt.
# MAGIC
# MAGIC > 📌 **The highest-value fact this capstone drills:** MLflow 3 evaluation is an explicit
# MAGIC > `mlflow.genai.evaluate(...)` call; `Correctness` and `RetrievalSufficiency` are the two reference-based
# MAGIC > built-ins; and both the model and the prompt are governed the same way — versioned UC assets promoted by a
# MAGIC > `@champion` alias.
# MAGIC
# MAGIC **Next:** **Capstone C3 — ship a governed, monitored agent.** Take this `@champion` build, deploy it behind
# MAGIC a Serving endpoint, and reuse the **reference-free** scorer set from M3 as production monitors so a
# MAGIC groundedness drop alerts before a customer complains.
