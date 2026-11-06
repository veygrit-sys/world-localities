# Europe national official address acquisition: Czechia, Serbia, Spain

Status: **actual national-source acquisition and integration tests initiated**, with acceptance conditional on downloaded bytes and successful live checks. A new script or a green synthetic test is **not** a successful national import.

## Authoritative sources, access and rights

| Country | Official source | National source unit | Reuse | What is downloaded by workflow |
| --- | --- | --- | --- | --- |
| CZ | ČÚZK RÚIAN nationwide addresses: https://atom.cuzk.gov.cz/RUIAN-CSV-ADR-ST/RUIAN-CSV-ADR-ST.xml | one monthly national ZIP containing 6,258 municipality CSV members in 2026-10-31; S-JTSK native coordinates | CC BY 4.0, attribution to ČÚZK | Atom feed and ZIP, full CSV record replay, SQLite index if accepted |
| RS | RGZ Address Register: https://data.gov.rs/sr/datasets/adresni-registar/ | national street and house-number exports, **two separate** CSV downloads | Serbian Open Data License; check exact downstream conditions | both direct CSV feeds and actual observed column schemas; join only after schema signoff |
| ES | CNIG CartoCiudad: https://centrodedescargas.cnig.es/CentroDescargas/cartociudad | **52 provincial GeoPackages**, with official layer `portalpk_publi` | compatible with CC BY 4.0, attribution to CNIG/IGN and contributing sources | real official province catalog + a provincial download handshake; complete 52-file ingestion requires confirmed direct access mechanism |

## Exact validations

- Original downloaded bytes get SHA-256 and size receipts, timestamp and final HTTPS origin. New snapshots are never overwritten.
- Czech national ZIP contains municipal CSVs (6,258 in the October 2026 snapshot), each semicolon-delimited CP1250 with documented RÚIAN address id, municipality id, street id, house number, postal code and **S-JTSK** coordinates. Do not mislabel these as latitude/longitude. Reject duplicate IDs and missing required fields; store native string identifiers without deleting leading zeroes. Avoid false cross-source joins.
- Serbian streets and house numbers have separate official IDs. Read the actual file headers before mapping; an unknown schema must fail review, not silently populate wrong columns. Only an exact reviewed source-ID-to-street-ID join may be validated. House numbers can be assigned to temporary and planned buildings/plots; national source presence is not carrier deliverability.
- Spanish CartoCiudad publication is provincial. Every 52 provincial source files must be seen and each actual GeoPackage `portalpk_publi` layer verified to claim **all provided provincial data was processed**. The OGC API and WFS do **not** support complete national bulk enumeration. WFS-only ingestion is not a national dataset.
- Completeness, current-status, independence from source, cross-border delivery and carrier acceptance **remain unverified** even when source-integrity checks pass. Official record-level data and registry-provided postal numbers are not carrier certification.

## Workflow jobs

1. Python 3.11 offline synthetic parsing contracts.
2. CZ monthly national raw ZIP download, source ID and source schema validation, every CSV row indexed; upload audit evidence only.
3. RS national street/house CSV acquisition and actual schema inspection; official address normalization is deliberately **blocked** until production columns are verified.
4. ES official 52-file portal inspection and license/consent handshake; do not bypass login, regional file restrictions or rate limits.

All live jobs preserve a failure log. GitHub PR status and reports must be checked, and country completion must be updated from the actual report rather than assuming that a workflow configuration means its job completed.

## Existing pipeline boundaries

Preserve `scripts/europe_priority_ingest.py`, `scripts/europe_priority_six.py` and `scripts/es_pt_mt_precision.py`. Their previously accepted source data and contracts remain independent. Any new indexed data are separate versioned source layers; raw snapshots are not added to the Git repository by this job.

## Independent acceptance gates still required

- Compare official source declared counts at same vintage, by province/municipality and active/current validity.
- Verify mailing postcode assignments with legally available postal authority evidence and 3rd-party test addresses.
- Evaluate exact street-number existence, historical records and incorrectly geocoded entries with withheld real samples.
- Carrier-specific output mapping and actual API acceptance must be demonstrated separately.

## 2026-11-06 first live-run correction

Official ČÚZK ZIP was acquired from the official Atom stream. An early parser expected one CSV and failed. Its actual file inventory contains 6,258 municipal CSV members named `CSV/20261031_OB_500011_ADR.csv` etc. Parser revised to process every municipal member, require exact code-to-member matching and reject duplicate address IDs. The prior failing run is not counted as an accepted import.

RGZ download from GitHub Actions timed out, and the CNIG download handshake returned HTTP 403 even though the public 52-province catalog was available. These are actual access observations, not claims that the datasets are unavailable generally.
