# Actual published postal-code facts: Oman Post, Palestine Post, SPL and UPU

This is the preserved 85-row manual excerpt, not the current project-wide import inventory. See [the acquired source layer](../imports/README.md) for subsequent Cyprus/Jordan original imports and country-level remaining work.

This folder contains **85 manually transcribed source/code/place pairings** from
public official postal pages, checked on **2026-11-05**. These are real published
facts, but they are **not an imported original full source dataset**. The original
HTML and source CSV bytes were not downloaded into GitHub. Each source's URL, source
type, granularity, review date, and reuse status are retained in
[official_excerpt.json](official_excerpt.json). Bulk re-distribution terms for the
Oman/Palestine HTML pages are not confirmed, so do not represent the excerpt as a
fully licensed national postal database.

| Country | Records | Evidence type | What is actually supported |
|---|---:|---|---|
| Oman | 37 | Oman Post's branch locator | 3-digit *post-office/branch* code to source-listed office and region label |
| Palestine | 45 | Palestine Post governorate postal tables | P3 *postal area* code to the Arabic place name(s) published in each region's table |
| Saudi Arabia | 1 | SPL published example | One Riyadh postcode example; not an exhaustive Riyadh postcode-to-locality list |
| Bahrain | 2 | UPU/Bahrain Post published examples | Two locality-postcode formatting examples, not exhaustive postcode assignment |
| Qatar | 0 | No conventional national postcode | Anwani Zone / Street / Building requires separate registered source/API |

## Validation contracts

- A postal-code value is **not a unique locality key**. On Palestine Post's page,
  P626 (Jifna and Doha), P663, P113 and P350 appear with multiple distinct names.
  Preserve one-to-many source associations without collapsing to one city.
- Oman branch code **is not evidence of home delivery throughout its named town**.
  Oman Post publishes Ruwi with different codes (112, 168) and Khasab with
  different codes (811, 819). It also uses combined governorate labels
  "Al Sharqiyah North & South", "Al Batinah North & South" and legacy variants.
  Such labels do not determine one current governorate.
- For Palestine, keep **P3/P7 postal addressing** independent of PCBS's
  **six-digit statistical locality coding**. The current extract has P3 rows only.
  Do not generate or extrapolate P7 codes.
- The join code calculates candidate GN locality IDs using source language,
  original GeoNames IDs, and region constraints where candidate region references
  exist. This is unreviewed name candidate generation, **not a certified
  official postal-to-GeoNames crosswalk**.
- A sample code is not evidence that a full directory was downloaded. Countrywide
  completeness, precise building/entrance locations, and deliverability remain false.
- Source dates are missing for some public webpages. They represent what was
  visible when inspected, not an official data-last-updated timestamp.
- Keep the official source authority and rights notes separate from the GeoNames
  CC BY 4.0 licence. No new blanket licence has been applied.

## Offline reproducibility

From the root of the repo:

    python scripts/western_asia_postal_join.py report --country all --output /tmp/wa-postal-join.json
    python scripts/western_asia_postal_join.py report --country OM
    python scripts/western_asia_postal_join.py inspect --country PS --code P626
    python -m unittest tests.test_western_asia_postal_join -v

The command reads the packaged source excerpts, confirms original-country
GeoNames ZIP/member SHA256 from the existing manifest, and reports counts for:
distinct codes, multiple places per code, unique/ambiguous/no GN candidates,
undetermined governorate references and source-scheme coverage.

## What remains for a comprehensive official join

- Palestine Open Data provides a CC BY licensed P3/P7 CSV catalogue at
  https://opendata.ps/dataset/postcodes , but its original resource bytes were
  not obtainable in the present session. Fetch exact resources, source checksums,
  field types and date, then create a separate original-data ingest.
- Saudi SPL publishes a National Address API with a developer account and
  lookups for regions, districts and postcodes. Do not use an example address
  as a full postal directory: https://splonline.com.sa/en/national-address-api/ .
- Bahrain UPU sample values cannot stand in for a postal-code block
  registry. Acquire a licensed official code-to-block lookup first.
- Oman Post's branch directory may be used to locate office codes but not as
  an authoritative building-address postal reference.
- Qatar has **Anwani Zone, Street, Building**; no synthetic national postcodes.
  A Qatar address API generally needs registration or operator access.
- Accept a future official original CSV only if its source URL, licence,
  SHA256, version and code-to-admin evidence are pinned. Review 1:N and
  time validity before graduating links from \`candidate\` to \`verified\`.
