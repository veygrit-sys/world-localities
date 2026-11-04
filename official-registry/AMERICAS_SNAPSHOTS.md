# Americas: preserved country locality snapshots

This batch contains the completed **US, CA, MX and BR country snapshots** from
[rei-k/world-address at commit 4efec82671b15a6bca4f0099acb6377c55af9aae](https://github.com/rei-k/world-address/tree/4efec82671b15a6bca4f0099acb6377c55af9aae/address-foundation/official-registry).
It is **not complete North America or South America coverage**. No new upstream
collection, Address1, street/premise data, postal assignments, or delivery
verification is included. Official-source geography is not proof of current
legal status or a count of unique municipal governments.

## Included snapshots

| Country | Locality rows | Region shards | Preserved source scope |
|---|---:|---:|---|
| [US](US/index.json) | 68,744 | 52 | 2026 Census Gazetteer: 32,363 places and 36,381 county subdivisions, covering 50 states, DC and Puerto Rico; other Island Areas excluded |
| [CA](CA/index.json) | 5,054 | 13 | Statistics Canada 2025 census subdivisions under 290 census divisions; reference date 2025-01-01, released 2025-06-18 |
| [MX](MX/index.json) | 2,478 | 32 | INEGI July 2025 AGEM catalogue: 2,462 municipality areas and 16 Mexico City territorial demarcations |
| [BR](BR/index.json) | 5,571 | 27 | IBGE municipality endpoint: 5,569 municipalities, Brasília and Fernando de Noronha; live source supplies no reference date |

The batch totals 81,847 locality roles plus 3,640 hierarchy anchors. Its 140
country files are byte-identical to the pinned source. The original `vintage`,
`observed_at`, source timestamps, URLs and SHA-256 values remain unchanged.
Observation time is not a legal effective date. Copying a snapshot does not
establish current freshness.

The checked [Canada refresh job on 2026-09-30](https://github.com/rei-k/world-address/actions/runs/36766121286/job/110060611428)
failed with HTTP 500 during source download at 19:32:25 UTC. Its publish step
was skipped. This preserved Canada snapshot remains readable and validated;
it is not presented as a successful fresh update. This is a dated observation,
not a claim about all future workflow runs.

## Read the data

Start with each country's `index.json`; it lists the region CSV filenames,
column order, counts and source limitations. `anchors.csv` supplies country,
region and any county/census-division parents. Join `id` to `parent_id` within
the same country. Every locality also retains its region's `state_id` and
`state_code`. All parent chains close within these CSV files.

Use UTF-8 and keep every CSV value as a string, especially identifiers with
leading zeros. [The schema guide](americas-snapshot-schema.json) documents the
preserved columns and country extensions. This is the source snapshot format;
it does not change or claim compatibility with existing JP/TW query/build
contracts. No JP/TW loader, schema, or snapshot is replaced by this batch.

- US places and county subdivisions are distinct, sometimes overlapping roles.
  Places attach directly to states; no single county is invented. All 4,830
  fictitious Census roles remain present and excluded from address candidates.
  Puerto Rico retains `address_country=PR` within the US source view
- Canadian census subdivisions include municipalities and statistical
  equivalents. Retain `CSDTYPE`, exact code ancestry, Indigenous and
  unorganized/statistical categories, and `lang=und` when language is unknown
- Mexican municipal-seat codes/names are attributes, not municipality aliases.
  Separate 2020 census statistics do not date the July 2025 catalogue
- Brazilian federal/state-district equivalents remain separately typed;
  Portuguese names and seven-character IBGE codes are preserved
- Empty postcode fields mean no associations loaded. `address_candidate` is
  a selection flag, never proof of postal deliverability

## Provenance and licences

The combined country snapshots retain **ODbL-1.0**, because their identifiers
and anchors derive from the existing CSC/world registry. This does not replace
the separate government-source conditions or make the data MIT.

Keep [DATA_LICENSES.md](americas-provenance/DATA_LICENSES.md), the unchanged
[admin notices](americas-provenance/third_party/admin/), and the original country
manifests with the data. The notices include the full
[CSC ODbL text](americas-provenance/third_party/admin/CSC-ODbL.txt), ISO-reference,
Unicode and CommerceGuys notices at their original relative paths. The
[program-code licence](americas-provenance/LICENSE) does not license the data.

Attribution: U.S. Census Bureau, 2026 Gazetteer Files; INEGI, Catálogo Único de
Claves de Áreas Geoestadísticas, corte julio 2025, datos transformados por Address
Foundation; IBGE, API de localidades, observed 2026-09-26. Adapted from Statistics
Canada, 2025 Census Subdivision Boundary File, reference date January 1, 2025.
This does not constitute an endorsement by Statistics Canada of this product.
No government or upstream-provider endorsement is implied.

[source-map.json](americas-provenance/source-map.json) records every preserved
source path, destination path, Git blob SHA-1, SHA-256, byte length and immutable
source URL. The 11 supporting provenance files include the original four
world-registry country records and the original registry manifest. Only those
four country records are bundled; the historical manifest and full notice
describe a broader source repository, not additional coverage in this batch.
Raw government input archives and the complete upstream database/search build
are not included; their source URLs/hashes and pinned source repository remain
available in the original manifests and mapping.

## Offline verification

From the repository root, with Python 3.9+ and no extra packages or network:

```sh
python scripts/verify_americas_snapshots.py
python -m unittest discover -s tests -p test_americas_snapshots.py -v
```

Checks cover all 151 preserved files' bytes and Git/SHA-256 hashes, original
manifest hashes, CSV schemas, region and category counts, unique IDs, resolved
acyclic ancestry, source-code identities, address flags, empty postal fields,
and original world-anchor hashes. All four regression tests pass, including
corruption, incorrect-parent and unsupported-completeness-claim rejection.
The [verification report](americas-provenance/verification.json) records the
result. Upstream raw-source rebuilds, SQLite/FTS search tests and current-source
freshness checks were not run for this snapshot-only transfer.
