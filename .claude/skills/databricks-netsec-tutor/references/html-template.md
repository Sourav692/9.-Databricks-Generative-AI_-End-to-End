# Self-Contained HTML Lesson Page (Networking & Security)

When the user accepts the HTML offer, produce a single standalone `index.html`
**for the whole topic (module)** — one page covering all its subtopics as
tabs/sections — that opens directly in a browser with no external build step.
**Do not create a separate HTML file per subtopic.** Model it on the project's
gold-standard **architect view**, `zerobus-ingest-architect-view.html` (in the
project root): a tabbed layout, a data-driven interactive SVG architecture
diagram, Databricks branding, mental-model + callouts, decision cards, and a
customer-questions section. Open that file and reuse its structure.

## Requirements

- **Architect-altitude, clear, and illustratively config-rich (not a docs
  replacement, not shallow)**: the page explains each subtopic so an FDE/RSA can
  say *what's happening and why* — traffic path + control + trade-off + *why it
  breaks* — at the depth a customer security architect expects, without
  operator-grade build detail. Cut trivia, rare flags, and argument-by-argument
  IaC; keep the understanding. Bullets carry substance; short paragraphs connect
  them. (Same altitude as the lesson — see SKILL.md "Audience & altitude" and
  "Depth & clarity".)
- **Subtopic tabs/sections**: present each subtopic as its own tab or `<section>`
  (mirror the reference example's tabbed nav) with a heading, the what/why +
  traffic path, its interactive diagram, and an illustrative config snippet — one
  consolidated page, not separate files.
- **Illustrative configuration is required** (see SKILL.md "Required: illustrative
  configuration"): each subtopic with a config surface shows **one representative,
  commented** snippet in a `<pre><code>` block — Terraform (`hcl`), Bicep/ARM,
  `az`/Databricks CLI (`bash`), SQL, or a REST/JSON body — **plus the Azure Portal
  click-path**. Show the lines that teach the point, not the whole module; push
  full apply-ready IaC to the hands-on artifact. Don't describe a setting in prose
  when a short snippet shows it more clearly.
- **Analogy + real-world use case per feature**: each feature/concept card
  should carry a one-line analogy and a concrete "when you'd use it" scenario.
- **Architect-framing blocks** (model on the reference example): a **decision
  block** ("pick it when / don't pick it when" cards), a short **customer talk-track
  / one-liner**, and **2–3 questions to ask the customer** before recommending it.
  These render the FDE field notes visually and keep the page at architect altitude.
- **Uses, edge cases & limitations**: every feature must include a short block on
  uses (when to use / when not), key edge cases (IP exhaustion, custom DNS, cost,
  GA-vs-Preview), and honest limitations (see SKILL.md).
- **Fully self-contained**: all CSS and JS inline in the file. No external CSS/JS
  frameworks required to render. (A single CDN script is acceptable only for an
  interactive diagram library such as Mermaid; otherwise inline.)
- **Clean, readable, standalone**: proper `<h1>`/`<h2>` headings, sectioned
  content, comfortable typography, light background, max-width content column.
- **Matches the explanation**: same sections as the lesson (What it is, Why it
  matters, How it works / traffic path, How to configure, comparison table,
  gotchas, references).
- **An interactive architecture diagram for each subtopic** — **not capped at
  one**. Build them in the **reference style** (`zerobus-ingest-architect-view.html`):
  a **data-driven SVG** where nodes are defined in a small JS object (box + label
  + sublabel + colour) with arrows between them, **clicking/hovering a node updates
  an info panel** with the plain-English *what it is + why it's here*, and
  **buttons/tabs switch between alternative architectures**. Place each diagram in
  the section/tab it explains. Vary the form to fit the content:
  - **Switchable architecture views** (default VNet vs VNet-injection vs +Private
    Link) — the primary pattern, like the example's Zerobus/Kafka/Hybrid toggle.
  - **Clickable traffic-path** (click a hop — user → front-end PE → control plane →
    SCC relay → cluster — to reveal what happens and the control at that hop).
  - **Step-through** deployment progression; **expandable tree** (UC hierarchy, NCC
    structure); **tabbed compare** (Service vs Private Endpoint).
  - Each node's info text should answer **"what is this and why is it here"** in
    customer language, and (for failure-prone hops) **what breaks here and why**.
  - Keep each diagram's JS scoped to its own container so multiple diagrams coexist
    without ID/handler collisions.
- **Config samples**: syntax-highlight them, or at minimum present them in a
  clean dark monospace `<pre><code>` box with comfortable padding. A single CDN
  include for a highlighter (e.g. highlight.js) is acceptable; otherwise style a
  `.code` block inline. Label each block's language and add a one-line caption
  saying what it does. Show the IaC AND the Portal steps where both help. Use the
  contrast (insecure default vs hardened) where it teaches the trade-off.
- Include a **References** section linking the cited docs (Azure-first:
  learn.microsoft.com/azure/databricks, then docs.databricks.com).

## Minimal skeleton

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>TOPIC — Azure Databricks Networking & Security</title>
  <style>
    :root { --bg:#f7f8fa; --fg:#1b1f24; --accent:#ff3621; --azure:#0078d4;
            --card:#fff; --border:#e3e6ea; }
    body { margin:0; background:var(--bg); color:var(--fg);
           font:16px/1.6 -apple-system,Segoe UI,Roboto,sans-serif; }
    main { max-width:900px; margin:0 auto; padding:32px 20px 80px; }
    h1 { color:var(--accent); }
    h2 { border-bottom:2px solid var(--border); padding-bottom:4px; }
    section { background:var(--card); border:1px solid var(--border);
              border-radius:12px; padding:20px 24px; margin:18px 0; }
    table { border-collapse:collapse; width:100%; }
    th,td { border:1px solid var(--border); padding:8px 10px; text-align:left; }
    pre { background:#0d1117; color:#e6edf3; padding:14px; border-radius:8px;
          overflow:auto; }
    .caption { font-size:13px; color:#666; margin:4px 0 12px; }
    /* interactive traffic-path diagram */
    .hop { cursor:pointer; border:1px solid var(--border); border-radius:8px;
           padding:12px 14px; margin:8px 0; background:#fff; }
    .hop .detail { display:none; margin-top:8px; color:#444; }
    .hop.open .detail { display:block; }
    .hop .head { font-weight:600; }
  </style>
</head>
<body>
<main>
  <h1>TOPIC</h1>
  <p class="lede">One-line plain-language definition.</p>

  <section id="path">
    <h2>Traffic path (click each hop)</h2>
    <div class="hop" onclick="this.classList.toggle('open')">
      <div class="head">① User → Workspace (front-end)</div>
      <div class="detail">Browser/BI/REST reaches the workspace URL… control:
        front-end Private Link or IP access list…</div>
    </div>
    <div class="hop" onclick="this.classList.toggle('open')">
      <div class="head">② Cluster → Control plane (back-end, via SCC relay)</div>
      <div class="detail">No public IPs; outbound over the SCC relay; back-end
        Private Link removes the public hop…</div>
    </div>
    <div class="hop" onclick="this.classList.toggle('open')">
      <div class="head">③ Cluster → ADLS storage</div>
      <div class="detail">Service Endpoint (free, backbone) or Private Endpoint
        (private IP, per-GB cost)…</div>
    </div>
  </section>

  <section><h2>What it is</h2><p>…</p></section>
  <section><h2>Why it matters</h2><p>…</p></section>
  <section><h2>How it works</h2><p>… trace the call/packet …</p></section>
  <section><h2>How to configure it</h2>
    <p class="caption">Terraform (azurerm + databricks providers)</p>
    <pre><code>… commented HCL …</code></pre>
    <p class="caption">Azure Portal</p>
    <ol><li>Portal → … → blade → field …</li></ol>
  </section>
  <section><h2>Comparison</h2><table><!-- … --></table></section>
  <section><h2>Uses, edge cases &amp; limitations</h2><ul><li>…</li></ul></section>
  <section><h2>Common mistakes / gotchas</h2><ul><li>…</li></ul></section>
  <section><h2>References</h2><ul>
    <li><a href="https://learn.microsoft.com/azure/databricks/…">Azure ADB doc</a></li>
  </ul></section>
</main>
</body>
</html>
```

The skeleton above shows a minimal hop-toggle for brevity. **For the real lessons,
use the richer data-driven SVG pattern from `zerobus-ingest-architect-view.html`**
(nodes/arrows defined in a JS object, a `renderDiagram(key)` function, a
`switchDiagram()` to toggle views, and an info panel updated on node click/hover).
Add one such diagram per subtopic, interleaved with the section it supports, and
scope each diagram's CSS/JS to its own container so handlers don't collide.

Adapt each interactive piece to what it shows (switchable architecture views, a
step-through deployment progression, an expandable tree for the UC hierarchy/NCC,
a tabbed compare for two endpoint types). Keep them genuinely interactive — not
static images.

## Mental model callout (required, near the top)

Render the lesson's **mental model** as a distinct callout just under the lede,
before the deep dive. Example:

```html
<section class="mental-model">
  <h2>🧠 Mental model</h2>
  <p><b>Hold this in your head:</b> SCC is a callback — the cluster always dials
     <i>out</i> to the control plane, so there's never an inbound door to guard.</p>
  <p class="caption">Where it sits: secures path ② compute ↔ control (see 2.2).</p>
</section>
```
Style it distinctly (e.g. left border + tinted background) so it reads as the
"intuition box," not body text.

## Terms-used-here glossary box (define-before-use)

If the lesson borrows terms owned by other modules, add a small glossary box near
the top so the reader never hits an unexplained term. Each entry = the term, a
2–3 line gloss, and the owning module (forward or back reference).

```html
<section class="glossary">
  <h2>Terms used here</h2>
  <dl>
    <dt>NIC (network interface card)</dt>
    <dd>The virtual network adapter a VM/endpoint uses to get an IP on a subnet.
        → full context in <b>Stage 3.2</b>.</dd>
    <dt>NSG (network security group)</dt>
    <dd>A stateful allow/deny firewall attached to a subnet or NIC. → deep dive in
        <b>Stage 1.3</b>.</dd>
  </dl>
</section>
```
Alternatively use short inline parentheticals at first use — whichever keeps the
page readable. For pages borrowing several terms, prefer the box.

## Architecture diagram: interactive + embedded static SVG (required)

Beyond the interactive diagram(s), author a **standalone SVG** of the architecture
and embed it, so the lesson has a crisp static picture too:

```html
<section id="architecture">
  <h2>Architecture</h2>
  <!-- interactive version (clickable hops / step-through / tree) lives here -->
  <div class="diagram"> … interactive … </div>
  <!-- static, zoom-crisp SVG saved alongside the lesson -->
  <figure>
    <img src="architecture.svg" alt="Azure Databricks VNet-injection traffic path:
         user → front-end PE → control plane; cluster (no public IP) → SCC relay;
         cluster → ADLS via private endpoint" width="100%" />
    <figcaption class="caption">Static SVG — opens crisp at any zoom; also in the repo.</figcaption>
  </figure>
</section>
```

- Save the file as `architecture.svg` (or a descriptive name) in the **lesson
  folder**. Author it as hand-written SVG markup or render a Mermaid graph to SVG.
- Label real Azure components (VNet, host/container subnet, NSG, SCC relay,
  Private Endpoint, control plane, ADLS Gen2, NAT, Azure Firewall…).
- **PNG optional:** only add a `.png` (and an `<img>` to it, or a download link)
  if a renderer like `mmdc`/`rsvg-convert` is actually available. Never fabricate
  a binary. SVG alone satisfies the requirement.
- Keep the SVG self-contained (no external fonts/refs) so it renders offline.

## Markdown companion (when requested)

When the user also accepts the markdown offer, produce a `.md` file with the same
sections and a **mermaid** topology / traffic-path diagram. Keep it concise and
bullet-driven, and include the **uses, edge cases & limitations** block for each
feature (see SKILL.md). Example diagram:

````markdown
```mermaid
flowchart LR
  U[User / BI / REST] -->|front-end Private Link| CP[Control Plane]
  subgraph Customer VNet (VNet injection)
    direction TB
    H[Host subnet] --- C[Container subnet: clusters]
  end
  C -->|SCC relay, outbound, no public IP| CP
  C -->|Service / Private Endpoint| ADLS[(ADLS Gen2)]
  C -->|0.0.0.0/0 via UDR| FW[Azure Firewall hub]
```
````
