# Unity Airways — sample RAG document corpus

The **source documents** for the Module 03 → 04 RAG pipeline. Unity Airways is the fictional airline used across the whole curriculum; these are its customer-facing policy documents — exactly the kind of unstructured content a support RAG assistant answers from.

## What's here

| File | Policy | Answers questions like |
|---|---|---|
| `refunds-and-cancellations.*` | 24-hour rule, refundability by fare, involuntary refunds | *"Can I get a refund on a Basic Economy fare?"* |
| `baggage-policy.*` | Carry-on, checked allowance by fare, fees, fare class Q | *"Checked baggage allowance on Basic Economy?"*, *"baggage fee for fare class Q on flight UA-8842"* |
| `fare-rules.*` | Fare families, booking-class codes, change/refund matrix | *"What does Basic Economy allow?"* |
| `changes-and-rebooking.*` | Voluntary changes, IROPS, missed connections | *"Can I rebook for free if my connection is cancelled?"* |
| `checkin-and-boarding.*` | Check-in windows, cutoffs, boarding groups | *"Check-in cutoff for a domestic morning flight?"* |
| `faq.*` | Natural-language Q&A across all of the above | (great for retrieval demos) |

- **`*.md`** — the human-readable **source of truth** (edit these; everything else is generated).
- **`pdf/*.pdf`** — generated PDFs **with a real text layer**, the format `ai_parse_document` ingests directly (no OCR needed). Regenerate with `python3 sample-docs/generate_pdfs.py` (needs `markdown` + `weasyprint`).
- **`scanned/fare-rules-scanned.png` (+ `.tiff`)** — a **scanned fare-rule sheet**: a raster image with **no text layer**, plus skew/grain/blur artifacts. Parsing it forces `ai_parse_document` down its **OCR path** (the "scanned fare-rule sheet" case 03-8 calls out). Regenerate with `python3 sample-docs/generate_scan.py` (needs `Pillow`).

The content deliberately contains the exact facts the Module 03/04 notebooks query, so retrieval and the RAG chain return good, checkable answers.

### Exercising the OCR path
Drop `scanned/fare-rules-scanned.png` (or the `.tiff`) into the **same UC Volume** as the PDFs. `ai_parse_document` auto-detects it's an image, runs OCR, and returns text + layout exactly as it does for the PDFs — a good way to prove the pipeline handles native PDFs **and** scans. The clean `pdf/fare-rules.pdf` and this scan cover overlapping content, so add only one of them if you don't want duplicate chunks in the index.

## Which notebooks need these

- **`notebooks/03-data-prep-chunking/03-module-lab.py`** — **self-contained**; it ships its own inline sample text, so it runs with *no* files. Swap these in only if you want to exercise the real-file path.
- **`notebooks/03-data-prep-chunking/03-8-ai-parse-extract.py`** — parses files from a UC **Volume**. **Needs these PDFs.**
- **`notebooks/03-data-prep-chunking/03-9-sdp-ingestion.py`** — the Lakeflow pipeline; Auto Loader reads the same kind of Volume. **Needs these PDFs.**
- **Module 04** consumes whatever chunks Module 03 produces — no separate upload.

## Where to put them (upload to the UC Volume)

The notebooks expect a Volume under `unity_airways.rag`. Two paths are referenced — upload to whichever notebook you're running (or both):

| Notebook | Volume path |
|---|---|
| `03-8-ai-parse-extract.py` (`VOLUME = "policy_docs"`) | `/Volumes/unity_airways/rag/policy_docs/` |
| `03-9-sdp-ingestion.py` | `/Volumes/unity_airways/rag/landing/policies/` |

*(Change the catalog/schema/volume in the notebook's config cell if you use a different location.)*

### Option A — Databricks UI
Catalog Explorer → `unity_airways` → `rag` → create the Volume (`policy_docs` or `landing`) → **Upload to volume** → drop in the six files from `sample-docs/pdf/`.

### Option B — Databricks CLI (from the repo root)
```bash
# create the volume once (or let the notebook's CREATE VOLUME IF NOT EXISTS cell do it), then:
databricks fs mkdir  dbfs:/Volumes/unity_airways/rag/policy_docs
databricks fs cp --recursive --overwrite sample-docs/pdf dbfs:/Volumes/unity_airways/rag/policy_docs

# for the 03-9 pipeline path instead:
databricks fs cp --recursive --overwrite sample-docs/pdf dbfs:/Volumes/unity_airways/rag/landing/policies
```

### Option C — from inside a Databricks notebook
```python
# after cloning this repo into the workspace (or uploading the pdf/ folder):
dbutils.fs.mkdirs("/Volumes/unity_airways/rag/policy_docs")
# then upload the PDFs via the Volume UI, or dbutils.fs.cp from a workspace/DBFS staging path
```

## Note
These are **fictional, illustrative** documents for training and demos — not real airline policies. Keep them clearly labeled as such if you reuse them.
