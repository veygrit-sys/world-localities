# Data attribution and redistribution

Original program code uses MIT. This is not a blanket license for data, model
inputs, search indices, or other people's software. Preserve this file and the
source metadata with each data release. The initial bundled snapshots were
downloaded on 2026-09-25; later country additions retain their own observation
dates. Source publication and reference dates are recorded separately in the
manifests.

## Worldwide country/subdivision catalogue (added in 0.2)

`artifacts/global-admin.sqlite` and its CSV/JSONL/index exports form a derived
database made available under the **Open Database License 1.0 (ODbL)**. The
original program code remains MIT. Keep the notices and licences of every
component below; the database-level licence does not replace their terms.
Original snapshots, transformation code and a per-file SHA-256 manifest are
included. The daily admin Release also includes `admin-source-snapshots.tar.gz`.

| Component | Upstream terms | Attribution and transformation |
|---|---|---|
| [Countries States Cities Database](https://github.com/dr5hn/countries-states-cities-database) | ODbL 1.0; full text in `third_party/admin/CSC-ODbL.txt` | Darshan Gada and CSC contributors. Complete countries and states JSON snapshots at a single pinned commit, native/translations preserved. Deduplication requires matching jurisdiction, code and Wikidata ID. Four coextensive territory references are preserved separately, not mistaken for internal subdivisions. Code crosswalks and specific name/type/parent corrections are recorded. No upstream endorsement. |
| [pycountry / iso-codes](https://github.com/pycountry/pycountry) | LGPL-2.1-only package; full text in `third_party/admin/ISO-reference-LGPL-2.1.txt` | pycountry and Debian iso-codes contributors. Unmodified ISO 3166-1 and 3166-2 JSON reference inputs are included; country-universe check, explicit code crosswalks, parent repair and selected missing subdivisions. This is an OSS reference snapshot, not a freshly licensed or independently verified ISO official database. Known older NO/VN entries are not restored. |
| [Unicode CLDR](https://cldr.unicode.org/) | Unicode-3.0; full text in `third_party/admin/Unicode-3.0.txt` | Copyright Unicode, Inc. Stable release selected from the official repository. Subdivision and country name fields extracted with language and draft status; official-language metadata supports labels. Draft/provisional translations are searchable and are not relabelled as verified official names. |
| GeoNames ADM1 and selected country dumps | CC BY 4.0 | © GeoNames. ADM1 evidence for CK, MO, MP, PM, SJ and TK fills whole jurisdictions missing from CSC. Their native/alternate-name language tags are not guessed. Macau's traditional/statistical parish classification is flagged. |
| Japan Post national postal / romanization CSV | Provider postal-data reuse statement, as below | All 47 prefecture names and kana, separately dated romanization, and prefecture/postcode associations. A prefecture/postcode association is not a point-address or deliverability check. |
| pypinyin | MIT software; upstream pronunciation notices apply | Generated Mandarin readings for available CN/TW/HK/MO Chinese labels. Marked unreviewed. Japanese Kanji and Korean names never receive Mandarin readings. Cantonese/Jyutping enrichment is not implemented. |
| koroman 1.0.16 | MIT software, Donghe Youn (Daissue) | Korean Romanization-based generated search names. Version pinned; not official or reviewed English names. See the Korea notice below. |
| [commerceguys/addressing](https://github.com/commerceguys/addressing) | MIT; full text in `third_party/admin/CommerceGuys-MIT.txt` | Copyright (c) 2014-2023 Bojan Zivanovic and contributors. A pinned `AddressFormatRepository.php` is parsed without execution to extract State-field usage, requiredness and label type. Generic fallback is explicit. This is postal-format evidence, not proof of absent administrative units. |
| [INSEE Code officiel géographique 2026](https://www.insee.fr/fr/information/8740222) | LicenseRef-INSEE-Reuse: preserve integrity and precise attribution under INSEE's [data reuse terms](https://www.insee.fr/fr/information/2381863) | INSEE, COG as of 2026-01-01, arrondissement CSV. Three records for department 973 (French Guiana). INSEE codes are kept separate from ISO codes; proper names are preserved for English display without claiming an official English translation. |
| [Virgin Islands Government, Sister Islands Programme Unit](https://www.gov.vg/sister-islands-programme-unit) | Factual extraction; government article text is not redistributed | The names Anegada, Virgin Gorda and Jost Van Dyke and their documented district-service role are curated facts. These three service districts are not claimed to partition the entire territory or to be ISO subdivisions. Review date is retained in `config/admin_policy.json`. |

The separately released `admin-lexical-ranker.json` is trained on name strings
from this derived database; retain the same source notices, training manifest
and ODbL-compliant database access when distributing the model with this
catalogue. No claim is made that a software licence erases database obligations.

Government sources linked in `config/admin_policy.json` support factual
corrections. Those articles are not copied into the dataset. The 250 country and
territory entries include separately labelled user-assigned XK; that code is
not described as an assigned ISO 3166-1 code. Coding/territorial views do not
assert sovereignty. Empty subdivision lists are recorded as source gaps or
non-enumeration, not proof that no administration exists.

The prepopulated `registry/` JSON and CSV files (added in 0.4) are exports of
the same ODbL derived database, including selected multilingual labels,
readings and postcode associations. Preserve this file, `third_party/admin/`,
and `registry/manifest.json` when redistributing them. Full alias/provenance
records and exact source bytes are available through the reproducible build
and admin data Release. Postal formatting evidence does not certify delivery.

## Locality catalogue added in 0.3

The separate locality database uses CSC's `json-cities.json.gz` release asset
and a states file pinned to the release commit. It contains all 152,970 source
rows, including administrative, unclassified and non-address rows; downstream
candidate classification is documented in `config/locality_policy.json`.
The source is ODbL-1.0. The derived locality database, name index and changes
are distributed with those terms and the source notices above. Original
language labels are retained; identical spellings share search postings.
Generated Mandarin pinyin is unreviewed. CSC translations and native labels
are not all independently verified.

Japan Post's national municipality/postal labels contribute a separate 1,892
records, kana readings, corresponding romanization where matched and 120,874
municipality/postcode associations. Its reuse statement above applies, and
this wider extraction is separate from the four-city address preview below.
Designated-city wards occur in these postal labels. Neither source entity
identity nor legal municipality status is inferred merely from name matches.

The compact administrative anchors derive from the worldwide catalogue and
retain its upstream source hash, language labels and original notices.
`locality-source-snapshots.tar.gz` makes the original city, administrative and
postal bytes, curation policies and licence files available for reproduction.
MIT code licensing does not supersede data terms.

## Japanese official-code hierarchy added in 0.5

`japan-registry/`, `artifacts/japan.sqlite`, the matching exports and test
excerpts add Digital Agency Japan Address Base Registry (ABR) prefecture and
municipality master data. Attribution: **「アドレス・ベース・レジストリ」
（デジタル庁）を加工してAddress Foundation作成**.

Sources: [ABR catalogue](https://dataset.address-br.digital.go.jp/api/feed/dcat-us/1.1.json)
and [ABR terms](https://www.digital.go.jp/policies/base_registry_address_tos).
The selected catalogue resources declare CC BY 4.0; the ABR site terms state
PDL 1.0 unless otherwise specified. Both the resource-specific licence URL
and a copy of the site's terms are retained with the downloaded snapshot.
Preserve attribution, indication of processing, and applicable source terms.
No official endorsement is implied.

Processing: validate six-digit LG check digits, retain official prefecture,
county, city and ward components, resolve the structured city references,
link exact five-digit postal municipality identifiers, index kana/romanized
names, and retain unmatched source rows separately. Three source-observed
postal name variants are recorded in `config/japan_policy.json`. Source
effective dates are not independently verified legal establishment dates.
Romanization is labelled ja-Latn, not English translation. Test fixtures
contain attributed excerpts with intentionally shortened postal lists.

Japan Post reuse conditions below continue to apply. The shared worldwide
prefecture registry and its identifiers retain the existing notices above.
The combined derived database continues under ODbL-1.0; this does not replace
ABR, Japan Post or other component conditions. Program code remains MIT.
The daily package includes `japan-source-snapshots.tar.gz` and notices.

## Address preview retained from 0.1 (source details)

| Source in this preview | Terms | Attribution and changes |
|---|---|---|
| GeoNames admin1CodesASCII and cities15000 | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) per current [extract README](https://download.geonames.org/export/dump/readme.txt) | © GeoNames, [geonames.org](https://www.geonames.org/). Selected fields, names and aliases normalized into a search database. No completeness or accuracy warranty. |
| France Base Adresse Nationale (BAN) | [Licence Ouverte / Open Licence 2.0](https://www.etalab.gouv.fr/licence-ouverte-open-licence/) per [official catalogue](https://www.data.gouv.fr/datasets/base-adresse-nationale) | Base Adresse Nationale, IGN / participating communes. Subset: department 75 rows with postal code 75001; transformed to streets, localities, address points and postcode links. Does not imply endorsement. |
| Japan Post downloadable postal CSV and romanization CSV | LicenseRef-JapanPost-Postal-Data: provider-specific reuse statement; not CC0 or MIT | 日本郵便「郵便番号データ」[UTF-8説明](https://www.post.japanpost.jp/service/search/zipcode/download/utf-readme.html)・[ローマ字説明](https://www.post.japanpost.jp/service/search/zipcode/download/readme_ro.html)。郵便番号データに関する使用・再配布条件に従う。自治体コード01101/13102/13206/34208を抽出。町域の例外表現・各種フラグを保持。ローマ字表は別の更新日であり完全に対応しない。 |
| Wikidata Q46913 / Q47974 structured labels and aliases | [CC0](https://www.wikidata.org/wiki/Wikidata:Licensing) | Wikidata contributors. Source revision and source modification time preserved. This preview contains two entries only. |
| Pinyin generated in this preview | Generated lookup aliases; underlying tool/data notices still apply | [pypinyin](https://github.com/mozillazg/python-pinyin), MIT software, includes upstream pronunciation data. Generation is marked unreviewed. Do not describe these pronunciations as officially verified. The pypinyin distribution is installed separately, not vendored. |

The lexical model was trained from these source-derived name strings using
synthetic queries. Its release includes the training manifest and these
attributions. It is not a standalone globally validated address model.

## BAN department 75 observation stage (v0.8)

Source: Base Adresse Nationale (BAN), operated and distributed by IGN,
with addresses contributed by the competent communes. The
[official catalogue](https://www.data.gouv.fr/api/1/datasets/base-adresse-nationale/)
declares `lov2`, [Licence Ouverte / Open Licence 2.0](https://www.etalab.gouv.fr/licence-ouverte-open-licence/).
Attribution: Base Adresse Nationale, IGN / contributing communes; department
75 CSV source timestamp 2026-09-25T03:36:38+00:00. Source URL:
[adresses-75.csv.gz](https://adresse.data.gouv.fr/data/ban/adresses/latest/csv/adresses-75.csv.gz).
The reviewed compressed source SHA-256 is
`93c9940934341a9f25bac1fc7fa13f9a17fac53574d92d94d4b7041d026a7d6f`.

This addition captures all 152,628 rows in that department export, rather
than the earlier v0.1 subset limited to postal code 75001. It is not a
France-wide address import or a count of unique real-world addresses.
The 152,625 source native IDs include three IDs with two positions each;
all rows and the original postal claims are retained. Changes consist of
parsing address components, composing Address1 from source number/suffix/street,
adding immutable content hashes and release observations, and recording
separate, versioned typed-code links to INSEE COG and locality-level postal
compatibility checks. No provider endorsement or deliverability is implied.

The linked stage reuses the official FR hierarchy, La Poste associations and
worldwide registry identifiers. Their separate notices below and above still
apply; the combined derived database remains under ODbL-1.0. This does not
change the BAN source's Open Licence 2.0 or the MIT licence for program code.
The full stage package preserves the raw BAN and catalogue-licence snapshots,
the stage SQLite database with source and reconciliation history, the linked
official FR database, current-observation and audit-event JSONL files,
manifests, checksums and these notices. The checked-in ten-row sample is a
bounded excerpt under the same source terms and transformation notice.
The separate `official-source-snapshots.tar.gz` also carries the original FR
inputs, worldwide anchor snapshot and third-party notices used by the pinned
official database; its contents are checked against that official manifest.

## Official France, US and Italy country adapters (v0.6–v0.7)

Source: Insee, Code officiel géographique 2026, reference geography at
2026-01-01. The selected commune, department and region tables come from
[the official COG page](https://www.insee.fr/fr/information/8740222).
[Insee legal notices](https://www.insee.fr/fr/information/2008466) identify
Licence Ouverte / Open Licence 2.0 for statistical information. Cite Insee,
retain the known update/reference dates, and do not alter the meaning or
misrepresent the transformed data. The download did not provide a
Last-Modified header; observation time is not substituted for that date.

Source: La Poste, Base officielle des codes postaux, source HTTP timestamp
2026-09-08. The [official catalogue](https://www.data.gouv.fr/api/1/datasets/base-officielle-des-codes-postaux/)
declares `lov2` (Licence Ouverte 2.0). The current data endpoint is on
`data.laposte.fr`. We join the original INSEE codes, deduplicate associations,
and label any aggregation via a COG parent separately. Postal records outside
the selected COG table are preserved as unmatched observations. Neither the
postal provider nor Insee endorses this derived database.

Source: U.S. Census Bureau, 2026 Gazetteer Files: states, counties, places,
and county subdivisions, source HTTP timestamps 2026-09-08.
[Source](https://www.census.gov/geographies/reference-files/time-series/geo/gazetteer-files.html),
[record layouts](https://www.census.gov/programs-surveys/geography/technical-documentation/records-layout/gaz-record-layouts/gaz26-record-layouts.html),
and [Census geographic materials reproduction/citation statement, section 1.2](https://www2.census.gov/geo/pdfs/maps-data/data/tiger/tgrshp2023/TGRSHP2023_TechDoc.pdf).
U.S. Government works are not subject to U.S. copyright under 17 USC 105;
retain U.S. Census Bureau attribution. This is not a grant for logos,
trademarks or unrelated third-party material. No logos or map imagery are
included. Our transformations add typed identifiers, state/county joins,
selection flags, search aliases and source manifests. Census geographic
roles and functional status codes are preserved. Statistical geography is
not a determination of jurisdictional authority, postal assignment or
deliverability.

Source: Istat, Elenco dei comuni italiani, reference date 2026-02-21,
source HTTP Last-Modified date 2026-02-26. The workbook is linked from
[Istat's administrative-unit code documentation](https://www.istat.it/classificazione/codici-dei-comuni-delle-province-e-delle-regioni/)
and available at its
[permanent download URL](https://www.istat.it/storage/codici-unita-amministrative/Elenco-comuni-italiani.xlsx).
[Istat's legal notice](https://www.istat.it/note-legali/) applies
[Creative Commons Attribution 4.0 International (CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/)
unless otherwise indicated; no different licence was found in this workbook.
Attribution: Istat, Elenco dei comuni italiani, 21 February 2026.
Our modifications add typed identifiers, an explicit 20-region code
crosswalk, current UTS parent links, search aliases and source manifests.
The 7,894 municipality rows and all five UTS types are retained. Historical
province and municipality codes remain separate attributes, including the
Sardinian recoding adopted for statistics from 2026-01-01. Official combined,
Italian and other-language labels are preserved without fabricated English
translations. No CAP postcode mapping is supplied by this adapter.
Retain Istat attribution, the licence link and this modification notice;
do not imply Istat endorsement or impose additional restrictions on the
licensed source material. Source excerpts used in fixtures share this notice.

The original official inputs retain their own terms. The integrated
Address Foundation exports also reuse the worldwide registry identifiers;
the combined derived database remains under ODbL-1.0 with all component
notices above. This does not relabel the original government inputs ODbL
or the combined data MIT. Program code remains MIT. The daily country
packages include the original input bytes, the world registry anchors,
their checksums and this notice. Fixtures contain attributed source excerpts.

## Planned sources, not bundled

- OSM is ODbL; code licenses do not override database obligations.
- Overture licenses vary by theme/source. Divisions are ODbL; address sources
  have individual permissive terms and attributions. Do not relabel all Overture
  data CDLA-Permissive or Apache.
- OpenAddresses publishes source specifications and processed data. Individual
  source data retains original terms; the repository's code license is not a
  blanket data license.
- GeoNames postal files have their own terms; do not assume the gazetteer's
  current CC-BY-4.0 label applies to every postal archive.
- geoBoundaries gbOpen and other product variants must be distinguished.
- Additional dictionaries, model weights, and national postal datasets require
  their own manifests. MIT pypinyin does not make every optional dictionary MIT.

Reference architecture: `docs/architecture_ja.md`. For a future OSM-derived
integrated database, preserve the original inputs and satisfy applicable ODbL
attribution and share-alike requirements. Splitting files alone is not a way to
remove those requirements.

## Brazil IBGE country adapter (v0.9)

Source: Instituto Brasileiro de Geografia e Estatística (IBGE), API de
localidades, UF and município endpoints, observed 2026-09-26. The live API
provides no reference date; observation time is not a legal effective date.
[API documentation](https://servicodados.ibge.gov.br/api/docs/localidades).
The federal open-data framework [Decreto 8.777/2016](https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2016/decreto/d8777.htm),
including its amended article 4, permits reuse of federal data; retain IBGE
attribution. We identify these terms as LicenseRef-BR-Decreto-8777-2016 and
do not substitute a Creative Commons licence. No third-party notices were
present in the selected endpoint responses.

Processing preserves the 27 UFs and all 5,571 endpoint rows, distinguishing
5,569 municipalities from Brasília and Fernando de Noronha. Code joins
check current and available legacy geographic paths. Original names, nested
rows and raw response bytes are retained, including gzip-encoded responses.
No CEP assignments or invented English translations are added. The combined
world-anchor-derived database retains ODbL and component conditions above;
this does not relabel original IBGE data or imply IBGE endorsement.

## Taiwan NLSC and Chunghwa Post adapter (v0.9)

Source attribution: National Land Surveying and Mapping Center, ListCounty and
ListTown1; Chunghwa Post, TOWN_MOI.kml. Reviewed catalogues:
https://data.gov.tw/dataset/101905, https://data.gov.tw/dataset/102011,
https://data.gov.tw/dataset/37759. Their Open Government Data License 1.0
(OGDL-Taiwan-1.0) is https://data.gov.tw/license. Retain attribution and
licence links; no endorsement is implied. The world-anchor-derived combined
database retains its existing ODbL/component conditions.

All 368 localities are joined by both official code namespaces, with county
identities and labels checked. English labels are original postal KML labels.
Pinyin is generated by MIT-licensed pypinyin 0.55.0 and explicitly unreviewed;
it is not an official reading or English translation. Postal codes are only
three-digit delivery areas, never validated full 3+3 addresses. KML HTTP
Last-Modified is 2021-11-26; neither source supplies a legal effective date.
Raw source and metadata are included in the country release.

## Germany: Destatis GV100AD official-code adapter

Source: Statistisches Bundesamt (Destatis), 2026, im Auftrag der Herausgebergemeinschaft Statistische Ämter des Bundes und der Länder. The selected [GV100AD August archive](https://www.destatis.de/DE/Themen/Laender-Regionen/Regionales/Gemeindeverzeichnis/Administrativ/Archiv/GV100ADQ/GV100AD3108.zip?__blob=publicationFile&v=14) contains the reference geography at 2026-08-31; its HTTP Last-Modified timestamp is 2026-07-31T09:26:03+00:00. These are separate dates. The archive's `Hinweise.txt` expressly allows reproduction and distribution, including excerpts, with source attribution. We record this product-specific permission as `LicenseRef-Destatis-GV100-Attribution`, not as an inferred Creative Commons or DL-DE-BY licence. Retain the bundled notice and dataset specification.

Transformations preserve AGS/ARS strings, map all 16 Länder to registered state codes, attach municipality-level rows through official county/state codes and retain eight source types. The 10,943 locality rows comprise 10,747 municipal governments, two inhabited and 194 uninhabited unincorporated areas. We apply the full Bautzen name published in `Hinweise.txt`, retaining the truncated source row and correction provenance. Administration-seat postcodes remain attributes, not complete postal assignments; no English translations are generated. No provider endorsement or deliverability claim is made.

The adapter is pinned to this reviewed August archive: checking it daily does not automatically adopt a later monthly issue. The combined derived database retains ODbL-1.0 and the component notices; the original Destatis inputs retain their own permission. Program code remains MIT. Attributed source excerpts in fixtures share this notice.


## Spain: INE official municipality-code adapter

Source: Instituto Nacional de Estadística (INE), [2026 municipality workbook](https://www.ine.es/daco/daco42/codmun/26codmun.xlsx), [autonomous-community/province crosswalk](https://www.ine.es/daco/daco42/codmun/cod_ccaa_provincia.htm), and [within-year changes](https://www.ine.es/daco/daco42/codmun/codmun_anual.htm). The baseline reference date is 2026-01-01, its published release date 2026-02-04 and its HTTP Last-Modified timestamp 2026-03-13T06:35:44+00:00. Thirteen checked name changes are applied; the latest REL resolution date is 2026-06-15. A resolution date is not asserted to be the legal effective date of a change.

The [INE reuse notice](https://www.ine.es/dyngs/AYU/index.htm?cid=125) applies [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) to INE-origin statistical information unless otherwise indicated. Attribution: Elaboración propia con datos extraídos del sitio web del INE: www.ine.es. Retain the source, supplied update dates, licence link and this processing notice; do not suggest INE participation or endorsement.

Processing preserves the five-character CPRO+CMUN identity and separate source check digit, joins 8,132 municipality roles to 17 autonomous communities, two autonomous cities and 50 provinces, and applies code-checked name changes while preserving original rows and historical aliases. Ceuta and Melilla do not receive invented provinces. Name language is unspecified where the source supplies no language field; no English translations, postal assignments or Address1 data are added. The combined derived database remains ODbL-1.0 with all component notices; original INE data retains CC BY 4.0. Code remains MIT, and fixture excerpts retain this attribution.

## Mexico: INEGI AGEE/AGEM official-code adapter

Source: Instituto Nacional de Estadística y Geografía (INEGI),
[Catálogo Único de Claves de Áreas Geoestadísticas](https://www.inegi.org.mx/app/ageeml/)
and its [documented API](https://www.inegi.org.mx/servicios/catalogounico.html).
The snapshot uses the national state response and all 32 state-scoped municipal-area
responses. The source catalogue period is July 2025. Population and dwelling fields,
where present, cite the 2020 Population and Housing Census; that statistical reference
is not substituted for the catalogue period or a legal effective date.

The [INEGI terms](https://www.inegi.org.mx/inegi/terminos.html) permit copying,
distribution, publication, adaptation, rearrangement, extraction and commercial use
subject to INEGI attribution, identifying the source and update date where possible,
declaring transformations and not implying INEGI endorsement. Attribution:
**Fuente: INEGI, Catálogo Único de Claves de Áreas Geoestadísticas, corte julio 2025;
datos transformados por Address Foundation.**

Processing preserves Spanish UTF-8 names, source rows, five-character AGEM codes and
leading zeros; maps all 32 state codes through an explicit table; and separates 2,462
municipality areas from Mexico City's 16 territorial demarcations. Municipal-seat
codes/names remain attributes rather than municipality aliases. No English translation,
postal assignment or Address1 record is added. The Servicio Postal Mexicano catalogue
is not redistributed by this adapter. The combined derived database retains ODbL-1.0
and other component notices; original INEGI data retains its own terms. Code remains MIT.

## Canada: Statistics Canada 2025 CSD adapter

Source: Statistics Canada, [2025 Census Subdivision Boundary File](https://www150.statcan.gc.ca/n1/pub/92-162-g/92-162-g2025001-eng.htm), released June 18, 2025 with geographic reference date January 1, 2025. The national feature service declares and supplies all 5,054 census subdivisions. The associated [type table](https://www150.statcan.gc.ca/n1/pub/92-162-g/2025001/tbl/tbl4.2-eng.htm) defines the complete CSDTYPE distribution. Census subdivisions include municipalities and statistical equivalents; this derived grouping does not replace provincial, territorial or federal legal status.

The [Statistics Canada Open Licence](https://www.statcan.gc.ca/en/terms-conditions/open-licence) grants worldwide, royalty-free, non-exclusive rights to use, reproduce, publish, freely distribute or sell the information and value-added products, subject to accurate reproduction, attribution and no implied endorsement. Required value-added notice: **Adapted from Statistics Canada, 2025 Census Subdivision Boundary File, reference date January 1, 2025. This does not constitute an endorsement by Statistics Canada of this product.** Government symbols and logos are not included.

Processing preserves seven-character CSDUID strings, exact PRUID/CDUID ancestry, source names, type codes and raw rows; maps the 13 PRUIDs to existing registered province/territory anchors through an explicit code table; and marks unorganized/statistical areas separately from default address candidates. It does not assign guessed name languages, translations, postal codes, streets or address ranges. The combined derived database retains ODbL-1.0 and other component notices; the original Statistics Canada information retains its Open Licence. Program code remains MIT.

## United Kingdom: ONS May 2026 local authority lookup

Source: Office for National Statistics, [Ward to Local Authority District to CTYUA to Region to Country (May 2026) lookup](https://www.data.gov.uk/dataset/45aa6dad-4337-4947-9ad0-0a48a8b6fa35/ward-to-local-authority-district-to-ctyua-to-rgn-to-ctry-may-2026-lookup-in-the-uk), with geographic reference date 7 May 2026 and catalogue update on 3 September 2026. The adapter selects distinct LAD and parent-code columns from the nationwide table, and crosschecks all 361 LAD identities and names against the separate ONS May 2026 LAD BUC boundary product's attributes. Geometry and ward rows are not imported into the locality registry.

The [ONS geographical licensing page](https://www.ons.gov.uk/methodology/geography/licences) supplies non-postcode/non-UPRN lookup products under the [Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/). Required attribution: **Source: Office for National Statistics licensed under the Open Government Licence v.3.0**. For the independent boundary-product attributes also retain: **Contains OS data © Crown copyright and database right 2026**. No endorsement is implied. Original ONS material remains subject to OGL; existing registry anchors and the combined derived database retain their component notices and ODbL obligations. Program code remains MIT.

Processing preserves nine-character GSS codes and source names, including official Welsh alternatives; maps four constituent-country codes explicitly to existing registered anchors; and distinguishes English statistical regions, shire counties and LAD types. A CTYUA code identical to a LAD denotes two source roles of the same area and never creates a second government or self-parent. Main-name language tags are not inferred from the metadata interface language. The data does not supply all settlements, parish councils, postal towns, postcode assignments or street/house-number addresses.

No ONS postcode or UPRN dataset is redistributed here. ONS notes separate commercial-use licensing for Northern Ireland postcode data beginning BT. OS Open Names is recorded only as a future Great Britain street/place-name source candidate, excluding Northern Ireland; no OS Open Names data is included in this release.

## Australia: ABS 2025 Local Government Areas

Source: Australian Bureau of Statistics, [Local Government Areas, 2025](https://www.abs.gov.au/statistics/standards/australian-statistical-geography-standard-asgs/edition-3-july-2021-june-2026/non-abs-structures/local-government-areas), using the national Mesh Block allocation workbook and GDA2020 boundary attributes. The source period is 2025; the release page identifies a 22 July 2025 release and a 21 July 2026 correction to the Cocos (Keeling) Islands state/territory attributes.

The [ABS copyright statement](https://www.abs.gov.au/website-privacy-copyright-and-disclaimer) makes ABS website material available under Creative Commons Attribution 4.0 unless an identified exclusion applies. Attribution: **Australian Bureau of Statistics, Australian Statistical Geography Standard Edition 3, Local Government Areas 2025; adapted by Address Foundation.** No ABS logo or endorsement is included. Original ABS material remains CC BY 4.0; existing registry components and the combined database retain their own notices and ODbL obligations. Program code remains MIT.

Processing preserves all 567 source codes and exact state-code membership, independently crosschecks allocation and boundary attributes, and distinguishes 542 LGAs, six unincorporated areas and 19 non-spatial balancing codes. ABS states that these boundaries approximate gazetted LGA boundaries using Mesh Blocks and are for statistical purposes; this registry does not relabel them as legal cadastral boundaries. It does not load Postal Areas, delivery postcodes, street names, premises or Address1 records.

## Korea: MOIS legal-code system and MOLIT national legal-dong file

Sources: Ministry of the Interior and Safety (MOIS), Administrative Standard Code Management System, [legal-code dataset catalogue](https://www.data.go.kr/data/15077871/openapi.do), retrieved from the public code.go.kr bulk download; and Ministry of Land, Infrastructure and Transport (MOLIT), [national legal-dong CSV, 2026-06-30 edition](https://www.data.go.kr/data/15063424/fileData.do). Both official catalogue entries explicitly state **이용허락범위 제한 없음** (unrestricted use). The MOIS entry identifies its dataset as the current codes provided by code.go.kr. The local identifier `LicenseRef-KR-PublicData-Unrestricted` records this dataset-specific permission, not a claim of MIT, CC0 or blanket KOGL coverage for the websites. Attribution: **Source: MOIS Administrative Standard Code Management System and MOLIT national legal-dong data; selected and adapted by Address Foundation, observed 2026-09-26.** No endorsement is implied.

The live master has 53,387 current/withdrawn rows; the MOLIT file has 20,561 rows. Current selected sido/sigungu codes and names are crosschecked, with the documented Sejong duplicate representation retained separately. MOLIT republishes processed MOIS codes and is not an independent legal authority for the same facts. Source bytes, catalogue permission pages and their SHA-256 hashes are retained in snapshot metadata. The unit fixture is a derived national sido/sigungu subset with five withdrawn examples, under the same data permission. The selected 253 withdrawn historical rows remain outside the current search registry; no successor is inferred from a similar name.

MOIS board notices about the July 2026 and Hwaseong changes are factual reference links only. Their attachments, government logos, and unrelated website material are not bundled or assigned a KOGL licence. The original data retains its provider terms; the existing registry and combined derived database retain their component notices and ODbL obligations. Program code remains MIT.

Search enrichment uses [koroman 1.0.16](https://github.com/gerosyab/koroman), MIT, Copyright (c) 2025 Donghe Youn (Daissue). Its dependency distribution retains the upstream licence; no upstream implementation is copied into the adapter. The model records library version, disabled mutable dictionaries, a suffix glossary, input text, `official=false` and `reviewed=false`. Romanized proper-name stems with translated administrative types are generated English display aids, not government-published English names. Hangul is preserved; no guessed Hanja, Japanese reading or Mandarin pinyin is attached. Postal assignments and Address1 are not included; Korea Post and Juso pages are future-source references only.
