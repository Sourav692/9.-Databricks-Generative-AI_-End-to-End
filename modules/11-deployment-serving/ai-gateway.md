# AI Gateway  ·  Module 11 · Topic 11.3  ·  [Theory + Hands-on] ★

> **You are here:** Roadmap Module 11 → 11.3 (cornerstone deep-dive).
> **Prerequisites:** 11.1 (the Unity Airways agent is live as an **agent** Model Serving endpoint, `ua-support-agent`, deployed from `unity_airways.rag.ua_support_agent`; for completions it calls a **Foundation Model / external endpoint the team owns, `ua-support-llm`**, serving `databricks-claude-sonnet-4-5`). Helpful: Module 04 (external models), Module 10 (agents). This is the *gateway/endpoint-config* angle; the **guardrails deep-dive lives in 12.2**, monitoring in **Module 13**, cost control in **Module 16**.

## TL;DR
- **AI Gateway is a governance layer that sits in front of a Model Serving endpoint.** It adds rate limiting, safety and PII guardrails, usage tracking, payload logging, and provider fallbacks without touching your app code.
- You turn it on per endpoint. In the UI it is the endpoint's **AI Gateway** tab; in code it is one call: **`w.serving_endpoints.put_ai_gateway(name, ...)`** (signature verified against the current `databricks-sdk`).
- **Two endpoints, two roles (the governed agent pattern).** The Unity Airways agent (`ua-support-agent`, a deployed `ResponsesAgent`) calls a Foundation Model / external endpoint the team owns (`ua-support-llm`) for completions. Put the levers — **rate limits, guardrails, usage tracking, fallbacks** — on `ua-support-llm` (an FM/external endpoint supports them all). The **agent endpoint supports inference tables only** via AI Gateway, so enable **payload logging** there.
- It works for both **Databricks-hosted Foundation Models** and **External Models** (OpenAI, Anthropic, Amazon Bedrock, Google Vertex AI, Cohere, and more), so you can swap or fail over models behind a stable endpoint.
- **PII detection/redaction is Preview.** Safety filtering, rate limits, usage tracking, payload logging, and fallbacks are the established feature set.
- **Unity AI Gateway (Beta)** is the go-forward direction: richer UI and observability, governance of MCP servers and other agent surfaces, and **budget management** (spend thresholds and hard cost caps).

## The problem
- Your agent from 11.1 answers traveler questions reliably, but the endpoint still talks straight to an LLM with no controls in front of it.
- The moment it leaves your notebook and real users (or a batch `ai_query` job) hit it, five questions land on your desk at once:
  - Who is allowed to call it, and how often, before one script drains the token budget?
  - How do we stop the model from leaking a passenger's passport number or answering an off-topic, unsafe prompt?
  - Where do we see spend, latency, and error rates per team?
  - Can we keep the raw request/response payloads to debug and to build an eval set later?
  - What happens when the upstream provider has an outage at 2am?
- An FDE hears these in every "we built a POC, now make it production" conversation. AI Gateway is the standard answer.

## Why the naive approach fails
- **Wiring controls into the app.** You could add rate-limit code, a PII regex, and a logging call inside `app.py`. Now every app re-implements it, each slightly differently, and none of it is governed centrally.
- **Managing provider keys yourself.** Calling OpenAI or Anthropic directly means storing each provider's API key, matching each provider's request format, and editing code every time you switch models. The book calls this the tightly coupled trap: it "risks breaking the moment we want to swap to another model."
- **No shared view.** Cost and traffic get tracked per project, so the platform team has no single place to see consumption or enforce policy.
- The fix is to move these concerns **out of the app and onto the endpoint**, where one config governs every caller.

## What it is
- **Plain-language definition:** AI Gateway is a set of governance and reliability features you attach to a Model Serving endpoint. Requests flow *through* the gateway, which enforces limits, filters unsafe content, logs traffic, tracks usage, and can fail over to a backup model before returning the response.
- **Mental model:** think of it as the **reverse proxy / API gateway** you would put in front of any production API, purpose-built for LLM endpoints and wired into Unity Catalog. Same idea as an nginx or Kong in front of a web service, but it speaks "LLM" and writes to Delta.

## Why it matters (for a Databricks FDE)
- It is the difference between a demo endpoint and a governed one. This is often the last gate before a customer goes to production.
- It is UC-native: policies, logs, and usage all land in the customer's existing governance and observability stack. No new vendor, no new key vault.
- It decouples the app from the model, so the customer can adopt cheaper/newer models later without re-releasing the app.
- It is the on-ramp to the topics customers ask about next: guardrails (12.2), monitoring (Module 13), and cost control (Module 16).

## Core concepts
- **Serving endpoints (two here)** — the **agent endpoint** `ua-support-agent` (the deployed `ResponsesAgent` from 11.1) and the **Foundation Model / external endpoint** `ua-support-llm` it calls for completions. AI Gateway is a property *of* an endpoint, not a separate service you deploy — and which levers you get depends on the **endpoint type** (next bullet).
- **Endpoint type decides the levers** — on a **Foundation Model / external / provisioned-throughput / pay-per-token** endpoint, AI Gateway supports the full set (rate limits, guardrails, usage tracking, fallbacks, inference tables). On an **agent endpoint** (a `ResponsesAgent` from `agents.deploy`), it currently supports **inference tables only**. So you govern the agent by configuring the FM/external endpoint it calls (`ua-support-llm`), and you log the agent's own payloads on the agent endpoint (`ua-support-agent`). *(Verified in the `databricks-sdk` `put_ai_gateway` docstring; evolving — verify for your workspace.)*
- **Rate limiting** — cap calls (and/or tokens) per **user**, **user group**, **service principal**, or the **whole endpoint**, over a renewal window. Protects budget and fairness.
- **AI guardrails** — safety filtering, **PII detection with BLOCK / MASK / NONE behavior (Preview)**, invalid-keyword blocking, and topic restriction, applied to the **input**, the **output**, or both.
- **Usage tracking** — writes per-request consumption (tokens, counts) to **system tables** so finance and platform teams can attribute spend.
- **Payload logging (inference tables)** — captures the raw request and response into a **Delta table in Unity Catalog**. This is your debugging trail and a seed for eval datasets.
- **Fallbacks** — an ordered list of served models; if the primary errors, the gateway retries the next one so callers still get a response.
- **External Models** — the governed proxy to third-party providers (OpenAI, Anthropic, Amazon Bedrock, Google Vertex AI, Cohere, etc.). The gateway holds the provider key so your app never sees it.
- **AI Gateway for serving endpoints** vs **Unity AI Gateway** — the established per-endpoint feature set vs the newer **Beta** product surface that governs many agent surfaces (Apps, MCP servers, coding tools, endpoints) and adds budgets.

## 🗺️ Visual map

**Diagram 1 — the two endpoints and where each lever lives.**

```mermaid
flowchart TB
  subgraph CALLERS["Callers"]
    app["Unity Airways app / client"]
    batch["Batch ai_query jobs"]
  end
  app --> AGENT
  batch --> AGENT
  subgraph AGENT["ua-support-agent (agent endpoint)"]
    it["AI Gateway: inference tables only<br/>payload logging to UC Delta table"]
  end
  subgraph LLM["ua-support-llm (Foundation Model / external endpoint)"]
    rl["Rate limiting<br/>per user / group / endpoint"]
    gr["AI guardrails<br/>safety plus PII (Preview) plus keywords"]
    ut["Usage tracking<br/>system tables"]
    fb["Fallbacks<br/>retry next model on error"]
  end
  AGENT -->|"LLM completion request"| LLM
  LLM --> MODEL["databricks-claude-sonnet-4-5<br/>plus fallback model"]
```

**Diagram 2 — the request lifecycle: the agent logs, `ua-support-llm` screens.**

```mermaid
sequenceDiagram
  participant U as Traveler
  participant AG as ua-support-agent (agent endpoint)
  participant GW as ua-support-llm (AI Gateway)
  participant M as Model (primary)
  participant F as Model (fallback)
  U->>AG: request
  AG->>AG: log payload to inference table
  AG->>GW: LLM completion request
  GW->>GW: rate-limit check (per caller)
  GW->>GW: input guardrails (safety, PII, keywords)
  GW->>M: forward if allowed
  alt primary healthy
    M-->>GW: completion
  else primary errors
    GW->>F: retry via fallback
    F-->>GW: completion
  end
  GW->>GW: output guardrails plus usage tracking
  GW-->>AG: screened completion
  AG-->>U: response
```

## How it works — deep dive

### Rate limiting
- **Mechanism:** you attach one or more limits, each keyed by `USER`, `USER_GROUP`, `SERVICE_PRINCIPAL`, or `ENDPOINT`, with a `calls` and/or `tokens` budget over a renewal window (currently `MINUTE`).
- **Why it matters:** stops a single runaway caller from exhausting throughput or spend, and lets you give different teams different quotas on the same endpoint.
- **Trade-off:** limits are enforced at the gateway, so a blocked call returns an error to the caller. Set them generously at first and tighten with real usage data from Module 13.

### AI guardrails (safety, PII, keywords, topics)
- **Mechanism:** `AiGatewayGuardrails` holds an `input` and an `output` `AiGatewayGuardrailParameters`, each with `safety` (bool), `pii` (BLOCK / MASK / NONE), `invalid_keywords`, and `valid_topics`.
- **Why it matters:** the same policy applies to every caller, on the way in and on the way out. The airline can block prompt injection on input and redact a passport number on output in one place.
- **Trade-off:** gateway guardrails are coarse-grained safety and filtering. Domain logic ("never quote a refund amount without a policy citation") still belongs in the agent. The full guardrails design pattern is **12.2**.
- **Maturity:** safety filtering, keyword and topic controls are the established set. **PII detection/redaction is Preview** — verify behavior before promising it to a customer.

### Usage tracking
- **Mechanism:** flip `usage_tracking_config.enabled = True` and the gateway writes per-request consumption to **system tables**.
- **Why it matters:** finance-grade attribution of tokens and calls per endpoint, without instrumenting the app.
- **Trade-off:** system tables are account-level and may need enabling; the exact schema/table name should be confirmed in the current docs (Module 13 / 16 go deep). Treat precise table names as verify-at-authoring.

### Payload logging (inference tables)
- **Mechanism:** `inference_table_config` names a UC `catalog_name`, `schema_name`, and `table_name_prefix`; the gateway lands each request/response as rows in a Delta table there.
- **Why it matters:** this is your production debugging trail and the raw material for building an offline eval set (Module 08) and for monitoring (Module 13).
- **Trade-off:** logging has storage cost and can capture sensitive content, so pair it with the PII guardrail and UC access controls. The exact payload table suffix is a doc detail — read it back from the endpoint config rather than hardcoding.

### Fallbacks
- **Mechanism:** `fallback_config.enabled = True` tells the endpoint to retry the next served model in its list when the primary errors. The book shows a primary model with an "Add fallback" chain in the UI.
- **Why it matters:** provider outages and rate-limit errors stop being incidents. Travelers "always receive a response even during provider outages."
- **Trade-off:** the fallback model may differ in quality or cost. Keep the fallback list short and put a comparable model second.

### External Models and provider swap
- **Mechanism:** register a Databricks-hosted model or an External Model (OpenAI, Azure OpenAI, Anthropic, Amazon Bedrock, Google Vertex AI, Cohere, and others). The gateway stores the provider credential and exposes one unified, OpenAI-compatible surface.
- **Why it matters:** swap models by config, not code. The app keeps calling the same endpoint; the gateway routes.
- **Trade-off:** external calls leave Databricks' hosted models, so latency and data-egress considerations apply. Governance and logging still run at the gateway.

### Unity AI Gateway (Beta) — the direction of travel
- **What it adds:** a richer UI and observability, **governance of MCP servers** and other agent surfaces (per the current docs, AI Gateway "governs and monitors agents deployed to Apps, LLM endpoints, MCP servers, coding tools, and model serving endpoints"), and **budget management** with spend thresholds and hard cost caps.
- **Why it matters:** it centralizes control beyond a single endpoint, across the whole agent estate.
- **Maturity:** **Beta.** Teach it as where things are heading; keep production plans on the established per-endpoint feature set and confirm Beta availability with the customer's account team.

## How to do it on Databricks

> 📌 **IMPORTANT — the governed agent pattern:** configure the four gateway *levers* on **`ua-support-llm`** (the FM/external endpoint the agent calls), and enable **inference tables** on **`ua-support-agent`** (the agent endpoint). Every LLM request the agent makes is then screened server-side on `ua-support-llm`, while the agent's own request/response payloads are captured via its inference table. One caveat: rate limits on `ua-support-llm` bound the agent's LLM traffic — per-end-user limits at the *agent* tier aren't available via AI Gateway today.

### Option A — UI (fastest to demo)
1. Open **Serving** and select **`ua-support-llm`** — the Foundation Model / external endpoint the agent calls.
2. Open its **AI Gateway** tab and edit the config.
3. Turn on **Rate limits** (e.g. 100 calls/min per user), **Guardrails** (safety on; add invalid keywords; set PII to Block or Mask — Preview), and **Usage tracking**. To add a **fallback**, add a second served model to *this* endpoint and enable fallback.
4. Now select **`ua-support-agent`** (the agent endpoint). Its **AI Gateway** tab exposes **only Inference tables** — turn payload logging on here (choose the UC catalog/schema) for monitoring (Module 13).
5. Save. Both endpoints update in place; the URLs and callers do not change.

### Option B — SDK (`put_ai_gateway`, reproducible)

```python
# [Hands-on] Govern the agent with the two-endpoint pattern:
#   * the four levers on the FM/external endpoint the agent calls (ua-support-llm)
#   * inference-table payload logging on the agent endpoint (ua-support-agent) — its
#     only AI Gateway lever
# Signature verified against current databricks-sdk:
#   w.serving_endpoints.put_ai_gateway(name, *, fallback_config, guardrails,
#       inference_table_config, rate_limits, usage_tracking_config)
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.serving import (
    AiGatewayGuardrails, AiGatewayGuardrailParameters,
    AiGatewayGuardrailPiiBehavior, AiGatewayGuardrailPiiBehaviorBehavior,
    AiGatewayRateLimit, AiGatewayRateLimitKey, AiGatewayRateLimitRenewalPeriod,
    AiGatewayUsageTrackingConfig, AiGatewayInferenceTableConfig, FallbackConfig,
)

w = WorkspaceClient()

# 1) The four levers on the Foundation Model / external endpoint the agent calls.
#    Because ua-support-llm is an FM/external endpoint, every lever is supported.
w.serving_endpoints.put_ai_gateway(
    name="ua-support-llm",  # FM/external endpoint that serves databricks-claude-sonnet-4-5

    # a) Rate limiting: 100 calls/min per USER (also: USER_GROUP, SERVICE_PRINCIPAL, ENDPOINT)
    rate_limits=[
        AiGatewayRateLimit(
            calls=100,
            renewal_period=AiGatewayRateLimitRenewalPeriod.MINUTE,
            key=AiGatewayRateLimitKey.USER,
            # tokens=200000,  # optional token budget in the same window
        ),
    ],

    # b) Guardrails: safety both ways; block PII in, mask PII out (PII = Preview); block keywords
    guardrails=AiGatewayGuardrails(
        input=AiGatewayGuardrailParameters(
            safety=True,
            invalid_keywords=["internal_fare_class", "competitor_airline"],
            pii=AiGatewayGuardrailPiiBehavior(
                behavior=AiGatewayGuardrailPiiBehaviorBehavior.BLOCK,
            ),
        ),
        output=AiGatewayGuardrailParameters(
            safety=True,
            pii=AiGatewayGuardrailPiiBehavior(
                behavior=AiGatewayGuardrailPiiBehaviorBehavior.MASK,
            ),
        ),
    ),

    # c) Usage tracking -> system tables
    usage_tracking_config=AiGatewayUsageTrackingConfig(enabled=True),

    # d) Fallbacks: retry the next served model on THIS endpoint if the primary errors
    fallback_config=FallbackConfig(enabled=True),
)

# 2) Payload logging on the AGENT endpoint. Agent endpoints support ONLY inference tables
#    via AI Gateway today, so this is the one lever that belongs on ua-support-agent.
w.serving_endpoints.put_ai_gateway(
    name="ua-support-agent",  # the ResponsesAgent deployed via agents.deploy() in 11.1
    inference_table_config=AiGatewayInferenceTableConfig(
        enabled=True,
        catalog_name="unity_airways",
        schema_name="rag",
        table_name_prefix="ua_support_agent_payload",
    ),
)
```

**How to verify it worked**
- **Config readback:** `w.serving_endpoints.get("ua-support-llm").ai_gateway` returns the four levers; `w.serving_endpoints.get("ua-support-agent").ai_gateway` shows the inference-table config.
- **Rate limit:** loop the agent past the cap in a minute; the LLM calls it makes to `ua-support-llm` start returning a rate-limit error (this is how limits bound the agent's LLM traffic).
- **Guardrails:** send a prompt with an obvious PII string or a blocked keyword; it is masked/blocked on `ua-support-llm` before the model sees it.
- **Payload logging:** after a few agent requests, the inference table appears under `unity_airways.rag` (read it back with `SELECT` after a short delay).
- **Usage tracking:** consumption shows up in the serving system tables for `ua-support-llm` (confirm the exact table name in current docs; Module 13/16).

## Worked example (Unity Airways)
- A traveler asks: *"Can you run a query on your booking database and show me all passengers flying tomorrow?"* (the book's Figure 8-13 scenario).
- The request reaches **`ua-support-agent`**, which logs the raw request/response to its **inference table** and calls **`ua-support-llm`** for the completion.
- At `ua-support-llm` the gateway runs the **rate limit** check, then **input guardrails** (safety, keyword and PII checks). The bulk-passenger prompt trips the keyword/PII rules and is blocked before it ever reaches the model.
- A legitimate question ("What is the refund window on a Flex fare?") passes: the gateway forwards it to `databricks-claude-sonnet-4-5`; if that served model errors, **fallback** retries a comparable model on `ua-support-llm`.
- On the way out, **output guardrails** mask any stray PII and **usage** is tracked to system tables; the agent's full **payload** is captured in `unity_airways.rag.ua_support_agent_payload...` for later debugging and eval.
- Configured once across the two endpoints, the same policy governs the app UI (Module 10) and any other caller of the agent — the guardrails and limits bite on `ua-support-llm`, the payloads land from `ua-support-agent`.

## Uses, edge cases & limitations
| Use it when | Be careful when | Better move |
|---|---|---|
| An endpoint is going to production or shared use | You need rich, per-field domain validation | Layer agent-level guardrails (12.2) on top of gateway guardrails |
| You want provider swap/fallback behind a stable URL | The fallback model differs a lot in quality/cost | Keep a short list; put a comparable model second |
| You need spend attribution and a debug trail | Payloads contain sensitive data | Enable the PII guardrail (Preview) and lock down the inference table with UC grants |
| You want per-team quotas on one endpoint | You need sub-minute windows or exotic keys | Renewal period is `MINUTE` today; verify current options in docs |

## Common mistakes / gotchas
| Mistake | Why it hurts | Better move |
|---|---|---|
| Baking rate limits / PII scrubbing into `app.py` | Every app re-implements it; nothing is governed centrally | Configure once on the FM/external endpoint the agent calls via `put_ai_gateway` |
| Putting guardrails / rate limits / fallbacks on the **agent** endpoint | Agent endpoints support only inference tables via AI Gateway, so those levers don't take there | Configure the four levers on the FM/external endpoint the agent calls (`ua-support-llm`); keep inference tables on the agent endpoint |
| Assuming PII redaction is GA | It is **Preview** and may change | Label it Preview; verify before committing to a customer |
| Treating "AI Gateway" and "Unity AI Gateway" as the same thing | One is the per-endpoint feature set; the other is a newer Beta product surface | Say which one you mean; keep production on the established features |
| Hardcoding the inference/system table names | Names are doc details and can differ | Read them back from the endpoint config / current docs |
| Logging payloads without access controls | Sensitive traffic sits in a readable table | Pair payload logging with PII guardrail + UC grants |

> 📌 **IMPORTANT:** AI Gateway is a **property of the FM/external serving endpoint the agent calls**, and the levers you get depend on the endpoint type. For a governed agent, put **rate limiting, guardrails, usage tracking, and fallbacks** on `ua-support-llm` (the FM/external endpoint the agent calls), and enable **payload logging (inference tables)** on the **agent endpoint** `ua-support-agent` — the one AI Gateway lever agent endpoints support today. Configure each with `w.serving_endpoints.put_ai_gateway(name, ...)`; together they govern **every** caller of the agent.

> 💡 **TIP (field):** Introduce a gateway "as soon as your agent moves out of your personal development notebook and into a shared environment." Start limits and guardrails permissive, enable payload logging on day one so you have data, then tighten using what Module 13 shows you.

> ⚠️ **GOTCHA:** The book (B1 Ch7/Ch8) calls this "MLflow AI Gateway / Databricks AI Gateway" and shows a standalone gateway endpoint URL. The current product term is **AI Gateway** configured on a Model Serving endpoint, with **Unity AI Gateway (Beta)** as the newer umbrella. **PII detection/redaction is Preview.** Exact **system table** and **inference table** names are doc details, so verify them live rather than quoting from memory. **Endpoint-type support is by design here, not a workaround:** the `databricks-sdk` `put_ai_gateway` docstring states AI Gateway is fully supported on **external-model, provisioned-throughput and pay-per-token** endpoints (the Foundation Model API modes), while **agent endpoints** (a `ResponsesAgent` deployed via `agents.deploy`) **currently support only inference tables**. That is exactly why the four levers sit on `ua-support-llm` and payload logging sits on `ua-support-agent`. Per-end-user rate limits at the *agent* tier aren't available via AI Gateway today; limits on `ua-support-llm` bound the agent's LLM traffic instead. Evolving; verify for your workspace.

## 📝 Notes
- _Space for your own notes: which levers your customer needs first, and what their per-team quotas should be._

**Self-check (5 questions)**
1. Name the five things AI Gateway can enforce on a serving endpoint. Which single SDK call configures them?
2. What are the four rate-limit keys, and what renewal period is currently supported?
3. What are the three PII behaviors, and what is the maturity label you must attach to PII redaction?
4. Where does payload logging write, and why pair it with a PII guardrail and UC grants?
5. What is the difference between "AI Gateway for serving endpoints" and "Unity AI Gateway," and which is Beta?

## How this maps to the certification
- **Exam domain: Deployment and Production (governance, monitoring, safety).** The cert expects you to know that Databricks governs LLM endpoints with rate limits, guardrails, usage tracking, payload/inference logging, and fallbacks, and that External Models are proxied and governed through the same layer. Expect scenario questions on "how do you stop a runaway caller / redact PII / fail over providers" — the answer is AI Gateway on the endpoint.

## Sources
- 📘 **B1 — _Practical MLflow for GenAI on Databricks_ (O'Reilly Early Release, RAW & UNEDITED), Ch 7:** "MLflow AI Gateway transitioning to Databricks AI Gateway" (pp. 260–262) — centralized secure interface, provider abstraction, swap by config, UC integration, usage rate limits on user groups, guardrails, usage/payload tracking to tables. Figure 7-2.
- 📘 **B1 — Ch 8:** "MLflow AI Gateway," "Using MLflow AI Gateway," "Capabilities," "Fallbacks," "Custom Guardrails," and "AI Guardrails" (pp. 312–324) — gateway as governed proxy, unified endpoint + OpenAI-compatible client, fallback chains, guardrails on input/output, layered guardrail design. Figures 8-9 through 8-13 (Unity Airways flow).
- 🧰 **`databricks-sdk` (live introspection, July 2026):** `ServingEndpointsAPI.put_ai_gateway(name, *, fallback_config, guardrails, inference_table_config, rate_limits, usage_tracking_config) -> PutAiGatewayResponse`; config dataclasses `AiGatewayGuardrails/GuardrailParameters/GuardrailPiiBehavior`, `AiGatewayRateLimit` (keys `USER/USER_GROUP/SERVICE_PRINCIPAL/ENDPOINT`, renewal `MINUTE`, `calls`/`tokens`), `AiGatewayUsageTrackingConfig`, `AiGatewayInferenceTableConfig`, `FallbackConfig`. The same docstring states "External model, provisioned throughput, and pay-per-token endpoints are fully supported; **agent endpoints currently only support inference tables**" — the basis for the two-endpoint pattern above. **This is the verified signature for the hands-on code above.**
- 🧭 **Naming cheat-sheet §6** (`references/naming-conventions.md`): AI Gateway feature set on Model Serving (rate limiting, guardrails incl. **PII Preview**, usage tracking, payload logging → inference tables, fallbacks, supported external providers) and **Unity AI Gateway = Beta** (MCP-service governance, budget management).
- 🌐 **Docs — AI Gateway** (`https://docs.databricks.com/ai-gateway/`): confirmed live via `llms.txt` (July 2026): "AI Gateway governs and monitors agents deployed to Apps, LLM endpoints, MCP servers, coding tools, and model serving endpoints." Endpoint-config and External Models pages under `docs.databricks.com/aws/en/ai-gateway/` and `.../generative-ai/external-models/` are JS-rendered; treat precise UI strings and table names as **live re-check pending**.
- 🔗 Cross-refs: guardrails deep-dive **12.2**; monitoring / inference tables **Module 13**; cost control / budgets **Module 16**; the endpoint itself **11.1**.
