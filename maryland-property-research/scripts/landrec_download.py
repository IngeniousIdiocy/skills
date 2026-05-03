"""
landrec_download.py — Python side of the landrec deed-PDF download flow.

The download itself is Playwright-MCP-driven (see SKILL.md "Downloading deed
PDFs autonomously" for the JS half). This module:

  - Builds the Viewer URLs the orchestrator should pass to browser_navigate.
  - Decodes the base64 JSON blob that the in-page fetch deposits via
    `browser_evaluate(filename=...)` into a real PDF file on disk.
  - Validates the resulting file (size, page count, "is this an HTML error
    page renamed .pdf?").

The orchestrator pattern in pseudocode:

    1. url = build_viewer_url(cid="BA", sr=62, ssu=343, sp=585, ep=590)
    2. browser_navigate(url)
    3. iframe_src = browser_evaluate(... iframe-src extractor ...)
    4. browser_evaluate(filename="deed_b64.json", function=BASE64_FETCH_JS.format(url=iframe_src))
    5. out_path = decode_b64_blob_to_pdf(playwright_output_dir / "deed_b64.json", out_pdf_path)
    6. validate_landrec_pdf(out_path)
"""

from __future__ import annotations

import base64
import json
import os
import pathlib
from dataclasses import dataclass
from typing import Optional


# ---------------------------------------------------------------------------
# 1. URL construction
# ---------------------------------------------------------------------------

LANDREC_BASE = "https://landrec.msa.maryland.gov"


def build_viewer_url(
    *,
    cid: str,           # "BA", "BC", "AA", ...
    sr: int,            # MSA series number, e.g. 62 for Baltimore Co.
    ssu: int,           # volume / book number
    sp: int,            # start page (folio)
    ep: Optional[int] = None,  # end page; defaults to sp + 5
) -> str:
    """Build the Viewer URL for a given citation.

    Per SKILL.md, set ep ≥ sp + 5 to capture multi-folio deeds with their
    trailing acknowledgments and recording stamps. `ep` defaults to `sp + 5`.
    """
    if ep is None:
        ep = sp + 5
    return (
        f"{LANDREC_BASE}/Pages/Viewer.aspx?"
        f"cid={cid}&q=CE&sr={sr}&ssu={ssu}&sp={sp}&ep={ep}&view=I&first=true"
    )


# ---------------------------------------------------------------------------
# 2. JS snippets the orchestrator hands to browser_evaluate
# ---------------------------------------------------------------------------

# Returns the array of iframe `src` attributes on the page.
# After browser_navigate(viewer_url), this is the way to discover the
# direct PDF URL that the viewer's iframe is loading.
JS_GET_IFRAME_SRCS = (
    "() => Array.from(document.querySelectorAll('iframe')).map(f => f.src)"
)


# In-page fetch + chunked base64 encoder. Format with the iframe `src` URL
# (single-quote it; we do not interpolate JS-side). Produces:
#   { "status": <int>, "b64": "<base64>" }
# Hand to browser_evaluate(filename="deed_b64.json", function=<this>) so that
# the JSON blob lands in the Playwright-MCP host output dir.
JS_FETCH_PDF_AS_BASE64 = """async () => {{
    const r = await fetch('{url}', {{credentials: 'include'}});
    const buf = await r.arrayBuffer();
    const bytes = new Uint8Array(buf);
    let bin = '';
    for (let i = 0; i < bytes.length; i += 0x8000) {{
        bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
    }}
    return {{status: r.status, b64: btoa(bin)}};
}}"""


def fetch_js(iframe_src_url: str) -> str:
    """Render JS_FETCH_PDF_AS_BASE64 with the iframe src URL substituted.

    The URL is single-quoted in the generated JS, so it must not contain
    a literal single quote (landrec URLs never do)."""
    if "'" in iframe_src_url:
        raise ValueError(
            f"iframe src contains a single quote — refusing to format JS: "
            f"{iframe_src_url!r}"
        )
    return JS_FETCH_PDF_AS_BASE64.format(url=iframe_src_url)


# ---------------------------------------------------------------------------
# 3. JSON-blob decoder (called from Python after the JS has run)
# ---------------------------------------------------------------------------

@dataclass
class DownloadResult:
    out_path: pathlib.Path
    bytes_written: int
    http_status: int


class LandrecDownloadError(RuntimeError):
    """Raised when the JSON blob indicates a non-200 fetch status, or when
    the decoded bytes look like an HTML error page rather than a PDF."""


def decode_b64_blob_to_pdf(
    blob_path: os.PathLike | str,
    out_pdf_path: os.PathLike | str,
) -> DownloadResult:
    """Decode the JSON blob produced by JS_FETCH_PDF_AS_BASE64 into a PDF
    file on disk.

    Raises LandrecDownloadError if the JS-side fetch returned non-200 or if
    the bytes don't start with the PDF magic. (HTML error pages with the
    landrec login form rendered are the most common failure here, indicating
    an expired session.)
    """
    blob_path = pathlib.Path(blob_path)
    out_pdf_path = pathlib.Path(out_pdf_path)

    data = json.loads(blob_path.read_text())

    status = int(data.get("status", 0))
    if status != 200:
        raise LandrecDownloadError(
            f"landrec returned HTTP {status} — session may have expired. "
            f"Re-log-in in the Playwright browser and retry."
        )

    pdf_bytes = base64.b64decode(data["b64"])

    if not pdf_bytes.startswith(b"%PDF-"):
        # Most likely the response was the login page HTML
        head = pdf_bytes[:200].decode("utf-8", errors="replace")
        raise LandrecDownloadError(
            f"response did not start with %PDF- magic; first 200 bytes were: "
            f"{head!r}. Session likely expired."
        )

    out_pdf_path.parent.mkdir(parents=True, exist_ok=True)
    out_pdf_path.write_bytes(pdf_bytes)

    return DownloadResult(
        out_path=out_pdf_path,
        bytes_written=len(pdf_bytes),
        http_status=status,
    )


# ---------------------------------------------------------------------------
# 4. Sanity-check helper
# ---------------------------------------------------------------------------

def validate_landrec_pdf(
    pdf_path: os.PathLike | str,
    *,
    min_bytes: int = 50_000,
    min_pages: int = 1,
) -> tuple[int, int]:
    """Cheap sanity checks: file size and page count. Returns (bytes, pages).

    Raises LandrecDownloadError if either check fails. A real multi-folio
    deed scan is typically 1–4 MB; <50 KB usually means an HTML error page
    misrouted into the PDF path.
    """
    pdf_path = pathlib.Path(pdf_path)
    size = pdf_path.stat().st_size
    if size < min_bytes:
        raise LandrecDownloadError(
            f"PDF too small ({size} bytes < {min_bytes}); likely an error page."
        )

    # Lazy import — fitz is heavy; callers that don't validate page count
    # shouldn't pay for it.
    import fitz  # noqa: WPS433
    with fitz.open(pdf_path) as doc:
        pages = len(doc)
    if pages < min_pages:
        raise LandrecDownloadError(
            f"PDF has only {pages} pages (expected ≥ {min_pages})."
        )
    return size, pages
