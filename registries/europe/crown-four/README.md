# Jersey, Guernsey, Isle of Man and Gibraltar: source-qualified locality evidence

This project manages four distinct collection/postal codes: **JE, GG, IM, GI**. Jersey, Guernsey and the Isle of Man are **Crown Dependencies**, not part of the United Kingdom; Gibraltar is a **British Overseas Territory**, not a Crown Dependency. Do not silently rewrite any of these as `GB`.

## Accepted source layers

- Existing `registries/europe/countries/{JE,GG,IM,GI}`: **449** pinned GeoNames observations; parent relations are replayed but unverified legal parents remain unchanged. Names are gazetteer observations, not mailing addresses.
- `official-reference.csv`: **44 government-attested reference facts**: Jersey's 12 parish names, Guernsey's ten parish names, the 21 authorities listed for the Isle of Man's **2025 local elections**, and the Royal Gibraltar Post Office's shared postcode `GX11 1AA`. These are plain published names and one shared territorial code, not a reused bulk address dataset. `ref:*` IDs are **provisional Veygrit IDs**, not assigned by governments.
- Separate optional ODbL 1.0 OpenStreetMap evidence: two Geofabrik extracts for *Guernsey and Jersey together* and for the *Isle of Man*. All records retain source identity; named road **segments are not unique roads**. PBF source bytes and timestamp are pinned to SHA-256 before import. Gibraltar has **no Geofabrik country-specific extract** in this pipeline; do not pretend Iberian or La Línea objects are Gibraltar addresses.

## Why the territories need separate rules

| Territory | Administrative reference | Postal policy |
|---|---|---|
| Jersey JE | 12 parishes | `JE`-prefixed postcode: syntax-only test; individual postcode existence unknown |
| Guernsey GG | Ten **Guernsey** parishes; Alderney and Sark require their own authoritative address sources | `GY` prefix; postcode finder is an online lookup, **not** redistribution permission |
| Isle of Man IM | **21** elected local authorities in 2025 source; a government ArcGIS service still describes **24** boundaries, so **do not merge editions** | `IM` prefix; actual postcode-to-address relationship unknown |
| Gibraltar GI | No invented parish grid | `GX11 1AA` is a **shared** code confirmed by the Royal Gibraltar Post Office, **not a unique building/postal zone**. Domestic notation `E/V` is not treated as a postcode |

Jersey's government Land and Property Gazetteer is described as containing **over 90,000 address points** and being updated daily. It is not copied or declared legally reusable; bulk access rights and actual source fields need a separate review. The Isle of Man MANNGIS map provides street/postcode search but its public mapping access does not imply redistribution rights. Guernsey Post offers an online Bailiwick-wide address finder; do not scrape bulk addresses from it.

Official background references in [`sources.json`](sources.json) preserve these restrictions. Names are sourced from the governments' public lists; the list itself is pinned to a source SHA-256.

## How to run (repository root; Python 3.11+)

```bash
python scripts/crown_four_localities.py audit
python scripts/crown_four_localities.py postcode --country GI --value 'GX11 1AA'
python scripts/crown_four_localities.py build --output /tmp/crown-four-base.sqlite
python scripts/crown_four_localities.py verify --db /tmp/crown-four-base.sqlite
python scripts/crown_four_localities.py query --db /tmp/crown-four-base.sqlite --country JE --text Helier
python -m unittest discover -s tests -p 'test_crown_four_localities.py' -v
```

Optional full-source ODbL import requires `pip install osmium==4.2.0` and network access:

```bash
mkdir -p /tmp/crown-pbf
python scripts/crown_four_localities.py download --source guernsey-jersey --directory /tmp/crown-pbf
python scripts/crown_four_localities.py download --source isle-of-man --directory /tmp/crown-pbf
python scripts/crown_four_localities.py build --output /tmp/crown-four-osm.sqlite --source-root /tmp/crown-pbf \
  --pin /tmp/crown-pbf/guernsey-jersey-source-pin.json \
  --pin /tmp/crown-pbf/isle-of-man-source-pin.json
python scripts/crown_four_localities.py verify --db /tmp/crown-four-osm.sqlite
python scripts/crown_four_localities.py query --db /tmp/crown-four-osm.sqlite --country UNRESOLVED --kind named_road_segment
```

An entire combined Channel Islands PBF **does not certify** whether its observations belong to JE or GG. Located nodes are only labeled `geographic_bbox_candidate_not_legal_border`; ways and relations with no country ID are quarantined as `UNRESOLVED`. Explicit OSM tags are source claims, not independently verified legal boundaries. The Isle of Man extract also covers a **buffer**, not a certified jurisdictional polygon. No way or relation centroid is invented. Gibraltar's OSM address points are not imported until a licensed, provenance-controlled local source and independently checked polygon exist.

## Completion status

The **Gazetteer and government name reference layer** is testable, verifiable and searchable. A full verified list of addresses and postal/address-to-carrier mappings is **not complete**. No national completeness percentages, delivery promises, or unverified road-to-number joins are asserted. Exact `source_id`, ODbL attribution, source hash, legal reuse terms and verification outcome must travel with all published derivative databases.
