# Attribution and reuse

The gazetteer rows are derived from **GeoNames**, https://www.geonames.org/,
downloaded from https://download.geonames.org/export/dump/ on 2026-09-26.
GeoNames data is licensed under **Creative Commons Attribution 4.0 International**:
https://creativecommons.org/licenses/by/4.0/ . Commercial use is allowed with attribution.

Changes made here: select all feature classes A and P for the 60 country/area
files in scope; preserve their original 19 text fields; add namespaced IDs,
type classifications, code-based parent references, quality flags and compressed
CSV exports. GeoNames does not endorse this derivative.

The country/area scope and English country names follow the United Nations
Statistics Division M49 geographic grouping:
https://unstats.un.org/unsd/methodology/m49/ . These are statistical groupings,
not new territorial or sovereignty determinations. Country/area codes are
cross-referenced with GeoNames countryInfo.txt; source labels and classifications
are retained separately. No boundary polygons are included or changed.

The source is not a complete, independently verified register of municipal
governments. Coordinates are source reference points, not entrances or boundaries.
No postal deliverability, population freshness, or current legal status is certified.

Python code follows the parent address-foundation project's MIT license.
The data remains subject to its own attribution requirements. It has not been
relicensed as MIT and has not been merged with the existing CSC/ODbL catalogue.
