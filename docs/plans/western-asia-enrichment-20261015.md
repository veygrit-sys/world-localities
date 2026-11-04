# Western Asia locality and address enrichment — 2026-10-15

## Scope and boundary
Use UN M49 Western Asia classification as the region membership source: Armenia AM, Azerbaijan AZ, Bahrain BH, Cyprus CY, Georgia GE, Iraq IQ, Israel IL, Jordan JO, Kuwait KW, Lebanon LB, Oman OM, Qatar QA, Saudi Arabia SA, State of Palestine PS, Syria SY, Türkiye TR, United Arab Emirates AE, Yemen YE (18 countries/areas). Iran IR is Southern Asia under M49, not Western Asia. Russia is Eastern Europe under M49; do not silently include it. Preserve territorial disputes and source-specific naming without asserting disputed sovereignty or silently overwriting identifiers.

## Implementation sequence
1. Gulf: SA, AE, QA, KW, BH, OM.
2. Levant: JO, LB, IL, PS, SY.
3. Mesopotamia and Arabian Peninsula: IQ, YE.
4. Anatolia and Caucasus: TR, AM, AZ, GE, CY.

## Country quality objectives
- Validate administrative levels and stable source codes, including municipality, district, settlement, and special jurisdictions where appropriate; never assume a uniform hierarchy.
- Preserve native script and language-tagged official and alternate names: Arabic, Hebrew, Turkish, Armenian, Georgian, Azerbaijani, Kurdish and other locally applicable languages. Preserve original orthography, diacritics and source provenance; transliteration is a searchable alias, not proof of official naming.
- Maintain postal codes as a separate, possibly missing or non-unique reference layer; do not infer deliverability or house-level precision from postal matches.
- For countries using national addressing systems, model building numbers, street names, neighborhood/district, unit, additional numbers and national address identifiers only where lawful authoritative reference data exists. Address1/Address2 mapping must be country-specific and reversible.
- Treat changing boundaries, disputed jurisdictions, and historic names as versioned claims with sources, dates, and confidence. Avoid collapsing distinct localities sharing a name.

## Source and license gates
Inventory `asia-registry` first; prefer official statistical, municipal, postal and open-government releases. Store source URL, publisher, license/terms, acquisition date, checksum, version and original code. Restrict redistribution when source terms do not permit it. Never use inferred or synthetic streets/house numbers as verified facts.

## Data quality gates
Reject duplicate canonical IDs, broken parent references, inconsistent country/region membership, unlicensed records, untraceable changes, invalid Unicode, unsupported administrative merges and unexpected row loss. Emit per-country before/after counts, source coverage, unmatched crosswalks, language coverage, postal coverage, disputed/ambiguous cases and regression results. Preserve existing `gn:` IDs and existing country packs.

## Test scenarios
Arabic/Hebrew right-to-left input and mixed-script rendering; Arabic diacritics and hamza variants; Turkish dotted/dotless I; Georgian and Armenian Unicode; identical locality names in different districts; postal codes absent/ambiguous; bilingual address formatting; PO boxes; building and unit numbering; historical renamings; cross-border and disputed area records; partial addresses.

## Execution loop
Inventory -> authoritative source/license review -> immutable snapshots -> deterministic import -> ID crosswalk -> native-name and postal tests -> address template validation -> quality report -> staged release. Continue with next country only after checks pass. This document is a plan, not an import or verified coverage claim.
