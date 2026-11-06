# Africa Localities — priority waves and evidence gates (2026-11-06)

## Execution order

Priority is fixed as **ZA → NG → KE → GH**, followed by **RW → EG → MA → DZ**.
The two waves are registered in [priority_sources.json](priority_sources.json).
This records actionable **source leads**, not imported or matched official datasets.

| Wave | Country | Current GeoNames A/P snapshot | Immediate blocking task |
|---|---|---:|---|
| 1 | ZA South Africa | 13,828 rows | MDB municipality and Stats SA place hierarchy crosswalk |
| 1 | NG Nigeria | **not migrated** | Restore pinned original `entities.csv.gz` (2,141,219 bytes; SHA in `migration.json`) |
| 1 | KE Kenya | 9,381 rows | KNBS official unit matching; 69 unresolved parents |
| 1 | GH Ghana | 16,289 rows | GSS regions/districts; 11 unresolved parents |
| 2 | RW Rwanda | 12,894 rows | NISR 2022 village ID chain |
| 2 | EG Egypt | 12,290 rows | CAPMAS administrative directory vintage |
| 2 | MA Morocco | **not migrated** | Restore pinned original source (1,736,680 bytes) and compare HCP RGPH 2024 |
| 2 | DZ Algeria | 10,492 rows | Tie 2026 new wilayas to official commune hierarchy; preserve transitional carrier formats |

*Counts mean current **stored source rows**, not unique real addresses, current municipalities, address validation accuracy or delivery coverage. Missing snapshots exist in source repository `rei-k/world-address` at the commit specified in `migration.json`. Large source blobs must be restored through a route that can read them in full; no placeholder data is allowed.*

## Current deliverables

- `priority_sources.json` records source authorities, URLs, country-specific work, unresolved reuse rights and the two-wave gate.
- `priority_audit.py` checks country scope, coverage/manifest/verification row correspondence, preserved file checksums, missing-source provenance and wave order.
- `reconcile_official.py` builds candidate-only mappings from a locally supplied official CSV, preserving GeoNames IDs and never changing source rows. It can use an independently reviewed parent crosswalk to reduce false matches.
- `test_priority_audit.py` includes offline regression cases that prohibit approving matches by identical names alone.

**No new official rows, postal codes, polygons or translations have been imported by these tools.** Source acquisition and rights clearance are separate next steps. **A successful checksum audit does not prove current official hierarchy, nationally complete addresses, postal validity or delivery success.**

## Run the audit (Python 3.11+, no additional packages)

From repository root:

```bash
python registries/africa/priority_audit.py --wave 1 --check
python registries/africa/priority_audit.py --wave 2 --check
python -m unittest discover -s registries/africa -p 'test*.py' -v
```

The output includes source status, unresolved parents, missing administrative assignments and source dates. `--check` fails on internal inconsistencies, **not** on known missing snapshots or unverified official matches.

## Official administrative comparison input

After downloading an official dataset for a priority country and checking its current release, terms and redistribution rights, normalise it *locally* into the following CSV format:

```csv
official_id,name,admin_level,parent_official_id,aliases
COUNTY-001,Example County,1,,
SUB-001,Example Subcounty,2,COUNTY-001,Example Sub-county
```

Use actual official IDs and source-vintage level definitions; rows above are **synthetic**, not a national reference list. Each country has a different legal meaning for level 1/2/3/4/5. Do not assume GeoNames ADM numbers correspond to official subdivisions by definition.

```bash
python registries/africa/reconcile_official.py \
  --country KE \
  --official-csv /path/to/licensed-kenya-official-units.csv \
  --source-url https://www.knbs.or.ke/reports/kenya-census-2019/ \
  --out /tmp/ke-official-candidates.json
```

Optional `--verified-parent-map /path/to/manual-parent-crosswalk.json` accepts official parent IDs mapped to verified `gn:` parent IDs. The map must already have human-reviewed provenance. If absent, a name-only candidate **never** receives inferred parent approval. An exact unique name is only a review candidate, never an accepted source crosswalk. The tool does not upload, redistribute or merge source data.

## Wave 1 country acceptance gates

1. **ZA:** record MDB boundary release and Stats SA geographic frame, keep wards vs municipalities separate, reconcile exact official codes and source hierarchy.
2. **NG:** restore original snapshot byte-for-byte; verify source hashes and metadata; attach independent state/FCT/LGA hierarchy. NIPOST's 2026-10-01 11-character digital postcodes are a distinct address system whose API/bulk use requires separate terms; no fabricated postal keys.
3. **KE:** compare KNBS census administration tables at their published vintage; triage all unresolved country/A1 parent assignments; do not auto-resolve to closest-named county.
4. **GH:** compare GSS census vintage for regions/districts, review 11 missing parent references and 39 localities lacking ADM1. Do not treat GhanaPostGPS as a GeoNames locality or assume permissive API/bulk rights.

Wave 1 is not complete until official data are actually captured, independently matched and quality-reviewed. Wave 2 collection starts thereafter, although its source references are catalogued now.

## Source and claim boundaries

- Keep GeoNames, statistical subdivisions, postal schemes, digital addresses and OSM road/building facts in **separate, licensed source layers**. Never sum overlapping counts.
- Pin extraction date, release/effective date, original URL, checksum, schema, licence/redistribution evidence and conversion revision.
- Administrative reform or territorial disputes may require time-versioned hierarchy. Do not silently reparent localities to a new province using name similarity or point-in-polygon alone.
- Published official lists can provide administrative evidence without proving a physical address exists. Independently tested deliveries are a separate later requirement.
- The master Africa baseline remains **56 of 60 areas, 388,038 source rows** until the missing archives and manifests are restored and verified; priority planning itself does not change that baseline.
