# OSM/Geofabrik place-node reference layer — ODbL 1.0

This folder is intentionally segregated from GeoNames CC BY 4.0 and the
official/statistical administrative CSVs. It has a distinct database licence:
OpenStreetMap contributors, **Open Database License 1.0**.

- Attribution: © OpenStreetMap contributors, https://www.openstreetmap.org/copyright
- Original country extracts: https://download.geofabrik.de/africa.html
- License: https://opendatacommons.org/licenses/odbl/1-0/
- Types: node features with place=city/town/village/hamlet/suburb/neighbourhood/quarter/locality and a non-empty name.
- Country fields: ZA, NG, KE, GH. Other places/ways/relations, buildings, road centrelines and individual address points are **not** included.
- Node identity remains `osm:node:<ID>`. Do not automatically equate OSM node identity with GeoNames IDs, postal codes or legally recognized administrative boundaries.
- Metadata: each `CC/source-receipt.json` records source PBF MD5, SHA256, byte length, source URL, derived gzip SHA256, place counts and per-place-type counts.
- The original PBF is too large to store in the repository; the compressed place-node CSV is a derived database. Distribution/usage must obey ODbL including applicable share-alike and attribution obligations. Evaluate compatibility before combining into any other single distributed database.
- Source recency is per actual Geofabrik download, not a claim of fixed national governmental admin geography.

Use a Python environment with `osmium==4.3.2`:

```bash
python registries/africa/import_osm_place_nodes.py --country KE
python registries/africa/verify_expansion.py --check
```

Actual country import is established **only** if the committed source receipt and compressed CSV both exist and their hashes/counts match. Merely adding this README or the GitHub Actions workflow is not proof of import.
