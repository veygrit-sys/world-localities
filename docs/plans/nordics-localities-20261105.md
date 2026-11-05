# Veygrit — Nordic localities / address source implementation (2026-11-05)

## Scope and completion criterion

The Nordic countries are **Denmark, Finland, Iceland, Norway and Sweden**. This package adds associated Åland, Faroe Islands, Greenland, and Svalbard/Jan Mayen as independently tracked regional / postal codes. It does not redefine Greenland as geographically European, or treat Svalbard and Jan Mayen as sovereign states. The Baltics and UK/IE remain in their existing country projects.

A source-verified gazetteer or import pipeline is not a nationally certified address-existence registry. Address completion needs legal reuse rights, a fixed recent source snapshot, checked administrative/road/house-number/postcode relationships, independently evaluated current-address cases, and verified carrier conversion/deliverability testing.

## Current code / existing sources

| Code | Existing registry | Official address source / constraint | Stage in this contribution |
|---|---|---|---|
| DK | GeoNames; Eurostat LAU | Datafordeler DAR (registered API key / OAuth); DAWA retired 2026-10-01 | pinned ingest adapter ready; no new national data |
| FI | GeoNames; Eurostat LAU | Finnish Ryhti open_address.csv.gz updated daily, CC-BY-4.0; completed building addresses only | pinned CSV.gz import ready; no new national data |
| IS | GeoNames | HMS Staðfangaskrá public weekly UTF-8 CSV, includes address numbers, lat/lon and point quality fields | pinned CSV import ready; no new national data |
| NO | GeoNames; Eurostat LAU | Kartverket Geonorge Matrikkelen-Adresse WFS / national downloads (CC BY 4.0). REST address search has 10k cap | pinned export ingest ready; no new national data |
| SE | GeoNames; Eurostat LAU; previous SCB 21 counties/290 municipalities in separate module | Lantmäteriet official address points require legal review | reuse existing indexes; approved import only |
| AX | GeoNames | Finnish NLS Geographical Names; Åland postcodes need separate provenance | place baseline, address unknown |
| FO | GeoNames | Umhvørvisstovan official address map services, daily data extract; rights review | place baseline, address unknown |
| GL | Five previous municipality-name seeds only | NunaGIS national address WFS / ArcGIS, source rights/actual downloads still unverified | five seeds; no complete locality list |
| SJ | GeoNames (small number of places) | Posten Svalbard postal codes; special shipping/customs rules; Jan Mayen needs independent evaluation | limited gazetteer, no delivery assertion |

## Source URLs (authority-owned)

- DK: https://datafordeler.dk/dataoversigt/danmarks-adresseregister-dar/dar-fildownload/ and https://www.klimadatastyrelsen.dk/om-klimadatastyrelsen/nyheder/nyhedsarkiv/2026/jul/dawa-lukker-d-1-oktober-2026
- FI: https://ryhti.syke.fi/en/front-page/services/ and https://www.maanmittauslaitos.fi/en/maps-and-spatial-data/datasets-and-interfaces/product-descriptions/geographic-names
- IS: https://hms.is/gogn-og-maelabord/grunngogntilnidurhals/stadfangaskra (official weekly CSV)
- NO: https://www.kartverket.no/api-og-data/eiendomsdata/apent-tilgjengelige-data-og-tjenester and https://data.norge.no/en/datasets/8f1151bf-ad63-3e47-adbb-143f876776ee/matrikkelen-adresse
- SE: https://geotorget.lantmateriet.se/geodataprodukter?filter=belagenhetsadress-nedladdning-vektor
- AX: https://www.maanmittauslaitos.fi/en/maps-and-spatial-data/datasets-and-interfaces/product-descriptions/geographic-names
- FO: https://www.us.fo/kort/adressuskra/
- GL: https://nunagis.gl/en/web-services/
- SJ: https://www.posten.no/en/sending/domestic/svalbard

## Non-negotiable checks

1. Preserve input bytes, SHA-256, timestamp, authority/URL/license, source-specific identifier and language. Keep leading zeros in postal numbers, house strings and municipality codes.
2. Model GeoNames, national official data, Eurostat LAU and postal-carrier data as **separate** evidence; do not join same names or nearby coordinates into a claimed identical address.
3. Reject cross-country rows, duplicate source IDs, unknown CRS, unsafe ZIP paths, changes to file hash and unverifiable source schemas.
4. `postcode` only checks shape. Actual postal existence and delivery are unknown unless independently checked.
5. For FI preserve Finnish/Swedish/Sámi names and declared language; for SE no Latin ASCII alias is 'English' by default; for FO/GL record Faroese/Kalaallisut as source labels, not auto-translated names.
6. Do not call source-record presence 'commercially useable' unless access and downstream reuse rights are reviewed. Do not copy unreviewed address/person attributes into generated output.
7. Greenland has only five municipality-name seeds today; a Nordic coverage metric aggregating country-code observations is **not** percentage coverage.

## External dependencies still needed to assert national completion

- DK: service registration + approved DAR snapshot and field-by-field schema verification.
- FI: retrieve Ryhti national CSV snapshot, SHA pin, map actual exported field names and independently assess missing building addresses.
- IS: retrieve weekly HMS source file, hash/identity check; normalize `HEINUM`/`HNITNUM` without collapsing multiple address coordinates.
- NO: download a complete Geonorge file snapshot instead of misusing the capped search endpoint; verify historical/matrikkeladress variants.
- SE: Lantmäteriet legal review and authorized national address-point export.
- AX/FO/GL: verify official rights and obtain national extracts, with independent country-code/address rules.
- SJ: evaluate populated places, carrier delivery routes and customs processes separately; no invented Jan Mayen street addresses.

## Evaluation exit criteria

- All official-file counts and IDs replay exactly from fixed and licensed snapshots.
- Independently collected, non-training address samples for each region produce precision / false-accept / hold and classification metrics.
- Currentness and administrative hierarchy have dated independent comparison; carrier-specific shipping formats are verified.
- There is no claim of worldwide or nationwide last-mile delivery without carrier evidence.
