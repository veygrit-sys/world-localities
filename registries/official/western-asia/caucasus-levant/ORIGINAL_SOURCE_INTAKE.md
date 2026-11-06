# Original sources: verified offline intake

The open-data portal listings were inspected but source bytes have not been
retrieved into the repository. No original official raw dataset is being
represented as present. This parser permits audit after a user acquires the
exact original file and its SHA-256 hash. The audit output contains only
aggregate metadata, column names, counts, and source provenance, not raw
addresses or personal information.

Supported original types:

- Azerbaijan REIS/IDDA government GeoJSON (AZ-IDDA-ADMIN-GEOJSON-2025),
  containing city and territorial-unit geometry. It audits geometry validity,
  per-feature properties and duplicate/missing source IDs, without pretending
  the statistical economic groups are official geographic boundaries.
- Jordan Post office CSV (JO-POST-OFFICES-2023), mapping explicit source column
  names, postal syntax and one-to-many postcodes across offices. The postal
  field and office field must be selected from the actual CSV header after
  inspection; do not guess a mapping from an unfamiliar schema.

Commands:

    python scripts/western_asia_original_source_intake.py inventory
    python scripts/western_asia_original_source_intake.py audit --source-id AZ-IDDA-ADMIN-GEOJSON-2025 --file /secure/az.geojson --sha256 ACTUAL_SHA256
    python scripts/western_asia_original_source_intake.py audit --source-id JO-POST-OFFICES-2023 --file /secure/jo.csv --sha256 ACTUAL_SHA256 --postcode-field OFFICIAL_CSV_HEADER --office-field OFFICIAL_CSV_HEADER --encoding utf-8-sig
    python -m unittest tests.test_western_asia_original_source_intake -v

Unreviewed source-code associations, geometry, or string matches never
authorize government-to-GeoNames ID verification, nationwide completeness
or deliverability. Review licences and historic/territorial boundaries
before creating an official national release.
