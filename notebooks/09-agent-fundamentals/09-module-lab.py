# Databricks notebook source
# MAGIC %md
# MAGIC # Module 09 lab — Build the Unity Airways support agent end to end
# MAGIC **Roadmap:** Module 09 (Agent fundamentals and tools) · Topics 09.3–09.11 · ★ 09.3 / 09.6 cornerstones · [Hands-on]
# MAGIC
# MAGIC One runnable lab that turns the Module 05 RAG chain into a **governed, registered agent**. You build the
# MAGIC three 09.3 tools, test each in isolation (09.10), wire a LangGraph tool-calling loop (09.5), wrap it in a
# MAGIC **`ResponsesAgent`** and register it to Unity Catalog (09.6), then swap a hand-wrapped tool for a
# MAGIC **managed MCP** server (09.8 / 09.11).
# MAGIC
# MAGIC | Step | Topic | What you do |
# MAGIC |---|---|---|
# MAGIC | 1 | **09.3** ★ | Build three tools — retriever + UC function (`get_flight_status`) + API `StructuredTool` |
# MAGIC | 2 | **09.10** | Test each tool in isolation — **before** packaging |
# MAGIC | 3 | **09.5** | A LangGraph tool-calling agent — `bind_tools` + `ToolNode` + `should_continue` |
# MAGIC | 4 | **09.6** ★ | Wrap in `ResponsesAgent`, log Model-as-Code with `resources`, register to UC |
# MAGIC | 5 | **09.8 / 09.11** | Managed **MCP** server (`DatabricksMCPClient`) as a governed, reusable tool source |
# MAGIC
# MAGIC Focused cornerstone notebooks: `09-3-create-tools.py` (09.3) and `09-6-responsesagent.py` (09.6). This lab
# MAGIC layers the full module around them. The retriever index is from **Modules 04–05**; packaging reuses the
# MAGIC Model-as-Code pattern from **05.6** and UC registration from **06.5**.
# MAGIC
# MAGIC ## Prerequisites (read before running)
# MAGIC - **Compute:** **serverless notebook/job**, or a **DBR ML runtime** (15.4 LTS ML or later).
# MAGIC - **MLflow:** **>= 3.1** (Models-from-Code, `ResponsesAgent`, `resources`, MLflow 3 logging + UC registry).
# MAGIC - **AI Search index (Modules 04–05):** `unity_airways.rag.ua_rag_chunks_index` ONLINE on **`unity-airways-vs`**.
# MAGIC - **Unity Catalog rights on `unity_airways.rag`:** `USE CATALOG` + `USE SCHEMA`, **`CREATE FUNCTION`** +
# MAGIC   **`EXECUTE`** (for `get_flight_status`), and **`CREATE MODEL`** (to register the agent).
# MAGIC - **Chat serving endpoint:** **`databricks-claude-sonnet-4-5`** — confirm on the supported-models page.
# MAGIC - **Secrets:** none — the weather API is keyless; declared `resources=[...]` drive auth passthrough on deploy.
# MAGIC - **Learner-set identifiers:** edit the constants in Step 0.
# MAGIC
# MAGIC > 📌 **The one rule of the module:** author on **`ResponsesAgent`** (recommended) — not `ChatAgent`
# MAGIC > (superseded) or `ChatModel` (legacy). Tools import from **`databricks-langchain`**; log **Model-as-Code**
# MAGIC > with `set_model`; register three-level `catalog.schema.model`; **managed MCP is Public Preview**.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 0. Install libraries and set variables

# COMMAND ----------

# MAGIC %pip install -U "mlflow>=3.1" databricks-langchain databricks-vectorsearch unitycatalog-ai langchain langgraph databricks-mcp requests
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

CATALOG      = "unity_airways"
SCHEMA       = "rag"
INDEX_NAME   = f"{CATALOG}.{SCHEMA}.ua_rag_chunks_index"     # Modules 04/05 (retriever tool)
UC_FUNCTION  = f"{CATALOG}.{SCHEMA}.get_flight_status"       # this lab creates it (09.3)
UC_MODEL     = f"{CATALOG}.{SCHEMA}.ua_support_agent"        # where we register the agent (09.6)
LLM_ENDPOINT = "databricks-claude-sonnet-4-5"              # confirm on the supported-models page

import mlflow
mlflow.langchain.autolog()   # trace every tool call + agent step

print("Index        :", INDEX_NAME)
print("UC function  :", UC_FUNCTION)
print("UC model     :", UC_MODEL)
print("LLM endpoint :", LLM_ENDPOINT)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 1 — Build the three tools (09.3)
# MAGIC Match the tool type to where the answer lives: **documents → retriever**, **a table → UC function**,
# MAGIC **an outside system → API tool**. The `tool_description` and SQL `COMMENT`s are the interface the LLM reads.

# COMMAND ----------

# --- Tool 1: retriever over the Module 04/05 AI Search index ---
from databricks_langchain import VectorSearchRetrieverTool

# NOTE: verify vs current docs — VectorSearchRetrieverTool signature is from Book 1 Ch7 (Early Release) and
# the retriever-tool doc page is JS-rendered; confirm current kwargs before asserting to a customer.
retriever_tool = VectorSearchRetrieverTool(
    index_name=INDEX_NAME,
    num_results=5,
    tool_description=("Search Unity Airways policy and FAQ documents about flight cancellations, "
                      "refunds, baggage rules, and travel policies."),
)

# COMMAND ----------

# MAGIC %sql
# MAGIC -- Tool 2: a governed Unity Catalog function. The COMMENTs become the tool description.
# MAGIC CREATE OR REPLACE FUNCTION unity_airways.rag.get_flight_status(
# MAGIC   in_flight_number STRING COMMENT 'IATA flight code, e.g. UA123',
# MAGIC   in_flight_date   STRING COMMENT 'Scheduled departure date, YYYY-MM-DD (UTC)'
# MAGIC )
# MAGIC RETURNS TABLE
# MAGIC COMMENT 'Return the live status, gate, and times for one Unity Airways flight on a date. Use for "is flight X on time / delayed / cancelled" questions.'
# MAGIC RETURN (
# MAGIC   SELECT flight_number, status, departure_gate,
# MAGIC          scheduled_departure, estimated_departure
# MAGIC   FROM   unity_airways.rag.flight_status_records   -- illustrative ops table
# MAGIC   WHERE  flight_number = in_flight_number
# MAGIC     AND  flight_date   = in_flight_date
# MAGIC );

# COMMAND ----------

# MAGIC %sql
# MAGIC -- Seed the ops table get_flight_status reads (illustrative; 09-3 and 09-6 reuse this same table).
# MAGIC -- Columns match the function's SELECT + WHERE. Must exist before any tool invocation below.
# MAGIC CREATE TABLE IF NOT EXISTS unity_airways.rag.flight_status_records (
# MAGIC   flight_number       STRING,
# MAGIC   flight_date         STRING,
# MAGIC   status              STRING,
# MAGIC   departure_gate      STRING,
# MAGIC   scheduled_departure STRING,
# MAGIC   estimated_departure STRING
# MAGIC );
# MAGIC
# MAGIC INSERT OVERWRITE unity_airways.rag.flight_status_records VALUES
# MAGIC   ('UA123', '2026-07-20', 'Delayed',   'B22', '2026-07-20T14:30:00Z', '2026-07-20T16:10:00Z'),
# MAGIC   ('UA456', '2026-07-20', 'On Time',   'C15', '2026-07-20T09:00:00Z', '2026-07-20T09:00:00Z'),
# MAGIC   ('UA789', '2026-07-20', 'Cancelled', 'A3',  '2026-07-20T18:45:00Z', NULL);

# COMMAND ----------

# Wrap the UC function as a tool. UCFunctionToolkit.tools is a LIST — one tool per function name.
from databricks_langchain import UCFunctionToolkit
from unitycatalog.ai.core.databricks import DatabricksFunctionClient

client = DatabricksFunctionClient()
uc_toolkit = UCFunctionToolkit(function_names=[UC_FUNCTION], client=client)
# Built-in code interpreter, added the same way when the agent must COMPUTE rather than look up:
#   UCFunctionToolkit(function_names=["system.ai.python_exec"], client=client)

# COMMAND ----------

# --- Tool 3: an API-calling tool — Pydantic schema + error-handled function + StructuredTool ---
from pydantic import BaseModel, Field
from langchain_core.tools import StructuredTool
import requests
from typing import Any

class AirportWeatherInput(BaseModel):
    latitude: float = Field(description="Airport latitude in decimal degrees")
    longitude: float = Field(description="Airport longitude in decimal degrees")

def get_airport_weather(latitude: float, longitude: float) -> dict[str, Any]:
    """Fetch the short-term weather forecast for an airport location."""
    try:
        resp = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={"latitude": latitude, "longitude": longitude,
                    "hourly": "temperature_2m,rain,precipitation_probability"},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()["hourly"]
    except Exception as e:
        return {"error": f"weather lookup failed: {e}"}   # readable error, not a crash

weather_tool = StructuredTool(
    name="get_airport_weather",
    func=get_airport_weather,
    description="Get the hourly weather forecast for an airport by latitude/longitude. "
                "Use to check whether weather may delay a flight.",
    args_schema=AirportWeatherInput,
)

# COMMAND ----------

# Assemble the one tool list — the exact list you package in 09.6.
tools = [retriever_tool, *uc_toolkit.tools, weather_tool]
print(f"{len(tools)} tools assembled:", [t.name for t in tools])

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 2 — Test each tool in isolation (09.10), before packaging
# MAGIC Test the **tool layer** and the **orchestration layer** separately. A tool can be perfect while the agent
# MAGIC still calls it at the wrong time. Confirm each tool returns something sensible on its own first.

# COMMAND ----------

checks = {
    "retriever (policy search)": lambda: retriever_tool.invoke(
        {"query": "Can my battery pack go in cabin baggage?"}),
    "get_flight_status (UC fn)": lambda: uc_toolkit.tools[0].invoke(
        {"in_flight_number": "UA123", "in_flight_date": "2026-07-20"}),
    "get_airport_weather (API)": lambda: weather_tool.invoke(
        {"latitude": 1.3667, "longitude": 103.8}),
}
for name, run in checks.items():
    try:
        out = str(run())[:120].replace("\n", " ")
        print(f"[OK]   {name}: {out}...")
    except Exception as e:
        print(f"[FAIL] {name}: {e}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 3 — A LangGraph tool-calling agent (09.5)
# MAGIC Bind the tools to the LLM, then build a small **planning-agent** loop: an `agent` node calls the LLM,
# MAGIC `should_continue` routes to the `ToolNode` when the LLM asked for a tool, and the tool result loops back
# MAGIC to the LLM until it can answer. This is dynamic flow (chosen at runtime), not a fixed order.

# COMMAND ----------

from typing import Annotated, TypedDict
from databricks_langchain import ChatDatabricks
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

SYSTEM_PROMPT = (
    "You are the Unity Airways support assistant. Use the retriever tool for policy/FAQ questions, "
    "get_flight_status for live flight status, and get_airport_weather for weather. Answer only from "
    "tool results and cite policy sources. Cap yourself to the tools you actually need.")

llm = ChatDatabricks(endpoint=LLM_ENDPOINT)
llm_with_tools = llm.bind_tools(tools)

class AgentState(TypedDict):
    messages: Annotated[list, add_messages]

def call_model(state: AgentState):
    return {"messages": [llm_with_tools.invoke(state["messages"])]}

def should_continue(state: AgentState):
    last = state["messages"][-1]
    return "tools" if getattr(last, "tool_calls", None) else END

builder = StateGraph(AgentState)
builder.add_node("agent", call_model)
builder.add_node("tools", ToolNode(tools))
builder.add_edge(START, "agent")
builder.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
builder.add_edge("tools", "agent")
graph = builder.compile()

# COMMAND ----------

# MAGIC %md
# MAGIC ### How to verify it worked
# MAGIC Ask a mixed question. The loop should call `get_flight_status` (status) and the retriever (refund policy),
# MAGIC then compose one grounded answer. The MLflow trace shows each hop.

# COMMAND ----------

out = graph.invoke({"messages": [
    ("system", SYSTEM_PROMPT),
    ("user", "Is flight UA123 on 2026-07-20 delayed, and can I get a refund if it is?"),
]})
print(out["messages"][-1].content)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 4 — Wrap in ResponsesAgent, log + register (09.6)
# MAGIC Materialize the whole agent into `agent.py` (Models-from-Code), ending in `mlflow.models.set_model(AGENT)`.
# MAGIC This is the same file `09-6-responsesagent.py` builds — self-contained, no notebook globals.

# COMMAND ----------

# MAGIC %%writefile agent.py
# MAGIC # agent.py — the Unity Airways support agent, self-contained. Loading re-executes this file; nothing pickles.
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
# MAGIC mlflow.langchain.autolog()
# MAGIC
# MAGIC LLM_ENDPOINT = "databricks-claude-sonnet-4-5"
# MAGIC INDEX_NAME   = "unity_airways.rag.ua_rag_chunks_index"
# MAGIC UC_FUNCTION  = "unity_airways.rag.get_flight_status"
# MAGIC SYSTEM_PROMPT = (
# MAGIC     "You are the Unity Airways support assistant. Use the retriever tool for policy/FAQ questions and "
# MAGIC     "get_flight_status for live flight status. Answer only from tool results; cite policy sources.")
# MAGIC
# MAGIC # Tools from 09.3 (identical to 09-3-create-tools.py)
# MAGIC retriever_tool = VectorSearchRetrieverTool(
# MAGIC     index_name=INDEX_NAME, num_results=5,
# MAGIC     tool_description=("Search Unity Airways policy and FAQ documents about flight cancellations, "
# MAGIC                       "refunds, baggage rules, and travel policies."))
# MAGIC client = DatabricksFunctionClient()
# MAGIC uc_toolkit = UCFunctionToolkit(function_names=[UC_FUNCTION], client=client)
# MAGIC tools = [retriever_tool, *uc_toolkit.tools]
# MAGIC
# MAGIC # LangGraph tool-calling loop (09.5)
# MAGIC llm_with_tools = ChatDatabricks(endpoint=LLM_ENDPOINT).bind_tools(tools)
# MAGIC
# MAGIC class AgentState(TypedDict):
# MAGIC     messages: Annotated[list, add_messages]
# MAGIC
# MAGIC def call_model(state: AgentState):
# MAGIC     return {"messages": [llm_with_tools.invoke(state["messages"])]}
# MAGIC
# MAGIC def should_continue(state: AgentState):
# MAGIC     last = state["messages"][-1]
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
# MAGIC # ResponsesAgent wrapper (09.6) — only predict / predict_stream are yours to implement.
# MAGIC class UASupportAgent(ResponsesAgent):
# MAGIC     def __init__(self, graph):
# MAGIC         self.graph = graph
# MAGIC
# MAGIC     def _responses_to_langchain(self, request: ResponsesAgentRequest):
# MAGIC         # NOTE: verify vs current docs — helper you write to map Responses items <-> framework messages.
# MAGIC         messages = [("system", SYSTEM_PROMPT)]
# MAGIC         for item in request.input:
# MAGIC             item = item if isinstance(item, dict) else item.model_dump()
# MAGIC             messages.append((item.get("role", "user"), item.get("content", "")))
# MAGIC         return messages
# MAGIC
# MAGIC     def predict(self, request: ResponsesAgentRequest) -> ResponsesAgentResponse:
# MAGIC         outputs = [e.item for e in self.predict_stream(request)
# MAGIC                    if e.type == "response.output_item.done"]
# MAGIC         return ResponsesAgentResponse(output=outputs, custom_outputs=request.custom_inputs)
# MAGIC
# MAGIC     def predict_stream(
# MAGIC         self, request: ResponsesAgentRequest
# MAGIC     ) -> Generator[ResponsesAgentStreamEvent, None, None]:
# MAGIC         result = self.graph.invoke({"messages": self._responses_to_langchain(request)})
# MAGIC         final_text = result["messages"][-1].content
# MAGIC         item = self.create_text_output_item(text=final_text, id=str(uuid.uuid4()))
# MAGIC         yield ResponsesAgentStreamEvent(type="response.output_item.done", item=item)
# MAGIC
# MAGIC AGENT = UASupportAgent(graph)
# MAGIC mlflow.models.set_model(AGENT)   # <-- last line: this object is the model

# COMMAND ----------

# Smoke-test agent.py the way MLflow will load it, before logging.
import sys, os
sys.path.insert(0, os.getcwd())
from agent import AGENT
from mlflow.types.responses import ResponsesAgentRequest

result = AGENT.predict(ResponsesAgentRequest(
    input=[{"role": "user", "content": "Can my battery pack go in cabin baggage?"}]))
print(result.output[-1])

# COMMAND ----------

# Log Model-as-Code with resources for auth passthrough, then pre-deploy check, then register to UC.
from mlflow.models.resources import (
    DatabricksServingEndpoint, DatabricksVectorSearchIndex, DatabricksFunction,
)

with mlflow.start_run():
    logged_agent = mlflow.pyfunc.log_model(
        python_model="agent.py",          # log the code, not the object
        name="agent",
        resources=[
            DatabricksServingEndpoint(endpoint_name=LLM_ENDPOINT),     # the LLM
            DatabricksVectorSearchIndex(index_name=INDEX_NAME),       # the retriever index
            DatabricksFunction(function_name=UC_FUNCTION),            # the UC function tool
        ],
        pip_requirements=[
            "mlflow", "databricks-langchain", "langgraph",
            "databricks-vectorsearch", "unitycatalog-ai",
        ],
    )
print("model_uri:", logged_agent.model_uri)

# COMMAND ----------

# Pre-deployment check — rebuild env, load, and predict (catches missing deps/resources now, not post-deploy).
mlflow.models.predict(
    model_uri=f"runs:/{logged_agent.run_id}/agent",
    input_data={"input": [{"role": "user", "content": "Is flight UA123 on 2026-07-20 on time?"}]},
    env_manager="uv",
)

# COMMAND ----------

# Register to Unity Catalog (three-level name → governed, versioned, deployable).
mlflow.set_registry_uri("databricks-uc")
registered = mlflow.register_model(model_uri=logged_agent.model_uri, name=UC_MODEL)
print(registered.name, registered.version)   # unity_airways.rag.ua_support_agent 1

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 5 — Managed MCP server as a tool (09.8 / 09.11)
# MAGIC **Model Context Protocol (MCP)** is an open standard (Anthropic, 2024) for exposing tools to any agent.
# MAGIC Databricks hosts **managed MCP servers** — UC-governed, authenticated by default — for Vector Search, UC
# MAGIC functions, Genie, and Databricks SQL, so you get a standardized, reusable tool source without running a
# MAGIC server. The URL points at a UC namespace; the same grants that protect the index/function protect the tool.
# MAGIC
# MAGIC > ⚠️ **GOTCHA:** managed MCP on Databricks is **Public Preview** (some surfaces GA). Label it as such in
# MAGIC > customer material and verify the exact server URLs + enrollment on current docs before committing them.

# COMMAND ----------

# NOTE: verify vs current docs — managed-MCP URL pattern + DatabricksMCPClient are from Book 1 Ch7 (Early
# Release); the managed-MCP doc page is JS-rendered. Confirm the URL and that the catalog/schema hosts your
# index before promising it. This is Public Preview.
from databricks.sdk import WorkspaceClient

ws = WorkspaceClient()
host = ws.config.host
# Managed MCP server for the AI Search indexes in this catalog.schema:
MANAGED_MCP_SERVER_URL = f"{host}/api/2.0/mcp/vector-search/{CATALOG}/{SCHEMA}"
print("Managed MCP server URL:", MANAGED_MCP_SERVER_URL)

from databricks_mcp import DatabricksMCPClient

mcp_client = DatabricksMCPClient(server_url=MANAGED_MCP_SERVER_URL, workspace_client=ws)
mcp_tools = mcp_client.list_tools()   # discover the tools this managed server exposes
print("MCP tools discovered:", [t.name for t in mcp_tools])

# Wrap a discovered MCP tool (09.8 pattern) and add it to `tools` exactly like any other tool — the retriever
# tool above could be replaced by the Vector Search managed-MCP tool once you standardize on MCP.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Recap, gotchas and next step
# MAGIC **What you built**
# MAGIC - Three **09.3** tools (retriever + UC function + API `StructuredTool`), each **tested in isolation (09.10)**.
# MAGIC - A **LangGraph tool-calling agent (09.5)** — `bind_tools` + `ToolNode` + `should_continue`.
# MAGIC - The agent wrapped in **`ResponsesAgent`**, logged **Model-as-Code** with `resources=[...]`, pre-deploy
# MAGIC   checked, and **registered to `unity_airways.rag.ua_support_agent` (09.6)**.
# MAGIC - A **managed MCP** server (09.8 / 09.11) discovered as a governed, reusable tool source (**Public Preview**).
# MAGIC
# MAGIC **Gotchas to remember**
# MAGIC - Author on **`ResponsesAgent`**, not `ChatAgent` / `ChatModel`. Tools import from **`databricks-langchain`**.
# MAGIC - Test the tool layer and the orchestration layer **separately** — a right tool called at the wrong time
# MAGIC   still fails the user.
# MAGIC - Declare every service the agent reaches in `resources=[...]`, or the deployed agent 401s.
# MAGIC - Register with `set_registry_uri("databricks-uc")` and a three-level `catalog.schema.model`.
# MAGIC - Managed MCP is **Public Preview** — verify URLs + enrollment before committing to a customer timeline.
# MAGIC
# MAGIC **Next:** the agent `unity_airways.rag.ua_support_agent` is registered and ready. **Deploy it in Module 11**
# MAGIC (`agents.deploy(...)` → Serving endpoint + Review App + feedback model + monitoring), or **go low-code with
# MAGIC Agent Bricks in Module 10** (Knowledge Assistant, Multi-Agent Supervisor) / a Databricks App (Module 10.5).
