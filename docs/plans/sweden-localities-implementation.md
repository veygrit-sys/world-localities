# Sweden Localities: deliverables and unblocked follow-ups (2026-11-05)

## Delivered as code and a reviewed candidate data layer

1. SCB 2026 official webpage transcription with **21 county and 290 municipality codes/names**, separate source ID namespace and pinned hash/byte size. This is a derived transcription; not a claim that the original XLSX has been independently replayed.
2. Offline CLI for municipality and GeoNames locality search. GeoNames source-IDs and unverified parent relations are retained; no municipal parent is guessed by matching strings.
3. GeoNames per-part checksum and row/identifier verification; Eurostat LAU checksum, code comparison and name-difference reporting (period 2024). No double-counting across layers.
4. An offline, hash-pinned SCB statistical-settlement importer (`GeoJSON` or read-only `GeoPackage`) with explicit schema mapping, duplicate-ID checks, CSV source preservation policy and deterministic no-clobber JSONL publication. A settlement polygon is not a delivery-address location.
5. Sweden postcode **syntax** screening. It always reports existence and delivery as unknown.
6. Network-free tests including full 2,017-row synthetic SCB locality inputs and failure modes (tampering, duplicates, unsafe SQL paths, ambiguous municipality references).

## Unverified/blocked for nationwide address validation

| Layer | Current status | Missing evidence |
|---|---|---|
| SCB 2026 counties/municipalities | 21/290 transcribed, pin + tests | Byte-for-byte official XLSX reconciliation and periodic version tracking |
| Eurostat LAU | Existing pinned 290 rows | 2024 to 2026 change review, not a replacement for current SCB |
| GeoNames places | Existing saved country snapshots, 33,003 total source features | Independent precision evaluation, official name comparisons |
| SCB tätorter/småorter 2023 | Importer implemented, data not loaded | Actual official GeoPackage/GeoJSON snapshot, source hash, field/schema check |
| Lantmäteriet Ortnamn | Source documented | Geotorget access, fixed snapshot and raw-source normalization |
| NVDB road names | Source documented | Access-controlled export, street/locality join quality evaluation |
| Postcode existence | Pattern only | Authorized authoritative postcode/postort feed with legal terms |
| Lantmäteriet address points | Access gated | Legal review and authorized API data, plus point/premise identity mapping |
| Delivery/cross-border carrier formatting | Not assessed | Real-world carrier rules, testing, rights, lifecycle evidence |

Do not mark the full country "complete" for delivery until authoritative street/number, postcodes and address-point validation are audited on an independent withheld benchmark. SCB settlement count and GeoNames rows are **not** denominators for national address coverage.

## CI and usage

```bash
python3 -m unittest discover -s tests -p test_sweden_localities.py -v
python3 scripts/sweden_localities.py verify
python3 scripts/sweden_localities.py search Stockholm --kind municipality
python3 scripts/sweden_localities.py search Göteborg --kind locality
python3 scripts/sweden_localities.py postcode '123 45'
```

This change is independent of the still-open six-country source-intake PR; its official source adapter can remain separate, and no existing GeoNames/Eurostat release is modified.
