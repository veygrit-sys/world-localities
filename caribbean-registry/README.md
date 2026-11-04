# Caribbean locality and administrative gazetteer: partial 27-area publication

27 of the 28 countries and areas in the UN M49 Caribbean grouping, using GeoNames country extracts acquired on 2026-10-01. Cuba (CU) is omitted in full while its country upload is pending approval. This is a source-preserving gazetteer baseline, not a certified register of every current municipality.

- 50,581 entities: 18,256 administrative subdivisions, 31,942 populated-place features, 383 other administrative/country features
- 31,630 source settlement features included in the default address-candidate filter; this does not certify postal deliverability
- 55,255 source-linked alternate-name and reference records; non-language tags such as links, Wikidata IDs, UN/LOCODE and postal codes remain distinguishable
- 196 direct GeoNames ID postal observations, supplied separately as a projection; they are not postal-authority verification
- 764 unresolved parent references and 2,544 country-only locality references remain explicit
- No Address1, street, building, personal-address or polygon data

## Scope and overlap

The 27 included M49 Caribbean areas are listed in `scope.json`; the same file explicitly records Cuba as omitted: AG, AI, AW, BB, BL, BQ, BS, CW, DM, DO, GD, GP, HT, JM, KN, KY, LC, MF, MQ, MS, PR, SX, TC, TT, VC, VG, VI.

Bermuda is in M49 Northern America and is not in this scope. Puerto Rico and the US Virgin Islands are separate source-country scopes here. Puerto Rico's existing US official municipality snapshot is a separate layer: do not sum overlapping layers or infer links by name. GeoNames administrative levels are source levels, not an assertion that all rows are municipalities. For example, the Dominican Republic source has many lower-level administrative features.

## Files and use

Each `countries/CC/` is an independently usable batch:

- `entities.csv.gz`: complete A/P rows for that acquired country source, with all 19 original text fields, stable `gn:<geonameid>` IDs, and derived parent/state references
- `metadata.json`: source URLs and archive SHA-256, coverage counts, labels, postal limits, and payload SHA-256
- `admin1.csv`: duplicate display projection, not additional entities
- `alternate-names.csv.gz`: original ten alternateNamesV2 fields and stable `gn-alt:<alternateNameId>` IDs, linked only to retained entity IDs
- `postal-links.csv.gz`, when nonempty: duplicate projection of alternate records tagged `post`, not additional alias records

Python 3.11 or later, standard library only:

    python build.py verify
    python query.py --country AG --level 1
    python query.py --country HT --text Jacmel --limit 10
    python -m unittest discover -s . -p 'test_caribbean.py' -v

Country-only verification is supported with `python build.py verify --country AG`.
To reproduce, acquire the original version of each source URL identified by its archive hash in country metadata, save country gazetteers as `CC.zip` and alternate archives as `CC-alternates.zip`, plus the M49 page as `m49.html` and GeoNames `countryInfo.txt`, then run:

    python build.py build --inputs /path/to/source-files

Upstream URLs are rolling extracts. A later download may differ; current sources do not guarantee byte-identical reproduction of an earlier date. The shipped entity and alternate records retain the original source fields needed for offline transformation replay. Local source archives were checked against all shipped retained rows; see `source-verification.json`.

## Parent and naming rules

Parents resolve only when a complete source administrative-code tuple matches exactly one current source ADM feature at the required level. Missing, ambiguous, gapped and absent references are not repaired by name or proximity. `state_id` may resolve independently while a lower-level parent remains missing. Country-only references are membership, not a claimed administrative relationship.

Source `name` and `asciiname` have no language tag. ASCII is not English. Language-tagged alternatives are preserved as attested observations, including preferred, short, colloquial, historic and temporal flags. Empty language remains undetermined. There are 1,296 entities with at least one attested English-tagged alternative; full native-language and English coverage is not achieved. `countryInfo.txt` language codes identify a source language reference only, not independently verified official or native-language status. No labels were invented or machine-translated.

Postal observations use only the source's explicit `post` tag and exact entity ID. No postal code is inferred from municipality names, coordinates or a parent. These limited links do not establish the complete postal system, current validity or delivery service.

## Verification and limits

Country and aggregate validation covers payload hashes, counts, unique identities, source country, exact code-based parent references, no dangling resolved links or cycles, alternate foreign keys, explicit postal projections, and exact replay of entity transformations. Regression tests cover unsafe parent assignment and language provenance.

This validates packaging, not the accuracy, freshness, legal status, completeness or deliverability of upstream records. Feature and modification dates are retained unchanged. Country-only or missing ADM1 information is not evidence that a territory legally has no divisions. Cross-repository and cross-region source IDs may overlap; do not blindly sum them.

Data: GeoNames, CC BY 4.0. Code: MIT. See `NOTICE.md`, `schema.json`, and `alternate-names-schema.json`.

## Reconstructing the published large file

The publication stores the Dominican Republic `countries/DO/entities.csv.gz` as two binary parts under `.parts/DO/` to keep upload requests bounded. The original compressed file is intentionally absent until materialized. This is a transport-only change: no entity, language, source hash or country metadata has changed.

Before the full validator, or before querying DO, run from the repository root:

    python -m localities materialize --registry caribbean --country DO
    python caribbean-registry/build.py verify
    python caribbean-registry/test_caribbean.py -v
    python -m unittest discover -s tests -p 'test_split_materialization.py' -v

`split_manifest.json` records the original relative path, full byte count and SHA-256, and each ordered part's path, byte count and SHA-256. The shared `localities.materialize` implementation uses only local files, verifies the parts and reconstructed output, and recreates the canonical gzip bytes exactly. It rejects unsafe/traversal paths, symlink paths, corrupt parts and a mismatched existing destination rather than overwriting it. Repeating the command with an already matching destination is safe. Other countries need no reconstruction. The compressed original must not be counted or uploaded in addition to its transport parts.

The partial publication-only clean-copy reconstruction, all 27 country replays and 13 regressions with the partial-scope assertion were tested; see `publication-verification.json`.
