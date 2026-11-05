# 11-country South-East/Central Europe evidence audit and intake

**Priority (9):** RS, BG, RO, HU, AL, MK, ME, BA and XK.  **Continue existing PR #8 (2):** HR and SI.

This project does **not** replace or relabel the existing `registries/europe/countries/CC` source archives, `registries/europe/eurostat-lau`, the already accepted Romanian SIRUTA 2026 layer, or the open PR #8's Croatia/Slovenia source adapters. A country-code presence never certifies nationwide coverage, postal validity, current address existence or carrier delivery.

## Implemented

- Full integrity audit of every selected country's GeoNames source partition, SHA-256, uncompressed SHA-256, record counts, source country codes, source IDs and asserted parent ID references; original parent gaps remain visible and **are not guessed away**.
- Separate audit of the existing accepted **Romania SIRUTA 2026** 16,978-row derived source by invoking its own verifier; its entries are **not** counted as additional unique addresses or joined by string similarity.
- An immutable source-qualified SQLite locality search index with native labels, original feature codes, source aliases, and isolated original source identities; `.casefold()` matching handles Cyrillic, Latin and accented search strings.
- Generic **offline** source pin/ingestion for reviewed CSV, gzip-CSV, ZIP/CSV, JSON arrays, ZIP/JSON arrays, or GeoPackage table. Field mappings are explicit, and unsupported coordinate systems must be converted and documented before import. Source identities across different publications are never guessed to be equal.
- A GitHub Actions job to run real repository audits, build/verify an index and export review artifacts. Offline synthetic tests exercise failures and candidate parsing.

## Commands (Python 3.11+, standard library)

```bash
python scripts/balkan_11_localities.py inventory
python scripts/balkan_11_localities.py audit --country all
python scripts/balkan_11_localities.py build --country all --output /new/europe-11-localities.sqlite
python scripts/balkan_11_localities.py verify --db /new/europe-11-localities.sqlite
python scripts/balkan_11_localities.py query --db /new/europe-11-localities.sqlite --country BA --text Sarajevo
python -m unittest discover -s tests -p 'test_balkan_11_localities.py' -v
```

**Note:** the built SQLite initially contains only the accepted GeoNames observations. Romanian 2026 SIRUTA is independently audited and recorded in the **provenance** table, not copied as a second set of independently verified address records. To search SIRUTA features, use the existing `python scripts/europe_priority_six.py ingest-ro` and corresponding search command. To ingest a newly rights-approved file add `--pin <snapshot-pin.json> --source-root <immutable-files>` to the `build` command.

## Source pin example, deliberately not accepted

```json
{
  "schema_version": 1, "country": "AL", "kind": "locality", "format": "csv",
  "source_id": "asig-localities-EXAMPLE", "source_version": "REPLACE_WITH_ACTUAL_DATE",
  "official_url": "https://asig.gov.al/en/geoportal/", "acquired_at": "REPLACE_WITH_ACTUAL_TIMESTAMP",
  "rights_reviewed": false, "commercial_reuse_reviewed": false, "license": "REQUIRES_REVIEW",
  "filename": "source.csv", "bytes": 0, "sha256": "REPLACE_WITH_ACTUAL_SHA256",
  "coordinate_crs": "not_provided", "fields": {"id": "OFFICIAL_CODE", "name": "OFFICIAL_NAME"}
}
```

Build fails if a candidate has unreviewed commercial/derivative distribution rights, a mismatched hash, an unknown identifier/column, duplicate IDs, unsafe source paths, cross-border source code or unsupported geometry CRS.

### Legal and data-quality cautions

- **Bulgaria NSI EKATTE:** the published NSI licence text includes restrictions on redistribution of derivative and combined works. Merely being downloadable does not make a merged commercial distribution unrestricted; obtain legal clearance before release. NSI official portal: https://nrnm.nsi.bg/ekatte/index
- **Kosovo/Serbia:** preserve distinct source jurisdictions. The project uses GeoNames `XK` as a dataset label only, not as an official ISO code or statement about sovereignty.
- **Bosnia-Herzegovina:** entity/canton/district/local municipality structures must remain explicit; do not auto-join municipal parent by similar name.
- **Montenegro:** 2010 settlements + 2022 municipality list refer to different source dates; never label a combined set as current without independent review.
- **North Macedonia:** keep Macedonian and Albanian native labels and official code sources separate.
- **Croatia and Slovenia:** existing PR #8 remains open; this audit does not merge, overwrite or invalidate that work.
- **Romania:** existing SIRUTA postcode field `0` is **not** a validated postal code. National SIRUTA parent codes prove administrative registration in the cited edition, not deliverable streets.

## Exit criteria for nationwide address verification

A country cannot be marked complete without a legally reusable official or independently evaluated source for municipality/place, street, house number and live postcode mapping, matching source version/rights, verified missingness denominator, and carrier transformation tests. See [source catalog](sources.json).
