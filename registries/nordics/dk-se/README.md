# Denmark and Sweden — Veygrit owned locality index

The own code performs indexing, normalization, querying, import/replay and
source-layer isolation. It **does not create official addresses by inference**.
It reuses source-qualified GeoNames, Eurostat and Sweden SCB data already in the
repository. The output is NOT a complete address file, verified deliverability
register, or a merged/licenseless address database.

## Supported baseline

* DK: historical/observational GeoNames feature records (7,404) and separate
  Eurostat LAU 2024 source-period observations (99). The latter is a statistical
  classification, NOT an assertion about today's legally registered municipality list.
* SE: historical/observational GeoNames feature records (33,003), separate
  Eurostat LAU 2024 source-period observations (290) and the existing
  2026 SCB 21-county/290-municipality **transcription** (311 projected records).
  The SCB transcription still requires an independent official XLSX replay.

Totals count source observations; source overlaps are deliberately not merged.
No estimate of distinct live municipalities, physical roads, or deliverable
addresses is made by adding source observations together.

## Run the index

From the repository root (Python 3.11+, standard library only):

```sh
python scripts/dk_se_localities.py build-places --root . --output /tmp/dk-se-places.sqlite3
python scripts/dk_se_localities.py search --database /tmp/dk-se-places.sqlite3 --country DK --text København
python scripts/dk_se_localities.py search --database /tmp/dk-se-places.sqlite3 --country DK --text Kobenhavn
python scripts/dk_se_localities.py search --database /tmp/dk-se-places.sqlite3 --country SE --text Stockholm --kind municipality
python scripts/dk_se_localities.py search --database /tmp/dk-se-places.sqlite3 --country SE --text 0180 --kind municipality
python -m unittest discover -s tests -p 'test_dk_se_localities.py' -v
```

All inputs are validated before creating a new immutable SQLite database.
Output names must be new; existing databases are never replaced. The retained
source labels (Danish/Swedish) are not automatically inferred as English
translations. Loose search aliases such as `ø -> o` are search keys only.

## Add OpenStreetMap roads and tagged addresses (independent ODbL layer)

The existing project tools (`scripts/osm_stream.py` and `scripts/osm_evidence.py`)
can process separately downloaded **pinned** Geofabrik `denmark-latest.osm.pbf`
and `sweden-latest.osm.pbf` extracts. The source receipt must include original
size/SHA-256 and respect the ODbL attribution and other requirements. The raw
PBF may be large: use the already supported `osmium` streaming export for
country-size archives; `osm_pbf_lite.py` is deliberately small-extract only.

```sh
# Step 1: create a reviewed OSM source receipt and export using the existing
#         project script; see scripts/osm_evidence.py for its manifest contract.
python scripts/osm_stream.py export --manifest /approved/osm-manifest.json \
  --data-root /pinned/osm --output /new/dk-se-osm-evidence

# Step 2: build search indexes from the verified evidence (each country separately)
python scripts/dk_se_localities.py import-osm --exported /new/dk-se-osm-evidence \
  --country DK --output /new/dk-osm-evidence.sqlite3
python scripts/dk_se_localities.py import-osm --exported /new/dk-se-osm-evidence \
  --country SE --output /new/se-osm-evidence.sqlite3
python scripts/dk_se_localities.py search --database /new/dk-osm-evidence.sqlite3 \
  --country DK --street Vej --number 003A
```

These files contain **tagged community observations, not certified roads,
addresses, national completeness or delivery endpoints**. Geofabrik extracts
can contain border buffered areas. Keep the ODbL source DB separate from the
official address and CC-BY place layers; follow ODbL rules for public derivatives.
Do not try to automatically infer an official street-to-house join from a name.

## Add official source snapshots (separate authorized layer)

The existing `scripts/nordic_localities.py ingest` parser is reused. It accepts
source-specific **CSV, gzip CSV, ZIP/CSV, JSONL or GeoJSON** with exact content
hash, known publisher URL, explicit source column mapping, explicit CRS, a
reviewed reuse licence and authorized access. No guessed column names or
missing credentials are bypassed. A Datafordeler CSV entity extract is the
simplest DK route; a reviewed CSV export from Lantmäteriet/SCB the SE route.

1. **DK:** Create a Datafordeler account and system/API key. Obtain authorized
   DAR entity CSV exports for `Adresse`, `Adressepunkt`, `Husnummer`,
   `NavngivenVej`, `Postnummer` (and DAGI `Kommuneinddeling` if needed).
   Record each source's original timestamp, identity, status, validity and
   relations **separately**. JSON/ZIP/JSON from DAR should first be transformed
   by a schema-specific audited converter to CSV, rather than guessed in a
   generic parser. Avoid the retired DAWA (shut down 2026-10-01).
2. **SE:** Download official name data from Ortnamn (free but requires account).
   For official `Belägenhetsadress` address points, a Lantmäteriet Geotorget
   account and **approved legal assessment** is necessary even though the
   product has no licence fee. The official output is GeoPackage via STAC;
   use a separately audited converter with verified source lineage and terms
   before bringing it into CSV/JSONL. SCB open tätorter is not an address-point
   register. Nationwide NVDB road exports via Lastkajen require registration.
3. Verify source licence separately for storage, commercial use, redistribution,
   ML training and combining with other layers. A free data price is not proof
   of full reuse permission. Do not publish protected address points in Git.

For a reviewed CSV file with true source headers, prepare a local manifest like:

```json
{
  "schema_version": 1,
  "country": "DK",
  "source_id": "REPLACE-WITH-ACTUAL-SNAPSHOT-ID",
  "source_url": "https://datafordeler.dk/dataoversigt/danmarks-adresseregister-dar/dar-fildownload/",
  "license": "REPLACE-WITH-ACTUAL-REVIEWED-LICENSE",
  "rights_reviewed": true,
  "access_authorized": true,
  "retrieved_at": "2026-11-05T00:00:00Z",
  "format": "csv",
  "kind": "address",
  "national_address_completeness_verified": false,
  "deliverability_verified": false,
  "fields": {
    "id": "REPLACE_WITH_SOURCE_ID_COLUMN",
    "name": "REPLACE_WITH_REAL_SOURCE_LABEL_COLUMN",
    "postcode": "REPLACE_WITH_REAL_POSTCODE_COLUMN"
  },
  "coordinate_crs": "unknown",
  "path": "snapshot.csv",
  "bytes": 0,
  "sha256": "REPLACE_WITH_REAL_SHA256"
}
```

This is an intentionally **invalid template** (`bytes:0`, placeholder hash):
first inspect the real source schema and fill the exact snapshot metadata.
Never set `rights_reviewed` or `access_authorized` to true without evidence.

```sh
python scripts/dk_se_localities.py import-official \
  --pin /approved/source-pin.json --source-root /approved/raw \
  --country DK --output /new/dk-official-address.sqlite3
python scripts/dk_se_localities.py search --database /new/dk-official-address.sqlite3 \
  --country DK --postcode 2100
```

Postal syntax flags are lexicographic checks only. In the official evidence DB
`address_exists` and `deliverable` intentionally remain `NULL` unless separate,
formal, independently evaluated capabilities are implemented. A source record
may be historic, provisional, not currently valid, not occupied, or not served
by a particular carrier. Status and bitemporal validity must be resolved using
the authoritative data model before asserting current official listing.

## Next quality gates

* Onboard real licensed DAR and Lantmäteriet snapshots with original file pins.
* Audit all source entities, dates, active statuses and source-to-source ID joins.
* Measure address precision/recall and false acceptance against held-out real
  addresses with authorized use and separately verify carrier deliverability.
* Replace transcription-based SCB 2026 with independently replayed official XLSX.
* Record source update frequency and original licence in a release audit.

See [source policy](source-policy.json) for publisher links and access boundaries.
