# 2026-11-24 OSM原典の復旧固定版

© OpenStreetMap contributors. OSM原本8件とその派生索引のOSM部分は [Open Data Commons Open Database License 1.0](https://opendatacommons.org/licenses/odbl/1-0/) に従います。[OpenStreetMapの著作権・帰属表示](https://www.openstreetmap.org/copyright)。抽出ファイルの提供はGeofabrik GmbHおよびOpenStreetMap.frです。

`osm/` は取得時の元PBFバイト列と取得証跡です。派生処理は既存の `scripts/europe_microstates.py` と `scripts/crown_four_localities.py` による道路名・地名・番地候補等の選択、地域所属の留保、SQLite索引化です。PBFの範囲や余白を法的な国境とみなしません。

今回の圧縮索引は `releases/source-recovery/20261124/` にあります。既存GeoNamesの行は [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)、公式名称の参照はそれぞれ元のNOTICE・出典・利用条件を引き継ぎます。ソースIDを保持し、出典の異なる行を一つの公式住所と同一視しません。元の参照は [microstates](../microstates/README.md)、[crown-four](../crown-four/README.md)、[国別GeoNames](../countries/) を参照してください。

この固定版は全国完全性・最新の郵便番号割当・個々の配達可能性を認定するものではありません。
