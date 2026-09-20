"""
sdat_lookup.py — SDAT (Maryland State Department of Assessments and Taxation)
property-record lookup helpers.

This module is the *parsing* and *step-documentation* half of the SDAT lookup.
The Playwright driving itself happens via the Playwright MCP from the calling
agent (Claude Code), because each step needs human-readable pause/wait points.
This file provides:

  - Canonical step sequence (`SDAT_FLOW`, used as a runbook the agent reads)
  - Form-field selectors (`SELECTORS`)
  - County code table (`COUNTY_CODES`)
  - `parse_sdat_result(html_or_text)` — extract the structured fields out of
    the result page text after Playwright has rendered it
  - `slugify_street(address)` — split a street address into the (number, name)
    pair SDAT expects, *without* the street-type suffix that breaks its search

Usage from the orchestrator (pseudo-code):

    from scripts.sdat_lookup import (
        SDAT_FLOW, SELECTORS, parse_sdat_result, slugify_street
    )

    number, name = slugify_street("4503 Roland Avenue")
    # → ("4503", "Roland")

    # Drive Playwright via MCP using SDAT_FLOW + SELECTORS as a runbook.
    # After the result page renders, dump the page text and call:
    record = parse_sdat_result(page_text)
    # → {
    #     "owner": "...",
    #     "address": "...",
    #     "deed_reference": "JFC 2021/85",
    #     "legal_description": "...",
    #     "lot_size_sf": 7500,
    #     "lot_dim": "50 x 150",
    #     "year_built": 1900,                # SDAT default - validate
    #     "use_code": "Residential",
    #     "stories": 2.5,
    #     "tax_id": "27 12 1234 567",
    #     ...
    #   }

The deed_reference field is what feeds into deed_pipeline.py for the
landrec walk-back.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# 1. Canonical SDAT URL + Playwright-driven step runbook
# ---------------------------------------------------------------------------

SDAT_BASE_URL = "https://sdat.dat.maryland.gov/RealProperty/Pages/default.aspx"

# County codes — SDAT's "County Selection" dropdown uses the two-digit
# numeric county code, NOT the postal abbreviation. (Use the postal abbrev
# only when constructing landrec URLs — see reference/landrec_url_patterns.md.)
COUNTY_CODES: dict[str, dict[str, str]] = {
    "01": {"name": "Allegany",       "landrec_cid": "AL"},
    "02": {"name": "Anne Arundel",   "landrec_cid": "AA"},
    "03": {"name": "Baltimore City", "landrec_cid": "BC"},
    "04": {"name": "Baltimore County", "landrec_cid": "BA"},
    "05": {"name": "Calvert",        "landrec_cid": "CV"},
    "06": {"name": "Caroline",       "landrec_cid": "CR"},
    "07": {"name": "Carroll",        "landrec_cid": "CL"},
    "08": {"name": "Cecil",          "landrec_cid": "CE"},
    "09": {"name": "Charles",        "landrec_cid": "CH"},
    "10": {"name": "Dorchester",     "landrec_cid": "DO"},
    "11": {"name": "Frederick",      "landrec_cid": "FR"},
    "12": {"name": "Garrett",        "landrec_cid": "GA"},
    "13": {"name": "Harford",        "landrec_cid": "HA"},
    "14": {"name": "Howard",         "landrec_cid": "HO"},
    "15": {"name": "Kent",           "landrec_cid": "KE"},
    "16": {"name": "Montgomery",     "landrec_cid": "MO"},
    "17": {"name": "Prince George's", "landrec_cid": "PG"},
    "18": {"name": "Queen Anne's",   "landrec_cid": "QA"},
    "19": {"name": "St. Mary's",     "landrec_cid": "SM"},
    "20": {"name": "Somerset",       "landrec_cid": "SO"},
    "21": {"name": "Talbot",         "landrec_cid": "TA"},
    "22": {"name": "Washington",     "landrec_cid": "WA"},
    "23": {"name": "Wicomico",       "landrec_cid": "WI"},
    "24": {"name": "Worcester",      "landrec_cid": "WO"},
}


def county_code_for(name_or_cid: str) -> Optional[str]:
    """
    Look up the SDAT county code (the two-digit string used in the
    County Selection dropdown) given either the county name or the
    landrec cid. Case-insensitive.

    Returns None if no match.
    """
    key = name_or_cid.strip().lower()
    for code, meta in COUNTY_CODES.items():
        if meta["name"].lower() == key or meta["landrec_cid"].lower() == key:
            return code
    return None


# Form-field selectors (kept in one place so a SDAT redesign needs one edit).
# These are stable as of the May 2026 SDAT site. Agent should re-snapshot
# the form before relying on them in case SDAT has changed.
SELECTORS: dict[str, str] = {
    # Step 1: County + search-method picker
    "county_dropdown":          "select#cphMainContentArea_ucSearchType_wzrdRealPropertySearch_ddlCounty",
    "search_method_dropdown":   "select#cphMainContentArea_ucSearchType_wzrdRealPropertySearch_ddlSearchType",
    "search_method_value_addr": "STREET ADDRESS",
    "continue_button":          "input#cphMainContentArea_ucSearchType_wzrdRealPropertySearch_StartNavigationTemplateContainerID_btnContinue",

    # Step 2: Street-address fields
    "street_number_field":      "input#cphMainContentArea_ucSearchType_wzrdRealPropertySearch_txtStreetNumber",
    "street_name_field":        "input#cphMainContentArea_ucSearchType_wzrdRealPropertySearch_txtStreetName",
    "next_button":              "input#cphMainContentArea_ucSearchType_wzrdRealPropertySearch_StepNavigationTemplateContainerID_btnStepNextButton",

    # Step 3: Result page — fields scraped by parse_sdat_result()
    # (no selectors needed; we parse the rendered text)
}


SDAT_FLOW: list[str] = [
    # The agent reads this sequence and executes each step via Playwright MCP.
    "1. Navigate to {SDAT_BASE_URL}.",
    "2. browser_snapshot to confirm the County Selection dropdown is present.",
    "3. browser_select_option on county_dropdown — value is the 2-digit code (see COUNTY_CODES).",
    "4. browser_select_option on search_method_dropdown — value 'STREET ADDRESS'.",
    "5. browser_click on continue_button.",
    "6. browser_wait_for the street-address fields to appear.",
    "7. browser_fill_form (NOT browser_type — type lets stray user keystrokes interleave) with:",
    "      street_number_field  = <number from slugify_street()>",
    "      street_name_field    = <name from slugify_street() — NO street-type suffix>",
    "8. browser_click on next_button.",
    "9. browser_wait_for the result page (look for 'Property Account Identifier').",
    "   - If multiple parcels match, SDAT shows a result list — pick the row whose",
    "     'Premise Address' matches the user's input most exactly, then click into it.",
    "10. browser_snapshot OR evaluate `document.body.innerText` to get the raw page text.",
    "11. Pass that text to parse_sdat_result() below.",
    "",
    "WARNING: Tell the user to NOT type in the Playwright window during steps 3-9.",
    "Stray keystrokes land in the focused form field (often the street_name_field)",
    "and corrupt the search — e.g., 'Roland' becomes 'Roland0' and the search fails.",
]


# ---------------------------------------------------------------------------
# 2. Address slug helper
# ---------------------------------------------------------------------------

# Street-type suffixes that SDAT does NOT want in the street_name_field.
# Strip these from the input before searching. The list is the standard USPS
# street suffix abbreviations plus the long forms.
_STREET_SUFFIXES: set[str] = {
    "ave", "avenue",
    "blvd", "boulevard",
    "cir", "circle",
    "ct", "court",
    "dr", "drive",
    "hwy", "highway",
    "ln", "lane",
    "pkwy", "parkway",
    "pl", "place",
    "rd", "road",
    "row",
    "sq", "square",
    "st", "street",
    "ter", "terrace",
    "trl", "trail",
    "way",
}

_DIRECTIONALS: set[str] = {
    "n", "north", "s", "south", "e", "east", "w", "west",
    "ne", "northeast", "nw", "northwest",
    "se", "southeast", "sw", "southwest",
}


def slugify_street(address: str) -> tuple[str, str]:
    """
    Split a free-form street address into (number, street_name) for SDAT,
    stripping the street-type suffix (Ave, St, Rd, etc.) which makes SDAT's
    search return zero results.

    Examples:
        "4503 Roland Avenue"        -> ("4503", "Roland")
        "123 N Charles St"          -> ("123", "N Charles")
        "9999 Old Frederick Rd. #B" -> ("9999", "Old Frederick")
        "415 Light Street, Unit 2"  -> ("415", "Light")

    The unit number is dropped — SDAT searches by parcel, not by unit.
    Directional prefixes (N/S/E/W) are kept because SDAT distinguishes
    "N Charles" from "S Charles" with the directional in the name field.

    City / state / ZIP are dropped (a comma or the word "Baltimore" /
    "Maryland" / "MD" terminates the street portion).

    Raises ValueError if the input has no street-number prefix.
    """
    raw = address.strip()
    # Cut at the first comma — anything after is city/state/ZIP/unit.
    if "," in raw:
        raw = raw.split(",", 1)[0]
    # Cut at " unit ", " apt ", " #" — unit indicators.
    raw = re.split(r"\s+(?:unit|apt|apartment|suite|ste|#)\b", raw, maxsplit=1, flags=re.I)[0]
    raw = raw.strip().rstrip(".")

    parts = raw.split()
    if not parts:
        raise ValueError(f"empty address: {address!r}")

    # First token must be the street number (digits, optionally hyphenated).
    if not re.match(r"^\d+[\d-]*$", parts[0]):
        raise ValueError(f"address has no leading street number: {address!r}")
    number = parts[0]

    # Trim trailing street-suffix tokens.
    name_tokens = parts[1:]
    while name_tokens and name_tokens[-1].lower().rstrip(".") in _STREET_SUFFIXES:
        name_tokens.pop()

    if not name_tokens:
        raise ValueError(f"address has no street name after stripping suffix: {address!r}")

    name = " ".join(name_tokens)
    return number, name


def address_slug(address: str) -> str:
    """
    Return a filename-safe slug of the address — used to name the output
    PDFs and raw deed PDFs in Downloads/.

    "4503 Roland Avenue, Baltimore, MD" -> "4503-roland"
    """
    number, name = slugify_street(address)
    name_slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return f"{number}-{name_slug}"


# ---------------------------------------------------------------------------
# 3. Result-page parser
# ---------------------------------------------------------------------------

@dataclass
class SdatRecord:
    """Structured SDAT property record. Any field may be None if SDAT
    didn't render it for this parcel."""
    address: Optional[str] = None
    owner: Optional[str] = None
    co_owner: Optional[str] = None
    mailing_address: Optional[str] = None
    tax_id: Optional[str] = None
    use_code: Optional[str] = None
    legal_description: Optional[str] = None
    deed_reference: Optional[str] = None    # e.g. "JFC/ 2021/ 85" -> normalized
    deed_reference_raw: Optional[str] = None
    lot_size_sf: Optional[int] = None
    lot_size_acres: Optional[float] = None
    lot_dim: Optional[str] = None           # e.g. "50 x 150"
    year_built: Optional[int] = None
    stories: Optional[float] = None
    grade: Optional[str] = None
    structure_area_sf: Optional[int] = None
    sale_date: Optional[str] = None
    sale_price: Optional[int] = None
    transfer_date: Optional[str] = None
    assessment_total: Optional[int] = None
    raw_fields: dict[str, str] = field(default_factory=dict)


# Regexes for the labelled-pair format SDAT emits when innerText'd.
# The page is a series of "Label: Value\n" pairs after rendering.
# (Some labels span lines; the patterns below are loose-tolerant.)
_FIELD_PATTERNS: dict[str, re.Pattern] = {
    "address": re.compile(r"Premise Address[:\s]+(.+?)(?:\n|$)", re.I),
    "owner": re.compile(r"Owner Name[:\s]+(.+?)(?:\n|$)", re.I),
    "co_owner": re.compile(r"(?:Owner Name 2|Co-?Owner)[:\s]+(.+?)(?:\n|$)", re.I),
    "mailing_address": re.compile(r"Mailing Address[:\s]+(.+?)(?:\n|$)", re.I),
    "tax_id": re.compile(r"Account (?:Identifier|Number|ID)[:\s]+(.+?)(?:\n|$)", re.I),
    "use_code": re.compile(r"(?:Principal Residence|Use Code|Property Use)[:\s]+(.+?)(?:\n|$)", re.I),
    "legal_description": re.compile(r"Legal Description[:\s]+(.+?)(?:\n\s*\n|$)", re.I | re.S),
    "deed_reference_raw": re.compile(r"Deed Reference[:\s/]+(.+?)(?:\n|$)", re.I),
    "lot_size_sf": re.compile(r"(?:Land Area|Lot Size)[:\s]+([\d,]+)\s*(?:SF|Sq\.?\s*Ft\.?|square\s*feet)", re.I),
    "lot_size_acres": re.compile(r"(?:Land Area|Lot Size)[:\s]+([\d.]+)\s*Acres?", re.I),
    "lot_dim": re.compile(r"(?:Lot Dimensions?|Frontage)[:\s]+([\d.]+\s*(?:x|by|X)\s*[\d.]+)", re.I),
    "year_built": re.compile(r"(?:Primary Structure Built|Year Built)[:\s]+(\d{4})", re.I),
    "stories": re.compile(r"Stories?[:\s]+([\d.]+)", re.I),
    "grade": re.compile(r"Quality Grade[:\s]+(.+?)(?:\n|$)", re.I),
    "structure_area_sf": re.compile(r"(?:Above Grade Living Area|Finished Area|Structure Area)[:\s]+([\d,]+)", re.I),
    "sale_date": re.compile(r"(?:Last (?:Sale|Transfer) Date|Sale Date)[:\s]+([\d/]+)", re.I),
    "sale_price": re.compile(r"(?:Sale Price|Last Sale Price)[:\s]+\$?([\d,]+)", re.I),
    "transfer_date": re.compile(r"(?:Transfer Date|Date of Transfer)[:\s]+([\d/]+)", re.I),
    "assessment_total": re.compile(r"(?:Total Assessment|Total Phase-In Value)[:\s]+\$?([\d,]+)", re.I),
}


def _strip_html(s: str) -> str:
    """Cheap HTML-to-text. If the caller already passed innerText, this
    is a no-op."""
    if "<" not in s:
        return s
    s = re.sub(r"<script[^>]*>.*?</script>", "", s, flags=re.I | re.S)
    s = re.sub(r"<style[^>]*>.*?</style>", "", s, flags=re.I | re.S)
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"</(p|div|tr|li|h[1-6])>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    # Decode the few HTML entities SDAT actually uses.
    s = s.replace("&nbsp;", " ").replace("&amp;", "&").replace("&#39;", "'")
    s = s.replace("&quot;", '"').replace("&lt;", "<").replace("&gt;", ">")
    # Collapse runs of internal whitespace per line.
    out_lines = []
    for ln in s.splitlines():
        ln = re.sub(r"[ \t]+", " ", ln).strip()
        out_lines.append(ln)
    # Collapse runs of blank lines.
    text = "\n".join(out_lines)
    return re.sub(r"\n{3,}", "\n\n", text)


def _to_int(s: str) -> Optional[int]:
    try:
        return int(s.replace(",", "").strip())
    except (ValueError, AttributeError):
        return None


def _to_float(s: str) -> Optional[float]:
    try:
        return float(s.replace(",", "").strip())
    except (ValueError, AttributeError):
        return None


def _normalize_deed_ref(raw: str) -> str:
    """
    SDAT emits the deed reference in several varied formats:
        "JFC/ 2021/ 85"
        "JFC 2021 / 85"
        "/JFC/02021/00085"
        "  SEB/  6592/   38"

    Normalize to "<CLERK> <BOOK>/<FOLIO>" with whitespace and zero-pads
    stripped.
    """
    parts = re.split(r"[\s/]+", raw.strip())
    parts = [p for p in parts if p]
    if len(parts) >= 3:
        clerk = parts[0]
        book = parts[1].lstrip("0") or "0"
        folio = parts[2].lstrip("0") or "0"
        return f"{clerk} {book}/{folio}"
    return raw.strip()


def parse_sdat_result(html_or_text: str) -> SdatRecord:
    """
    Parse the rendered SDAT result page into a structured record.

    Pass either the raw HTML or the already-extracted innerText. Fields
    SDAT did not render are left as None on the returned SdatRecord.

    Always cross-validate `year_built` against the chain — SDAT defaults
    that field to 1900 (or other round-number defaults like 1920) for
    properties whose actual build year was never researched. See the
    main SKILL.md "Known gotchas #10".
    """
    text = _strip_html(html_or_text)
    rec = SdatRecord(raw_fields={})

    for fname, pat in _FIELD_PATTERNS.items():
        m = pat.search(text)
        if not m:
            continue
        val = m.group(1).strip().rstrip(",")
        rec.raw_fields[fname] = val
        if fname in {"lot_size_sf", "year_built", "structure_area_sf",
                     "sale_price", "assessment_total"}:
            setattr(rec, fname, _to_int(val))
        elif fname in {"lot_size_acres", "stories"}:
            setattr(rec, fname, _to_float(val))
        elif fname == "deed_reference_raw":
            rec.deed_reference_raw = val
            rec.deed_reference = _normalize_deed_ref(val)
        else:
            setattr(rec, fname, val)

    return rec


# ---------------------------------------------------------------------------
# 4. CLI smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":  # pragma: no cover
    # Exercise slugify_street against a few representative inputs.
    samples = [
        "4503 Roland Avenue",
        "123 N Charles St",
        "9999 Old Frederick Rd. #B",
        "415 Light Street, Unit 2",
        "8000 York Road, Towson, MD 21204",
        "1 W Pratt St",
    ]
    for s in samples:
        try:
            n, name = slugify_street(s)
            print(f"{s!r:50s} -> ({n!r}, {name!r})  slug={address_slug(s)}")
        except ValueError as e:
            print(f"{s!r:50s} -> ERROR: {e}")
