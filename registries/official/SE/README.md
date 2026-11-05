# Sweden (SE): SCB administrative reference + locality search

## Accepted local content

- `scb-municipalities-2026.csv`: 21 län, 290 kommuner, identifiers and names **transcribed from SCB's rendered 2026 official code list** on 2026-11-05. This is a *derived transcription*, not an original SCB XLSX file. `source-manifest.json` records the exact file bytes and the limitation: independent row-by-row XLSX reconciliation remains pending.
- `registries/europe/eurostat-lau/SE`: 290 official Eurostat LAU observations (2025 release label, 2024 source period). This remains a distinct source, not a replacement for SCB's 2026 register.
- `registries/europe/countries/SE`: existing GeoNames entries, preserved with original IDs and metadata, not a government-certified or delivery address register.

The SCB transcription covers the **official county/municipality list**, not all named locations, postal codes, streets or buildings. GeoNames data are not counted as unique addresses. No model has been trained and no address deliverability has been tested.

## Commands (Python 3.11+, no extra runtime packages)

```bash
python3 scripts/sweden_localities.py verify
python3 scripts/sweden_localities.py search Göteborg --kind municipality
python3 scripts/sweden_localities.py search Älvsjö --kind locality
python3 scripts/sweden_localities.py postcode '123 45'
python3 -m unittest discover -s tests -p test_sweden_localities.py -v
```

The `verify` command cross-checks the 21/290 official SCB transcription, the saved Eurostat LAU and GeoNames file hashes/counts. An exact SCB/Eurostat code-set comparison is reported, including differences; their snapshots are distinct.

The `postcode` command tests **format only** and returns `null` for existence and delivery. Name search returns source-qualified records; it does not silently equate municipality names with GeoNames administrative IDs.

## Optional SCB statistical settlement polygons

SCB publishes `Statistiska tätorter` (2023: 2,017) and `Statistiska småorter` (2023: 3,097) as free open geodata (CC0). They are **statistical built-up areas**, not unique postal addresses. For an officially obtained file, fix its SHA-256/size and verify its fields, CRS and license; then run the offline importer:

```bash
python3 scripts/sweden_localities.py import-scb \
  --pin /path/to/reviewed_tatorter_pin.json \
  --source-root /path/to/cached/scb/ \
  --output /new/output/se-tatorter-2023.jsonl
```

A pin must declare country `SE`, dataset `tatorter_2023` or `smaorter_2023`, official SCB WFS source URL, `format` (`gpkg` or `geojson`), file path, bytes, SHA-256, `license: CC0-1.0`, `rights_reviewed: true`, `crs`, and explicit field mapping `id`, `name`, `county`, `municipality`. `gpkg` needs the actual confirmed `table`. A reference example (field names must be verified on the **actual** export, not guessed):

```json
{
  "country": "SE", "dataset": "tatorter_2023", "format": "gpkg",
  "source_url": "https://geodata.scb.se/geoserver/stat/wfs?service=WFS&request=GetFeature",
  "path": "Tatorter_2023.gpkg", "bytes": 1, "sha256": "<64-hex-from-actual-file>",
  "license": "CC0-1.0", "rights_reviewed": true, "crs": "EPSG:3006",
  "table": "Tatorter_2023",
  "fields": {"id": "tatortskod", "name": "tatort", "county": "lan", "municipality": "kommun"}
}
```

`bytes: 1` and the hash placeholder are deliberately **not usable** until replaced by a checked source. Incorrect field names are rejected. No actual SCB polygon archive has been incorporated into this repository as part of this change.

## Missing for complete delivery-address coverage

1. Lantmäteriet's *Belägenhetsadress Nedladdning, vektor* (GeoPackage/STAC) requires an account and legal review; it must **not** be accessed or redistributed without that approval.
2. Lantmäteriet's Ortnamn data are free, but Geotorget API access still requires authorization. The INSPIRE Geographical Names download is an alternative to examine after verifying its actual release and license.
3. NVDB `Gatunamn` / `ÖvrigtVägnamn`: road names are not a list of every delivery street; obtain the licensed export using the relevant API/account rules.
4. PostNord / Postnummerservice: current postal code and postort existence cannot be established by a regex; check rights and a suitable data agreement before any bulk import.
5. Independently review source coverage, missing addresses, time validity, specific premises, and carrier-specific delivery rules; the 21/290 and SCB settlement counts are not address coverage figures.

## Official sources

- SCB 2026 county/municipality list: https://www.scb.se/hitta-statistik/regional-statistik-och-kartor/regionala-indelningar/lan-och-kommuner/lan-och-kommuner-i-kodnummerordning/
- SCB reuse terms: https://www.scb.se/om-scb/om-scb.se-och-anvandningsvillkor/
- SCB tätorter: https://www.scb.se/vara-tjanster/oppna-data/oppna-geodata/statistiska-tatorter/
- Lantmäteriet Ortnamn: https://geotorget.lantmateriet.se/link/ortnamn-nedladdning-vektor
- Lantmäteriet addresses: https://geotorget.lantmateriet.se/geodataprodukter/belagenhetsadress-nedladdning-vektor-api
- NVDB API acquisition: https://www.nvdb.se/sv/kund/hamta-aktuella-data/
- PostNord postcode system: https://www.postnord.se/vara-verktyg/sok-postnummer-och-adress/
