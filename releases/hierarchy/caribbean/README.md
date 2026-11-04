# カリブ海：行政階層・道路・明示番地

独立国13か国とその他15国・地域、UN M49の計28対象を扱う。
全行政区・住所用の通り・物理的な道路網・割当番地の網羅を目標とする。
現時点の全国完全性は未確認で、配達可能性は対象外。

## 今回の取込

| 出典レイヤー | 今回検証した内容 | 限界 |
| --- | --- | --- |
| 保存済み行政階層 | 28対象、106原典、70,789ノード、93,920原観測と61,392別名行の再照合 | 出典別ノード数。現行の行政区数・全行政区の網羅率ではない |
| BAN：GP・MQ・BL・MF | 314,632番号付き位置観測、314,290住所ID、うち自治体認証220,061位置 | 同じIDに複数位置がある。独立した全国割当台帳との照合は未完了 |
| Census All Roads：PR・VI | 81ファイル、196,190道路地物のDBF属性・PolyLine形状を全行再照合 | 別路線名の重なる地物を含む。番号範囲から割当番地を生成しない |
| OpenStreetMap | 28対象の範囲を確認し、1,788,611オブジェクトを取込。道路way 1,185,849件、明示番地観測590,970件 | OSMの観測。公的台帳の全件取得・割当確定と同一視しない |

[管理表](COVERAGE_JA.md)、[国別4層の状態](coverage-status.json)、
[今回の検証記録](verification.json)を正本とする。
`original/` と `address-points/CARIBBEAN_*` は2026-10-17版の記録で、今回の検証結果とは分ける。
既存の `caribbean-registry/` の27地域スナップショットも別出典・別版であり、単純合算しない。

## 保存済み行政階層の復元と検索

元の `Veygrit_Caribbean_20261017.zip` を使う。原書庫と選択したコード・説明のSHA-256は
`archive.json` に固定している。大容量原典と生成索引は通常のGitに入れない。

```bash
python3 scripts/hierarchy_snapshot.py restore --region caribbean --archives /path/to/archives --target /path/to/new-hierarchy
python3 scripts/hierarchy_cli.py --region caribbean --data-root /path/to/new-hierarchy/Veygrit_Caribbean_20261017/address-points -- build
python3 scripts/hierarchy_cli.py --region caribbean --data-root /path/to/new-hierarchy/Veygrit_Caribbean_20261017/address-points -- loop --scope all
```

階層モジュールのGit上の名称は `caribbean_hierarchy.py`。
親参照の欠落・矛盾・版差を残し、同名・同座標だけでは結合しない。
DOの155対158自治体、JMのPortmore境界、HTの階層差は未解決のまま管理する。

## BANとCensusの復元

データ書庫名は `Caribbean_Official_Source_Data_20261022.zip`。
`official-data-archive.json` は書庫のハッシュ、`official-sources.json` は85原典のハッシュを固定する。
復元先・索引の出力先には未作成のパスを指定する。

```bash
python3 scripts/hierarchy_snapshot.py restore --manifest releases/hierarchy/caribbean/official-data-archive.json --archives /path/to/archives --target /path/to/new-official
python3 scripts/caribbean_official.py build --sources /path/to/new-official/Caribbean_Official_Source_Data_20261022 --db /path/to/new-official.sqlite
python3 scripts/caribbean_official.py replay --sources /path/to/new-official/Caribbean_Official_Source_Data_20261022 --db /path/to/new-official.sqlite
python3 scripts/caribbean_official.py coverage --db /path/to/new-official.sqlite
python3 scripts/caribbean_official.py crosscheck-admin --db /path/to/new-official.sqlite --hierarchy-db /path/to/new-hierarchy/Veygrit_Caribbean_20261017/address-points/generated/caribbean_hierarchy.sqlite
```

住所ID、番地、接尾辞、行政コードは文字列として保持する。
GP・MQの66コミューンと、BL・MFの明示コード別表現を含む計68参照をINSEE原典へ接続した。
BLの97701を架空の下位コミューンにせず977のcollectivityへ、MFも同様に接続する。
BANの街路名称グループ20,751件は検索用の集計であり、独立した全街路台帳ではない。

## OpenStreetMapの復元と再取得

公開データの出典はOpenStreetMap contributors、ライセンスは
[ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/)。
帰属表示は `© OpenStreetMap contributors`。公式データとOSMの観測は出典別に保持する。

`osm-data-archive.json` で固定した書庫を復元後、正規化データから索引を再構築できる。
生成SQLiteは配布書庫に含めず、データの読取・検索・復元はPython標準ライブラリで実行できる。

```bash
python3 scripts/hierarchy_snapshot.py restore --manifest releases/hierarchy/caribbean/osm-data-archive.json --archives /path/to/archives --target /path/to/new-open-map
python3 scripts/caribbean_osm.py restore-index --snapshot /path/to/new-open-map/Caribbean_OpenMap_Source_Data_20261022 --db /path/to/new-open-map.sqlite
python3 scripts/caribbean_osm.py query --db /path/to/new-open-map.sqlite --country CU --limit 20
```

PBFから再抽出する場合のみ、オープンソースのpyosmiumとShapelyを使う。
版を固定したGeofabrik配布の取得URL・SHA-256は `osm-source.json` にある。
中央アメリカ全体の配布から28対象を抽出するため、元配布の全件をカリブ海件数に数えない。

```bash
python3 -m pip install -r requirements-caribbean-osm.txt
python3 scripts/caribbean_osm.py extract --pbf /path/to/central-america-261020.osm.pbf --receipt releases/hierarchy/caribbean/osm-source.json --target /path/to/new-osm-extraction
python3 scripts/caribbean_osm.py replay --pbf /path/to/central-america-261020.osm.pbf --snapshot /path/to/new-osm-extraction
```

元のOSM種別・ID・版・タグ・明示された参照を残す。補間wayを実在番地へ展開しない。
境界をまたぐ道路や重複する国境ポリゴンは要確認とし、最寄り国へ強制配属しない。
OSM行政境界地物数は法的な行政区数ではない。BQの法的な共同範囲を共通行政機関と扱わない。
無名・工事中・計画道路も原タグを保持し、通行可能性や配達可能性を推測しない。

OSMの明示されたsubarea参照は `osm-parent-audit.json` で監査し、循環・階層の矛盾・未収録参照を記録する。
配布候補の所在・範囲・取得条件は `openaddresses-candidates.json` に残した。
