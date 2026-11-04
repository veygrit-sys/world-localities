# Northern America quality layer (UN M49 021)

This directory is a **non-destructive view**, not a copy of the source locality
data. In UN M49, Northern America (021) has five countries/areas: Bermuda (BM),
Canada (CA), Greenland (GL), Saint Pierre and Miquelon (PM), and United States
(US). The larger *North America* (003) **also** includes Central America and
the Caribbean. See the [official UN M49 list](https://unstats.un.org/unsd/methodology/m49/overview/).

## Initial data status, 2026-10-15

| M49 country/area | Existing source locality rows | Status |
|---|---:|---|
| US | 68,744 | Existing 2026 Census snapshot, 52 region files; **1,231 Puerto Rico rows belong to M49 Caribbean** |
| CA | 5,054 | Existing Statistics Canada 2025 CSD snapshot, 13 province/territory files |
| BM | unknown | Source pending; **not** a claim of zero localities |
| GL | unknown | Source pending; **not** a claim of zero localities |
| PM | unknown | Source pending; **not** a claim of zero localities |

A separate [administrative-name seed catalogue](admin-seeds.json) adds **18
evidence-backed names** for the three missing country/area sources: Bermuda's
nine parishes and two municipalities, Greenland's five municipalities,
and Saint Pierre and Miquelon's two French communes with INSEE codes 97501
and 97502. These are **not** a substitute for a locality source. Seed IDs
outside INSEE are provisional; the data have no house number or delivery
authority. Pending-country queries return seed names in the separate
`administrative_seeds` property while `status=not_loaded` remains true.

There are **72,567 rows in the M49 Northern America view**, computed as
68,744 - 1,231 + 5,054. The untouched US original contains **68,744** source
rows, including Puerto Rico; its native role counts are not redefined.
The US 2026 Gazetteer does not include other US Island Areas. The Canadian
source contains census subdivisions, including statistical/Indigenous and
unorganized categories, not only incorporated municipalities. These counts are
source rows, **not unique governments or verified addresses**.

This directory does **not** create a new authoritative localities layer for
BM/GL/PM, official English translations, street/address numbers, postal-code
assignments or delivery guarantees.

## Read localities

From the repository root, using Python 3.11+ standard library:

    python north-america-registry/query.py --country US --region US-CA --text San --limit 10
    python north-america-registry/query.py --country CA --region CA-NS --text Shelburne
    python north-america-registry/query.py --country GL
    python north-america-registry/query.py --country US --region US-PR --include-cross-region-pr

The default US view omits US-PR from Northern America. The explicit override
preserves inspection of source data; it does **not** make Puerto Rico part of
UN M49 Northern America. The Caribbean regional GeoNames PR layer remains
independent. **Do not add both layers as unique localities.**

The query exposes the original ID, role, source country, actual name language
(`und` means *undetermined*), and the original name unchanged.
It can filter by a **source** address-candidate flag, which is *not* a
deliverability determination. Substring search normalizes Unicode for matching
but does not manufacture official transliterations or translations.

`name-overrides.json` corrects one proven display defect:
Canada `CA-NS` is mistakenly labelled "New Scotia" in the preserved
country index. The presentation layer displays **Nova Scotia**, backed by
[Statistics Canada 2025](https://www150.statcan.gc.ca/n1/pub/72-212-x/2025001/sect4-eng.htm).
The original country files, index, manifests, and hashes are unchanged; the
output includes `region_name_in_snapshot` for provenance. If the original
index changes, the correction **fails closed** until reviewed.

## Quality targets for the next rounds

1. Source license, edition/date, stable geographic IDs and hash-based ingestion
   for BM, GL and PM, including municipal/statistical type and overseas status.
2. All US/CA region roles and parent code chains; ambiguous geometry and
   census/municipality identity must be flagged, not silently equated.
3. Official English and local-language names with authority, date, language and
   independent attestation; distinguish accents, alternate names and original text.
4. USPS/Canada Post and territory-specific postal **crosswalks**, many-to-many;
   never conflate Census ZCTA or Canadian CSD with delivery zones.
5. Address1 street and number-range checks, then separately verify premise
   and Address2 subpremise coverage with legal/licensed sources. Unavailable data
   remains explicitly pending.

See [the Americas orchestration layer](../americas-registry/README.md).
