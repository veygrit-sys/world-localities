# Denmark & Sweden — self-built open OSM locality and address *candidates*

This is an **independent, provenance-preserving ODbL evidence layer**, not an official address register, an authoritative municipality hierarchy or a certified delivery-address validator.

Existing GeoNames/Eurostat/Nordic datasets in `world-localities` remain separate. In Sweden, the previously verified 21 län / 290 kommuner register is unchanged. In Denmark, the DAR API is a separately authenticated official data source; it is **not** scraped or circumvented here. Neither country has a verified count of all deliverable addresses in this package.

## Reproducible nationwide-source intake

The open source is the country-level OpenStreetMap PBF from Geofabrik, one file for DK, another for SE. Downloading a complete open extract **does not** imply complete OSM address mapping. The national extract contains buffered source observations; an OSM address-point claim is not proof of postal existence, door/entrance geometry, municipal approval or last-mile carrier acceptance.

Requires Python 3.11+ and `osmium` (`pip install osmium==4.2.0`) for PBF input; XML is supported **only for explicit synthetic test fixtures**.

```bash
# Both folders must exist and be empty, and need enough disk space for PBF + SQLite.
mkdir -p /data/veygrit/dk /data/veygrit/se
python scripts/dk_se_open_osm.py download --country DK --directory /data/veygrit/dk
python scripts/dk_se_open_osm.py download --country SE --directory /data/veygrit/se

python scripts/dk_se_open_osm.py build \
  --pin /data/veygrit/dk/denmark-source-pin.json \
  --source-root /data/veygrit/dk --output /data/veygrit/dk-evidence.sqlite
python scripts/dk_se_open_osm.py build \
  --pin /data/veygrit/se/sweden-source-pin.json \
  --source-root /data/veygrit/se --output /data/veygrit/se-evidence.sqlite

python scripts/dk_se_open_osm.py verify --db /data/veygrit/dk-evidence.sqlite
python scripts/dk_se_open_osm.py search --db /data/veygrit/se-evidence.sqlite \
  --category named_place --text Göteborg
python scripts/dk_se_open_osm.py search --db /data/veygrit/dk-evidence.sqlite \
  --category address_candidate --postcode 0100
```

`download` writes the exact SHA-256, byte size, download time and source URL into a dedicated JSON receipt. The resulting PBF is not in Git. Never overwrite a pinned snapshot; move to a new folder to refresh. A raw file may be pinned separately with `pin`. Build will refuse mismatched SHA-256 or file size, unsafe paths, XML not declared as a test fixture, unknown origin, missing ODbL attribution or unreviewed rights. The national dataset remains under ODbL; attribution and relevant share-alike obligations must be respected in any derived release.

## Output design

`features` SQLite rows are source-qualified `osm:node:<id>`, `osm:way:<id>`, `osm:relation:<id>` objects, with separate categories: `named_place`, `named_road_segment`, `address_candidate`, `administrative_boundary_label`.

- Stores raw house number strings, street/placename, OSM-reported postal code/city, and the **source tag** municipality if present.
- Retains WGS84 node coordinates only. A building way's centroid or relation's coordinate is **not** guessed.
- Retains the OSM address/street labels, relevant Swedish/Danish name tags and OSM object IDs; excludes phone/email/name-of-person/contact tags, and all OSM author metadata.
- Duplicates in the same category and source object ID are errors. The same OSM object may legitimately have multiple categories.
- Road segment observations are **not unique streets**, and OSM `addr:street` does not itself prove a street-to-house relationship.
- Report always states `postal_existence_verified=false`, `national_completeness_verified=false`, `deliverability_verified=false`.
- `postcode` is **syntax-only**, not an existence lookup. `search` by postcode uses the stored lexeme with only spaces ignored; it does not normalize a false postcode into a valid one.
- All results remain subject to ODbL, and must not silently be merged into a proprietary official-source table or exported without license review.

## Full-source execution on GitHub Actions

The separate workflow `.github/workflows/dk-se-open-osm.yml` has a small automatic contract-test job and a **manual** full-source run per country. The manual run acquires and hashes an open full-country PBF, builds and verifies the SQLite index, and uploads a report artifact. An optional switch also compresses and uploads the generated SQLite index; this can be large and consume GitHub Actions storage. National imports are **not** automatically claimed to have been executed merely by checking in this code.

## Separate official registers

- Denmark: [Datafordeler DAR file download](https://datafordeler.dk/dataoversigt/danmarks-adresseregister-dar/dar-fildownload/) requires API key/OAuth and account setup; its status is independent of this open community dataset.
- Sweden: [Lantmäteriet Belägenhetsadress](https://geotorget.lantmateriet.se/geodataprodukter/belagenhetsadress-nedladdning-vektor-api) requires legal review and account/API access, even though the product is free. Official address points require an authorized dataset. This module does not request access, download, or copy gated data.
- OSM open raw sources: [Denmark](https://download.geofabrik.de/europe/denmark.html), [Sweden](https://download.geofabrik.de/europe/sweden.html); [ODbL terms](https://www.openstreetmap.org/copyright).

## Completion gates not reached

National completeness requires an independent count of current, deliverable address objects and a current authority source; ZIP/PBF ingestion alone cannot establish it. A future certified layer needs a legally authorized street/number/point register, postcode/postort truth data, independent ground-truth evaluation, carrier-specific transformation and delivery testing. Until then, consumer-facing validation must return **unknown / needs confirmation** for addresses only seen in OSM.
