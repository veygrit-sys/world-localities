# Column meanings

All identifiers and codes are strings. Empty strings mean an absent or
unresolved value; they never mean numeric zero. CSV is UTF-8.

## GeoNames country parts

| Column | Meaning |
|---|---|
| `id` | `gn:` plus the unchanged GeoNames integer ID |
| `kind` | `admin_subdivision`, `locality`, or `other_admin_feature` |
| `admin_level` | Source ADM1–ADM5 level, otherwise empty |
| `parent_id` | Uniquely resolved administrative parent, country scope, or empty |
| `parent_relation` | Evidence or reason the immediate source relationship is unresolved |
| `parent_candidates_json` | All exact administrative code matches, including ambiguous ones |
| `state_id` | Separately resolved source ADM1; this is not necessarily a state |
| `state_relation`, `state_candidates_json` | Evidence and all ADM1 code matches |
| `address_candidate` | `1` for selected current place feature types, not deliverability |
| `quality_flags_json` | JSON array of source and relationship limitations |
| Source columns below | Unmodified strings from the source country extract |

The 19 source columns are `geonameid`, `name`, `asciiname`, `alternatenames`,
`latitude`, `longitude`, `feature_class`, `feature_code`, `country_code`, `cc2`,
`admin1_code`, `admin2_code`, `admin3_code`, `admin4_code`, `population`,
`elevation`, `dem`, `timezone`, `modification_date`.

Coordinates are WGS84 representative points, not parcel boundaries or delivery
entrances. `modification_date` is a source record edit date, not the legal date
of a municipal reorganisation. Administrative codes are GeoNames codes, not
guaranteed ISO 3166-2 or national government codes. Untagged alternate names
must not be relabelled as verified native-language/English translations.

Parent resolution uses every code in the corresponding country/ADM path.
Missing levels are not skipped. `country_scope_only` indicates scope only,
not a direct municipal relationship. ADM1 rows may refer to themselves only
in `state_id`, never in `parent_id`. Historical rows have no asserted current
parent. `entities-*.csv.gz` parts are disjoint; `admin1.csv` is a duplicate
view and must not be added to entity totals.

## Eurostat

`eurostat-lau/CC/units.csv.gz` is a separate source namespace. Its `id` is
`eurostat:lau:2025:<EU LAU CODE>`. `lau_code` is the suffix of the source EU
LAU code; `source_lau_code` retains the separate workbook cell, including
cases where a numeric cell omits leading zeros. `source_period` is the
workbook PERIOD value and is not silently changed to 2025.

`name_national` and `name_latin` are the source labels. A Latin label is not
a guaranteed English translation. `statistical_parent_id` references a
NUTS/statistical region code, not an administrative parent. The separate
`statistical_regions.csv` contains prefix-based code nodes with no invented
names or government status. No GeoNames `state_id` is manufactured from NUTS.

`source_sheet`, `source_row`, `source_country`, `source_validation` and
`quality_flags_json` preserve scope and review limitations. `country` is a
source hierarchy view: French overseas LAUs remain under the source FR
sheet and Åland LAUs under FI, without changing postal-country identities.
The list release label is 2025, the NUTS classification is 2024 and the source
row PERIOD may be 2024. Those three values have different meanings.
