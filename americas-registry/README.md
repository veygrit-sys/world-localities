# Americas: region-by-region enrichment and audit loop

This is a **logical Americas (UN M49 019) integration layer**. It does not
move or duplicate large existing locality datasets, rewrite source identities,
or change third-party licences.

## Strict area order

| Order | Area | UN M49 | Countries/areas with a locality source | Missing sources in current publication |
|---|---|---|---:|---|
| 1 | [Northern America](../north-america-registry/README.md) | 021 | 2 / 5 (US, CA) | BM, GL, PM |
| 2 | [Central America](../central-america-registry/ENRICHMENT_20261015.md) | 013 | 8 / 8: six preserved GeoNames packs + Costa Rica supplement + separate INEGI Mexico | None for source country layers |
| 3 | [Caribbean](../caribbean-registry/README.md) | 029 | 27 / 28 | CU |
| 4 | [South America](../south-america-registry/README.md) | 005 | 16 / 16 GeoNames country-area source packs | None for source packs |

The Northern quality layer also contains **18 attributed administrative names**
for BM/GL/PM (not counted as locality source coverage) and a sourced,
non-destructive Canadian Nova Scotia presentation correction.

Across these four M49 areas, **53 / 57 country-area sources** are included,
but no claim of full official municipal, address, postcode or translation
completeness follows. In particular, South America's 16/16 is source-pack
coverage, **not** official locality/municipal coverage. An area with zero source
locality rows may still contain territory anchors; zero source rows does not
prove no settlements.

UN M49 calls Northern America (021), Central America (013) and the Caribbean
(029) parts of the larger North America (003). Mexico is in M49 Central
America, regardless of colloquial use of "North America". Puerto Rico is
in M49 Caribbean and is present in the **US Census source** as US-PR, so this
view excludes its 1,231 US-source rows from Northern totals while preserving
the original source and independent Caribbean layer.

## Execute one audit / obtain the improvement queue

Run at the repository root, with Python 3.11+ standard library:

    python americas-registry/audit.py --mode audit > /tmp/americas-audit.json
    python americas-registry/audit.py --mode plan > /tmp/americas-plan.json
    python americas-registry/audit.py --mode cycle --rounds 3
    python -m unittest discover -s tests -p 'test_americas_unified.py' -v
    python scripts/verify_americas_snapshots.py

The audit checks: unique M49 placement, source country membership,
expected source totals, central/Caribbean published coverage CSV hashes,
official US/CA/MX index totals, source completeness flags, pending scope,
and explicit PR/MX cross-region accounting. It does **not** re-download
official sources, run authoritative name QA, or verify delivery addresses.
For preserved US/CA/MX/BR snapshot-bytes and parent-chain validation use
the independent `scripts/verify_americas_snapshots.py` command.

`--mode plan` produces a deterministic queue ordered by area, starting with
missing authoritative sources before language/postal and Address1 gaps.
`--mode cycle` rechecks the areas sequentially, stops on no input changes,
and **does not pretend that repeated audits add records**. Ingestion,
legal source review, QA and commits must occur between enrichment rounds;
re-run these checks after any such change.

## Required ingestion and publication gates

- **Scope and identity:** M49 country-area roster, ISO code, role,
  versioned source identifier and provenance; avoid "same name = same place".
- **Hierarchy:** closed/acyclic parent chain where source allows it; unresolved
  parents must remain reported, never filled by unreliable guesses.
- **Language:** distinguish verified English/local names, original-language
  strings, transliterations and machine-generated suggestions.
- **Postal:** use exact postal scheme/code as string (leading zeros intact),
  evidence, coverage relation and validity; one-to-many/many-to-many links.
- **Street and Address2:** separately record licensed road names, range or
  house number, premise and subpremise evidence. Reject unsupported "full
  worldwide address validation" claims.
- **Publication:** source licences and attribution, stable snapshots,
  checksum verification, reproducible builds, negative tests and human approval
  of new country claims before merging.

Source licences still apply: preserved US/CA/MX/BR snapshots include
ODbL-linked material; GeoNames packages are CC BY 4.0. Retain original
notices. Base layers must not be silently replaced by cross-source
merge results.

Central America now validates actual gazetteer payloads and the pinned Costa Rica raw archives through `quality_cycle.py`; the legacy six-country raw ZIP replay is still a separate task. The government 84-canton CodeSystem remains separate from the 82 ADM2 records in the Costa Rica GeoNames snapshot.
