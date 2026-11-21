# 米国ワシントンD.C.全域の公式住所点

DC政府の Office of the Chief Technology Officer（OCTO / DC GIS）が公開する Master Address Repository（MAR）を使用する。2026-11-21 UTCに、Open Data DC の配布CSVとArcGIS FeatureServerの件数・識別子一覧を匿名GETで取得した。データセット固有の [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) が適用される。[公開カタログ](https://opendata.dc.gov/datasets/DCGIS::address-points)・[ライセンスを記載したアイテム情報](https://www.arcgis.com/sharing/rest/content/items/aa514416aaf74fdc94748f1e56e7cc8a?f=json)

| 固定版の内容 | 件数 |
|---|---:|
| 公開CSV全体 | 144,455行 |
| D.C.全域のうち登録種別 `ADDRESS`、状態 `ACTIVE` | 141,189住所点 |
| 掲載された異なるZIP値 | 115 |
| 別に照合したPennsylvania Avenue NWの公式検索 | 101住所点 |

`PLACE`、`ASSIGNED`、`TEMPORARY` は抽出対象外。これらの区分以外の新規・改廃住所の最新性は独立には調査していない。MARに掲載された住所・座標の根拠で、米国全土、室番号、居住者、郵便事業者による配達可否は対象外。

## 照合と再現

全国共通CLIからこの出典を選択できる。市・州・ZIP・住所・MAR IDを同じ住所点で照合する。例として `1600 Pennsylvania Ave NW` と `20500` は `US-DC-MAR:293211`、`1350 Pennsylvania Avenue NW` と `20004` は `US-DC-MAR:293203` に対応する。通りと番地の組み合わせを保持するため、両ZIPを入れ替えると同じ住所点に一致しない。単独のZIPの検索ではその番号に掲載された複数の住所点が返る。

通りの異なる確認例は `901 G St. NW`、`20001`、`US-DC-MAR:239815`。DC公共図書館の案内にもこの住所表記とZIPが掲載されている。[Martin Luther King Jr. Memorial Library](https://www.dclibrary.org/plan-visit/martin-luther-king-jr-memorial-library)

検索は英字の大文字小文字と空白、方角直前の代表的な街路種別略記（`ST`・`AVE`・`RD` 等、末尾のピリオドは任意）に対応する。方角を保持し、番地範囲から補間しない。[USPSの街路種別表](https://pe.usps.com/text/pub28/pub28apc_002.htm)

```sh
python -m localities.open_reference.us.verify_mar
python -m localities.open_reference.us.verify_mar --online
python -m localities.open_reference.us.build --output /tmp/dc-mar-candidate
```

最初のコマンドはオフラインで全8分割の圧縮前後のハッシュ・行数・全OBJECTID集合を照合し、別途取得した1街路101行も比較する。`--online` は登録・APIキーを使わず、元の全量CSV（84,704,187バイト）、全対象OBJECTID、件数を再取得し、SHA-256と再生成した全住所点の値を照合する。公開元で値やファイルが変わった場合は差分を報告する。3番目のコマンドは出典が更新された際に、新しいディレクトリへ同じ手順で候補版を作成する。

配布物は全量CSVから対象行のMAR ID、OBJECTID、住所、都市、州、ZIP、緯度、経度の文字列を抽出し、MAR ID順に最大2万行ずつ可逆圧縮したもの。公開元の独立した件数応答およびOBJECTID一覧と、選択行の件数とID集合を照合済み。これらの入力URL・取得日・原本と分割ファイルのハッシュは [citywide/citywide.json](citywide/citywide.json) を参照。別の1街路に対する公式応答の原本とハッシュは [source.json](source.json) に収録。結果を再配布する際は District of Columbia, Office of the Chief Technology Officer (OCTO), Open Data DC, *Address Points* を出典として表示し、加工内容とライセンスを添える。
