# Hands-on Artifact Conventions (IaC, CLI, Runbook, Notebook)

Use these conventions when generating the **last** artifact for a lesson — the
runnable/applyable hands-on piece. Networking & security on Azure Databricks is
configured through **IaC, CLI, the Azure Portal, and (for governance/audit) SQL**
— not PySpark. Pick the artifact type that matches the topic.

> **The hands-on artifact is the last artifact and is conditional.** Create
> markdown first, then HTML, then a hands-on artifact only if it genuinely adds
> value. Produce **1–2 artifacts per topic (module) covering all its subtopics** —
> never one per subtopic. If none is warranted, the markdown lesson describes the
> **step-by-step Azure Portal / Account Console actions** instead.
>
> **Altitude:** the hands-on artifact is where the **full, apply-ready IaC** lives.
> The lesson body (markdown/HTML) carries only *illustrative* snippets so an
> FDE/RSA can explain the setup; the complete provider config, every variable, and
> the full resource graph belong here, for the engineer who will actually apply it.

## Choosing the artifact type

| Topic family | Primary artifact | Also show |
| --- | --- | --- |
| VNet injection, subnets, NSG, UDR, NAT | **Terraform** (`azurerm` + `databricks`) | Portal runbook |
| Private Link (front/back/web-auth), Private DNS | **Terraform** / **Bicep** | Portal runbook + DNS records |
| Data exfiltration protection (Azure Firewall) | **Terraform** | firewall-rules table |
| NCC, network policies, IP access lists, token mgmt, CMK, SCIM | **Databricks CLI / REST / Python SDK / Terraform `databricks`** | Portal/Account-Console runbook |
| Unity Catalog grants, ABAC, masking, external locations | **SQL** | UI path |
| Audit logs, system tables, monitoring | **SQL** (system tables) | alert setup steps |
| Pure-conceptual / Portal-only | *no runnable artifact* | markdown UI runbook |

## Infrastructure-as-Code (Terraform) conventions

- Use the **`azurerm`** provider for Azure primitives and the **`databricks`**
  provider for workspace/account objects. Pin provider versions at the top and
  add a one-line comment on required provider auth (e.g. account vs workspace
  scope).
- Start every IaC file with a short header comment block:
  - **Goal** (one line).
  - **Prerequisites**: subscription/resource group, Databricks account or
    workspace, required RBAC roles (e.g. Network Contributor, Databricks
    workspace admin / account admin), region (resources must be co-regional).
  - **What it provisions** (3–5 bullets) and **cost caveats** (NAT egress,
    Private Endpoint per-GB, Azure Firewall).
- **Comment the non-obvious lines** — *why* a subnet is delegated, *why* an NSG
  rule or UDR exists, *why* `no_public_ip = true`, *why* a Private DNS Zone is
  linked. The config should teach.
- Use **variables** for subscription/region/CIDR/workspace so the sample is
  portable; show realistic CIDRs (`/16` VNet, `/18` or `/21` subnets, a small
  `/28` Private Link subnet).
- Prefer **enterprise-shaped** samples (subnet delegation block, NSG association,
  route table + UDR, Private Endpoint + Private DNS Zone group) over bare
  single-resource toys — but keep each file focused on the lesson's topic.
- Don't invent arguments. Verify resource/argument names against the current
  Terraform provider docs before including them (e.g.
  `azurerm_databricks_workspace.custom_parameters`,
  `azurerm_private_endpoint`, `azurerm_private_dns_zone`,
  `databricks_mws_network_connectivity_config`).

Example header:

```hcl
# Goal: Deploy an Azure Databricks workspace with VNet injection + Secure Cluster Connectivity (No Public IP).
# Prerequisites:
#   - Azure subscription + resource group; "Network Contributor" on the RG.
#   - Databricks account; provider auth at workspace scope.
#   - All resources co-regional with the workspace.
# Provisions: VNet, host+container subnets (delegated), NSG, NAT gateway, the workspace (NPIP).
# Cost: NAT gateway has an hourly + per-GB egress charge.
terraform {
  required_providers {
    azurerm    = { source = "hashicorp/azurerm",    version = "~> 3.0" }
    databricks = { source = "databricks/databricks", version = "~> 1.0" }
  }
}
```

## Bicep / ARM (alternative)

- Acceptable as the alternative IaC when a customer is Azure-native and prefers
  Bicep/ARM. Same header/commenting discipline. Parameterize region/CIDR.

## CLI / REST / SDK conventions

- For Databricks account/workspace objects with no clean Terraform path in the
  lesson, show the **Databricks CLI** command, the **REST** call (method + path +
  minimal JSON body), or the **Python SDK** snippet — whichever the docs use.
- Show the **`az`** CLI for Azure-side resources where it's clearer than Portal
  clicks.
- Note required auth/scope (account vs workspace token, Entra ID role) at the top.
- Never invent REST fields or CLI flags — verify against current docs.

## Portal / Account Console runbook conventions

When the artifact (or the no-artifact fallback) is a UI runbook:

- Give **exact, ordered steps**: `Portal → Resource → blade → field → value →
  button`. Name the blade and field precisely.
- Call out **where account-level vs workspace-level** settings live (Account
  Console vs workspace admin settings).
- Flag steps that are **irreversible** (e.g. some VNet-injection / CIDR choices
  can't be changed post-deployment) or that **require downtime**.
- Verify UI paths against current docs — Azure and Databricks UIs change.

## SQL conventions (governance & audit artifacts)

- Use Unity Catalog **three-level namespacing** `catalog.schema.table`.
- Show real grants and policies: `GRANT SELECT ON ...`, row filters, column
  masks, `CREATE EXTERNAL LOCATION`, `CREATE STORAGE CREDENTIAL`.
- For auditing, query **system tables** (e.g. `system.access.audit`); comment
  what each query answers (who accessed what, failed logins, grant changes).
- Keep cells/statements small, commented, and runnable top-to-bottom; include a
  cleanup statement when the script creates demo objects.

## Current vs deprecated terms (verify before asserting)

| Use this | Instead of |
| --- | --- |
| Microsoft Entra ID | Azure Active Directory / AAD |
| Workspace storage (root) | DBFS root (legacy) |
| Unity Catalog external locations + ADLS Gen2 | DBFS mounts |
| Secure Cluster Connectivity / No Public IP | "open inbound ports" setups |
| Network Connectivity Configuration (NCC) | (serverless ad-hoc IP allowlisting) |
| Host / container subnet | public / private subnet (Portal still shows old labels) |
| Lakeflow Declarative Pipelines / Lakeflow Jobs | Delta Live Tables / Workflows |

Verify feature names, GA-vs-Preview status, ports, and CIDR limits against the
docs before asserting them (these drift, and the source decks lag the product).
