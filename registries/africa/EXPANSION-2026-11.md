# Africa priority expansion — recorded delivery and unresolved gaps

Scope: 2026-11-06. This file distinguishes data actually stored in the branch from verification code and unmet objectives.

## Verified new source layers (not unique addresses)

| Country | Source | Source year | Source rows | Ingestion status |
|---|---|---:|---:|---|
| South Africa (ZA) | OCHA/Municipal Demarcation Board, provinces, districts, local municipalities via gbOpen | 2020 | 274 | Imported, original GeoJSON SHA-verified |
| Nigeria (NG) | GRID3, states/FCT and 774 LGAs via gbOpen | 2022 | 811 | Imported, original GeoJSON SHA-verified |
| Rwanda (RW) | NISR village hierarchy | 2022 | 14,823 | Imported, government ID hierarchy and derived CSV SHA-verified |
| Egypt (EG) | OCHA/CAPMAS-origin ADM2 via gbOpen | 2020 | 365 | Imported, original GeoJSON SHA-verified |
| Morocco (MA) | HCP RGPH 2024 communes, third-party harmonized under CC BY 4.0 | 2024 | 1,503 | Imported, pinned Git blob |
| Algeria (DZ) | 69 wilayas and 1,541 communes bilingual transcription | 2026 | 1,610 | Imported, pinned source repository; official commune IDs unavailable |

Counts are not additive to the existing GeoNames base or previous KE/GH 613-unit overlay. Source-level units may be the same geographic entities observed in different archives and years. Authority origin is not the same as current legal codification.

## Previous first-wave verified source overlay

- Kenya: IEBC/OCHA (2020) 47 ADM1 + 290 ADM2 shape IDs = 337.
- Ghana: GSS/USAID (2019) 16 ADM1 + 260 ADM2 shape IDs = 276.
- Source-year spatial membership for 65 KE + 1 GH unresolved GeoNames features. Original missing direct-parent IDs: 69 KE + 11 GH = 80; currently **0 of those 80 officially repaired**. Three strong KE administrative identity candidates lack an original, extant GeoNames ADM2 parent and are not auto-linked.

## Status of Nigerian historical GeoNames 65,444 source records

**NOT MIGRATED.** The archive remains in the private `rei-k/world-address` pinned 2026-09-26 source snapshot. Blob `f47e339f54fd7d34162d16dc1fd73d92c02d1087`, compressed size 2,141,219 bytes, source commit `4efec82671b15a6bca4f0099acb6377c55af9aae`. The connector returns metadata but cannot fetch compressed file bytes. The exact-checksum migration script `registries/africa/restore_pinned_ng.py` is implemented, but has not executed against an authenticated local clone. Do not substitute 2022 GRID3 state/LGA shapefiles or a newer GeoNames download for the historical GeoNames dump.

At the current baseline the original regional gazetteer remains **56 of 60 units / 388,038 GeoNames A/P rows**. The prospective 57-unit / 453,482-row count is **not** active. The newly imported NG **811 state/LGA geographic units** are different data.

## OpenStreetMap locality enrichment

Importer `registries/africa/import_osm_place_nodes.py` and source-checking GitHub Actions workflow support ZA/NG/KE/GH. Source PBF is checked against Geofabrik-provided MD5; records preserve source type, OSM node ID, tagged names, lat/lon, and ODbL attribution in an **isolated separate source layer**. Only a completed country workflow and persisted `osm-localities/CC/source-receipt.json` with byte checks establishes actual import; a workflow being queued or running does not.

## Address code diagnostics

`registries/africa/priority_address_codes.py` distinguishes country-specific postal / digital-address **syntax** and returns unknown for physical address validation and deliverability. For Nigeria, ordinary 6-digit historical postal code and 2026 digital alphanumeric building code are distinct systems; the official NIPOST API/bulk access is separate and may require authorization. Ghana's GhanaPostGPS codes are not generic ordinary numeric ZIP codes. Rwanda has no presumed universal postal-code regex. None of this supplies a verified address/point or universal carrier acceptance.

## Quality and audit

Use Python 3.11+:

```bash
python registries/africa/verify_expansion.py --check
python -m unittest discover -s registries/africa -p 'test*.py' -v
python registries/africa/priority_audit.py --wave 1 --check
python -m localities country verify --country KE
python -m localities country verify --country GH
```

Quality gates: pinned source SHA and dataset release year, record identity uniqueness, valid names, known child/parent code references where exposed, exclusion of blank synthetic values, licence separation, historical administrative boundary differences and explicit unmatched/ambiguous review buckets. Delivery success, current legal administrative certification and national address completeness require independent, dated evidence.

## Next required source verification

1. Authenticated old private repository checkout and exact historical Nigeria blob replay (only then update Africa manifests and country module records).
2. For KE/GH, authoritative *current national government* subcounty/district identifiers; reconcile historical 2019/2020 geoBoundaries and 80 missing original source references with time-valid, independently reviewed crosswalk. Never invent direct GeoNames parent IDs.
3. ZA/NG/KE/GH: match new ODbL tagged localities using candidate IDs with duplicate and border checks; road, building address and carrier delivery coverage remain separate layers.
4. RW/Egypt/Morocco/Algeria: further dated parent code and postal authority data and independent address evaluations. Distinguish original official codes from third-party row ordering and names.

### Sources and terms

- NISR: https://statistics.gov.rw/terms-use and 2022 Village Boundary 2022 service.
- GeoBoundaries original authority-origin boundaries: https://www.geoboundaries.org/ ; included per-source licenses are CC BY 3.0 IGO and CC BY 4.0.
- Morocco HCP and Lehnert RGPH harmonized data: https://github.com/machinemirror/morocco-census/blob/main/LICENSE-DATA . Cite HCP and Lehnert (2026), https://doi.org/10.5281/zenodo.22953567 .
- Algeria bilingual records (MIT): https://github.com/islam-re/Algeria-wilayas ; original government gazette must be consulted for legal date and boundaries.
- Geofabrik PBF / OpenStreetMap ODbL: https://download.geofabrik.de/africa.html and https://www.openstreetmap.org/copyright .
