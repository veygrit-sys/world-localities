# Central Asia enrichment plan — 2026-10-15

## Scope
UN M49 Central Asia: Kazakhstan (KZ), Kyrgyzstan (KG), Tajikistan (TJ), Turkmenistan (TM), Uzbekistan (UZ). Afghanistan is covered by the separate South Asia plan. Mongolia belongs to Eastern Asia under M49. Preserve any cross-region aliases without duplicating stable IDs.

## Objectives
Enhance existing asia-registry data using reproducible, legally reusable authoritative administrative and postal sources. Do not claim any new dataset, completeness or deliverability verification until imported and tested.

## Country-specific research and acceptance
- KZ: oblasts, cities of republican significance, districts, rural settlements; Kazakh Cyrillic/Latin and Russian variants, historic renamings, postal code relationships.
- KG: oblasts, Bishkek/Osh, raions and local settlements; Kyrgyz/Russian spellings and administrative changes.
- TJ: regions, districts and jamoats; Tajik Cyrillic, Russian variants, Gorno-Badakhshan hierarchy and ambiguous locality names.
- TM: welaýat, etrap, cities and settlements; Turkmen Latin/Cyrillic legacy aliases, source restrictions and postal coverage gaps.
- UZ: regions, Karakalpakstan, Tashkent city, districts and mahallas; Uzbek Latin/Cyrillic and Russian aliases, versioned administrative crosswalks.

## Data contract
Each canonical row must preserve country ISO code, source-specific identifier, stable internal locality ID, parent ID, administrative level/type, native-script official name, optional language-tagged aliases, effective date, source URL, retrieval timestamp, license/attribution and verification status. Unknowns remain null. Postal areas and delivery offices are separate many-to-many layers; no assumption that postal codes uniquely determine Address1 or Address2. Streets, house numbers, buildings and apartments are separate evidence-graded layers.

## Pipeline
1. Inventory existing country packs and identify gaps, duplicates, orphan parents, historical aliases and source-license constraints.
2. Capture immutable official reference snapshots, checksums and source receipts; do not overwrite raw originals.
3. Construct versioned crosswalks; flag ambiguous mappings for review, never silently match by name alone.
4. Implement Unicode normalization and reversible, language-aware alias search; retain native originals and avoid lossy transliteration as canonical data.
5. Introduce country-specific address field templates and parser fixtures. Distinguish syntactic validity, reference match and delivery verification.
6. Run offline regression tests and emit before/after coverage and unresolved-issue reports; publish only validated country increments.

## Quality gates
Reject duplicate canonical IDs, dangling parents, country mismatches, unlicensed data, missing provenance, invalid UTF-8, non-reproducible transformations, unexpected count decreases, and unsupported claims of postal or street-level completeness. Test script variants, renamings, border/administrative exceptions, rural localities, postal ambiguity and incomplete addresses. Preserve backward compatibility with existing `asia-registry` country packs and `gn:` identifiers.

## Execution order
KZ -> UZ -> KG -> TJ -> TM, revisiting low-confidence mappings after each cycle. This document defines the process; no country data was imported in this commit.
