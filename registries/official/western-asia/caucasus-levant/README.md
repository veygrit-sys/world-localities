# Armenia / Georgia / Azerbaijan / Israel / Jordan: official-evidence joins

This page describes the 2026-11-05 manual-reference snapshot. Current original-data imports and remaining gates are in [the source import layer](../imports/README.md); its manifest supersedes historical zero-import statements for overall project status.

2026-11-05. This module extends world-localities to a further five countries. It
reuses **verified SHA-256 archived GeoNames snapshots** without modifying any
existing IDs. The official administrative labels and postcodes are sourced from
public postal operators and official government/statistics pages. Names are
review **candidates**, never legal identity assertions.

## Data included

| Country | Official admin reference labels | Published code samples | Postal-code scheme |
|---|---:|---:|---|
| AM | 11 (Government of Armenia; 10 marzes + Yerevan) | 14 | 4 ASCII digits incl. leading zeros |
| GE | 12 (Geostat reporting regions) | 3 | 4 ASCII digits incl. leading zeros |
| AZ | 2 (operator geographic labels only; not full official rayon register) | 24 | AZ + 4 ASCII digits |
| IL | 6 (CBS statistical districts) | 2 | 7 ASCII digits |
| JO | 12 (Ministry of Interior governorates) | 3 | 5 ASCII digits |

Sources are documented record by record in [source_evidence.json](source_evidence.json).
**Original nationwide official postal datasets imported: 0.** Examples or postal
office branches are not substitutes for national postcode tables or certified
code-to-location mapping. Source HTML/PDF original bytes and extraction SHA256
are not stored; use/republication terms for complete datasets remain pending.

### National differences

- Armenia: HayPost office/postcode pairs for Yerevan and published 0601 Vedi
  example; 0001/0002 are distinct offices and do not imply one city postcode.
- Georgia: 0100, 0160 and 0180 are published address examples in Tbilisi, not
  a complete building-level code directory. Tbilisi regional label is distinct
  from the post office / recipient address.
- Azerbaijan: Nakhchivan Post branch codes are explicitly office-level.
  \`AZ7001\` identifies a branch, not all addresses in Nakhchivan; \`AZ7211\`
  Bənəniyar is preserved with source Azerbaijani lettering. Do not equate a
  4-digit numeric key from another country with an Azerbaijani postcode.
- Israel: CBS officially reports **six** districts. GeoNames has **seven** ADM1
  records including a separately classified Judea and Samaria Area; never
  silently promote it to a seventh CBS district. Hebrew, Arabic and English
  fields are independent. The 7-digit postcode can be building-specific.
  No source-to-territory reclassification is performed.
- Jordan: 12 MOI governorates. The 2004 UPU examples for 11937/11190 are
  explicitly **historical**, while MOI's 11118 is a ministry contact address.
  None of these three samples prove all of Amman's postal zones.

## Run

    python scripts/western_asia_caucasus_levant_join.py report --country all \
      --output /tmp/am-ge-az-il-jo.json
    python scripts/western_asia_caucasus_levant_join.py postcode --country AZ --code az1000
    python scripts/western_asia_caucasus_levant_join.py find-code --country AM --code 0002
    python -m unittest tests.test_western_asia_caucasus_levant_join -v

Reports give government name candidates / ambiguities / unmatched counts,
published code samples, code-to-place GN candidates, and incomplete ADM1 links.
**No record is auto-promoted** to authenticated administrative identity, postal
assignment, entrance accuracy, or carrier deliverability.

## Next stage

1. Acquire licence-approved official source bytes with source date and SHA256
   for the full HayPost branch table, Georgian Post postal lookup, Azərpoçt
   operator directory, Israel Post address/house-level directory, Jordan Post.
2. Create an official administrative-key crosswalk using original administrative
   IDs, boundary versions and provenance, reviewed independently of string
   matches; no arbitrary ISO↔GeoNames code assumption.
3. For fully official code-to-locality associations, store multi-valued,
   country-specific postal relation tables with a reviewed grain and
   separate expiration/freshness fields. Introduce carrier-specific service
   acceptance checks only when an authorized carrier interface exists.

The four-country first wave and five-country Gulf/Palestine wave are unchanged.
