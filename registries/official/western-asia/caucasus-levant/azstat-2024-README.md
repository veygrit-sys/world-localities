# Azerbaijan official classification: 2024 nationwide source-adapter

On 2026-11-08 the official HTML was acquired and parsed: 6,697 distinct codes, plus one identical repeated source row for 50408028 / Qaralar k. The [saved aggregate audit](../imports/reports/AZ-IABT-2024-audit.json) pins its bytes and SHA-256. Exact repeated rows are counted separately during audit; conflicting names for the same code still fail. Full original redistribution and 2026 freshness remain unverified.

The State Statistical Committee's administrative-territorial classification
(Inzibati Ərazi Bölgüsü Təsnifatı, 2024 / IƏBT) is available at
https://www.azstat.gov.az/tesnifat/cedeveller/arazi.jsp?parm=arazi
with an "Excel" export at
https://www.azstat.gov.az/tesnifat/cedevellerexcel/araziex.jsp?parm=arazi .

Official methodology: https://www.azstat.gov.az/tesnifat/cedeveller/bchaptes.jsp?prkod=03

The official eight-digit code is **not a postcode**. The first 3 digits identify
classification tier 1, positions 4–5 tier 2, positions 6–7 tier 3 and
the final digit is a status code. Do not assume that official prefix
values equal GeoNames admin1_code or ISO 3166-2 values.

Run the offline parser tests:

    python -m unittest tests.test_azstat_2024_official_admin -v

Run controlled **full original-source retrieval**:

    python scripts/azstat_2024_official_admin.py fetch \
      --output /tmp/azstat-2024.html
    python scripts/azstat_2024_official_admin.py audit \
      --source /tmp/azstat-2024.html --min-rows 1000 \
      --geonames --output /tmp/azstat-2024-audit.json

A GitHub Actions source audit is included: it fetches the source to a temporary
runner filesystem and records original byte count, SHA-256, source URL, row
counts, code-part distribution and unreviewed GeoNames candidate counts.
It **does not publish the entire original official dataset or silently change
existing GeoNames records**. The 2024 dataset's 2026 freshness and redistribution
licence have not been independently verified. Until that review, the original
bytes are not checked into this repository; the Actions artifact contains only
the audit summary.

This work establishes a reproducible import path, not verified national
address or postcode coverage. All disputed historical/territorial classifications
remain the publisher's claims and must carry source dates and jurisdiction scope.
