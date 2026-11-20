#!/usr/bin/env python3
"""Write docs/report.docx from docs/report.md with python-docx.

The layout follows docs/report.pdf: A4, margins 20/20/30/15 mm, Times New Roman
14 pt body with 1.5 spacing and 1.25 cm indent, bordered tables, centred figures
with captions, page numbers from page 2 and a table of contents with page numbers.
Every paragraph uses an explicit style, so the file imports cleanly into Google Docs.
"""

from __future__ import annotations

import re
from pathlib import Path

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_TAB_ALIGNMENT, WD_TAB_LEADER
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from docx.enum.style import WD_STYLE_TYPE
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
FONT = "Times New Roman"
TEXT_WIDTH_CM = 16.5
BLACK = RGBColor(0, 0, 0)


def _set_fonts(rpr_owner, name: str) -> None:
    """Set the font on all four script slots and drop theme font references."""
    rpr = rpr_owner.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.insert(0, rfonts)
    for attr in list(rfonts.attrib):
        if "Theme" in attr or "theme" in attr:
            del rfonts.attrib[attr]
    for slot in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        rfonts.set(qn(slot), name)


def _style(doc: Document, name: str, kind=WD_STYLE_TYPE.PARAGRAPH):
    styles = doc.styles
    if name in [s.name for s in styles]:
        return styles[name]
    return styles.add_style(name, kind)


def _format(style, size: float, *, bold=False, align=WD_ALIGN_PARAGRAPH.JUSTIFY, first=0.0,
            left=0.0, line=1.5, before=0.0, after=0.0, keep_next=False) -> None:
    style.font.name = FONT
    style.font.size = Pt(size)
    style.font.bold = bold
    style.font.italic = False
    style.font.color.rgb = BLACK
    _set_fonts(style.element, FONT)
    pf = style.paragraph_format
    pf.alignment = align
    pf.first_line_indent = Cm(first)
    pf.left_indent = Cm(left)
    pf.line_spacing = line
    pf.space_before = Pt(before)
    pf.space_after = Pt(after)
    pf.keep_with_next = keep_next
    pf.widow_control = True


def _page_setup(doc: Document) -> None:
    section = doc.sections[0]
    section.orientation = WD_ORIENT.PORTRAIT
    section.page_width, section.page_height = Cm(21.0), Cm(29.7)
    section.top_margin, section.bottom_margin = Cm(2.0), Cm(2.0)
    section.left_margin, section.right_margin = Cm(3.0), Cm(1.5)
    section.footer_distance = Cm(1.0)
    section.different_first_page_header_footer = True
    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _add_page_field(footer)
    for run in footer.runs:
        run.font.name = FONT
        run.font.size = Pt(12)


def _add_page_field(paragraph) -> None:
    run = paragraph.add_run()
    for tag, text in (("begin", None), ("instr", " PAGE "), ("separate", None), ("text", "2"), ("end", None)):
        if tag == "instr":
            el = OxmlElement("w:instrText")
            el.set(qn("xml:space"), "preserve")
            el.text = text
        elif tag == "text":
            el = OxmlElement("w:t")
            el.text = text
        else:
            el = OxmlElement("w:fldChar")
            el.set(qn("w:fldCharType"), tag)
        run._r.append(el)


def _styles(doc: Document) -> None:
    normal = doc.styles["Normal"]
    _format(normal, 14, first=1.25)

    h1 = doc.styles["Heading 1"]
    _format(h1, 14, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, first=0.0, before=0.0, after=6, keep_next=True)
    h2 = doc.styles["Heading 2"]
    _format(h2, 14, bold=True, align=WD_ALIGN_PARAGRAPH.LEFT, first=1.25, before=6, after=3, keep_next=True)

    _format(_style(doc, "Table Caption"), 12, align=WD_ALIGN_PARAGRAPH.LEFT, first=0.0, line=1.0,
            before=4, after=2, keep_next=True)
    _format(_style(doc, "Figure Caption"), 12, align=WD_ALIGN_PARAGRAPH.CENTER, first=0.0, line=1.0,
            before=2, after=6)
    _format(_style(doc, "Cell"), 11, align=WD_ALIGN_PARAGRAPH.LEFT, first=0.0, line=1.0)
    _format(_style(doc, "Center"), 14, align=WD_ALIGN_PARAGRAPH.CENTER, first=0.0, line=1.5)
    _format(_style(doc, "Title Line"), 20, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, first=0.0, line=1.5)
    _format(_style(doc, "Sign"), 14, align=WD_ALIGN_PARAGRAPH.LEFT, first=0.0, left=8.5, line=1.4)
    _format(_style(doc, "Bold Center"), 14, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, first=0.0, after=8)
    _format(_style(doc, "Code"), 11, align=WD_ALIGN_PARAGRAPH.LEFT, first=0.0, line=1.0)
    _format(_style(doc, "Toc Entry"), 14, align=WD_ALIGN_PARAGRAPH.LEFT, first=0.0, line=1.5, after=4)
    _format(_style(doc, "List Item"), 14, align=WD_ALIGN_PARAGRAPH.LEFT, first=-0.75, left=1.25)


INLINE = re.compile(r"(\*\*.+?\*\*|`[^`]+`|<b>.*?</b>|<br>)")


def add_inline(paragraph, text: str, *, size: float | None = None, bold: bool = False) -> None:
    """Add text with **bold**, `code`, <b>bold</b> and <br> line breaks."""
    text = text.replace("&nbsp;", " ")
    for token in INLINE.split(text):
        if not token:
            continue
        run_bold, run_text, font = bold, token, None
        if token == "<br>":
            paragraph.add_run().add_break()
            continue
        if token.startswith("**") and token.endswith("**"):
            run_bold, run_text = True, token[2:-2]
        elif token.startswith("<b>") and token.endswith("</b>"):
            run_bold, run_text = True, token[3:-4]
        elif token.startswith("`") and token.endswith("`"):
            run_text, font = token[1:-1], "Courier New"
        run = paragraph.add_run(run_text)
        run.bold = run_bold
        run.font.name = font or FONT
        _set_fonts(run._r, font or FONT)
        if size:
            run.font.size = Pt(size)
        run.font.color.rgb = BLACK


def _page_break_at_start(paragraph) -> None:
    """Explicit page break as the first run: honoured by Word, Google Docs and previewers."""
    run = paragraph.add_run()
    run.add_break(WD_BREAK.PAGE)
    element = run._r
    element.getparent().remove(element)
    ppr = paragraph._p.pPr
    paragraph._p.insert(1 if ppr is not None else 0, element)


def _para(doc, text: str, style: str, *, page_break=False, keep_next=False, **fmt):
    p = doc.add_paragraph(style=style)
    if page_break:
        _page_break_at_start(p)
    if keep_next:
        p.paragraph_format.keep_with_next = True
    for key, value in fmt.items():
        setattr(p.paragraph_format, key, value)
    add_inline(p, text)
    return p


def _picture(doc, rel_path: str, page_break: bool) -> None:
    path = ROOT / "docs" / rel_path
    with Image.open(path) as im:
        w, h = im.size
    width = min(TEXT_WIDTH_CM, 10.0 * w / h)
    p = doc.add_paragraph(style="Center")
    if page_break:
        _page_break_at_start(p)
    p.paragraph_format.keep_with_next = True
    p.paragraph_format.space_before = Pt(4)
    p.add_run().add_picture(str(path), width=Cm(width))


def _table(doc, rows: list[list[str]], aligns: list[str]) -> None:
    header, body = rows[0], rows[1:]
    ncols = len(header)
    weights = []
    for c in range(ncols):
        longest = max(len(r[c]) if c < len(r) else 0 for r in rows)
        weights.append(min(max(longest, 6), 48))
    total = sum(weights)
    widths = [max(1.8, TEXT_WIDTH_CM * w / total) for w in weights]
    scale = TEXT_WIDTH_CM / sum(widths)
    widths = [w * scale for w in widths]

    table = doc.add_table(rows=1 + len(body), cols=ncols)
    table.style = doc.styles["Table Grid"]
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    for r_idx, row in enumerate([header] + body):
        for c_idx in range(ncols):
            cell = table.rows[r_idx].cells[c_idx]
            cell.width = Cm(widths[c_idx])
            p = cell.paragraphs[0]
            p.style = doc.styles["Cell"]
            text = row[c_idx] if c_idx < len(row) else ""
            if r_idx == 0:
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                add_inline(p, text, bold=True)
            else:
                align = {"r": WD_ALIGN_PARAGRAPH.RIGHT, "c": WD_ALIGN_PARAGRAPH.CENTER}.get(aligns[c_idx], WD_ALIGN_PARAGRAPH.LEFT)
                p.alignment = align
                add_inline(p, text)
    header_row = table.rows[0]._tr
    trpr = header_row.get_or_add_trPr()
    marker = OxmlElement("w:tblHeader")
    trpr.append(marker)
    spacer = doc.add_paragraph(style="Normal")
    spacer.paragraph_format.first_line_indent = Cm(0)
    spacer.paragraph_format.line_spacing = 1.0
    spacer.paragraph_format.space_after = Pt(4)


def _list_item(doc, marker: str, text: str) -> None:
    p = _para(doc, f"{marker}\t" + text, "List Item")
    p.paragraph_format.tab_stops.add_tab_stop(Cm(1.25))


def _split_row(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _toc(doc, entries: list[str], pages: dict[str, object]) -> None:
    for title in entries:
        p = doc.add_paragraph(style="Toc Entry")
        p.paragraph_format.tab_stops.add_tab_stop(Cm(TEXT_WIDTH_CM - 0.1), WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.DOTS)
        add_inline(p, title)
        run = p.add_run("\t" + str(pages.get(title, "")))
        run.font.name = FONT
        run.font.size = Pt(14)


def build(md: str, pages: dict[str, object], out: Path) -> None:
    doc = Document()
    _page_setup(doc)
    _styles(doc)
    doc.core_properties.title = "Исследование методов распространения информации в распределённых системах"

    headings = [line[2:].strip() for line in md.splitlines() if line.startswith("# ")]
    md = md.replace("<!--TOC-->", "@@TOC@@")

    titlepage = re.search(r'<div class="titlepage">(.*?)</div>\s*\n\n', md, flags=re.S)
    if titlepage:
        inner = titlepage.group(1)
        sign = re.search(r'<div class="sign">(.*?)</div>', inner, flags=re.S)
        head = inner.replace(sign.group(0), "@@SIGN@@") if sign else inner
        items = re.split(r'(@@SIGN@@)', head)
        first = True
        for part in items:
            if part == "@@SIGN@@":
                for text in re.findall(r"<p>(.*?)</p>", sign.group(1), flags=re.S):
                    _para(doc, text, "Sign", first_line_indent=Cm(0))
                continue
            for cls, text in re.findall(r'<p(?: class="(\w+)")?>(.*?)</p>', part, flags=re.S):
                if cls == "ttl":
                    _para(doc, text, "Title Line", space_before=Pt(120) if first else Pt(0))
                elif cls == "city":
                    _para(doc, text, "Center", space_before=Pt(250))
                elif cls == "ministry" or cls is None or cls == "center":
                    _para(doc, text, "Center")
                first = False
        md = md[titlepage.end():]

    lines = md.split("\n")
    pending_break = False
    i = 0
    paragraph_buffer: list[str] = []

    def flush_paragraph() -> None:
        nonlocal pending_break, paragraph_buffer
        if paragraph_buffer:
            _para(doc, " ".join(paragraph_buffer), "Normal", page_break=pending_break)
            pending_break = False
            paragraph_buffer = []

    while i < len(lines):
        line = lines[i].rstrip()
        stripped = line.strip()
        if not stripped:
            flush_paragraph()
            i += 1
            continue
        if stripped == '<div class="pagebreak"></div>':
            flush_paragraph()
            pending_break = True
        elif stripped.startswith('<div class="toc-title">'):
            flush_paragraph()
            text = re.sub(r"</?div[^>]*>", "", stripped)
            _para(doc, text, "Bold Center", page_break=pending_break)
            pending_break = False
        elif stripped == "@@TOC@@":
            flush_paragraph()
            _toc(doc, headings, pages)
        elif line.startswith("# "):
            flush_paragraph()
            _para(doc, line[2:].strip(), "Heading 1", page_break=pending_break)
            pending_break = False
        elif line.startswith("## "):
            flush_paragraph()
            _para(doc, line[3:].strip(), "Heading 2", page_break=pending_break)
            pending_break = False
        elif stripped.startswith('<p class="tcap">'):
            flush_paragraph()
            text = re.sub(r'</?p[^>]*>', "", stripped)
            _para(doc, text, "Table Caption")
        elif stripped.startswith('<p class="caption">'):
            flush_paragraph()
            text = re.sub(r'</?p[^>]*>', "", stripped)
            _para(doc, text, "Figure Caption")
        elif stripped.startswith("!["):
            flush_paragraph()
            m = re.match(r"!\[.*?\]\((img/[^)]+)\)", stripped)
            _picture(doc, m.group(1), pending_break)
            pending_break = False
        elif stripped.startswith("|"):
            flush_paragraph()
            block = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                block.append(lines[i].strip())
                i += 1
            sep = _split_row(block[1])
            aligns = ["r" if c.endswith(":") else "l" for c in sep]
            rows = [_split_row(r) for k, r in enumerate(block) if k != 1]
            _table(doc, rows, aligns)
            continue
        elif re.match(r"^[*-] ", stripped):
            flush_paragraph()
            _list_item(doc, "•", stripped[2:])
        elif re.match(r"^\d+\. ", stripped):
            flush_paragraph()
            num, rest = stripped.split(". ", 1)
            _list_item(doc, f"{num}.", rest)
        else:
            paragraph_buffer.append(stripped)
        i += 1
    flush_paragraph()

    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out))
