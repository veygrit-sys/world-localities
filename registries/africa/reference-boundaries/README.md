# Kenya and Ghana pinned administrative boundary reference layer

Generated on 2026-11-06 from **exact SHA256-verified original GeoJSON
bytes** at geoBoundaries Git repository revision `9469f09`.

## Actual imported rows

| Country | Layer | Units | Year represented | Original source | License |
|---|---|---:|---|---|---|
| KE | KEN ADM1 | 47 | 2020 | IEBC / OCHA ROSEA | CC BY 3.0 IGO |
| KE | KEN ADM2 | 290 | 2020 | IEBC / OCHA ROSEA | CC BY 3.0 IGO |
| GH | GHA ADM1 | 16 | 2019 | Ghana Statistical Service / USAID Ghana HPNO | CC BY 4.0 |
| GH | GHA ADM2 | 260 | 2019 | Ghana Statistical Service / USAID Ghana HPNO | CC BY 4.0 |
| **Total** | | **613** | | | |

See `source_receipts.json` for original URLs, SHA256, byte lengths,
licenses and per-layer counts. Original GeoJSON geometry was used to
derive the testable crosswalk but is **not** duplicated in this repository.
A non-legal representative-point-in-polygon association attaches ADM2
shapes to a source ADM1 polygon when unique. This is not a government
administrative code, legal parent approval, or a live boundary certificate.

- Kenya source: [geoBoundaries KEN ADM2](https://www.geoboundaries.org/api/current/gbOpen/KEN/ADM2/).
- Ghana source: [geoBoundaries GHA ADM2](https://www.geoboundaries.org/api/current/gbOpen/GHA/ADM2/).
- Publisher: [geoBoundaries, William & Mary geoLab](https://www.geoboundaries.org/).
- Kenya source license: [CC BY 3.0 IGO](https://creativecommons.org/licenses/by/3.0/igo/).
- Ghana source license: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).

This layer is not an endorsement by, nor an official service of,
IEBC, OCHA, Ghana Statistical Service, USAID or geoBoundaries.

## 80 cases inspected against polygons

Source GeoNames unresolved direct parents are preserved without altering
`countries/KE/entities.csv.gz` or `countries/GH/entities.csv.gz`.

| Finding | Kenya cases | Ghana cases |
|---|---:|---:|
| Unique name + unique spatial ADM2 + source-state name consistent | 3 | 0 |
| Spatial ADM2 candidate with source-state consistent but without exact name | 11 | 1 |
| Spatial areas found; GeoNames source lacked a comparable ADM1 identity | 51 | 0 |
| GeoNames source state's name conflicts with spatial ADM1 | 1 | 5 |
| No unique spatial area | 2 | 5 |
| Source ADM1 vs ADM2 spatial areas disagree | 1 | 0 |
| **Total direct-parent cases reviewed** | **69** | **11** |

Three strongest Kenya entity candidates are **Ainamoi** (`gn:11429139`),
**Ainabkoi** (`gn:11429474`) and **Endebess** (`gn:11468271`).
The polygon area, source county name and locality name agree, but the
GeoNames source is ADM3 and the corresponding direct ADM2 parent is still
absent. This makes a *cross-source location candidate*, not a valid
`parent_id`. Do not substitute source-specific geoBoundaries shapeID for
a missing original GeoNames parent.

Six source-state/polygon disagreements need independent local review:
Kenya **Nyatike** and Ghana **Obiliakua, Moshiehenekurom, two distinct
Nyamebekyere features, Anyin**. The source may use old administrative
boundaries or wrong positions; do not select whichever layer is newer.
Other cases near coastlines and borders have no unique polygon and
must remain unassigned until audited.

## What is not achieved

- **0** of the 80 missing GeoNames direct parent IDs have been rewritten
  or certified. Spatial membership is a distinct relationship.
- 2019/2020 administrative and electoral datasets are not proven to be
  current national-government local administrative unit registries in 2026.
  Specifically, IEBC election constituencies and national administration
  sub-counties may not align; treating 290 shapes as the latter without
  reviewing the source definition would be incorrect.
- A published district boundary does **not** confirm any specific postal
  delivery address, postal code, location spelling or road.
- The SHA checks prove that these derived rows were built from a pinned
  published source; they do **not** prove official contemporary validity.
- Other provider terms, attribution, source vintages and territorial
  disputes must be checked before redistributing more geometry.

## Reproduction

```bash
python -m pip install shapely==2.1.2
python registries/africa/reconcile_boundary_gaps.py
python -m unittest discover -s registries/africa -p 'test*.py' -v
```

The import downloads 4 pinned files (approx 49 MB), verifies size and
SHA256, extracts the 613 named shapes to `*-source-units.csv`, then
checks 80 original-source unresolved parent coordinates against polygons.
The report is `unresolved-spatial-review.csv` with source-specific
identifiers, the outcome, and `approved_administrative_parent=false`.
`unresolved-spatial-summary.json` contains aggregated case counts.

## Source-year spatial membership overlay

`source-year-spatial-memberships.csv` now supplies **66 source-year
spatial memberships** between unresolved GeoNames source IDs and
unambiguous geoBoundaries ADM1/ADM2 polygons: **65 Kenya (2020) and
1 Ghana (2019)**. This is computed from unique point containment within
the internally consistent same-year shape hierarchy, omitting geographic
conflicts, multiple candidates and areas with no unique boundary.

These source-specific ADM2 shape IDs **are not** the missing immediate
original GeoNames `parent_id` values. No new GN entities or parent IDs
were invented. This is a second relationship that can be safely read by
downstream clients for year-scoped geographic enrichment but must never
be passed as a legally verified current administrative parent. The
other **14** unresolved records remain without this source-year
overlay. All **80** original direct-parent gaps remain unresolved in
the original GeoNames hierarchy.
