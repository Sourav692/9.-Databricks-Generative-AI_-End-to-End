# Compliance Rubric — derived from databricks-netsec-tutor

This is the standing checklist the reviewer uses for **Check 2**. Always prefer
the **live** `databricks-netsec-tutor/SKILL.md` (rules change); use this file as
the mapping guide and as a fallback when the tutor skill can't be located. When
you fall back to this cached rubric, say so in the report.

## How to use

1. Read the tutor `SKILL.md` + its `references/` (including `curriculum.md`,
   `html-template.md`, `lab-and-config-conventions.md`,
   `verification-checklist.md`).
2. For each rule below, decide **Pass / Fail / N/A** against the artifact.
3. Give evidence (a quote or `file:line`) for Pass; a precise gap for Fail.
4. Mark **N/A** with a reason when a rule doesn't apply to the artifact type
   (e.g. SQL-convention rules when reviewing a pure-Terraform infra artifact).

## Rubric items

### A. Teaching style & structure
- **A1 — Simple-first:** plain-language explanation precedes technical depth.
- **A2 — Jargon defined:** each unavoidable term gets a one-sentence plain
  definition before use. Networking is jargon-dense — CIDR, NSG, UDR, NAT, SNAT,
  FQDN, RFC 1918, SCC, NPIP, NCC, and the Private Endpoint vs Service Endpoint vs
  Private Link distinction must each be defined on first use.
- **A3 — Required sections:** What it is → Why it matters → How it works (trace
  the traffic path / control mechanism) → How to configure it (Portal + IaC/CLI)
  → comparison table (where useful) → uses/edge-cases/limitations → common
  mistakes/gotchas → references.
- **A4 — Bullets & headings:** clear headings/subheadings; bullets used where
  they improve clarity.
- **A5 — Comparison table and/or gotchas** present when the topic warrants
  (e.g. Service Endpoint vs Private Endpoint; default VNet vs VNet injection).
- **A6 — Sub-topic decomposition & depth:** the topic is broken into its
  sub-topics, each with its own subheading and a genuine deep dive (traffic path
  / mechanism + *why* + trade-off), not a one-line skim. A shallow lesson that
  only states definitions without tracing how traffic flows or what the control
  does → Fail.
- **A7 — Trivia pruned:** depth is spent on enterprise-relevant mechanics, not
  exhaustive parameter dumps, deprecated setups, or deep AWS/GCP detail.
- **A8 — Architect altitude (FDE/RSA):** the lesson reads at architect altitude —
  it explains *what's happening and why*, *why an issue occurs* (cause→effect), and
  gives the customer talk-track, rather than operator-grade build detail. Pure
  network-engineer minutiae (argument-by-argument IaC, every NSG/UDR flag) that an
  architect wouldn't carry into a customer room → should be trimmed or deferred to
  the hands-on artifact. A lesson pitched at hands-on-operator depth → Fail (major).

### B. Accuracy (BLOCKING)
- **B1 — No invented features/args/ports/DNS-zones/service-tags/UI paths.**
- **B2 — Doc grounding:** version-sensitive claims cite a specific
  `learn.microsoft.com/azure/databricks` (Azure-first), `learn.microsoft.com/azure`,
  or `docs.databricks.com` page.
- **B3 — Uncertainty flagged:** anything unconfirmed is explicitly marked, not
  asserted as fact — especially **GA-vs-Preview status, regional availability,
  ports, CIDR limits, and tier requirements**.
- **B4 — Sources distinguished:** official docs vs. third-party clearly labeled.

### C. Current names, scope & best practices
- **C1 — Current names:** Microsoft Entra ID (not AAD); workspace storage (not
  DBFS root); SCC / No Public IP; NCC; Unity Catalog; Lakeflow naming. Deprecated
  names flagged or mapped.
- **C2 — Azure-first scope:** terms, diagrams, and citations default to Azure
  (VNet/NSG/UDR/Private Endpoint/Entra ID/ADLS). AWS/GCP terms appear only as an
  explicit ≤1-line aside, never as the lesson's actual setup. Wrong-cloud terms
  used as the real architecture → Fail.
- **C3 — UC & storage best practice:** Unity Catalog + external locations + ADLS
  Gen2 over DBFS mounts / workspace-storage root for governed data.
- **C4 — Recommended baselines:** SCC + VNet injection for classic; NCC for
  serverless; back-end Private Link, IP access lists, CMK, SCIM+SSO where relevant.

### CC. Configuration examples (BLOCKING for teaching artifacts) — see SKILL.md "Required: configuration examples"
- **CC1 — Illustrative config present:** every markdown and HTML teaching artifact
  includes real config; each subtopic with a config surface (IaC / CLI / NSG rule /
  UDR / DNS record / SQL grant) shows **one representative, commented** snippet
  rather than prose only. Missing config on a config-bearing topic → Fail. But the
  lesson should NOT dump full apply-ready modules inline — that belongs in the
  hands-on artifact (see A8 altitude).
- **CC2 — Real-shaped & commented:** snippets reflect production patterns (subnet
  delegation, NSG association, route table + UDR, Private Endpoint + Private DNS
  Zone group, `no_public_ip`, NCC binding, real grants) and comment the non-obvious
  lines — but, in the lesson body, kept to the illustrative lines that teach the
  point. Full apply-ready depth lives in the hands-on artifact.
- **CC3 — Portal path AND IaC where both help:** the exact Azure Portal / Account
  Console click-path is shown alongside the IaC/CLI for hands-on topics.
- **CC4 — Config accuracy:** no invented Terraform args, Bicep types, REST
  fields, CLI flags, ports, or DNS names; UC SQL uses 3-level names; everything
  verifiable against docs (ties to B1).
- **CC5 — Cost called out:** where a config carries real Azure cost (NAT egress,
  Private Endpoint per-GB, Azure Firewall, extra hops), it's noted.

### CF. FDE field notes (BLOCKING for teaching artifacts) — see SKILL.md "Required: FDE field notes"
- **CF1 — Present:** every markdown and HTML lesson includes a clearly-labelled
  "FDE field notes" block. Missing on a teaching lesson → Fail (major).
- **CF2 — Substance:** it covers common customer asks, a positioning talk-track,
  what breaks in the field **plus the first diagnostic check** (not just the
  symptom), and an engagement decision rule (tier/cost/regulatory). A vague block
  that just restates the concept → Fail.

### MM. Mental model (BLOCKING for teaching artifacts) — see SKILL.md "Required: mental model"
- **MM1 — Present near top:** a labelled "Mental model" callout appears before the
  deep dive, with a dominant analogy + a one-sentence "hold this in your head"
  takeaway + where it sits in the 3-path scaffold. Missing → Fail (major).

### TG. Define-before-use terms (BLOCKING for teaching artifacts) — see SKILL.md "Required: define prerequisite terms before first use"
- **TG1 — No undefined jargon:** every networking/Azure/Databricks term not taught
  in an EARLIER module gets a 2–3 line gloss at/just before first use (inline or in
  a "Terms used here" box). A term used cold (e.g. NIC/NSG/gateway/SNAT/FQDN with
  no gloss) → Fail.
- **TG2 — Cross-referenced:** borrowed terms point to the module that owns the deep
  dive (forward or back reference), so the learner knows where the depth lives.

### DG. Architectural diagrams (BLOCKING for teaching artifacts) — see SKILL.md "Required: architectural diagrams"
- **DG1 — Interactive architecture per subtopic:** the HTML has a genuinely
  architectural interactive diagram for **each subtopic** (at least one per topic),
  built in the reference "architect view" style (data-driven SVG nodes, click/hover
  → an info panel with the *what + why*, switchable views / step-through / tree) —
  not just an input widget. Missing, or only one shallow diagram for a
  multi-subtopic page → Fail.
- **DG2 — Embedded static SVG:** a standalone `*.svg` architecture image exists in
  the lesson folder AND is embedded in the HTML via `<img>`. Missing SVG → Fail.
  PNG is optional (best-effort) — its absence is never a finding.
- **DG3 — Azure-labelled & accurate:** diagram components are real Azure-first
  labels (VNet, host/container subnet, NSG, SCC relay, Private Endpoint, control
  plane, ADLS…) and match the lesson's described path.

### D. Scope
- **D1 — On-topic & Azure-first:** content matches the requested
  networking/security topic; no out-of-scope filler; cloud defaults to Azure.
  (If the request defined exclusions, confirm they're respected.)

### E. Artifact order & format (per the tutor's "Artifact creation order")
- **E1 — Order:** markdown first → HTML second → hands-on artifact last.
- **E2 — Hands-on conditional & right-typed:** the hands-on artifact is created
  only when it adds value, the decision is stated, and the type fits the topic
  (IaC + Portal/CLI runbook for infra; SQL/SDK for governance/audit) — NOT a
  forced Spark notebook for a pure-networking topic.
- **E3 — Granularity (ONE page per topic):** exactly one `lesson.md` + one
  `index.html` per topic (module), with subtopics as sections/tabs — NOT separate
  per-subtopic files. Hands-on: 1–2 per topic covering its subtopics, not one per
  subtopic. Separate HTML/md per subtopic → Fail.
- **E4 — No-artifact fallback:** when none is warranted, the markdown lays out
  step-by-step **Azure Portal / Account Console / CLI** actions instead.

### F. IaC / CLI / runbook conventions (N/A if none) — see lab-and-config-conventions.md
- **F1 — Header block:** goal, prerequisites (RG/subscription, RBAC roles,
  region co-location, account vs workspace scope), what it provisions, cost
  caveats.
- **F2 — Correct providers/resources:** `azurerm` + `databricks` Terraform
  providers (version-pinned) or Bicep/ARM; verified resource/argument names.
- **F3 — Parameterized & portable:** variables for subscription/region/CIDR/
  workspace; realistic CIDRs.
- **F4 — Commented & enterprise-shaped:** non-obvious lines explained; production
  patterns over toys.
- **F5 — Irreversible/downtime steps flagged** in runbooks (e.g. VNet-injection
  or CIDR choices fixed post-deploy).

### G. HTML conventions (N/A if no HTML) — see html-template.md
- **G1 — Self-contained:** inline CSS/JS, opens standalone in a browser.
- **G2 — Interactive diagram(s):** at least one, and more when the concept
  warrants (topology, traffic-path step-through, DNS before/after, endpoint
  compare); not capped at one.
- **G3 — Multiple-diagram hygiene:** each diagram's CSS/JS scoped to its own
  container (no ID/handler collisions).
- **G4 — Matches lesson sections; references section links cited docs (Azure-first).**

### H. Markdown conventions (N/A if no markdown)
- **H1 — Headings/sections** mirror the lesson.
- **H2 — Mermaid topology / traffic-path diagram** included where possible (or
  Portal/CLI steps when no IaC artifact).

### I. Tone
- **I1 — Patient, precise, practical; correctness over completeness; not
  condescending, not oversimplified-to-wrong.**

## Severity mapping (feeds the verdict)
- **Blocking (→ 🔴 Needs revision):** any B-item failure; A3 (required structure)
  failure on a teaching lesson; **A6 (no sub-topic depth — shallow/skim lesson);
  CC1 (no illustrative config on a config-bearing topic) or CC4 (inaccurate/invented
  config); C2/D1 (lesson is not Azure-first / wrong-cloud architecture); E3
  (per-subtopic files instead of one consolidated page per topic); DG1 (no
  per-subtopic interactive architecture diagram).**
- **Major (→ 🟡 at least):** outdated primary product name unflagged or
  wrong-cloud term (C1/C2); other E-item failures (incl. forced notebook for infra);
  missing/embedded SVG (DG2); **A7 (trivia bloat), A8 (wrong altitude —
  operator-grade instead of architect), CC2/CC3/CC5 (toy config / missing Portal
  path / missing cost note).**
- **Minor (→ 🟡):** tone (I1), bullets/headings (A4), cosmetic gaps.
- **Clean on Check 1 + Check 2 ⇒ ✅ Approved.**
