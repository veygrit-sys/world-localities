# Official localities / address development — IT, RS, BG, RO, GR, HU

The canonical GeoNames place sources remain in `registries/europe/countries/{CC}` and Eurostat LAU is a **separate statistical namespace**. This module adds versioned legal-source discovery, a safe offline importer and a 2026 Romanian SIRUTA snapshot. No source row is by itself proof of valid postal service or deliverability.

## Ready now

- `python scripts/europe_priority_six.py inventory`: six-country source plan, URLs, scope and caveats.
- `python scripts/europe_priority_six.py audit-geonames --country all`: replay SHA-256 checks, decompressed source hashes, row counts, ID uniqueness and country identity for all six pre-existing GeoNames bundles.
- `python scripts/europe_priority_six.py audit-ro`: verify the complete **16,978-row 2026 SIRUTA derived mirror** byte-identical to upstream's pinned Git blob and verify 42 counties, 3,187 UAT (including 6 Bucharest sectors), 13,749 localities, unique source codes, and parent references. Historical/current postal assignments are **not** inferred.
- `python scripts/europe_priority_six.py ingest-ro --output /new/ro-siruta-2026.sqlite`: publish a new standalone source-qualified SQLite search index for Romania. No overwrite.
- `python scripts/europe_priority_six.py search --db /new/ro-siruta-2026.sqlite --text București`: search the built index.
- `python scripts/europe_priority_six.py ingest --pin /data/pin.json --source-root /data/immutable --output /new/output.sqlite`: load a **new** rights-reviewed, byte- and SHA-256-pinned source CSV, ZIP/CSV, JSON array, ZIP/JSON or GeoPackage table with explicit field mapping and source CRS.

`ingest` refuses unknown ID mappings, unsafe paths, changed bytes, repeated identifiers, unreviewed rights, missing provenance, failed required fields and unsupported coordinate systems. Source status, original parent/street IDs, and house number strings are preserved, and independent identity evidence is never merged by name/coordinate. Other columns (which could include person/contact data) are excluded unless specifically mapped and approved.

### Example approved pin (schema illustration only; not an accepted real source)

```json
{
  "schema_version": 1, "country": "RS", "kind": "address", "format": "csv",
  "source": "rgz-address-house-numbers-EXAMPLE", "source_version": "REPLACE_WITH_SOURCE_DATE",
  "official_url": "https://data.gov.rs/sr/datasets/adresni-registar/",
  "downloaded_at": "REPLACE_WITH_UTC_TIMESTAMP", "rights_reviewed": false,
  "license_name": "REPLACE_AFTER_REVIEW", "filename": "actual-export.csv",
  "bytes": 0, "sha256": "REPLACE_WITH_SHA256", "coordinate_crs": "not_provided",
  "fields": {"id": "ACTUAL_UNIQUE_ADDRESS_ID", "house_number": "ACTUAL_HOUSE_NUMBER", "street_id": "ACTUAL_STREET_ID"}
}
```

To run for a real source, select actual headers and update the pin after legal review; the example above is deliberately **not executable** as an accepted source. A source may contain a parcel/planned building rather than a current deliverable residence.

## Source policy

- Romania's normalized 2026 SIRUTA data is derived from the INS 2026 SIRUTA S1 source, mirrored by [romania/siruta](https://github.com/romania/siruta), license **CC BY 4.0**. Full attribution and links are in [`sources.json`](sources.json). The upstream official raw file SHA-256 is recorded separately from the derived CSV Git blob. No independent replay of the transformation from 2026 raw original is claimed.
- Italy ANNCSU distributes monthly ZIP/CSV street and civic data. Serbia RGZ publishes official street and house number data. Bulgaria NSI EKATTE provides current and archived JSON/Excel. Greece ELSTAT publishes a 2026 municipalities/settlements register. Hungary KSH publishes settlement/county information via Helységnévtár. **Their official bulk files have not been imported by this change**; confirm schema, licensing and exact source bytes first.
- `postal_existence_verified`, `national_address_completeness_verified`, and `deliverability_verified` remain `false`. Caller should use `unknown / requires confirmation` for a delivery decision without separate provider rules.
- Never add the same person or property as several national observations merely because source layers overlap. Excluded: personal contact information, legal/cadastral owner attribution and fictional missing house numbers.

## Further work

The country-by-country acquisition and independent quality gates are in `sources.json`. For ANNCSU and RGZ, compare street IDs and house numbers at the entity level; for EKATTE and SIRUTA, validate current administrative geography. Then collect separately licensed address points, postal assignments and carrier-specific delivery rules.
