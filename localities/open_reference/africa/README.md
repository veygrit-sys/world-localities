# モーリシャスの郵便局住所と位置

モーリシャス政府のオープンデータポータルで公開された郵便局名、所在地表記、郵便番号を検索する。位置資料には原典の経度・緯度もある。照合は特定の郵便局の掲載内容まで。一般住宅の住所や郵便番号の現行割当、施設の営業状況、配達可否は未評価。

| 公開資料 | 収録範囲 |
|---|---|
| [List of Post Offices and Addresses in Mauritius](https://data.govmu.org/dataset/list-post-offices-and-addresses-mauritius) | 105行。住所欄の空欄9行と郵便番号欄の空欄1行を保持する。 |
| [Location of Post Offices in Mauritius](https://data.govmu.org/dataset/location-post-offices-mauritius) | 経緯度付き102行。所在地・郵便番号が無い行も名前と位置を保持し、最後の完全な空行1件を除外する。 |

2つの表には同じ局が繰り返し登場する。局名・住所・郵便番号の完全一致で原典行を返す。大文字小文字・空白・Unicode正規化のみ検索用に調整する。つづりの差や同じ郵便番号から同一施設を推定しない。返す住所・地名・郵便番号は元の文字列で、空欄は空文字列のまま返す。郵便番号だけで検索した結果が複数なら、郵便局の名前や住所を同じ原典行で確認できる。

登録やAPIキーを使わずに両CSVを取得した。2026-11-21取得、ポータルの各CSV最終更新日は2024-09-30。位置データの[付属メタデータ](https://data.govmu.org/dataset/d2d3e7af-9ea1-42b2-8012-ece7515f4033/resource/99def1ad-a3c7-4ff1-a89f-874c0a66c016/download/metadata-locations-of-post-offices-in-mauritius.txt)は元資料をMauritius Post、最初のアップロードを2021年9月と記載している。局名が一致する他方の表から空欄や新しい日付を補完しない。

```sh
python -m localities.open_reference.africa.verify_mu_offices
python -m localities.open_reference.africa.verify_mu_offices --download
```

ダウンロード検査は[sources.json](sources.json)のURLから原本を取得し、バイト数、SHA-256、項目構成、行数を検査した後、同梱CSVをバイト単位で再現する。原典が変わった場合は差し替えずに停止する。office-addresses.csv / office-locations.csv には電話番号と電子メールを収録していない。record_id は原典系列とその中で一意な掲載名から作る。source_row はヘッダを1行目としたCSV記録の位置。

## Attribution and reuse

Adapted from data from the Mauritius Digital Promotion Agency (MDPA), Open Data Mauritius. The location dataset credits Mauritius Post as its source and NCB for the original upload and CSV conversion. The portal labels both datasets [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). Both adapted CSV files in this directory are distributed under that same license. Keep source attribution, indicate changes, and apply the same license when sharing further adaptations.

The extraction changes the encoding from Windows-1252 to UTF-8, removes contact columns, renames columns, adds the source row number and skips the wholly blank trailing record. Coordinate values retain the upstream decimal strings.
