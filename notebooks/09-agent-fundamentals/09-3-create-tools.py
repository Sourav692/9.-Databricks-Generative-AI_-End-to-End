# Databricks notebook source
# MAGIC %md
# MAGIC # 09.3 ★ — Creating agent tools: retriever, structured-data lookup, API-calling
# MAGIC **Roadmap:** Module 09 (Agent fundamentals and tools) · Topic 09.3 (cornerstone) · [Hands-on] (+ [Theory])
# MAGIC
# MAGIC ## The problem
# MAGIC The Module 05 RAG chain can answer *"what is the baggage policy?"* from the policy docs. A real Unity
# MAGIC Airways passenger asks harder things: *"Is flight UA123 on the 20th delayed?"* (a row in an ops table),
# MAGIC *"will weather delay my flight out of Singapore?"* (a live external API), *"am I owed a refund?"* (docs
# MAGIC **and** a record). A single retrieval step cannot do this. The LLM needs to **decide**, per question,
# MAGIC whether to search docs, query a table, or call an API — and it can only do that if you hand it those
# MAGIC capabilities as **tools**.
# MAGIC
# MAGIC ## What you will build
# MAGIC The three tool types that cover almost every agent, for the Unity Airways support agent:
# MAGIC 1. **Retriever tool** — `VectorSearchRetrieverTool` over the Module 04/05 AI Search index.
# MAGIC 2. **Structured-data lookup tool** — a **Unity Catalog function** `get_flight_status`, wrapped by
# MAGIC    `UCFunctionToolkit` (plus a note on the built-in `system.ai.python_exec`).
# MAGIC 3. **API-calling tool** — a plain Python function wrapped as a LangChain `StructuredTool` with a
# MAGIC    Pydantic input schema.
# MAGIC
# MAGIC Then you **test each tool in isolation** (09.10) and `bind_tools(...)` the list to the LLM. This exact
# MAGIC `tools` list is what you package into a `ResponsesAgent` in 09.6 (`09-6-responsesagent.py`).
# MAGIC
# MAGIC ### Prerequisites (read before running)
# MAGIC - **Compute:** **serverless notebook/job**, or a **DBR ML runtime** (15.4 LTS ML or later).
# MAGIC - **MLflow:** **>= 3.1** (for automatic tracing of each tool call).
# MAGIC - **AI Search index (Modules 04–05):** `unity_airways.rag.ua_rag_chunks_index` ONLINE on endpoint
# MAGIC   **`unity-airways-vs`** — the retriever tool wraps it.
# MAGIC - **Unity Catalog rights on `unity_airways.rag`:** `USE CATALOG` + `USE SCHEMA`, plus **`CREATE FUNCTION`**
# MAGIC   and **`EXECUTE`** to create and test `get_flight_status`.
# MAGIC - **Chat serving endpoint:** **`databricks-claude-sonnet-4-5`** — confirm on the supported-models page.
# MAGIC - **Secrets:** none for these tools (the weather API is keyless). A real partner API would keep its key
# MAGIC   in a Databricks secret scope (see 09.4).
# MAGIC - **Learner-set identifiers:** edit the constants in Step 0.
# MAGIC
# MAGIC > 📌 **The one rule of this topic:** a tool is only as good as its **name + description + input schema** —
# MAGIC > that trio is the entire interface the LLM sees. Match the **tool type to where the answer lives**:
# MAGIC > documents → retriever tool, a table → UC function, an outside system → API tool.
# MAGIC >
# MAGIC > ⚠️ **Naming trap:** the LangChain integration package is **`databricks-langchain`**
# MAGIC > (`from databricks_langchain import ...`), *not* `langchain-databricks`. The Vector Search SDK is still
# MAGIC > **`databricks-vectorsearch`** despite the "AI Search" rebrand.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 0. Install libraries and set variables
# MAGIC `databricks-langchain` (`VectorSearchRetrieverTool`, `UCFunctionToolkit`, `ChatDatabricks`),
# MAGIC `databricks-vectorsearch` (the index client), `unitycatalog-ai` (`DatabricksFunctionClient`),
# MAGIC `langchain` (`StructuredTool`), `requests` (the API tool), and `mlflow` (>= 3.1, tracing).

# COMMAND ----------

# MAGIC %pip install -U "mlflow>=3.1" databricks-langchain databricks-vectorsearch unitycatalog-ai langchain requests
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

CATALOG      = "unity_airways"
SCHEMA       = "rag"
INDEX_NAME   = f"{CATALOG}.{SCHEMA}.ua_rag_chunks_index"     # the Module 04/05 AI Search index
UC_FUNCTION  = f"{CATALOG}.{SCHEMA}.get_flight_status"       # the structured-lookup tool we create below
LLM_ENDPOINT = "databricks-claude-sonnet-4-5"               # confirm on the supported-models page

print("Index        :", INDEX_NAME)
print("UC function  :", UC_FUNCTION)
print("LLM endpoint :", LLM_ENDPOINT)

# COMMAND ----------

# Turn on automatic tracing so every tool call below shows up as a span in the MLflow Trace UI.
import mlflow
mlflow.langchain.autolog()

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Tool 1 — the retriever tool
# MAGIC You already built and queried this AI Search index in Modules 04–05. Instead of calling it directly in
# MAGIC a fixed chain, wrap it as a tool the agent calls *when it decides retrieval is needed*. The
# MAGIC `tool_description` is what the LLM reads to decide whether *this* tool answers the question — say what it
# MAGIC covers, when to call it, and the keywords a user might use, and don't let it overlap with your other tools.

# COMMAND ----------

from databricks_langchain import VectorSearchRetrieverTool

# NOTE: verify vs current docs — VectorSearchRetrieverTool class + kwargs are from Book 1 Ch7 (O'Reilly
# Early Release) and the retriever-tool doc page is JS-rendered; confirm the current signature before you
# assert it to a customer. The minimal form below assumes a Delta Sync index with managed embeddings;
# self-managed-embedding / multi-column indexes may need extra kwargs.
retriever_tool = VectorSearchRetrieverTool(
    index_name=INDEX_NAME,                                   # your Module 04/05 index
    num_results=5,                                           # top-k chunks to return
    tool_description=(
        "Search Unity Airways policy and FAQ documents about flight cancellations, "
        "refunds, baggage rules, and travel policies. Use this for 'what is the policy' "
        "or 'am I allowed to' questions."
    ),
)

# COMMAND ----------

# MAGIC %md
# MAGIC ### How to verify it worked
# MAGIC Invoke the tool directly. It should return ranked policy chunks, and the call should appear in the
# MAGIC MLflow Trace UI as a retriever span.

# COMMAND ----------

print(retriever_tool.invoke({"query": "refund on a Basic Economy fare?"}))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Tool 2 — the structured-data lookup tool (a Unity Catalog function)
# MAGIC Documents can't tell you if flight UA123 is delayed — that is a **row in a table**. The Databricks-native
# MAGIC way to expose a table lookup to an agent is a **Unity Catalog function**: governed, versioned, reusable.
# MAGIC The `COMMENT`s are not decoration — they become the tool description the LLM reads.
# MAGIC
# MAGIC > 💡 **TIP:** the same `CREATE FUNCTION` a data engineer writes for a dashboard becomes an agent tool with
# MAGIC > governance, lineage, and permissions already attached — no new security surface, no bespoke microservice.

# COMMAND ----------

# MAGIC %sql
# MAGIC -- The COMMENTs on the function and each parameter become the description the LLM reads to pick + fill it.
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

# MAGIC %md
# MAGIC ### Seed the ops table the function reads (illustrative)
# MAGIC `get_flight_status` selects from `unity_airways.rag.flight_status_records`, so that table must exist with
# MAGIC rows before you can test the function or wrap it as a tool. This is **illustrative seed data** standing in
# MAGIC for a live ops feed — **09-6 (`09-6-responsesagent.py`) and the module lab reuse this same table**. It
# MAGIC includes flight `UA123` on `2026-07-20` (the value every test below queries) plus other statuses for variety.

# COMMAND ----------

# MAGIC %sql
# MAGIC -- Columns match the get_flight_status SELECT (flight_number, status, departure_gate,
# MAGIC -- scheduled_departure, estimated_departure) + the WHERE keys (flight_number, flight_date).
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

# MAGIC %md
# MAGIC ### Test the function directly — before it is ever a tool (09.10)
# MAGIC `DatabricksFunctionClient.execute_function(...)` runs the UC function straight, so you see the row(s)
# MAGIC before you trust an agent with it. This is the cheapest possible tool unit test.

# COMMAND ----------

from unitycatalog.ai.core.databricks import DatabricksFunctionClient

client = DatabricksFunctionClient()
result = client.execute_function(
    function_name=UC_FUNCTION,
    parameters={"in_flight_number": "UA123", "in_flight_date": "2026-07-20"},
)
print(result.value)   # you see the row(s) before wrapping it as a tool

# COMMAND ----------

# MAGIC %md
# MAGIC ### Wrap the function as a tool with `UCFunctionToolkit`
# MAGIC `UCFunctionToolkit` takes `function_names=[...]` and returns a **list** of LangChain tools in `.tools`,
# MAGIC one per function. Pass the same `DatabricksFunctionClient`.

# COMMAND ----------

from databricks_langchain import UCFunctionToolkit

uc_toolkit = UCFunctionToolkit(
    function_names=[UC_FUNCTION],   # can list several UC functions here
    client=client,
)
flight_tool = uc_toolkit.tools[0]   # uc_toolkit.tools is a LIST — one tool per function name
print(flight_tool.invoke({"in_flight_number": "UA123", "in_flight_date": "2026-07-20"}))

# COMMAND ----------

# MAGIC %md
# MAGIC ### Built-in code-execution tool (optional)
# MAGIC Databricks ships **`system.ai.python_exec`**, a sandboxed Python executor. Add it exactly like your own
# MAGIC UC function — `UCFunctionToolkit(function_names=["system.ai.python_exec"])` — when the agent needs to
# MAGIC *compute* (date math, unit conversions) rather than look something up. An instant code interpreter.

# COMMAND ----------

# NOTE: verify vs current docs — `system.ai.python_exec` availability/grants vary by workspace. Uncomment to
# add the built-in code-execution tool the same way you wrapped your own function.
# code_toolkit = UCFunctionToolkit(function_names=["system.ai.python_exec"], client=client)
# python_exec_tool = code_toolkit.tools[0]

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Tool 3 — the API-calling tool
# MAGIC Some answers live outside Databricks entirely. Weather is the classic flight example. Declare the inputs
# MAGIC with **Pydantic** so the LLM fills them correctly, write the function **with error handling** so a failed
# MAGIC call doesn't crash the agent, then wrap it as a `StructuredTool`.
# MAGIC
# MAGIC > ⚠️ **GOTCHA:** an API tool leaves the Databricks trust boundary — network egress, secrets/keys, rate
# MAGIC > limits, possibly PII. Keep keys in secrets, prefer governed connections, and read 09.4 before shipping one.

# COMMAND ----------

from pydantic import BaseModel, Field

class AirportWeatherInput(BaseModel):
    latitude: float = Field(description="Airport latitude in decimal degrees")
    longitude: float = Field(description="Airport longitude in decimal degrees")

# COMMAND ----------

import requests
from typing import Any

def get_airport_weather(latitude: float, longitude: float) -> dict[str, Any]:
    """Fetch the short-term weather forecast for an airport location.
    Returns hourly temperature, rain, and precipitation probability."""
    try:
        resp = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": latitude,
                "longitude": longitude,
                "hourly": "temperature_2m,rain,precipitation_probability",
            },
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()["hourly"]
    except Exception as e:
        # return a readable error so the LLM can recover, not a stack trace
        return {"error": f"weather lookup failed: {e}"}

# COMMAND ----------

from langchain_core.tools import StructuredTool

weather_tool = StructuredTool(
    name="get_airport_weather",
    func=get_airport_weather,
    description="Get the hourly weather forecast for an airport by latitude/longitude. "
                "Use to check whether weather may delay a flight.",
    args_schema=AirportWeatherInput,   # secures the input types the LLM might otherwise hallucinate
)

# COMMAND ----------

# MAGIC %md
# MAGIC ### How to verify it worked
# MAGIC Invoke it with Singapore's coordinates. It should return forecast data — or a clean `{"error": ...}` on
# MAGIC failure, **not** a crash.

# COMMAND ----------

print(weather_tool.invoke({"latitude": 1.3667, "longitude": 103.8}))   # Singapore

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Assemble the one tool list
# MAGIC Gather every tool into one list. `UCFunctionToolkit.tools` is already a list, so extend with it and
# MAGIC append the others. Start **small and well-defined** — a few sharp tools beat a sprawling toolbox.

# COMMAND ----------

tools = []
tools.extend(uc_toolkit.tools)   # structured lookups: get_flight_status, ...
tools.append(retriever_tool)     # unstructured retrieval
tools.append(weather_tool)       # external API

print(f"{len(tools)} tools assembled:")
for t in tools:
    print(" -", t.name)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Test each tool in isolation (09.10) before packaging
# MAGIC Silent tool failures are expensive to debug in production. Confirm each tool returns something sensible
# MAGIC on its own — this is the tool-layer test you run *before* the tools ever go into a `ResponsesAgent` (09.6).

# COMMAND ----------

checks = {
    "retriever (policy search)": lambda: retriever_tool.invoke(
        {"query": "Can my battery pack go in cabin baggage?"}),
    "get_flight_status (UC fn)": lambda: flight_tool.invoke(
        {"in_flight_number": "UA123", "in_flight_date": "2026-07-20"}),
    "get_airport_weather (API)": lambda: weather_tool.invoke(
        {"latitude": 1.3667, "longitude": 103.8}),
}

for name, run in checks.items():
    try:
        out = run()
        preview = str(out)[:120].replace("\n", " ")
        print(f"[OK]   {name}: {preview}...")
    except Exception as e:
        print(f"[FAIL] {name}: {e}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6. Bind the tool list to the LLM
# MAGIC Binding is what makes the tools visible to the model. `bind_tools(tools)` tells
# MAGIC `databricks-claude-sonnet-4-5` which tools exist; it then reads each `tool_description` and decides which
# MAGIC to call, with what arguments.

# COMMAND ----------

from databricks_langchain import ChatDatabricks

llm = ChatDatabricks(endpoint=LLM_ENDPOINT)
llm_with_tools = llm.bind_tools(tools)   # the model can now request any of these tools

# COMMAND ----------

# MAGIC %md
# MAGIC ### How to verify it worked
# MAGIC Ask a mixed question. The model should emit **tool calls** — expect `get_flight_status` (status) and the
# MAGIC retriever (refund policy). Open the MLflow Trace to confirm each call is a span with sensible args.

# COMMAND ----------

resp = llm_with_tools.invoke(
    "Is flight UA123 on 2026-07-20 delayed, and can I get a refund if it is?")
print("Tool calls the model chose:")
print(resp.tool_calls)   # shows which tools the model picked and with what args

# COMMAND ----------

# MAGIC %md
# MAGIC ## 7. Recap, gotchas and next step
# MAGIC **What you built**
# MAGIC - **Retriever tool** — `VectorSearchRetrieverTool` over `unity_airways.rag.ua_rag_chunks_index`.
# MAGIC - **Structured-data lookup tool** — the UC function `unity_airways.rag.get_flight_status`, tested with
# MAGIC   `DatabricksFunctionClient.execute_function(...)` and wrapped by `UCFunctionToolkit`.
# MAGIC - **API tool** — `get_airport_weather` wrapped as a `StructuredTool` with a Pydantic `args_schema`.
# MAGIC - One `tools` list, each tool tested in isolation, then `llm.bind_tools(tools)`.
# MAGIC
# MAGIC **Gotchas to remember**
# MAGIC - Vague or overlapping `tool_description` / SQL `COMMENT` is the #1 cause of wrong-tool bugs — one clear
# MAGIC   purpose per tool; say when to use it and the keywords.
# MAGIC - No `args_schema` on the API tool → the LLM passes wrong types and the call fails.
# MAGIC - UC functions need **three-level** names (`catalog.schema.function`), never two.
# MAGIC - An API tool with no `try/except` lets one outage crash the whole agent — return `{"error": ...}`.
# MAGIC - Import tools from **`databricks-langchain`**, not `langchain_community` / `langchain-databricks`.
# MAGIC
# MAGIC **Next:** `09-6-responsesagent.py` packages this exact `tools` list into a **`ResponsesAgent`**, logs it
# MAGIC Models-from-Code with `resources=[...]`, and registers it to `unity_airways.rag.ua_support_agent`. The
# MAGIC consolidated `09-module-lab.py` wires the LangGraph tool-calling loop (09.5) and managed MCP (09.8/09.11)
# MAGIC around these tools.
