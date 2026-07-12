# Verification Checklist (run before asserting version-sensitive facts)

The cardinal rule: **do not hallucinate.** Never invent APIs, Terraform
arguments, NSG service tags, ports, REST fields, config flags, UI paths, Private
DNS zone names, or features. When unsure, say so and verify first. Networking &
security facts drift fast (GA-vs-Preview, regional availability, ports, CIDR
limits) — verify them.

## Verify when the claim involves any of these

- Feature **availability** (GA / Public Preview / Private Preview, per cloud and
  often **per region** — e.g. serverless NCC private endpoints, egress control).
- **Tier** requirements (Premium vs Enterprise for Private Link, CMK, CSP, etc.).
- **Ports / protocols** (443, 6666, 8443–8451, 3306 legacy metastore, 9093
  telemetry; TLS 1.2+).
- **CIDR / address-space limits** (VNet `/16`–`/24`, subnets up to `/26`, Azure's
  5 reserved IPs per subnet, max cluster nodes for a sizing).
- **Private DNS zone names** (`privatelink.azuredatabricks.net`) and **OAuth
  CNAME** records.
- **Which services support Private Link / Service Endpoints** and which can't be
  put behind a Private Endpoint (e.g. some log/telemetry/artifact stores on
  Azure).
- **Terraform/Bicep resource & argument names**, **REST/SDK fields**, **`az` /
  Databricks CLI flags**.
- **UI navigation** ("Portal → … → blade" and Account Console paths change).
- **Product names** that have been rebranded (see name map below).
- Anything you "remember" but cannot pin to a current doc page.

## How to verify (Azure-first)

1. **Azure Databricks docs** — `https://learn.microsoft.com/azure/databricks/`
   is the canonical source for Azure-specific networking & security (VNet
   injection, SCC, Private Link, NCC, CMK, IP access lists, compliance). Fetch the
   specific page and cite the exact URL.
2. **Databricks docs / llms.txt index** — fetch
   `https://docs.databricks.com/llms.txt`, find the relevant section, then
   WebFetch the page (use for cross-cloud concepts, Unity Catalog, system tables).
   The `databricks-docs` skill wraps this.
3. **Azure platform docs** — `https://learn.microsoft.com/azure/` for the
   underlying primitives (VNet, NSG, UDR, Private Link, Private Endpoint, Service
   Endpoints, Private DNS Zone, NAT Gateway, Microsoft Entra ID, Key Vault).
4. **Terraform Registry** — the `databricks/databricks` and `hashicorp/azurerm`
   provider docs for resource/argument names before writing HCL.
5. **`WebSearch` / `WebFetch`** — for the latest docs or official blog posts when
   the index is insufficient.
6. **Cite** the specific doc page URL in the lesson's References section.

## Distinguish sources

- **Official docs** (`learn.microsoft.com/azure/databricks`,
  `learn.microsoft.com/azure`, `docs.databricks.com`) and the **official
  Databricks / Microsoft Tech Community blogs** → authoritative; cite directly.
- **Third-party blogs** → may add value but label clearly as third-party and
  cross-check the core claim against docs.

## Known rebrands / current names (verify, don't assume)

| Current name | Older / informal name |
| --- | --- |
| Microsoft Entra ID | Azure Active Directory / AAD |
| Workspace storage (root container) | DBFS root |
| Unity Catalog external locations + ADLS Gen2 | DBFS mounts |
| Secure Cluster Connectivity (SCC) / No Public IP (NPIP) | (open-port setups) |
| Network Connectivity Configuration (NCC) | (serverless ad-hoc allowlisting) |
| Host subnet / container subnet | public subnet / private subnet (Portal labels) |
| Lakeflow Declarative Pipelines | Delta Live Tables (DLT) |
| Lakeflow Jobs | Databricks Workflows / Jobs |

Names and availability change over time and the assistant knowledge cutoff may
lag the product. The source DBX Networking decks in particular predate some
rebrands and GA milestones — when a name, port, limit, tier, or syntax is even
slightly uncertain, verify against the live docs before teaching it as fact.

## If you cannot verify

State plainly: "I can't confirm this is current — here's what I believe, and
here's how to check it in the docs." Do not present unverified specifics
(especially GA-vs-Preview, ports, or CIDR limits) as fact.
