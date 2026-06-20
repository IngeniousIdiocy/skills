"""
transcription_template.py — generates the originating-deed transcription PDF.

The transcription is structured as:
  1. Title page: deed title, parties subtitle, dates, citation, MSA accession,
     about-this-transcription block, optional scope note, present-terms summary
  2. Parties + consideration section
  3. Property description (full metes-and-bounds + together/habendum lead-in)
  4. Numbered covenants (each as its own clause paragraph; bolded operative phrases)
  5. Warranty + power-of-attorney + execution
  6. Signature block
  7. Acknowledgment
  8. Recording stamp
  9. Reader's commentary (optional notes)

`[?]` brackets on uncertain readings are preserved verbatim from the source HTML.

All data is supplied via dataclasses; nothing about a specific property is
hard-coded. Use build_outputs.py to wire deed-pipeline output into the
DeedTranscription structure.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from . import _styles as S


@dataclass
class Covenant:
    number: int           # 1-based
    text_html: str        # body of the covenant; bold operative phrases via <b>


@dataclass
class CommentaryNote:
    """One paragraph of reader's commentary (rendered as a NOTE-styled
    italic block-quote at the end of the document)."""
    text_html: str


@dataclass
class DeedTranscription:
    """Everything build_transcription() needs to render the PDF."""
    output_path: str

    # --- Title page block ---
    deed_title: str = "Deed of Conveyance"
    parties_subtitle_html: str = ""        # "<grantor> &mdash; to &mdash; <grantee>"
    dates_subtitle_html: str = ""          # "Dated <date> &middot; Recorded <date>"
    citation_subtitle_html: str = ""       # "<jurisdiction> Land Records, Liber <X>, folios <Y>"
    accession_subtitle_html: str = ""      # "Maryland State Archives accession MSA CE ..."

    transcription_provenance_html: str = (
        "<b>About this transcription.</b> Typed from the scanned cursive original "
        "with image enhancement to recover lighter passages. Modern font and modern "
        "punctuation reconstructed where the script was ambiguous. Bracketed words "
        "marked <b>[?]</b> indicate places where the original handwriting was not "
        "legible to the transcriber and the reading is best-guess. Verify against "
        "the scan in any matter of legal consequence."
    )
    scope_note_html: Optional[str] = None        # e.g. "This is the actual original deed for ..."
    present_terms_summary_html: Optional[str] = None  # "Property in present terms. Lot 20 + N1/2 of 21..."

    # --- Body sections ---
    parties_consideration_paragraphs_html: list[str] = field(default_factory=list)
    property_description_paragraphs_html: list[str] = field(default_factory=list)
    covenants: list[Covenant] = field(default_factory=list)
    warranty_execution_paragraphs_html: list[str] = field(default_factory=list)

    # --- Signature block (each entry = one centered italic line) ---
    signature_lines: list[str] = field(default_factory=list)

    # --- Acknowledgment + recording ---
    acknowledgment_paragraphs_html: list[str] = field(default_factory=list)
    notary_signature_lines: list[str] = field(default_factory=list)
    recording_stamp_html: Optional[str] = None    # e.g. "Recorded ..., examined. Per <Clerk>."

    # --- Reader's commentary ---
    commentary_notes: list[CommentaryNote] = field(default_factory=list)

    # --- PDF metadata ---
    pdf_title: Optional[str] = None
    pdf_author: str = "maryland-property-research skill"


def _P(html: str, style):
    return Paragraph(html, style)


def build_transcription(doc: DeedTranscription) -> str:
    """Render the originating-deed transcription PDF. Returns the output path."""
    pdf = SimpleDocTemplate(
        doc.output_path, pagesize=LETTER,
        leftMargin=0.9 * inch, rightMargin=0.9 * inch,
        topMargin=0.8 * inch, bottomMargin=0.8 * inch,
        title=doc.pdf_title or doc.deed_title,
        author=doc.pdf_author,
    )

    story = []

    # ---- Title block ----
    story.append(_P(doc.deed_title, S.H1))
    for line in (
        doc.parties_subtitle_html,
        doc.dates_subtitle_html,
        doc.citation_subtitle_html,
        doc.accession_subtitle_html,
    ):
        if line:
            story.append(_P(line, S.SUB))

    story.append(Spacer(1, 0.20 * inch))

    if doc.transcription_provenance_html:
        story.append(_P(doc.transcription_provenance_html, S.NOTE))

    if doc.scope_note_html:
        story.append(_P(doc.scope_note_html, S.NOTE))

    if doc.present_terms_summary_html:
        story.append(_P(doc.present_terms_summary_html, S.NOTE))

    story.append(Spacer(1, 0.10 * inch))

    # ---- Parties and consideration ----
    if doc.parties_consideration_paragraphs_html:
        story.append(_P("Parties and Consideration", S.H2))
        for p in doc.parties_consideration_paragraphs_html:
            story.append(_P(p, S.BODY))

    # ---- Property description (metes + together/habendum) ----
    if doc.property_description_paragraphs_html:
        # Property description usually flows directly from the consideration
        # block in the deed itself; we don't add a header for it unless the
        # first paragraph already starts a new section.
        for p in doc.property_description_paragraphs_html:
            story.append(_P(p, S.BODY))

    # ---- Covenants ----
    if doc.covenants:
        # Auto-pluralize: "The N Restrictive Covenants"
        n = len(doc.covenants)
        if n == 1:
            heading = "The Restrictive Covenant"
        else:
            heading = f"The {_num_word(n).capitalize()} Restrictive Covenants"
        story.append(_P(heading, S.H2))
        for c in doc.covenants:
            story.append(_P(f"<b>{c.number}.</b> {c.text_html}", S.CLAUSE))

    # ---- Warranty / POA / Execution ----
    if doc.warranty_execution_paragraphs_html:
        story.append(_P("Warranty, Power of Attorney, and Execution", S.H2))
        for p in doc.warranty_execution_paragraphs_html:
            story.append(_P(p, S.BODY))

    # ---- Signatures ----
    if doc.signature_lines:
        story.append(Spacer(1, 0.15 * inch))
        for line in doc.signature_lines:
            story.append(_P(line, S.SIG))
        story.append(Spacer(1, 0.20 * inch))

    # ---- Acknowledgment ----
    if doc.acknowledgment_paragraphs_html:
        story.append(_P("Acknowledgment", S.H2))
        for p in doc.acknowledgment_paragraphs_html:
            story.append(_P(p, S.BODY))
    for line in doc.notary_signature_lines:
        story.append(_P(line, S.SIG))

    if doc.recording_stamp_html:
        story.append(Spacer(1, 0.10 * inch))
        story.append(_P(doc.recording_stamp_html, S.BODY))

    # ---- Reader's commentary ----
    if doc.commentary_notes:
        story.append(Spacer(1, 0.20 * inch))
        story.append(_P("Reader's Commentary", S.H2))
        for note in doc.commentary_notes:
            story.append(_P(note.text_html, S.NOTE))

    pdf.build(story)
    return doc.output_path


_NUM_WORDS = {
    1: "one", 2: "two", 3: "three", 4: "four", 5: "five",
    6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten",
    11: "eleven", 12: "twelve", 13: "thirteen", 14: "fourteen",
    15: "fifteen", 16: "sixteen", 17: "seventeen", 18: "eighteen",
    19: "nineteen", 20: "twenty",
}


def _num_word(n: int) -> str:
    return _NUM_WORDS.get(n, str(n))
