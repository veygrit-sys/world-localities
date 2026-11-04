# South America locality and administrative gazetteer

Source-preserving GeoNames country extracts: the existing fourteen snapshots were retrieved on 2026-10-01; Argentina and Paraguay were retrieved on 2026-10-02. This is a gazetteer baseline, not a verified current register of all municipalities, postal addresses, or deliverable destinations. All source A/P features are retained with no population cutoff, including historical and abandoned features. Feature classes other than A/P are excluded and counted in each country's metadata.

## Verified publication totals

This publication contains **16 of 16 UN M49 South America countries/areas**. Argentina (AR) and Paraguay (PY) have the same entity, ADM1 projection, alternate-value and metadata structure as the previous fourteen. `pending_country_codes` is empty. `complete_pack` means country/area inclusion in this gazetteer; official municipality completeness and postal deliverability remain unverified.

- 16 published countries/areas; 272,379 source entity identities
- 21,522 administrative rows; 250,721 populated-place rows; 136 other A-class rows
- 339,656 alternate-name/value observations linked by source ID
- 554 unresolved direct-parent references retained explicitly
- Full-pack integrity and exact derived-column replay passed; 33 data/reconstruction/scope regression tests passed

Counts are source identities, not deduplicated real-world municipality or postal-address totals. English and local-language coverage remains incomplete; see `summary.json` and country metadata.

| Added country | A/P entities | Administrative rows | Locality rows | Alternate values | Source-tagged English entities |
| --- | ---: | ---: | ---: | ---: | ---: |
| Argentina | 15,496 | 605 | 14,889 | 41,207 | 743 |
| Paraguay | 15,369 | 8,498 | 6,868 | 9,247 | 56 |

These administrative counts include multiple GeoNames levels, including 8,234 ADM3 records in Paraguay, and are not counts of municipal governments. Neither new country's selected aliases have a `post` value. The full pack retains the previous 94 source postal observations without asserting delivery coverage.

## Scope and files

UN M49 intermediate region 005, South America, defines the scope. This publication includes all sixteen areas: AR, BO, BR, BV, CL, CO, EC, FK, GF, GS, GY, PE, PY, SR, UY, VE. Bouvet Island, the Falkland Islands (Malvinas), French Guiana, and South Georgia and the South Sandwich Islands are included according to that statistical classification. This is not a sovereignty determination. Source country assignments and secondary country codes are preserved without reinterpretation.

- `scope.json`: sourced country/area profiles and any separate external coverage
- `countries/CC/entities.csv.gz`: all retained administrative, populated-place, and other A-class rows, with all 19 original GeoNames fields
- `countries/CC/admin1.csv`: duplicate display projection of ADM1 entities; do not count twice
- `countries/CC/alternate-values.csv.gz`: all alternate-name/value observations whose GeoNames entity ID is in the country's retained entity set
- `countries/CC/metadata.json`: URLs, retrieval date, source hashes, counts, output hashes, label coverage and unresolved hierarchy counts
- `coverage.csv`, `manifest.json`, `verification.json`: country counts, publication inventory and integrity results
- `schema.json`: exact entity and alias columns and meaning
- `sources/geonames-readme.txt`: upstream schema and attribution statement
- `sources/source-inventory.json`: source-input byte hashes and reuse provenance
- `sources/AR.zip`, `AR-alternatenames.zip`, `PY.zip`, `PY-alternatenames.zip`: retained original new-country archives, with larger files represented in `.parts/`
- `sources/countryInfo-2026-10-02.txt`: exact new-country profile/language-list snapshot
- `sources/baseline-14-publication.json`: 73 immutable country payload, projection, metadata and part hashes pinned to main `a7439bc`

The sixteen original M49 source rows are reused from main's 2026-10-01 snapshot. Its retrieval date is preserved in `scope.json`; no new M49 HTML or country grouping is invented. The live M49 HTML is not compatible with the original twelve-column parser, so `--scope-from scope.json` provides explicit offline reuse. AR/PY metadata separately identifies their 2026-10-02 `countryInfo` bytes. All previous fourteen country files, profiles and split parts retain their exact published bytes and paths.

The manifest explicitly reports what is prepared; the M49 scope itself is not proof of official administrative completeness. Bouvet Island has no A/P locality or ADM1–5 record in this extract; its source territory feature is retained, rather than inventing a settlement or state. Country profiles are reference anchors and are not added to entity counts.

## Identity and hierarchy

`gn:<geonameid>` is a stable source identity; `gn-alt:<alternateNameId>` is an alternate-value source identity. `country:CC` is a country/area profile reference. These are not cross-source reconciled real-world IDs. Source country and administrative codes remain strings, preserving leading zeroes, and must not be assumed to be ISO 3166-2 codes.

Direct parents are resolved only by unique, exact, complete source administrative-code tuples. An absent intermediate parent stays unresolved; an ADM1 match is retained separately in `state_id`, without substituting it as the direct parent. No name-similarity or coordinate-proximity join is used. Historical administrative entities cannot parent active administrative records or settlements. `country_scope_only` means only country membership was available, not direct administrative governance.

The source ADM1–5 hierarchy has different meanings across countries. Its rows must not all be called municipal governments. The source can be outdated, incomplete or inconsistent with legal boundaries; current official hierarchy has not been independently certified. Population zero may mean unknown. Coordinates are source reference points, not boundaries or entrances.

## Language and postal values

The primary `name` and flat `alternatenames` fields have no source language tags. Their language remains undetermined; `asciiname` is an ASCII rendering and is never labeled as an English translation.

Language-tagged observations are in `alternate-values.csv.gz`. All source flags and date ranges are preserved, as are special source values such as `post`, `link`, and `wkdt`. A `language_name` value is source-attested for its stated language. The country-language coverage count compares exact source language tags to the source `countryInfo.txt` language list. This is not a claim that every name is indigenous or officially approved. A name can have multiple alternatives in one language; none is silently selected as authoritative.

The metadata's `current_english_name_entities` and `current_country_language_name_entities` count names that are not marked historic and have no end-period. These are source-filter counts, not independent confirmation that a name is legally current. Missing English/local-language names remain missing; no translation, transliteration or language guess is substituted. Label coverage is materially incomplete and is disclosed per country.

Postal values are only rows explicitly tagged `post` by GeoNames and linked to the exact source entity ID. There is no name-based postal join, no fabricated postcode, no street address or Address1 field, and no postal deliverability validation.

## Large-file publication and automatic reconstruction

Twelve compressed files (nine derived gzip files and three original ZIPs) are distributed as 37 ordered raw binary chunks of at most 512 KiB under `.parts/`. `split_manifest.json` records original paths, byte counts, full SHA-256/Git blob hashes and each ordered part's byte count and SHA-256. These chunks are not separate gzip or ZIP streams; exact concatenation restores the original compressed bytes without recompression or data changes. The listed originals are absent from the published tree. The previous fourteen-country publication representation is unchanged, including its unsplit gzip files.

`query.py` automatically materializes the requested country; `build.py verify` automatically materializes every country before validating it. From the repository root, explicit restoration is available with `python -m localities materialize --registry south-america --country AR`. This is offline and requires no extra packages. A clean publication-only copy is tested with all twelve listed originals absent, including the shared reconstruction suite. See `publication_verification.json`. A writable checkout is needed for the reconstructed files. Use a writable copy if the installed package is read-only. The original canonical metadata and integrity hashes remain valid.

`publication.py pack` creates/checks parts without altering canonical bytes. `publication.py verify` checks the previous 73 published file hashes before any restoration, uses an isolated clean copy, runs all tests and full entity replay, and independently rebuilds all eight AR/PY country files from retained source archives. All eight rebuilt files match exactly. Other fourteen upstream ZIP pairs were not shipped by PR #9: their preserved entity columns replay exactly and their recorded archive hashes match the inventory, but replay of those original ZIP bytes was not performed.

Reconstruction rejects path traversal, symlink paths, missing/corrupt/wrong-size parts, invalid aggregate sizes, checksum mismatches, and mismatched existing outputs. Existing correct files are reused. A temporary output is fully verified before an exclusive link creates the destination; existing output is never overwritten.

## Use and reproduce

Python 3.11+ and the standard library are sufficient:

```sh
python query.py --country UY --text Montevideo --limit 10
python query.py --country PE --kind admin_subdivision --level 1
python build.py verify
python -m unittest discover -v
python publication.py pack
python publication.py verify
```

To rebuild, download each selected `CC.zip` from `https://download.geonames.org/export/dump/`, each country alias archive from `https://download.geonames.org/export/dump/alternatenames/CC.zip` to `CC-alternatenames.zip`, plus `countryInfo.txt` and the UN M49 overview HTML as `m49.html`. Then run:

```sh
python build.py build --inputs /path/to/inputs --scope-from scope.json --retrieved-on YYYY-MM-DD
python build.py verify
```

`--countries AR PY` limits regeneration to these countries and preserves unselected country profiles. Missing source bytes are named before output is written. Scope, source inventory and verification must agree before a full-pack result passes. Source URLs are mutable daily exports; the recorded hashes identify the retrieved bytes. Raw selected entity columns and all included alternate-value source columns survive in the shipped CSVs. Integrity verification replays all entity-derived columns exactly, checks file hashes, unique source IDs, country scope, references, acyclic hierarchy, alias linkage, source inventory, language coverage and postal flags. Deterministic gzip excludes timestamps and filenames. Re-compression may depend on Python/zlib versions.

For an offline AR/PY rebuild using the retained snapshots:

```sh
(cd .. && python -m localities materialize --registry south-america --country AR)
(cd .. && python -m localities materialize --registry south-america --country PY)
mkdir -p /tmp/south-america-inputs
cp sources/AR.zip sources/AR-alternatenames.zip sources/PY.zip sources/PY-alternatenames.zip /tmp/south-america-inputs/
cp sources/countryInfo-2026-10-02.txt /tmp/south-america-inputs/countryInfo.txt
python build.py build --inputs /tmp/south-america-inputs --scope-from scope.json --countries AR PY --retrieved-on 2026-10-02
python build.py verify
python publication.py pack
python publication.py verify
```

## Related layers and licensing

The destination's official IBGE Brazil municipal layer is a separate dataset. Do not merge same-named gazetteer settlements and official municipalities automatically, and do not add their counts as distinct real-world localities. No official layer is copied or overwritten here.

GeoNames data and derived CSVs: Creative Commons Attribution 4.0. Source: https://www.geonames.org/ and https://download.geonames.org/export/dump/. License: https://creativecommons.org/licenses/by/4.0/. Changes are the A/P selection, country packaging, typed identities, administrative-code linkage and validation metadata. GeoNames provides the data as-is, without completeness or accuracy warranty. Code is MIT; see `LICENSE` and `NOTICE.md`.
