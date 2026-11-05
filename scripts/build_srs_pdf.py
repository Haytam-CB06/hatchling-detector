"""Render the Nazar Vision SRS Markdown as a reviewable, paginated PDF.

Usage (with the bundled Codex Python runtime):
    python scripts/build_srs_pdf.py

The Markdown file remains the editable source of truth.
"""

from __future__ import annotations

from html import escape
from pathlib import Path

from markdown_it import MarkdownIt
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    LongTable,
    PageTemplate,
    Paragraph,
    Spacer,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "Nazar_Vision_Software_Requirements_Specification.md"
OUTPUT = ROOT / "docs" / "pdf" / "Nazar_Vision_Software_Requirements_Specification.pdf"

PAGE_W, PAGE_H = A4
LEFT = 48
RIGHT = 48
TOP = 57
BOTTOM = 51
CONTENT_W = PAGE_W - LEFT - RIGHT

NAVY = colors.HexColor("#172A45")
BLUE = colors.HexColor("#245B87")
MUTED = colors.HexColor("#617084")
PALE = colors.HexColor("#F3F6FA")
RULE = colors.HexColor("#DCE4EC")
INK = colors.HexColor("#1B2735")


def register_fonts() -> None:
    fonts = Path("C:/Windows/Fonts")
    pdfmetrics.registerFont(TTFont("Segoe", str(fonts / "segoeui.ttf")))
    pdfmetrics.registerFont(TTFont("Segoe-Bold", str(fonts / "segoeuib.ttf")))
    pdfmetrics.registerFont(TTFont("Segoe-Italic", str(fonts / "segoeuii.ttf")))
    pdfmetrics.registerFont(TTFont("Segoe-BoldItalic", str(fonts / "segoeuiz.ttf")))
    pdfmetrics.registerFontFamily(
        "Segoe",
        normal="Segoe",
        bold="Segoe-Bold",
        italic="Segoe-Italic",
        boldItalic="Segoe-BoldItalic",
    )
    pdfmetrics.registerFont(TTFont("Consolas", str(fonts / "consola.ttf")))


def make_styles() -> dict[str, ParagraphStyle]:
    base = ParagraphStyle(
        "Body",
        fontName="Segoe",
        fontSize=9.5,
        leading=13.9,
        textColor=INK,
        alignment=TA_LEFT,
        spaceAfter=7.1,
        allowWidows=0,
        allowOrphans=0,
    )
    return {
        "body": base,
        "title": ParagraphStyle(
            "Title",
            parent=base,
            fontName="Segoe-Bold",
            fontSize=21,
            leading=27,
            textColor=NAVY,
            spaceAfter=10,
            keepWithNext=1,
        ),
        "h2": ParagraphStyle(
            "Section",
            parent=base,
            fontName="Segoe-Bold",
            fontSize=13,
            leading=18,
            textColor=NAVY,
            spaceBefore=15,
            spaceAfter=7,
            keepWithNext=1,
        ),
        "h3": ParagraphStyle(
            "Subsection",
            parent=base,
            fontName="Segoe-Bold",
            fontSize=10.7,
            leading=15,
            textColor=BLUE,
            spaceBefore=11,
            spaceAfter=5,
            keepWithNext=1,
        ),
        "list": ParagraphStyle(
            "List",
            parent=base,
            leftIndent=18,
            firstLineIndent=0,
            bulletIndent=3,
            spaceAfter=5,
        ),
        "table": ParagraphStyle(
            "TableBody",
            parent=base,
            fontSize=8.25,
            leading=11.2,
            spaceAfter=0,
        ),
        "table_header": ParagraphStyle(
            "TableHeader",
            parent=base,
            fontName="Segoe-Bold",
            fontSize=8.15,
            leading=10.8,
            textColor=colors.white,
            spaceAfter=0,
        ),
        "kicker": ParagraphStyle(
            "Kicker",
            parent=base,
            fontName="Segoe-Bold",
            fontSize=7.5,
            leading=10,
            textColor=BLUE,
            spaceAfter=5,
            tracking=0.7,
        ),
    }


def inline_markup(token) -> str:
    """Convert supported Markdown inline tokens to ReportLab Paragraph markup."""
    fragments: list[str] = []
    for child in token.children or []:
        kind = child.type
        if kind == "text":
            fragments.append(escape(child.content))
        elif kind == "code_inline":
            fragments.append(
                '<font name="Consolas" color="#174E79">'
                + escape(child.content)
                + "</font>"
            )
        elif kind == "strong_open":
            fragments.append("<b>")
        elif kind == "strong_close":
            fragments.append("</b>")
        elif kind == "em_open":
            fragments.append("<i>")
        elif kind == "em_close":
            fragments.append("</i>")
        elif kind in ("softbreak", "hardbreak"):
            fragments.append("<br/>" if kind == "hardbreak" else " ")
        elif kind == "image":
            # No images are expected in this SRS; retain their alternative text.
            fragments.append(escape(child.content))
        elif kind in ("link_open", "link_close", "html_inline"):
            # Preserve displayed citation/link text. Local relative links are kept in
            # the Markdown source rather than embedded as machine-specific PDF URLs.
            if kind == "html_inline":
                fragments.append(escape(child.content))
        else:
            if child.content:
                fragments.append(escape(child.content))
    return "".join(fragments)


def table_widths(index: int) -> list[float]:
    proportions = {
        1: [0.27, 0.73],  # Document control
        2: [0.24, 0.52, 0.24],  # Actors
        3: [0.33, 0.67],  # FiftyOne fields
        4: [0.24, 0.10, 0.66],  # NFRs
        5: [0.24, 0.46, 0.30],  # Verification
        6: [0.11, 0.27, 0.52, 0.10],  # Extensions
        7: [0.11, 0.50, 0.39],  # Open decisions
        8: [0.28, 0.72],  # Glossary
    }[index]
    return [CONTENT_W * p for p in proportions]


def build_table(tokens, start: int, styles, number: int):
    rows = []
    row = None
    header = False
    i = start + 1
    while i < len(tokens):
        token = tokens[i]
        if token.type == "table_close":
            break
        if token.type == "thead_open":
            header = True
        elif token.type == "thead_close":
            header = False
        elif token.type == "tr_open":
            row = []
        elif token.type == "tr_close":
            rows.append(row)
            row = None
        elif token.type in ("th_open", "td_open"):
            style = styles["table_header" if header else "table"]
            content = inline_markup(tokens[i + 1])
            row.append(Paragraph(content, style))
        i += 1

    table = LongTable(
        rows,
        colWidths=table_widths(number),
        repeatRows=1,
        hAlign="LEFT",
        splitByRow=1,
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
                ("LINEBELOW", (0, 0), (-1, 0), 0.7, NAVY),
                ("LINEBELOW", (0, 1), (-1, -1), 0.35, RULE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table, i + 1


class SrsDocTemplate(BaseDocTemplate):
    def __init__(self, path: Path):
        super().__init__(
            str(path),
            pagesize=A4,
            leftMargin=LEFT,
            rightMargin=RIGHT,
            topMargin=TOP,
            bottomMargin=BOTTOM,
            title="Nazar Vision - Software Requirements Specification",
            author="Nazar Vision project team",
            subject="Graduation project planning baseline",
            pageCompression=1,
        )
        frame = Frame(
            LEFT,
            BOTTOM,
            CONTENT_W,
            PAGE_H - TOP - BOTTOM,
            leftPadding=0,
            rightPadding=0,
            topPadding=0,
            bottomPadding=0,
        )
        self.addPageTemplates(PageTemplate(id="normal", frames=frame, onPage=self.decorate))
        self.heading_serial = 0

    def decorate(self, canv, doc):
        canv.saveState()
        canv.setStrokeColor(RULE)
        canv.setLineWidth(0.7)
        canv.line(LEFT, PAGE_H - 39, PAGE_W - RIGHT, PAGE_H - 39)
        canv.setFont("Segoe-Bold", 7.5)
        canv.setFillColor(BLUE)
        canv.drawString(LEFT, PAGE_H - 29, "NAZAR VISION")
        canv.setFont("Segoe", 7.2)
        canv.setFillColor(MUTED)
        canv.drawRightString(PAGE_W - RIGHT, PAGE_H - 29, "SOFTWARE REQUIREMENTS SPECIFICATION")
        canv.line(LEFT, 37, PAGE_W - RIGHT, 37)
        canv.setFont("Segoe", 7.2)
        canv.drawString(LEFT, 25, "NV-SRS-001  •  Version 1.0 planning baseline  •  18 October 2026")
        canv.drawRightString(PAGE_W - RIGHT, 25, f"Page {doc.page}")
        canv.restoreState()

    def afterFlowable(self, flowable):
        if isinstance(flowable, Paragraph) and getattr(flowable, "section_level", None):
            self.heading_serial += 1
            key = f"srs-heading-{self.heading_serial}"
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(
                flowable.getPlainText(),
                key,
                level=0 if flowable.section_level == 2 else 1,
                closed=False,
            )


def make_story(tokens, styles):
    story = []
    i = 0
    table_number = 0
    list_stack = []
    item_first_paragraph = []

    while i < len(tokens):
        token = tokens[i]
        kind = token.type

        if kind == "heading_open":
            level = int(token.tag[1])
            style = styles["title" if level == 1 else "h2" if level == 2 else "h3"]
            heading = Paragraph(inline_markup(tokens[i + 1]), style)
            if level in (2, 3):
                heading.section_level = level
            if level == 1:
                story.append(Paragraph("PROJECT DOCUMENTATION  /  REQUIREMENTS BASELINE", styles["kicker"]))
                story.append(heading)
                story.append(Spacer(1, 3))
            else:
                story.append(heading)
            i += 3
            continue

        if kind == "table_open":
            table_number += 1
            table, i = build_table(tokens, i, styles, table_number)
            story.extend([table, Spacer(1, 9)])
            continue

        if kind in ("bullet_list_open", "ordered_list_open"):
            list_stack.append({"ordered": kind == "ordered_list_open", "number": int(token.attrGet("start") or 1) - 1})
        elif kind in ("bullet_list_close", "ordered_list_close"):
            list_stack.pop()
        elif kind == "list_item_open":
            item_first_paragraph.append(True)
            if list_stack[-1]["ordered"]:
                list_stack[-1]["number"] += 1
        elif kind == "list_item_close":
            item_first_paragraph.pop()
        elif kind == "paragraph_open":
            para_markup = inline_markup(tokens[i + 1])
            if list_stack:
                level = len(list_stack)
                style = ParagraphStyle(
                    f"List-{level}",
                    parent=styles["list"],
                    leftIndent=18 + (level - 1) * 14,
                    bulletIndent=2 + (level - 1) * 14,
                )
                bullet = None
                if item_first_paragraph[-1]:
                    bullet = (
                        f"{list_stack[-1]['number']}." if list_stack[-1]["ordered"] else "•"
                    )
                    item_first_paragraph[-1] = False
                story.append(Paragraph(para_markup, style, bulletText=bullet))
            else:
                story.append(Paragraph(para_markup, styles["body"]))
            i += 3
            continue

        i += 1
    return story, table_number


def main():
    register_fonts()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    markdown = SOURCE.read_text(encoding="utf-8")
    tokens = MarkdownIt("commonmark").enable("table").parse(markdown)
    styles = make_styles()
    story, tables = make_story(tokens, styles)
    SrsDocTemplate(OUTPUT).build(story)
    print(f"Wrote {OUTPUT}")
    print(f"Parsed {tables} Markdown tables and {len(story)} top-level flowables")


if __name__ == "__main__":
    main()
