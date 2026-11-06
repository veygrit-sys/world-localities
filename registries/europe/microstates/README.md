# European microstates: source-qualified localities and address candidates

The **five continental European microstates** are AD, LI, MC, SM, VA; this module also includes **MT (Malta)**, often counted among Europe's six smallest sovereign states. Crown dependencies and Gibraltar are excluded; they remain separately managed. All six already had a GeoNames country extract. This change adds **28 independently sourced official naming/postal reference observations** and an actual full-country OSM ingestion workflow. It does not claim to import previously inaccessible official building-level registers.

## Recorded evidence

| Country | Official source / register | New fixed official name facts | Existing GeoNames / other source |
| --- | --- | ---: | --- |
| AD | [Andorra government: seven parishes](https://www.govern.ad/documents/d/guest/viure_andorra2?download=true), [government geoportal address lookup](https://www.ideandorra.ad/geoportal/mIndex.jsp?lang=es) | 7 parishes | GeoNames; government address-search interface is not a confirmed bulk download |
| LI | [Government: eleven municipalities](https://www.llv.li/en/national-administration/public-procurement-department/basic-provisions/client/clients-countries-municipalities-etc), [official address/street CSV download portal](https://service.geo.llv.li/download/) | 11 names | GeoNames and **existing** `releases/hierarchy/western-europe/official-sources.json`; do not re-add official addresses |
| MC | [IMSEE](https://www.imsee.mc/) | 0 | GeoNames; OSM street/house-number candidate extract; no invented quartiers |
| SM | [Government: nine Castelli](https://www.interni.sm/pub2/InterniSM/Giunte-di-Castello/Le-Giunte-di-Castello.html) | 9 Castelli | GeoNames and OSM community extracts |
| VA | [Vatican State international postal code SCV-00120](https://www.vatican.va/roman_curia/secretariat_state/documents/informazione_generale/sp_ss_scv_info-generale_en.html) | 1 postal reference | GeoNames and a separate Vatican City OSM.fr extract, no fabricated residential street system |
| MT | [Office of the Address Registrar](https://address.gov.mt/), [government councils data](https://address.gov.mt/registers/) | 0 | GeoNames and existing Eurostat LAU 68 rows; no direct copy of restricted/unknown-license address register |

Names in `official-reference.csv` are **independently transcribed factual labels**, with local reference IDs only. Their IDs are **not official government-issued identifiers**. No names are joined across providers on name/coordinate alone. Dates and exact legal rights for any future large official data dump must be reviewed. The previous LI official address totals are historical *source observations*, not current unique deliverable households.

## Commands (repository root)

```bash
python scripts/europe_microstates.py inventory
python scripts/europe_microstates.py audit --country all
python scripts/europe_microstates.py build --output /new/microstates-baseline.sqlite
python scripts/europe_microstates.py verify --db /new/microstates-baseline.sqlite
python scripts/europe_microstates.py search --db /new/microstates-baseline.sqlite --country SM --text Fiorentino
python scripts/europe_microstates.py postcode --country VA --value 'SCV-00120'
```

The `audit` verifies compressed and decompressed GeoNames SHA-256, sizes, counts, country scope, duplicate IDs and asserted parent references, and checks the fixed manually attested name list checksum. Existing source identities, local spelling and current-vs-historical limitations stay intact. `build` outputs a **new**, never-overwritten, source-separated SQLite index. The database verification checks all source counts and a complete deterministic content digest.

## Entire open community OSM exports

The GitHub Actions workflow [microstates-full-source.yml](../../../.github/workflows/microstates-full-source.yml) runs every country's full PBF scan on a pull request or by manual workflow dispatch. Independent data sources: Geofabrik for **AD, LI, MC, MT** and OpenStreetMap.fr for **SM, VA**, whose national files are not listed as distinct Geofabrik subregions. Files are acquired into a clean directory; each source is byte- and SHA-256-pinned without overwriting old snapshots.

```bash
mkdir -p /new/osm-snapshots
for cc in AD LI MC SM VA MT; do
  python scripts/europe_microstates.py download --country "$cc" --directory /new/osm-snapshots
done
python -m pip install 'osmium==4.2.0'
python scripts/europe_microstates.py build --osm-root /new/osm-snapshots --output /new/microstates-osm.sqlite
python scripts/europe_microstates.py verify --db /new/microstates-osm.sqlite
```

Source files and derived OSM data remain under **ODbL-1.0** with attribution to OpenStreetMap contributors and extract providers. OSM node coordinates are retained only for nodes with valid locations; **no address point is invented for ways or relations**. OSM `addr:housenumber` yields an address *candidate*, not evidence of a country-authorized building number or delivery. Cross-border extracts may contain a buffer; `addr:country` conflicts are preserved in source flags.

This module deliberately does not ingest private contacts, contributor user metadata, private addresses, or perform automated scraping of restricted government services. Downloaded PBF bytes are kept outside git; the CI artifact is a compressed SQLite observation index with source receipts.

## Remaining quality / certification gates

- AD: official address-number export licensing, reference-date verification and crosswalk with the seven parishes.
- LI: review separate official address-file snapshots and historical/official status, street/building reference consistency; preserve existing accepted PINs.
- MC: verify current districts/street IDs against an authoritative register instead of treating community tags as official.
- SM: official roads/civic numbers (alongside Castelli), validated municipal hierarchy and postal assignments.
- VA: government/site-specific mail destination rules; `SCV-00120` is an international postal designation, **not** an assertion that arbitrary Vatican street addresses exist.
- MT: official local councils/localities and street/door number source download, usage permission, postal codes and region crosswalk.
- All six: independent real address benchmark, observed accuracy and false positives, shipping-provider format tests. Until then `postcode_existence_verified=false`, `national_address_completeness_verified=false`, `deliverability_verified=false`.
