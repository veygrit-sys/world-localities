# CSV schema, version 1

Encoding is UTF-8; all values are strings. Empty fields indicate missing or
unasserted values, not zero. JSON columns contain JSON arrays.

| Added column | Meaning |
|---|---|
| `id` | `gn:` plus the original GeoNames ID |
| `kind` | `admin_subdivision`, `locality`, or `other_admin_feature` |
| `admin_level` | Current ADM level 1–5, otherwise empty; not a legal municipality classification |
| `parent_id` | Unambiguous direct source administrative parent, country scope, or empty |
| `parent_relation` | Evidence or reason the parent could not be asserted |
| `parent_candidates_json` | ID candidates found for the exact parent administrative-code prefix |
| `state_id` | Independently resolved ADM1 ID, self for ADM1, or empty |
| `state_relation` | Evidence or reason ADM1 could not be asserted |
| `state_candidates_json` | ID candidates found for the exact ADM1 code |
| `address_candidate` | `1` for selected current populated-place classes, otherwise `0` |
| `quality_flags_json` | Source limitations, missing relationships and candidate exclusions |

The original 19 columns follow unchanged in order:

`geonameid, name, asciiname, alternatenames, latitude, longitude, feature_class,
feature_code, country_code, cc2, admin1_code, admin2_code, admin3_code, admin4_code,
population, elevation, dem, timezone, modification_date`.

Original field definitions and feature codes:
https://download.geonames.org/export/dump/readme.txt
https://www.geonames.org/export/codes.html

Selection: all feature-class P records, and class A with feature code ADM1–ADM5,
ADM1H–ADM5H or ADMD. Current ADM5 has no dedicated admin5 code in the standard
dump. Historical and abandoned features are preserved for search/history and are
not assigned current administrative parents.

`parent_relation` values include `source_country`, `source_admin_code`,
`country_scope_only`, `missing_code`, `missing_reference`, `ambiguous_code`,
`historical_parent_not_asserted`, `not_assigned_for_other_feature`.
`state_relation` also includes `self_is_adm1` and `not_applicable`.

The gazetteer schema and presentation engine input schema are separate.
To use gazetteer entities in the presentation engine, explicitly map `country_code`
to `country` and build `ancestor_ids` from accepted, reviewed parent relations.
Do not infer `municipality_id` from every locality or every ADM level.
Name rows require identified language, usage, source and status; do not import
unlabelled aliases as English/local official names.
