# Western Asia administrative-source candidate crosswalk

Scope: SA, BH, QA, OM, PS. The JSON contains 52 curated public reference names from government/statistics material, NOT original complete official datasets. Source URLs, snapshot years, and the exact intended GeoNames admin level are recorded per country.

Candidate name matches require human review and explicit official administrative ID evidence; no name match is automatically verified. GeoNames IDs are immutable. Palestine is special: GeoNames ADM1 represents the West Bank / Gaza Strip grouping, while PCBS governorates are compared at ADM2.

Official postal codes/Anwani locators have not been ingested. Do not fabricate postcode joins from names, geographic proximity or numeric prefixes. The source links in the JSON are leads to original datasets; bulk acquisition, licensing, checksums, versioning and code assignments remain separate gates.

Reproducible audit: python scripts/western_asia_admin_crosswalk.py report --country all
Unit tests: python -m unittest tests.test_western_asia_admin_crosswalk -v

Next: acquire original MOI Oman 2025 governorates/wilayats XLSX; Palestine PCBS locality and government P3/P7 CSVs; Bahrain geographic blocks; Saudi GEOSA/SPL reference and Qatar official municipality/zone tables. Review source licences and capture SHA-256 before postal or locality mapping.
