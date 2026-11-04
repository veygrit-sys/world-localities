# Source attribution and changes

Source: **Postcode Dataset**, Government of Malaysia, data.gov.my.

Original data source identified by the catalogue: **Malaysian Communications and Multimedia Commission**.

- Catalogue: https://data.gov.my/data-catalogue/poskod
- CSV: https://storage.data.gov.my/dictionaries/postcodes.csv
- Catalogue basis: June 2026; catalogue last updated 2 August 2026, 12:00 +08:00.
- Retrieved: 4 November 2026; exact timestamp, HTTP Last-Modified, byte length and SHA-256 are in `sources.json`.
- Licence declared by the official catalogue: **Creative Commons Attribution 4.0 International (CC BY 4.0)**, https://creativecommons.org/licenses/by/4.0/ .

The original CSV is retained without modification in `sources/postcodes.csv`.

Changes made by this project: lossless row extraction; five-digit postcodes retained as strings; source-qualified internal observation and association IDs added; original city/state strings retained; separate NFC/whitespace comparison columns added; deterministic gzip CSV output and integrity/count metadata generated.

No official endorsement is implied. These are source postcode/city/state associations. No claim is made that the data describes every street, building, premise, current address, or deliverable address. The official catalogue describes annual compilation and warns that changes may not be immediately reflected. Download and transformation do not remove that limitation.
