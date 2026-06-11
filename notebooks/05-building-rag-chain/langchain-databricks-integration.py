# Databricks notebook source
# MAGIC %md
# MAGIC # LangChain ↔ Databricks — `ChatDatabricks` & `DatabricksVectorSearch`
# MAGIC **Roadmap:** Module 05 · Topic 05.2 · `[Hands-on]`
# MAGIC
# MAGIC Build a minimal **RAG chain** for the *Unity Airways* assistant using the two first-party
# MAGIC LangChain–Databricks classes. Mirrors *Practical MLflow for GenAI on Databricks*, Ch4 (pp. 140–147).
# MAGIC
# MAGIC ### Prerequisites
# MAGIC - **Compute:** Serverless notebook compute (or an ML runtime, e.g. 15.4 LTS ML+).
# MAGIC - **Model:** a pay-per-token **Foundation Model API** serving endpoint (default: `databricks-claude-3-7-sonnet`).
# MAGIC - **Vector Search:** an **endpoint** + a **Delta-sync index** with Databricks-managed embeddings
# MAGIC   (see Module 04 to create one). You need the index's `catalog.schema.index` name.
# MAGIC - **Unity Catalog:** read access to the index and the source docs.
# MAGIC - **Libraries:** `databricks-langchain`, `mlflow` (installed below).

# COMMAND ----------

# MAGIC %md
# MAGIC ## 0 · Install dependencies

# COMMAND ----------

# MAGIC %pip install -U databricks-langchain mlflow langchain-core

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1 · Configuration
# MAGIC Set these via the notebook widgets at the top (or edit the defaults). Fill in your Vector Search
# MAGIC endpoint + index before running the retrieval cells.

# COMMAND ----------

dbutils.widgets.text("llm_endpoint", "databricks-claude-3-7-sonnet", "1 · LLM serving endpoint")
dbutils.widgets.text("vs_endpoint", "", "2 · Vector Search endpoint")
dbutils.widgets.text("vs_index", "", "3 · Vector Search index (catalog.schema.index)")

LLM_ENDPOINT = dbutils.widgets.get("llm_endpoint")
VS_ENDPOINT = dbutils.widgets.get("vs_endpoint")
VS_INDEX = dbutils.widgets.get("vs_index")

QUESTION = "How do I book flights with Unity Airways?"  # the book's running example query

print(f"LLM endpoint : {LLM_ENDPOINT}")
print(f"VS endpoint  : {VS_ENDPOINT or '(TODO: set the vs_endpoint widget)'}")
print(f"VS index     : {VS_INDEX or '(TODO: set the vs_index widget)'}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2 · Enable MLflow tracing
# MAGIC One call and **every** LangChain invocation below is captured as an MLflow Trace
# MAGIC (view them in the experiment's **Traces** tab). Tracing is covered in Module 07.

# COMMAND ----------

import mlflow

mlflow.langchain.autolog()  # auto-trace all LangChain calls in this notebook

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3 · `ChatDatabricks` — call a served model (LLM-only baseline)
# MAGIC `ChatDatabricks` wraps a LangChain `ChatModel` pointing at a Model Serving / Foundation Model endpoint.
# MAGIC First, see what the LLM answers **without** any retrieved context.

# COMMAND ----------

from databricks_langchain import ChatDatabricks

chat_model = ChatDatabricks(
    endpoint=LLM_ENDPOINT,
    temperature=0,
    max_tokens=256,
)

# LLM-only answer (not grounded in Unity Airways docs yet)
print(chat_model.invoke(QUESTION).content)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4 · `DatabricksVectorSearch` — query the index
# MAGIC `DatabricksVectorSearch` wraps a LangChain `VectorStore` over a Vector Search index.
# MAGIC Use `.similarity_search(...)` to inspect what gets retrieved.

# COMMAND ----------

from databricks_langchain import DatabricksVectorSearch

assert VS_ENDPOINT and VS_INDEX, "Set the 'vs_endpoint' and 'vs_index' widgets first (Module 04 creates the index)."

vector_store = DatabricksVectorSearch(
    endpoint=VS_ENDPOINT,
    index_name=VS_INDEX,
)

# direct similarity search — peek at the top match
for doc in vector_store.similarity_search(query=QUESTION, k=1):
    print(f"* {doc.page_content}\n  metadata={doc.metadata}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5 · Turn the index into a retriever
# MAGIC `.as_retriever(...)` returns the standard LangChain retriever interface, so it composes with any chain.

# COMMAND ----------

retriever = vector_store.as_retriever(
    search_kwargs={"k": 3, "query_type": "ANN"},
)

# the retriever returns LangChain Documents
print(retriever.invoke(QUESTION))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6 · Assemble the RAG chain (LCEL)
# MAGIC Compose `retriever → prompt → model → parser`. The prompt merges the retrieved **context**
# MAGIC with the user **question**, so the answer is grounded in Unity Airways' own docs.

# COMMAND ----------

from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser

prompt = PromptTemplate(
    template=(
        "You are a customer support assistant for Unity Airways.\n"
        "Answer the question using ONLY the context. If unsure, say you don't know.\n\n"
        "Context:\n{context}\n\n"
        "Question: {question}"
    ),
    input_variables=["context", "question"],
)


def format_docs(docs):
    """Flatten retrieved Documents into a single context string."""
    return "\n\n".join(d.page_content for d in docs)


rag_chain = (
    {"context": retriever | format_docs, "question": RunnablePassthrough()}
    | prompt
    | chat_model
    | StrOutputParser()
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 7 · Invoke — grounded answer

# COMMAND ----------

print(rag_chain.invoke(QUESTION))

# COMMAND ----------

# MAGIC %md
# MAGIC ## ✅ Recap & next steps
# MAGIC - **`ChatDatabricks(endpoint=...)`** → call any served / Foundation Model endpoint from LangChain.
# MAGIC - **`DatabricksVectorSearch(index_name=...)`** → query a Vector Search index; `.as_retriever()` makes it chain-ready.
# MAGIC - **LCEL** wires `retriever → prompt → model → parser` into a RAG chain; `mlflow.langchain.autolog()` traces every run.
# MAGIC
# MAGIC **Good practice (Module 05.5–05.7):** move `LLM_ENDPOINT`, `VS_INDEX`, and the prompt into a
# MAGIC `rag_chain_config.yml` loaded via `mlflow.models.ModelConfig`, then **log the chain as code** so it's versioned and deployable.
# MAGIC
# MAGIC **Next roadmap topic:** `05.3 — LLM-only app → full RAG chain`.
