# Maryland Land Records — Scanned Clerk Index Volumes

The digital grantor/grantee name search at landrec has a hard coverage
cliff (see SKILL.md gotcha #11). For older deeds, the **scanned clerk
indexes** are the canonical source — and they are the path the skill
must take when the digital name search returns `NoResults` for a year
that the cliff covers.

These indexes are accessible through landrec's `JumpResults.aspx` viewer
the same way the deed pages are; they are simply a different MSA series.

## Series IDs

| `cid` | Series | Approximate coverage | Type |
|---|---|---|---|
| `BA` | CE 35 | 1851–1920s | Combined grantor/grantee index, by surname |
| `BC` | (TBD — record as discovered) | | |

(Other counties have their own series — fill in as discovered. Series
IDs are the same `MSA CE NN-MM` shape used for deed-volume accessions.)

## Volume bucketing (BA, CE 35 series — confirmed empirically)

Each scanned volume covers **three buckets simultaneously**:

1. A range of **years**
2. A first-letter of the indexed party's **surname**
3. A first-letter of the indexed party's **first name**

So volumes are addressed by `(year-range, surname-letter, first-name-letter)`.

Confirmed bindings from real sessions:

| Accession | Years | Surname | First name |
|---|---|---|---|
| CE 35-33 | 1905–1914 | G–Hb | various |
| CE 35-46 | 1915–1921 | Fr–Hf | various |

## In-volume layout

Within a volume, entries are bucketed by `(surname-letter, first-name-letter)`
then **chronological** within the bucket. Folios advance roughly monthly
within a bucket. So to find a specific (surname, first-name, date) tuple:

1. Open the `(surname-letter, first-name-letter)` bucket
2. Scan chronologically — folios advance roughly monthly
3. Binary-narrow by jumping to a folio in the rough year range, then
   stepping forward/backward

Example navigation observed for "Edward B. Green, September 1913" in CE 35-33:

- Folio 300: last entries of February 1910, all G surnames, M first names
- Folio 330: starts May 1916 (overshot — but tells you the cadence is roughly
  one folio per month within the bucket)
- Backed off to the September-1913 region of the bucket — found the target

## Column semantics

| Column | Meaning |
|---|---|
| Surname | The indexed party's surname |
| First name | The indexed party's first name |
| **Course** | **`from` = indexed party is the GRANTEE** (received from the right-column party); **`to` = indexed party is the GRANTOR** (gave to the right-column party) |
| Other party | The party on the other side of the transaction |
| Type | `Lease` / `Deed` / `Mort` (mortgage) / `Rel` (release) etc. |
| Liber | Book number |
| Folio | Page number |

The **Course** column is the key insight: a single index serves both
grantor and grantee searches. To find conveyances **to** the indexed
person, look for `Course=from`. To find conveyances **from** the indexed
person, look for `Course=to`.

## Strategy: finding a developer-originating deed via the lot's first grantee

The originating-developer deed is the hardest to find by name, because:
- Developer name searches return long lists across many lots
- Lot-specific clues are absent at the developer-name level

Faster path: **search for the first non-developer grantee** — the person
who took the originating deed from the developer. When you find them in
the `(surname-letter, first-name-letter, year)` bucket with `Course=from`
and the developer's name in the right column, you've found the
originating-conveyance row.

Example: For 2210 Sulgrave Ave the chain pointed to "Edward B. Green"
in 1913 (cited in the 1914 guardian deed). Searching CE 35-33 at the
September-1913 folio for the G/E bucket returned the row:

```
Green, Edward B. | from | Hill Top Park Co. | Lease | 418 | 168
```

That row IS the originating-developer lease. Five sibling rows on the
same folio gave the parallel mortgage and reversion citations.

## Navigation via JumpResults.aspx

Drive the JumpResults viewer the same way you drive Viewer.aspx for deed
pages. Use the index series ID (e.g., `cid=BA&bk=35-33`) and step through
folios. Save scans to `~/Downloads/index-scans/` rather than mixing them
with deed PDFs.

## Recording new bindings

Whenever the recovery tree (gotcha #3 step 12) needs an index volume
that isn't yet cataloged in the table above, add the binding to the
"Volume bucketing" table once confirmed. Empirical, like everything
else in this skill.
