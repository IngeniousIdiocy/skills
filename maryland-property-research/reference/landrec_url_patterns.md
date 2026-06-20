# landrec.msa.maryland.gov — URL Grammar

The Maryland State Archives MDLandRec portal exposes a handful of
URL endpoints. They are mostly stable across years (no fragment-only
routing, no SPA), so deep-linking and Playwright automation against
them is reliable. This document is the reverse-engineered map of the
endpoints the skill drives.

## Authentication

All deed-content endpoints require an authenticated session. The skill
does **not** automate login — login is interactive (occasional CAPTCHA,
sometimes T&C re-acceptance) and the user does it once at session start.
After login, the session cookie carries authentication on all subsequent
requests including direct PDF URLs.

If a fetch returns the login page instead of a deed PDF, the session has
expired (typical timeout: 30 minutes idle). Surface a clear "session
dropped, please log in again" message rather than retrying.

## Endpoints

### 1. Search page

```
https://landrec.msa.maryland.gov/Pages/Search.aspx
```

The user-facing entry point. Hosts:
- A county selector (dropdown of all 24 MD counties + Baltimore City)
- A clerk/book/page jump form (the field IDs are stable; see below)
- A grantor/grantee name index search

**Always navigate here to switch counties.** Do *not* edit the `cid`
URL parameter directly — it sometimes drops the auth cookies, forcing
a re-login. Use the in-page dropdown.

#### Stable form-field IDs (as of May 2026)

```
body_ddlCounty             — county dropdown (postal-style cids: BC, BA, AA, ...)
body_tbjtnvBook            — book jump field
body_tbjtnvPage            — page (folio) jump field
body_btnjtnvSubmit         — jump submit button
body_tbgnGrantor           — grantor name search
body_tbgnGrantee           — grantee name search
```

Re-snapshot the form before relying on these in case landrec was
re-themed; they are not officially documented.

### 2. Jump-results disambiguation

```
https://landrec.msa.maryland.gov/Pages/JumpResults.aspx?cid={CID}&bk={BOOK}&pg={PAGE}
```

Reached by submitting the jump form. When a `(book, page)` pair maps to
exactly one volume, landrec immediately redirects to the Viewer. When the
book number is ambiguous (the same number existed under multiple clerks
in different eras — common for low book numbers like `1`, `2`, `3`), this
page renders a list of candidate volumes with their MSA accession numbers
and date ranges.

**Pick the candidate whose date range contains the recital's stated
deed date.** If you guess wrong here, the viewer will load the wrong
volume and the citation cross-validation will fail.

### 3. Single-deed viewer

```
https://landrec.msa.maryland.gov/Pages/Viewer.aspx
  ?cid={CID}                  e.g. BC, BA
  &q=CE                       always "CE" for "Court of Equity" — keep verbatim
  &sr={SERIES}                MSA series number, e.g. 62 for Baltimore Co.,
                              94 for Baltimore City circuit court land records.
                              The skill discovers this from JumpResults.
  &ssu={VOLUME}               the volume (book) number, padded if landrec
                              padded it on the JumpResults link
  &sp={START_PAGE}            first folio of the deed
  &ep={END_PAGE}              last folio of the deed
  &view=I                     "I" = image viewer; "T" exists but is rarely used
  &first=true                 always include
```

#### Page-range tactics

- A 1900s-era deed is typically 5–7 folios long, with the recording
  stamp on the last folio. The skill should set `ep ≥ sp + 5` to capture
  the entire deed plus the recording stamp without paging.
- For modern deeds (~1990+) where deeds are usually single-folio, `ep =
  sp` works, but the skill defaults to `ep = sp + 5` for safety — extra
  folios are cheap.
- The viewer's iframe loads the underlying PDF lazily; wait for the
  iframe `src` to populate before extracting the PDF URL.

### 4. Direct PDF (cookies required)

```
https://landrec.msa.maryland.gov/PDF/{ACCESSION}/MSA%20CE%20{SR}-{SSU}%20p.{SP}%20to%20p.{EP}.pdf
```

The viewer's iframe `src` attribute resolves to a URL of this shape.
Navigating to the URL directly while the session cookie is set triggers
a download; the skill saves the file straight to `~/Downloads/` with the
caller-controlled name (see `build_outputs.raw_deed_filename()`).

`ACCESSION` is the MSA accession code for the volume — e.g.
`MSA%20CE%2062-343`. It comes back from JumpResults and the skill plumbs
it through to the filename.

## County code (`cid`) table

| `cid` | County |
|---|---|
| `AL` | Allegany |
| `AA` | Anne Arundel |
| `BC` | Baltimore City |
| `BA` | Baltimore County |
| `CV` | Calvert |
| `CR` | Caroline |
| `CL` | Carroll |
| `CE` | Cecil |
| `CH` | Charles |
| `DO` | Dorchester |
| `FR` | Frederick |
| `GA` | Garrett |
| `HA` | Harford |
| `HO` | Howard |
| `KE` | Kent |
| `MO` | Montgomery |
| `PG` | Prince George's |
| `QA` | Queen Anne's |
| `SM` | St. Mary's |
| `SO` | Somerset |
| `TA` | Talbot |
| `WA` | Washington |
| `WI` | Wicomico |
| `WO` | Worcester |

(SDAT uses two-digit numeric codes for the same counties — see
`scripts/sdat_lookup.py:COUNTY_CODES` for the cross-reference.)

## Pre-1851 / Howard County peculiarity

Howard County was carved out of Anne Arundel County in 1851. Pre-1851
land records for any current Howard parcel are recorded in **Anne Arundel**
records (`cid=AA`), not Howard. Apply the same logic for other later-formed
counties: Wicomico (1867 from Worcester + Somerset), Garrett (1872 from
Allegany).

## Pre-1918 Baltimore annexation

The 1918 Baltimore annexation moved a swath of north Baltimore (Roland
Park, Guilford, parts of Mt. Washington, etc.) from Baltimore County into
Baltimore City. Pre-1918 deeds for these properties are in `cid=BA`;
post-1918 are in `cid=BC`. Earlier Baltimore annexations (1816, 1888)
affect older central-Baltimore neighborhoods analogously.

## Recovery from dropped session

If a fetch returns the login page (response body contains `loginContent`
or `Forms/Login.aspx`):

1. Stop automation.
2. Tell the user the session dropped and ask them to re-log-in at
   `https://landrec.msa.maryland.gov`.
3. Wait for confirmation.
4. Resume with the same Viewer / PDF URL — the cookie is fresh and the
   request will succeed.

Do not loop on retry; landrec's login page does not auto-redirect back
to your intended URL.
