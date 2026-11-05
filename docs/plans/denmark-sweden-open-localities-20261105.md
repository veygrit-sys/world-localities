# Veygrit Denmark & Sweden: independent open address candidate pipeline (2026-11-05)

## Why build independently

The goal is not to wait for authorization to build the entire localities experience. The existing GeoNames/Eurostat and official municipality layers can already serve geographic names. A separate OpenStreetMap-backed source can add **candidate** roads, numbers and source-localized placenames now, with explicit ODbL provenance. This is not a replacement for registered postal address data.

## Deliverables in this change

1. DK/SE origin-allowlisted OSM snapshot downloader with immutable SHA-256 receipts, a bounded download and no API secrets.
2. Large-PBF pyosmium import and small synthetic XML import, indexed by OSM object and category into an SQLite file atomically without overwrite.
3. Unicode-preserving street/house/locality/municipality labels, leading-zero-preserving postcode strings, WGS84 mapped node geometry only, no guessed way centroids, and source country conflict reporting.
4. Search by category, Unicode-folded name and postal code; index integrity and count verification.
5. 29 synthetic offline regression tests; read-only suite runs as CI, full real-data build is a separate manual opt-in with optional archival of the large result.
6. ODbL and attribution metadata; notes describing unverified completeness, actual postcode existence and carrier deliverability.

## Data flow

```text
Geofabrik OSM PBF [ODbL; separately stored]
    | https origin + timestamp + exact hash/size
    v
Pinned source receipt -> libosmium streaming parser
    | keep only approved non-personal name/address tags
    | preserve node coordinates, never infer way centroids
    v
SQLite OSM evidence DB (DK / SE separately)
    | unique OSM IDs per category, category/field indexes
    v
Search + immutable export report (source-qualified candidates)

Existing GeoNames, SCB / Eurostat, DAR / Lantmäteriet:
    remain separate; no fuzzy merge, no false authority upgrade.
```

## Explicitly incomplete

The ingest code and local synthetic test run are complete; **download and full parsing of the large 2026 nationwide PBFs must be performed in an environment with network and sufficient disk**. Full-source counts and coverage percentages are **not** asserted in this version. A PBF import will not make OSM address coverage nationally complete. Official DK DAR authentication and SE Lantmäteriet legal review remain external steps, needed only for an authoritative/independently validated register and commercial re-use under their terms.

When publishing a derived OSM database, retain attribution, ODbL share-alike obligations, source URL and exact source snapshot. Keep the official registries in their current licensing partitions. Never use an unreviewed source as training material or overwrite an accepted official snapshot.
