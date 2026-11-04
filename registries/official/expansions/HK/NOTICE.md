# Hong Kong official ALS data notice

Source: Hong Kong Special Administrative Region Government, Digital Policy Office, Address Lookup Service (ALS). The Government and the relevant organisations own the intellectual property rights in the source data. This project preserves that attribution in the original and transformed copies. No government endorsement or affiliation is implied.

- Official archive: https://www.als.gov.hk/data/ALS-GeoJSON.zip
- Official catalogue: https://data.gov.hk/en-data/dataset/hk-dpo-als_01-als/resource/92eed8bd-9e6f-4aac-9c9a-5ea6f5dbb4b8
- Official schema: https://www.als.gov.hk/docs/als-geojson.schema.json
- Applicable source terms: https://data.gov.hk/en/terms-and-conditions
- Original retrieval date: 2026-11-04. Following execution-environment loss, source bytes were reacquired on 2026-11-05 and the original ZIP and normalized CSV SHA-256 digests were reproduced exactly. The schema and terms are preserved as obtained snapshots; no address currentness claim follows from retrieval.
- Catalogue resource update date recorded for this edition: 2026-10-23. This describes catalogue metadata, not each observation's legal or effective date.

DATA.GOV.HK permits browsing, downloading, distribution and reproduction for commercial and non-commercial purposes subject to its full conditions. Those conditions include identifying and acknowledging the original source and ownership, complying with the other conditions and indemnity provisions, and accepting the data as supplied without warranties. Read the complete terms in the linked official page and the saved `sources/data-gov-hk-terms.html` snapshot. This notice is a summary, not a replacement for those terms. No SPDX licence or repository-wide licence is assigned to these source data by this project.

Transformations select every district 2D Feature from the saved original archive and preserve all selected source features in canonical JSON in the CSV. Original Chinese and English labels, source identifiers, street/building number strings and ranges, WGS84 coordinates and HK1980 values remain source observations. Empty English fields and missing coordinates are retained. Observation IDs derive from member name and row position; they are not government address IDs. Multiple observations sharing a CSU identifier remain separate.

The original ZIP also contains an optional 3D public-rental-housing member. It is retained byte-for-byte as part of the archive but is neither parsed nor normalized into this dataset. No nationwide completeness, freshness, premise or unit completeness, uniqueness, geocoding suitability, legal address validity or deliverability is asserted. Source data may include omissions, differing observations and errors.

The normalized data are distributed with this notice, `sources.json`, original source receipt, original archive, and saved official schema and terms. Derived source-file hashes and deterministic replay establish fidelity to this pinned source edition, not independent real-world accuracy.
