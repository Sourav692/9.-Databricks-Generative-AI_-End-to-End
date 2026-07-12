# Azure Databricks Networking & Security — Beginner → Expert Curriculum

This is the recommended module map and teaching order, grounded in the **DBX
Networking** decks (Azure System Architecture, the *Networking & Security
Fundamentals — Module 5* endpoints/DNS deck, and the *L300 Cloud Infra &
Security Enablement* deck) and reconciled with current Azure Databricks docs.

Use it to (a) decide what a "beginner→expert" path looks like, (b) scope an
individual lesson within the larger arc, and (c) sequence a multi-lesson build.
**Always verify version/GA-Preview/region facts against the docs before
teaching** — the decks lag the product (e.g. they may say "DBFS"/"AAD"; teach
"workspace storage"/"Microsoft Entra ID").

The arc has four levels. Each module lists its sub-topics, the primary grounding,
and the natural hands-on artifact.

> **Also a primary source:** the user's Notion page **"General Networking
> Concepts"** (`https://app.notion.com/p/General-Networking-Concepts-2c2bd80266da806f9d6fc2658091ccfc`),
> under "Notes – Networking and Security in Databricks". Fetch it with
> `mcp__notion__notion-fetch` and reuse its framing/analogies where they're good;
> reconcile any stale terms against current docs. See SKILL.md "Using attached
> materials".

---

## LEVEL 0 — Networking & Cloud Foundations (Beginner)

Goal: a learner with no cloud-networking background can follow every later
module. Cloud-agnostic primitives, taught with Azure terminology.

### M0.1 — IP addressing & CIDR
- Public vs private IP; RFC 1918 (`10.0.0.0/8`, `172.16.0.0/12`,
  `192.168.0.0/16`) and RFC 6598 (`100.64.0.0/10`); reserved ranges.
- CIDR notation, subnet math, how netmask size determines host count.
- Analogy: public IP = street address; private IP = apartment number.
- Hands-on: CIDR-sizing worksheet (markdown table), no IaC.

### M0.2 — VNets, subnets, and the cloud network model
- Virtual Network (VNet) as an isolated address space; subnets as subdivisions.
- Azure: VNet + subnets; brief one-line map to AWS VPC / GCP VPC.
- Hands-on: a minimal `azurerm_virtual_network` + `azurerm_subnet` Terraform.

### M0.3 — Firewalls, NSGs, and routing
- Network Security Group (NSG): stateful allow/deny inbound & outbound between
  Azure resources; service tags.
- Route tables & User-Defined Routes (UDR): overriding Azure's default system
  routes; the `0.0.0.0/0` catch-all.
- NAT Gateway (egress, stable outbound IP) and the role of an Internet Gateway.
- Hands-on: an NSG + route-table Terraform snippet with commented rules.

### M0.4 — DNS, endpoints, and name resolution
- DNS as "the phonebook of the internet"; resolver/recursion in one paragraph.
- What an *endpoint* is (a named destination resolving to an IP).
- Azure **Private DNS Zones** and why private resolution matters.
- Hands-on: a Private DNS Zone + record-set snippet.

### M0.5 — Common network topologies
- Hub-and-spoke (central hub, spokes don't talk directly); benefits & the
  single-point-of-failure / bottleneck trade-offs.
- VNet peering; on-prem connectivity via ExpressRoute / VPN Gateway.
- Hands-on: mermaid hub-and-spoke diagram; conceptual, no IaC.

---

## LEVEL 1 — Azure Databricks Architecture & Default Connectivity (Beginner→Intermediate)

Goal: understand what the platform *is* before securing it.

### M1.1 — Control plane vs compute plane
- Control plane (Databricks-managed: web app, Unity Catalog, cluster/jobs/query
  managers, SCC relay) vs compute plane (where data is processed).
- Classic compute = customer subscription; serverless compute = Databricks
  account. Storage & data always in the customer subscription.
- The "secure boundary" and Secure Cluster Connectivity intro (no inbound ports).
- Grounding: `databricks-docs` (architecture); Azure ADB architecture docs.

### M1.2 — The three connectivity paths
- (1) Users/apps → Databricks, (2) compute plane ↔ control plane, (3) compute
  plane → storage. Classic vs serverless behavior for each.
- This is the mental scaffold for the whole curriculum — every later module
  secures one of these three paths.

### M1.3 — Azure Databricks deployment & workspace storage
- First-party Azure service; deployed via Portal / ARM / Bicep / CLI / Terraform.
- Workspace storage (root container, system vs user; the term that replaced
  "DBFS root") — and why you must NOT use it for governed data.
- Account Console, workspace, Unity Catalog metastore relationships.
- Hands-on: `azurerm_databricks_workspace` Terraform (default/managed VNet).

---

## LEVEL 2 — Classic Compute Plane Networking (Intermediate)

Goal: design and defend a secure classic-compute network on Azure.

### M2.1 — Default (managed) VNet vs VNet injection
- Default: Databricks manages the VNet (simple, no customization, auto NAT).
- VNet injection: deploy into a customer VNet for full control of NSGs and UDRs.
- Subnet delegation to `Microsoft.Databricks/workspaces` and the immutable
  **network intent policy** (why Service Endpoint *Policies* can't attach).
- Grounding: ADB "Deploy in your VNet (VNet injection)" docs.

### M2.2 — Subnets & address-space sizing
- Host subnet ("public-subnet") and container subnet ("private-subnet") — both
  private under SCC; prefer the host/container naming.
- VNet `/16`–`/24`, two subnets up to `/26`; Azure reserves 5 IPs per subnet;
  the VNet-CIDR-minus-2 recommendation to leave room for a Private Link subnet.
- Address space → max cluster nodes; IP exhaustion when scaling; CIDR update
  process (downtime, VNet-injection only).
- Hands-on: sizing table + a VNet/subnet Terraform with the delegation block.

### M2.3 — Secure Cluster Connectivity (SCC) / No Public IP (NPIP)
- No public IPs on VMs, no open inbound ports; the **SCC relay** reverses the
  call direction (outbound DP→CP). Why CP↔DP still uses public IPs until Private
  Link. NAT gateway for a stable egress IP.
- Best-practice baseline: VNet injection + SCC.
- Hands-on: workspace Terraform with `no_public_ip = true` + custom VNet.

### M2.4 — Egress: NSG rules, UDRs, NAT gateway
- Restricting outbound traffic with NSG rules; UDRs to send egress to a firewall;
  Azure NAT Gateway for managed egress.
- The required outbound destinations (control plane / SCC relay, artifact &
  log/telemetry storage, metastore) and their ports.
- Hands-on: UDR + NSG Terraform; the egress-allowlist table.

### M2.5 — Compute → storage (classic): public / service / private endpoints
- Storage firewall + **Service Endpoints** (free, Azure-backbone, subnet-scoped,
  egress-only, no DNS/NIC) vs **Private Endpoints** (a real NIC + private IP,
  per-GB cost, needs DNS, works on-prem). Public endpoint as the insecure default.
- Why Service Endpoint *Policy* doesn't work with ADB (delegated subnets).
- Hands-on: storage-account firewall + service-endpoint Terraform; PE alternative.

---

## LEVEL 3 — Private Link, DNS & Advanced Topologies (Advanced)

Goal: the full private, exfiltration-protected enterprise architecture.

### M3.1 — Private Link connection types
- **Back-end** Private Link (compute plane → control plane: SCC relay + web
  app/REST). **Front-end** Private Link (user → workspace UI/REST/Connect).
  **Web-auth** private connection (SSO/OAuth callback; one per region).
- Setting "Allow Public Network Access" to Disabled; the locked web-auth
  workspace pattern.
- Grounding: ADB Private Link docs.

### M3.2 — Private DNS for Private Link
- `privatelink.azuredatabricks.net` zone; replacing the public
  `adb-<id>.azuredatabricks.net → public IP` with the private IP; OAuth callback
  CNAMEs; custom-DNS single-entry constraint (shared private endpoint).
- Common access errors (workspace denial, OAuth denial) and their DNS root cause.
- Hands-on: Private DNS Zone + A/CNAME records + VNet link Terraform.

### M3.3 — Transit / hub-and-spoke for Databricks
- Separate transit VNet for front-end PE; hub VNet with shared PEs; ports 443 &
  6666; standard vs simplified deployment (separate transit VNet vs transit
  subnet, single combined PE).
- Hands-on: hub-spoke peering + PE-subnet Terraform; topology mermaid.

### M3.4 — Data Exfiltration Protection (DEP)
- SCC + VNet injection + Private Link + **Azure Firewall** in a hub; UDR routes
  all egress to the firewall; firewall allowlist for Databricks
  artifact/log/telemetry/metastore FQDNs; don't route SCC through the firewall
  (extra hop). Combine with full Private Link.
- Hands-on: Azure Firewall + UDR + firewall-rules table; the DEP reference diagram.

---

## LEVEL 4a — Serverless Networking (Advanced)

Goal: secure connectivity for the Databricks-hosted serverless compute plane.

### M4a.1 — Serverless architecture & why networking differs
- Serverless compute plane lives in the Databricks account; dynamic IPs mean you
  can't peer or whitelist a static IP — hence NCC. CP↔serverless always over the
  cloud backbone (TLS), never public internet.

### M4a.2 — Network Connectivity Configuration (NCC)
- Account-level, **regional** object bound to one or more workspaces. Default
  rules expose **service endpoint subnet IDs** for storage-firewall allowlisting;
  **private endpoints** to ADLS (and Azure SQL for Lakehouse Federation).
- Logical separation: create NCCs per desired isolation boundary; prefer Service
  Endpoints + backbone, use Private Endpoints only when mandated (cost).
- Hands-on: NCC create + bind via Databricks CLI / Terraform `databricks` provider.

### M4a.3 — Serverless egress control / network policies
- Default-deny outbound with exceptions (UC locations/connections; explicitly
  enumerated FQDNs; enumerated storage). Direct storage access from UDF/REPL
  denied — only UC securables. Network policies per workspace.
- Hands-on: an egress/network-policy definition snippet.

### M4a.4 — Storage access patterns (serverless)
- Public (no firewall) vs Service Endpoints (NCC-provided subnet IDs) vs Private
  Endpoints (NCC maps storage FQDN → private IP). Managed Identity / access
  connector; short-lived tokens (SAS) from the Serverless Access Manager.

---

## LEVEL 4b — Security: Identity, Authorization, Encryption, Compliance (Intermediate → Expert)

Goal: the security half of "Networking & Security" — runs in parallel with the
networking levels; teach it once a learner understands the architecture (L1).

### M4b.1 — Identity & authentication
- Microsoft Entra ID SSO; SCIM provisioning of users/groups; **identity
  federation** via the account console; account vs workspace admins; service
  principals for automation; PAT vs Entra ID tokens; token lifetime management.
- Multi-IdP federation (Okta, Entra ID).
- Grounding: `databricks-docs` + ADB identity docs.

### M4b.2 — Network access controls for users
- **IP access lists** (account console & workspace level); Entra ID Conditional
  Access; front-end Private Link as the strongest control. (Ties back to M3.1.)

### M4b.3 — Authorization & data governance (Unity Catalog)
- Metastore → catalog → schema → securable hierarchy; grants; **ABAC**, row
  filters, column masks; storage credentials & external locations; the managed
  identity **access connector**; UC isolation (physical storage separation per
  catalog/schema, workspace-catalog binding).
- Cluster policies; cluster **access modes** and their UC compliance; access
  control on workspace objects (clusters, jobs, secrets, notebooks).
- Grounding: `databricks-unity-catalog`.
- Hands-on: SQL — `GRANT`, row-filter/column-mask, external location + storage
  credential.

### M4b.4 — Encryption
- In transit: TLS 1.2+ everywhere (CP↔DP always encrypted). At rest: Azure
  Storage encryption. **Customer-Managed Keys (CMK)** via Azure Key Vault for
  managed services and workspace storage; inter-node / local-disk encryption.
- Hands-on: CMK configuration via Terraform/CLI + Key Vault access.

### M4b.5 — Compute security & isolation
- Serverless isolation model; ephemeral, scoped tokens (Azure SAS) used directly
  to storage (not via control plane); confused-deputy protection; workspace and
  data isolation standards.

### M4b.6 — Compliance, auditing & monitoring
- **Enhanced Security & Compliance (ESC)** add-on, **Enhanced Security
  Monitoring (ESM)**, **Compliance Security Profile (CSP)**; certifications.
- **Audit logs** + diagnostic logging; **system tables**; integrating into a
  wider SIEM; alerts via Databricks SQL.
- Hands-on: SQL queries over `system.access.audit` and related system tables.

---

## LEVEL 5 — Synthesis, Best Practices & Interview/Customer Prep (Expert)

### M5.1 — Reference architectures end-to-end
- Azure Standard (recommended) vs Simplified deployment; full-DEP architecture;
  isolated/regulated workspace; IP-exhaustion architecture. Walk a packet from
  user → workspace → cluster → storage naming the control at each hop.

### M5.2 — Networking & security best-practices checklist
- SCC + customer-managed VNet always; size subnets for peak nodes; RFC 1918/6598;
  back-end Private Link; Service Endpoints/Private Link for external services
  (validate cost first); Premium/Enterprise tier; SCIM + SSO + MFA; separate
  admin accounts; cluster policies + user isolation; CMK; IP access lists; audit
  logging on; IaC for everything; follow org network norms.

### M5.3 — Customer-conversation & interview scenarios
- "Walk me through securing an ADB workspace for a regulated bank"; "Service
  Endpoint vs Private Endpoint — when and why?"; "How does SCC work and what does
  Private Link add?"; "How does serverless reach my private ADLS?"; "How do you
  prevent data exfiltration?". Each scenario = synthesis across the modules above.

---

## LEVEL 6 — FDE Field Engineering (Expert · the customer-facing layer)

The first five levels teach the platform. Level 6 is the **Field Engineer's
job**: deploy it at a real customer, troubleshoot it when it breaks, defend it in
an interview, and hand the customer collateral. Every Level 0–5 lesson already
carries an **FDE field notes** block; Level 6 turns that lens into standalone
playbooks and deliverables.

### Stage 10 — FDE Field Playbooks (Troubleshooting · Deployment · Escalation)
- **10.1 — Compute & networking startup failures:** cluster/workspace won't
  start, **IP exhaustion**, NSG/UDR/subnet-delegation misconfig; symptom →
  first diagnostic check → fix.
- **10.2 — Connectivity troubleshooting:** front-end access failures, **Private
  Link / Private DNS** resolution problems, SCC relay, OAuth/web-auth errors;
  the DNS-first diagnostic discipline.
- **10.3 — Storage & serverless access troubleshooting:** Service vs Private
  Endpoint, NCC, storage-firewall denials, managed-identity/access-connector
  failures.
- **10.4 — Customer deployment patterns & the architecture decision flow:** which
  topology (Standard / Simplified / full-DEP / isolated / IP-exhaustion) for which
  customer regulatory + cost profile; a decision tree.
- **10.5 — Diagnostics, support & escalation:** what to collect (logs, system
  tables, NSG flow logs, DNS lookups), when/how to escalate, and the tools an FDE
  reaches for.

### Stage 11 — FDE Interview Prep Capstone
- **11.1 — Whiteboard scenarios:** design end-to-end secure Azure Databricks for a
  regulated customer; narrate the packet path and the control at each hop.
- **11.2 — Rapid-fire Q&A bank:** Service Endpoint vs Private Endpoint, SCC,
  Private Link types, NCC, exfiltration protection, CIDR sizing — crisp answers.
- **11.3 — Defending trade-offs & cost conversations:** how to justify a design,
  handle the follow-up probes, and talk cost (NAT, Private Endpoint, firewall).

### Stage 12 — Customer-Facing Collateral
- **12.1 — Sizing & architecture decision guide:** CIDR/subnet sizing + topology
  selection a customer can act on.
- **12.2 — Customer-ready security & networking overview:** the "is Databricks
  secure?" one-pager grounded in the platform's controls.
- **12.3 — Deployment & hardening checklist:** the pre-go-live checklist (SCC,
  VNet injection, Private Link, NCC, CMK, IP access lists, audit logging, IaC).

---

## Sequencing guidance

- **Linear path:** L0 → L1 → L2 → L3 → L4a, with L4b woven in after L1 (security
  doesn't have to wait for advanced networking).
- **For an interview crunch:** L1 (architecture), M2.1–M2.3 (VNet injection +
  SCC), M3.1–M3.2 (Private Link + DNS), M4a.2 (NCC), M4b.1/M4b.3/M4b.4 (identity,
  UC, encryption), L5 (synthesis).
- **One lesson at a time:** when the user asks for a single topic, locate it in
  this map, teach its sub-topics deeply, and reference the neighboring modules so
  the learner sees where it fits in the three-path scaffold (M1.2).
