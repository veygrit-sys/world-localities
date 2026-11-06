# Eastern Europe: Moldova, Ukraine, Belarus, Russia

Scope: `MD`, `UA`, `BY`, `RU`. These are **source-separated geographic observation sets**, not four certified delivery-address registries. Existing GeoNames records live at `registries/europe/countries/{CC}` and are not replaced. The RU country extract spans the full source-country area, including Asian Russia; it is **not** a geographic-only European Russia extraction. Russian national register publication does not determine international sovereignty, and a GeoNames country-code assignment is not proof of border status. In contested regions, source authority, date, and de facto access are separate attributes; do not fuse UA and RU observations simply by matching names, coordinates, or alleged jurisdiction.

## Implemented

- Replays all **272,110 saved GeoNames records** in the four existing country partitions; validates compressed SHA-256, decoded SHA-256, row counts, source country, unique GeoNames IDs, asserted parent ID availability, and class totals.
- Builds an immutable source-qualified SQLite index from verified GeoNames, without data duplication, with original parent-relations and native Cyrillic/Romanian labels retained. Missing or disputed parents are not filled by guesswork.
- Source-pinned importer for `CSV`, `CSV.gz`, `ZIP/CSV`, `JSON array`, `XLSX` and explicitly selected regional `ZIP/XML` records (including a GAR/FIAS record-like XML adapter). All field mapping, archive membership, CRS, source version, SHA-256/bytes, downstream commercial-rights review, and explicit ID scheme are mandatory. XLSX parsing requires optional `openpyxl`; all regular GeoNames commands use the Python standard library. Region-by-region imports avoid holding national GAR XML in memory.
- Postcode shape tests, **never** assignment/existence/delivery checks. Real postal data remains unimported.
- `MD CUATM`, `UA KATOTTG`, `BY SOATO`, `RU GAR/FIAS and OKATO` as official **candidates**. No new official national snapshot is claimed downloaded, normalized or redistributed in this PR.

## Commands (repository root)

```bash
python scripts/eastern_four_localities.py inventory
python scripts/eastern_four_localities.py audit --country all
python scripts/eastern_four_localities.py build --country all --output /tmp/eastern-four.sqlite
python scripts/eastern_four_localities.py verify --db /tmp/eastern-four.sqlite
python scripts/eastern_four_localities.py query --country UA --text Київ --db /tmp/eastern-four.sqlite
python scripts/eastern_four_localities.py query --country MD --text Chișinău --db /tmp/eastern-four.sqlite
python scripts/eastern_four_localities.py postcode --country RU --value '101000'
python -m unittest discover -s tests -p 'test_eastern_four_localities.py' -v
```

The unified CLI exposes the same operations as `python -m localities eastern ...`.

## Approved real-source pin template (initially deliberately invalid)

```json
{
  "schema_version": 1,
  "country": "UA",
  "kind": "administrative",
  "format": "xlsx",
  "source_id": "mininfra-katottg-20260707",
  "snapshot_version": "2026-07-07",
  "acquired_at": "REPLACE_AFTER_DOWNLOAD_WITH_OFFSET_AWARE_TIME",
  "source_url": "https://mininfra.gov.ua/diialnist/rozvytok-mistsevoho-samovriaduvannia/kodyfikator-administratyvno-terytorialnykh-odynyts-ta-terytorii-terytorialnykh-hromad",
  "code_scheme": "KATOTTG",
  "rights_reviewed": false,
  "commercial_reuse_reviewed": false,
  "license": "REVIEW_EXACT_RELEASE",
  "filename": "katottg.xlsx",
  "bytes": 0,
  "sha256": "REPLACE_WITH_64_CHARACTER_HASH",
  "coordinate_crs": "not_provided",
  "sheet": "REVIEW_REAL_SHEET",
  "header_row": 1,
  "field_map": {"id": "REVIEW_REAL_SOURCE_CODE_FIELD", "name": "REVIEW_REAL_NAME_FIELD"}
}
```

The example **must not** pass acceptance. For huge RU GAR exports, pin an independent **region-specific ZIP**, select `format=zip_xml`, `member=<exact source XML member>`, `record_tag=<exact source element, e.g. OBJECT or HOUSE>`, and map attributes `id`, `name`, `parent_id` etc from the **actual** version's schema. No FIAS lineage or active-status is invented by this generic adapter. Both historical and withdrawn records must be handled according to dated source metadata before being marked current.

```bash
python scripts/eastern_four_localities.py build --country UA \
  --pin /sources/UA/approved-pin.json --source-root /sources/UA \
  --output /new/ua-admin-with-geonames.sqlite
```

## Source provenance and unresolved rights

| Country | Official target | Published evidence / known constraint | Actual new source data |
|---|---|---|---|
| MD | [BNS CUATM XLSX](https://statistica.gov.md/files/files/Clasificatoare/CUATM_2025.xlsx) | 2025 workbook; a 2025-10-17 amendment and usage rights must be checked | Not ingested |
| UA | [Ministry KATOTTG](https://mininfra.gov.ua/diialnist/rozvytok-mistsevoho-samovriaduvannia/kodyfikator-administratyvno-terytorialnykh-odynyts-ta-terytorii-terytorialnykh-hromad) | 2026-07-07 edition listed, authoritative XLSX still to pin and compare | Not ingested |
| BY | [Belstat / SOATO](https://www.belstat.gov.by/) | OКРБ 003-2017 classification; public official current CSV and redistribution license not established | Not ingested |
| RU | [FNS GAR/FIAS](https://www.nalog.gov.ru/opendata/7707329152-fias/), [Rosstat OKATO](https://www.rosstat.gov.ru/opendata/7708234640-okato) | FNS lists a 2026-11-03 release, very large XML ZIP; Rosstat OKATO CSV separate | Not ingested |

## Verification boundaries

Passing an integrity audit only establishes that **saved source bytes** have not changed. It does not mean administrative changes are current, any national address is present, a postal code is assigned, a place is accessible, or delivery is supported. All published data layers retain source license and attribution separately. Independent reference data and carrier checks are necessary for a future delivery-grade address service. Retain `XK`/`UA`/`RU` identity namespace boundaries; do not infer internationally accepted territorial claims from issuer listings.
