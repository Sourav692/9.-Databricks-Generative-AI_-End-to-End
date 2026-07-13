# Databricks notebook source
# MAGIC %md
# MAGIC # Module 02 Lab — Prompt Engineering
# MAGIC **Roadmap:** Module 02 · Topics 02.1, 02.2, 02.6 (hands-on core)
# MAGIC
# MAGIC ## The problem
# MAGIC An LLM support assistant works in the demo, then invents refund eligibility and phantom fees
# MAGIC in production. This lab builds the prompt-craft skills that prevent that: core techniques,
# MAGIC structured/JSON output, prompt templates in code, and a simple prompt-version comparison.
# MAGIC
# MAGIC ## What you will build
# MAGIC - Zero-shot / few-shot / reasoning prompts on the **Unity Airways** support use case
# MAGIC - A strict **JSON** prompt with downstream **schema validation**
# MAGIC - A reusable **prompt template** with `{{variable}}` placeholders
# MAGIC - A lightweight **prompt-version comparison** (v1 vs v2) on a tiny eval set
# MAGIC
# MAGIC ### Prerequisites
# MAGIC - Compute: **serverless** notebook or an ML runtime (DBR 14.3 LTS ML+). No cluster libraries needed.
# MAGIC - Libraries: `databricks-sdk` (preinstalled on Databricks); `mlflow>=3.1` for the comparison section.
# MAGIC - Access: a **Foundation Model APIs** pay-per-token entitlement, or an external-model / provisioned
# MAGIC   endpoint you can call.
# MAGIC - Unity Catalog: set `CATALOG` / `SCHEMA` below to a location you can write to (used only in the
# MAGIC   optional comparison section).
# MAGIC - Model endpoint: this lab uses `databricks-claude-sonnet-4-5`. **Endpoint names change** — confirm
# MAGIC   yours on *Serving → supported models* and edit `MODEL_ENDPOINT` if needed.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Setup
# MAGIC We call Databricks Model Serving through the **OpenAI-compatible client** from the Databricks SDK.
# MAGIC This is the pattern the book uses and it works cleanly with any serving endpoint.

# COMMAND ----------

# The OpenAI-compatible client is auth-free inside a Databricks notebook (uses your identity).
from databricks.sdk import WorkspaceClient

MODEL_ENDPOINT = "databricks-claude-sonnet-4-5"  # verify on Serving > supported models

w = WorkspaceClient()
client = w.serving_endpoints.get_open_ai_client()

def ask(prompt_text, temperature=0.1, max_tokens=350):
    """Send one user message to the serving endpoint and return the text response."""
    resp = client.chat.completions.create(
        model=MODEL_ENDPOINT,
        messages=[{"role": "user", "content": prompt_text}],
        temperature=temperature,   # low temp for consistent support answers
        max_tokens=max_tokens,     # cap output so answers can't run away
    )
    return resp.choices[0].message.content

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. The core idea — a prompt is a control surface
# MAGIC A good prompt sets the **role and scope**, gives **measurable constraints**, and says **what to do
# MAGIC when information is missing**. We compare a vague prompt with a controlled one on the same question.

# COMMAND ----------

question = "Can I change my flight to next week?"

# Zero-shot, vague: leaves too much room for interpretation -> may invent policy
vague = f"Answer this customer question: {question}"

# Zero-shot, controlled: role + constraints + missing-info rule
controlled = f"""You are a customer support assistant for Unity Airways.
Task: Answer the customer's question using only the information provided.
If key details are missing, ask exactly one clarifying question.
Do not invent fees, waivers, or exceptions.

Customer question: {question}

Write a concise answer (max 120 words)."""

print("=== VAGUE ===\n", ask(vague), "\n")
print("=== CONTROLLED ===\n", ask(controlled))

# COMMAND ----------

# MAGIC %md
# MAGIC ### How to verify it worked
# MAGIC The **controlled** answer should ask for the booking reference or fare type instead of promising a
# MAGIC free change. The **vague** one often over-promises. That difference is the whole point of 02.1.

# COMMAND ----------

# MAGIC %md
# MAGIC ### Few-shot: teach the decision posture with 3 short examples
# MAGIC One example that answers directly, one that asks for a missing detail, one that declines to speculate.

# COMMAND ----------

few_shot = f"""You are a customer support assistant for Unity Airways.
Rules:
- If key details are missing, ask exactly ONE clarifying question.
- Do not invent fees, waivers, or eligibility.
- Keep the final answer under 120 words.

Examples:
Q: What are your customer support hours?
A: Unity Airways support is available 24/7 for urgent travel issues.

Q: Can I change my flight to next week?
A: You can often change a booking, but eligibility and fees depend on your fare type and ticket rules. Can you share your booking reference?

Q: Will I definitely get a full refund if I cancel today?
A: I can't confirm a full refund without checking your fare rules, because eligibility depends on your ticket type. Could you share your booking reference?

Now respond to this question using the same style and rules.
Q: {question}
A:"""

print(ask(few_shot))

# COMMAND ----------

# MAGIC %md
# MAGIC ### Reasoning prompt: deliberate silently, output only the answer
# MAGIC In production you want better judgment, not the model's full monologue. Ask it to reason internally.

# COMMAND ----------

reasoning = f"""You are a customer support assistant for Unity Airways.

Internal reasoning (do not reveal):
- List missing key details (fare type, booking reference, route/date, disruption type).
- Decide: ask one question OR answer.
- Identify any statement that would be speculation and avoid it.

Customer question: {question}

Output (customer-facing only):
- If clarifying is needed: ask exactly ONE question.
- Otherwise: provide the answer in 2-4 short sentences."""

print(ask(reasoning))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Structured output — make the format a contract  [02.2]
# MAGIC When output feeds a parser, declare the exact schema, forbid extra text, and **validate downstream**.
# MAGIC "Please format as JSON" is not enough; use strong constraints like "ONLY" and "any additional text is invalid".

# COMMAND ----------

import json

json_prompt = f"""You are a customer support assistant for Unity Airways.

Return ONLY a valid JSON object with EXACTLY these keys:
- "answer": string
- "clarifying_question": string or null

Rules:
- If key details are missing, put one question in "clarifying_question" and keep "answer" short.
- If nothing is missing, set "clarifying_question" to null.
- Do not include explanations, comments, or any text outside the JSON object.

Customer question: {question}"""

raw = ask(json_prompt)
print("RAW MODEL OUTPUT:\n", raw)

# COMMAND ----------

# MAGIC %md
# MAGIC ### Downstream validation — the prompt reduces errors, validation catches the rest
# MAGIC A structured prompt improves consistency but does not guarantee perfect JSON every time. Parse it,
# MAGIC and on failure you would reprompt or fall back (shown here as a simple check).

# COMMAND ----------

def parse_support_json(text):
    """Validate the model output against our expected contract. Returns (ok, parsed_or_error)."""
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as e:
        return False, f"Not valid JSON: {e}"
    if set(obj.keys()) != {"answer", "clarifying_question"}:
        return False, f"Unexpected keys: {sorted(obj.keys())}"
    return True, obj

ok, result = parse_support_json(raw)
print("VALID CONTRACT?" , ok)
print(result)
# In production: if not ok -> reprompt with a corrective instruction, or route to a human / simpler prompt.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Prompt templates in code  [02.2 hands-on]
# MAGIC A template is a reusable instruction with placeholders. Author with **double-brace** `{{variable}}`
# MAGIC so the same template works with the MLflow Prompt Registry (Topic 02.5). Fill it at runtime.

# COMMAND ----------

# A plain-Python template with a {{question}} placeholder (registry-compatible double braces).
SUPPORT_TEMPLATE = """You are a customer support assistant for Unity Airways.
Rules:
- If key details are missing, ask exactly one clarifying question.
- Do not invent fees, waivers, or exceptions.
Customer question: {{question}}
Write a concise answer (max 120 words)."""

def render(template, **variables):
    """Render a {{double_brace}} template. Fails loudly if a variable is missing."""
    text = template
    for key, value in variables.items():
        text = text.replace("{{" + key + "}}", str(value))
    if "{{" in text:   # a placeholder was left unfilled -> surface it, don't ship nonsense
        raise ValueError(f"Unfilled placeholder(s) in template: {text}")
    return text

prompt_text = render(SUPPORT_TEMPLATE, question="Do I get a refund if I miss my flight?")
print(ask(prompt_text))

# COMMAND ----------

# MAGIC %md
# MAGIC > **GOTCHA:** the MLflow **Prompt Registry** uses `{{double_brace}}` variables, but LangChain's
# MAGIC > `PromptTemplate` uses `{single_brace}`. When you load a registry prompt into a LangChain chain,
# MAGIC > convert it with `prompt.to_single_brace_format()`. We stick to double braces here for registry parity.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Simple prompt-version comparison  [02.6 preview]
# MAGIC Turn "I like v2 better" into "v2 is measurably better." We define two prompt versions and a tiny
# MAGIC eval set of "gotcha" questions, then check whether each answer covers the **expected facts**.
# MAGIC
# MAGIC This is a lightweight, self-contained check. The full MLflow evaluation flow
# MAGIC (`mlflow.genai.evaluate` + the `Correctness` scorer) is in `02-5-prompt-registry.py`.

# COMMAND ----------

# Two prompt versions to compare
V1 = """You are a Unity Airways customer support assistant.
Customer question: {{question}}"""

V2 = """You are a careful Unity Airways customer support assistant.
Rules:
- If key details are missing, ask exactly one clarifying question.
- Do not invent fees, waivers, or refund eligibility.
- Keep the answer under 120 words.
Customer question:
{{question}}
Answer:"""

# Tiny eval set: each case lists checkable "expected facts" a good answer should reflect
eval_set = [
    {"question": "My flight is tomorrow. Can I change it to next week?",
     "expected_facts": ["eligibility depends on fare", "ask for booking reference or fare details"]},
    {"question": "I missed my flight due to traffic. Do I get a refund?",
     "expected_facts": ["refund eligibility depends on fare rules", "does not promise a refund"]},
    {"question": "My flight was canceled. Can I rebook for free?",
     "expected_facts": ["rebooking depends on disruption policy", "avoids blanket free promise"]},
]

# COMMAND ----------

# A cheap keyword-overlap "did it cover the expected idea?" check.
# NOTE: this is a teaching heuristic, NOT a real scorer. Use mlflow.genai Correctness (LLM judge) for real work.
def covers(answer, expected_facts):
    a = answer.lower()
    hits = 0
    for fact in expected_facts:
        # count a fact as covered if a few of its key words appear
        words = [w for w in fact.lower().split() if len(w) > 3]
        if sum(1 for wd in words if wd in a) >= max(1, len(words) // 2):
            hits += 1
    return hits / len(expected_facts)

def score_version(template):
    total = 0.0
    for case in eval_set:
        prompt_text = render(template, question=case["question"])
        answer = ask(prompt_text)
        total += covers(answer, case["expected_facts"])
    return total / len(eval_set)

score_v1 = score_version(V1)
score_v2 = score_version(V2)
print(f"v1 coverage: {score_v1:.2f}")
print(f"v2 coverage: {score_v2:.2f}")
print("Winner:", "v2" if score_v2 >= score_v1 else "v1")

# COMMAND ----------

# MAGIC %md
# MAGIC ### How to verify it worked
# MAGIC The constrained **v2** should score at least as high as the minimal **v1**, because it explicitly
# MAGIC requires asking for missing details and avoids inventing eligibility. Keep the **eval set fixed**
# MAGIC when comparing versions; if you change the prompt AND the dataset, you are running a different
# MAGIC experiment.
# MAGIC
# MAGIC > **IMPORTANT:** the keyword `covers()` check is a stand-in so this notebook runs anywhere. In real
# MAGIC > work, score with an LLM-as-a-judge (`from mlflow.genai.scorers import Correctness`) so grading is
# MAGIC > less sensitive to exact wording. That is what `02-5-prompt-registry.py` does.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6. Recap, gotchas & next steps
# MAGIC **What we built**
# MAGIC - Core prompting techniques (zero/few-shot/reasoning) on Unity Airways support
# MAGIC - A strict JSON prompt + downstream schema validation
# MAGIC - A registry-compatible `{{variable}}` prompt template
# MAGIC - A fixed-dataset prompt-version comparison (v1 vs v2)
# MAGIC
# MAGIC **Gotchas to remember**
# MAGIC - Endpoint names churn — confirm `MODEL_ENDPOINT` on the supported-models page.
# MAGIC - "Please format as JSON" is weak; use "return ONLY ... any additional text is invalid" + validation.
# MAGIC - Registry templates use `{{double}}` braces; convert with `to_single_brace_format()` for LangChain.
# MAGIC - Change one thing per version so you can attribute a score change to a specific edit.
# MAGIC
# MAGIC **Next roadmap topic**
# MAGIC - **02.5 — MLflow Prompt Registry** (`02-5-prompt-registry.py`): register/alias these prompts and run
# MAGIC   a real `mlflow.genai.evaluate` comparison instead of the keyword heuristic above.
