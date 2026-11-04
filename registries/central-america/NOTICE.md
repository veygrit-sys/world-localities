# Licenses and source attribution

## GeoNames data

© GeoNames and contributors, https://www.geonames.org/.
Country gazetteer dumps and country alternate-name dumps were retrieved on
2026-10-01 from https://download.geonames.org/export/dump/ and
https://download.geonames.org/export/dump/alternatenames/.
They are licensed under [Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/).
The source readme is preserved at `sources/readme.txt`; it disclaims accuracy,
timeliness and completeness. This package and its transformations are not endorsed
by GeoNames. Preserve attribution, source URLs, source IDs and this license notice
when redistributing these data or extracts.

Changes: select all A/P features from six country extracts; retain all original
19 columns; add stable `gn:` identifiers, exact full-code administrative links,
unresolved-parent flags and an address-candidate filter; extract language-tagged
labels and `post` evidence only for exact retained IDs; map source country IDs to
explicit `country:<CC>` label roots; deterministic gzip encoding. Historical
features remain distinguishable. No fuzzy name matching or inferred translations
are used. Source ZIPs and checksums are included for reproducibility.

## Factual statistical grouping and administrative count checks

Country scope follows [United Nations Statistics Division M49](https://unstats.un.org/unsd/methodology/m49/),
Central America (013), checked 2026-10-01. This statistical grouping is not a
sovereignty or boundary determination. Only country names, identifiers and grouping
facts are reproduced.

`source_freshness.json` cites dated official references from
El Salvador's Legislative Assembly for factual administrative counts. Those
publications are linked as verification evidence; their text, tables, maps and
PDFs are not redistributed or relicensed as GeoNames data.

## Software

Original scripts and documentation: MIT, see `LICENSE`.
Core entity fields, parent resolution, deterministic gzip and eight safety tests
adapt the existing Africa registry at
[world-address commit 4efec826](https://github.com/rei-k/world-address/tree/4efec82671b15a6bca4f0099acb6377c55af9aae/address-foundation/africa-registry).
Scope, locale layer, raw-source replay, freshness checks and documentation were
adapted/added for this region. The MIT software license does not supersede data
licenses.

Partial-publication change: country CR source and derived data are excluded.
The shared countryInfo metadata copy omits its CR row, with original and derived
checksums recorded in sources.json. UN M49 membership names remain solely to
describe the explicit six-of-eight coverage and exclusions.
