# Sources and reuse

## GeoNames

Source: GeoNames, https://www.geonames.org/ and
https://download.geonames.org/export/dump/ (individual country ZIP extracts).
Data licence: Creative Commons Attribution 4.0 International,
https://creativecommons.org/licenses/by/4.0/ .
Source documentation: https://download.geonames.org/export/dump/readme.txt .

This derived extract selects administrative features and populated places,
adds qualified identifier/relationship columns and splits CSV files by country.
It preserves source codes, labels and coordinates. Attribution must be retained
when redistributing these data. GeoNames does not certify this transformation.
Exact acquisition dates and source hashes are in country metadata.

## Eurostat LAU correspondence

Source: European Commission, Eurostat, LAU 2025 – NUTS 2024 correspondence
table, https://ec.europa.eu/eurostat/web/nuts/local-administrative-units .
The workbook snapshot URL and hash are recorded in `eurostat-lau/source.json`.
Reuse policy: https://ec.europa.eu/eurostat/help/copyright-notice .
Statistical data reuse is allowed with source attribution, subject to the
source's specific third-party exceptions. This package does not contain GISCO
boundary geometries or the separate historical 1961–2011 population products.

Changes: selected identity/name/NUTS columns, preserved source validation
statuses, qualified IDs, statistical prefix nodes and country CSV packaging.
Eurostat is not responsible for this transformation or its downstream use.
No endorsement or independent validation by Eurostat is implied.

## Scope

Country/area classification reference: United Nations Statistics Division,
M49, https://unstats.un.org/unsd/methodology/m49/ .
Supplemental coverage is explicitly identified in `scope.json` and is not
represented as the UN's classification. No new border geometries are provided.

Code follows the surrounding repository's software licence. Data source terms
remain applicable independently of the software licence.
