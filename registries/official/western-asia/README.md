# Western Asia: official reference rules for nine countries

This folder extends the existing GeoNames-based locality archives and bilingual address-format
profiles. It is not a nationwide street/address directory and contains **no imported official
postcodes or building entrances**. Rules reviewed 2026-11-05. The nine countries remain
independently maintained in the JSON source inventory; shared code does not erase country
specificity.

| Code | Format-only capabilities | Source priority | Unverified |
|---|---|---|---|
| TR | 5-digit codes; UPU sublocality suffix (e.g. 06050-01); preserve leading zero | PTT province/district/neighbourhood lookup | Assigned code, province match, complete address |
| CY | 4-digit domestic; CY- prefix for inbound international; Greek/Turkish/English kept distinct | Cyprus Post directory Excel via data.gov.cy, CC BY 4.0 | Excel not downloaded/imported; geographic coverage |
| KW | 5-digit code; keep home block and P.O. box workflows separate | Ministry of Communications lookup by block and box range | Code-to-block/box assignment and freshness |
| AE | No single nationwide postcode format; validate Makani shape; preserve Onwani separately | Dubai Municipality Makani, Abu Dhabi Onwani, Emirates Post | Whether IDs exist, emirate scope, delivery |
| SA | SPL 5 digits, building/additional number 4 digits, short address 4 letters + 4 digits | Saudi Post SPL National Address | Actual address/short code assignment and API rights |
| BH | 3 or 4 digits (UPU range 1XX–12XX), home and P.O. box | UPU Bahrain Post January 2024 | Locality/postcode correspondence, building existence |
| QA | No nationwide postcode requirement; Anwani zone + street + building; P.O. box branch | Qatar Post standards and August 2024 UPU sheet | Numeric plate membership, carrier acceptance |
| OM | 3-digit post office code, P.O. box format; home format provisional | UPU January 2026 and Oman Post | Home delivery and post office code assignment |
| PS | P+3-digit area code or P+7-digit delivery-point structure, never treat placeholders as assigned codes | Palestine Post and UPU May 2025 | Territory-specific acceptance, point assignment |

## Source gates

- The official Cyprus Post XLSX is listed as public under **CC BY 4.0** at
  https://www.data.gov.cy/en/dataset/385 . Fetch, preserve hash and publisher attribution,
  review columns and import as a *separate* versioned official postal reference. The current
  repo does not include the spreadsheet or its rows.
- The PTT public portal at https://www.turkiye.gov.tr/ptt-posta-kodu-sorgulama
  supports province/district/neighbourhood lookup. A bulk redistribution right is not
  established; do not scrape and republish without reviewing terms and acquisition limits.
- The Kuwait Ministry of Communications provides distinct directories for **block** and
  **P.O. Box ranges** at https://www.moc.gov.kw/en/important-links?tab=2 . A numeric
  5-digit match alone is not enough to assert that a box or block is assigned the code.
- Dubai Municipality's Makani is a **10-digit entrance locator**, not a postal code.
  Its public use has attribution/non-sale conditions:
  https://www.dm.gov.ae/open-data2/open-data-for-makani/ .
  Abu Dhabi's Onwani system uses building, street, area and postcode components;
  do not impose a Dubai Makani identifier in Abu Dhabi:
  https://onwani.abudhabi.ae/ .
- UAE postal delivery guidance is available at https://www.emiratespost.ae/faq .
  The 2014 UPU sheet is a historical example, not sufficient evidence that every
  current parcel is delivered only to a P.O. box.

See rules.json for exact source IDs, publication dates, roles and reuse gates.

## Additional official reference guidance (SA/BH/QA/OM/PS)

- Saudi Post SPL specifies six national address components (building number, street,
  district, city, 5-digit postcode, additional 4-digit number) and an optional 4-letter
  plus 4-digit **short address**. A syntactically valid code is not an actual
  registered address: https://portal.splonline.com.sa/en/national-address-1/ .
- Bahrain's UPU sheet (January 2024) describes three- or four-digit postcodes,
  range 1XX–12XX, and home/P.O. Box line orders:
  https://www.upu.int/UPU/media/upu/PostalEntitiesFiles/addressingUnit/bhrEn.pdf .
- Qatar Post's Anwani blue plates record **Zone, Street and Building** numbers;
  these are not interchangeable with a national postcode. Inbound international mail
  has separate DOHA/QATAR conventions. See
  https://www.qatarpost.qa/Home/PostalStandards and
  https://www.upu.int/UPU/media/upu/PostalEntitiesFiles/addressingUnit/qatEn.pdf .
- Oman Post's January 2026 UPU sheet documents a **3-digit post office code** with
  P.O. Box; it does not prove nationwide home street delivery data:
  https://www.upu.int/UPU/media/upu/PostalEntitiesFiles/addressingUnit/omnEn.pdf .
- Palestine Post's May 2025 UPU sheet uses P + 7 digits for delivery point
  structure; Palestine Post also publishes P + 3 digit *area* fallback codes.
  The letters "xxxx" on example templates are placeholders, not verified values.
  See https://www.upu.int/UPU/media/upu/PostalEntitiesFiles/addressingUnit/pseEn.pdf
  and https://www.palpost.ps/home/reports/1254?culture=ar-SA .
- No official source rows were imported; all linked datasets remain behind explicit
  provenance, licensing, and coverage review gates. No carrier deliverability is proven.

## Usage

From the repository root:

    python -m unittest tests.test_western_asia_reference -v
    python scripts/western_asia_reference_cli.py inspect --country TR
    python scripts/western_asia_reference_cli.py validate --country CY --postcode 2008 --direction inbound
    python scripts/western_asia_reference_cli.py validate --country KW --postcode 54404 --block 4
    python scripts/western_asia_reference_cli.py validate --country AE --emirate AE-DU --makani "30032 95320"
    python scripts/western_asia_reference_cli.py validate --country SA --short-address RAGI2929
    python scripts/western_asia_reference_cli.py validate --country BH --postcode 317
    python scripts/western_asia_reference_cli.py validate --country QA --zone 38 --street-number 904 --building-number 15
    python scripts/western_asia_reference_cli.py validate --country OM --postcode 133 --po-box 15 --delivery-mode po_box
    python scripts/western_asia_reference_cli.py validate --country PS --postcode P6100154
    python -m unittest discover -s tests -p 'test_western_asia*' -v

Call addressing.western_asia_reference.validate_western_asia_reference from other
Python code. Response statuses are format_only, format_unverified, incomplete and
invalid_format. Even a format_only result **never asserts existence, official postcode
assignment, building identity, or carrier deliverability**.

## Next source-driven quality gates

1. Pin allowed official source bytes and SHA-256, source date, licence, expected grain,
   record count and localities missing from joins.
2. Join *reviewed* postal/municipal IDs to the existing registries/asia GeoNames IDs
   using a separately auditable mapping. Do not overwrite gn: IDs, and do not turn
   geographic-name matches into confirmed same-entity relations automatically.
3. Run held-out address quality tests for syntax, code/locality association, ambiguity,
   native/English names, precision and carrier-specific acceptance. Record nationwide
   completeness separately for each country and version.
