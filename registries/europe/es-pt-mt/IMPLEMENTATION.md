# ES–PT–MT high precision implementation status (2026-11-06)

The first release provides a source-aware, deterministic baseline index and tested intake of legal official files for the three countries. It does not upload unverified national address datasets. The repo's GeoNames snapshot has 39,207 ES + 22,115 PT + 361 MT = 61,683 observations. The build validates preserved compressed and uncompressed hashes, row counts and unique ids for *all* source parts.

The following country objectives are distinct:

- Spain: CNIG CartoCiudad province GeoPackages (source-specific address entrances, postal and municipality code links) plus INE Nomenclátor settlement codes. Data downloaded by user/authorized pipeline later, not included in this PR.
- Portugal: DGT CAOP2025 (continent, Madeira and Azores separately) plus INE's Base Nacional de Moradas of mainland Portugal. Confirm INSPIRE geometry/CRS and file terms before acceptance.
- Malta: Address Registrar street/locality registry feeds and local council official boundaries; registered address / door numbers require verified export and Gazette history. Portal metadata does not automatically confer official status or deliverability.

Normalized evidence schema retains `source_ref`, native strings, postcode lexeme, original CRS, x/y only for explicit source points, unknown/unverified flags, and original parent source IDs. Sources are never merged by name alone. Postal syntax is a **format** check, not proof of a real postcode. The SQL index is read-only by default for queries; release and evaluation require legally reviewed source snapshots, independent real-address benchmark and actual carrier rules.

CLI and detailed receipts: `registries/europe/es-pt-mt/README.md`. Country catalog: `registries/europe/es-pt-mt/source-catalog.json`.
