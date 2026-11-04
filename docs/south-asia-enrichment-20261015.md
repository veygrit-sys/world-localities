# South Asia enrichment plan (2026-10-15)

Scope: AF, BD, BT, IN, LK, MV, NP, PK (UN M49 Southern Asia). This is a planning and quality-gate document, not a claim of new verified address data.

## Priorities
1. Inventory country-specific administrative hierarchy, stable identifiers, source date, licenses, postal coverage, and existing `asia-registry` records without duplicating GeoNames IDs.
2. Add independently sourced official administrative crosswalks per country, preserving source names, language/script, effective date, original codes and provenance.
3. Normalize native-script and romanized aliases without treating transliterations as official names. Preserve Unicode, variant spelling and provenance.
4. Join postal areas only when authoritative postal datasets permit it. Model one-to-many and many-to-many relations; never infer a unique street/address from a postal code.
5. Validate Address1/Address2 and street/house number only against licensed, evidenced reference data; distinguish parsed, structurally plausible, and deliverability-verified results.
6. Stage new source snapshots as immutable artifacts with checksums, retrieval timestamps, license notes and replayable transforms.

## Country-specific risks
- IN: state/UT, district, subdistrict, village/town and PIN delivery-office relationships vary; do not conflate PIN and locality.
- PK: provinces/territories, districts/tehsils and postal areas need versioned crosswalks.
- BD: divisions, districts, upazilas, unions and postal offices have distinct levels.
- LK: provinces, districts, divisional secretariats and postal towns must remain distinct.
- NP: provinces, districts, local levels and wards need effective-date tracking.
- BT: dzongkhags, gewogs and thromdes require official code alignment.
- MV: atolls, islands and municipalities require stable island identifiers.
- AF: provincial/district data can conflict across sources and dates; mark disputed or unverifiable boundaries rather than guessing.

## Acceptance gates
- No destructive rewrite of existing IDs or country packs.
- Every added row has source identifier, attribution/license, retrieval date, and confidence/evidence status.
- Country counts and unmatched crosswalk rates reported before and after import.
- Reject duplicate canonical keys, dangling parents, invalid country assignment, and unexpected count drops.
- Regression tests cover Unicode, alternate names, ambiguous postal codes, islands, historical administrative changes, and missing address components.
- Do not claim street-level completeness or delivery verification without evidence.

## Execution order
Inventory -> source licensing review -> immutable ingestion -> crosswalk QA -> country-specific address parsing -> regression testing -> staged release. Promote each country only after all gates pass.
