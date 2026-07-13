# Databricks notebook source
# MAGIC %md
# MAGIC # 09.6 ★ — Packaging an agent with ResponsesAgent and registering in Unity Catalog
# MAGIC **Roadmap:** Module 09 (Agent fundamentals and tools) · Topic 09.6 (cornerstone) · [Hands-on]
# MAGIC
# MAGIC ## The problem
# MAGIC Coming out of 09.3 / 09.5 you have a working agent object in a notebook: it calls
# MAGIC `databricks-claude-sonnet-4-5`, retrieves policy chunks from `unity_airways.rag.ua_rag_chunks_index`, and
# MAGIC looks up live flight status through the UC function `unity_airways.rag.get_flight_status`. A notebook
# MAGIC object is not a product. To serve it — behind an endpoint, a review app, or a Databricks App — a teammate
# MAGIC has to load the **exact same agent** with the **right credentials** for the LLM, the index, and the function.
# MAGIC
# MAGIC ## What you will build
# MAGIC The five moves that turn the in-memory agent into a governed UC model:
# MAGIC 1. **Wrap it** — an `agent.py` defining a `ResponsesAgent` subclass around the LangGraph tool-calling loop.
# MAGIC 2. **Declare it** — `mlflow.models.set_model(AGENT)` as the last line of `agent.py` (Models-from-Code).
# MAGIC 3. **Log it** — `mlflow.pyfunc.log_model(python_model="agent.py", ..., resources=[...])`.
# MAGIC 4. **Verify it** — `mlflow.models.predict(...)` reloads the model in a clean env and calls it.
# MAGIC 5. **Register it** — `set_registry_uri("databricks-uc")` → `register_model(..., "unity_airways.rag.ua_support_agent")`.
# MAGIC
# MAGIC ### Prerequisites (read before running)
# MAGIC - **Compute:** **serverless notebook/job**, or a **DBR ML runtime** (15.4 LTS ML or later).
# MAGIC - **MLflow:** **>= 3.1** (Models-from-Code, `ResponsesAgent`, `resources`, MLflow 3 logging + UC registry).
# MAGIC - **Tools from 09.3, available in UC (run `09-3-create-tools.py` first):** the AI Search index
# MAGIC   `unity_airways.rag.ua_rag_chunks_index` (Modules 04–05), the UC function
# MAGIC   `unity_airways.rag.get_flight_status`, and the seed table `unity_airways.rag.flight_status_records`
# MAGIC   that the function reads — without the table, `agent.py`'s tool call and the pre-deploy
# MAGIC   `mlflow.models.predict(...)` below fail with `TABLE_OR_VIEW_NOT_FOUND`.
# MAGIC - **Chat serving endpoint:** **`databricks-claude-sonnet-4-5`** — confirm on the supported-models page.
# MAGIC - **Unity Catalog:** `USE CATALOG` on `unity_airways`, `USE SCHEMA` on `rag`, **`EXECUTE` on
# MAGIC   `unity_airways.rag.get_flight_status`** (`agent.py` builds `UCFunctionToolkit` at load time and the
# MAGIC   pre-deploy `mlflow.models.predict(...)` actually calls the tool), and **`CREATE MODEL`** on
# MAGIC   `unity_airways.rag` to register the agent.
# MAGIC - **Secrets:** none — declared `resources=[...]` drive automatic authentication passthrough on deploy.
# MAGIC - **Learner-set identifiers:** edit the constants in Step 0.
# MAGIC
# MAGIC > 📌 **The one rule of this topic:** author new agents on **`ResponsesAgent`** (`from mlflow.pyfunc import
# MAGIC > ResponsesAgent`) — **not** `ChatAgent` (being superseded) or `ChatModel` (legacy). Log **Model-as-Code**
# MAGIC > (`python_model="agent.py"` ending in `set_model`), declare every service in `resources=[...]`, and
# MAGIC > register with a three-level `catalog.schema.model` name.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 0. Install libraries and set variables
# MAGIC `mlflow` (>= 3.1, for `ResponsesAgent` + Models-from-Code + resources), `databricks-langchain` (tools + LLM),
# MAGIC `langgraph` (the tool-calling loop), `databricks-vectorsearch` and `unitycatalog-ai` (the retriever + UC
# MAGIC function clients that `agent.py` builds at load time).

# COMMAND ----------

# MAGIC %pip install -U "mlflow>=3.1" databricks-langchain langgraph databricks-vectorsearch unitycatalog-ai
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

CATALOG      = "unity_airways"
SCHEMA       = "rag"
UC_MODEL     = f"{CATALOG}.{SCHEMA}.ua_support_agent"        # three-level name — catalog.schema.model
INDEX_NAME   = f"{CATALOG}.{SCHEMA}.ua_rag_chunks_index"     # from Modules 04/05 (retriever tool)
UC_FUNCTION  = f"{CATALOG}.{SCHEMA}.get_flight_status"       # from 09-3-create-tools.py (lookup tool)
LLM_ENDPOINT = "databricks-claude-sonnet-4-5"              # confirm on the supported-models page

print("UC model     :", UC_MODEL)
print("Index        :", INDEX_NAME)
print("UC function  :", UC_FUNCTION)
print("LLM endpoint :", LLM_ENDPOINT)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Materialize the agent into `agent.py` (Models-from-Code)
# MAGIC `%%writefile` writes the cell body to a file next to the notebook. This is the **entire agent**, with no
# MAGIC notebook state:
# MAGIC - the three-word config at the top (endpoint, index, function) so the resource list and the agent read
# MAGIC   the same constants;
# MAGIC - the **09.3 tools** (`VectorSearchRetrieverTool` + `UCFunctionToolkit`);
# MAGIC - a **LangGraph tool-calling loop** (`bind_tools` + `ToolNode` + `should_continue`);
# MAGIC - a **`UASupportAgent(ResponsesAgent)`** class implementing `predict` (and `predict_stream`);
# MAGIC - ending in **`mlflow.models.set_model(AGENT)`** — the line that tells MLflow which object is the model.
# MAGIC
# MAGIC > 💡 **TIP:** keep `agent.py` self-contained and importable — no notebook-only globals, no `dbutils` at
# MAGIC > import time. That is what lets MLflow re-execute it cleanly at load time.

# COMMAND ----------

# MAGIC %%writefile agent.py
# MAGIC # agent.py — the entire Unity Airways support agent, self-contained (no notebook globals).
# MAGIC # Loading this model RE-EXECUTES this file, rebuilding fresh tool clients + LLM client. Nothing pickles.
# MAGIC from typing import Annotated, Any, Generator, TypedDict
# MAGIC import uuid
# MAGIC
# MAGIC import mlflow
# MAGIC from databricks_langchain import ChatDatabricks, VectorSearchRetrieverTool, UCFunctionToolkit
# MAGIC from unitycatalog.ai.core.databricks import DatabricksFunctionClient
# MAGIC from langgraph.graph import StateGraph, START, END
# MAGIC from langgraph.graph.message import add_messages
# MAGIC from langgraph.prebuilt import ToolNode
# MAGIC from mlflow.pyfunc import ResponsesAgent
# MAGIC from mlflow.types.responses import (
# MAGIC     ResponsesAgentRequest, ResponsesAgentResponse, ResponsesAgentStreamEvent,
# MAGIC )
# MAGIC
# MAGIC mlflow.langchain.autolog()   # loaded/served copies keep emitting traces for every step + tool call
# MAGIC
# MAGIC # Canonical Unity Airways names (in prod: read these via mlflow.models.ModelConfig).
# MAGIC LLM_ENDPOINT = "databricks-claude-sonnet-4-5"
# MAGIC INDEX_NAME   = "unity_airways.rag.ua_rag_chunks_index"
# MAGIC UC_FUNCTION  = "unity_airways.rag.get_flight_status"
# MAGIC
# MAGIC SYSTEM_PROMPT = (
# MAGIC     "You are the Unity Airways support assistant. Use the retriever tool for policy/FAQ questions "
# MAGIC     "and the get_flight_status tool for live flight status. Answer only from tool results; cite the "
# MAGIC     "source when you use policy text. If you don't have enough information, say so."
# MAGIC )
# MAGIC
# MAGIC # ---- Tools from 09.3 (identical to 09-3-create-tools.py) --------------------------------------------
# MAGIC # NOTE: verify vs current docs — VectorSearchRetrieverTool signature is from Book 1 Ch7 (Early Release);
# MAGIC # the retriever-tool doc page is JS-rendered. Confirm current kwargs before asserting to a customer.
# MAGIC retriever_tool = VectorSearchRetrieverTool(
# MAGIC     index_name=INDEX_NAME,
# MAGIC     num_results=5,
# MAGIC     tool_description=("Search Unity Airways policy and FAQ documents about flight cancellations, "
# MAGIC                       "refunds, baggage rules, and travel policies."),
# MAGIC )
# MAGIC client = DatabricksFunctionClient()
# MAGIC uc_toolkit = UCFunctionToolkit(function_names=[UC_FUNCTION], client=client)
# MAGIC
# MAGIC tools = [retriever_tool, *uc_toolkit.tools]   # the SAME tool list you assembled in 09.3
# MAGIC
# MAGIC # ---- LangGraph tool-calling loop (09.5) ------------------------------------------------------------
# MAGIC llm = ChatDatabricks(endpoint=LLM_ENDPOINT)
# MAGIC llm_with_tools = llm.bind_tools(tools)
# MAGIC
# MAGIC class AgentState(TypedDict):
# MAGIC     messages: Annotated[list, add_messages]
# MAGIC
# MAGIC def call_model(state: AgentState):
# MAGIC     return {"messages": [llm_with_tools.invoke(state["messages"])]}
# MAGIC
# MAGIC def should_continue(state: AgentState):
# MAGIC     last = state["messages"][-1]
# MAGIC     # if the LLM asked for a tool, route to the tool node; otherwise the answer is ready
# MAGIC     return "tools" if getattr(last, "tool_calls", None) else END
# MAGIC
# MAGIC builder = StateGraph(AgentState)
# MAGIC builder.add_node("agent", call_model)
# MAGIC builder.add_node("tools", ToolNode(tools))
# MAGIC builder.add_edge(START, "agent")
# MAGIC builder.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
# MAGIC builder.add_edge("tools", "agent")
# MAGIC graph = builder.compile()
# MAGIC
# MAGIC # ---- ResponsesAgent wrapper (09.6) ----------------------------------------------------------------
# MAGIC class UASupportAgent(ResponsesAgent):
# MAGIC     """Wrap the LangGraph agent in MLflow's recommended authoring interface.
# MAGIC     Only predict / predict_stream are yours to implement; the base class supplies helpers + schema."""
# MAGIC
# MAGIC     def __init__(self, graph):
# MAGIC         self.graph = graph
# MAGIC
# MAGIC     def _responses_to_langchain(self, request: ResponsesAgentRequest):
# MAGIC         # NOTE: verify vs current docs — this is the _responses_to_cc()/_langchain_to_responses() style
# MAGIC         # helper you write to map Responses input items <-> your framework's messages.
# MAGIC         messages = [("system", SYSTEM_PROMPT)]
# MAGIC         for item in request.input:
# MAGIC             item = item if isinstance(item, dict) else item.model_dump()
# MAGIC             messages.append((item.get("role", "user"), item.get("content", "")))
# MAGIC         return messages
# MAGIC
# MAGIC     def predict(self, request: ResponsesAgentRequest) -> ResponsesAgentResponse:
# MAGIC         # collect the completed items produced by the streaming path (the 09.6 pattern)
# MAGIC         outputs = [event.item for event in self.predict_stream(request)
# MAGIC                    if event.type == "response.output_item.done"]
# MAGIC         return ResponsesAgentResponse(output=outputs, custom_outputs=request.custom_inputs)
# MAGIC
# MAGIC     def predict_stream(
# MAGIC         self, request: ResponsesAgentRequest
# MAGIC     ) -> Generator[ResponsesAgentStreamEvent, None, None]:
# MAGIC         # Run the LangGraph loop, then emit the final message as a completed output item.
# MAGIC         # A token-streaming impl would iterate graph.stream(...) and yield create_text_delta(...) events.
# MAGIC         result = self.graph.invoke({"messages": self._responses_to_langchain(request)})
# MAGIC         final_text = result["messages"][-1].content
# MAGIC         item = self.create_text_output_item(text=final_text, id=str(uuid.uuid4()))
# MAGIC         yield ResponsesAgentStreamEvent(type="response.output_item.done", item=item)
# MAGIC
# MAGIC AGENT = UASupportAgent(graph)
# MAGIC mlflow.models.set_model(AGENT)   # <-- last line: this object is the model MLflow logs

# COMMAND ----------

# MAGIC %md
# MAGIC ### Smoke-test the wrapped agent in the notebook (before logging)
# MAGIC Import and call it. This runs `agent.py` exactly the way MLflow will at load time, so an import or config
# MAGIC error shows up here while it is cheap to fix. You should get a coherent answer, and the MLflow trace
# MAGIC should show the retriever and (if relevant) the UC-function tool calls.

# COMMAND ----------

import sys, os
sys.path.insert(0, os.getcwd())   # make the freshly written agent.py importable

from agent import AGENT
from mlflow.types.responses import ResponsesAgentRequest

req = ResponsesAgentRequest(
    input=[{"role": "user", "content": "Can my battery pack go in cabin baggage?"}])
result = AGENT.predict(req)
print(result.output[-1])

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Log as Model-as-Code with resources
# MAGIC `python_model=` is the **path to the file**, not the object. Declare the Databricks services the agent
# MAGIC calls in `resources=[...]` so deployment mints scoped, short-lived credentials automatically — the
# MAGIC "automatic authentication passthrough". Here that is three services: the **LLM endpoint**, the
# MAGIC **retriever index**, and the **UC function**. Omit one and the model logs fine but **401s at inference**.

# COMMAND ----------

import mlflow
from mlflow.models.resources import (
    DatabricksServingEndpoint, DatabricksVectorSearchIndex, DatabricksFunction,
)

with mlflow.start_run():
    logged_agent = mlflow.pyfunc.log_model(
        python_model="agent.py",          # Model-as-Code: log the code, not the object
        name="agent",
        resources=[
            DatabricksServingEndpoint(endpoint_name=LLM_ENDPOINT),        # the LLM
            DatabricksVectorSearchIndex(index_name=INDEX_NAME),          # the retriever index
            DatabricksFunction(function_name=UC_FUNCTION),               # the UC function tool
        ],
        pip_requirements=[
            "mlflow>=3.1", "databricks-langchain", "langgraph",
            "databricks-vectorsearch", "unitycatalog-ai",
        ],
    )

print("model_uri:", logged_agent.model_uri)   # MLflow 3 -> models:/<model_id>

# COMMAND ----------

# MAGIC %md
# MAGIC ### How to verify it worked
# MAGIC `logged_agent.model_uri` prints, and the run shows an `agent` model artifact with a
# MAGIC `pyfunc` / `ResponsesAgent` flavor in the MLflow UI.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Pre-deployment check — load + predict in a clean environment
# MAGIC `mlflow.models.predict(...)` rebuilds the environment from the logged artifacts (here with `uv`), loads
# MAGIC the model, and calls it. If a dependency or resource is missing, you find out **now**, not after deploy.

# COMMAND ----------

mlflow.models.predict(
    model_uri=f"runs:/{logged_agent.run_id}/agent",
    input_data={"input": [{"role": "user", "content": "Is flight UA123 on 2026-07-20 on time?"}]},
    env_manager="uv",
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Register to Unity Catalog (creates version 1)
# MAGIC Point the registry at UC, then register the logged agent under the three-level name so it is governed,
# MAGIC versioned, and deployable — exactly like the RAG chain in 06.5.

# COMMAND ----------

mlflow.set_registry_uri("databricks-uc")
registered = mlflow.register_model(model_uri=logged_agent.model_uri, name=UC_MODEL)
print(registered.name, registered.version)   # unity_airways.rag.ua_support_agent 1

# COMMAND ----------

# MAGIC %md
# MAGIC ### How to verify it worked
# MAGIC The model appears in Catalog Explorer under `unity_airways.rag` → Models with a version number.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Hand off to deployment (forward reference — not run here)
# MAGIC Deployment is **not** part of this topic. Two surfaces read the registered version:
# MAGIC - **Agent Framework deploy (Module 11):** `agents.deploy(...)` stands up a Model Serving endpoint + a
# MAGIC   Review App + a feedback model, and turns on tracing, inference tables, and monitoring.
# MAGIC - **Databricks Apps (Module 10.5):** package the agent behind an app for a custom UI.

# COMMAND ----------

# Module 11 — Agent Framework deploy (reference only; do not run in this packaging notebook):
# from databricks import agents
# agents.deploy(UC_MODEL, registered.version)
#
# Or go low-code with Agent Bricks (Module 10) / package behind a Databricks App (Module 10.5).
print("Registered agent ready for deployment:", UC_MODEL, "version", registered.version)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6. Recap, gotchas and next step
# MAGIC **What you built**
# MAGIC - `agent.py` — the 09.3 tools + a LangGraph loop wrapped in a **`UASupportAgent(ResponsesAgent)`**,
# MAGIC   ending in `mlflow.models.set_model(AGENT)`.
# MAGIC - A **Models-from-Code** log (`python_model="agent.py"`) with **`resources=[...]`** for the LLM endpoint,
# MAGIC   the index, and the UC function — the auto-auth list.
# MAGIC - A **pre-deploy check** (`mlflow.models.predict`, `env_manager="uv"`) and **UC registration** as
# MAGIC   `unity_airways.rag.ua_support_agent`.
# MAGIC
# MAGIC **Gotchas to remember**
# MAGIC - Author on **`ResponsesAgent`** — not `ChatAgent` (superseded) or `ChatModel` (legacy). The deprecated
# MAGIC   `SplitChatMessagesRequest` / `StringResponse` helpers are out; use `ResponsesAgentRequest` / `Response`.
# MAGIC - Pass the **file path** to `log_model`, not the agent object — live tool clients don't pickle, and the
# MAGIC   serving stack needs the Responses I/O contract.
# MAGIC - Every service the agent reaches at run time must appear in `resources=[...]`, or the deployed agent
# MAGIC   **401s** when it calls it.
# MAGIC - Register with `mlflow.set_registry_uri("databricks-uc")` and a three-level `catalog.schema.model` name.
# MAGIC
# MAGIC **Next:** the consolidated `09-module-lab.py` walks the full module — 09.3 tools → 09.5 LangGraph loop →
# MAGIC this 09.6 packaging → 09.10 tool testing → 09.8/09.11 **managed MCP**. Then **Module 10** (Agent Bricks,
# MAGIC low-code) and **Module 11** (deploy with `agents.deploy`).
