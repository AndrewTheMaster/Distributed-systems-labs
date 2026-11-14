#!/usr/bin/env python3
"""Build the lab report: Markdown -> HTML -> PDF (Chrome headless), with a
table of contents that contains real page numbers and page numbering added
after rendering.

Inputs:  docs/report.md, docs/generated/tables.md, docs/img/*.png
Outputs: docs/report.html, docs/report.pdf
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import fitz  # PyMuPDF
import markdown

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
REPORT = DOCS / "report.md"
TABLES = DOCS / "generated" / "tables.md"
HTML = DOCS / "report.html"
PDF = DOCS / "report.pdf"

CSS = """
@page { size: A4; margin: 20mm 15mm 20mm 30mm; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body {
  font-family: "Times New Roman", Times, serif;
  font-size: 14pt;
  line-height: 1.5;
  color: #000;
  margin: 0;
  text-align: justify;
}
p { margin: 0; text-indent: 1.25cm; }
p.titlepage, .titlepage p { text-indent: 0; }
.titlepage { text-align: center; min-height: 240mm; position: relative; }
.titlepage p { margin: 0; text-align: center; font-size: 14pt; line-height: 1.4; }
.titlepage .ministry { margin-bottom: 0; }
.titlepage .ttl { font-size: 20pt; margin-top: 45mm; margin-bottom: 8mm; }
.titlepage .center { margin-top: 2mm; }
.titlepage .sign { text-align: left; margin-top: 60mm; margin-left: 85mm; }
.titlepage .sign p { text-align: left; }
.titlepage .city { position: absolute; bottom: 0; left: 0; right: 0; }
.toc-title { text-align: center; font-weight: bold; margin-bottom: 8mm; text-indent: 0; }
.toc-line { display: flex; align-items: baseline; margin: 0 0 3mm 0; text-indent: 0; text-align: left; }
.toc-line .t { flex: 0 1 auto; }
.toc-line .dots { flex: 1 1 auto; border-bottom: 1px dotted #000; margin: 0 3px 4px 4px; }
.toc-line .n { flex: 0 0 auto; }
h1 { font-size: 14pt; font-weight: bold; text-align: center; margin: 0 0 6mm 0; line-height: 1.5; page-break-after: avoid; }
h2 { font-size: 14pt; font-weight: bold; text-align: left; text-indent: 1.25cm; margin: 6mm 0 3mm 0; page-break-after: avoid; }
p.tcap { text-indent: 0; text-align: left; font-size: 12pt; margin: 4mm 0 2mm 0; page-break-after: avoid; }
p.caption { text-indent: 0; text-align: center; font-size: 12pt; margin: 2mm 0 6mm 0; }
p:has(> img) { text-indent: 0; text-align: center; margin: 4mm 0 0 0; page-break-after: avoid; }
img { display: block; margin: 0 auto; max-width: 100%; height: auto; }
ul, ol { margin: 2mm 0 2mm 0; padding-left: 1.25cm; }
li { margin: 0 0 1mm 0; text-indent: 0; }
table { border-collapse: collapse; width: 100%; margin: 1mm 0 4mm 0; font-size: 11pt; line-height: 1.25; page-break-inside: auto; }
tr { page-break-inside: avoid; }
th, td { border: 1px solid #000; padding: 1.2mm 1.8mm; vertical-align: top; text-align: left; text-indent: 0; }
th { font-weight: bold; text-align: center; }
td p { text-indent: 0; }
code { font-family: "Courier New", Courier, monospace; font-size: 11pt; }
pre { font-size: 10pt; }
hr { display: none; }
.pagebreak { page-break-before: always; }
a { color: #000; text-decoration: none; }
"""


def headings(md: str) -> list[str]:
    """Top-level headings of the report body, in order (for the TOC)."""
    body = md.replace("<!--TABLES-->", "")
    out = []
    for line in body.splitlines():
        if line.startswith("# "):
            out.append(line[2:].strip())
    return out


def toc_html(entries: list[str], pages: dict[str, int | str]) -> str:
    lines = []
    for title in entries:
        n = pages.get(title, "")
        lines.append(
            f'<div class="toc-line"><span class="t">{title}</span>'
            f'<span class="dots"></span><span class="n">{n}</span></div>'
        )
    return "\n".join(lines)


def render_html(md_text: str, tables_text: str, pages: dict[str, int | str]) -> str:
    entries = headings(md_text)
    body = md_text.replace("<!--TOC-->", toc_html(entries, pages))
    body = body.replace("<!--TABLES-->", tables_text)
    html_body = markdown.markdown(
        body,
        extensions=["tables", "sane_lists", "attr_list"],
        output_format="html5",
    )
    return (
        "<!doctype html>\n<html lang=\"ru\">\n<head>\n<meta charset=\"utf-8\">\n"
        "<title>Исследование методов распространения информации в распределённых системах</title>\n"
        f"<style>{CSS}</style>\n</head>\n<body>\n{html_body}\n</body>\n</html>\n"
    )


def find_chrome() -> str | None:
    candidates = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        shutil.which("google-chrome"),
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
    ]
    for c in candidates:
        if c and Path(c).exists():
            return c
    return None


def print_pdf(chrome: str) -> None:
    cmd = [
        chrome,
        "--headless",
        "--disable-gpu",
        "--no-sandbox",
        "--no-pdf-header-footer",
        "--run-all-compositor-stages-before-draw",
        "--virtual-time-budget=15000",
        f"--print-to-pdf={PDF.resolve()}",
        HTML.resolve().as_uri(),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 or not PDF.exists():
        print(result.stdout, file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        raise SystemExit("failed to generate PDF")


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def locate_headings(entries: list[str]) -> dict[str, int]:
    """Page number (1-based) where each top-level heading starts in the PDF."""
    doc = fitz.open(PDF)
    result: dict[str, int] = {}
    # Skip the title page and the table of contents page(s).
    start = 0
    for i, page in enumerate(doc):
        if "СОДЕРЖАНИЕ" in page.get_text():
            start = i + 1
    for title in entries:
        for i in range(start, len(doc)):
            lines = [norm(x) for x in doc[i].get_text().splitlines()]
            if norm(title) in lines:
                result[title] = i + 1
                break
    doc.close()
    return result


def add_page_numbers() -> None:
    """Page numbers bottom-centre; the title page is not numbered (as in the
    course template)."""
    doc = fitz.open(PDF)
    for i, page in enumerate(doc):
        if i == 0:
            continue
        label = str(i + 1)
        width = fitz.get_text_length(label, fontname="tiro", fontsize=12)
        x = page.rect.width / 2 - width / 2
        y = page.rect.height - 9 * 2.835  # 9 mm from the bottom edge
        page.insert_text((x, y), label, fontname="tiro", fontsize=12)
    tmp = PDF.with_suffix(".tmp.pdf")
    doc.save(tmp, garbage=3, deflate=True)
    doc.close()
    tmp.replace(PDF)


def main() -> None:
    if not REPORT.exists():
        raise SystemExit(f"missing {REPORT}")
    chrome = find_chrome()
    if not chrome:
        raise SystemExit("Chrome/Chromium not found; cannot render PDF")

    md_text = REPORT.read_text(encoding="utf-8")
    # Keep "NN %" together on one line (non-breaking space before the percent sign).
    md_text = re.sub(r"(\d) %", "\\1\u00a0%", md_text)
    tables_text = TABLES.read_text(encoding="utf-8") if TABLES.exists() else ""
    entries = headings(md_text)

    pages: dict[str, int | str] = {t: "" for t in entries}
    for attempt in range(3):
        HTML.write_text(render_html(md_text, tables_text, pages), encoding="utf-8")
        print_pdf(chrome)
        found = locate_headings(entries)
        new_pages = {t: found.get(t, "") for t in entries}
        if new_pages == pages:
            break
        pages = new_pages
    else:
        raise SystemExit("table of contents did not converge")

    add_page_numbers()
    print(f"wrote {HTML.relative_to(ROOT)}")
    print(f"wrote {PDF.relative_to(ROOT)} ({PDF.stat().st_size} bytes)")
    for t in entries:
        print(f"  {pages[t]:>3}  {t}")


if __name__ == "__main__":
    main()
