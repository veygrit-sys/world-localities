# 東アジア：行政区・道路・番地の取込（2026-10-22）

対象は既存プロジェクトと同じ CN・HK・JP・KP・KR・MN・MO・TW の8地域。全行政区・住所用の通り・物理道路網・全割当番地の完全網羅は未完了。世界管理表と同じ4区分の32項目すべてで全国網羅の検証は未達とし、分母・網羅率は未確定のまま保持する。配達可能性は対象外。

日本を補強する順序と完了条件は[日本の完全網羅に向けた実行計画](../../../docs/japan-complete-coverage-plan-ja.md)を参照。既存公式台帳の再利用、ABR町字、座標なしを含む住居表示、地番、道路・通り名を自治体別に照合する計画です。

## 取得・統合した資料

| 原典 | 取得した観測行 | 範囲と限界 |
|---|---:|---|
| 日本：ABR由来のOpenAddresses住居表示資料 | 21,984,066 | 位置情報との結合がある住居表示の部分集合。地番や全住所の名簿ではない。元の番号・ID文字列とEPSG:6668の座標値を保持 |
| 日本：Geolonia町丁目位置参照 | 277,658 | 47都道府県コード・1,894市区町村コードを観測。番地や公式ABR町字IDではない。座標欠損469行も保持 |
| 香港：ALS由来のOpenAddresses資料 | 182,122 | StreetNumberあり179,934行。GeoAddressの反復27,751行を残す。提供元は網羅性を保証していない |
| 台湾：内政部115年（2026年）道路名 | 35,798 | 道路名の行。番地、公式道路ID、道路形状は含まない |
| 中国：コミュニティの統計区分参照 | 665,276 | 2023-06-30版。31省級・342地級・2,978県級・41,352郷級・620,573村級。明示親参照を照合。streetsは郷鎮・街道であり実道路ではない |
| 台湾：NLSC行政コードAPI | 8,377 | 22県市・368郷鎮市区・7,781件の名称付き村里参照・206件の名称なし参照。全391応答を取得し、要求時の親コードとの対応を保持。単一時点の法定全名簿とは判定しない |

## OSM補助観測

| 抽出範囲 | 選択された観測 | active道路way | 番地タグ観測 | 行政境界タグ観測 |
|---|---:|---:|---:|---:|
| CN | 8,984,663 | 8,518,735 | 160,130 | 128,424 |
| HK | 275,070 | 184,203 | 64,508 | 292 |
| JP | 11,218,190 | 10,661,600 | 260,624 | 97,132 |
| KP | 262,280 | 259,605 | 193 | 1,783 |
| KR | 2,525,230 | 1,820,504 | 525,435 | 17,027 |
| MN | 211,595 | 123,841 | 6,113 | 1,732 |
| MO | 27,804 | 13,514 | 13,191 | 61 |
| TW | 10,683,783 | 825,686 | 9,811,551 | 32,036 |

件数は抽出ファイル内のタグ観測。物理道路・一意住所・法定行政区の全国総数ではない。抽出範囲への所属を法定国境内の所属とみなさず、地域間の重複も自動統合しない。道路の工事・廃止等の状態、原語の全タグ、OSM ID・版・時刻、節点・関係の順序付き参照を保持。補間から架空の番地を生成しない。

配布物には全選択オブジェクトを保持するnative PBFを収録する。無タグの参照節点をすべて同梱したものではなく、道路線・行政界面の形状は未組立。元PBF全体は配布しない。元PBFを全件再読込した照合記録と原典URL・MD5・SHA-256・バイト数を残す。将来その原典が提供元で削除された場合、同一元PBFの再取得は保証できない。

## 再取得・検索・検証

原典とnative PBFのファイル本体は通常Gitに入れず、別添の分割ZIPと[復元索引](archive.json)に保持する。コードはこのリポジトリに置く。分割ZIP索引のcode_filesに記録したSHA-256と一致する版を使用し、対応コミットは世界管理表のupdates.jsonのeast-asia欄で確認する。[原典一覧](sources.json)、[原典全件照合](source-replay.json)、[native PBF照合](projections.json)、[品質上の残課題](quality-findings.json)、[網羅状況](coverage.json)を参照。

```sh
python3 -m pip install -r scripts/requirements-osm.txt
python3 scripts/hierarchy_cli.py --region east-asia -- coverage
python3 scripts/restore_data_parts.py --manifest EA_OpenData_20261022.manifest.json --parts-directory . --output EA_OpenData_20261022.zip
python3 -m zipfile -e EA_OpenData_20261022.zip restored
python3 scripts/hierarchy_cli.py --region east-asia --data-root restored/data -- search --source-projection --source OSM-JP --kind road --limit 5
python3 scripts/east_asia_query.py --source-projection --data-root restored/data --source OSM-JP --id osm:way:4847506
python3 scripts/hierarchy_cli.py --region east-asia --data-root restored/data -- search --source JP-ABR-residential-OA --text 札幌 --limit 5
python3 scripts/hierarchy_cli.py --region east-asia -- parents --source TW-NLSC --data-root restored/data/tw-nlsc --id village:66000010001
python3 scripts/hierarchy_cli.py --region east-asia --data-root restored/data -- parents --source CN-statistical-villages --id 110101001001
python3 scripts/east_asia_sources.py acquire --data-root originals --output originals/sources.json
python3 scripts/east_asia_sources.py replay --data-root originals --accepted releases/hierarchy/east-asia/source-audit.json --output original-replay.json
python3 scripts/tw_nlsc_reference.py replay --data-root restored/data/tw-nlsc
```

CSVに明示されたIDを維持し、ID列のないGeoloniaと台湾道路名の検索IDは当該原典内の行番号。名称一致やコード接頭辞から公式ID・親階層を推定しない。台湾APIの親対応は元のリクエストから、中国の親対応は明示された親コード列から確認する。既存のアジア基盤・住所書式は維持し、今回の原典を補強資料として追加する。

日本の全国pref/city/townマスターは取得時HTTP 403。韓国等の公式全件住所台帳も未取得。これらを未取得のまま「全国網羅済み」と扱わない。詳細は[source-review.json](source-review.json)と[検証結果](verification.json)。

## 出典・利用条件

[NOTICES.md](NOTICES.md)に原典ごとの提供者・利用条件を記載。原典と派生資料をソース別に保管し、一致していない住所を自動的に同一とみなさない。
