#!/usr/bin/env python3
"""
Generate a *scanned* Unity Airways fare-rule sheet as a raster image (PNG + TIFF).

Why this file exists: the clean PDFs in `pdf/` carry a real text layer, so
`ai_parse_document` reads them without OCR. This script rasterizes a fare-rule
sheet to an image with NO text layer and adds scan artifacts (grayscale, skew,
grain, blur), so parsing it on Databricks exercises `ai_parse_document`'s
**OCR path** — the "scanned fare-rule sheet" case called out in 03-8.

Usage:   python3 sample-docs/generate_scan.py
Requires: Pillow   (pip install pillow)
Outputs:  sample-docs/scanned/fare-rules-scanned.png  (+ .tiff)
"""
from pathlib import Path
import random
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance, ImageChops

HERE = Path(__file__).resolve().parent
OUT = HERE / "scanned"
OUT.mkdir(exist_ok=True)
random.seed(7)  # deterministic output

# A4 at ~150 DPI
W, H = 1240, 1754
MARGIN = 96
INK = 20  # near-black on the grayscale scan

FONT = "/System/Library/Fonts/Supplemental/Arial.ttf"
FONT_B = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
def font(size, bold=False):
    try:
        return ImageFont.truetype(FONT_B if bold else FONT, size)
    except OSError:
        return ImageFont.load_default()

TABLE = [
    ["Fare family", "Class codes", "Change fee", "Refundable", "Free bags"],
    ["Basic Economy", "E, N", "n/a (no changes)", "No", "0"],
    ["Main Economy", "Y B M Q H K", "$0 (+ fare diff)", "Credit", "1"],
    ["Premium Economy", "P, A", "$0 (+ fare diff)", "Credit", "2"],
    ["Business", "J, C, D", "$0", "Yes", "2"],
    ["First", "F", "$0", "Yes", "3"],
]
NOTES = [
    "Fare class Q is a discounted Main Economy fare: 1 free checked bag; first extra bag $35 online.",
    "Basic Economy is non-refundable and non-changeable after the 24-hour risk-free window.",
    "Change fees were eliminated on Main Economy and above; you pay only the fare difference.",
    "Tickets are valid for 12 months from the date of issue.",
]

def render_sheet() -> Image.Image:
    img = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(img)
    x = MARGIN
    y = MARGIN

    d.text((x, y), "UNITY AIRWAYS", font=font(40, bold=True), fill=(INK, INK, INK)); y += 54
    d.text((x, y), "FARE RULES — QUICK REFERENCE SHEET", font=font(26, bold=True), fill=(INK, INK, INK)); y += 40
    d.text((x, y), "Document UA-POL-03A   ·   Effective 1 January 2026   ·   Unity Airways (UA) flights",
           font=font(18), fill=(70, 70, 70)); y += 30
    d.line((x, y, W - MARGIN, y), fill=(INK, INK, INK), width=3); y += 30

    # table
    cols = [x, x + 300, x + 560, x + 820, x + 1000, W - MARGIN]
    row_h = 62
    hdr = font(19, bold=True)
    cell = font(18)
    for r, row in enumerate(TABLE):
        ry = y + r * row_h
        if r == 0:
            d.rectangle((cols[0], ry, cols[-1], ry + row_h), fill=(232, 232, 238))
        # row borders
        d.rectangle((cols[0], ry, cols[-1], ry + row_h), outline=(INK, INK, INK), width=2)
        for c in range(len(row)):
            d.line((cols[c], ry, cols[c], ry + row_h), fill=(INK, INK, INK), width=2)
            d.text((cols[c] + 12, ry + 20), row[c], font=(hdr if r == 0 else cell), fill=(INK, INK, INK))
    y = y + len(TABLE) * row_h + 44

    d.text((x, y), "Notes", font=font(22, bold=True), fill=(INK, INK, INK)); y += 38
    for n in NOTES:
        d.text((x + 8, y), "•  " + n, font=font(18), fill=(35, 35, 35)); y += 34

    y = H - MARGIN - 30
    d.line((x, y, W - MARGIN, y), fill=(150, 150, 150), width=1); y += 12
    d.text((x, y), "Unity Airways is a fictional airline for Databricks GenAI training. Illustrative only — not a real policy.",
           font=font(14), fill=(120, 120, 120))
    return img

def scanify(img: Image.Image) -> Image.Image:
    g = img.convert("L")                                   # grayscale like a photocopier
    # Light paper grain: mostly-white noise (232..255) multiplied in, so it only
    # lightly mottles the page and never darkens the background toward black.
    grain = Image.effect_noise((W, H), 16).point(lambda p: 232 + p * 23 // 255)
    g = ImageChops.multiply(g, grain)                      # text stays dark, paper stays light
    g = ImageEnhance.Contrast(g).enhance(1.12)             # a touch punchier / photocopied
    g = ImageEnhance.Brightness(g).enhance(0.99)
    g = g.filter(ImageFilter.GaussianBlur(0.6))            # slight softness of a scan
    g = g.rotate(-1.4, expand=False, resample=Image.BICUBIC, fillcolor=248)  # skewed feed
    return g

if __name__ == "__main__":
    scanned = scanify(render_sheet())
    png = OUT / "fare-rules-scanned.png"
    tif = OUT / "fare-rules-scanned.tiff"
    scanned.save(png, "PNG", dpi=(150, 150))
    scanned.save(tif, "TIFF", dpi=(150, 150))
    print(f"  wrote {png.relative_to(HERE.parent)}  ({png.stat().st_size:,} bytes)")
    print(f"  wrote {tif.relative_to(HERE.parent)}  ({tif.stat().st_size:,} bytes)")
    print("  No text layer — parsing this on Databricks exercises ai_parse_document's OCR path.")
