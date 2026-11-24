# LINZ physical addresses in five New Zealand districts

The common `validate` operation looks up a LINZ address using the territorial authority (`municipality`), `road` and `house_number`. Supply `unit` separately when applicable. `city` or `town` is compared to the LINZ town/city and `suburb` to its suburb/locality. Postcodes remain unverified by this source. Example:

```json
{"operation":"validate","country":"NZ","components":{"municipality":"Chatham Islands Territory","suburb":"Chatham Island","city":"Chatham Islands","road":"North Road","house_number":"1059"}}
```

The capture contains 18,624 current LINZ address IDs across Chatham Islands Territory (468), Gore District (7,121), Kaikoura District (3,085), Kawerau District (3,076) and Mackenzie District (4,874). The public service reported its last data edit on 2 November 2026. The scope of the capture and each response is a published physical address. An address in this source does not establish delivery service.

Sourced from the [LINZ Data Service, NZ Addresses](https://data.linz.govt.nz/layer/123113-nz-addresses/), © Crown copyright, licensed for reuse under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). World Localities selected current addresses in five districts from the [LINZ ArcGIS service](https://www.arcgis.com/home/item.html?id=3632c8130f034ff8bbfb122a50533550), removed coordinates, projected source fields, sorted by LINZ address ID and compressed the CSV. The retained attribution and source record ID accompany each successful match.

To capture a new edition, run `python scripts/project_nz_linz_addresses.py --output /path/to/new-directory`. The script compares the returned object IDs with an independent inventory and count for each authority and verifies the layer edit timestamp across the capture. The compressed projection, CSV hashes, ID-inventory hashes and acquisition date are in [snapshot/source.json](snapshot/source.json).
