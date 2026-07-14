#!/usr/bin/env python3
"""
Generate the Unity Airways policy PDFs from the Markdown sources in this folder.

These PDFs are the raw RAG source corpus for Module 03 (`ai_parse_document` in
`03-8-ai-parse-extract.py` and `03-9-sdp-ingestion.py`) and, downstream, Module 04.

Usage (from the repo root or this folder):
    python3 sample-docs/generate_pdfs.py

Requires: markdown, weasyprint   (pip install markdown weasyprint)
Outputs:  sample-docs/pdf/*.pdf   (one PDF per *.md, excluding README.md)
"""
from pathlib import Path
import markdown
from weasyprint import HTML

HERE = Path(__file__).resolve().parent
OUT = HERE / "pdf"
OUT.mkdir(exist_ok=True)

# Professional airline-policy-document styling (print/A4).
CSS = """
@page { size: A4; margin: 22mm 20mm; }
* { box-sizing: border-box; }
body { font-family: "Helvetica Neue", Arial, sans-serif; color: #1a1a1a; font-size: 10.5pt; line-height: 1.5; }
h1 { color: #14143c; font-size: 20pt; margin: 0 0 4px; border-bottom: 3px solid #2b2bf0; padding-bottom: 8px; }
h2 { color: #14143c; font-size: 13pt; margin: 20px 0 6px; }
h3 { color: #333; font-size: 11pt; margin: 14px 0 4px; }
p { margin: 6px 0; }
strong { color: #14143c; }
blockquote { border-left: 3px solid #2b2bf0; background: #f4f4fb; margin: 10px 0; padding: 8px 14px; color: #333; }
ul { margin: 6px 0 6px 4px; padding-left: 20px; }
li { margin: 3px 0; }
table { border-collapse: collapse; width: 100%; margin: 10px 0; font-size: 9.5pt; }
th, td { border: 1px solid #c9c9d6; padding: 6px 9px; text-align: left; vertical-align: top; }
th { background: #14143c; color: #fff; font-weight: 600; }
tr:nth-child(even) td { background: #f6f6fb; }
code { background: #eee; padding: 1px 4px; border-radius: 3px; font-family: "Courier New", monospace; font-size: 9.5pt; }
.footer { margin-top: 26px; padding-top: 8px; border-top: 1px solid #ccc; color: #888; font-size: 8pt; }
"""

FOOTER = ('<div class="footer">Unity Airways is a fictional airline created for Databricks GenAI '
          "training and demos. This document is illustrative and not a real airline policy.</div>")

def build():
    md = markdown.Markdown(extensions=["tables", "sane_lists", "attr_list"])
    sources = sorted(p for p in HERE.glob("*.md") if p.name.lower() != "readme.md")
    if not sources:
        print("No source .md files found next to this script.")
        return
    for src in sources:
        md.reset()
        html_body = md.convert(src.read_text(encoding="utf-8"))
        html_doc = (f"<html><head><meta charset='utf-8'><style>{CSS}</style></head>"
                    f"<body>{html_body}{FOOTER}</body></html>")
        out_pdf = OUT / (src.stem + ".pdf")
        HTML(string=html_doc, base_url=str(HERE)).write_pdf(str(out_pdf))
        print(f"  {src.name:38s} ->  pdf/{out_pdf.name}  ({out_pdf.stat().st_size:,} bytes)")
    print(f"\nDone. {len(sources)} PDFs written to {OUT}")

if __name__ == "__main__":
    build()
