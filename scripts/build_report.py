#!/usr/bin/env python3
"""Build docs/report.pdf (Chrome, with TOC page numbers) and docs/report.docx (pandoc)
from docs/report.md."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import fitz  # PyMuPDF
import markdown

from docx_report import build as build_docx
from report_tables import inject

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
REPORT = DOCS / "report.md"
HTML = DOCS / "report.html"
PDF = DOCS / "report.pdf"
DOCX = DOCS / "report.docx"

CSS = """
@page { size: A4; margin: 20mm 15mm 20mm 30mm; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { font-family: "Times New Roman", Times, serif; font-size: 14pt; line-height: 1.5; color: #000; margin: 0; text-align: justify; }
p { margin: 0; text-indent: 1.25cm; }
.titlepage { text-align: center; min-height: 240mm; position: relative; }
.titlepage p { margin: 0; text-indent: 0; text-align: center; line-height: 1.4; }
.titlepage .ttl { font-size: 20pt; margin-top: 45mm; margin-bottom: 8mm; }
.titlepage .sign { text-align: left; margin-top: 60mm; margin-left: 85mm; }
.titlepage .sign p { text-align: left; }
.titlepage .city { position: absolute; bottom: 0; left: 0; right: 0; }
.toc-title { text-align: center; font-weight: bold; margin-bottom: 8mm; text-indent: 0; }
.toc-line { display: flex; align-items: baseline; margin: 0 0 3mm 0; text-indent: 0; text-align: left; }
.toc-line .dots { flex: 1 1 auto; border-bottom: 1px dotted #000; margin: 0 3px 4px 4px; }
h1 { font-size: 14pt; font-weight: bold; text-align: center; margin: 0 0 6mm 0; page-break-after: avoid; }
p.tcap { text-indent: 0; text-align: left; font-size: 12pt; margin: 4mm 0 2mm 0; page-break-after: avoid; }
p.caption { text-indent: 0; text-align: center; font-size: 12pt; margin: 2mm 0 6mm 0; }
p:has(> img) { text-indent: 0; text-align: center; margin: 4mm 0 0 0; page-break-after: avoid; }
img { display: block; margin: 0 auto; max-width: 100%; max-height: 100mm; width: auto; height: auto; }
ul, ol { margin: 2mm 0; padding-left: 1.25cm; }
li { margin: 0 0 1mm 0; text-indent: 0; }
table { border-collapse: collapse; width: 100%; margin: 1mm 0 4mm 0; font-size: 11pt; line-height: 1.25; }
tr { page-break-inside: avoid; }
th, td { border: 1px solid #000; padding: 1.2mm 1.8mm; vertical-align: top; text-align: left; text-indent: 0; }
th { font-weight: bold; text-align: center; }
.pagebreak { page-break-before: always; }
"""

TITLE_CLASS_STYLE = {"ttl": "Title Centered", "sign": "Left Block", "city": "Centered"}


def headings(md: str) -> list[str]:
    return [line[2:].strip() for line in md.splitlines() if line.startswith("# ")]


def toc_html(entries: list[str], pages: dict[str, object]) -> str:
    return "\n".join(
        f'<div class="toc-line"><span>{t}</span><span class="dots"></span><span>{pages.get(t, "")}</span></div>'
        for t in entries
    )


def render_html(md_text: str, pages: dict[str, object]) -> str:
    body = md_text.replace("<!--TOC-->", toc_html(headings(md_text), pages))
    html_body = markdown.markdown(body, extensions=["tables", "sane_lists", "attr_list"], output_format="html5")
    return (
        '<!doctype html>\n<html lang="ru">\n<head>\n<meta charset="utf-8">\n'
        "<title>Исследование методов распространения информации в распределённых системах</title>\n"
        f"<style>{CSS}</style>\n</head>\n<body>\n{html_body}\n</body>\n</html>\n"
    )


def find_chrome() -> str:
    for c in [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        shutil.which("google-chrome"),
        shutil.which("chromium"),
    ]:
        if c and Path(c).exists():
            return c
    raise SystemExit("Chrome/Chromium not found; cannot render PDF")


def print_pdf(chrome: str) -> None:
    cmd = [
        chrome, "--headless", "--disable-gpu", "--no-sandbox", "--no-pdf-header-footer",
        "--run-all-compositor-stages-before-draw", "--virtual-time-budget=15000",
        f"--print-to-pdf={PDF.resolve()}", HTML.resolve().as_uri(),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 or not PDF.exists():
        raise SystemExit(f"PDF rendering failed:\n{result.stderr}")


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def locate_headings(entries: list[str]) -> dict[str, int]:
    doc = fitz.open(PDF)
    start = max((i + 1 for i, p in enumerate(doc) if "СОДЕРЖАНИЕ" in p.get_text()), default=1)
    found: dict[str, int] = {}
    for title in entries:
        for i in range(start, len(doc)):
            if norm(title) in [norm(x) for x in doc[i].get_text().splitlines()]:
                found[title] = i + 1
                break
    doc.close()
    return found


def add_page_numbers() -> None:
    """Bottom-centre page numbers; the title page is not numbered."""
    doc = fitz.open(PDF)
    for i, page in enumerate(doc):
        if i == 0:
            continue
        label = str(i + 1)
        width = fitz.get_text_length(label, fontname="tiro", fontsize=12)
        page.insert_text((page.rect.width / 2 - width / 2, page.rect.height - 9 * 2.835), label,
                         fontname="tiro", fontsize=12)
    tmp = PDF.with_suffix(".tmp.pdf")
    doc.save(tmp, garbage=3, deflate=True)
    doc.close()
    tmp.replace(PDF)


def build_pdf(md_text: str) -> dict[str, object]:
    chrome = find_chrome()
    entries = headings(md_text)
    pages: dict[str, object] = {t: "" for t in entries}
    for _ in range(3):
        HTML.write_text(render_html(md_text, pages), encoding="utf-8")
        print_pdf(chrome)
        found = {t: found_page for t, found_page in locate_headings(entries).items()}
        new_pages = {t: found.get(t, "") for t in entries}
        if new_pages == pages:
            break
        pages = new_pages
    else:
        raise SystemExit("table of contents did not converge")
    add_page_numbers()
    HTML.unlink(missing_ok=True)
    print(f"wrote {PDF.relative_to(ROOT)}")
    return pages


def main() -> None:
    md_text = inject(REPORT.read_text(encoding="utf-8"))
    # Keep "NN %" on one line.
    md_text = re.sub(r"(\d) %", "\\1\u00a0%", md_text)
    pages = build_pdf(md_text)
    build_docx(md_text, pages, DOCX)
    print(f"wrote {DOCX.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
