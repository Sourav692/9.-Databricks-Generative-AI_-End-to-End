#!/usr/bin/env python3
"""Search / extract text from the project PDF books to ground explanations.

Requires `pdftotext` (poppler; already available on this machine). Run from the
project root so relative `books/...` paths resolve.

Usage:
  python3 pdf_text.py "books/<book>.pdf"                  # dump front matter (pages 1-12) for TOC / chapter discovery
  python3 pdf_text.py "books/<book>.pdf" "<search term>"  # find pages containing the term + matching lines

Workflow: use this to LOCATE the page(s), then use the built-in Read tool on the
PDF with that page range to read full context before teaching. Keeps the
'no hallucination' rule honest: find the source, read it, then explain.
"""
import sys, subprocess, shutil


def pages(pdf):
    if not shutil.which("pdftotext"):
        sys.exit("ERROR: pdftotext (poppler) not found. Install: brew install poppler — "
                 "or just use the Read tool on the PDF directly with a page range.")
    r = subprocess.run(["pdftotext", "-layout", pdf, "-"], capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("pdftotext failed: " + (r.stderr or "").strip())
    return r.stdout.split("\f")  # poppler separates pages with form-feed


def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    pdf = sys.argv[1]
    pg = pages(pdf)
    term = sys.argv[2].lower() if len(sys.argv) > 2 else None
    print(f"[{pdf}] {len(pg)} pages\n")

    if not term:
        print("=== Front matter (pages 1-12) for TOC / chapter discovery ===\n")
        for i, p in enumerate(pg[:12], start=1):
            t = " ".join(p.split())
            if t:
                print(f"--- page {i} ---\n{t[:1500]}\n")
        return

    hits = 0
    for i, p in enumerate(pg, start=1):
        if term in p.lower():
            hits += 1
            print(f"================= page {i} =================")
            for line in p.splitlines():
                if term in line.lower():
                    print("  …", line.strip())
            if hits >= 12:
                print("\n... (more matches; refine the term or open the reported pages with Read) ...")
                break
    if hits == 0:
        print(f"No pages matched '{term}'. Try a broader term, or run with no term to see the front matter/TOC.")
    else:
        print(f"\n>>> Matched {hits}+ page(s). Use the Read tool on those page numbers for full context.")


if __name__ == "__main__":
    main()
