# OpenStreetMap の地図上の住所・施設名

米国ワシントンD.C.のGeofabrik抽出ファイルから、同一の地図要素に `addr:state=DC`、名称、番地、通り名があり、図書館または博物館・美術館のタグが付いた76要素を抽出した。2026年1月1日21:21:30 UTC時点の地図の記録であり、公的台帳の現行住所・営業状況・配達可能性は確認していない。データは20ノード・51ウェイ・5リレーションで、施設の一意件数とは異なる。抽出範囲に重なる周辺州の住所は除いた。ノードのみ原典の座標を収録した。

`lookup` はOSM ID、施設名・原典が言語を明示した名称、原典に明記された郵便番号・市・州・通り名、または番地＋通り名（例 `1250 New York Avenue Northwest`）の全ての一致行を返す。空白・大文字小文字・Unicode NFCを照合用に整える。資料で別の地図要素が同じ住所を共有していれば両方を返す。言語別名称は16要素にあり、別の言語に推測変換しない。5要素には市名タグがないため、市名をデータに補わない。個々の施設の正解・翻訳を評価する際、この抽出から作った例を独立評価には数えない。

## 原典と再現

[Geofabrikの2026年1月1日固定PBF](https://download.geofabrik.de/north-america/us/district-of-columbia/district-of-columbia-260101.osm.pbf)（20,320,010バイト）と[同社配布のMD5](https://download.geofabrik.de/north-america/us/district-of-columbia/district-of-columbia-260101.osm.pbf.md5)を登録・鍵なしで取得した。取得日、原本SHA-256、選択行のSHA-256は [source.json](source.json) に記載している。

通常検索は標準ライブラリで動作し、初回読込時に収録データのSHA-256を検査する。原典から再検証する場合は既存の `scripts/requirements-osm.txt` を用いる。次のコマンドは固定PBFを取得し、SHA-256と複製時刻を確かめて地図要素を再選択し、[records.jsonl](records.jsonl) と全バイトを比較する。取得済みの同じファイルは `--pbf <file.osm.pbf>` で指定できる。

```sh
python -m localities.open_reference.osm.replay_osm_places
```

## データの帰属

© OpenStreetMap contributors. [OpenStreetMapの著作権・帰属表示](https://www.openstreetmap.org/copyright)。このフォルダーのOSM抽出データは [Open Data Commons Open Database License 1.0](https://opendatacommons.org/licenses/odbl/1-0/) の下で提供する。Geofabrik GmbHの公開配布ファイルを利用した。データ加工は上記条件・項目による抽出と整形である。外部に表示・再配布する際はライセンスと帰属を引き継ぐ。
