"""
Shared reportlab paragraph styles used by both deliverable PDFs.

Kept in one place so the two output documents look like a matched set.
Anyone hand-tuning the layout should edit only this file.
"""

from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet


_base = getSampleStyleSheet()


H1 = ParagraphStyle(
    "H1", parent=_base["Heading1"], fontName="Times-Bold",
    fontSize=18, leading=22, alignment=TA_CENTER, spaceAfter=6,
)
H2 = ParagraphStyle(
    "H2", parent=_base["Heading2"], fontName="Times-Bold",
    fontSize=13, leading=16, spaceBefore=14, spaceAfter=6,
    textColor=HexColor("#222"),
)
H2C = ParagraphStyle("H2C", parent=H2, alignment=TA_CENTER)

SUB = ParagraphStyle(
    "Sub", parent=_base["Normal"], fontName="Times-Italic",
    fontSize=10, leading=13, alignment=TA_CENTER,
    textColor=HexColor("#555"),
)
SUB_LARGER = ParagraphStyle("SubLarger", parent=SUB, fontSize=12)

BODY = ParagraphStyle(
    "Body", parent=_base["Normal"], fontName="Times-Roman",
    fontSize=11, leading=15, alignment=TA_JUSTIFY, spaceAfter=8,
)

NOTE = ParagraphStyle(
    "Note", parent=_base["Normal"], fontName="Times-Italic",
    fontSize=9.5, leading=13, alignment=TA_LEFT,
    textColor=HexColor("#666"),
    leftIndent=14, rightIndent=14, spaceAfter=8,
)

CLAUSE = ParagraphStyle(
    "Clause", parent=BODY,
    leftIndent=22, firstLineIndent=-22, spaceAfter=8,
)

SIG = ParagraphStyle(
    "Sig", parent=_base["Normal"], fontName="Times-Italic",
    fontSize=11, leading=15, alignment=TA_CENTER, spaceAfter=2,
)

CELL = ParagraphStyle(
    "Cell", parent=_base["Normal"], fontName="Times-Roman",
    fontSize=8.5, leading=11, alignment=TA_LEFT,
)
CELL_B = ParagraphStyle("CellB", parent=CELL, fontName="Times-Bold")
CELL_I = ParagraphStyle("CellI", parent=CELL, fontName="Times-Italic")

SMALL = ParagraphStyle(
    "Small", parent=_base["Normal"], fontName="Times-Roman",
    fontSize=9, leading=12, alignment=TA_LEFT, spaceAfter=6,
)

FOOTER = ParagraphStyle(
    "Footer", parent=SMALL, fontName="Times-Italic", fontSize=8.5,
    textColor=HexColor("#666"), alignment=TA_CENTER,
)


# Table colors (header + originating-row highlight)
TABLE_HEADER_BG = HexColor("#E8E4D9")
TABLE_GRID = HexColor("#999")
TABLE_ORIGINATING_HIGHLIGHT = HexColor("#FFF7E0")
