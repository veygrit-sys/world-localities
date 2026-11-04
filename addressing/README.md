# Worldwide address compatibility layer

This package keeps country and language-specific rendering separate from factual
address verification. It accepts structured components in any mapping order,
normalizes aliases without discarding the original semantics, and renders them
with a pinned country profile.

The compiled profiles cover 251 country and territory codes and 16 source locale
variants from OpenCageData/address-formatting. Reviewed East, Southeast,
Southern, Central and Western Asia, Western, Southern, Northern and Eastern
Europe, Oceania, Northern Africa, Eastern Africa, Middle Africa, Western Africa,
Southern Africa, Northern America, Central America and Caribbean extensions bring runtime
coverage to 558 locale profiles. They contain 542 new locale profiles and 240 reviewed
replacements, including Asian, European, Oceanian, African and American
base-country templates with explicit
Address2/subpremise placement. Those templates target display compatibility.
They are not proof that a postal operator accepts an address, that a street or
premise exists, or that a shipment is deliverable.

Verification levels are separate: format, parsed components, locality, postal,
street, premise, subpremise and carrier/postal-operator deliverability. A higher
claim may only be emitted when evidence for that level is available.

```bash
python -m addressing verify
python -m addressing east-asia
python -m addressing southeast-asia
python -m addressing south-asia
python -m addressing central-asia
python -m addressing western-asia
python -m addressing western-europe
python -m addressing southern-europe
python -m addressing northern-europe
python -m addressing eastern-europe
python -m addressing central-europe
python -m addressing oceania
python -m addressing northern-africa
python -m addressing eastern-africa
python -m addressing middle-africa
python -m addressing western-africa
python -m addressing southern-africa
python -m addressing northern-america
python -m addressing central-america
python -m addressing caribbean
python -m addressing profile --country JP --language ja
python -m addressing render --country JP --language ja \
  --components-json '{"country":"日本","postcode":"1000005","state":"東京都","city":"千代田区","neighbourhood":"丸の内","house_number":"1-1"}'
```

## East Asia native and English output

`east_asia_profiles.json` covers CN, HK, JP, KP, KR, MN, MO and TW. Every
country/area has one default native-language profile and an English profile;
Macao additionally supports Portuguese, while Mongolia keeps Cyrillic and
traditional Mongolian script values distinct. Language-dependent values are supplied
explicitly so that an unverified transliteration cannot silently become an
"English official name". Numeric fields such as postcodes and house numbers are
shared safely. Strict mode refuses output when a required English value is
missing or contains non-Latin letters.

```bash
python -m addressing render-bilingual --country JP --components-json \
  '{"postcode":"1000005","state":{"ja":"東京都","en":"Tokyo"},"city":{"ja":"千代田区","en":"Chiyoda-ku"},"road":{"ja":"丸の内","en":"Marunouchi"},"house_number":"1-1"}'
```

The extension records postal-authority sources and a romanization policy per
country. KP remains explicitly `provisional`; the system does not present that
profile as postal-operator verified. Automatic machine translation is not used
as address evidence.

## Southeast Asia native and English output

`southeast_asia_profiles.json` covers BN, KH, ID, LA, MY, MM, PH, SG, TH, TL
and VN. It provides 14 domestic-language variants and an explicit English
profile for every country. Singapore separates Malay, Simplified Chinese and
Tamil; Timor-Leste separates Tetum and Portuguese. Latin-script domestic values
such as Malay, Indonesian, Filipino and Vietnamese still require an explicit
`en` value and are never relabelled as English merely because the script is
compatible.

Address2 is rendered through the country template. Structured block, entrance,
floor and unit fields are combined into the same subpremise line without being
reported as dropped. Myanmar and Timor-Leste remain `provisional` because the
reviewed public operator material did not expose a complete current bilingual
country template.

```bash
python -m addressing render-southeast-asia --country TH --components-json \
  '{"postcode":"12130","state":{"th":"ปทุมธานี","en":"Pathum Thani"},"road":{"th":"ถนนรังสิต-นครนายก 4","en":"Rangsit-Nakhon Nayok 4 Road"},"house_number":"491"}'
```

The shared localized engine rejects cross-script fallback, missing English
components and non-Latin text labelled as English. Automatic translation or
romanization may propose a candidate in a separate workflow, but it cannot
promote that candidate to verified address evidence.

## Southern Asia native and English output

`south_asia_profiles.json` covers AF, BD, BT, IN, IR, LK, MV, NP and PK. It
provides 11 nationwide domestic-language variants and an explicit English
profile for all nine countries. Afghanistan separates Dari and Pashto; Sri
Lanka separates Sinhala and Tamil. The India profile currently represents the
Union-level Hindi and English path rather than claiming separate coverage for
every state language.

The shared engine validates Arabic, Bengali, Devanagari, Sinhala, Tamil,
Thaana and Tibetan scripts for native-language fields. It also rejects Unicode
bidirectional embedding, override and isolate controls that could disguise an
RTL address value. Numeric house numbers and postcodes remain safely shareable.

```bash
python -m addressing render-south-asia --country IN --components-json \
  '{"postcode":"110003","state":{"hi":"दिल्ली","en":"Delhi"},"city":{"hi":"नई दिल्ली","en":"New Delhi"},"road":{"hi":"अमृता शेरगिल मार्ग","en":"Amrita Shergill Road"},"house_number":"4"}'
```

Nepal remains `provisional`: the public postal material shows a 2025 migration
to federal local-level and ward-level codes, while the older international
country sheet still documents the legacy five-digit form. The renderer keeps
the supplied current code but does not silently convert or certify a legacy one.

## Central Asia native and English output

`central_asia_profiles.json` covers KG, KZ, TJ, TM and UZ. It provides nine
script-qualified domestic-language variants and a separate English profile for
all five countries. Kyrgyzstan, Kazakhstan and Tajikistan keep their national
language and Russian values distinct even where both use Cyrillic. Uzbekistan
supports explicit `uz-Latn` and `uz-Cyrl` inputs through the same national line
ordering, while Turkmen Latin values still cannot silently populate English.

The shared engine validates Cyrillic letters and permits the modifier-letter
apostrophes used in Uzbek Latin without weakening mixed-script rejection.
QazPost's seven-character building postcode and the transitional six-digit
numeric code are both preserved; no conversion is attempted. Kyrgyzstan,
Tajikistan and Uzbekistan keep their six-digit code before the locality, while
Turkmenistan keeps its six-digit code on a separate line after locality and
province information.

```bash
python -m addressing render-central-asia --country UZ --components-json \
  '{"postcode":"100123","city":{"uz-Latn":"Toshkent","uz-Cyrl":"Тошкент","en":"Tashkent"},"road":{"uz-Latn":"Amir Temur koʻchasi","uz-Cyrl":"Амир Темур кўчаси","en":"Amir Temur Street"},"house_number":"4"}'
```

Every Central Asia profile carries operator or UPU provenance. The profiles
validate representation and line order only; street, premise, Address2 and
deliverability claims still require evidence at their corresponding validation
level.

## Western Asia native and English output

`western_asia_profiles.json` covers AE, AM, AZ, BH, CY, GE, IL, IQ, JO, KW,
LB, OM, PS, QA, SA, SY, TR and YE. It provides 22 domestic-language variants
and a separate English profile for all 18 countries and areas. Cyprus separates
Greek and Turkish, Iraq separates Arabic and Kurdish, Israel separates Hebrew
and Arabic, and Lebanon separates Arabic and French.

Arabic, Armenian, Greek, Georgian, Hebrew and Latin scripts are validated.
Languages sharing a script remain separate: Iraqi Arabic cannot fill Kurdish,
and Lebanese French or Turkish cannot silently become English. Address2 is
explicit in every national template.

The profiles preserve materially different postal systems: Azerbaijan's
`AZ`-prefixed code, Cyprus's inbound `CY-` prefix, Israel's seven digits,
Palestine's current P-prefixed eight-character code, Oman's standalone
three-digit line, Saudi Arabia's National Address order, and countries whose
reviewed public templates do not use a postcode. AE, IQ, JO, KW, SY and YE are
marked `provisional` because their public country sheets are old, incomplete,
or unavailable; output from those profiles always carries a warning.

```bash
python -m addressing render-western-asia --country SA --components-json \
  '{"postcode":"12643","city":{"ar":"الرياض","en":"Riyadh"},"road":{"ar":"طريق الملك عبدالعزيز","en":"King Abdulaziz Road"},"house_number":"8228","address2":{"ar":"الوحدة 18","en":"Unit 18"}}'
```

## Western Europe native and English output

`western_europe_profiles.json` covers AT, BE, CH, DE, FR, LI, LU, MC and NL.
It provides 16 domestic-language variants and a separate English profile for
all nine countries. Belgium keeps Dutch, French and German distinct;
Luxembourg keeps Luxembourgish, French and German distinct; Switzerland keeps
German, French, Italian and Romansh distinct. Values are never copied across
those languages merely because all use Latin script.

Postal layout follows current operator guidance where available. France places
apartment, floor and staircase information before building and delivery lines;
Belgium keeps a box designator with the thoroughfare and house number; the
Netherlands preserves the official BAG house-number addition on that line.
Austria, Germany, Liechtenstein and Switzerland retain supplied subpremise
information without manufacturing punctuation. Luxembourg's `L-`,
Liechtenstein's `FL-`, Monaco's normal/CEDEX and Dutch alphanumeric postcode
forms are preserved rather than inferred.

All nine profiles have official guidance or operator-derived domestic evidence;
none is marked provisional. These sources establish representation and line
order, not the existence of a street, premise or deliverable subpremise.

```bash
python -m addressing render-western-europe --country CH --native-language fr-Latn \
  --components-json '{"postcode":"1556","city":{"fr-Latn":"Cerniaz VD","en":"Cerniaz VD"},"road":{"fr-Latn":"Rue du Marché","en":"Market Street"},"house_number":"8","address2":{"fr-Latn":"Appartement 2","en":"Apartment 2"}}'
```

## Southern Europe native and English output

`southern_europe_profiles.json` covers AD, AL, BA, ES, GI, GR, HR, IT, ME,
MK, MT, PT, RS, SI, SM and VA. It provides 34 domestic language/script
variants and an English profile for all 16 countries and areas. Bosnia and
Herzegovina, Montenegro and Serbia keep Latin and Cyrillic records distinct;
Spain keeps Spanish, Catalan, Basque, Galician and Occitan distinct. Gibraltar
and Malta reuse their explicit English profile where English is itself a
domestic language.

Country templates preserve the material postal differences. Albania renders
postcode and locality on separate lines. Malta renders locality before its
separate alphanumeric postcode. Croatia preserves a supplied inbound `HR-`
prefix, Greece normalizes an unspaced five-digit code to the documented 3-2
form, and Portugal normalizes seven digits to 4-3. Serbia keeps the five-digit
delivery-office code and separately supplied six-digit `PAK` line distinct.
Italy and Vatican City place staircase, floor and apartment information above
the street line; Spain places staircase, floor and door information on the
street line and province on the following line.

Andorra remains `provisional` because its French and Spanish postal operators
publish opposite street-number orders and the current renderer exposes one
default route per country. San Marino is `source_derived_domestic` from the
current Italian-system specification and an official 47890 address example.
These statuses do not claim street, premise or deliverability verification.

```bash
python -m addressing render-southern-europe --country RS --native-language sr-Cyrl \
  --components-json '{"postcode":"24210","sorting_code":"PAK 456769","city":{"sr-Cyrl":"БАЈМОК","en":"BAJMOK"},"road":{"sr-Cyrl":"Београдска","en":"Beogradska Street"},"house_number":"3"}'
```

## Northern Europe native and English output

`northern_europe_profiles.json` covers AX, DK, EE, FI, FO, GB, GG, IE, IM,
IS, JE, LT, LV, NO, SE and SJ. It provides 32 domestic language variants and
an English profile for all 16 countries and territories. Åland, the Faroe
Islands, Guernsey, Jersey, the Isle of Man, and Svalbard and Jan Mayen remain
independent country-code profiles instead of being collapsed into Finland,
Denmark, the United Kingdom or Norway.

The profiles keep Finnish and Swedish separate in Finland; Faroese and Danish
separate in the Faroe Islands; and English and Irish separate in Ireland.
Norway exposes Bokmål, Nynorsk, Northern Sámi, Southern Sámi and Lule Sámi;
the United Kingdom exposes English, Welsh, Scottish Gaelic and Irish. Jersey
also keeps English, French and Jèrriais values independent. Shared Latin script
never permits one language to silently fill another or English.

Material postal differences are preserved. Åland and the Faroe Islands use
`AX-` and `FO-` postcode forms. Latvia places `LV-` plus four digits to the
right of locality, while Lithuania places `LT-` plus five digits before it.
Ireland keeps Eircode on its own line; United Kingdom and Crown Dependency
postcodes are normalized without losing their separate island/post-town lines.
Norwegian residential-unit numbers remain above the street, Swedish postcodes
use the documented three-plus-two spacing, and SJ follows the Norwegian postal
route with Norway as the international country line. SJ is
`source_derived_domestic`; none of the 16 profiles is marked provisional.

```bash
python -m addressing render-northern-europe --country AX --native-language sv-Latn \
  --components-json '{"postcode":"22100","city":{"sv-Latn":"MARIEHAMN","en":"MARIEHAMN"},"road":{"sv-Latn":"Postgränd","en":"Post Alley"},"house_number":"8"}'
```

## Eastern Europe native and English output

`eastern_europe_profiles.json` covers BG, BY, CZ, HU, MD, PL, RO, RU, SK and
UA. It provides 14 domestic language/script variants and a separate English
profile for all 10 countries. Belarusian and Russian remain separate in
Belarus; Romanian, Russian, Ukrainian and Gagauz remain separate in Moldova.
Cyrillic and Latin values are script-checked, and a shared script never permits
one language to silently fill another or English.

The country templates preserve the important postal differences. Hungary puts
the destination before the street/premise line and its four-digit postcode on
a separate final address line. Belarus and Moldova put the postcode before the
locality, while Russia and Ukraine retain their documented specific-to-general
order. Czech and Slovak postcodes normalize to three-plus-two spacing, Polish
postcodes to two-plus-three with a hyphen, and Moldovan codes to `MD-` plus four
digits. Building, entrance, floor and apartment data is retained through
Address2. Official postal-operator or UPU guidance supports all 10 routes; none
is marked provisional. These profiles validate representation and order, not
street existence, premise existence or deliverability.

```bash
python -m addressing render-eastern-europe --country UA --native-language uk-Cyrl \
  --components-json '{"postcode":"01001","state":{"uk-Cyrl":"Київська область","en":"Kyiv Region"},"city":{"uk-Cyrl":"Київ","en":"Kyiv"},"road":{"uk-Cyrl":"вул. Хрещатик","en":"Khreshchatyk Street"},"house_number":"22","address2":{"uk-Cyrl":"кв. 14","en":"apartment 14"}}'
```

## Central Europe cross-region output

Central Europe is not a separate UN M49 subregion, so `central_europe.py`
defines an explicit nine-country core: AT, CH, CZ, DE, HU, LI, PL, SI and SK.
It is a crosswalk rather than another profile extension. Austria, Switzerland,
Germany and Liechtenstein reuse the Western Europe policies; Czechia, Hungary,
Poland and Slovakia reuse Eastern Europe; Slovenia reuses Southern Europe.
No country template, source record or locale profile is copied.

The crosswalk exposes 12 domestic language/script variants and English for all
nine countries. It therefore preserves Swiss German, French, Italian and
Romansh selection, the Czech/Polish/Slovak postcode rules, Hungary's distinct
line order, Liechtenstein's supplied `FL-` prefix, and Address2 placement from
the authoritative country routes. Croatia and Luxembourg remain available
through their existing Southern and Western Europe registries; they are not
silently included in this deliberately narrow core.

```bash
python -m addressing render-central-europe --country CH --native-language rm-Latn \
  --components-json '{"postcode":"8001","city":{"rm-Latn":"Turitg","en":"Zurich"},"road":{"rm-Latn":"Via da la Staziun","en":"Station Street"},"house_number":"4a","address2":{"rm-Latn":"Abitaziun 8","en":"Apartment 8"}}'
```

## Oceania domestic-language and English output

`oceania_profiles.json` covers all 29 UN M49 Oceania countries and territories.
It exposes 61 domestic language variants and an English profile for every
destination. The profiles reuse the existing `oceania-registry` packs—29
country splits and 46,594 locality records—as candidate locality data rather
than duplicating those records in the address layer.

Postal routing is grouped by the system actually used: Australia Post for AU
and its external territories, NZ Post for New Zealand, USPS forms for AS, FM,
GU, MH, MP, PW and UM, French-overseas forms for NC, PF and WF, and separate
operator formats for the Pacific states. Kiribati's `KI` code, Nauru's
`NRU68`/`NRU70` identifiers and Tuvalu's `TUV` code are included rather than
the older no-postcode fallback data. Postcode checking is syntactic only and
does not claim that a code was assigned to a supplied street or premise.

Address2, floor/unit data, PO Boxes, village, island and archipelago components
remain distinct. Māori, Samoan, Tongan, Tahitian, iTaukei, Bislama and other
Latin-script values do not silently fill English. CK, HM, NU, PN, SB, TK and
VU are marked `provisional` because a complete current public operator template
was not available; that status is returned as a machine-readable warning.

```bash
python -m addressing render-oceania --country NZ --native-language mi-Latn \
  --components-json '{"postcode":"1010","city":{"mi-Latn":"TĀMAKI MAKAURAU","en":"AUCKLAND"},"neighbourhood":{"mi-Latn":"Tāmaki Makaurau Waenga","en":"Auckland Central"},"road":{"mi-Latn":"Te Ara o Kuīni","en":"Queen Street"},"house_number":"12","address2":{"mi-Latn":"Whare 4","en":"Unit 4"}}'
```

## Northern Africa domestic-language and English output

`northern_africa_profiles.json` covers DZ, EG, EH, LY, MA, SD and TN: all
seven countries or areas in the UN M49 Northern Africa group. It exposes 15
domestic language/script variants and a separate English profile for every
destination. Arabic, Kabyle Latin, Standard Moroccan Amazigh in Tifinagh,
French and Spanish values remain language-tagged; sharing a script never fills
an English field, and Tifinagh is checked as its own script.

The extension reuses `africa-registry` rather than copying localities. The
seven-country upstream scope contains 78,724 locality rows. This repository
currently materializes 31,778 rows for DZ, EG, EH, LY, SD and TN; Morocco's
46,946-row source remains explicitly upstream-only. These are candidate
localities, not verified street addresses.

UPU-designated-operator forms are implemented per country: five digits for
Algeria, Morocco and Sudan; Egypt's July 2023 seven-digit code; Tunisia's four
digits; and no invented code for Libya. Address2, building, street, district,
governorate/state and P.O. Box data remain separate. Libya and Sudan are
`provisional` because their public country sheets are dated. Western Sahara is
also `provisional` and sovereignty-neutral: an optional five-digit value is
accepted only when supplied for a Morocco-routed operation, while no operator,
administration or postcode is inferred from a locality.

```bash
python -m addressing render-northern-africa --country MA --native-language zgh-Tfng \
  --components-json '{"postcode":"10000","city":{"zgh-Tfng":"ⵕⵕⴱⴰⵟ","en":"RABAT"},"road":{"zgh-Tfng":"ⴰⵙⵙⵉⴼ","en":"River Avenue"},"house_number":"23","address2":{"zgh-Tfng":"ⵜⵉⴳⵎⵉ 13","en":"Apartment 13"}}'
```

## Eastern Africa domestic-language and English output

`eastern_africa_profiles.json` covers all 22 countries or areas in the UN M49
Eastern Africa group. It exposes 53 domestic language/script variants and a
separate English profile for every destination. Amharic and Tigrinya use an
Ethiopic-script check; Arabic is checked independently; Latin-script domestic
languages still require explicit English values instead of being relabelled.

The extension links to 137,842 upstream locality candidates in
`africa-registry`, of which 113,668 are materialized locally. Madagascar's
24,174 rows remain upstream-only. These locality rows are discovery candidates,
not evidence that a street, building or postal delivery point exists.

Postcode rules follow the reviewed route: Malawi uses six digits and Uganda's
January 2026 form uses five; Djibouti, Ethiopia, Kenya, Madagascar, Mauritius,
Mozambique, Réunion, Tanzania and Mayotte keep their country-specific syntax.
Zambia rejects example five-digit strings because its UPU sheet says actual
codes were unassigned. Seychelles accepts only a supplied legacy `0000`
placeholder during its 2026 addressing-system transition. IO and TF are marked
as special territory/station routes, not ordinary residential coverage.

Address2, building, P.O. Box, neighbourhood, village, island and administrative
hierarchy fields remain distinct. ER, ET, KM, RW, SC, SO, SS, ZM and ZW are
returned as `provisional`, making dated or incomplete public evidence visible.

```bash
python -m addressing render-eastern-africa --country MW --native-language ny-Latn \
  --components-json '{"postcode":"102010","city":{"ny-Latn":"Lilongwe","en":"LILONGWE"},"road":{"ny-Latn":"Msewu wa Mchinji","en":"Mchinji Road"},"house_number":"14","address2":{"ny-Latn":"Chipinda 2","en":"Unit 2"}}'
```

## Middle Africa domestic-language and English output

`middle_africa_profiles.json` covers AO, CM, CF, TD, CG, CD, GQ, GA and ST:
all nine countries in the UN M49 Middle Africa group. It exposes 20 domestic
language/script variants and a separate English profile for every destination.
French, Portuguese, Spanish, Arabic, Sango, Lingala, Kituba, Kongo, Swahili and
Tshiluba values remain explicitly tagged; shared Latin script never fills a
missing English value, and Arabic is checked independently.

The extension links to 101,713 upstream locality candidates in
`africa-registry`, of which 64,477 are materialized locally. The Democratic
Republic of the Congo's 37,236 rows remain upstream-only. Locality candidates
are not evidence that a street, premise or delivery point exists.

The Democratic Republic of the Congo uses a seven-digit code and keeps village,
sector, territory and province separate. Gabon keeps its two-digit postcode and
an independently supplied delivery-office code. Angola, Cameroon, the Central
African Republic, Chad, the Republic of the Congo, Equatorial Guinea and São
Tomé and Príncipe reject invented form-placeholder codes. Address2, premises,
P.O. Box and administrative hierarchy fields remain available in every country
template. AO, CM, GA and TD return a `provisional` warning because their public
country sheets are dated.

```bash
python -m addressing render-middle-africa --country CD --native-language sw-Latn \
  --components-json '{"postcode":"1004131","state":{"sw-Latn":"KINSHASA","en":"KINSHASA"},"road":{"sw-Latn":"Barabara ya Posta","en":"Post Office Road"},"house_number":"1","address2":{"sw-Latn":"Jengo B","en":"Building B"}}'
```

## Western Africa domestic-language and English output

`western_africa_profiles.json` covers BJ, BF, CV, CI, GM, GH, GN, GW, LR, ML,
MR, NE, NG, SH, SL, SN and TG: all 17 countries or areas in the UN M49 Western
Africa group. It exposes 30 domestic language/script variants and a separate
English profile for every destination. French, Portuguese, Arabic, Mooré,
Kabuverdianu, Akan, Upper Guinea Crioulo, Bambara, Hausa, Yoruba, Igbo, Krio,
Wolof and Ewe values are selected explicitly; shared Latin script never fills a
missing English value, and Arabic is checked independently.

The extension links to 192,989 upstream locality candidates in
`africa-registry`, of which 131,560 are materialized locally. Nigeria's 61,429
rows remain upstream-only. These locality candidates support matching and
administrative context but do not prove a street, premise or delivery point.

The postal layer validates ten postcode systems, including Ghana's postcode or
extended digital-address form, Nigeria's six digits and Saint Helena's fixed
`STHL 1ZZ`. Benin and Côte d'Ivoire keep delivery-office codes in
`sorting_code`, never in `postcode`; Mauritania keeps `BP 10000` as a P.O. Box.
Countries documented without postcodes reject invented form placeholders.
Address2, building, road, house number, P.O. Box, village/locality and
administrative hierarchy remain distinct. Eleven countries return a
`provisional` warning because their public country sheets are dated.

```bash
python -m addressing render-western-africa --country GH --native-language ak-Latn \
  --components-json '{"postcode":"GA-183-8164","city":{"ak-Latn":"ACCRA","en":"ACCRA"},"road":{"ak-Latn":"Independence Avenue","en":"Independence Avenue"},"house_number":"14","address2":{"ak-Latn":"Ɔdan B, dan 2","en":"Block B, Floor 2"}}'
```

## Southern Africa domestic-language and English output

`southern_africa_profiles.json` covers BW, LS, NA, SZ and ZA: all five
countries in the UN M49 Southern Africa group. It exposes 22 written domestic
language variants and a separate English profile for every destination.
English, Setswana, Sesotho, siSwati, Afrikaans, German, Oshindonga,
Oshikwanyama and South Africa's 11 written official languages are selected
explicitly. South African Sign Language is documented as an official language
but is not misrepresented as a serializable postal-text profile.

All 19,365 locality candidates for the five countries are materialized in
`africa-registry` and match the upstream snapshot. They support locality and
administrative matching only; they do not prove a street number, premise,
postcode assignment, geocode or deliverability.

Lesotho's three digits, Namibia's five digits, Eswatini's one letter plus three
digits and South Africa's four digits are checked independently. Botswana
rejects invented postcode placeholders. Address2, complex/unit, street and
house number, rural delivery point, village, P.O. Box and Private Bag fields are
preserved. Namibia and South Africa put the postcode on its own line and avoid
inserting a province into the normal coded form. All five countries return a
`provisional` warning because the public country-format sheets are dated; the
current UPU postcode requirement table is stored as separate evidence.

```bash
python -m addressing render-southern-africa --country ZA --native-language zu-Latn \
  --components-json '{"postcode":"1852","postal_city":{"zu-Latn":"LYNDHURST","en":"LYNDHURST"},"road":{"zu-Latn":"Collet Drive","en":"Collet Drive"},"house_number":"449","address2":{"zu-Latn":"1023 Collet Heights","en":"1023 Collet Heights"}}'
```

## Northern America domestic-language and English output

`northern_america_profiles.json` covers BM, CA, GL, PM and US: the five
countries or areas in UN M49 Northern America (021). It intentionally does not
reclassify Mexico, Central America, the Caribbean or Puerto Rico into this
regional profile. Seven written domestic-language variants cover English,
French, Greenlandic and Danish, with a separate English route for every area.
Shared Latin script never fills a missing translation.

The profile links to the non-destructive `north-america-registry` view. Canada
and the United States contribute 72,567 source locality rows after the 1,231
Puerto Rico rows in the US snapshot are excluded from this M49 area. Bermuda,
Greenland and Saint Pierre and Miquelon remain pending locality sources; their
11, 5 and 2 administrative-name seeds are kept separate and never promoted to
street, postal or deliverability evidence.

The postal layer distinguishes Bermuda's two-letter/two-digit home code and
four-letter P.O. Box code, including the repeated delivery-office prefix;
Canada's `ANA NAN`; Greenland's `39xx`; Saint Pierre and Miquelon's fixed
`97500`; and US ZIP or ZIP+4. Address2, secondary units, streets and house
numbers, P.O. Box, Canadian and US rural routes, highway contracts and general
delivery remain explicit fields. Province, territory and state names resolve
to postal abbreviations when the pinned profile contains a match. Greenland
and Saint Pierre and Miquelon are marked `source_derived_domestic` because
their current operator examples supplement inherited or dated UPU sheets.

```bash
python -m addressing render-northern-america --country CA --native-language fr-Latn \
  --components-json '{"postcode":"H3Z2Y7","state":{"fr-Latn":"Québec","en":"Quebec"},"city":{"fr-Latn":"MONTRÉAL","en":"MONTREAL"},"road":{"fr-Latn":"RUE BEAUDRY","en":"BEAUDRY STREET"},"house_number":"123 ½","address2":{"fr-Latn":"SERVICE DU MARKETING","en":"MARKETING DEPARTMENT"}}'
```

## Central America domestic-language and English output

`central_america_profiles.json` covers BZ, CR, GT, HN, MX, NI, PA and SV: all
eight countries in UN M49 Central America (013). It exposes nine domestic
written-language variants and a separate English route for every country.
Belize supports explicit English and Spanish input; the other seven countries
use explicit Spanish and English values. Shared Latin script never fills a
missing translation or relabels a proper name.

The address layer links all eight existing source layers: seven GeoNames-derived
country datasets plus Mexico's separate preserved INEGI snapshot. Together they
contain 59,641 source locality rows. These are not asserted to be unique current
legal places. Six direct-ID postal aliases remain source evidence only and are
not promoted into an official postcode crosswalk or deliverability result.

Belize rejects invented postcode placeholders. Costa Rica, Guatemala, Mexico
and Nicaragua validate five digits; El Salvador validates four. Honduras keeps
the current five-digit numeric form separate from the dated two-letter/four-digit
form. Panama preserves the UPU four-digit transition form and the geolocated
national code introduced in May 2026, classifying syntax without deriving a
coordinate or residence. Address2, exterior/interior numbers, P.O. Box, colonia,
zone, province/department/municipality and descriptive landmark-distance routes
are retained explicitly.

```bash
python -m addressing render-central-america --country MX --native-language es-Latn \
  --components-json '{"postcode":"02860","state_code":"CDMX","city":{"es-Latn":"MÉXICO","en":"MEXICO CITY"},"municipality":{"es-Latn":"Azcapotzalco","en":"Azcapotzalco"},"neighbourhood":{"es-Latn":"Col. Tlatilco","en":"Tlatilco"},"road":{"es-Latn":"Urión","en":"Urion Street"},"house_number":"30","address2":{"es-Latn":"Interior 4","en":"Interior 4"}}'
```

## Caribbean domestic-language and English output

`caribbean_profiles.json` covers AG, AI, AW, BB, BL, BQ, BS, CU, CW, DM, DO,
GD, GP, HT, JM, KN, KY, LC, MF, MQ, MS, PR, SX, TC, TT, VC, VG and VI: all
28 countries or areas in UN M49 Caribbean (029). It provides 36 domestic
written-language variants and a separate English route for every area. Dutch,
Papiamento or Papiamentu, French, Haitian Creole and Spanish values remain
explicit; shared Latin script never fills a missing translation.

The address layer links the existing `caribbean-registry` publication. Its 27
published country layers contain 50,581 entities, 31,942 populated-place
rows, 31,630 address candidates and 55,255 alternate-name rows. Cuba remains
explicitly pending and contributes no locality row. The 196 direct-ID postal
observations are source observations, not an official postcode crosswalk, and
the registry contains no street, building, premises or deliverability evidence.
The Dominican Republic entity gzip remains in verified split transport parts
and is reconstructed with the documented materialization command before a full replay.

Nine areas with no postcode system reject invented placeholders. The other 19
validate their documented syntax, including fixed `AI-2640` and `TKCA 1ZZ`,
Barbados `BB` codes, Haitian `HT` codes, island-specific Cayman `KYx-xxxx`,
Saint Lucia `LCxx xxx`, French territorial 971xx/972xx codes, and USPS ZIP or
ZIP+4 for Puerto Rico and the U.S. Virgin Islands. Cayman island digits can be
checked against an explicitly supplied island name. Puerto Rico preserves the
urbanization line and never translates `CALLE` or other proper street text.
Address2, P.O. Box, post-office collection, island, parish, district, sector,
lieu-dit and rural sub-locality remain separately representable.

```bash
python -m addressing render-caribbean --country PR --native-language es-Latn \
  --components-json '{"postcode":"00926-3232","city":{"es-Latn":"SAN JUAN","en":"SAN JUAN"},"neighbourhood":{"es-Latn":"URB HIGHLAND GDNS","en":"URB HIGHLAND GDNS"},"road":{"es-Latn":"CALLE MAIN","en":"CALLE MAIN"},"house_number":"125","address2":{"es-Latn":"COND AMAPOLA APT 103","en":"COND AMAPOLA APT 103"}}'
```

`profiles.json` is generated by `scripts/compile_address_profiles.py`. The
source commit and SHA-256 are embedded in the generated file. Runtime use is
standard-library only; refreshing the profiles requires PyYAML.

## Source and license

The formatting profiles are derived from
<https://github.com/OpenCageData/address-formatting>, copyright 2020 OpenCage
GmbH, under the MIT License; the required notice is preserved in
`LICENSE.address-formatting.txt`. The source project describes the templates as
consumer-facing geographic address formatting and explicitly excludes some
postal-mail concerns such as apartment numbers and PO boxes. This package
therefore adds loss-avoidance warnings and keeps Address2/subpremise support as
an explicit compatibility layer rather than claiming source verification.
