# Databricks notebook source
# MAGIC %md
# MAGIC # Topic 02.5 (★) — MLflow Prompt Registry
# MAGIC **Roadmap:** Module 02 · Topic 02.5 (cornerstone) · also touches 02.6 (evaluate) and 02.7 (optimize)
# MAGIC
# MAGIC ## The problem
# MAGIC A support bot promised a customer a full refund. Nobody can say which prompt was live, who changed
# MAGIC it, or what the last known-good version was. This notebook fixes that: give prompts a governed home
# MAGIC with immutable versions, mutable aliases, and Unity Catalog governance — then promote by evidence.
# MAGIC
# MAGIC ## What you will build
# MAGIC - Register v1 and v2 of a Unity Airways support prompt with `mlflow.genai.register_prompt`
# MAGIC - Promote/roll back with `set_prompt_alias` (staging, production)
# MAGIC - Load by alias and by version; render `{{variables}}` with `.format()`
# MAGIC - Compare versions on a fixed eval set with `mlflow.genai.evaluate` + the `Correctness` scorer
# MAGIC
# MAGIC ### Prerequisites  (read before running)
# MAGIC - **The Prompt Registry is Beta on Databricks.** A workspace admin may need to enable it on the
# MAGIC   **Previews** page.
# MAGIC - Libraries: **`mlflow[databricks]>=3.1.0`** (install cell below).
# MAGIC - Compute: serverless or ML runtime; a **Foundation Model APIs** entitlement or a serving endpoint.
# MAGIC - **Unity Catalog:** you need a schema where you hold **`CREATE FUNCTION`, `EXECUTE`, and `MANAGE`**.
# MAGIC   Set `CATALOG` / `SCHEMA` below to that schema.
# MAGIC - Model endpoint: uses `databricks-claude-sonnet-4-5`. Endpoint names change — verify on
# MAGIC   *Serving → supported models* and edit `MODEL_ENDPOINT`.

# COMMAND ----------

# MAGIC %pip install -U "mlflow[databricks]>=3.1.0"
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Setup — choose a governed location
# MAGIC A prompt name is a Unity Catalog identifier: `catalog.schema.prompt_name`. Set your UC location and
# MAGIC (optionally) tag the experiment so GenAI APIs default to this schema for prompt resolution.

# COMMAND ----------

import mlflow

CATALOG = "genai"        # <-- change to a catalog you can write to
SCHEMA = "default"      # <-- change to a schema where you hold CREATE FUNCTION, EXECUTE, MANAGE
MODEL_ENDPOINT = "databricks-claude-sonnet-4-5"  # verify on Serving > supported models

PROMPT_NAME = f"{CATALOG}.{SCHEMA}.unity_airways_customer_support"

mlflow.set_tracking_uri("databricks")
mlflow.set_experiment("/Shared/unity-airways/unity-airways-prompts")

# Optional: set a default Prompt Registry location so short names resolve to this schema.
mlflow.set_experiment_tags({"mlflow.promptRegistryLocation": f"{CATALOG}.{SCHEMA}"})

print("Prompt name:", PROMPT_NAME)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Register version 1 (baseline)
# MAGIC `register_prompt` creates the prompt if the name is new, otherwise it adds a new version. Templates
# MAGIC use **double-brace** `{{variable}}` syntax. Use `commit_message` and `tags` to record intent.

# COMMAND ----------

v1 = mlflow.genai.register_prompt(
    name=PROMPT_NAME,
    template="""You are a customer support assistant for Unity Airways.

Rules:
- If key details are missing, ask exactly one clarifying question.
- Do not invent fees, waivers, or exceptions.

Customer question: {{question}}

Write a concise answer (max 120 words).""",
    commit_message="v1: baseline support answer with safety and brevity constraints",
    tags={"use_case": "customer_support", "language": "en", "owner": "unity-airways-support"},
)
print(f"Created prompt {v1.name} version {v1.version}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Register version 2 — one intentional change
# MAGIC Versions are **immutable**; to "edit" you register a new version. Change one thing per version and
# MAGIC record the hypothesis, so you can attribute a later score change to a specific edit.

# COMMAND ----------

v2 = mlflow.genai.register_prompt(
    name=PROMPT_NAME,
    template="""You are a customer support assistant for Unity Airways.

Rules:
- If the question is ambiguous, ask exactly one clarifying question.
- If the customer mentions refunds, do not promise eligibility without fare details.
- Do not invent fees, waivers, or exceptions.
- Keep the answer under 120 words.

Customer question:
{{question}}

Answer:""",
    commit_message="v2: tighten ambiguity handling and refund safety posture",
    tags={"change_type": "behavior", "risk": "medium",
          "hypothesis": "reduces overconfident refund promises"},
)
print(f"Created version {v2.version} of {v2.name}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### How to verify it worked
# MAGIC Open the experiment `/Shared/unity-airways/unity-airways-prompts` → **Prompts** tab. You should see
# MAGIC two versions of `unity_airways_customer_support`, each with its commit message and tags. The
# MAGIC **Compare** view highlights the diff between v1 and v2.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Promote with aliases (mutable pointers)
# MAGIC An alias is a stable label your app references. Reassigning it promotes or rolls back **without a
# MAGIC redeploy**. We stage v2 and keep production on the known-good v1 until it earns promotion.

# COMMAND ----------

mlflow.genai.set_prompt_alias(name=PROMPT_NAME, alias="staging", version=v2.version)
mlflow.genai.set_prompt_alias(name=PROMPT_NAME, alias="production", version=v1.version)
print(f"staging -> v{v2.version}, production -> v{v1.version}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Load and render — by alias (prod) and by version (dev)
# MAGIC URIs: version = `prompts:/<name>/2`, alias = `prompts:/<catalog>.<schema>.<name>@<alias>`.
# MAGIC Load by **alias** in production so promotions don't need a redeploy; load by **version** in dev for
# MAGIC deterministic reproduction.

# COMMAND ----------

# By alias (production path)
prompt_prod = mlflow.genai.load_prompt(f"prompts:/{PROMPT_NAME}@production")
print("Loaded", prompt_prod.name, "version", prompt_prod.version)

# By version (deterministic dev/test)
prompt_v2 = mlflow.genai.load_prompt(f"prompts:/{PROMPT_NAME}/{v2.version}")

# Render the {{question}} variable with .format()
rendered = prompt_prod.format(question="Can I change my flight tomorrow?")
print("\n--- rendered prompt ---\n", rendered)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6. Make the model call
# MAGIC Use the OpenAI-compatible client from the Databricks SDK. Log the prompt name + version alongside
# MAGIC the response so any customer report traces back to an exact version.

# COMMAND ----------

from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
client = w.serving_endpoints.get_open_ai_client()

resp = client.chat.completions.create(
    model=MODEL_ENDPOINT,
    messages=[{"role": "user", "content": rendered}],
    temperature=0.1, max_tokens=350,
)
print(f"[prompt used: {prompt_prod.name} v{prompt_prod.version}]")
print(resp.choices[0].message.content)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 7. Evaluate & compare versions on a fixed dataset  [02.6]
# MAGIC Build a small, representative eval dataset in Unity Catalog. Fields are **`inputs`** and
# MAGIC **`expectations`** (write `expected_facts` as checkable statements). Keep the dataset **fixed** while
# MAGIC comparing versions.

# COMMAND ----------

EVAL_DATASET_NAME = f"{CATALOG}.{SCHEMA}.ua_support_prompt_eval"

# Current API: create_dataset(name=...). The Early-Release book's uc_table_name= is deprecated;
# pass the fully qualified UC table name as `name`.
eval_dataset = mlflow.genai.create_dataset(name=EVAL_DATASET_NAME)
eval_dataset = eval_dataset.merge_records([
    {"inputs": {"question": "My flight is tomorrow. Can I change it to next week?"},
     "expectations": {"expected_facts": [
         "Eligibility depends on fare rules or fare type",
         "May involve a change fee or fare difference",
         "Ask for booking reference or fare details if missing"]}},
    {"inputs": {"question": "I missed my flight due to traffic. Do I get a refund?"},
     "expectations": {"expected_facts": [
         "Refund eligibility depends on fare rules",
         "Do not promise a refund without checking ticket conditions",
         "Provide next steps to verify eligibility"]}},
    {"inputs": {"question": "My flight was canceled. Can I rebook for free?"},
     "expectations": {"expected_facts": [
         "Rebooking depends on disruption policy",
         "Ask for booking details if needed",
         "Avoid claiming blanket waivers without evidence"]}},
])
print(f"Eval dataset ready: {EVAL_DATASET_NAME}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### A predict function per version
# MAGIC The function loads a specific prompt version from the registry, renders it, and calls the model.
# MAGIC Returning a dict keeps outputs consistent so the scorer can read them.

# COMMAND ----------

def make_predict_fn(prompt_name, version):
    def answer_question(question: str) -> dict:
        prompt = mlflow.genai.load_prompt(f"prompts:/{prompt_name}/{version}")
        content = prompt.format(question=question)
        resp = client.chat.completions.create(
            model=MODEL_ENDPOINT,
            messages=[{"role": "user", "content": content}],
            temperature=0.1, max_tokens=350,
        )
        return {"response": resp.choices[0].message.content}
    return answer_question

# COMMAND ----------

# MAGIC %md
# MAGIC ### Run evaluation for each version
# MAGIC `mlflow.genai.evaluate` is the MLflow 3 GenAI entry point (NOT `mlflow.evaluate(model_type=...)`).
# MAGIC The `Correctness` scorer uses the `expected_facts` in the dataset. Log `prompt_version` so the runs
# MAGIC group cleanly in the UI.

# COMMAND ----------

from mlflow.genai.scorers import Correctness

results = {}
for version in [v1.version, v2.version]:
    with mlflow.start_run(run_name=f"ua_support_v{version}_eval"):
        mlflow.log_param("prompt_name", PROMPT_NAME)
        mlflow.log_param("prompt_version", version)
        mlflow.log_param("eval_dataset", EVAL_DATASET_NAME)
        eval_results = mlflow.genai.evaluate(
            predict_fn=make_predict_fn(PROMPT_NAME, version),
            data=eval_dataset,
            scorers=[Correctness()],
        )
        results[f"v{version}"] = eval_results
        score = eval_results.metrics.get("correctness/mean", 0)
        print(f"v{version} correctness/mean: {score:.2f}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Choose a winner and verify
# MAGIC Promote the higher-correctness version as long as a spot-check of edge cases shows no obvious
# MAGIC regression. Then move `staging` first, validate, then move `production`.

# COMMAND ----------

print("\n=== Version comparison ===")
for label, result in results.items():
    print(f"{label}: correctness={result.metrics.get('correctness/mean', 0):.2f}")

best = max(results.items(), key=lambda kv: kv[1].metrics.get("correctness/mean", 0))
print(f"\nBest version by correctness: {best[0]}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### How to verify it worked
# MAGIC Two evaluation runs appear in the experiment. Open **Evaluation runs**, group by the `prompt_version`
# MAGIC param, and use **Compare** to see `correctness/mean` side by side. The constrained v2 should score
# MAGIC higher on the refund/cancellation "gotcha" cases.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 8. Promote the winner (and know your rollback)
# MAGIC Promotion is a single alias reassignment. Record the previous production version first so rollback
# MAGIC is immediate.

# COMMAND ----------

winner_version = int(best[0].lstrip("v"))
previous_prod = prompt_prod.version   # remember the current production version for rollback

mlflow.genai.set_prompt_alias(name=PROMPT_NAME, alias="production", version=winner_version)
print(f"Promoted production -> v{winner_version}. Rollback target if needed: v{previous_prod}")

# To roll back:  mlflow.genai.set_prompt_alias(name=PROMPT_NAME, alias="production", version=previous_prod)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 9. (Optional) Prompt optimization  [02.7]
# MAGIC `mlflow.genai.optimize_prompts` proposes an improved template you still review and promote through
# MAGIC the same lifecycle. `GepaPromptOptimizer` is the confirmed first-class optimizer.
# MAGIC
# MAGIC > **VERIFY:** the interface is Beta-adjacent and moving. Confirm `GepaPromptOptimizer` args and any
# MAGIC > additional optimizer classes against `mlflow.genai.optimize` before relying on this in production.

# COMMAND ----------

# Uncomment to run. Optimization makes many model calls; keep max_metric_calls low while validating.
#
# from mlflow.genai.optimize import GepaPromptOptimizer
#
# def predict_fn(question: str) -> str:
#     prompt = mlflow.genai.load_prompt(f"prompts:/{PROMPT_NAME}/{v1.version}")
#     content = prompt.format(question=question)   # MUST load from registry + .format() or nothing is optimized
#     resp = client.chat.completions.create(
#         model=MODEL_ENDPOINT,
#         messages=[{"role": "user", "content": content}],
#         temperature=0.1, max_tokens=350)
#     return resp.choices[0].message.content
#
# result = mlflow.genai.optimize_prompts(
#     predict_fn=predict_fn,
#     train_data=eval_dataset,               # reuse the fixed dataset (inputs + expected_facts)
#     prompt_uris=[v1.uri],
#     optimizer=GepaPromptOptimizer(
#         reflection_model=f"databricks:/{MODEL_ENDPOINT}",
#         max_metric_calls=20),              # optimization budget (default 100)
#     scorers=[Correctness()],
# )
# candidate = result.optimized_prompts[0]
# print(candidate.template)   # review, then register as a new version and re-run section 7 before promoting

# COMMAND ----------

# MAGIC %md
# MAGIC ## 10. Discovery & cleanup
# MAGIC On a UC-backed registry, `search_prompts` supports only a `catalog='...' AND schema='...'` filter, so
# MAGIC list then filter in Python. Deletion is conservative: remove versions first, then the prompt.

# COMMAND ----------

all_prompts = mlflow.genai.search_prompts(
    filter_string=f"catalog = '{CATALOG}' AND schema = '{SCHEMA}'")
support = [p for p in all_prompts if "unity_airways" in p.name.lower()]
print("Found:", [p.name for p in support])

# --- Cleanup (leave commented unless you really want to delete) ---
# from mlflow import MlflowClient
# mc = MlflowClient()
# mc.delete_prompt_version(PROMPT_NAME, str(v1.version))
# mc.delete_prompt_version(PROMPT_NAME, str(v2.version))
# mc.delete_prompt(PROMPT_NAME)   # only after all versions are deleted

# COMMAND ----------

# MAGIC %md
# MAGIC ## 11. Recap, gotchas & next steps
# MAGIC **What we built:** registered v1/v2, promoted via aliases, loaded by alias and version, evaluated
# MAGIC both on a fixed UC dataset with `Correctness`, and promoted the winner with a known rollback.
# MAGIC
# MAGIC **Gotchas**
# MAGIC - Prompt Registry is **Beta**; needs `mlflow[databricks]>=3.1.0`, a UC schema, and
# MAGIC   `CREATE FUNCTION` + `EXECUTE` + `MANAGE`.
# MAGIC - Versions are immutable; aliases are mutable. Promote/roll back by moving a pointer.
# MAGIC - Templates use `{{double}}` braces; convert with `to_single_brace_format()` for LangChain.
# MAGIC - Use `mlflow.genai.evaluate`, not `mlflow.evaluate(model_type="databricks-agent")`.
# MAGIC - Endpoint names churn — verify `MODEL_ENDPOINT` on the supported-models page.
# MAGIC
# MAGIC **Next roadmap topic:** Module 03 — Data preparation & chunking for RAG (the next stop after
# MAGIC prompting on the fastest path to a RAG app).
