# rag_chain.py — the entire chain, self-contained (no notebook globals). Loading re-runs this file.
import mlflow
from databricks_langchain import ChatDatabricks, DatabricksVectorSearch
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough

mlflow.langchain.autolog()

INDEX_NAME    = "unity_airways.rag.ua_rag_chunks_index"
VS_ENDPOINT   = "unity-airways-vs"
CHAT_ENDPOINT = "databricks-claude-sonnet-4-5"

retriever = DatabricksVectorSearch(
    endpoint=VS_ENDPOINT,
    index_name=INDEX_NAME,
    columns=["chunk_id", "content", "source_doc"],
).as_retriever(search_kwargs={"k": 5})

def format_docs(docs):
    return "\n\n".join(d.page_content for d in docs)

prompt = ChatPromptTemplate.from_messages([
    ("system",
     "You are the Unity Airways policy assistant. Answer the question using ONLY the "
     "context below. If the context does not contain the answer, say you don't know. "
     "Cite the source_doc you used.\n\nContext:\n{context}"),
    ("human", "{question}"),
])

llm = ChatDatabricks(endpoint=CHAT_ENDPOINT, temperature=0)

chain = (
    {"context": retriever | format_docs, "question": RunnablePassthrough()}
    | prompt | llm | StrOutputParser()
)

mlflow.models.set_model(chain)   # ← THIS is the model MLflow logs
