# Postal source notices

Separate source terms remain applicable; this inventory does not replace them.

## GeoNames

Postal observations © [GeoNames](https://www.geonames.org/), licensed under
[Creative Commons Attribution 4.0](https://creativecommons.org/licenses/by/4.0/).
The captured `sources/geonames/20261118/readme.txt` and directory listing accompany
the unmodified `allCountries.zip` archive. The inventory is a derived count and
classification, with no added accuracy, timeliness or completeness warranty.
Stage two also retains the unmodified CA/GB/NL complete-length GeoNames archives
under `sources/geonames/20261118-full/`. Classification and counts are derived;
the source files themselves have not been edited. Complete length does not imply
current assignment or nationwide completeness.

### GB complete-length archive

The GeoNames README reports Royal Mail copyright and database right 2022.
Its postal source table reports Royal Mail copyright and database right 2010–2026.
Both declarations are preserved with their respective source references; these
dates are not represented as a verified data-effective date.

For upstream Code-Point Open attribution, retain:

- Contains OS data © Crown copyright and database right 2026.
- Contains Royal Mail data © Royal Mail copyright and Database right 2022; 2010–2026 as reported by GeoNames.
- Contains National Statistics data © Crown copyright and database right 2026.

[OS attribution guidance](https://www.ordnancesurvey.co.uk/products/product-support)
and [Open Government Licence](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/)
remain applicable to the upstream OS data. The captured product is the GeoNames
archive, not a direct download of the OS source. Northern Ireland coverage has
not been established from this capture.

## Japan Post

The existing unmodified UTF-8 ZIP is referenced at
`../registries/official/JP/sources/postal-utf.zip`, under
[Japan Post's terms](https://www.post.japanpost.jp/service/search/zipcode/download/utf-readme.html).
Original metadata remains in `../registries/official/JP/sources.json`.
This layer reads the original ZIP and does not copy the ABR/ODbL joined derivative.

The additional unmodified 2026-10-30 normal and business/PO-box ZIPs are stored at
`sources/japanpost/20261030/`. The business format and its exclusions are described
by [Japan Post](https://www.post.japanpost.jp/service/search/zipcode/download/office/readme.html).
The September normal snapshot remains stored as history and is not selected for
default lookup after this update.

## Taiwan

The existing `../registries/official/TW/postal_links.csv` prefix projection remains
under Taiwan Open Government Data License, version 1.0. Original attribution,
metadata and limitations remain in `../registries/official/TW/sources.json`.

## Additional official publications captured 2026-11-18

The 13 snapshots under `sources/official/20261118/` preserve the downloaded byte
images using lossless gzip. Both stored and original sizes and SHA-256 hashes,
provider names, public references and extraction limitations are recorded in
`sources.json` and `stage3-review.json`. The extraction and catalogue are derived
work; official publication does not establish nationwide completeness or current
assignment of every listed code.

- Namibia: [NamPost postal-code directory](https://www.nampost.com.na/postal/postal-codes).
  The list covers postal infrastructure, including offices and boxes.
- Kosovo: [Posta e Kosovës postal-code list](https://postakosoves.com/en/orari-dhe-kodet-postare/kodet-postare/).
- Bosnia and Herzegovina: [postal-office directory](https://www.post.ba/media/files/popis_ureda.pdf),
  listing BHP/HP/PS operators. Closure symbols are not reliably available in the
  extracted text, so this snapshot is archived and excluded from default lookup.
- Montenegro: [Pošta Crne Gore office directory](https://www.postacg.me/centar-za-korisnike/lokacije-poslovnica/).
  The snapshot is the read-only response used by the public directory frontend.
- Cambodia: [MEF DataEF / MPTC postal-code dataset](https://data.mef.gov.kh/datasets/pd_697c1a83ed95920007af6a15).
  Nine public API responses are retained, including their byte and hash receipts.
- Laos: [Lao Post postal-code page](https://laopost.com.la/about/postcode).
  Sixteen public AIF-hosted API responses are retained, sorted by source ID to
  avoid unstable postcode pagination. Original Lao and English labels remain.

For these six providers, a specific redistribution licence was not confirmed.
Original rights remain with the providers; public access is not represented as
a Creative Commons or uniform open-data licence. Cambodia and Lao/AIF footer
rights declarations remain in the captured evidence. No ownership of the source
publications is asserted by this repository.

Uzbekistan: the [LexUZ official postal-index legislation](https://lex.uz/ru/docs/6350526?otherlang=4)
was registered on 2023-01-13, number 3414. The Russian-language assignment tables
are selected once; the parallel Uzbek tables and routing masks are not counted
again. Article 8 of the [copyright law](https://lex.uz/acts/1023494) excludes official
documents and their official translations. This is not labelled a CC licence.

Mauritius: six CSV publications from the [government data portal](https://data.govmu.org/)
cover Mauritius, Rodrigues and Agalega. Their individual dataset/resource URLs
are retained in `sources.json`. The portal declares
[Creative Commons Attribution-ShareAlike 4.0](https://creativecommons.org/licenses/by-sa/4.0/).
Retain attribution to the Mauritius government portal and the Ministry of Digital
Transformation, and the applicable ShareAlike terms when sharing adapted data.
Three-column and four-column publications are kept separately. The source value
`712547` is retained as an anomaly and not corrected by inference. A metadata
modification date alone is not represented as proof of newer underlying data.
