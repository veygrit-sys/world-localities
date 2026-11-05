# Western Asia administrative-source candidate crosswalk

Scope: SA, BH, QA, OM, PS. The JSON contains 52 curated public reference names from government/statistics material, NOT original complete official datasets. Source URLs, snapshot years, and the exact intended GeoNames admin level are recorded per country.

Candidate name matches require human review and explicit official administrative ID evidence; no name match is automatically verified. GeoNames IDs are immutable. Palestine is special: GeoNames ADM1 represents the West Bank / Gaza Strip grouping, while PCBS governorates are compared at ADM2.

Official postal codes/Anwani locators have not been ingested. Do not fabricate postcode joins from names, geographic proximity or numeric prefixes. The source links in the JSON are leads to original datasets; bulk acquisition, licensing, checksums, versioning and code assignments remain separate gates.

Reproducible audit: python scripts/western_asia_admin_crosswalk.py report --country all
Unit tests: python -m unittest tests.test_western_asia_admin_crosswalk -v

Next: acquire original MOI Oman 2025 governorates/wilayats XLSX; Palestine PCBS locality and government P3/P7 CSVs; Bahrain geographic blocks; Saudi GEOSA/SPL reference and Qatar official municipality/zone tables. Review source licences and capture SHA-256 before postal or locality mapping.

## Confirmed PCBS governorate statistical codes (distinct from postal codes)

The PCBS *Palestinian Localities Guide 1997* (published December 1999), printed
page 10, explicitly defines a 2-digit governorate code as the first two digits
of a 6-digit statistical locality code. The 16 governorate codes are
01, 05, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75.
We preserve the leading zero for Jenin (01). Source:
https://www.pcbs.gov.ps/Downloads/book508.pdf

The function `inspect_pcbs_locality_code("602825")` identifies prefix 60 (Gaza)
as a **format-only** interpretation, not official confirmation that a particular
locality exists or that it is geographically assigned. A 2021 PCBS published
Gaza locality table lists code 602825 for Gaza, providing an independently
documented example: https://microdata.pcbs.gov.ps/statisticsIndicatorsTables.aspx?lang=en&table_id=708 .
Other sample values used in unit tests are published by the relevant PCBS
tables, not a comprehensive locality dataset.

**Crucial:** PCBS numeric statistical code `602825` is not Palestine postal
code `P6100154`. Neither may be derived from the other. Do not infer a
geographic/geonames identity from a valid prefix alone.
