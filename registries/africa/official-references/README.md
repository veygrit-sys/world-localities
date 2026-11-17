# Africa priority official-source reference additions (2026-11-06)

These are separate source layers, not modifications to the original
GeoNames A/P hierarchy. An administrative record is not necessarily
a valid postal address.

## Rwanda: NISR village hierarchy (2022)

Source: https://gis-server.statistics.gov.rw/server/rest/services/Hosted/Village_Boundary_2022/FeatureServer/3

14,823 village IDs and names, grouped under 2,148 cells, 416 sectors,
30 districts and 5 provinces. RW-NISR-2022-villages.csv preserves
government IDs/names but neither personal addresses nor polygons.
NISR general reuse terms permit CC BY 4.0 with attribution, subject
to any special licensing in the asset:
https://statistics.gov.rw/terms-use .

## Morocco: HCP RGPH 2024 communes

Source: https://github.com/machinemirror/morocco-census
Pinned commit: 3ac55931b4758394efefa86318da1a9e740b8f29
Original upstream Git blob SHA: bd12edfdb732fb534e7fcfb2564795909c70b256

MA-HCP-2024-communes.csv has 1,503 commune codes, French/Arabic names
and associated province names. It does not include verified official
province parent codes or postal codes. HCP census material was
harmonized by the third-party source and is not HCP-endorsed.
Derived source data are CC BY 4.0:
https://github.com/machinemirror/morocco-census/blob/main/LICENSE-DATA .
Credit HCP (RGPH 2024) and Lehnert, M. R. (2026), morocco-census,
https://doi.org/10.5281/zenodo.22953567 .
HCP's original regional categories are retained without assertions
about disputed territorial status or sovereignty.

## Algeria: 69 wilayas, 1,541 communes for 2026

Legal reference: Law 26-06 dated 2026-04-04, Official Journal 25,
published 2026-04-05; and Presidential Decree 26-206 of 2026-05-25
(Official Journal 40, codes 59-69).

MIT-licensed transcription source: https://github.com/islam-re/Algeria-wilayas
Pinned commit: bfb29814117d11a6a101fa07c38911f6675b748b
Original bilingual JSON Git blob SHA: 1aba9bc954bf43328ca54081f0448f613b72604e

DZ-2026-wilayas.csv: 69 numbered wilayas.
DZ-2026-communes.csv: 1,541 commune/wilaya name pairs in Arabic
and Latin-script transcription. Commune row order is not a
government-issued commune code. No missing official code was created.
Practical government/transport implementation dates may differ from
the legal effective date. Do not treat outdated 2012/2017 boundaries
as 2026 law.

## Egypt: CAPMAS-origin ADM2 (2020)

Source: https://www.geoboundaries.org/api/current/gbOpen/EGY/ADM2/
2020 OCHA/CAPMAS-origin 365-unit reference, CC BY 3.0 IGO.
Original source shape IDs are retained in
EG-CAPMAS-OCHA-2020-ADM2.csv. Source and derived SHA-256 values
are documented in EG-CAPMAS-OCHA-2020-ADM2.source.json.
Not certified as a current government parent code system.

## Boundaries and license separation

These tables are separate from GeoNames, postal provider records,
private address data, and any ODbL/OpenStreetMap derivatives.
Do not add overlapping layer counts or call them unique addresses.
Postal code shape checks cannot establish a building's existence,
legal administrative assignment or delivery success.
