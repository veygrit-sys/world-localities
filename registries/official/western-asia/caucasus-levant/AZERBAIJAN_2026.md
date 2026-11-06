# Azerbaijan 2026 administrative names and locality audit

Source: Azerbaijan State Statistical Committee regional index (29 June 2026),
https://stat.gov.az/source/regions/ . The checked-in JSON contains 14 economic
reporting regions and 68 listed administrative-unit labels. Economic regions
are **statistical groups**, not GeoNames ADM1 units. Nakhchivan is listed as
one autonomous republic here, not all subordinate districts or settlements.

Command examples:

    python scripts/western_asia_azerbaijan_administration.py report
    python scripts/western_asia_azerbaijan_administration.py find --name Ağdərə
    python -m unittest tests.test_western_asia_azerbaijan_administration -v

This compares names against the SHA-256-verified existing GeoNames AZ archive
(71 ADM1 records) and separates cities from rayon names where the original
label provides such a hint. A valid transliteration is **not** an official
English name or an authenticated government-to-GeoNames identity.

Source target for the next stage: Azerbaijan government 2025 GeoJSON 'Cities
and administrative territorial units of Azerbaijan', in the companion
original-source-acquisition.json. Download original GeoJSON bytes, record
SHA-256 and licence, inspect the actual schema/coordinates/stable IDs, and
then conduct a separate administrative crosswalk; no original GeoJSON file
was downloaded in this implementation.
