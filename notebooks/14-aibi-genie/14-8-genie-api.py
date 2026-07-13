# Databricks notebook source
# MAGIC %md
# MAGIC # 14.8 — Genie Agents API (Conversation API) round-trip: REST and the Python SDK
# MAGIC **Roadmap:** Module 14 (AI/BI Genie) · Topic 14.8 · [Hands-on] · standalone cornerstone-style notebook
# MAGIC
# MAGIC The **Genie Agents API** (a.k.a. the Conversation API) is how you drive a Genie Agent programmatically — the
# MAGIC engine behind **embedding** (14.7), automation, and using a Genie Agent as an **agent tool** (Modules 09.11 / 10).
# MAGIC This notebook runs the full round-trip **two ways** against the **"Unity Airways Revenue Analytics"** Agent:
# MAGIC 1. **Raw REST** (`requests`) — the exact endpoints, so you can port to any language / external app.
# MAGIC 2. **Python SDK** (`databricks-sdk`, `w.genie.*`) — the ergonomic path with `_and_wait` polling helpers.
# MAGIC
# MAGIC **The round-trip:** `start-conversation` → **poll the message** until a terminal status → **fetch the
# MAGIC query-result** (rows) → optional **follow-up** on the same `conversation_id`.
# MAGIC
# MAGIC ## Prerequisites
# MAGIC - **A Genie Agent** (build it in `14-module-lab.py` Step 2). Copy its **`space_id`** from the URL
# MAGIC   `.../genie/rooms/<space_id>`. *(The product is "Genie Agents"; the REST path keeps the legacy `spaces` noun.)*
# MAGIC - **A serverless (or Pro) SQL warehouse** attached to the Agent (it runs the generated SQL).
# MAGIC - **Auth:**
# MAGIC   - In-workspace: the SDK uses notebook auth automatically. For the REST cells, a **PAT** is simplest — store it in
# MAGIC     a **secret scope** (never hardcode). `TOKEN = dbutils.secrets.get("genie", "pat")`.
# MAGIC   - External client: a **PAT or OAuth (service principal)** token with access to the Agent + warehouse.
# MAGIC - **Compute:** serverless notebook or DBR 15.4 LTS+. `databricks-sdk>=0.73` for the verified `w.genie.*` surface.
# MAGIC
# MAGIC > 📌 **IMPORTANT:** UC permissions apply to the calling identity — the API does **not** bypass governance. A user
# MAGIC > (or service principal) only gets rows they're already allowed to see.

# COMMAND ----------

# MAGIC %pip install -U "databricks-sdk>=0.73"
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

# ---- Learner-set variables --------------------------------------------------
SPACE_ID = "REPLACE-with-your-genie-space-id"     # from the Agent URL: .../genie/rooms/<space_id>
QUESTION = "What was total revenue last quarter by fare class?"

# Host + token for the RAW REST cells. In-workspace you can derive both from the notebook context.
HOST  = spark.conf.get("spark.databricks.workspaceUrl", None)
HOST  = f"https://{HOST}" if HOST else "https://<your-workspace>.cloud.databricks.com"

# Prefer a secret scope over a hardcoded token. Falls back to the notebook API token in-workspace.
try:
    TOKEN = dbutils.secrets.get(scope="genie", key="pat")
except Exception:
    TOKEN = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiToken().get()

print("Host   :", HOST)
print("Space  :", SPACE_ID)
print("Token  :", "set" if TOKEN else "MISSING")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Part A — Raw REST round-trip (`requests`)
# MAGIC Base path: `/api/2.0/genie/spaces/{space_id}`. These are the **verified endpoints** from the P5 build brief.
# MAGIC 1. `POST .../start-conversation`  body `{"content": "..."}`  → `conversation_id` + `message_id`
# MAGIC 2. `GET  .../conversations/{conversation_id}/messages/{message_id}`  → poll `status` to a terminal state
# MAGIC 3. `GET  .../conversations/{conversation_id}/messages/{message_id}/query-result`  → the SQL result rows
# MAGIC 4. `POST .../conversations/{conversation_id}/messages`  body `{"content": "..."}`  → a follow-up (same context)

# COMMAND ----------

import time, requests

BASE = f"{HOST}/api/2.0/genie/spaces/{SPACE_ID}"
HDRS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
TERMINAL = {"COMPLETED", "FAILED", "CANCELLED", "QUERY_RESULT_EXPIRED"}

def rest_start(content):
    """1) Start a conversation. Returns (conversation_id, message_id)."""
    r = requests.post(f"{BASE}/start-conversation", headers=HDRS, json={"content": content}, timeout=30)
    r.raise_for_status()
    j = r.json()
    # The response nests conversation + message; field names can vary slightly by version — read defensively.
    conv = j.get("conversation_id") or j.get("conversation", {}).get("id")
    msg  = j.get("message_id") or j.get("message", {}).get("id")
    return conv, msg

def rest_poll(conv, msg, timeout_s=180, every_s=2):
    """2) Poll the message until a terminal status. Returns the message JSON."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        r = requests.get(f"{BASE}/conversations/{conv}/messages/{msg}", headers=HDRS, timeout=30)
        r.raise_for_status()
        m = r.json()
        status = m.get("status")
        print("  status:", status)
        if status in TERMINAL:
            return m
        time.sleep(every_s)
    raise TimeoutError("Genie message did not reach a terminal status in time.")

def rest_query_result(conv, msg, attachment_id=None):
    """3) Fetch the SQL result rows for a completed message (or a specific attachment)."""
    url = (f"{BASE}/conversations/{conv}/messages/{msg}/attachments/{attachment_id}/query-result"
           if attachment_id else
           f"{BASE}/conversations/{conv}/messages/{msg}/query-result")
    r = requests.get(url, headers=HDRS, timeout=60)
    r.raise_for_status()
    return r.json()

# COMMAND ----------

if SPACE_ID.startswith("REPLACE"):
    print("[skipped] Set SPACE_ID first.")
else:
    conv, msg = rest_start(QUESTION)
    print("conversation_id:", conv, "\nmessage_id     :", msg)
    message = rest_poll(conv, msg)
    print("\nterminal status:", message.get("status"))

    # Attachments carry the answer: a "text" attachment (prose) and/or a "query" attachment (SQL + statement).
    for att in message.get("attachments", []):
        if att.get("text"):
            print("\nGenie says:", att["text"].get("content"))
        if att.get("query"):
            print("\nGenerated SQL:\n", att["query"].get("query"))
            qr = rest_query_result(conv, msg, attachment_id=att.get("attachment_id"))
            sr = qr.get("statement_response", qr)
            result = (sr.get("result") or {})
            rows = result.get("data_array") or []
            cols = [c["name"] for c in (sr.get("manifest", {}).get("schema", {}).get("columns", []))]
            print("\nColumns:", cols)
            for row in rows[:10]:
                print(row)

# COMMAND ----------

# MAGIC %md
# MAGIC ### Follow-up over REST (same conversation → Genie keeps context)

# COMMAND ----------

if not SPACE_ID.startswith("REPLACE"):
    r = requests.post(f"{BASE}/conversations/{conv}/messages", headers=HDRS,
                      json={"content": "Now break that down by loyalty tier."}, timeout=30)
    r.raise_for_status()
    fmsg = r.json().get("message_id") or r.json().get("id")
    follow = rest_poll(conv, fmsg)
    for att in follow.get("attachments", []):
        if att.get("query"):
            print("Follow-up SQL:\n", att["query"].get("query"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Part B — Python SDK (`w.genie.*`) — the ergonomic path
# MAGIC The SDK collapses start + poll into `_and_wait` helpers (default 20-min timeout) and returns typed objects.
# MAGIC **Verified surface (databricks-sdk 0.73.0):**
# MAGIC `start_conversation`, `start_conversation_and_wait`, `create_message`, `create_message_and_wait`, `get_message`,
# MAGIC `get_message_query_result`, `get_message_attachment_query_result`, `get_space`, `list_spaces`.

# COMMAND ----------

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.dashboards import MessageStatus

w = WorkspaceClient()   # notebook auth in-workspace; or WorkspaceClient(host=..., token=...) externally

def sdk_ask(space_id, content):
    """Start a conversation, wait for completion, return the GenieMessage."""
    return w.genie.start_conversation_and_wait(space_id=space_id, content=content)

def sdk_print_answer(space_id, msg):
    """Print prose + generated SQL + the first rows for a completed GenieMessage."""
    print("status:", msg.status)
    if msg.status != MessageStatus.COMPLETED:
        print("error:", getattr(msg, "error", None)); return
    mid = msg.message_id or msg.id
    for att in (msg.attachments or []):
        if att.text:
            print("\nGenie says:", att.text.content)
        if att.query:
            print("\nGenerated SQL:\n", att.query.query)
            res = w.genie.get_message_query_result(
                space_id=space_id, conversation_id=msg.conversation_id, message_id=mid)
            sr = res.statement_response
            if sr and sr.result and sr.result.data_array:
                cols = [c.name for c in sr.manifest.schema.columns]
                print("\nColumns:", cols)
                for row in sr.result.data_array[:10]:
                    print(row)

# COMMAND ----------

if SPACE_ID.startswith("REPLACE"):
    print("[skipped] Set SPACE_ID first.")
else:
    # Optional: confirm the Agent exists and see its warehouse.
    space = w.genie.get_space(space_id=SPACE_ID)
    print("Agent:", space.title, "| warehouse:", space.warehouse_id)

    msg = sdk_ask(SPACE_ID, QUESTION)
    sdk_print_answer(SPACE_ID, msg)

    # Follow-up in the same conversation (context preserved).
    follow = w.genie.create_message_and_wait(
        space_id=SPACE_ID, conversation_id=msg.conversation_id,
        content="Compare that to the same quarter a year earlier.")
    print("\n--- follow-up ---")
    sdk_print_answer(SPACE_ID, follow)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Verify it worked
# MAGIC - The **SQL** printed by REST and by the SDK for the same question should match what the Agent shows in the UI.
# MAGIC - The **rows** should be the governed answer (revenue by fare class, cancelled excluded) — ideally via the
# MAGIC   `bookings_metrics` metric view if it's attached (Module 15).
# MAGIC - The **follow-up** should build on prior context (Genie resolves "that" to the previous result).
# MAGIC
# MAGIC ## Gotchas & recap
# MAGIC - **REST path = `spaces`, SDK namespace = `w.genie`** — that split is the #1 confusion. Poll the **message** for
# MAGIC   status; fetch the **query-result** separately for rows.
# MAGIC - **Statuses:** `SUBMITTED → FILTERING_CONTEXT → ASKING_AI → PENDING_WAREHOUSE → EXECUTING_QUERY → COMPLETED`
# MAGIC   (or `FAILED` / `CANCELLED` / `QUERY_RESULT_EXPIRED`). Only poll to a **terminal** state.
# MAGIC - **Response field names can shift** between API versions — read defensively (as the REST helpers do) and
# MAGIC   **re-verify `w.genie.*` against your installed SDK**; never invent a method name.
# MAGIC - **Secrets, not hardcoded tokens.** Use a secret scope; the app/service-principal identity governs what's visible.
# MAGIC
# MAGIC **Next:** wrap this round-trip in a **Databricks App** (Module 10) for a branded chat UI, or expose the Agent as a
# MAGIC **managed MCP server** (09.11) so any agent can call it as a structured-data tool.
