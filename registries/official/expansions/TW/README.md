# Taiwan official road-name expansion

This layer imports 35,798 distinct source road-name rows from the Ministry of the Interior's **全國路名資料**, catalogue [35321](https://data.gov.tw/dataset/35321), ROC year 115 (2026). The canonical download CSV was retrieved on 2026-11-04. Its exact UTF-8 BOM, CRLF line endings, city/site_id/road text and source order are preserved inside `sources/national-roads-115.csv.gz`. `site_id` is a source administrative-area label, not an independently verified code.

`records.csv.gz` retains all rows, covering 21 source city/county labels and 361 source administrative-area labels. IDs are deterministic, source-scoped hashes of the exact three source strings; they are not official road identifiers. No machine-translated English road names are generated.

Existing `registries/official/TW` files are copied as byte-identical context snapshots. A road's `site_id` may be linked to a postal-area label only when there is one exact-label candidate, or one whitespace-folded candidate when no exact candidate exists. There are 33,846 exact matches and 1,952 whitespace-folded matches. These are label candidates, not proof of legal administrative equivalence. English names come only from official postal-area labels. Three-digit values are postal prefixes, not complete six-digit postcodes.

The first-page official API probe advertised 35,797 total rows while the complete CSV contains 35,798 unique rows. Both observations are retained. The CSV is explicitly canonical; the importer does not select by whichever count is larger, union sources, or present the probe as a complete API snapshot. Source effective date and nationwide current completeness are unknown.

This road-name list does not establish house numbers, buildings, address existence, six-digit postcodes, geocodes, delivery coverage or serviceability. No such completeness claims are made.

Rebuild and verify offline from the retained sources:

```sh
python scripts/import_tw_official.py build \
  --source registries/official/expansions/TW/sources/national-roads-115.csv.gz \
  --api-probe registries/official/expansions/TW/sources/api-probe-115-page1.json.gz \
  --output /tmp/tw-road-rebuild
python scripts/import_tw_official.py verify
```

`build` requires a new output folder. `verify(folder)` checks source/file SHA-256 receipts, replays every canonical row against the bundled postal context, checks identity and parent-city consistency, and compares category counts. Retrieval is not an upstream freshness guarantee. File hashes, source URLs, licence terms, provenance and linkage-source hashes are in `coverage.json` and `sources.json`.
