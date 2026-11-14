#!/usr/bin/env python3
"""Combine report.md and generated tables into HTML and print a PDF via Chrome."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
REPORT = DOCS / "report.md"
TABLES = DOCS / "generated" / "tables.md"
HTML = DOCS / "report.html"
PDF = DOCS / "report.pdf"

CSS = """
@page { size: A4; margin: 17mm 15mm 17mm 15mm; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body {
  font-family: -apple-system, "Helvetica Neue", Arial, sans-serif;
  font-size: 10.5pt;
  line-height: 1.42;
  color: #1b1b1b;
  max-width: 190mm;
  margin: 0 auto;
}
h1 { font-size: 21pt; line-height: 1.2; margin: 0 0 8mm 0; }
h2 { font-size: 15pt; margin-top: 8mm; border-bottom: 1px solid #ddd; padding-bottom: 2mm; }
h3 { font-size: 12pt; margin-top: 6mm; }
p { margin: 2.2mm 0; text-align: justify; }
ul, ol { margin: 2mm 0 2mm 6mm; }
li { margin: 1mm 0; }
code { font-family: Menlo, Consolas, monospace; font-size: 9pt; background: #f4f4f4; padding: 0 2px; border-radius: 2px; }
pre { background: #f6f8fa; padding: 3mm; border-radius: 2mm; overflow-x: auto; font-size: 8.5pt; }
pre code { background: none; padding: 0; }
table { border-collapse: collapse; width: 100%; margin: 3mm 0 5mm 0; font-size: 8.6pt; page-break-inside: avoid; }
th, td { border: 1px solid #cfcfcf; padding: 1.6mm 2.2mm; vertical-align: top; }
th { background: #f0f3f7; font-weight: 600; }
tr:nth-child(even) td { background: #fafafa; }
img { max-width: 100%; height: auto; display: block; margin: 3mm auto 1mm auto; page-break-inside: avoid; }
blockquote { border-left: 3px solid #bbb; margin: 3mm 0; padding: 1mm 4mm; color: #444; }
hr { border: none; border-top: 1px solid #ddd; margin: 6mm 0; }
.pagebreak { page-break-before: always; }
a { color: #0b5cad; text-decoration: none; }
"""


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


def main() -> None:
    if not REPORT.exists():
        raise SystemExit(f"missing {REPORT}")
    body = REPORT.read_text(encoding="utf-8")
    if TABLES.exists():
        body += "\n\n<div class=\"pagebreak\"></div>\n\n"
        body += TABLES.read_text(encoding="utf-8")
    html_body = markdown.markdown(
        body,
        extensions=["tables", "fenced_code", "sane_lists", "toc"],
        output_format="html5",
    )
    html = (
        "<!doctype html>\n<html lang=\"ru\">\n<head>\n<meta charset=\"utf-8\">\n"
        "<title>Распространение информации в распределённых системах</title>\n"
        f"<style>{CSS}</style>\n</head>\n<body>\n{html_body}\n</body>\n</html>\n"
    )
    HTML.write_text(html, encoding="utf-8")
    print(f"wrote {HTML.relative_to(ROOT)}")

    chrome = find_chrome()
    if not chrome:
        print("Chrome/Chromium not found; HTML is ready, PDF was not generated.", file=sys.stderr)
        return
    env = dict(os.environ)
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
    result = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if result.returncode != 0 or not PDF.exists():
        print(result.stdout, file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        raise SystemExit("failed to generate PDF")
    print(f"wrote {PDF.relative_to(ROOT)} ({PDF.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
