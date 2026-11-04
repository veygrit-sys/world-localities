> **2026-10-15 現行統合版:** コスタリカの追加レイヤーとメキシコの別出典を含め、中央アメリカ8/8か国を参照できるようになりました。
> [追加内容・検証範囲](ENRICHMENT_20261015.md)、`query_enriched.py`、`quality.py`を参照してください。
> 以下の6か国版の説明と既存manifest/coverageは、変更していない保存済み原本の説明です。

# Central America locality and administrative source snapshot

Six country batches contain 53,257 GeoNames administrative/populated-place
entities, 42,606 language-tagged alternate names and 6 direct-ID postal
associations. Source retrieval: 2026-10-01. This is a source-preserving gazetteer,
not a complete current legal municipality register or delivery-validation service.

## Explicit scope

UN M49 Central America (013) comprises Belize (BZ), Costa Rica (CR), El Salvador
(SV), Guatemala (GT), Honduras (HN), Mexico (MX), Nicaragua (NI), Panama (PA).
This partial publication contains 6 of the 8 M49 members: BZ, GT, HN, NI, PA, SV.
Costa Rica (CR) is pending approval and has no source or derived country records
in this package. Mexico (MX) is separate and is not included in this batch;
[`official-registry/MX`](../official-registry/MX) is an independently managed
source layer. No complete eight-country coverage is claimed.

Country membership follows the [UN M49 classification](https://unstats.un.org/unsd/methodology/m49/).
It makes no additional territorial/legal determination. No Caribbean or South
American country is included, and Address1, street/building addresses and boundary
polygons are outside scope.

## Coverage

| Country | Source A/P entities | Administrative subdivisions | Populated places | Unresolved source parents | Language-tagged names | Direct-ID postal rows |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Belize | 537 | 8 | 528 | 0 | 1,093 | 0 |
| Guatemala | 17,363 | 362 | 16,981 | 6 | 17,697 | 0 |
| Honduras | 13,286 | 316 | 12,966 | 0 | 2,928 | 4 |
| Nicaragua | 2,817 | 177 | 2,632 | 2 | 3,483 | 0 |
| Panama | 14,043 | 775 | 13,267 | 0 | 13,624 | 2 |
| El Salvador | 5,211 | 321 | 4,889 | 0 | 3,781 | 0 |

Other administrative features and political entities are retained separately;
therefore entity counts exceed subdivisions plus populated places. Counts are
source rows, not unique real-world place identities. `admin1.csv` is a duplicate
preview and must not be added to entity totals. Country roots in metadata are
scope anchors, not additional settlement rows. See `coverage.csv`,
`locale_coverage.csv` and country metadata for machine-readable counts.

## Important quality limits

- El Salvador has 14 ADM1, 44 ADM2 and 262 ADM3 rows. These counts match the
  [post-reform organization described by its Legislative Assembly](https://www.asamblea.gob.sv/node/12819).
  Count agreement does not certify every label, boundary or parent assignment.
- Eight immediate parent references remain unresolved; three locality rows have
  country-scope-only placement. Deeper missing references are never replaced by
  a guessed immediate state parent. All original administrative code strings are
  preserved; GeoNames ADM1 codes are not automatically ISO 3166-2 codes.
- Source labels are not presumed legally official, native-language labels or
  English translations. The main `name` and `asciiname` columns have unspecified
  language. The locale layer carries only explicit source language tags.
- English and local-language coverage is incomplete. Names may be historic,
  colloquial or short; original flags and date ranges are preserved. The query
  chooses non-historic, non-ended labels with explicit locale/fallback evidence.
- The six postal links are GeoNames `post` aliases on exact entity IDs, not an
  official postal-authority crosswalk. Carrier validation is false. An empty
  postal table means no such source associations were loaded, not that the
  country has no postcodes. Leading zeros are preserved.
- `gn:` IDs may also occur in another regional/source layer. Deduplicate by
  source identity only when appropriate; do not sum snapshots blindly.

## Files and independent country use

Each `countries/<CC>/` contains:

- `entities.csv.gz`: stable identities, original codes and names, source feature
  types, parent evidence and quality flags (30 columns, same core schema as Africa)
- `admin1.csv`: small human-readable first-level preview
- `metadata.json`: entity counts, source URL/checksum, dates, quality limits
- `names.csv.gz` and `locale_metadata.json`: exact-ID, language-tagged names
- `postal_links.csv.gz`: only direct-ID source postal evidence

The corresponding `sources/<CC>.zip` and `sources/alternatenames/<CC>.zip` preserve
exact downloaded bytes. Guatemala and Panama source ZIPs are published as four
ordered binary parts of at most 512 KiB, described in `split_manifest.json`; their
full-file hashes remain canonical. The shared `localities.materialize` module verifies every part and the
reconstructed size/SHA256, rejecting traversal, symlinks and mismatched existing
outputs. Build and verification restore these sources automatically; explicit
restoration from the repository root is available with
`python -m localities materialize --registry central-america --country GT` (or `PA`).
These files support an independently testable country batch.
No network or third-party Python packages are needed to read, query or verify.

```sh
cd central-america-registry
python verify.py --countries BZ
python query.py --country GT --text 'Guatemala' --language es --limit 10
python query.py --country SV --level 2 --language en --limit 10
python test_central_registry.py -v
python -m unittest discover -s ../tests -p 'test_split_materialization.py' -v
python verify.py --report source_verification.json
```

With all six included countries present, rebuild/verify the exact data from local sources:

```sh
python build.py build --inputs sources
python build.py summarize
python build.py verify
python build_names.py build --inputs sources --countries BZ GT HN NI PA SV
python build_names.py verify --inputs sources --countries BZ GT HN NI PA SV
```

`schema.json` describes entity columns; `locale_schema.json` describes label and
postal fields. `sources.json` records raw checksums and code provenance.
All 19 regression tests and raw-source replay checks pass; those are structural
and reproducibility checks, not proof of source completeness. See [NOTICE.md](NOTICE.md)
for attribution, transformations and separate software/data licenses.

The shared `sources/countryInfo.txt` is a documented derivative of the downloaded
country metadata with the CR row omitted; its original and filtered checksums are
recorded in `sources.json`. All six included country ZIPs and derived country
files retain their previously validated bytes.
