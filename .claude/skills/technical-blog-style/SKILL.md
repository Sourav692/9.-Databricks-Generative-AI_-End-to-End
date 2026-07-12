---
name: technical-blog-style
description: Apply a practical technical-blog voice to tutorials, explainers, notebooks, one-pagers, and HTML learning content. Use when writing or revising technical education content, especially Databricks/AI/ML content, where the desired style is problem-first, clear, hands-on, diagram-rich, builder-oriented, and human rather than generic.
---

# Technical Blog Style

Use this skill to shape technical learning content in the style requested by the user:

- Daily Dose of Data Science clarity: patient, structured, beginner-friendly, visual.
- Level Up Coding engineering depth: builder-oriented, practical, concrete, system-focused.
- Final human polish through `fe-workflows:humanize`, when that skill is available.

The goal is not to imitate any author. The goal is to reuse the effective pattern:
clear setup, useful diagrams, real implementation detail, and no generic AI filler.

## Style Formula

Apply this sequence to every substantial lesson, blog-style explainer, one-pager, or tutorial:

1. **Start with the real problem.**
   - Name the pain: unreliable agents, weak retrieval, slow inference, confusing governance, brittle prompts.
   - Make it concrete in 2-4 sentences.
   - Avoid broad trend openings.

2. **Explain why the simple approach breaks.**
   - Show the naive path first.
   - State the failure mode: hallucination, poor recall, high latency, bad permissions, stale docs, hidden cost.
   - Keep this direct and specific.

3. **Introduce the key idea in plain language.**
   - Define the concept before naming every API.
   - Use one tight analogy only if it helps.
   - Move quickly from intuition to mechanism.

4. **Break the system into components.**
   - Use a numbered flow, table, or diagram.
   - Each component should have a job, an input, and an output.
   - Prefer "what happens next" explanations over abstract taxonomies.

5. **Show the architecture or flow visually.**
   - Include at least one diagram when the content has moving parts.
   - Use diagrams to teach sequence, ownership, boundaries, data flow, or failure points.
   - Pair diagrams with short captions that explain what to notice.

6. **Move into implementation.**
   - Show the smallest useful code or UI path.
   - Explain the non-obvious lines.
   - Include prerequisites, runtime/version scope, and expected output when useful.

7. **End with trade-offs, gotchas, and field guidance.**
   - Include what to use, when to avoid it, and how to debug it.
   - Surface cost, latency, governance, observability, and evaluation implications.
   - Close with practical next steps, not a motivational wrap-up.

## Voice Rules

- Write like a technical practitioner teaching another technical practitioner.
- Keep paragraphs short: 1-3 sentences.
- Use bullets heavily, but avoid dumping lists with no narrative.
- Prefer concrete verbs: build, route, log, score, query, deploy, trace, filter.
- Use "you" when explaining a workflow; use "we" sparingly.
- Keep claims grounded. If a fact, API, metric, default, or version is uncertain, say it needs verification.
- Use named examples instead of generic placeholders whenever possible.
- For Databricks GenAI content, prefer the project running use case when it fits.

## Structure Patterns

Use these headings when they fit the artifact:

- **The Problem**
- **Why The Naive Version Fails**
- **The Core Idea**
- **System Map**
- **How It Works**
- **Implementation**
- **What To Watch**
- **Field Notes**
- **Sources**

For certification or interview content, add:

- **What The Exam Cares About**
- **How To Say It In An Interview**

For hands-on lessons, add:

- **Prerequisites**
- **Run This**
- **Expected Result**
- **How To Verify It Worked**

## Diagram Guidance

Use diagrams for one of four jobs:

- **Flow:** request -> retrieval -> prompt -> model -> answer -> trace.
- **Architecture:** user, app, serving endpoint, UC, Vector Search/AI Search, MLflow.
- **Decision:** choose A when, choose B when, avoid C if.
- **Failure analysis:** where latency, permissions, hallucination, or stale data enters.

Keep diagrams readable:

- 5-9 nodes is usually enough.
- Labels should be plain words.
- Every diagram needs a caption explaining the takeaway.

## Anti-Patterns

Remove these during the final pass:

- Broad openings like "AI is transforming every industry."
- Vague praise like "robust", "powerful", "cutting-edge", "seamless".
- The pattern "This is not X. This is Y."
- Long lists of features with no explanation of when to use each.
- Code blocks that are not explained.
- Diagrams that repeat the text without adding structure.
- Conclusions that only summarize. End with decision rules or practical next steps.

## Required Final Pass

Before shipping content:

1. Re-read the draft as a learner.
2. Confirm the opening states a concrete problem.
3. Confirm every major section earns its place.
4. Confirm diagrams and code snippets teach something specific.
5. Apply `fe-workflows:humanize` if available:
   - Remove banned AI phrases.
   - Break up wall-of-text paragraphs.
   - Keep the user's voice profile if one exists.
   - Preserve factual accuracy, source citations, code, APIs, and required project markers.

If `fe-workflows:humanize` is not available as a loadable skill, still apply its default behavior:
plain human prose, short paragraphs, no filler, no em dashes, no banned AI phrasing.
