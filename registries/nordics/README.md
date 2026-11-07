# Nordics: source-qualified locality and address infrastructure

Scope: DK, FI, IS, NO, SE plus AX, FO, GL and SJ. These nine registry codes are **not** nine independent Nordic countries; official administrative, postal and territorial distinctions are preserved. Greenland (GL) is geographically in North America but part of the broader Nordic area via the Kingdom of Denmark. The UN M49 Northern Europe list is a different classification.

The canonical `registries/europe/` GeoNames and LAU data are reused, not copied; `registries/north-america/admin-seeds.json` supplies only five provisional Greenland municipality-name seeds. Sources are not automatically joined by similar names or coordinates. No Nordic address-file ingestion is asserted as completed by this module.

**実取得の追加（2026-11-08）:** [HMSアイスランドStaðfangaskráの公式CSV 139,795住所点をGitHub Actionsで全件SQLite索引に変換・検証](../../docs/plans/europe-cz-is-it-next-20261108.md)。HNITNUMとHEINUMは異なる識別子。成果物の永続保存・下流の再配布権限・配達可能性は未検証のため、保存済みGeoNamesや他の公式源泉と合算しません。

## Commands (Python 3.11+, no dependencies)

```bash
python scripts/nordic_localities.py inventory
python scripts/nordic_localities.py verify --country all
python scripts/nordic_localities.py search --country SE --text Stockholm --limit 10
python scripts/nordic_localities.py search --country GL --text Nuuk --limit 10
python scripts/nordic_localities.py postcode --country SE --value '123 45'
python scripts/nordic_localities.py compile --country all --output /tmp/nordic-geonames.jsonl.gz
python -m unittest discover -s tests -p 'test_nordic_localities.py' -v
```

`compile` creates a new immutable, source-qualified index; it **never** overwrites. `verify` audits gzip bytes, decompressed hashes, rows, duplicates, country references and the separate Eurostat files. A passing hash or count is not proof of current administrative legal status or address existence.

## Official data imports

Each actual official source must first be downloaded via its lawful official distribution channel and pinned using a reviewed JSON manifest. Then:

```bash
python scripts/nordic_localities.py ingest --pin /path/to/approved-source-pin.json --source-root /new/pinned/data --output /new/output/source-qualified.jsonl
```

`ingest` requires source URL on an authority-specific allowlist, exact SHA-256, size, retrieval timestamp, rights-reviewed status, access authorization where relevant, explicit CRS and source-column mapping. It supports CSV, gzip CSV, ZIP-contained CSV, JSON lines and small GeoJSON FeatureCollections. Importers do not fetch remotely, reuse missing API keys, infer a commercial license, copy unapproved personal-data fields, or treat syntax/official listing as confirmed deliverability.

Country-specific source planning and unresolved access constraints: [Nordic implementation plan](../../docs/plans/nordics-localities-20261105.md). Official source link register: [catalog](catalog.json).

## Acceptance status

- All 8 Europe-coded areas: immutable GeoNames source bundles **already in repository**, verification and search implemented.
- Greenland: five curated, provisional names from the existing North American administrative seeds, **not** a Greenland-wide locality dataset.
- Finland, Norway and Iceland: freely published official address distributions identified; **not downloaded and pinned by this change**.
- Denmark: modern Datafordeler authentication required; DAWA ended 2026-10-01.
- Sweden: Lantmäteriet official address points require legal review; previously accepted SCB municipality index remains separate.
- AX/FO/GL/SJ: authoritative data access/terms or limited coverage still need country-specific acquisition.

Do not publish percentages of national address coverage without an independent target denominator and evaluation.
