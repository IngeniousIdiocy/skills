"""
build_outputs.py — orchestrator that takes the deed-pipeline output and
the originating-deed transcription content, and produces the two
deliverable PDFs (chain summary + transcription).

The skill orchestrator (Claude Code) is responsible for:

  1. Walking the chain via deed_pipeline.process_deed_pdf() until it reaches
     the originating developer deed.
  2. Reading the originating deed in full (this is the only deed whose
     covenants need transcription) and turning it into the structured
     DeedTranscription dataclass.
  3. Building the list of ChainEntry rows from each deed's metadata.
  4. Calling build_chain_summary_pdf() and build_transcription_pdf() below.

Both output paths default to the user's Downloads folder with the address
slug as a prefix; override `output_dir` to redirect.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Iterable, Optional

# Make sibling packages (templates/, reference/) importable when this file
# is invoked as a script (`python scripts/build_outputs.py`) rather than
# as a module (`python -m scripts.build_outputs`).
_SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SKILL_ROOT not in sys.path:
    sys.path.insert(0, _SKILL_ROOT)

from templates.chain_summary_template import (  # noqa: E402
    ChainEntry, ChainSummaryDocument, build_chain_summary,
)
from templates.transcription_template import (  # noqa: E402
    Covenant, CommentaryNote, DeedTranscription, build_transcription,
)


# ---------------------------------------------------------------------------
# Default output location
# ---------------------------------------------------------------------------

def default_output_dir() -> str:
    """User's Downloads folder, cross-platform-ish."""
    home = os.path.expanduser("~")
    return os.path.join(home, "Downloads")


# ---------------------------------------------------------------------------
# Convenience input dataclasses (slightly looser than the template ones)
# ---------------------------------------------------------------------------

@dataclass
class ChainRow:
    """Loose-form chain row before HTML-isation. Keep the human-readable
    strings here; build_chain_summary_pdf() formats them into HTML."""
    date: str                       # "1909-07-15" or "1909-07-15 (rec. 1909-07-30)"
    grantor: str                    # display name
    grantee: str                    # display name
    liber: str                      # "WPC 343"  or  "SCL 3219"
    folio: str                      # "585-590"  or  "385"
    jurisdiction: str               # "Baltimore County" / "Baltimore City"
    msa_accession: Optional[str] = None  # "MSA CE 62-343"
    citing_note: Optional[str] = None    # "(citing deed incorrectly named folio 83)"
    substance: str = ""             # plain English; bold-key-phrases via <b>
    is_originating: bool = False    # True for the developer's deed at the chain bottom


def _entries_from_rows(rows: Iterable[ChainRow]) -> tuple[list[ChainEntry], int]:
    """Convert ChainRow list to ChainEntry list + originating-row index
    (1-based after the header)."""
    entries: list[ChainEntry] = []
    originating_index = 0
    for i, r in enumerate(rows, start=1):
        entries.append(_chain_entry(r))
        if r.is_originating and originating_index == 0:
            originating_index = i
    return entries, originating_index


def _chain_entry(row: ChainRow) -> ChainEntry:
    # Date column with optional recorded-date suffix
    date_html = row.date.replace(" (rec. ", "<br/>(rec. ")
    if "<br/>(rec. " in date_html and not date_html.endswith(")"):
        date_html += ")"

    # Grantor → Grantee, with the originating row bold
    if row.is_originating:
        gg_html = f"<b>{row.grantor}</b> &rarr; <b>{row.grantee}</b>"
    else:
        gg_html = f"{row.grantor} &rarr; {row.grantee}"

    # Citation cell
    citation_parts = [f"Liber {row.liber}", f"folio{'s' if '-' in row.folio else ''} {row.folio}"]
    if row.jurisdiction:
        citation_parts.append(f"({row.jurisdiction})")
    if row.msa_accession:
        citation_parts.append(row.msa_accession)
    citation_html = "<br/>".join(citation_parts)
    if row.citing_note:
        citation_html += f"<br/><i>{row.citing_note}</i>"

    return ChainEntry(
        date_html=date_html,
        grantor_to_grantee_html=gg_html,
        citation_html=citation_html,
        substance_html=row.substance,
    )


# ---------------------------------------------------------------------------
# Build helpers — chain summary
# ---------------------------------------------------------------------------

def build_chain_summary_pdf(
    *,
    address_display: str,
    address_slug: str,
    rows: list[ChainRow],
    property_description_html: str = "",
    sdat_discrepancy_html: Optional[str] = None,
    covenant_analysis_paragraphs_html: Optional[list[str]] = None,
    diligence_items_html: str = "",
    compiled_subtitle_html: str = "",
    footer_disclaimer_html: Optional[str] = None,
    output_dir: Optional[str] = None,
) -> str:
    """Build the chain summary PDF; returns the output path."""
    out_dir = output_dir or default_output_dir()
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{address_slug}-title-chain-summary.pdf")

    entries, originating_index = _entries_from_rows(rows)
    if originating_index == 0 and entries:
        # Fall back to the first row (assumes oldest-first chain order)
        originating_index = 1

    doc = ChainSummaryDocument(
        output_path=out_path,
        address_display=address_display,
        compiled_subtitle_html=compiled_subtitle_html,
        property_description_html=property_description_html,
        sdat_discrepancy_html=sdat_discrepancy_html,
        entries=entries,
        originating_index=originating_index,
        covenant_analysis_paragraphs_html=covenant_analysis_paragraphs_html or [],
        diligence_items_html=diligence_items_html,
    )
    if footer_disclaimer_html is not None:
        doc.footer_disclaimer_html = footer_disclaimer_html
    return build_chain_summary(doc)


# ---------------------------------------------------------------------------
# Build helpers — transcription
# ---------------------------------------------------------------------------

def build_transcription_pdf(
    *,
    address_slug: str,
    deed_year: int,
    developer_slug: str,
    transcription: DeedTranscription,
    output_dir: Optional[str] = None,
) -> str:
    """Build the originating-deed transcription PDF.
    `transcription.output_path` is overridden to follow the standard naming."""
    out_dir = output_dir or default_output_dir()
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(
        out_dir,
        f"{address_slug}-{deed_year}-{developer_slug}-deed-transcription.pdf",
    )
    transcription.output_path = out_path
    return build_transcription(transcription)


# ---------------------------------------------------------------------------
# Raw-deed-PDF naming helper (used by the orchestrator when downloading)
# ---------------------------------------------------------------------------

def raw_deed_filename(
    *,
    address_slug: str,
    year: int,
    grantor_short: str,
    grantee_short: str,
    liber: str,        # e.g. "WPC 343" or "WPC343"
    folio: str,        # e.g. "585" or "585-590"
) -> str:
    """Standard filename for a raw deed PDF saved into Downloads/.

    Format: {address-slug}-{year}-{grantor}-to-{grantee}-{liber}-{folio}.pdf
    Spaces in the liber are removed; everything else is kept as the caller
    provides it (so the caller controls capitalization)."""
    liber_compact = liber.replace(" ", "")
    parts = [address_slug, str(year), grantor_short, "to", grantee_short, f"{liber_compact}-{folio}"]
    return "-".join(parts) + ".pdf"


# ---------------------------------------------------------------------------
# CLI smoke test (renders both PDFs with placeholder content into /tmp)
# ---------------------------------------------------------------------------

if __name__ == "__main__":  # pragma: no cover
    import tempfile

    out_dir = tempfile.mkdtemp(prefix="mpr-smoke-")
    print(f"Writing to {out_dir}")

    # Note: the templates accept HTML, so literal angle brackets in caller-supplied
    # text must be escaped to &lt; / &gt; or the reportlab parser will reject them.
    rows = [
        ChainRow(
            date="1909-07-15 (rec. 1909-07-30)",
            grantor="[Developer]",
            grantee="[First Grantee]",
            liber="[CLERK] 343",
            folio="585-590",
            jurisdiction="[County]",
            msa_accession="MSA CE ...",
            substance=(
                "<b>The originating deed.</b> Imposes the perpetual covenants "
                "on the land. Detail: residence-only use; one dwelling max; "
                "minimum build cost; plan approval; setback; perpetual "
                "maintenance fee; mutual-consent amendment."
            ),
            is_originating=True,
        ),
        ChainRow(
            date="2024-01-15",
            grantor="[Prior Owner]",
            grantee="[Current Owner]",
            liber="[CLERK] 9999",
            folio="123",
            jurisdiction="[County]",
            substance="Special warranty only &mdash; no new covenants.",
        ),
    ]

    chain_path = build_chain_summary_pdf(
        address_display="[Subject Address]",
        address_slug="placeholder",
        rows=rows,
        property_description_html=(
            "<b>Property:</b> [description from the originating deed]."
        ),
        sdat_discrepancy_html=None,
        covenant_analysis_paragraphs_html=[
            "<b>Total recorded covenants binding this property: N.</b>",
        ],
        diligence_items_html=(
            "(1) Reconcile SDAT vs deed parcel.<br/>"
            "(2) Review Schedule B-II of title commitment for specific "
            "exception of the originating deed.<br/>"
            "(3) Cross-check SDAT build year against earliest possible "
            "chain date; consult MIHP.<br/>"
            "(4) Verify any maintenance fee against deed cap."
        ),
        compiled_subtitle_html="Compiled by maryland-property-research skill",
        output_dir=out_dir,
    )
    print(f"chain summary: {chain_path}")

    transc = DeedTranscription(
        output_path="",  # overridden by build_transcription_pdf
        deed_title="Deed of Conveyance",
        parties_subtitle_html="[Developer] &mdash; to &mdash; [First Grantee]",
        dates_subtitle_html="Dated [date] &middot; Recorded [date]",
        citation_subtitle_html=(
            "[County] Land Records, Liber [CLERK] No. 343, folios 585&ndash;590"
        ),
        accession_subtitle_html="Maryland State Archives accession MSA CE ...",
        scope_note_html=None,
        present_terms_summary_html=(
            "<b>Property in present terms.</b> [description]."
        ),
        parties_consideration_paragraphs_html=[
            "<b>This Deed</b> made this [day] of [month], [year], by and "
            "between [Developer], of the first part, and [First Grantee], "
            "of the second part.",
        ],
        property_description_paragraphs_html=[
            "<b>Beginning</b> for the same at ...",
        ],
        covenants=[
            Covenant(1, "<b>Residence purposes only and not otherwise.</b>"),
            Covenant(2, "<b>One dwelling</b> on the land hereby conveyed."),
        ],
        warranty_execution_paragraphs_html=[
            "And the said [Developer] covenants that it will warrant "
            "specially the property hereby granted and conveyed.",
        ],
        signature_lines=[
            "[corporate seal]",
            "[Officer Name], [Title]",
        ],
        acknowledgment_paragraphs_html=[
            "<b>State of Maryland, [County], To Wit:</b>",
            "I hereby certify that on this [date], before me appeared "
            "[Officer], who acknowledged the foregoing deed.",
        ],
        notary_signature_lines=["[Notary Name], Notary Public"],
        recording_stamp_html=(
            "<b>Recorded [date], examined.</b><br/>Per [Clerk Name], Clerk."
        ),
        commentary_notes=[
            CommentaryNote(
                "<b>Substantive answer.</b> Reading these covenants in context."
            ),
        ],
    )
    transc_path = build_transcription_pdf(
        address_slug="placeholder",
        deed_year=1909,
        developer_slug="developer",
        transcription=transc,
        output_dir=out_dir,
    )
    print(f"transcription: {transc_path}")
