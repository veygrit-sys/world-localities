# Japan Post romanized postal localities

The address API can validate Japanese, kana and published Latin components together under one seven-digit postcode. For example, submitting `150-0001`, `東京都`, `SHIBUYA KU` and `JINGUUMAE` verifies those four fields on ordinary postal row 40027 and romanized row 40059. The validator returns both publisher row references. Building, street number, delivery and spelling variants outside the source remain separate.

The 2026-11-09 [Japan Post romanized CSV](https://www.post.japanpost.jp/service/search/zipcode/download/roman-zip.html) has 124,840 rows. We joined it to the [2026-10-30 ordinary Japanese snapshot](https://www.post.japanpost.jp/service/search/zipcode/download/utf-zip.html) on postcode and the full Japanese prefecture, municipality and town. Publisher-inserted whitespace is ignored. The projection retains 120,654 unambiguous rows in 116,905 postal codes. Of the 124,527 Japanese observations, 2,472 have no exact counterpart, 2 have ambiguous identities and 1,399 meet the previous registry's truncation thresholds. The API never generates substitute romanized labels for these missing pairs.

Japanese-to-Latin translation prefers the date-stamped 2026 join. Reverse translation of earlier published spellings can still use the 2025 snapshot and identifies its date in the receipt. The translation digit check preserves an input where the published Latin form changes digit groups. A postal qualifier or instruction does not verify a town or a house number.

The data is derived from Japan Post's two postal datasets. Source terms and the exact ZIP digests are in [the manifest](data/source.json). Newer files at the same download URLs can have different dates and digests. To reproduce with the pinned files, run this command with a new target directory.

```sh
python scripts/project_jp_post_roman.py postal/sources/japanpost/20261030/utf_ken_all.zip /path/to/20261109/KEN_ALL_ROME.zip /path/to/new-directory
```

## Release replay

From the uniquely joined non-truncated rows, exclude empty romanized fields and native town names containing `（` or `場合` or ending in `一円`. Within each native prefecture, rank by SHA-256 of the UTF-8 string `world-localities:20261124:` followed by the decimal (1-based) romanized source row number. Take the first three. On the resulting 141 inputs, validation changed from 0 to 141 full postcode, prefecture, municipality and town matches with the expected romanized source row. The updated code left the swapped field unverified in 282 cross-prefecture controls. Exact romanized output on all three source labels changed from 56 to 137 of 141, with the four digit-preservation cases retained in Japanese.
