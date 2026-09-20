# plats.msa.maryland.gov — URL Grammar

Maryland's **subdivision plats** live on a different MSA portal from
land records. This document is the reverse-engineered URL map for it,
parallel to `landrec_url_patterns.md`.

Plats are not part of the deed chain proper, but deeds routinely cite
them — `WPC Plat Book 4, folio 42`, `RPC Plat No. 3, plat 7`, etc. —
as the canonical source for original lot dimensions and developer
numbering. The skill drives this portal when:

1. The originating deed's metes-and-bounds calls the plat by reference,
   and you want the lot dimensions for cross-checking SDAT.
2. The user asks for a copy of the developer's recorded plat alongside
   the deed.

## Authentication

Plats.net uses the **same MSA login** as landrec — the session cookie
issued by the landrec Search.aspx login generally carries to plats.net
on the same browser context. If a plats fetch returns the login page,
re-log-in at landrec; the cookie refreshes both portals.

## Endpoints

### 1. Search / index page

```
https://plats.msa.maryland.gov/pages/index.aspx
```

User-facing entry. Hosts a county selector and a plat-book-and-page
jump form analogous to landrec's deed-jump form.

### 2. Plat viewer

```
https://plats.msa.maryland.gov/pages/plat.aspx
  ?cid={CID}                  same county codes as landrec
  &qualifier={QUAL}           usually "M" — historical, keep verbatim
  &series={SERIES}            MSA series for plats (distinct from deed series)
  &volume={VOLUME}            plat-book number
  &page={PAGE}                plat number within the book
```

The viewer renders a single plat sheet with pan/zoom controls. The
underlying image URL is exposed via the page's iframe `src`, the same
way deed PDFs are exposed on landrec — and the same in-page
`fetch()` + base64 round-trip pattern (see SKILL.md "Downloading deed
PDFs autonomously") works to capture it.

### 3. Direct image URL (cookies required)

```
https://plats.msa.maryland.gov/PDF/{ACCESSION}/MSA%20...{path}.pdf
```

Mirrors landrec's PDF endpoint shape. Treat identically.

## Citing plats from deeds

A deed citation like:

```
... as shown on the plat of Hill Top Park, Revision Plat No. 1,
recorded among the Plat Records of Baltimore County in
Liber WPC Plat Book 4, folio 42 ...
```

maps to:

```
cid=BA, series={MSA series for BA plats}, volume=4, page=42
```

The clerk-prefix `WPC` is the same clerk who served Baltimore County
deeds in that era (see `clerk_codes.md`). MSA assigns plats their own
series number distinct from the deed series — discover the series
number from `JumpResults.aspx` the first time it comes up for a
jurisdiction, then cache it here.

## Save naming

Plats land in `~/Downloads/` with naming parallel to deeds:

```
{address-slug}-{year}-{developer-slug}-plat-{volume}-{page}.pdf
```

Example: `2210-sulgrave-1912-hill-top-park-revision-plat-1-WPC4-42.pdf`.

## What this skill does NOT extract from plats

- Bearing/distance calls to digitize the metes-and-bounds (use a
  professional surveyor or GIS plat-to-shapefile tool)
- Restrictive covenants (those are in the deed, not the plat —
  occasionally a plat has a covenant block in the margin, but it is
  always re-recited in the originating deed; rely on the deed)

The skill only fetches the plat image and includes it in the chain
summary as a referenced figure if useful for the user's question.
