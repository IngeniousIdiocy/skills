"""
deed_pipeline.py — Render-enhance-extract-validate pipeline for Maryland
recorded-deed scans pulled from landrec.msa.maryland.gov.

The pipeline answers two questions for each deed in a chain:
  1. What does this deed say (parties, dates, property description, recital)?
  2. What is the prior deed it points to (clerk + book + folio)?

The hard part is question 2. Citations within faint cursive scans are
unreliable at default rendering. The recipe in `enhance_image()` is the
single most important fix — without it, OCR on book/folio digits is
consistently wrong.

After extracting a candidate citation, `validate_citation_by_jump()`
pulls the cited deed and checks whether the parties + date match what
the parent recital said. Mismatch → retry with alternate image variants,
or scan ±5 folios in the same volume.

Dependencies: PyMuPDF (fitz), Pillow, numpy, optional pytesseract for
fallback OCR. The Read tool of a multimodal LLM agent (Claude Sonnet 4.6
or Opus 4.7) is the primary "OCR" — these helpers prepare the images
the LLM agent will read.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

import fitz  # PyMuPDF
import numpy as np
from PIL import Image, ImageEnhance, ImageOps


# ---------------------------------------------------------------------------
# 1. Render PDF page to PNG
# ---------------------------------------------------------------------------

DEFAULT_DPI = 240


def render_pdf_pages(pdf_path: str | Path, out_dir: str | Path, *, dpi: int = DEFAULT_DPI) -> list[Path]:
    """Render every page of `pdf_path` to PNG at `dpi`, returning the saved paths.

    240 DPI is the sweet spot — higher mostly grows file size without legibility gain.
    """
    pdf_path = Path(pdf_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(pdf_path)
    saved: list[Path] = []
    for i, page in enumerate(doc, start=1):
        pix = page.get_pixmap(dpi=dpi)
        out = out_dir / f"p{i}.png"
        pix.save(out)
        saved.append(out)
    return saved


# ---------------------------------------------------------------------------
# 2. Enhance image — the recipe
# ---------------------------------------------------------------------------

@dataclass
class EnhancedSet:
    """The set of variants produced for one source page.

    Two enhancement profiles are produced:

      DIGITS profile (aggressive: contrast 2.4×, sharpness 2.0×, cutoff 1)
      Use for: book/folio numbers, dates, dollar amounts, MSA accessions.
      Why: aggressive contrast collapses faint digit strokes into solid lines.
      Cost: aggressive sharpening DEFORMS cursive letterforms — makes proper
      names systematically harder to read (S↔K, n-o-w↔n-o-x, t↔l↔h confusion).

      LETTERFORMS profile (mild: contrast 1.5×, sharpness 1.0×, cutoff 0.5)
      Use for: grantor/grantee names, witnesses, notaries, place names.
      Why: preserves stroke shape so cursive ascenders/descenders stay legible.
      Cost: faint digits may not pop out as cleanly — keep DIGITS for citations.

    The agent should look at BOTH variants when extracting any field that
    matters. A name read from `enhanced_letters` confirmed by a re-read of
    the same name from `enhanced_letters_zoom_2x` is much more reliable than
    either alone.
    """
    base: Path
    # Digits-tuned variants (existing recipe — best for book/folio/dates):
    enhanced: Path                 # whole-page, digits-tuned
    enhanced_zoom_2x: Path         # 2x upscale of cropped recital, digits-tuned
    inverted: Path                 # white-on-black 2x crop, digits-tuned
    threshold: Path                # binary 2x crop, digits-tuned
    cropped_recital: Path          # cropped recital, digits-tuned

    # Letterforms-tuned variants (use for cursive proper names):
    enhanced_letters: Path         # whole-page, letterforms-tuned
    enhanced_letters_zoom_2x: Path # 2x upscale of larger crop, letterforms-tuned


# Two enhancement profiles — the difference is everything for proper names.
# DIGITS_PROFILE is the original aggressive recipe; LETTERS_PROFILE is mild.
DIGITS_PROFILE = {"contrast": 2.4, "sharpness": 2.0, "autocontrast_cutoff": 1}
LETTERS_PROFILE = {"contrast": 1.5, "sharpness": 1.0, "autocontrast_cutoff": 0.5}


def _apply_profile(img: Image.Image, profile: dict) -> Image.Image:
    out = ImageEnhance.Contrast(img).enhance(profile["contrast"])
    out = ImageEnhance.Sharpness(out).enhance(profile["sharpness"])
    out = ImageOps.autocontrast(out, cutoff=profile["autocontrast_cutoff"])
    return out


def enhance_image(
    src: str | Path,
    out_dir: str | Path | None = None,
    *,
    crop_top_frac: float = 0.04,
    crop_bottom_frac: float = 0.55,
    letters_crop_top_frac: float = 0.0,
    letters_crop_bottom_frac: float = 0.85,
) -> EnhancedSet:
    """Apply both enhancement profiles to `src` and produce all variants.

    DIGITS profile (existing recipe):
      1. Convert to grayscale
      2. ImageEnhance.Contrast(2.4)
      3. ImageEnhance.Sharpness(2.0)
      4. ImageOps.autocontrast(cutoff=1)
      5. 2x LANCZOS upscale of the cropped recital area
      Plus inverted + binary-threshold fallback variants for hard cases.

    LETTERFORMS profile (new — for proper names):
      1. Convert to grayscale
      2. ImageEnhance.Contrast(1.5)              — mild
      3. ImageEnhance.Sharpness(1.0)             — no extra sharpening
      4. ImageOps.autocontrast(cutoff=0.5)       — gentle
      5. Larger crop (top 0%–85% of page captures parties, witnesses,
         signatures — not just the citation band).
      6. 2x LANCZOS upscale.

    The two profiles are NOT redundant — use DIGITS for the citation
    extraction (book/folio/date) and LETTERS for the grantor/grantee names.
    """
    src = Path(src)
    out_dir = Path(out_dir) if out_dir else src.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    stem = src.stem

    img = Image.open(src).convert("L")
    w, h = img.size

    # ---- DIGITS profile: whole page ----
    full = _apply_profile(img, DIGITS_PROFILE)
    enhanced_path = out_dir / f"{stem}_enh.png"
    full.save(enhanced_path)

    # ---- DIGITS profile: cropped recital (tight) ----
    crop = img.crop((0, int(h * crop_top_frac), w, int(h * crop_bottom_frac)))
    e = _apply_profile(crop, DIGITS_PROFILE)
    cropped_path = out_dir / f"{stem}_recital.png"
    e.save(cropped_path)

    # 2x LANCZOS upscale of the digits-tuned cropped recital
    zoom_2x = e.resize((e.width * 2, e.height * 2), Image.LANCZOS)
    zoom_2x_path = out_dir / f"{stem}_recital_2x.png"
    zoom_2x.save(zoom_2x_path)

    # Inverted (white-on-black)
    inverted_path = out_dir / f"{stem}_inverted.png"
    ImageOps.invert(zoom_2x).save(inverted_path)

    # Binary threshold
    arr = np.array(ImageOps.autocontrast(crop, cutoff=2))
    thresh = arr.mean() - 0.5 * arr.std()
    binary = (arr < thresh).astype("uint8") * 255
    binary = 255 - binary
    threshold_path = out_dir / f"{stem}_threshold.png"
    Image.fromarray(binary).save(threshold_path)

    # ---- LETTERFORMS profile: whole page ----
    letters_full = _apply_profile(img, LETTERS_PROFILE)
    letters_path = out_dir / f"{stem}_letters.png"
    letters_full.save(letters_path)

    # ---- LETTERFORMS profile: larger crop, 2x upscale ----
    letters_crop = img.crop((
        0,
        int(h * letters_crop_top_frac),
        w,
        int(h * letters_crop_bottom_frac),
    ))
    letters_e = _apply_profile(letters_crop, LETTERS_PROFILE)
    letters_zoom_2x = letters_e.resize(
        (letters_e.width * 2, letters_e.height * 2), Image.LANCZOS
    )
    letters_zoom_2x_path = out_dir / f"{stem}_letters_2x.png"
    letters_zoom_2x.save(letters_zoom_2x_path)

    return EnhancedSet(
        base=src,
        enhanced=enhanced_path,
        enhanced_zoom_2x=zoom_2x_path,
        inverted=inverted_path,
        threshold=threshold_path,
        cropped_recital=cropped_path,
        enhanced_letters=letters_path,
        enhanced_letters_zoom_2x=letters_zoom_2x_path,
    )


def render_and_enhance(pdf_path: str | Path, out_dir: str | Path) -> list[EnhancedSet]:
    """Render every page of `pdf_path` to PNG and produce the enhanced set
    for each. Returns one EnhancedSet per page in order.
    """
    pages = render_pdf_pages(pdf_path, out_dir)
    return [enhance_image(p, out_dir) for p in pages]


# ---------------------------------------------------------------------------
# 3. Citation extraction
# ---------------------------------------------------------------------------

# Chain-back recital regex.
#
# The recital sentence is structurally:
#
#   Being [the same | part of the same] [lot|property|premises]
#   ... by deed dated <date>, <year> and recorded ...
#   [in] Liber <CLERK>. No. <BOOK>, folio <FOLIO>
#   ... was granted and conveyed by <GRANTOR> [unto|to] [the said] <GRANTEE>
#
# Whitespace is variable; the deed body is one continuous paragraph in old
# scans. We use re.DOTALL via the `(?s)` mode flag below.

CHAIN_BACK_RE = re.compile(
    r"""
    Being\s+(?:the\s+same|part\s+of\s+the\s+same)
    \s+(?:lot|property|premises)
    [^.]*?                                                     # filler
    deed\s+dated\s+
    (?P<date>[A-Za-z]+\s+\d{1,2}(?:st|nd|rd|th)?,?\s*\d{4})    # date
    [^.]*?
    Liber\s+
    (?P<clerk>[A-Z](?:\.?\s*[A-Z])*\.?)                        # clerk prefix (e.g., W.P.C.)
    \s*No\.?\s*
    (?P<book>\d+)                                              # book number
    [^.]*?
    folio\s+
    (?P<folio>\d+)                                             # folio number
    [^.]*?
    granted\s+and\s+conveyed\s+by\s+
    (?P<grantor>[^,]+(?:,\s+[^,]+)?)                           # grantor (optionally with spouse)
    \s+(?:unto|to)\s+
    (?:the\s+said\s+)?
    (?P<grantee>[^.,]+(?:,\s+[^.,]+)?)                         # grantee
    """,
    re.IGNORECASE | re.DOTALL | re.VERBOSE,
)


# Same-day "even date" / straw-deed pattern detection.
# Triggered by phrases like:
#   "by deed of even date herewith"
#   "recorded or intended to be recorded prior hereto"
STRAW_RE = re.compile(
    r"(by\s+deed\s+of\s+even\s+date\s+herewith"
    r"|recorded\s+(?:or\s+intended\s+to\s+be\s+recorded\s+)?prior\s+hereto)",
    re.IGNORECASE | re.DOTALL,
)


# Metes-and-bounds neighbor reference (looks similar to chain-back but is
# a survey landmark, not a chain step). Triggered by phrases like:
#   "to the end of the second line of the land"
#   "thence ... and following the third line of said <Name>'s land"
NEIGHBOR_METES_RE = re.compile(
    r"(?:end\s+of\s+the\s+\w+\s+line|following\s+the\s+\w+\s+line)\s+of\s+(?:said\s+)?(?:the\s+)?(?:land|[A-Z][a-z]+(?:'s|\s+land))",
    re.IGNORECASE,
)


@dataclass
class Citation:
    """One chain-back citation extracted from a deed body."""
    date_text: str                         # raw matched date string
    clerk: str                             # clerk prefix, normalized (no dots)
    book: int
    folio: int
    grantor: str
    grantee: str
    is_straw: bool = False                 # True if recital looks like even-date companion deed
    raw_match: str = ""                    # the matched substring, for debugging

    @property
    def normalized_clerk(self) -> str:
        return re.sub(r"\W+", "", self.clerk).upper()


@dataclass
class DeedReadResult:
    """Output of reading a deed's text body."""
    text: str
    citations: list[Citation] = field(default_factory=list)
    has_straw_pattern: bool = False
    neighbor_refs: list[str] = field(default_factory=list)


def parse_citations(text: str) -> DeedReadResult:
    """Run all the recital-pattern regexes against `text` and return
    structured citations + flags.
    """
    citations: list[Citation] = []
    for m in CHAIN_BACK_RE.finditer(text):
        c = Citation(
            date_text=m.group("date").strip(),
            clerk=m.group("clerk").strip(),
            book=int(m.group("book")),
            folio=int(m.group("folio")),
            grantor=_clean_party(m.group("grantor")),
            grantee=_clean_party(m.group("grantee")),
            raw_match=m.group(0),
        )
        # Mark straw deeds — chain-back recital that points to a same-day
        # companion deed (will not be in landrec under the cited folio
        # but at a nearby folio; treat as a sibling, not a chain link).
        window = text[max(0, m.start() - 200): m.end() + 200]
        c.is_straw = bool(STRAW_RE.search(window))
        citations.append(c)

    has_straw = any(c.is_straw for c in citations)
    neighbor = [m.group(0) for m in NEIGHBOR_METES_RE.finditer(text)]

    return DeedReadResult(
        text=text,
        citations=citations,
        has_straw_pattern=has_straw,
        neighbor_refs=neighbor,
    )


def _clean_party(s: str) -> str:
    s = re.sub(r"\s+", " ", s).strip(" ,.")
    return s


# ---------------------------------------------------------------------------
# 4. Cross-validation — pulled-deed sanity check
# ---------------------------------------------------------------------------

@dataclass
class ValidationResult:
    matched: bool
    reason: str
    candidate_citation: Citation
    actual_parties: Optional[tuple[str, str]] = None
    actual_date: Optional[str] = None


def validate_pulled_deed(
    candidate: Citation,
    pulled_text: str,
) -> ValidationResult:
    """Given a candidate `Citation` (i.e., what we read from the parent
    deed's recital) and the actual text of the deed at the cited
    Liber/folio, decide whether the citation is correct.

    Match criteria (any failure → not matched):
      - Pulled deed's date matches recital's date (year + month)
      - Pulled deed's grantor and grantee match recital's grantor/grantee
        (case-insensitive substring match, accounting for surname variations)

    The pulled deed's first ~3000 characters are usually enough — parties
    and date appear in the opening sentence of the deed body.
    """
    head = pulled_text[:3000]

    # Date match — at least the year, ideally the month
    cand_year = re.search(r"\d{4}", candidate.date_text)
    if not cand_year:
        return ValidationResult(False, "couldn't parse year from candidate date",
                                candidate)
    if cand_year.group(0) not in head:
        return ValidationResult(False, f"year {cand_year.group(0)} not in pulled deed",
                                candidate)

    # Party match — at least one surname token from grantor + at least one
    # from grantee should appear in the pulled deed body
    if not _surname_present(candidate.grantor, head):
        return ValidationResult(
            False, f"grantor surname not found in pulled deed", candidate
        )
    if not _surname_present(candidate.grantee, head):
        return ValidationResult(
            False, f"grantee surname not found in pulled deed", candidate
        )

    return ValidationResult(True, "parties and year both match", candidate)


def _surname_present(party: str, body: str) -> bool:
    """Heuristic: any all-caps or capitalized token of length ≥ 4 in
    `party` should appear in `body` (case-insensitive).

    Skips ubiquitous filler tokens (his/her/wife/of/the/etc.).
    """
    skip = {
        "his", "her", "wife", "husband", "and", "the", "of", "for", "etux",
        "etal", "to", "unto", "said", "this", "that", "is", "as", "an",
    }
    body_lc = body.lower()
    surnames = [
        t for t in re.findall(r"[A-Za-z]{4,}", party)
        if t.lower() not in skip
    ]
    return any(s.lower() in body_lc for s in surnames)


# ---------------------------------------------------------------------------
# 5. Retry / fallback strategy when validation fails
# ---------------------------------------------------------------------------

@dataclass
class FolioScanRange:
    """A range of folios to try when the cited folio doesn't validate.

    Strategy: scan ±N folios around the cited folio in the same volume,
    looking for the deed whose parties + date match.
    """
    clerk: str
    book: int
    folio_center: int
    spread: int = 5

    def candidates(self) -> Iterable[int]:
        for delta in (0, -1, 1, -2, 2, -3, 3, -4, 4, -5, 5):
            yield self.folio_center + delta


def fallback_image_variants(enhanced_set: EnhancedSet) -> list[Path]:
    """Order in which to try alternate image variants when the first read
    fails downstream validation.
    """
    return [
        enhanced_set.enhanced_zoom_2x,
        enhanced_set.inverted,
        enhanced_set.threshold,
        enhanced_set.cropped_recital,
    ]


# ---------------------------------------------------------------------------
# 6. Top-level entry point
# ---------------------------------------------------------------------------

def process_deed_pdf(
    pdf_path: str | Path,
    work_dir: str | Path,
) -> list[EnhancedSet]:
    """Convenience: render + enhance every page of a deed PDF and return
    the set of paths a multimodal LLM should read.

    The LLM agent reads each enhanced PNG, transcribes the deed body to
    plain text, then this module's `parse_citations()` pulls the chain
    information out of the transcribed text.
    """
    return render_and_enhance(pdf_path, work_dir)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python deed_pipeline.py <deed.pdf> <work_dir>", file=sys.stderr)
        sys.exit(2)

    src, work = sys.argv[1], sys.argv[2]
    sets = process_deed_pdf(src, work)
    for s in sets:
        print(f"{s.base.name}: enhanced={s.enhanced.name} 2x={s.enhanced_zoom_2x.name}")
