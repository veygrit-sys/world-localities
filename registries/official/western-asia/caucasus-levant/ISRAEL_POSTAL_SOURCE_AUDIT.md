# Israel: historic building/entrance ZIP7 audit and government street IDs

Two sources with different grains are supported **only when raw bytes are supplied and
SHA-256 pinned**. The audited input file is never published or embedded in results.

1. 2020 OData historical ZIP7 (source ID IL-ODATA-ZIP7-2020): third-party
   collection of Israel Post public website address records, circa Sep 2020.
   Fields include LocationID, StreetID, House Number, Entrance, ZIP 5, ZIP 7.
   This is **not a currently authoritative postcode register**. Numeric ZIP7
   must contain exactly seven ASCII digits. Source Excel fields that lost leading
   zeros are flagged rather than silently padded. Duplicate building/entrance
   keys and conflicting ZIP7 assignments are audited.
2. 2026 Population & Immigration Authority streets and synonyms CSV
   (IL-STREETS-2026): government locality/street codes with official/synonym
   names. These are not postal codes, not proof of building existence, and not
   guaranteed to share ID namespaces with the 2020 ZIP7 dataset.

Offline use:

    python scripts/western_asia_israel_postcode_sources.py catalogue
    python scripts/western_asia_israel_postcode_sources.py audit --source-id IL-ODATA-ZIP7-2020 --file /secure/zip-merged.xlsx --sha256 ACTUAL_SHA256
    python scripts/western_asia_israel_postcode_sources.py audit --source-id IL-STREETS-2026 --file /secure/streets.csv --sha256 ACTUAL_SHA256
    python -m unittest tests.test_western_asia_israel_postcode_sources -v

An audited file is never automatically marked as nationally complete, current,
authoritative, government-to-GeoNames verified or carrier-deliverable. The original
download resource URL, publication date and licensing review requirements live
in the source acquisition JSON. Raw originals are not checked into this repository.
Before using a historic ZIP7 record for delivery, get a current postcode
response from Israel Post or an authorized carrier at the correct building entry.
