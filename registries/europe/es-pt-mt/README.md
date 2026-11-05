# ES / PT / MT: locality/address quality expansion

This package raises the **integrity and traceability** of Spain, Portugal and Malta locality/address evidence. It does **not** claim complete nationwide address coverage or a postal/carrier-authoritative registry. It preserves the existing `registries/europe/countries/*` and `registries/europe/eurostat-lau/*` layers unmodified.

## Verified input already stored in the repository

| Country | GeoNames baseline records (Sep 2026 release) | Known gaps |
|---|---:|---|
| Spain ES | 39,207 | 131 unresolved parent references; Address1 and postal joins not loaded |
| Portugal PT | 22,115 | Address1 and postal joins not loaded; regional islands must stay in scope |
| Malta MT | 361 | official road/door number and postal joins not loaded |

The 61,683 baseline records are **features/observations**, not distinct deliverable addresses. Eurostat LAU counts (ES 8,132; PT 3,092; MT 68) overlap the baselines and are not added to the feature count.

## Existing-data audit and query

At repository root:

```sh
python scripts/es_pt_mt_precision.py build --output /tmp/es-pt-mt-localities.sqlite
python scripts/es_pt_mt_precision.py verify --db /tmp/es-pt-mt-localities.sqlite
python scripts/es_pt_mt_precision.py search --db /tmp/es-pt-mt-localities.sqlite --country ES --text Madrid
python scripts/es_pt_mt_precision.py search --db /tmp/es-pt-mt-localities.sqlite --country PT --text Lisboa
python scripts/es_pt_mt_precision.py postcode --country MT --value 'VLT 1117'
python -m unittest discover -s tests -p test_es_pt_mt_precision.py -v
```

This validates each GeoNames gzip part against its recorded file length, compressed and uncompressed SHA-256, row count, country and unique ID; then publishes an immutable read-only-searchable SQLite index. A `PASS` verifies byte/row integrity, not completeness or present-day existence.

## Adding true official data (no unapproved download)

1. Download an **actual** source snapshot directly from the listed national authority. Keep the original bytes and license/attribution evidence; record its source date, byte length and SHA-256.
2. Inspect *actual* column names, identifiers, CRS and GeoPackage layers. Choose the correct kind and supply an explicit `fields` map; do not map an unrelated source column because its label looks similar.
3. Save a receipt JSON with schema 1: `country`, `dataset`, `publisher_url`, `license`, `attribution`, `rights_reviewed: true`, `source_date`, `kind`, `format`, `crs`, `path`, `bytes`, `sha256`, `fields`, and `table` for GPKG or `member` for ZIP. `dataset` must be unique and source-specific. Do not put personal names, contacts or dwellings not necessary for a locality query into the field map.
4. Run:

```sh
python scripts/es_pt_mt_precision.py build \
  --repo . --source-root /secure/source/files \
  --receipt /secure/receipts/ES-cartociudad-province.json \
  --output /secure/results/ES-PT-MT-2026.sqlite
python scripts/es_pt_mt_precision.py verify --db /secure/results/ES-PT-MT-2026.sqlite
```

The implementation accepts `csv`, `csv.gz`, `zip-csv`, `jsonl`, small `geojson`, `gpkg` and `zip-gpkg`. GeoPackage is read-only; layer name and CRS must match source metadata. A Point's x/y is preserved **in its original CRS**, never guessed to be WGS84; polygon centroids are not invented. For large CartoCiudad and CAOP country/province files, prefer pinned GeoPackage exports over paginating an API with an unknown download cap.

### What each country's precision work needs

- **ES**: CartoCiudad province GPKG address/entrance and postal/admin relationships; INE Nomenclátor as a *distinct* settlement source. Compare original municipality codes and validate province boundaries. Do not collapse source provenance by matching text.
- **PT**: CAOP2025 mainland, Azores and Madeira separately; DTMNFR stable code + parent checks. INE Base Nacional de Moradas is a different INSPIRE address layer, and its advertised coverage is mainland Portugal. Do not invent island address points.
- **MT**: Registrar official locality and street exports and documented door-numbering records. Verify actual API export access and current authority before accepting. Maltese English/native orthography and street aliases remain distinct. The `[A-Z]{3} ?[0-9]{4}` code pattern is **syntax only**, no postcode master list is loaded.

### Release gates

No nationwide precision claim before (a) source snapshot is genuinely downloaded and pinned, (b) all source IDs replay, (c) administrative, road, postcode and house-number links are checked against official code systems, (d) independent held-out real-address test examples are evaluated, and (e) carrier-specific address rendering and deliverability rules are tested. If any layer is absent, return `unknown` rather than fabricate a match.

Original source rights and notices remain source-specific. No common relicensing of mixed official, GeoNames, or OSM-derived datasets.

## Additional official Portugal CAOP2025 acquisition

`python scripts/pt_caop2025_capture.py --output-dir /new/caop-work` downloads the three CAOP2025 DGT GeoPackage ZIPs for the mainland, Azores, and Madeira into a **new** output location, pins original and extracted byte hashes, discovers only the published parish schema (`dtmnfr`, `freguesia`), checks regional table CRS and counts, and generates separate reviewed receipts for the general ES/PT/MT importer. The workflow `.github/workflows/pt-caop2025-official.yml` builds and verifies the resulting source-separated SQLite index. It does **not** treat official administrative polygons as postal or delivery addresses. The original downloads are excluded from Git commits; the artifact only contains the attribution, provenance report and normalized index.
