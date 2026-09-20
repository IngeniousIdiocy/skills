"""
chain_summary_template.py — generates the one-to-two-page title chain
& covenant summary PDF.

The output is a single document made of:
  1. Title block (address + subtitle + compilation date)
  2. Property description paragraph
  3. Optional SDAT-discrepancy note
  4. Chain table (originating row highlighted)
  5. Covenant analysis paragraphs
  6. Diligence-items list
  7. Footer disclaimer

All data is supplied via dataclasses; nothing about a specific property
is hard-coded. Use build_outputs.py to wire deed-pipeline output into the
ChainSummaryDocument structure.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from reportlab.lib.colors import black
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import inch
from reportlab.platypus import (
    Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from . import _styles as S


@dataclass
class ChainEntry:
    """One row in the chain table."""
    date_html: str                  # e.g. "1909-07-15<br/>(rec. 7/30)"
    grantor_to_grantee_html: str    # e.g. "<b>X</b> &rarr; <b>Y</b>"
    citation_html: str              # e.g. "Liber WPC 343<br/>folios 585&ndash;590"
    substance_html: str             # plain explanatory paragraph (HTML)


@dataclass
class ChainSummaryDocument:
    """Everything build_chain_summary() needs to render the PDF."""
    output_path: str
    address_display: str            # e.g. "4503 Roland Avenue, Baltimore, MD 21210"
    subtitle: str = "Title Chain &amp; Covenant Summary"
    compiled_subtitle_html: str = ""  # e.g. "Compiled May 2, 2026 from MSA scans"

    property_description_html: str = ""
    sdat_discrepancy_html: Optional[str] = None  # None if no discrepancy

    entries: list[ChainEntry] = field(default_factory=list)
    originating_index: int = 1     # data-row index (1-based after header)
                                   # of the originating-developer row to highlight

    covenant_analysis_paragraphs_html: list[str] = field(default_factory=list)
    diligence_items_html: str = ""  # one HTML blob with <br/>-separated items

    footer_disclaimer_html: str = (
        "<i>This summary was generated from independent review of every "
        "recorded deed in this property's chain of title and is offered as "
        "research context, not legal advice. A licensed Maryland real estate "
        "attorney should review the underlying deed scans before any "
        "contested decision.</i>"
    )

    pdf_title: Optional[str] = None
    pdf_author: str = "maryland-property-research skill"


def _P(html: str, style):
    return Paragraph(html, style)


def _build_chain_table(entries: list[ChainEntry], originating_index: int) -> Table:
    """Build the chain table. Originating row is highlighted by the
    1-based data-row index (1 = first row after header)."""
    rows = [[
        _P("Date", S.CELL_B),
        _P("Grantor &rarr; Grantee", S.CELL_B),
        _P("Citation", S.CELL_B),
        _P("Substance", S.CELL_B),
    ]]
    for e in entries:
        rows.append([
            _P(e.date_html, S.CELL_B),
            _P(e.grantor_to_grantee_html, S.CELL),
            _P(e.citation_html, S.CELL),
            _P(e.substance_html, S.CELL),
        ])

    t = Table(
        rows,
        colWidths=[0.8 * inch, 1.85 * inch, 1.45 * inch, 3.3 * inch],
        repeatRows=1,
    )
    style_cmds = [
        ("FONT", (0, 0), (-1, -1), "Times-Roman", 8.5),
        ("BACKGROUND", (0, 0), (-1, 0), S.TABLE_HEADER_BG),
        ("TEXTCOLOR", (0, 0), (-1, 0), black),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("GRID", (0, 0), (-1, -1), 0.4, S.TABLE_GRID),
    ]
    if 1 <= originating_index <= len(entries):
        style_cmds.append((
            "BACKGROUND",
            (0, originating_index),
            (-1, originating_index),
            S.TABLE_ORIGINATING_HIGHLIGHT,
        ))
    t.setStyle(TableStyle(style_cmds))
    return t


def build_chain_summary(doc: ChainSummaryDocument) -> str:
    """Render the chain summary PDF. Returns the output path."""
    pdf = SimpleDocTemplate(
        doc.output_path, pagesize=LETTER,
        leftMargin=0.55 * inch, rightMargin=0.55 * inch,
        topMargin=0.55 * inch, bottomMargin=0.55 * inch,
        title=doc.pdf_title or f"{doc.address_display} - Title Chain Summary",
        author=doc.pdf_author,
    )

    story = []

    story += [
        _P(doc.address_display, S.H1),
        _P(doc.subtitle, S.SUB_LARGER),
    ]
    if doc.compiled_subtitle_html:
        story.append(_P(doc.compiled_subtitle_html, S.SUB))
    story.append(Spacer(1, 0.15 * inch))

    if doc.property_description_html:
        story.append(_P(doc.property_description_html, S.SMALL))

    if doc.sdat_discrepancy_html:
        story.append(_P(doc.sdat_discrepancy_html, S.SMALL))

    story.append(Spacer(1, 0.10 * inch))
    story.append(_build_chain_table(doc.entries, doc.originating_index))
    story.append(Spacer(1, 0.18 * inch))

    if doc.covenant_analysis_paragraphs_html:
        story.append(_P("Covenant Analysis", S.H2))
        for p_html in doc.covenant_analysis_paragraphs_html:
            story.append(_P(p_html, S.SMALL))

    if doc.diligence_items_html:
        story.append(Spacer(1, 0.12 * inch))
        story.append(_P("Diligence Items for Title Company / Counsel", S.H2))
        story.append(_P(doc.diligence_items_html, S.SMALL))

    story.append(Spacer(1, 0.10 * inch))
    story.append(_P(doc.footer_disclaimer_html, S.FOOTER))

    pdf.build(story)
    return doc.output_path
