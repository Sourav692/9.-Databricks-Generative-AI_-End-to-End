# Databricks notebook source
# MAGIC %md
# MAGIC # Module 01 Lab — Foundation Model APIs and External Models
# MAGIC **Roadmap:** Module 01 · Topic 01.6 (cornerstone hands-on) · [Hands-on]
# MAGIC
# MAGIC ## The problem
# MAGIC You need to reach a model on Databricks — fast for a prototype, and governed for production —
# MAGIC without rewriting your app when you graduate from a shared model to reserved capacity or a
# MAGIC third-party provider.
# MAGIC
# MAGIC ## What you will build
# MAGIC - Call a **Foundation Model API (pay-per-token)** four ways: `ChatDatabricks`, the OpenAI-compatible
# MAGIC   client, the MLflow Deployments SDK, and `ai_query()` in SQL.
# MAGIC - See how **temperature** changes output determinism.
# MAGIC - (Optional) Create an **External Model** endpoint (OpenAI) behind a Databricks secret and query it
# MAGIC   with the *same* code — the payoff of one serving surface.
# MAGIC - Compare **pay-per-token vs provisioned throughput vs external models** as a decision table.
# MAGIC
# MAGIC ### Prerequisites
# MAGIC - **Compute:** Serverless notebook compute, or an ML runtime cluster (DBR ML 14.3 LTS+). Runs in one session.
# MAGIC - **Libraries:** `databricks-langchain`, `openai`, `mlflow` (installed in the Setup cell).
# MAGIC - **Access:** permission to query Model Serving; the Foundation Model APIs enabled in the workspace.
# MAGIC - **Unity Catalog:** none required for the core lab (no tables written). The `ai_query` SQL cell needs a
# MAGIC   SQL warehouse or serverless SQL.
# MAGIC - **Secrets (optional External Model cell only):** a secret scope with your provider key, e.g.
# MAGIC   `databricks secrets create-scope genai_demo` then `databricks secrets put-secret genai_demo openai_api_key`.
# MAGIC
# MAGIC > ⚠️ **GOTCHA:** Served-model endpoint names change often. Confirm the names below on the
# MAGIC > **supported-models** page before running:
# MAGIC > `https://docs.databricks.com/aws/en/machine-learning/foundation-model-apis/supported-models`

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Setup
# MAGIC Keep setup small. Pin the endpoint names in one place so the whole lab (and later your app) reads
# MAGIC them from config, never hardcoded deep in the code.

# COMMAND ----------

# MAGIC %pip install -U databricks-langchain openai mlflow
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

# --- Config: the ONLY place endpoint names live. Verify on the supported-models page. ---
CHAT_ENDPOINT = "databricks-meta-llama-3-3-70b-instruct"  # pay-per-token chat model (verify it is current)
EMBED_ENDPOINT = "databricks-gte-large-en"                # general-purpose embedding endpoint
EXTERNAL_ENDPOINT = "openai-gpt-4o-proxy"                 # created in the optional External Model cell

# Secret scope/key used ONLY by the optional External Model cell (do not put raw keys in notebooks).
SECRET_SCOPE = "genai_demo"
SECRET_KEY = "openai_api_key"

print("Chat endpoint :", CHAT_ENDPOINT)
print("Embed endpoint:", EMBED_ENDPOINT)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. The core idea
# MAGIC Everything on Databricks reaches a model through **Mosaic AI Model Serving**. The Foundation Model
# MAGIC APIs are the Databricks-hosted slice of that surface, offered in two modes:
# MAGIC
# MAGIC - **Pay-per-token** — billed per token, zero setup, best for prototyping and moderate traffic.
# MAGIC - **Provisioned throughput** — reserved capacity with performance guarantees and fine-tuned weights.
# MAGIC
# MAGIC **External Models** wrap a third-party provider (OpenAI, Anthropic, Google) in the same governed
# MAGIC surface. Below we hit a pay-per-token endpoint four different ways — all return the same shape.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Run it — four ways to call one pay-per-token endpoint
# MAGIC ### 3a. LangChain — `ChatDatabricks` (recommended for app code)
# MAGIC Note the package is **`databricks-langchain`** and the import is `databricks_langchain`
# MAGIC (NOT `langchain-databricks` / `langchain_community`).

# COMMAND ----------

from databricks_langchain import ChatDatabricks

# temperature=0 -> near-deterministic, the right default for structured / factual tasks.
llm = ChatDatabricks(endpoint=CHAT_ENDPOINT, temperature=0)
answer = llm.invoke("In one sentence, what is a Databricks Foundation Model API?")
print(answer.content)

# COMMAND ----------

# MAGIC %md
# MAGIC ### 3b. OpenAI-compatible client
# MAGIC Foundation Model APIs speak the OpenAI schema, so existing OpenAI code works by changing only
# MAGIC `base_url` and the model name. We mint a short-lived token from the SDK instead of pasting one.

# COMMAND ----------

from openai import OpenAI
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
client = OpenAI(
    api_key=w.tokens.create(comment="fmapi-lab", lifetime_seconds=600).token_value,
    base_url=f"{w.config.host}/serving-endpoints",
)
resp = client.chat.completions.create(
    model=CHAT_ENDPOINT,
    messages=[{"role": "user", "content": "Say hello to a Databricks Field Engineer in 5 words."}],
    temperature=0,
)
print(resp.choices[0].message.content)

# COMMAND ----------

# MAGIC %md
# MAGIC ### 3c. MLflow Deployments SDK
# MAGIC A provider-agnostic client — the same `predict()` call works for hosted, external, and custom endpoints.

# COMMAND ----------

from mlflow.deployments import get_deploy_client

deploy_client = get_deploy_client("databricks")
r = deploy_client.predict(
    endpoint=CHAT_ENDPOINT,
    inputs={"messages": [{"role": "user", "content": "Name one benefit of pay-per-token."}],
            "temperature": 0},
)
print(r["choices"][0]["message"]["content"])

# COMMAND ----------

# MAGIC %md
# MAGIC ### 3d. SQL — `ai_query()` for batch / inline inference
# MAGIC This is how you score a whole Delta table at scale without a Python loop. Runs on a SQL warehouse
# MAGIC or serverless SQL.

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT ai_query(
# MAGIC   'databricks-meta-llama-3-3-70b-instruct',  -- keep in sync with CHAT_ENDPOINT above
# MAGIC   'Classify the sentiment as positive, negative, or neutral. Return one word only. Review: "Flight was delayed but the staff were kind."'
# MAGIC ) AS sentiment;

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3e. Temperature in action (01.2)
# MAGIC Low temperature = stable, repeatable output. Higher temperature = more variety. Run this and note
# MAGIC how the two temperatures differ for a creative prompt (structured tasks should stay at 0).

# COMMAND ----------

prompt = "Give a short, catchy tagline for Unity Airways."
for temp in (0.0, 1.0):
    out = ChatDatabricks(endpoint=CHAT_ENDPOINT, temperature=temp).invoke(prompt).content
    print(f"temperature={temp}: {out}\n")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Verify it worked
# MAGIC A well-formed chat response has a non-empty `choices[0].message.content`. We also confirm the
# MAGIC endpoint is queryable and inspect its family via the Serving API.

# COMMAND ----------

# 4a. Assert we got real text back.
assert isinstance(answer.content, str) and len(answer.content.strip()) > 0, "Empty response from ChatDatabricks"
assert resp.choices[0].message.content, "Empty response from OpenAI client"
print("PASS: all pay-per-token calls returned text.")

# 4b. Inspect the endpoint object (state should be READY).
ep = w.serving_endpoints.get(CHAT_ENDPOINT)
print("Endpoint:", ep.name, "| state:", ep.state.ready if ep.state else "unknown")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. (Optional) External Model — call OpenAI through a governed Databricks endpoint
# MAGIC Only run this if you have a provider key stored as a Databricks secret (see Prerequisites). The key
# MAGIC is referenced as `{{secrets/scope/key}}` and is **never** written in the notebook. After creation,
# MAGIC query `EXTERNAL_ENDPOINT` with the *same* ChatDatabricks / OpenAI-client / `ai_query` code.

# COMMAND ----------

# We use MLflow Deployments create_endpoint, which takes the documented config as a plain
# dict — so the only names in play are the doc-verified fields (provider, task, *_config).
from mlflow.deployments import get_deploy_client

def ensure_external_openai_endpoint():
    existing = [e.name for e in w.serving_endpoints.list()]
    if EXTERNAL_ENDPOINT in existing:
        print(f"Endpoint '{EXTERNAL_ENDPOINT}' already exists — skipping create.")
        return
    deploy = get_deploy_client("databricks")
    deploy.create_endpoint(
        name=EXTERNAL_ENDPOINT,
        config={
            "served_entities": [{
                "name": "gpt-4o",
                "external_model": {
                    "name": "gpt-4o",            # provider's model name (verify current)
                    "provider": "openai",        # openai | anthropic | google-cloud-vertex-ai | ...
                    "task": "llm/v1/chat",       # route schema
                    # key stored as a Databricks secret, never in code
                    "openai_config": {"openai_api_key": f"{{{{secrets/{SECRET_SCOPE}/{SECRET_KEY}}}}}"},
                },
            }]
        },
    )
    print(f"Creating '{EXTERNAL_ENDPOINT}' — wait for state READY in the Serving UI before querying.")

# Uncomment to run:
# ensure_external_openai_endpoint()

# COMMAND ----------

# MAGIC %md
# MAGIC Once the external endpoint is READY, the *same* client code works — only the endpoint name changed:

# COMMAND ----------

# Uncomment after the external endpoint is READY:
# ext_llm = ChatDatabricks(endpoint=EXTERNAL_ENDPOINT, temperature=0)
# print(ext_llm.invoke("In one sentence, what is an external model in Databricks Model Serving?").content)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6. Compare the three offerings
# MAGIC | Offering | Setup | Billing | Best for | Fine-tuned weights? |
# MAGIC |---|---|---|---|---|
# MAGIC | **Foundation Model API — pay-per-token** | None | Per token | Prototyping, evals, moderate traffic | No |
# MAGIC | **Foundation Model API — provisioned throughput** | Reserve capacity | Per capacity band | Production, SLAs, high throughput | Yes |
# MAGIC | **External Model** | Create endpoint + secret | Provider bills; Databricks governs | Calling OpenAI/Anthropic/Google under one governance layer | Provider-dependent |
# MAGIC
# MAGIC > 💡 **TIP:** Keep the endpoint **name in config** (as we did). Moving pay-per-token → provisioned
# MAGIC > throughput → external is then a one-line change, not a rewrite.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 7. Recap, gotchas, and next steps
# MAGIC **What we built**
# MAGIC - Called one pay-per-token Foundation Model API via `ChatDatabricks`, the OpenAI client, MLflow
# MAGIC   Deployments, and `ai_query()` — all returning the same shape.
# MAGIC - Saw temperature control determinism.
# MAGIC - (Optional) Fronted OpenAI as a governed External Model with the key in a secret.
# MAGIC
# MAGIC **Gotchas to remember**
# MAGIC - Package is **`databricks-langchain`** (`from databricks_langchain import ChatDatabricks`).
# MAGIC - Endpoint names churn (DBRX was retired from the list) — verify on the supported-models page.
# MAGIC - Set **temperature = 0** for JSON / SQL / classification.
# MAGIC - Never hardcode provider keys — use `{{secrets/scope/key}}`.
# MAGIC
# MAGIC **Cleanup (only if you created the external endpoint):**

# COMMAND ----------

# Uncomment to delete the optional external endpoint you created:
# w.serving_endpoints.delete(EXTERNAL_ENDPOINT)
# print(f"Deleted {EXTERNAL_ENDPOINT}")

# COMMAND ----------

# MAGIC %md
# MAGIC **Next roadmap topic:** Module 02 — Prompt engineering (02.1 Fundamentals and core prompting techniques).
# MAGIC You now have a model endpoint to send those prompts to.
