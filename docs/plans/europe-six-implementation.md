# Six-country European address enhancement: LT / LV / SI / HR / AT / SE

This is a **source-intake implementation**, not a claim of national address coverage.
The existing European GeoNames/LAU rows are kept unchanged. Official address
registers are separate source layers; equality of a place name is not an identity join.

## Existing baseline

- **LT, LV, SI, HR, SE**: Existing `registries/europe/countries/{CC}` GeoNames baseline; postal relationship and Address1 remain not loaded in that particular baseline.
- **AT**: A BEV pinned relational ZIP has already been processed through `scripts/western_europe_sources.py` and accepted validation in `releases/hierarchy/western-europe/`. Do not re-ingest or double-count it. GeoNames recorded 31 unresolved immediate parents, a separate task.
- **SE**: The Lantmäteriet `Belägenhetsadress Nedladdning, vektor` GeoPackage / STAC download requires application/legal review despite being fee-free. No bulk file is downloaded or claimed here.
- **LV**: The provider describes a coordinate transition on **2026-10-07** from LKS-92 TM to LKS-2020 TM; do not silently relabel existing geometry.

The machine-readable source review is `docs/plans/europe-six-sources.json`. It contains only official source *candidates*. It does not grant license clearance or pin source bytes.

## Processing contract

Only accept a **local, source-specific snapshot** after a human/operator has identified the exact downloaded file, observed schema, license/reuse conditions, original reference system and reference date. For each accepted file provide a manifest such as:

```json
{
  "country": "LV",
  "source_id": "LV-VZD-verified-snapshot",
  "snapshot_date": "YYYY-MM-DD",
  "rights_reviewed": true,
  "path": "relative/path/to/source.csv",
  "bytes": 123,
  "sha256": "<64 lowercase hex characters>",
  "format": "csv",
  "delimiter": ";",
  "coordinate_crs": "unknown",
  "kind": "address",
  "fields": {"id": "EXACT_SOURCE_ID", "street": "EXACT_STREET_FIELD", "postcode": "EXACT_POSTAL_FIELD"}
}
```

The placeholder fields above are **not official VZD column names**. Replace them only after inspecting a real file. Supported formats: `csv`, `csv_zip` (with an explicit `member`), `jsonl`, small `geojson`, `gml` (explicit `record_selector` local tag), and `gpkg` (explicit `record_selector` table). Complex GML/XML field paths need a country-specific adapter rather than guessing from leaf labels. GeoPackage geometry is deliberately not decoded.

```bash
python3 scripts/europe_six_official.py catalog
python3 scripts/europe_six_official.py audit --manifest /path/to/accepted-pin.json --data-root /pinned/raw
python3 scripts/europe_six_official.py normalize --manifest /path/to/accepted-pin.json --data-root /pinned/raw --output /new/export.jsonl
python3 -m unittest tests/test_europe_six_official.py -v
```

Validation is fail-closed for stale SHA/length, missing fields, duplicate source IDs, missing rights review, invalid paths, unsafe ZIP members and attempts to overwrite outputs. Numbers, IDs and postal codes are preserved as **strings**. Coordinate values retain their original CRS label; they are not converted to GPS and are not automatically emitted as WGS84. Every produced row is marked `source_record_only` and `not_verified` for delivery.

## Acceptance gates for all six

1. Capture the actual official URL, download or API permission, immutable bytes, original timestamps, SHA-256 and license NOTICE.
2. Confirm the source's real field mapping and CRS, distinguish current/historical/cancelled, and keep provenance.
3. Run independent record-identity, parent, postcode, address number and coordinate checks against a source-independent evaluation set.
4. Separate valid syntax, recorded address, current official address, and delivery eligibility. Never infer national completeness from file count.
5. Only after all evidence passes, consider country bundle releases and model-training eligibility; preserve source/version separation.

## Specific remaining work

| Country | Next country-specific work |
|---|---|
| LT | Verify Registrų centras AdresoTaskas export schema and reuse rights, pin actual address-point snapshots |
| LV | Map VZD CSV table IDs and validity histories; validate CRS change and postcode/address link |
| SI | Inspect the published GURS Register of addresses export and confirm field naming and access rights |
| HR | Resolve DGU INSPIRE Addresses ATOM feed to its referenced GML files, inspect nested INSPIRE structures |
| AT | Reconcile existing BEV address/road joins with municipality reference and GeoNames parent gaps; avoid adding already pinned records |
| SE | Complete access/legal review for Lantmäteriet STAC GeoPackage before any data retrieval or redistribution |

Reference official portals are stored in `europe-six-sources.json`; no third-party extraction or unverified national completeness is claimed.
