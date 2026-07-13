# Databricks notebook source
# MAGIC %md
# MAGIC # 10.5 ★ — Build and deploy a GenAI app on Databricks Apps
# MAGIC **Roadmap:** Module 10 (Agent Bricks and no/low-code agents) · Topic 10.5 (cornerstone) · [Hands-on] (+ [Theory])
# MAGIC
# MAGIC ## Read this first — a scaffold notebook, not a run-all
# MAGIC A **Databricks App is deployed from files + the CLI**, not executed cell by cell. So this notebook is a
# MAGIC **driver / scaffold**: it writes the two files that *define* the app (`app.py` + `app.yaml`, plus a
# MAGIC `requirements.txt`), then hands you the exact **`databricks apps`** commands to ship them. The chat UI
# MAGIC itself runs on the Apps platform, next to your data — not in this notebook.
# MAGIC
# MAGIC ## What you build
# MAGIC A thin **Streamlit** chat UI that queries a **deployed agent serving endpoint** — the Module 09
# MAGIC `agents.deploy()` endpoint for `unity_airways.rag.ua_support_agent`, or a **Knowledge Assistant** endpoint
# MAGIC from 10.2. The app is a source directory:
# MAGIC 1. **`app.py`** — the Streamlit chat UI (`st.set_page_config()` first, cached client, endpoint query).
# MAGIC 2. **`app.yaml`** — the manifest: the start `command` + an `env` var bound to a **serving-endpoint resource** via `valueFrom`.
# MAGIC 3. **`requirements.txt`** — only extras (`databricks-sdk`, `openai`); the frameworks are pre-installed.
# MAGIC
# MAGIC ## Prerequisites (read before running)
# MAGIC - **Compute (to run this notebook):** any serverless/DBR notebook — it only writes files and prints commands.
# MAGIC   The **app** itself runs on the Databricks Apps runtime (**Python 3.11, ~2 vCPU / 6 GB**, frameworks pre-installed).
# MAGIC - **A deployed endpoint to front:** the Module 09 agent endpoint (from `agents.deploy("unity_airways.rag.ua_support_agent", …)`)
# MAGIC   **or** a Knowledge Assistant endpoint (10.2). Read the exact endpoint name from the deploy output / console — it is auto-generated.
# MAGIC - **`databricks` CLI configured** (v0.294.0+; **OAuth** recommended — `databricks apps logs` does not work with a PAT).
# MAGIC - **Unity Catalog:** rights to **create an app** and to grant the app **Can Query** on the serving endpoint.
# MAGIC - **Secrets:** none — the app runs as its **own service principal**; scoped creds are injected. No PAT in code.
# MAGIC - **Learner-set identifiers:** app name + workspace upload path in the CLI cell below; endpoint name via the `valueFrom` resource.
# MAGIC
# MAGIC > 📌 **The one rule of this topic:** a Databricks App is **a source directory (`app.py` + `app.yaml`) that the
# MAGIC > platform runs as a scoped service principal**. Keep it safe and portable by **declaring the serving endpoint
# MAGIC > as a resource** (permission **Can Query**) and **referencing it with `valueFrom`** — never a hardcoded ID or token.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. `app.py` — the Streamlit chat UI that queries the agent endpoint
# MAGIC `%%writefile` writes the cell body to a file next to the notebook. Notes on the pattern:
# MAGIC - **`st.set_page_config()` must be the very first Streamlit call** — anything before it errors.
# MAGIC - **Cache the client with `@st.cache_resource`** so Streamlit reuses one connection across reruns (see gotchas).
# MAGIC - **No endpoint name, no token in code** — the endpoint name arrives from `app.yaml` (`valueFrom`), and the
# MAGIC   SDK's `Config()` auto-detects the app service-principal credentials the platform injects.

# COMMAND ----------

# MAGIC %%writefile app.py
# MAGIC # app.py — a thin Streamlit chat UI over a deployed agent / Knowledge Assistant endpoint.
# MAGIC # The UI is deliberate: capture the message, call the endpoint, render the reply, keep turn history.
# MAGIC import os
# MAGIC import requests
# MAGIC import streamlit as st
# MAGIC from databricks.sdk import WorkspaceClient
# MAGIC from databricks.sdk.core import Config
# MAGIC
# MAGIC # st.set_page_config() MUST be the first Streamlit call on the page.
# MAGIC st.set_page_config(page_title="Unity Airways — Support", page_icon="✈️", layout="centered")
# MAGIC
# MAGIC # Injected by app.yaml (valueFrom: serving-endpoint). The NAME of the deployed endpoint — the Module 09
# MAGIC # agents.deploy() endpoint for unity_airways.rag.ua_support_agent, or a Knowledge Assistant endpoint (10.2).
# MAGIC # Nothing hardcoded here: valueFrom resolves the resource at runtime, so the app stays portable + secret-free.
# MAGIC ENDPOINT = os.environ["SERVING_ENDPOINT"]
# MAGIC
# MAGIC
# MAGIC @st.cache_resource                      # build ONE client, reuse it across Streamlit reruns
# MAGIC def get_client():
# MAGIC     # WorkspaceClient() auto-detects the app service-principal creds via SDK Config()
# MAGIC     # (DATABRICKS_CLIENT_ID / DATABRICKS_CLIENT_SECRET are injected by the platform — no code needed).
# MAGIC     # NOTE: confirm get_open_ai_client() and the exact serving-endpoint resource key vs current docs —
# MAGIC     # the Databricks Apps doc pages are JS-rendered; treat these strings as live re-check pending.
# MAGIC     return WorkspaceClient().serving_endpoints.get_open_ai_client()
# MAGIC
# MAGIC
# MAGIC def ask_agent_rest(messages):
# MAGIC     # Dependency-light FALLBACK: a signed POST to /serving-endpoints/<name>/invocations.
# MAGIC     # Prefer this when your agent speaks the Responses schema or you want raw REST instead of the OpenAI client.
# MAGIC     cfg = Config()                       # picks up the app SP credentials — no secret in code
# MAGIC     headers = cfg.authenticate()         # adds the Authorization: Bearer header
# MAGIC     headers["Content-Type"] = "application/json"
# MAGIC     r = requests.post(
# MAGIC         f"https://{cfg.host}/serving-endpoints/{ENDPOINT}/invocations",
# MAGIC         headers=headers,
# MAGIC         json={"messages": messages},     # match your agent / KA input schema
# MAGIC         timeout=120,
# MAGIC     )
# MAGIC     r.raise_for_status()
# MAGIC     return r.json()
# MAGIC
# MAGIC
# MAGIC client = get_client()
# MAGIC
# MAGIC st.title("Unity Airways — Support Assistant")
# MAGIC
# MAGIC if "messages" not in st.session_state:
# MAGIC     st.session_state.messages = []
# MAGIC
# MAGIC for m in st.session_state.messages:              # replay the conversation on every rerun
# MAGIC     with st.chat_message(m["role"]):
# MAGIC         st.markdown(m["content"])
# MAGIC
# MAGIC if prompt := st.chat_input("Ask about a flight, refund, or baggage rule…"):
# MAGIC     st.session_state.messages.append({"role": "user", "content": prompt})
# MAGIC     with st.chat_message("user"):
# MAGIC         st.markdown(prompt)
# MAGIC     with st.chat_message("assistant"):
# MAGIC         resp = client.chat.completions.create(   # OpenAI-compatible call to the endpoint
# MAGIC             model=ENDPOINT,
# MAGIC             messages=st.session_state.messages,
# MAGIC         )
# MAGIC         answer = resp.choices[0].message.content
# MAGIC         st.markdown(answer)
# MAGIC         # REST fallback (swap in if your endpoint uses the Responses schema):
# MAGIC         # answer = str(ask_agent_rest(st.session_state.messages))
# MAGIC     st.session_state.messages.append({"role": "assistant", "content": answer})

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. `app.yaml` — start command + the injected endpoint resource
# MAGIC Two keys do the work: **`command`** (the argv list that starts the app) and **`env`** (variables injected at
# MAGIC runtime). `SERVING_ENDPOINT` uses **`valueFrom`** to resolve the serving-endpoint **resource** you attach in the
# MAGIC app UI — so the endpoint name lives in config, never in the repo.

# COMMAND ----------

# MAGIC %%writefile app.yaml
# MAGIC command:
# MAGIC   - "streamlit"
# MAGIC   - "run"
# MAGIC   - "app.py"
# MAGIC
# MAGIC env:
# MAGIC   # Bind SERVING_ENDPOINT to the serving-endpoint resource you attach in the app UI
# MAGIC   # (Configure -> + Add resource -> Serving endpoint, permission: Can Query).
# MAGIC   # valueFrom resolves the resource at runtime — no endpoint name or token in the repo.
# MAGIC   - name: SERVING_ENDPOINT
# MAGIC     valueFrom: serving-endpoint
# MAGIC
# MAGIC # Port: the runtime injects DATABRICKS_APP_PORT (default 8000) and auto-configures Streamlit to it.
# MAGIC # Do NOT bind to 8080. For non-Streamlit frameworks (Flask/FastAPI/Dash), read DATABRICKS_APP_PORT in code.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. `requirements.txt` — only the extras
# MAGIC Streamlit / Dash / Gradio / Flask / FastAPI are **pre-installed** on the Apps runtime — do **not** list them.
# MAGIC List only what the runtime lacks: here the SDK and the OpenAI client.

# COMMAND ----------

# MAGIC %%writefile requirements.txt
# MAGIC databricks-sdk
# MAGIC openai

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Resources + service principal — scoped auth, no secrets
# MAGIC - The app runs as **its own service principal** — not you, and it does **not** carry your permissions.
# MAGIC - Attach the model serving endpoint as a **resource** and grant **Can Query** (the minimal permission for a chat app).
# MAGIC   Databricks injects scoped credentials that the SDK reads automatically; `DATABRICKS_CLIENT_ID` /
# MAGIC   `DATABRICKS_CLIENT_SECRET` appear in the app env with zero code.
# MAGIC - Because `app.yaml` references the endpoint via `valueFrom: serving-endpoint`, moving the app between
# MAGIC   workspaces is a **config change, not a code change**.
# MAGIC - Need per-user row/column filtering? Turn on **user authorization** and read the `x-forwarded-access-token`
# MAGIC   header so the query runs as the signed-in user — that trade-off is the deep dive in **11.9**.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Build the exact CLI commands for your workspace
# MAGIC The cell below only **prints** the commands filled in for your user — copy them into a terminal where the
# MAGIC `databricks` CLI is configured. It does not deploy from here (deployment needs the configured CLI, not the notebook).

# COMMAND ----------

# App name rules: <= 26 chars, lowercase letters / numbers / hyphens, NO underscores.
APP_NAME = "ua-support-chat"

# Where to upload the app source in the workspace. Derive from the current user when possible.
try:
    _user = (
        dbutils.notebook.entry_point.getDbutils().notebook().getContext().userName().get()
    )
except Exception:
    _user = "me@unity.com"   # edit to your workspace user if the lookup is unavailable
WORKSPACE_PATH = f"/Workspace/Users/{_user}/apps/{APP_NAME}"

print(f"""# Run these from the folder holding app.py / app.yaml / requirements.txt, CLI configured (OAuth recommended):

# 1. Create the app object (it runs as its own service principal)
databricks apps create {APP_NAME}

# 2. Upload the source directory into the workspace
databricks workspace mkdirs {WORKSPACE_PATH}
databricks workspace import-dir . {WORKSPACE_PATH}

# 3. Deploy from that workspace path
databricks apps deploy {APP_NAME} --source-code-path {WORKSPACE_PATH}

# 4. Confirm it is RUNNING and read the URL; stream logs on first boot
databricks apps get {APP_NAME} -o json   # look for app_status.state = RUNNING and the url
databricks apps logs {APP_NAME}          # [SYSTEM]/[APP] lines; "App started successfully" (needs OAuth auth)

# After first deploy: in the app UI add the serving endpoint as a resource (Can Query), then redeploy so
# valueFrom resolves. Share the app with CAN USE (support team) and CAN MANAGE (developers) only.
""")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6. The real deploy flow (reference) — and the fast start
# MAGIC The canonical `databricks apps` flow (subcommands confirmed against the CLI — note there is **no** `init` or
# MAGIC `validate` subcommand):
# MAGIC
# MAGIC ```bash
# MAGIC # 1. Create the app object (name <= 26 chars, lowercase/hyphens, no underscores)
# MAGIC databricks apps create ua-support-chat
# MAGIC
# MAGIC # 2. Upload the source directory into the workspace
# MAGIC databricks workspace mkdirs /Workspace/Users/me@unity.com/apps/ua-support-chat
# MAGIC databricks workspace import-dir . /Workspace/Users/me@unity.com/apps/ua-support-chat
# MAGIC
# MAGIC # 3. Deploy from that path
# MAGIC databricks apps deploy ua-support-chat \
# MAGIC   --source-code-path /Workspace/Users/me@unity.com/apps/ua-support-chat
# MAGIC
# MAGIC # 4. Confirm RUNNING + read the URL; stream logs on boot
# MAGIC databricks apps get ua-support-chat -o json    # app_status.state: RUNNING, plus the url
# MAGIC databricks apps logs ua-support-chat            # needs OAuth auth (not a PAT)
# MAGIC ```
# MAGIC
# MAGIC - **The app runs as a service principal** with scoped resource auth — **no secrets** to manage.
# MAGIC - **Faster start:** the **AI Playground** (10.1) "**Export to Databricks Apps**" button scaffolds this exact
# MAGIC   `app.py` + `app.yaml` wired to your endpoint — deploy that, then customize the UI.
# MAGIC - **Iterate locally** with `databricks apps run-local` before you deploy.
# MAGIC
# MAGIC The commented `%sh` cell below carries the same flow. It is commented on purpose — the `databricks` CLI and its
# MAGIC auth are configured on **your machine**, not on notebook compute. Uncomment + edit only if your driver has the CLI.

# COMMAND ----------

# MAGIC %sh
# MAGIC # Uncomment ONLY if the `databricks` CLI is installed + configured on this notebook's driver.
# MAGIC # databricks apps create ua-support-chat
# MAGIC # databricks workspace mkdirs /Workspace/Users/me@unity.com/apps/ua-support-chat
# MAGIC # databricks workspace import-dir . /Workspace/Users/me@unity.com/apps/ua-support-chat
# MAGIC # databricks apps deploy ua-support-chat --source-code-path /Workspace/Users/me@unity.com/apps/ua-support-chat
# MAGIC # databricks apps get ua-support-chat -o json
# MAGIC # databricks apps logs ua-support-chat

# COMMAND ----------

# MAGIC %md
# MAGIC ## 7. Recap, gotchas and next step
# MAGIC **What you built**
# MAGIC - `app.py` — a thin Streamlit chat UI that queries the deployed endpoint (OpenAI-compatible client + REST fallback).
# MAGIC - `app.yaml` — `command: ["streamlit","run","app.py"]` and `SERVING_ENDPOINT` bound via `valueFrom: serving-endpoint`.
# MAGIC - `requirements.txt` — only the extras (`databricks-sdk`, `openai`).
# MAGIC - The `databricks apps` **create → import-dir → deploy --source-code-path → get → logs** flow, printed for your workspace.
# MAGIC
# MAGIC **Gotchas to remember**
# MAGIC - **Never hardcode a PAT or endpoint ID** in `app.py` — declare a resource, reference it via `valueFrom`, let `Config()` auth.
# MAGIC - **`st.set_page_config()` must run first**; **`@st.cache_resource`** the client (one connection per app, not per rerun).
# MAGIC - **Never bind 8080** — the runtime injects `DATABRICKS_APP_PORT` (default 8000) and auto-configures Streamlit.
# MAGIC - **Grant the app SP `Can Query`** on the endpoint, then **redeploy** — otherwise it 403s at runtime.
# MAGIC - **`databricks apps logs` needs OAuth** (not a PAT); use `databricks apps get` for status either way.
# MAGIC - **`get_open_ai_client()` + the `serving-endpoint` resource key are grounded on the Apps skill/docs** — the doc
# MAGIC   pages are JS-rendered, so confirm the exact strings against current docs before asserting them to a customer.
# MAGIC - A **Databricks App** is the product UX; the **`agents.deploy()` Review App** is for SMEs grading answers — different jobs, same endpoint.
# MAGIC
# MAGIC **Next:** back to the module lab `10-module-lab.py` for the full low-code journey (10.1–10.8), then **Module 11**
# MAGIC for serving, the Review App, AI Gateway, and the Databricks Apps **auth** deep dive (11.9).
