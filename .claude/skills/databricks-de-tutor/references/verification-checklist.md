# Verification Checklist (run before asserting version-sensitive facts)

The cardinal rule: **do not hallucinate.** Never invent APIs, parameters, config
flags, UI paths, or features. When unsure, say so and verify first.

## Verify when the claim involves any of these

- Feature **availability** (is it GA / Public Preview / on a given DBR or
  serverless tier?).
- **Syntax** of a SQL command, config flag, or API parameter.
- **Limits / quotas / pricing.**
- **UI navigation** ("go to … → …" paths change frequently).
- **Product names** that have been rebranded (see name map below).
- Anything you "remember" but cannot pin to a current doc page.

## How to verify

1. **`databricks-docs` skill / llms.txt index** — fetch
   `https://docs.databricks.com/llms.txt`, find the relevant section, then
   WebFetch the specific page under `https://docs.databricks.com/aws/en/`.
2. **`spark-api-beta` MCP server** — for PySpark/Spark API signatures, Spark
   Connect/Serverless support, and DBR-version availability.
   - `spark_search_apis`, `spark_get_api_info`, `spark_get_version_changes`.
3. **`WebSearch` / `WebFetch`** — for the latest docs or official Databricks blog
   posts when the index is insufficient.
4. **Cite** the specific doc page URL in the lesson's References section.

## Distinguish sources

- **Official docs** (`docs.databricks.com`) and **official Databricks blog** →
  authoritative; cite directly.
- **Third-party blogs** → may add value but label clearly as third-party and
  cross-check the core claim against docs.

## Known rebrands / current names (verify, don't assume)

| Current name | Older / informal name |
| --- | --- |
| Lakeflow Declarative Pipelines | Delta Live Tables (DLT) |
| Lakeflow Jobs | Databricks Workflows / Jobs |
| Lakeflow Connect | (managed ingestion connectors) |
| Unity Catalog Volumes | DBFS mounts (legacy) |

Names and availability change over time and the assistant knowledge cutoff may
lag the product. When a name, limit, or syntax is even slightly uncertain,
verify against the live docs before teaching it as fact.

## If you cannot verify

State plainly: "I can't confirm this is current — here's what I believe, and
here's how to check it in the docs." Do not present unverified specifics as fact.
