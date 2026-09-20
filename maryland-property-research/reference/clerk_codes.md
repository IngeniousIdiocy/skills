# Maryland Land Records — Clerk Prefix Codes

Maryland land records are organized into **liber** (book) volumes, each
identified by a **clerk's initials** plus a sequential number. The clerk
prefix changes each time the office of Clerk of the Court turns over,
so the prefix is also a coarse date marker — useful for sanity-checking
a citation read against the date the deed claims to be from.

This document is the lookup table the skill uses to:

1. Validate a clerk-code OCR read (e.g., reject "SFJ 1937" because SFJ
   was never the active prefix in 1937).
2. Disambiguate similar-looking prefixes (JFC vs SCL vs SFJ vs SEB).
3. Pick the right `cid` (Baltimore City vs Baltimore County) for a given
   clerk era.

Coverage below is **Baltimore City + Baltimore County** because that is
where the historic developer-platted neighborhoods this skill targets
are concentrated. Other counties have their own clerk sequences; those
are not listed here. When working in another county, look up its clerk
sequence on the MSA "Maryland Land Records" landing page or by inspecting
the date-range column in `JumpResults.aspx` for that `cid`.

## Notation

- *Clerk code*: the alphabetic prefix written on the spine of the volume
  and used in the SDAT deed-reference field. Often two or three capital
  letters with no internal punctuation in modern records, but sometimes
  written `W.P.C.` or `W. P. C.` in cursive recitals.
- *Era (years)*: the inclusive year range during which volumes with this
  prefix were *recorded* (not necessarily the dates inside the deeds).
- *Jurisdiction*: `BC` = Baltimore City, `BA` = Baltimore County. A
  single prefix usually serves only one jurisdiction; entries showing
  both are pre-annexation overlap or post-annexation continuation.

## Baltimore County (`cid=BA`)

Most Roland Park / Guilford / Mt. Washington / etc. pre-1918 chains
terminate in this jurisdiction. After the 1918 annexation, recently
annexed parcels' subsequent deeds appear in Baltimore *City* records
instead.

| Clerk code | Era (recorded) | Notes |
|---|---|---|
| `JWS` | 1880s–early 1900s | Plat records appear here too — e.g. Roland Park Plat 1 is at JWS Plat Book 1. |
| `WPC` | ~1908–~1918 | William P. Cole. Holds most Roland Park developer-era conveyances. |
| `WHM` | post-1918 | Continuation of County records after annexation. |

## Baltimore City (`cid=BC`)

| Clerk code | Era (recorded) | Notes |
|---|---|---|
| `SCL` | ~1918–~1935 | Holds the immediate post-annexation Roland Park records, including the same-day "straw dance" TBE-conversion deeds. |
| `MLP` | ~1935–~1947 | |
| `MLP/CWB` overlap | ~1947 | Volumes occasionally co-labeled during transition. |
| `JFC` | ~1955–~1968 | James F. Carney. **Used for two distinct numbering tracks** — early `JFC` numbers (≤ ~500) are different volumes from the later `JFC 2000s` series; the city renumbered at the boundary. Validate by date: a `JFC 307` deed should be ~1957 and a `JFC 2021` deed should be ~1966. |
| `SFJ` | ~1968–~1975 | |
| `RHB` | ~1975–~1985 | |
| `JWS` (city) | ~1985–~1990 | Distinct from Baltimore County's earlier JWS plat-book usage. |
| `AM`  | ~1985–~1990 | Sometimes co-runs with JWS in transition years. |
| `SEB` | ~1990–~2000 | Saundra E. Banks. Many late-1990s arms-length sales. |
| `FMC` | ~2000–~2010 | |
| `AWB` | ~2010–~2018 | |
| `MDR` | ~2018–present | Modern volumes; format and indexing largely unchanged from prior sequences. |

## How to use this table

When the cross-validation loop in `deed_pipeline.py` reads a citation
like `Liber JFC No. 307, folio 225, deed dated 1957-12-21`:

1. Look up `JFC` → era 1955–1968. **1957 is in range → clerk read is plausible.**
2. Look up `JFC` → jurisdiction Baltimore City. **Confirm cid=BC for the next-back fetch.**
3. If the read had been `Liber SFJ No. 307, ...` for a 1957 deed, this
   table would flag it: SFJ was post-1968, so the prefix was misread —
   re-run the image enhancement with alternate variants (inverted /
   threshold) and try again.

A failed prefix lookup is a **higher-confidence error signal** than a
failed folio lookup, because clerk prefixes don't have offset-by-±5
ambiguity — a wrong prefix is wrong, not approximate.

## When this table is wrong

Update entries in this file (and the `clerk_era_lookup()` helper that
should consume it) whenever the cross-validation loop catches a clerk
code that's actually valid for a date the table rejects. Real Maryland
clerks occasionally serve through transition years not captured here;
the era columns are *approximate* and useful for catching gross misreads
(±20 years), not precise (±1 year).

## Source of this table

Compiled from observation across multiple chain walks plus the volume
date ranges that landrec's `JumpResults.aspx` page surfaces when a book
number maps to multiple physical volumes. There is no single official
"clerk index" published by MSA, so the table is empirical — additions
are welcome.
