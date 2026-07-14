# Databricks notebook source
# MAGIC %md
# MAGIC # Upload the Unity Airways sample docs into a UC Volume
# MAGIC **Companion to Module 03** · loads the `sample-docs/` corpus so `03-8-ai-parse-extract.py` and
# MAGIC `03-9-sdp-ingestion.py` have documents to parse. Run this once; then run the Module 03 notebooks.
# MAGIC
# MAGIC ## What it does
# MAGIC 1. Creates the target catalog/schema **Volume** (if missing).
# MAGIC 2. Copies the generated **PDFs** (`sample-docs/pdf/*.pdf`) and, optionally, the **scanned image**
# MAGIC    (`sample-docs/scanned/fare-rules-scanned.png`) into that Volume.
# MAGIC 3. Lists the Volume so you can confirm the upload.
# MAGIC
# MAGIC ## Prerequisites (read before running)
# MAGIC - **This repo must be checked out as a Databricks Git folder** (Workspace → Repos / Git folders), so
# MAGIC   the `sample-docs/` files exist in the workspace next to this notebook. (If you uploaded the files
# MAGIC   some other way, set `SOURCE_DIR` in Step 1 to wherever `pdf/` and `scanned/` live.)
# MAGIC - **Compute:** serverless notebook, or a DBR‑ML cluster. "Files in workspace" must be enabled (default).
# MAGIC - **Unity Catalog:** the catalog **`unity_airways`** must exist and you need **CREATE VOLUME** +
# MAGIC   write access on schema **`rag`**. Change the identifiers below if you use a different location.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 0. Configuration
# MAGIC Pick the **target** to match the notebook you'll run next:
# MAGIC - `"parse"`   → Volume `policy_docs`  → path `03-8-ai-parse-extract.py` reads
# MAGIC - `"pipeline"`→ Volume `landing` (subfolder `policies/`) → path `03-9-sdp-ingestion.py` reads
# MAGIC
# MAGIC Set `INCLUDE_SCAN = True` to also upload the scanned image (exercises the `ai_parse_document` **OCR** path).

# COMMAND ----------

CATALOG = "unity_airways"   # must already exist; change to a catalog you own
SCHEMA  = "rag"             # schema you can write to

TARGET  = "parse"           # "parse" (for 03-8) or "pipeline" (for 03-9)
INCLUDE_SCAN = True         # also upload sample-docs/scanned/fare-rules-scanned.png (OCR path)

# Resolve the Volume + optional subfolder from TARGET.
if TARGET == "pipeline":
    VOLUME, SUBPATH = "landing", "policies/"          # 03-9 reads /Volumes/.../landing/policies/
elif TARGET == "parse":
    VOLUME, SUBPATH = "policy_docs", ""               # 03-8 reads /Volumes/.../policy_docs/
else:
    raise ValueError("TARGET must be 'parse' or 'pipeline'")

VOLUME_PATH = f"/Volumes/{CATALOG}/{SCHEMA}/{VOLUME}/{SUBPATH}"
print("Target Volume path:", VOLUME_PATH)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Locate the `sample-docs/` source files
# MAGIC In a Git folder the notebook's directory is the working directory, so `pdf/` and `scanned/` sit
# MAGIC right here. We try the working dir, then the notebook's workspace path, then fall back to a manual
# MAGIC override. If detection fails, set `SOURCE_DIR` to the absolute workspace path of `sample-docs/`.

# COMMAND ----------

import os
from pathlib import Path

SOURCE_DIR = None   # e.g. "/Workspace/Repos/you@databricks.com/genai-course/sample-docs" — set only if auto-detect fails

def _candidates():
    if SOURCE_DIR:
        yield Path(SOURCE_DIR)
    # 1) current working dir (notebook folder when running from a Git folder)
    yield Path.cwd()
    # 2) the notebook's own workspace path -> /Workspace/<path>/.. (parent folder)
    try:
        ctx = dbutils.notebook.entry_point.getDbutils().notebook().getContext()
        nb = ctx.notebookPath().get()                 # e.g. /Repos/you/genai-course/sample-docs/upload_to_volume
        yield Path("/Workspace" + nb).parent
    except Exception:
        pass

BASE = None
for c in _candidates():
    if (c / "pdf").is_dir():
        BASE = c
        break

assert BASE is not None, (
    "Could not find the sample-docs folder (no 'pdf/' subdir found). "
    "Set SOURCE_DIR above to the absolute workspace path of sample-docs/ and re-run."
)
SRC_PDF  = BASE / "pdf"
SRC_SCAN = BASE / "scanned"
print("Source folder :", BASE)
print("PDFs found    :", len(list(SRC_PDF.glob('*.pdf'))))
print("Scan present  :", (SRC_SCAN / 'fare-rules-scanned.png').exists())

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Create the schema and Volume (idempotent)

# COMMAND ----------

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")
spark.sql(f"CREATE VOLUME IF NOT EXISTS {CATALOG}.{SCHEMA}.{VOLUME}")
# Make the subfolder (for the 03-9 'pipeline' target); harmless when SUBPATH is empty.
os.makedirs(VOLUME_PATH, exist_ok=True)
print("Ready:", VOLUME_PATH)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Copy the documents into the Volume
# MAGIC Writes straight to the `/Volumes/...` path with `shutil` (works on serverless and classic clusters).
# MAGIC Re-running overwrites the same files, so this is safe to repeat.

# COMMAND ----------

import shutil

sources = sorted(SRC_PDF.glob("*.pdf"))
if INCLUDE_SCAN:
    scan = SRC_SCAN / "fare-rules-scanned.png"   # swap to .tiff if you prefer
    if scan.exists():
        sources.append(scan)

assert sources, f"No source files found under {BASE}. Did you generate the PDFs (generate_pdfs.py)?"

copied = 0
for s in sources:
    dst = f"{VOLUME_PATH}{s.name}"
    shutil.copy2(str(s), dst)
    print(f"  copied  {s.name:34s} -> {dst}")
    copied += 1
print(f"\n{copied} file(s) uploaded to {VOLUME_PATH}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Verify the upload

# COMMAND ----------

files = dbutils.fs.ls(VOLUME_PATH)
for f in files:
    print(f"  {f.name:36s} {f.size:>10,} bytes")
assert len(files) > 0, f"Nothing landed in {VOLUME_PATH} — check the source folder and permissions."
print(f"\nOK — {len(files)} file(s) in the Volume. Module 03 can now parse them.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Next steps
# MAGIC - **`TARGET = "parse"`** → open **`notebooks/03-data-prep-chunking/03-8-ai-parse-extract.py`** and run it
# MAGIC   (its `VOLUME = "policy_docs"` now has documents). The scanned PNG, if uploaded, drives the **OCR** path.
# MAGIC - **`TARGET = "pipeline"`** → attach **`notebooks/03-data-prep-chunking/03-9-sdp-ingestion.py`** to a
# MAGIC   Lakeflow Declarative Pipeline; Auto Loader will pick these files up from `landing/policies/`.
# MAGIC - Either path lands `unity_airways.rag.ua_rag_chunks`, which **Module 04** then indexes.
# MAGIC
# MAGIC > 💡 Re-run with the other `TARGET` (and `INCLUDE_SCAN` toggled) to stage both locations.
