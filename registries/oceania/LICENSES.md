# Licences and attribution

The data sources have separate terms. A software licence does not supersede data licences.

| Component | Terms | Attribution and transformation |
| --- | --- | --- |
| `sources/geonames/`, `data/`, GeoNames fields in `countries.*` | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | © GeoNames, https://www.geonames.org/. The 29 country dumps were downloaded on 2026-09-26 UTC. All populated-place features and administrative features other than political entity records are selected. Types, aliases, IDs and coordinates are preserved; deterministic parent links and QA flags are added. Original archives, download headers and SHA-256 hashes are included. No endorsement is implied. |
| `scope.csv`, UN M49 fields in `countries.*` | Factual classification extracted from UN M49 | United Nations Statistics Division, [M49](https://unstats.un.org/unsd/methodology/m49/), checked 2026-09-26 UTC. The 29 country/area entries and four subregions reproduce region 009 for statistical grouping. No sovereignty or boundary determination is made. |
| `official/AU/` ABS source fields | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | Australian Bureau of Statistics, Australian Statistical Geography Standard Edition 3, Local Government Areas 2025; adapted by Address Foundation. The pinned existing tables are copied unchanged and hashed. Includes 542 LGAs, six unincorporated areas and 19 non-spatial codes. ABS Mesh Block approximations do not constitute legal boundaries. |
| Existing administrative anchors and combined imported AU registry | [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/) and component notices | The imported WorldAddress derived database retains its ODbL obligations. Compact anchors include Countries States Cities Database identifiers and labels: Darshan Gada and CSC contributors. `official/AU/third_party/` and `upstream_DATA_LICENSES.md` retain the original notices. The separate GeoNames export has not been joined or deduplicated into this derived database. |
| Scripts and newly authored documentation | MIT, see `LICENSE` | WorldAddress contributors. |
| Additional GeoNames alternate names and direct-ID postal associations in `locale/` | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | © GeoNames, https://www.geonames.org/. Country alternate-name archives are retained with retrieval metadata. Names are filtered to the original entity scope, language tags and dates retained, country GeoNames IDs mapped to `country:<CC>` roots, and `post` rows separated as postal evidence. No endorsement or carrier validation is implied. |
| Google Address Data templates and derived `country_profiles.json` | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | Google, [libaddressinput](https://github.com/google/libaddressinput#license), https://chromium-i18n.appspot.com/ssl-address/data. Country records inherit missing defaults from `ZZ`; no delivery certification is implied. Raw responses, retrieval dates and SHA-256 hashes are retained. Google licenses its data under CC BY 4.0 separately from its Apache-licensed source code. |

ABS terms: https://www.abs.gov.au/website-privacy-copyright-and-disclaimer

GeoNames terms and field definitions: `sources/geonames/readme.txt` and
https://download.geonames.org/export/dump/readme.txt

If publishing only a subset, retain the applicable attribution, licence links, original source identifiers, source dates, declared changes and limitations. The complete package contains both raw GeoNames archives and the scripts used to derive these outputs.
