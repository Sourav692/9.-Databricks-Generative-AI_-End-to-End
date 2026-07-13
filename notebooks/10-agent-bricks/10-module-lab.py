# Databricks notebook source
# MAGIC %md
# MAGIC # Module 10 lab — Build the Unity Airways experience with no/low-code Agent Bricks
# MAGIC **Roadmap:** Module 10 (Agent Bricks and no/low-code agents) · Topics 10.1–10.8 · ★ 10.2 / 10.5 cornerstones · [Theory + Hands-on]
# MAGIC
# MAGIC The **no/low-code counterpart to Module 09**. Instead of hand-coding a `ResponsesAgent`, you assemble the same
# MAGIC Unity Airways support experience from **console tiles + a Python front end**. This module is largely
# MAGIC **console/UI-driven**, so this lab mixes `%md` console walkthroughs with the genuinely runnable bits: querying
# MAGIC a deployed Knowledge Assistant / agent endpoint, and the **GA SQL AI-function** alternatives for the two Beta tiles.
# MAGIC
# MAGIC | Step | Topic | Status | What you do |
# MAGIC |---|---|---|---|
# MAGIC | 1 | **10.1** AI Playground | **GA** | `%md` — prototype + "Export to Databricks Apps" |
# MAGIC | 2 | **10.2** ★ Knowledge Assistant | **GA** | `%md` console build, then **runnable** endpoint query |
# MAGIC | 3 | **10.3** Multi-Agent Supervisor | **GA** | `%md` — routes Genie Agents + Knowledge Assistant + MCP |
# MAGIC | 4 | **10.4** Custom Agents | — | `%md` — the escape hatch back to Module 09 code |
# MAGIC | 5 | **10.5** ★ Databricks Apps | **GA** | `%md` brief — points to `10-5-databricks-apps.py` |
# MAGIC | 6 | **10.6** End-to-end | — | `%md` — the full low-code journey in one pass |
# MAGIC | 7 | **10.7** Information Extraction | **Beta** | `%md` + **runnable GA SQL**: `ai_parse_document` / `ai_extract` |
# MAGIC | 8 | **10.8** Custom LLM | **Beta** | `%md` + **runnable GA SQL**: `ai_classify` / `ai_summarize` / `ai_gen` |
# MAGIC
# MAGIC Cornerstone notebooks: `10-5-databricks-apps.py` (10.5). The Knowledge Assistant reads the **Module 04** index
# MAGIC `unity_airways.rag.ua_rag_chunks_index`; a Custom Agent wraps the **Module 09** agent `unity_airways.rag.ua_support_agent`.
# MAGIC
# MAGIC ## Prerequisites (read before running)
# MAGIC - **Compute:** **serverless notebook/job**, or a **DBR ML runtime** (15.4 LTS ML or later). The SQL AI-function
# MAGIC   cells need a **serverless SQL warehouse or DBR** with AI Functions available.
# MAGIC - **UC objects (`unity_airways.rag`):** the Module 04 AI Search index `ua_rag_chunks_index`, and — for the KA
# MAGIC   query cell — a **deployed Knowledge Assistant or agent endpoint** (build the KA in 10.2, or reuse the Module 09
# MAGIC   `agents.deploy()` endpoint). If you have not built one yet, that cell is **illustrative** and guarded.
# MAGIC - **`databricks` CLI configured** — only for the App deploy path (10.5 / `10-5-databricks-apps.py`).
# MAGIC - **Secrets:** none. **Learner-set identifiers:** the endpoint name + Volume path in Step 0.
# MAGIC - Building an Agent Bricks tile is **console-driven** — no cluster needed to author it; provisioning uses serverless capacity.
# MAGIC
# MAGIC > 📌 **The one rule of this module — start no-code, drop to code only when a tile can't do it.**
# MAGIC > AI Playground (prototype) → Agent Bricks tile (Knowledge Assistant / Multi-Agent Supervisor / …) → Databricks App
# MAGIC > (front end), with the **Custom Agent** (Module 09) as the escape hatch.
# MAGIC >
# MAGIC > **Name the maturity of every tile:** GA — AI Playground, Knowledge Assistant, Multi-Agent Supervisor.
# MAGIC > **Beta** — Information Extraction, Custom LLM (use the **GA SQL AI functions** for hardened pipelines today).

# COMMAND ----------

# MAGIC %md
# MAGIC ## 0. Install libraries and set variables
# MAGIC The SDK powers the runnable endpoint-query cell; the SQL AI-function cells need no pip. `databricks-sdk` is
# MAGIC usually pre-installed on DBR ML — the `%pip` keeps versions predictable across compute.

# COMMAND ----------

# MAGIC %pip install -U databricks-sdk
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

CATALOG      = "unity_airways"
SCHEMA       = "rag"
INDEX_NAME   = f"{CATALOG}.{SCHEMA}.ua_rag_chunks_index"     # Module 04 — the KA's knowledge source
UC_MODEL     = f"{CATALOG}.{SCHEMA}.ua_support_agent"        # Module 09 — the Custom Agent behind 10.4
LLM_ENDPOINT = "databricks-claude-sonnet-4-5"              # AI Playground default chat model; confirm on supported-models
VOLUME_DOCS  = f"/Volumes/{CATALOG}/{SCHEMA}/ua_policy_docs" # optional Volume knowledge source for the KA

# The Knowledge Assistant / agent endpoint you query in Step 2. Read the exact name from the console
# ("Use"/"Query" panel) or the agents.deploy() output — it is auto-generated (e.g. ka-<id>-endpoint).
KA_ENDPOINT  = "ka-REPLACE-with-your-endpoint"

print("Index        :", INDEX_NAME)
print("UC agent     :", UC_MODEL)
print("LLM endpoint :", LLM_ENDPOINT)
print("KA endpoint  :", KA_ENDPOINT)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 1 — AI Playground (10.1) · GA · [Hands-on, console]
# MAGIC **AI Playground** is the no-code chat surface where you find the *shape* before building anything.
# MAGIC
# MAGIC **Console steps** *(confirm exact nav labels in your workspace):*
# MAGIC 1. Open **AI Playground** from the left nav (under **Machine Learning / Generative AI**).
# MAGIC 2. **Compare models side by side** — send the same Unity Airways prompt to a few foundation models
# MAGIC    (`databricks-claude-sonnet-4-5` is the reference chat model) and eyeball quality, latency, cost.
# MAGIC 3. **Attach tools with no code** — a UC function (`get_flight_status`), **AI Search** retrieval over
# MAGIC    `unity_airways.rag.ua_rag_chunks_index`, and/or **MCP** servers — then watch the model emit tool calls.
# MAGIC 4. **Export when it's good** — **"Export to Databricks Apps"** scaffolds a hosted chat app (→ 10.5), or
# MAGIC    export-to-code hands the same setup to a notebook (the Module 09 path).
# MAGIC
# MAGIC **How to verify:** ask *"Is UA217 to Tokyo delayed, and is my booking refundable?"* with the retriever + a UC
# MAGIC function attached — you should see tool calls and cited chunks. Each turn is captured as an MLflow trace.
# MAGIC
# MAGIC > 💡 **TIP:** Playground is the cheapest way to kill a bad idea. Decide model + tools + rough system prompt here,
# MAGIC > then move to a Knowledge Assistant (pure Q&A) or export to Apps/code.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 2 — ★ Knowledge Assistant (10.2) · GA (Jan 2026) · [Hands-on]
# MAGIC A **Knowledge Assistant (KA)** is a **managed, cited Q&A chatbot** over your documents — the same outcome as the
# MAGIC Module 05 hand-coded RAG chain, with essentially no code. Full deep-dive: `modules/10-agent-bricks/knowledge-assistant.md`.
# MAGIC
# MAGIC **Console build flow** *(confirm exact labels in the current console):*
# MAGIC 1. **Agent Bricks → Knowledge Assistant → create.**
# MAGIC 2. **Name** (`Unity Airways Policy Assistant`), **Description** (what it answers), **Instructions**
# MAGIC    ("always cite the specific policy; if it is not in the docs, say so plainly").
# MAGIC 3. **Knowledge source** — attach a **UC Volume folder** of docs (`{VOLUME_DOCS}`) **or** the existing
# MAGIC    **AI Search index** `unity_airways.rag.ua_rag_chunks_index` (reuse Module 04 — keeps your chunking/embeddings).
# MAGIC 4. **(Optional) Sample questions** — a handful of real questions seed the judge-backed quality loop.
# MAGIC 5. **Create and wait for ONLINE** (a couple of minutes). Databricks manages chunking/indexing (Volume source),
# MAGIC    retrieval, generation, the quality loop, and **citations**, and stands up a **serving endpoint**.
# MAGIC
# MAGIC **How to verify:** in the tile's built-in chat, a policy answer carries **citations** back to the source doc; a
# MAGIC question with no supporting source produces a graceful "I don't have that" rather than an invented policy.

# COMMAND ----------

# MAGIC %md
# MAGIC ### Consume the KA endpoint (runnable)
# MAGIC Once ONLINE, query the KA like any Model Serving endpoint. The exact request/response schema depends on the
# MAGIC endpoint signature, so **confirm the payload shape in the console "Query"/"Use" panel** before wiring a client.

# COMMAND ----------

from databricks.sdk import WorkspaceClient

# NOTE: verify vs current docs — Agent Bricks endpoint names and request/response signatures change between
# releases and the KA doc pages are JS-rendered. Confirm KA_ENDPOINT + the schema in the console before relying on this.
w = WorkspaceClient()

QUESTION = "Can I get a refund on a Basic Economy fare?"
try:
    resp = w.serving_endpoints.query(
        name=KA_ENDPOINT,                                   # exact name shown in the console (e.g. ka-<id>-endpoint)
        messages=[{"role": "user", "content": QUESTION}],   # confirm this schema in the console "Query"/"Use" panel
    )
    print(resp)   # answer text + citation metadata (shape per the endpoint signature)
except Exception as e:
    print("[illustrative] Set KA_ENDPOINT to your live Knowledge Assistant / agent endpoint, then re-run.")
    print("Reason:", repr(e))

# COMMAND ----------

# MAGIC %md
# MAGIC The same endpoint is reachable at `POST /serving-endpoints/{name}/invocations` with a bearer token (for
# MAGIC non-Python clients), and the console offers **"Export to Databricks Apps"** to wrap it in a chat UI — that is 10.5.
# MAGIC
# MAGIC > ⚠️ **GOTCHA:** do not present the endpoint name pattern (`ka-<id>-endpoint`) or the payload schema as fixed.
# MAGIC > When doc Q&A is not enough (tools, multi-step planning), the KA is the wrong tool — reach for a custom
# MAGIC > `ResponsesAgent` (Module 09) or a Multi-Agent Supervisor (10.3).

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 3 — Multi-Agent Supervisor (10.3) · GA (Feb 2026) · [Theory + Hands-on, console]
# MAGIC The **Multi-Agent Supervisor** (a.k.a. Supervisor Agent) is the **managed** version of Module 09.9's
# MAGIC agents-as-tools pattern. You declare specialist sub-agents; it **routes and composes** one cited answer.
# MAGIC
# MAGIC **What it orchestrates:**
# MAGIC - **Genie Agents** — natural-language Q&A over Unity Catalog **tables** (structured: bookings, flight status),
# MAGIC - **Knowledge Assistants** — cited answers over **unstructured** docs (the 10.2 KA),
# MAGIC - **MCP servers** — governed **tools / actions** (managed or external).
# MAGIC
# MAGIC **Console flow** *(confirm labels):* Agent Bricks → Multi-Agent Supervisor → add each sub-agent with a
# MAGIC **routing description** (crisp, non-overlapping — vague descriptions are the #1 cause of wrong routing) →
# MAGIC create → test routing with unambiguous example questions.
# MAGIC
# MAGIC **Unity Airways example:** *policy* → the Knowledge Assistant, *"is my flight delayed / what's my booking"* →
# MAGIC a **Genie Agent** over the ops tables, *action (rebook / open a ticket)* → an **MCP** tool.
# MAGIC
# MAGIC > 💡 **TIP:** three sharp sub-agents beat six overlapping ones — the same lesson as a good `tool_description`
# MAGIC > in Module 09.4, now enforced through the console. A deployed Module 09 agent endpoint can itself be a sub-agent.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 4 — Custom Agents (10.4) · the escape hatch to code · [Theory]
# MAGIC When the tiles cannot express what you need — bespoke tool logic, unusual control flow, a specific framework —
# MAGIC drop back to a **Custom Agent**: a Python **`ResponsesAgent`** + your framework (the Module 09 artifact).
# MAGIC
# MAGIC - **What it is:** exactly `agent.py` from Module 09.6, ending in `mlflow.models.set_model(AGENT)`.
# MAGIC - **How it deploys:** via **`agents.deploy(UC_MODEL, version)`** (→ Serving endpoint + Review App + feedback model,
# MAGIC   Module 11) **or** behind a **Databricks App** (10.5) for a fully custom front end.
# MAGIC - **Same governance:** it registers to Unity Catalog and serves like any tile, in the same permission/monitoring model.
# MAGIC
# MAGIC ```python
# MAGIC # Reference only (Module 09 built + registered unity_airways.rag.ua_support_agent):
# MAGIC # from databricks import agents
# MAGIC # agents.deploy(UC_MODEL, version)      # then front it with a Databricks App (10.5) or use as a sub-agent (10.3)
# MAGIC ```
# MAGIC
# MAGIC > ⚠️ **GOTCHA:** don't force a tile to do a Custom Agent's job. If you are hacking instructions to fake tool
# MAGIC > logic the tile doesn't support, that is the signal to switch to code (Module 09). The escape hatch is a feature.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 5 — ★ Databricks Apps (10.5) · GA · [Hands-on]
# MAGIC An endpoint is an API, not a product. **Databricks Apps** hosts a Python web app (Streamlit / Dash / Flask /
# MAGIC Gradio / FastAPI) *in* your workspace, behind SSO, next to your data.
# MAGIC
# MAGIC - **The whole contract:** a source directory — `app.py` (the chat UI) + `app.yaml` (start `command` + `env` with
# MAGIC   a `valueFrom` **serving-endpoint resource**) + `requirements.txt` (only extras).
# MAGIC - **Deploy:** `databricks apps create` → `databricks workspace import-dir .` → `databricks apps deploy
# MAGIC   --source-code-path` → `databricks apps get` (confirm `app_status.state: RUNNING`) → `databricks apps logs`.
# MAGIC - **Auth:** the app runs as its **own service principal** with scoped resource creds — **no secrets in code**.
# MAGIC
# MAGIC **➡️ Full hands-on scaffold (writes `app.py` + `app.yaml`, prints the CLI flow): `10-5-databricks-apps.py`.**
# MAGIC
# MAGIC > 📌 **IMPORTANT:** declare the serving endpoint as a **resource** (permission **Can Query**) and reference it
# MAGIC > via **`valueFrom`** — never a hardcoded ID or token. The app is a thin UI; the agent endpoint does the work.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 6 — Get started end-to-end (10.6) · [Hands-on]
# MAGIC The full low-code journey in one pass, so you can run it as a single demo:
# MAGIC 1. **Prototype (10.1):** in **AI Playground**, pick `databricks-claude-sonnet-4-5`, attach the AI Search
# MAGIC    retriever + a UC function, confirm the shape works.
# MAGIC 2. **Build the agent (10.2 / 10.3):** a **Knowledge Assistant** over the Module 04 index for pure Q&A; if the
# MAGIC    use case spans structured + unstructured + actions, wrap specialists in a **Multi-Agent Supervisor**.
# MAGIC 3. **(If needed) go custom (10.4):** author a **Custom Agent** (`ResponsesAgent`, Module 09) and deploy it.
# MAGIC 4. **Front it (10.5 ★):** a **Databricks App** (Streamlit chat) wired to the endpoint via a resource.
# MAGIC 5. **Govern + monitor (Module 11):** MLflow tracing/monitoring on the endpoint; a Review App for feedback;
# MAGIC    AI Gateway guardrails at serving time.
# MAGIC
# MAGIC **How to verify:** a stakeholder with only the app URL asks a Unity Airways question and gets a cited answer —
# MAGIC no notebook, no API token, no code on their side.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 7 — Information Extraction (10.7) · **Beta** · [Theory + Hands-on]
# MAGIC The **Information Extraction** tile turns unstructured docs / PDFs / images into a **structured table** via a
# MAGIC generated JSON schema — no parsing code. Unity Airways example: scanned booking confirmations → a governed table
# MAGIC with `booking_ref`, `passenger_name`, `flight_number`, `claim_amount`.
# MAGIC
# MAGIC > ⚠️ **GOTCHA:** Information Extraction is **Beta** — label it as such, expect UI/schema changes, and verify
# MAGIC > enrollment before a production timeline. **For a hardened batch job today, use the GA SQL AI functions below.**

# COMMAND ----------

# MAGIC %md
# MAGIC ### GA alternative (runnable): `ai_parse_document` / `ai_extract`
# MAGIC These SQL AI functions are **GA** and the console-tile's batch cousin — the safe path for production pipelines.

# COMMAND ----------

# MAGIC %sql
# MAGIC -- NOTE: verify vs current docs — AI Function signatures evolve; confirm on the AI Functions doc page.
# MAGIC -- ai_parse_document(<file bytes>): OCR / layout-parse a document into structured text+layout JSON (GA).
# MAGIC -- Point READ_FILES at your Volume of policy/booking PDFs.
# MAGIC SELECT
# MAGIC   path,
# MAGIC   ai_parse_document(content) AS parsed          -- structured parse of each document
# MAGIC FROM READ_FILES('/Volumes/unity_airways/rag/ua_policy_docs/*.pdf', format => 'binaryFile')
# MAGIC LIMIT 3;

# COMMAND ----------

# MAGIC %sql
# MAGIC -- ai_extract(text, array(fields)): pull named fields out of free text into columns (GA).
# MAGIC -- This is the SQL equivalent of the Information Extraction tile's schema-guided extraction.
# MAGIC SELECT ai_extract(
# MAGIC   'Booking UA123 for Jane Doe, flight UA456 on 2026-07-20, refund of $250 approved.',
# MAGIC   array('booking_ref', 'passenger_name', 'flight_number', 'refund_amount')
# MAGIC ) AS extracted;

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 8 — Custom LLM (10.8) · **Beta** · [Theory + Hands-on]
# MAGIC The **Custom LLM** tile builds a **task-tuned model** for a narrow domain text task from your examples —
# MAGIC the four shapes: **summarize**, **classify**, **transform**, **generate**. Unity Airways example: a ticket
# MAGIC classifier (`refund / rebooking / baggage / complaint`) and a thread summarizer for the support queue.
# MAGIC
# MAGIC > ⚠️ **GOTCHA:** Custom LLM is **Beta** — mark the maturity, verify enrollment, don't promise it on a production
# MAGIC > date without checking current docs. **For scaled, GA text tasks today, use the SQL AI functions below.**

# COMMAND ----------

# MAGIC %md
# MAGIC ### GA alternative (runnable): `ai_classify` / `ai_summarize` / `ai_gen`
# MAGIC All three are **GA** and cover the Custom LLM task shapes without managing any fine-tuning.

# COMMAND ----------

# MAGIC %sql
# MAGIC -- NOTE: verify vs current docs — confirm signatures on the AI Functions doc page before asserting to a customer.
# MAGIC -- ai_classify(text, array(labels)): route an inbound ticket into a category (GA) — the Custom LLM "classify" shape.
# MAGIC SELECT ai_classify(
# MAGIC   'My checked bag never arrived at baggage claim after flight UA456.',
# MAGIC   array('refund', 'rebooking', 'baggage', 'complaint')
# MAGIC ) AS ticket_category;

# COMMAND ----------

# MAGIC %sql
# MAGIC -- ai_summarize(text[, max_words]): a one-line disposition for the support queue (GA) — the "summarize" shape.
# MAGIC SELECT ai_summarize(
# MAGIC   'Passenger waited three hours, flight delayed twice, missed the connection to Tokyo, ' ||
# MAGIC   'and is now asking for compensation and a hotel voucher for the overnight stay.',
# MAGIC   20
# MAGIC ) AS disposition;

# COMMAND ----------

# MAGIC %sql
# MAGIC -- ai_gen(prompt): draft a policy-grounded response (GA) — the "generate" shape.
# MAGIC SELECT ai_gen(
# MAGIC   'Draft a short, polite reply telling a Unity Airways passenger their Basic Economy fare is ' ||
# MAGIC   'non-refundable, but they may be eligible for travel credit. Two sentences.'
# MAGIC ) AS draft_reply;

# COMMAND ----------

# MAGIC %md
# MAGIC ## Recap, gotchas and next step
# MAGIC **What you assembled**
# MAGIC - **Prototyped** the shape in **AI Playground (10.1, GA)**, built a cited **Knowledge Assistant (10.2 ★, GA)** and
# MAGIC   queried its endpoint, composed specialists with a **Multi-Agent Supervisor (10.3, GA)**, kept the **Custom Agent
# MAGIC   (10.4)** escape hatch, and put a **Databricks App (10.5 ★, GA)** in front.
# MAGIC - Ran the **GA SQL alternatives** for the two **Beta** tiles: `ai_parse_document` / `ai_extract` (10.7) and
# MAGIC   `ai_classify` / `ai_summarize` / `ai_gen` (10.8).
# MAGIC
# MAGIC **Gotchas to remember**
# MAGIC - **Name the maturity:** GA — AI Playground, Knowledge Assistant, Multi-Agent Supervisor. **Beta** — Information
# MAGIC   Extraction, Custom LLM (prefer the GA SQL AI functions for hardened pipelines).
# MAGIC - **Module 10 reuses, it doesn't replace** — the KA reads the Module 04 index; the Supervisor can front the
# MAGIC   Module 09 agent and Genie Agents; a Custom Agent wraps Module 05/09 code.
# MAGIC - **Don't present JS-rendered console/endpoint specifics as fixed** — confirm nav labels, endpoint names, and
# MAGIC   payload schemas in the current console before wiring a client or asserting them to a customer.
# MAGIC
# MAGIC **The low-code Unity Airways experience is shippable.** Deploy path = **Databricks Apps (10.5)** for a branded
# MAGIC end-user UI, **or `agents.deploy()` (Module 11)** for the Agent Framework endpoint + Review App + monitoring.
