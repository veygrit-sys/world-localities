# Korea: Sejong road-name address pilot

The **202609** Ministry of the Interior and Safety / Juso Korean road-name address DB supplies **27,966 source address observations** in the selected `rnaddrkor_sejong.txt` member: 1,139 road codes, 153 postal codes and 140 legal-dong codes. Scope is Sejong (`36110`) only. These are source observations, with no claim of nationwide completeness, currentness, physical premise verification or deliverability.

The 24 fields follow the official Korean-address layout. Original Korean text, official 26-digit address IDs, 12-digit road codes, five-digit postal codes, building/lot numbers, effective dates, prior addresses and both building-name columns remain separate strings. Missing values remain empty. This source does not provide English names or an independent deletion-date field; neither is generated. The `63` change reason is preserved when provided, but the full snapshot does not establish a deletion history. The related-parcel (`jibun`) companion is outside this pilot.

The original selected member is saved byte-for-byte inside `sources/rnaddrkor_sejong.txt.gz`; gzip packaging is deterministic. `sources.json` records the official ZIP URL, selected-member SHA-256 and CRC, source-month, retrieval time, layout and catalogue terms. The 92 MB national archive is not bundled. Offline verification replays the saved Sejong member and compares every resulting CSV byte, hash, field and count.

## Reproduce

Run from the repository root:

```sh
python scripts/import_kr_official.py acquire --output /tmp/kr-sejong-202609.txt.gz
python scripts/import_kr_official.py build --source /tmp/kr-sejong-202609.txt.gz --output /tmp/kr-sejong-rebuilt --retrieved-at 2026-11-04T19:37:03Z
python scripts/import_kr_official.py verify --folder /tmp/kr-sejong-rebuilt
```

`acquire` uses ordinary public HTTP Range to retrieve the pinned ZIP member, validates its member name, lengths, CRC and SHA-256, and requires no account or API key. It fails if that source snapshot changes. `build(source, output, retrieved_at=None)` and `verify(folder)` also work as Python functions. Outputs must be new paths.

Search fields are listed in `coverage.json`. A match returns a source observation within this pilot; it does not certify a delivery destination.

## Source and terms

- [Official Korean-address catalogue, identifier 15050417](https://www.data.go.kr/data/15050417/fileData.do)
- [Official catalogue metadata](https://www.data.go.kr/catalog/15050417/fileData.json)
- [Juso address download page](https://business.juso.go.kr/jst/jstAddressDownload)
- [Public Data Portal source terms](https://www.data.go.kr/ugs/selectPortalPolicyView.do)

The catalogue covers the same Korean-address DB and states `이용허락범위 제한 없음` (no limitation on the permission scope). The upstream dataset keeps its own source terms; no Creative Commons, KOGL or repository code licence is substituted. See `NOTICE.md` for attribution.
