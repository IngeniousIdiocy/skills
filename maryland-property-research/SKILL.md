---
name: maryland-property-research
description: Trace the complete recorded deed chain for a Maryland property back to its originating developer conveyance and produce a typed title-chain summary PDF plus a typed transcription of the originating deed (with covenants). Trigger when the user gives a Maryland street address and asks for title research, covenant analysis, deed history, or restrictive-covenant review — e.g., "research the title for this address", "what covenants apply to my property", "trace the deed chain back to the developer", "are there fence/setback restrictions on this lot". Particularly applicable to historic developer-platted neighborhoods (Roland Park, Guilford, Homeland, Mt. Washington, Bolton Hill, Sudbrook Park, Greenbelt). The skill drives landrec.msa.maryland.gov via the Playwright MCP. The user logs in once at the landrec login page; after that the skill operates autonomously, including reading faint cursive citations via image-enhancement (2× LANCZOS upscale + Pillow autocontrast/sharpen) and self-correcting via a cross-validation loop. Skip if the property is not in Maryland (skill is tied to Maryland State Archives' landrec portal).
---

# maryland-property-research — Maryland deed-chain title research

## Why this skill exists

Recorded deed history is hard:

- Maryland's land-records portal (**landrec.msa.maryland.gov**, run by Maryland State Archives) is paywalled-by-login and uses a non-obvious clerk/book/folio citation grammar that varies across decades and jurisdictions.
- Restrictive covenants imposed by historic developers almost never get re-recited in modern deeds. They run with the land in equity, but the **only** place to read them is the original developer deed at the bottom of the chain.
- 1900s-era deed scans are cursive, often faint, and citations to prior deeds (clerk prefix + book + folio) misread catastrophically — one wrong digit in a folio number sends you pulling the wrong deed for a neighbor's property and re-doing the entire analysis.
- Modern Maryland deeds use special-warranty-only language and add no new covenants; the chain backward through them tells you almost nothing without going all the way to the developer.

This skill encodes the pipeline — SDAT lookup → landrec walk-back → image-enhance-then-read → cross-validate → produce two delivery PDFs — including the specific image-processing recipe that makes faint-cursive folio numbers reliably legible. Without that recipe, OCR is consistently wrong on book/folio digits.

## When to trigger

Use this skill when the user asks for any of:

- "Research the title for `<Maryland address>`"
- "Trace the deed chain back to the developer"
- "What covenants/restrictions apply to my property"
- "Is there a fence/setback/use restriction on `<Maryland address>`"
- Historic-neighborhood covenant questions ("can I build X", "do I need ARC approval")
- "Build me a title chain summary for `<Maryland address>`"
- "Find the original developer's deed for my house"

**Skip** when:

- The property is not in Maryland (this skill is tied to landrec.msa.maryland.gov — for other states, the chain pattern is the same but the data source is different).
- The user only wants the *current* owner / assessment (use SDAT directly without going into landrec).
- The user explicitly says they want only title-insurance interpretation or legal advice — output of this skill is research, not legal opinion.

## Pre-flight checks

Before driving any browser:

1. **Playwright MCP must be installed.** Check with `claude mcp list 2>&1 | grep -i playwright`. If absent, install:
   ```bash
   claude mcp add playwright npx -- "@playwright/mcp@latest"
   ```
   The user must restart Claude Code after install before the `mcp__playwright__*` tools become available.

2. **Python + libraries.** Check with:
   ```bash
   python -c "import fitz, pypdf, PIL, reportlab, numpy" 2>&1
   ```
   Install missing pieces with `python -m pip install pymupdf pypdf Pillow reportlab numpy --quiet`.

3. **landrec login.** Navigate the Playwright browser to `https://landrec.msa.maryland.gov/Pages/Search.aspx`. Tell the user:

   > "Please log in to landrec in the Playwright browser tab now. The skill needs an authenticated session to download deed PDFs. Once you're at the search page, reply 'logged in' and I'll continue. **Don't type in the Playwright window during automation** — text aimed at it lands in whatever form field happens to be focused and corrupts citations."

   Wait for confirmation before proceeding.

## Known gotchas — read this section before doing anything

These are the failure modes observed in the original session. Reproduce the fixes verbatim.

### 1. Faint cursive scans need TWO different enhancement passes — one for digits, one for letters

PyMuPDF rendering at default DPI plus direct Read of the PNG produces wrong readings on essentially every faint scan. But there is a second, sneakier failure mode: **a single enhancement recipe that helps digits actually hurts cursive proper names**, because aggressive contrast/sharpening collapses ascenders and descenders into similar-looking glyphs (`S↔K`, `n-o-w↔n-o-x`, `Patrick↔Parish`). The pipeline observed this in real-world testing where the citation digits were correct but the grantee's surname was systematically wrong across the entire chain.

The fix is **two enhancement profiles**, applied to every page, used for different fields:

| Field type | Use this variant | Profile parameters |
|---|---|---|
| Book number (e.g., "WPC 343") | `enhanced` / `enhanced_zoom_2x` | DIGITS: contrast 2.4×, sharpness 2.0×, autocontrast cutoff 1 |
| Folio number (e.g., "585") | same | same |
| Date (e.g., "July 15, 1909") | same | same |
| Dollar amount (e.g., "$13,000") | same | same |
| MSA accession (e.g., "MSA CE 62-343") | same | same |
| Grantor name | `enhanced_letters` / `enhanced_letters_zoom_2x` | LETTERS: contrast 1.5×, sharpness 1.0×, autocontrast cutoff 0.5 |
| Grantee name | same | same |
| Witness / notary / attorney name | same | same |
| Place name (street, neighborhood) | same | same |

Both passes are produced by `scripts/deed_pipeline.py:enhance_image()` and returned together in the `EnhancedSet` dataclass. Always look at BOTH variants when extracting any field that matters.

```python
import fitz
from scripts.deed_pipeline import enhance_image

doc = fitz.open(pdf_path)
pix = doc[0].get_pixmap(dpi=240)         # 240 DPI is the sweet spot
pix.save("p.png")

es = enhance_image("p.png")              # produces ALL variants

# When extracting "WPC 343, folio 585":   read es.enhanced_zoom_2x  (digits)
# When extracting "Henry Snow":           read es.enhanced_letters_zoom_2x (letters)
```

For *very* faint scans, the digits-tuned variants also include **inverted** (white-on-black) and **binary-threshold** fallbacks at `es.inverted` and `es.threshold`.

**Common confusions caught by this two-pass approach:**

- Digit confusions (DIGITS profile catches): `3 ↔ 5 ↔ 8`, `2 ↔ 5`, `7 ↔ 1`, dates off by ±20 years (1937 vs 1957).
- Clerk-prefix confusions (DIGITS profile catches): `SFJ ↔ SCL ↔ JFC`, `WPC ↔ MPC`.
- Letter confusions (only LETTERS profile catches): `Snow ↔ Knox`, `Bouchner ↔ Bouchier`, `Patrick ↔ Parish`, `Smith ↔ Smyth`, `Maud ↔ Mand`.

**Without applying both profiles, names will be silently wrong but internally consistent across deeds** — the chain validation loop (gotcha #3 below) won't catch them because the same misread propagates from each deed's grantee block to the next deed's chain-back recital.

### 2. Maryland clerk prefixes look similar in cursive

`JFC` vs `SCL` vs `SFJ` vs `SEB` are easy to misread. **Cross-reference the clerk code against the date** the deed claims — each clerk has a known era (see `reference/clerk_codes.md`). If the read says "SFJ 5757 1937" but SFJ was never a clerk in 1937, the clerk read is wrong.

### 3. Citations in deeds are systematically off by ±1–5 folios

Folio-number citations within deeds are not always exact — observed offsets up to ±5 folios from the cited number, and occasionally ±1 in the book number itself (cursive Arabic numerals collapse `2 ↔ 5 ↔ 8` and `7 ↔ 1`).

**Always validate** after pulling a candidate next-back deed by checking that the parties, date, and property description in the candidate deed match the recital you extracted from the parent deed:

```
parent_recital says: deed dated <date>, grantor <X>, grantee <Y>, property <description>
candidate at <liber>/<folio>:
  date matches?     ?
  parties match?    ?
  property matches? ?
→ accept iff all three match
```

#### Mandatory recovery decision tree (do not deliberate — execute these in order)

If validation fails OR the clerk-era / date check (gotcha #2) fires, **do not stop to think about it**. The decision tree IS the thinking. The first time the validation loop printed the same "this read is unusual, let me validate" line on a real run, the agent repeated that same sentence ~17 times in a row before doing anything because the recovery action wasn't specified. Specify it.

**The user is the LAST-resort oracle, not an early shortcut.** Exhaust all twelve mechanical steps below before escalating. Asking the user prematurely wastes their time on a problem the recovery tree could have solved automatically.

```
WHEN validation fails or clerk-era mismatch:
  step 1:  re-render the source page at 240 DPI (in case the cache is stale)
  step 2:  run enhance_image() to produce ALL variants in the EnhancedSet
           (digits AND letters profiles, inverted, threshold)
  step 3:  re-extract the citation reading EACH digits variant once
           (enhanced_zoom_2x, inverted, threshold) — record all reads
  step 4:  majority vote across the three reads; if two agree, that's the
           candidate. Pull and re-validate parties+date.
  step 5:  if still failing, re-render the page at 400 DPI, then 600 DPI,
           re-running enhance_image() each time
  step 6:  crop just the citation/name region and re-render the crop at
           600 DPI (small region → more pixels per glyph). Re-extract.
  step 7:  if still failing, scan ±5 folios in the same volume
           (try folios sp-2..sp+5 — recorded-sequentially is biased forward
           not backward)
  step 8:  if still failing, scan ±1 in book number
           (cursive 2↔5↔8 and 7↔1 collisions)
  step 9:  if still failing AND the source citation is typeset (not cursive),
           apply gotcha #12: try the modern grantor's name in the digital
           name index for cited-year ±2
  step 10: try the address-number search on landrec (works for recent deeds
           and for any era where the address is normalized in the index)
  step 11: try the digital grantor/grantee name search for the most likely
           candidate name (works for ~1989+ in BC, varying in BA per
           gotcha #11)
  step 12: try the scanned clerk index volumes (CE 35 series for BA,
           equivalent for BC) — see reference/scanned_index_volumes.md for
           bucket structure and navigation tactics
  step 13: ONLY now surface to the user. Provide:
            - all candidate readings from steps 3–6
            - absolute path to enhanced_letters_zoom_2x (for names)
              AND enhanced_zoom_2x (for digits)
            - optionally browser_navigate the Playwright tab to the source
              page so the user has the in-viewer zoom controls
           Ask SPECIFICALLY: not "is this right?" but "I see surname
           starting `Wh-` and ending `-te`; can you read it?" — one ask
           per field. If the user can't read it either, mark `[?]` in the
           transcription and proceed.
  STOP. Do not "think about whether this is unusual" — the decision tree
  IS the thinking. Execute it.
```

The intent is to make the recovery path **mechanical**, not deliberative. Every step has a concrete action. The agent must not loop on "this is unusual, let me validate" without taking the next mechanical step. If a step fails to produce a candidate, the next step starts immediately. **Every step before 13 is fully automated** — the user only sees a question after twelve mechanical attempts have failed.

### 4. Same-day "even date" companion deeds = straw pattern, not a real chain

A recital like *"by deed of even date herewith and intended to be recorded prior hereto, was granted and conveyed by the said `<grantee>`"* indicates a **same-day companion deed** in the same volume, recorded just before this one. In early-20th-century Maryland this was the way to convert solely-owned property into tenancy by the entireties:

1. Prior owner → Spouse-A alone (vests fee in Spouse-A)
2. Spouse-A + Spouse-B → straw grantee (releases dower, parks title at the straw)
3. Straw grantee → Spouse-A + Spouse-B as TBE (returns to the couple as tenants by the entireties)

All three deeds are dated the same day, all describe the same parcel, all special-warranty only. **Recognize the pattern and treat it as a single TBE-conversion event in the chain summary**, not as three independent owners. The straw grantees are not real predecessors — they are notary-office paper instruments (often a law-firm employee or relative serving for that one transaction).

Detection regex (after extracting the recital text):

```python
STRAW_RE = re.compile(
    r"(by\s+deed\s+of\s+even\s+date\s+herewith"
    r"|recorded\s+(?:or\s+intended\s+to\s+be\s+recorded\s+)?prior\s+hereto)",
    re.I | re.S,
)
```

### 5. Don't confuse chain-back recitals with metes-and-bounds neighbor references

Metes-and-bounds language uses *neighbor* parcels as survey landmarks. A typical metes recital looks like:

> *"thence southerly along the west lines of said Lots N and N+1, X feet to the end of the second line of the land which by deed dated `<date>` and recorded among the Land Records of `<county>` in Liber `<NEIGHBOR-CITATION>`, was granted and conveyed by the `<developer>` to `<NEIGHBOR>`, thence easterly and following the third line of said `<NEIGHBOR>`'s land..."*

That citation is **the neighbor's deed**, not the chain ancestor of the subject property. Pulling it sends you down a wrong path that can waste an hour. Watch for the "thence... line of said `<X>`'s land" frame — that's a survey landmark, not the chain.

The actual chain-back recital is a *separate sentence* later in the deed, usually starting:

```
Being the same property which by deed dated <date> and recorded ... was granted and conveyed by <prior grantor> to <prior grantee, usually a party to this deed>
```

or

```
Being part of the same property which ...
```

Extract via:

```python
CHAIN_BACK_RE = re.compile(
    r"Being\s+(?:the\s+same|part\s+of\s+the\s+same)\s+(?:lot|property|premises)"
    r"[^.]*?deed\s+dated\s+([A-Za-z]+\s+\d+,?\s*\d{4})"
    r"[^.]*?Liber\s+([A-Z](?:\.?\s*[A-Z])*\.?)\s*No\.?\s*(\d+)"
    r"[^.]*?folio\s+(\d+)"
    r"[^.]*?granted\s+and\s+conveyed\s+by\s+([^,]+(?:,\s+[^,]+)?)\s+(?:unto|to)\s+(?:the\s+said\s+)?([^.,]+)",
    re.I | re.S,
)
```

The **metes-and-bounds reference** to a neighbor is a different sentence. Distinguish by:
- Chain-back recitals come **after** the metes-and-bounds, near the habendum
- Chain-back recitals usually grant the property *to* a party in the current deed
- Neighbor metes references describe a *line* or a *corner*, not a whole property

### 6. Baltimore annexation 1918 (Maryland Act 1918, Chapter 82) — and earlier annexations

A swath of north Baltimore (including Roland Park, Guilford, parts of Mt. Washington, etc.) was annexed to Baltimore City **in 1918**. Pre-1918 deeds for these properties are recorded in **Baltimore County** records (`cid=BA`); post-1918 deeds are in **Baltimore City** records (`cid=BC`).

Don't try to look up a pre-1918 deed for an annexed property in Baltimore City records — it isn't there. Watch for the explicit boilerplate *"annexed to Baltimore City by the Maryland Act of 1918, Chapter 82"* in post-1918 deeds; that's the marker that the chain crosses the jurisdictional boundary.

The same pattern applies to earlier Baltimore annexations (1816, 1888) for older central-Baltimore neighborhoods, and to other Maryland jurisdictional shifts (e.g., D.C. retrocession of Alexandria/Arlington in 1846 affects nothing in MD, but the Frederick → Montgomery split of 1776, Howard formation 1851, Wicomico formation 1867, Garrett formation 1872 do — flag the date of any boundary change against the chain). When the recital cites a county that doesn't currently contain the parcel, suspect a historical jurisdictional shift before suspecting a misread.

### 7. Don't change `cid` mid-session by URL editing

Changing the `cid=` parameter in the URL directly can drop the landrec session. Instead, on the search page use the in-page **county dropdown** to switch jurisdictions; that preserves the auth cookies.

### 8. The user typing in the Playwright window corrupts form fields

If the user types into the Playwright tab during automation, keystrokes land in whatever form field happens to be focused — including SDAT/landrec search inputs that the skill is filling — producing corrupted searches like a stray digit appended to a street name. **Tell the user once at the start** to leave the Playwright window alone during automation. If a form fill produces unexpected results, immediately re-fill via JS rather than retyping (typing also fights focus):

```javascript
document.getElementById('<field-id>').value = '<value>';
```

### 9. Tenancy-by-entireties survivorship and marriage name changes are not separately recorded

If the chain shows a widow/widower with a new last name (a person whose maiden or first-marriage name appears in an earlier deed and a different married name in a later one), don't go searching for an A→B "name change" deed — there isn't one. Tenancy-by-entireties survivorship vests title in the surviving spouse by **operation of law** with no recorded instrument; marriage name changes happen via marriage license, not land records. Note these transitions in the summary as bullet rows (e.g., "between deed N and deed N+1: spouse-A predeceased spouse-B, who took 100% by entireties survivorship and later remarried, hence the surname change") and move on. Cross-check by searching contemporaneous probate/obituary records only if the chain summary hinges on it.

### 10. SDAT's "Primary Structure Built" date is often a default and unreliable

SDAT often shows `1900` as a placeholder build year for old houses (and similarly round-number defaults appear elsewhere — `1920`, `1950`). Cross-check against the earliest possible date in the recorded chain (the property can't have been built before the developer first conveyed the lot, and usually wasn't built before the lot was first improved per insurance maps). For a researched build date, recommend the user check the **Maryland Inventory of Historic Properties (MIHP)** — historic-district properties usually have individual MIHP forms with researched build dates and architect attribution where known.

### 11. landrec's grantor/grantee name index has a hard coverage cliff

The digital name search at landrec is **not comprehensive across all eras**. Empirical coverage (mid-2026):

- Baltimore City (`cid=BC`): name index returns results only for ~1989+ deeds. Pre-1989 grantor/grantee searches return `NoResults` even when the deed exists.
- Baltimore County (`cid=BA`): similar cliff at varying dates per surname-letter shard.

When a name search returns `NoResults` for a year before this cliff, **don't conclude the deed doesn't exist** — fall back to the **scanned clerk index volumes** (see `reference/scanned_index_volumes.md`). Those are the original handwritten clerk indexes, scanned and accessible via `JumpResults.aspx`. They cover back to the 19th century. The address-number search on landrec is also worth trying first — it's a separately-indexed path that sometimes returns results when the name path fails.

### 12. Typed citations in modern deeds are also frequently wrong

It's not just cursive. Attorneys in the 1990s+ routinely transcribed prior-deed citations incorrectly. Observed: a 2005 deed cited `SEB 4322/281`, then in a corrective-language recital cited `SEB 4822/281` — both wrong; the actual prior deed was at `SEB 4827/281`.

When a citation walk-back fails on a **modern deed where the citation is typeset** (not cursive), do NOT assume image-enhancement will help. Instead, in this order:

1. Try the modern deed's grantor name in the digital name index for the cited year ±2 years.
2. Try the address-number search on landrec.
3. Only then scan ±5 folios in the cited volume (the cursive recovery tree).

The cursive image-enhancement recipe is irrelevant when the source is already typeset — the misread is the attorney's, not the OCR's.

### 13. Ground-rent split — same-day reversion sale (distinct from the straw dance)

A different same-day-companion-deed pattern from gotcha #4. Common in Maryland 1880s–1930s:

1. Developer issues a 99-year **ground lease** to the occupant on day X, citation `<Liber>/<P1>`. The occupant pays annual ground rent (often $90–$300/year) but holds the leasehold, not the fee.
2. Same day, developer sells the **reversion** (the right to receive ground rent and to take the fee at lease expiry) to a passive investor — citation `<Liber>/<P1+N>`, usually within ±20 folios in the same volume.
3. Two paper owners thereafter: leaseholder + reversioner. They transfer independently down their own chains.
4. Eventually a successor leaseholder buys the reversion from a successor reversioner; **fee and leasehold merge** in that party. From then on the lot is held in fee simple.

Detection signals:
- The originating "deed" begins `This Lease,` or `This Deed of Lease,`
- It reserves `annual rent of <amount>`
- A distinct deed in the same volume within ±20 folios on the same date conveys "the reversion" or names a different grantee for "the fee" of the same lot

Pipeline impact: **Follow the leasehold chain, not the reversion**. The reversion converges back into the chain at the merger event. Note the reversion split as a chain row but don't pull every reversion successor — the originating-covenant analysis only depends on the lease, since covenants ride the leasehold.

### 14. Plat references go to plats.msa.maryland.gov, not landrec

Plat citations in deeds — `WPC Plat Book 4, folio 42`, `RPC Plat No. 3, plat 7` — refer to **subdivision plats**, which live on a separate Maryland State Archives portal:

```
https://plats.msa.maryland.gov/pages/index.aspx
```

Different viewer; the URL grammar parallels landrec's. See `reference/plats_url_patterns.md` for the URL schema. Plats aren't part of the deed chain proper, but they're the canonical source for original lot dimensions and developer numbering — useful for cross-checking SDAT's legal-description field against the originating deed.

### 15. Covenant schemes can self-expire — read the whole numbered block before reporting

Some early-20th-century Maryland developers (Hill Top Park 1913, others) wrote **self-extinguishing** covenant schemes. Hill Top Park's covenants expired by their own terms on January 1, 1931 — 18 years after the originating lease. Roland Park / Guilford / Homeland a few blocks south used **perpetual** schemes — but you can't assume the developer next door did the same.

**Always read the entire numbered-covenant block** before reporting any covenants as live. Trigger phrases to scan for:

- `shall terminate ... on the [date]`
- `shall be of no force or effect after [date]`
- `for a period of [N] years from [date]`
- `until the [year]`
- `this restriction shall expire`

If found, **flag prominently in the chain summary's covenant analysis**:

> Total recorded covenants binding this property today: **zero, expired YYYY-MM-DD per Covenant N**.

Do not transcribe an expired scheme as if it were currently binding. Note the expiry date in the originating-deed chain row's substance column.

### 16. Developer-principal taking a lot from his own development is legitimate

Soft signal worth flagging, not a misread. Pattern: an officer who signed the originating developer-conveyance later appears as a **grantee** on the same lot. Example seen on 2210 Sulgrave: Theophilus White signed the 1913 Hill Top Park lease as VP of Hill Top Park Co.; he personally acquired Lot 8 in 1917 from Robert B. Green.

When this pattern appears, do NOT dismiss it as a name-extraction error. Verify against the index that the same name appears in both roles, then note the unusual chain step in the substance column ("developer principal personally acquires lot from his own development").

## Name verification protocol (mandatory)

This protocol exists because of a real failure mode observed in testing: the chain-validation loop only verifies *internal consistency* across deeds. When the same name is misread the same way in two consecutive deeds (as the chain-back recital and the grantee), validation passes while both reads are wrong. The skill produced a chain summary calling the originating grantee "Henry Knox" when the deed actually said "Henry Snow"; the wrong name then propagated through the transcription PDF, the chain summary table, every raw-deed filename, and the covenant analysis.

The cure is a structured layer of name checks. **Do all of these, in order, for every name that appears in the deliverables.**

### A. Use the LETTERFORMS variant for every name read

When extracting any proper name (grantor, grantee, witness, notary, attorney, predecessor cited in a recital), read the name from `enhanced_letters_zoom_2x` — NOT from `enhanced_zoom_2x`. The digits-tuned recipe deforms cursive letterforms (see gotcha #1). Reading names off the digits variant is the primary cause of name misreads.

### B. External cross-check between deeds and SDAT

The grantee of deed N must equal the grantor of deed N+1 (modulo TBE survivorship and marriage-name changes — see gotchas #4 and #9). If they disagree on more than spelling/punctuation:
- one of the names is wrong (most likely)
- there's an unrecorded instrument missing from the chain (less likely)
- a TBE survivorship event occurred (check for widow/widower language)
- a marriage name change occurred (check for "f/k/a" or "formerly known as")

Equivalently: the grantor of the most recent deed must equal SDAT's prior owner of record (SDAT keeps the most recent transfer). If the most recent deed's grantor doesn't match SDAT's prior owner, the most recent deed's grantor was misread — re-extract from `enhanced_letters_zoom_2x` and re-validate.

### C. Surface every chain-endpoint name to the user before generating PDFs

After the chain walk completes and before the chain-summary PDF or the originating-deed transcription PDF is rendered, print a verification block to the user:

```
Names extracted from the chain — please verify before I render PDFs:

  Originating developer:   <Developer Name>
    enhanced image:        <abs path to enhanced_letters_zoom_2x for that page>

  Originating grantee:     <Grantee Name>
    enhanced image:        <abs path>

  Each subsequent grantor → grantee transition:
    1909 deed:  <Grantor> → <Grantee>     image: <abs path>
    1918 deed:  <Grantor> → <Grantee>     image: <abs path>
    ...

Reply 'confirmed' or specify a correction (e.g., 'originating grantee is Henry Snow not Henry Knox').
```

Always include the **absolute path to the LETTERFORMS-tuned enhanced image** (`enhanced_letters_zoom_2x`) used for that read, so the user can click open the image in their default viewer and read the cursive themselves. This is the cheapest possible cross-check and it catches the worst class of error before it propagates into deliverables.

Wait for the user's confirmation or corrections; apply any corrections and re-confirm before generating the PDFs. The user typing "confirmed" is the ship-gate.

### D. Reasonableness check on era/origin

Maryland-historic-context: most originating-deed grantees in north-Baltimore historic neighborhoods are surnames common to early-20th-century Baltimore (Snow, Bouchner, Maulsby, Knox, Beasley, Lang, Smith, Bouchier, etc.). Some are confusable in cursive — `Snow ↔ Knox` is a known visual collision. If the read produces an unusual surname for the era (e.g., a contemporary-sounding name on a 1909 deed), suspect the read.

This is a soft check, not a hard one — Maryland had plenty of unusual surnames too. Use it only as a "look twice" trigger for steps A–C.

## URL grammar (reverse-engineered from session)

| Endpoint | URL | Notes |
|---|---|---|
| Search page (county + clerk + book + page jump form) | `https://landrec.msa.maryland.gov/Pages/Search.aspx` | Use this; don't edit `cid` directly. |
| Jump-to-volume disambiguation (when book number repeats across clerks) | `https://landrec.msa.maryland.gov/Pages/JumpResults.aspx?cid={BC\|BA}&bk={book}&pg={page}` | Returns a list of MSA accessions; pick the one whose date range contains the deed you're looking for. |
| Single-deed viewer | `https://landrec.msa.maryland.gov/Pages/Viewer.aspx?cid={BC\|BA}&q=CE&sr={series}&ssu={volume}&sp={start}&ep={end}&view=I&first=true` | `sr` is MSA series; `ssu` is volume; `sp`/`ep` define the page range. Always set `ep` ≥ `sp` + 5 to capture multi-page deeds and trailing acknowledgments. |
| Direct PDF URL | from the viewer's `<iframe src>` — `https://landrec.msa.maryland.gov/PDF/{accession}/MSA%20CE%20{sr}-{ssu}%20p.{sp}%20to%20p.{ep}.pdf` | **Navigating to this URL renders inline in pdf.js — it does NOT trigger a host-side download.** See "Downloading deed PDFs autonomously" below. |

`cid` values: `BC` = Baltimore City, `BA` = Baltimore County, `AA` = Anne Arundel, etc. (see `reference/landrec_url_patterns.md` for the full table).

## Downloading deed PDFs autonomously

This is the single non-obvious step in the whole pipeline and it is **the** failure mode when the user is not driving. Read carefully.

`browser_navigate` to a `.pdf` URL renders the PDF inline in Playwright's pdf.js viewer. It does NOT save a file to the host filesystem. Likewise, `browser_network_requests` returns request *metadata* but not response bodies, so it cannot be used to capture the PDF either.

The working approach is an **in-page `fetch()` + base64 round-trip via `browser_evaluate(filename=...)`**. Three Playwright MCP calls and one Python decode:

```
# 1. Open the viewer (so the iframe gets its src populated)
mcp__playwright__browser_navigate(url=<viewer URL>)

# 2. Read the iframe's src
mcp__playwright__browser_evaluate(
    function="() => Array.from(document.querySelectorAll('iframe')).map(f => f.src)"
)
# → returns e.g. 'https://landrec.msa.maryland.gov/PDF/802662/MSA%20CE%2062-343%20p.00585%20to%20p.00590.pdf'

# 3. Fetch the PDF in the page context (cookies inherit) and stash bytes as base64.
#    The `filename=` arg writes the eval's return value to that file under
#    the Playwright-MCP host-output dir.
mcp__playwright__browser_evaluate(
    filename="deed_b64.json",
    function="""async () => {
        const r = await fetch('<iframe src>', {credentials: 'include'});
        const buf = await r.arrayBuffer();
        const bytes = new Uint8Array(buf);
        let bin = '';
        for (let i = 0; i < bytes.length; i += 0x8000)
            bin += String.fromCharCode.apply(null, bytes.subarray(i, i+0x8000));
        return {status: r.status, b64: btoa(bin)};
    }"""
)
```

Then in Python (use the `download_landrec_pdf()` helper in `scripts/landrec_download.py`):

```python
import base64, json, pathlib
data = json.loads(pathlib.Path(playwright_output_dir / "deed_b64.json").read_text())
assert data["status"] == 200, f"landrec returned HTTP {data['status']} — session may have expired"
pathlib.Path(out_pdf_path).write_bytes(base64.b64decode(data["b64"]))
```

**Validation after every download** (catch corrupted/HTML-error responses early):
- file size > 50 KB (a real multi-folio deed scan is typically 1–4 MB; <5 KB usually means an HTML error page)
- `len(fitz.open(path)) >= 1` and ideally `>= sp_to_ep_span`

If the fetch returns HTTP 401/403, or the resulting "PDF" is actually HTML containing `Login.aspx`, the landrec session has expired. Stop and tell the user to re-log-in; do not retry in a loop.

**Why the chunked base64 loop?** `btoa(String.fromCharCode(...bigArray))` blows the JS stack on large PDFs (multi-MB). The 0x8000-chunk slice keeps the call-stack depth bounded.

## The autonomous workflow

```
                    user gives address
                            │
                            ▼
   ┌────────────────────────────────────────────┐
   │ 1. SDAT lookup (no login)                  │
   │    sdat.dat.maryland.gov                   │
   │    → owner, deed reference, legal desc,    │
   │      lot dims, build date                  │
   └────────────────────────────────────────────┘
                            │
                            ▼
   ┌────────────────────────────────────────────┐
   │ 2. landrec entry                           │
   │    user logs in once                       │
   │    skill drives the rest                   │
   └────────────────────────────────────────────┘
                            │
                            ▼
   ┌────────────────────────────────────────────┐
   │ 2a. TRY NORMALIZED SEARCHES FIRST          │
   │    a. street-number search on landrec      │
   │    b. modern-grantor name index search     │
   │    ↳ either may return decades of recent   │
   │      citations directly. Only fall through │
   │      to the citation walk-back loop if     │
   │      both come up empty. (The walk-back    │
   │      loop is the slowest path and should   │
   │      be the FALLBACK, not the default.)    │
   └────────────────────────────────────────────┘
                            │
                            ▼
   ┌────────────────────────────────────────────┐
   │ 3. for each deed back through chain:       │
   │   a. navigate viewer with sp/ep ≥ +5       │
   │   b. download iframe PDF via in-page       │
   │      fetch + base64 round-trip             │
   │      (see "Downloading deed PDFs" above)   │
   │   c. validate file size + page count       │
   │   d. PyMuPDF render @ 240 DPI              │
   │   e. Pillow enhance (recipe above)         │
   │   f. extract chain-back recital            │
   │   g. validate by jump-to-cited-folio       │
   │      - parties match? date match?          │
   │      - if no, retry with alt image variants│
   │      - if no, scan ±5 folios               │
   │      - if no, ask user                     │
   └────────────────────────────────────────────┘
                            │
                            ▼
   ┌────────────────────────────────────────────┐
   │ 4. detect special patterns:                │
   │    - same-day straw dance                  │
   │    - neighbor metes references             │
   │    - 1918 annexation jurisdiction shift    │
   │    - TBE survivorship, marriage rename     │
   └────────────────────────────────────────────┘
                            │
                            ▼
   ┌────────────────────────────────────────────┐
   │ 5. stop when:                              │
   │    - reach developer (e.g., RPC), OR       │
   │    - reach earliest digital record, OR     │
   │    - grantor name index empty backward     │
   └────────────────────────────────────────────┘
                            │
                            ▼
   ┌────────────────────────────────────────────┐
   │ 6. read originating deed in full           │
   │    extract numbered covenants              │
   └────────────────────────────────────────────┘
                            │
                            ▼
   ┌────────────────────────────────────────────┐
   │ 7. cross-validate SDAT vs deed parcel      │
   │    flag discrepancies (lot dims, build yr) │
   └────────────────────────────────────────────┘
                            │
                            ▼
   ┌────────────────────────────────────────────┐
   │ 8. produce outputs:                        │
   │    - chain-summary.pdf (1–2 pp)            │
   │    - originating-deed-transcription.pdf    │
   │    - all raw deed PDFs in Downloads/       │
   └────────────────────────────────────────────┘
```

The orchestrator script and helpers are in `scripts/`. The reportlab layouts are in `templates/`. Reference data (clerk codes, URL grammar) is in `reference/`.

## Output deliverables

Two PDFs per run, plus the raw deed PDFs.

### Chain summary PDF (`{address-slug}-title-chain-summary.pdf`)

Letter-size, 1–2 pages. Table format with columns: **Date** | **Grantor → Grantee** | **Citation** (Liber/folio + MSA accession) | **Substance** (covenants? straw? survivorship?). Originating-developer row highlighted. Below the table: a covenant-analysis paragraph and a **Diligence items** section explicitly calling out:

- SDAT vs deed-described parcel discrepancies (lot dimensions, square footage)
- Schedule B-II review for specific listing of the originating deed; ALTA enhanced / owner's homeowner policy as backup
- SDAT build date vs earliest possible chain date; MIHP for researched build year
- Any maintenance-fee or assessment cap recited in the originating deed (verify against current invoices)

Final disclaimer footer (research, not legal advice).

### Originating-deed transcription PDF (`{address-slug}-{year}-{developer-slug}-deed-transcription.pdf`)

Letter-size, ~4 pages. Sections: title page with full citation; parties + consideration; property description (full metes); all numbered covenants with operative phrases bolded; signatures + acknowledgment + recording stamp; reader's commentary. `[?]` brackets on uncertain readings preserved.

### Raw deed PDFs

All saved to `~/Downloads/` with consistent naming:

```
{address-slug}-{year}-{grantor-short}-to-{grantee-short}-{liber}{book}-{folio}.pdf
```

Where `{address-slug}` is the lowercased street number + street name (no suffix), `{grantor-short}` and `{grantee-short}` are surnames or developer abbreviations, and `{liber}{book}-{folio}` matches the citation written in compact form (e.g., `WPC343-585`, `SCL3219-388`, `JFC307-225`, `SEB6592-38`).

## Out of scope (don't try to do these)

- **Probate research** — Orphans' Court records aren't on landrec; flag the gap, recommend Maryland State Archives in-person research if the chain hits a death-and-distribution gap
- **Title insurance interpretation** — recommend the user's title company review Schedule B-II of the title commitment; don't try to read or interpret it
- **Legal advice** — output is research, not legal opinion; final disclaimer in both PDFs
- **Pre-digitization deeds at MSA** — landrec digital coverage extends back to ~1850s for some volumes but not all; if you hit the digital-records floor, flag it and recommend in-person research
- **Counties outside Maryland** — skill is MD-specific because it's tied to landrec.msa.maryland.gov

## One-line invocation (after pre-flight)

```
"Research the title for <Maryland address>. Trace the deed chain back as far as
landrec digital records allow. Produce the chain summary PDF, transcription PDF,
and save all raw deed PDFs to my Downloads folder."
```

The skill handles the rest, asking for user help only at the login step and only if cross-validation completely fails on a citation read.

## Performance / cost notes

Rough order of magnitude (typical historic-platted property, ~8–12 deeds in the digital chain back to the developer):

- Time per deed *without* the image-enhancement recipe: ~5–10 minutes including misreads + retries on each citation
- Time per deed *with* the enhancement recipe applied first: ~2 minutes, usually zero retries
- The image-enhancement step adds ~200ms per page rendered; that cost is dwarfed by the eliminated retry loop, so it's a strict win — apply it on every read, not selectively.
- End-to-end runtime is dominated by login + landrec page load latency, not by the local image processing or the OCR. Expect **30–60 minutes wall-clock for a 10-deed chain** on a fast connection with a responsive user — that's the target.
- With **dedicated user collaboration** on cursive escalations (last-resort step 13 in the recovery tree), expect **1–2 hours**. With a slow-to-respond user (typical when they're multitasking), real wall-clock can stretch to 2–3 hours; the bottleneck there is human latency, not the skill.
- The mechanical recovery tree (gotcha #3) keeps user-asks rare — under normal conditions, zero or one cursive escalations on a 10-deed chain. Steps 1–12 fix the vast majority of misreads automatically.

## Principal lesson

**The developer's originating deed is the only deed that matters for covenant analysis, and reading the citation chain reliably back to it requires the image-enhancement recipe.** Modern deeds in the chain repeat parcel descriptions but never re-recite the original covenants; skipping straight to the developer is correct, and getting there reliably hinges on each book/folio read being right the first time.
