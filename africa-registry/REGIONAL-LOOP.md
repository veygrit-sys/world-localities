# Africa north-first enrichment loop

The existing 56-country snapshot is preserved. New country files are built as review candidates in a separate directory; neither the tool nor its workflow promotes or deletes baseline data.

## Order and scope

| Order | Region | Countries/areas |
|---|---|---:|
| 1 | Northern Africa | 7 |
| 2 | Western Africa | 17 |
| 3 | Middle Africa | 9 |
| 4 | Eastern Africa | 22 |
| 5 | Southern Africa | 5 |

All 60 entries of the existing `upstream/scope.json` are checked once per pass. This includes the previously untransferred MA, NG, CD and MG. Northern order: DZ, EG, LY, MA, SD, TN, EH. M49 is a statistical grouping, not a sovereignty decision; EH remains distinct, and source `cc2` fields are retained. Scope is frozen and checked against the existing source, not represented as newly certified international status.

## Run

Python 3.11 or newer, standard library only. From the repository root:

```sh
python3 -m unittest discover -s africa-registry -p 'test*.py' -v
python3 africa-registry/build.py verify
python3 africa-registry/regional_loop.py --output /tmp/africa-candidates --cache /tmp/africa-source-cache
```

Use `--regions north` for the first region only. Select multiple regions with space-separated keys. Output must be new and must not overlap the baseline or cache. Reuse a checksum-verified cache with `--offline` and a new output path for reproducibility. A new empty cache is necessary for fresh upstream collection; cached downloads are never relabelled as newly retrieved. Do not run with Python `-O`.

The branch workflow has a bounded one-pass push trigger and manual dispatch, not a recurring schedule. It runs the existing baseline tests and integrity checks, then processes regions sequentially. It requests contents-read only and cannot push candidates into main. Candidate records and raw source receipts/ZIPs are retained as a private Actions artifact for 14 days. Preserve an accepted artifact elsewhere before it expires.

## Outputs and quality gates

- Existing `gn:` identities, all 19 raw GeoNames fields and original 30-column entity format are retained. Parent assignment uses the existing exact source-code builder, never fuzzy names.
- Per-country GeoNames A/P extracts and language-tagged alternate names are collected separately. Original preferred/historical/time flags survive. Special `post`, IATA and link values are identifiers, not translations or verified postal assignments.
- SHA-256 receipts, archive limits, exact ZIP member names, real calendar dates, finite coordinates, duplicate checks, lossless replay, input-order independence and deterministic compression are checked.
- Each country has `delta.json` and `enrichment.json`. Disappeared IDs, significant count drops, older source dates, increased unresolved parent counts, failed name collection and the Algerian hierarchy gap block automatic acceptance.
- `run-report.json` distinguishes base integrity, alternate-name completion, country errors and review blockers. `verification.json` comes from the preserved builder; `artifact-manifest.json` inventories output checksums. Partial failures remain visible and produce a nonzero exit status. Successful integrity checks do not grant release approval.

## Official Algeria reference

`official-references/DZ-2026-wilayas.json` transcribes the eleven new wilaya names, source codes 59–69 and seats from decree 26-206, official Gazette No. 40, 3 June 2026, page 5. The official French page text and rendered page were inspected. These are source facts, not automatically linked GeoNames entities. ISO codes, municipal membership, legal/operational transition dates and boundaries are not invented. The PDF itself is not archived in this patch, and its digest is explicitly null.

Source: https://www.joradp.dz/FTP/jo-francais/2026/F2026040.pdf

## Explicit limits

This is collection and integrity verification, not full official validation of all African addresses. No complete streets, house numbers, Address1/Address2, postcode-to-address mapping or deliverability is claimed. Source preferred names are not independently certified official translations. Existing BF/BI source-freshness caveats remain applicable. Country count matching is not sufficient to verify current administrative membership.

GeoNames data remains CC BY 4.0; see `NOTICE.md`. New code follows this directory's MIT licence. Tests use synthetic fixtures and are not geographic evidence. No main merge, public publication or continuous service is performed by this loop.
