# 中米8か国の公開地理データ追加

対象はBZ・CR・GT・HN・MX・NI・PA・SV。全行政区・住所用の通り・物理的な道路網・
割当番地の完全網羅を目標として、取得できた原典を追加し、不足を国別に管理する。
配達可能性は対象外。

## 道路・住所の補助データ

Geofabrik配布のOpenStreetMap公開抽出を8か国向けに取得した。原典は合計1,043,836,421バイト。
配布元MD5を取得の前後で照合し、バイト数とSHA-256、解決後の日付付きURLも固定した。
原典の利用条件はODbL 1.0。帰属表示はOpenStreetMap contributors、抽出元はGeofabrik。

- [配布元の中米一覧](https://download.geofabrik.de/central-america.html)
- [メキシコの配布元](https://download.geofabrik.de/north-america/mexico.html)
- [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/)

道路wayの原典ID・ノード参照・座標列・タグ、住所番号タグ、行政境界の原典参照を保持する。
工事中・計画中等は現用道路と分ける。番地の文字列や接尾辞を分割・補完せず、補間線から
番号を展開しない。行政境界relationの部材参照は保持するが、多角形の組立は未実施。

同じOSM IDが複数の抽出に現れても、名前で別物にしたり、別名だけで同一にしたりしない。
同じIDの異なるペイロードも残す。抽出には国境外の参照地物が含まれることがあるため、
抽出コードを法的な所属国とは扱わない。道の区間数は一意の道路名数ではなく、
番号タグの記録は発番機関による割当確認ではない。

データ本体は別の配布書庫に保存し、通常のGitには原典の固定情報・実装・検証結果を置く。
OSMの書庫には固定PBF 8本と国別の圧縮データを含む。
[分割情報](osm-data-parts.json)と[書庫検証](data-archive-verification.json)を参照する。

```bash
python3 scripts/restore_data_parts.py --manifest CA_OSM_20261022.manifest.json --parts-directory /path/to/parts --output /path/to/CA_OSM_20261022.zip
python3 -m zipfile -e /path/to/CA_OSM_20261022.zip /path/to/central-america-data
```

```bash
python3 -m pip install -r scripts/requirements-osm.txt
python3 scripts/osm_stream.py query --exported /path/to/evidence --extract GT --kind roads --text Avenida
python3 scripts/osm_stream.py query --exported /path/to/evidence --extract CR --kind address-numbers --limit 10
```

固定原典から再構築する場合は、未作成の取得先と出力先を指定する。

```bash
python3 scripts/fetch_osm_evidence.py --manifest source-manifest.json --output /path/to/new-raw
python3 scripts/osm_stream.py export --manifest /path/to/new-raw/source-manifest.json --data-root /path/to/new-raw --output /path/to/new-evidence
python3 scripts/osm_stream.py verify --manifest /path/to/new-raw/source-manifest.json --data-root /path/to/new-raw --exported /path/to/new-evidence --output /path/to/replay.json
```

国別のJSON Linesをgzipで圧縮し、原典IDとタグ・座標を直接検索できる形にした。
OSM内のタグなしノードも座標解決には使い、保持対象の地物だけを出力する。
再照合では固定PBFから同じ変換を再実行して、全保持行のID・版・タグ・部材参照・
ノードおよびwayの全座標列と照合する。relationの多角形組立は検証対象に含めない。
SQLite形式を必要とする場合は `scripts/osm_evidence.py build` も利用できる。

## OSMの取得件数

| 抽出 | 現用タグの道路way | 番号タグ観測 | 全保持観測 |
| --- | ---: | ---: | ---: |
| BZ | 37,974 | 5,677 | 51,112 |
| CR | 163,364 | 11,747 | 219,653 |
| GT | 352,168 | 15,836 | 383,774 |
| HN | 198,940 | 581 | 211,890 |
| MX | 4,584,799 | 1,107,857 | 5,825,398 |
| NI | 119,089 | 936 | 134,020 |
| PA | 122,386 | 12,061 | 157,113 |
| SV | 121,232 | 5,460 | 140,106 |

合計7,123,066観測。道路way 5,699,952件、番号タグ1,160,155観測。
国境にまたがる同一OSM IDは複数抽出に現れるため、表の合計は一意な実在地物数ではない。
PBFの原典時刻は全8抽出とも2026-10-20T20:23:47Z。
[出力記録](osm-export.json)、[原典再照合](osm-replay.json)、
[実データ検索24件](osm-query-checks.json)、[テスト結果](test-results.json)を参照する。

## メキシコの番号資料

[OpenAddressesの取得設定](https://github.com/openaddresses/openaddresses/blob/master/sources/mx/countrywide.json)が参照する、
Digital Guard / AddressForAll保存のINEGI由来CSVを取得した。圧縮原典683,565,189バイト、
展開後3,497,198,443バイト。内容アドレスのSHA-256とZIPのCRCを照合し、全31,236,822行を読んだ。
保存元メタデータの取得日は2023-08-16で、各原典の地理的基準日や現在の完全性とは扱わない。

| 観測内容 | 原行数 |
| --- | ---: |
| 全CSV行 | 31,236,822 |
| 空欄とSN等の表記を除く番号文字列 | 15,325,709 |
| SN・S/N等の番号なし表記 | 15,910,873 |
| 番号空欄 | 240 |
| 州名・cidadeラベル空欄 | 各70,505 |
| 地球上の緯度経度として無効・欠損 | 69,880 |
| 有効な緯度経度だが広域のメキシコ確認範囲外 | 1 |

32の州名ラベルと空欄を保持する。確認範囲は外接矩形による異常抽出で、法的国境の判定ではない。
全原行を保持し、番号なしや座標異常を削除しない。`gid` はCSVの原行キーであり、
INEGIの公式住所IDではない。番号文字列の行数を一意な建物数や割当確認済み住所数とはしない。
州・cidade・nsviaを名称一致だけで公式行政区へ接続しない。

帰属表示はINEGI Instituto Nacional de Estadística y Geografía。保存・提供はDigital Guard / AddressForAll。
INEGIの自由利用条件の証拠PDFはSHA-256付きで保持した。OSM資料と別の出典・利用条件で管理する。
詳細は [全行検証](mx-address-validation.json)、[取得記録](mx-address-source.json)、
[原典レビュー](source-review.json)を参照する。

```bash
python3 scripts/restore_data_parts.py --manifest MX_Addresses_Source_20261022.manifest.json --parts-directory /path/to/parts --output /path/to/MX-inegi-addresses.zip
python3 scripts/mx_address_evidence.py query --archive /path/to/MX-inegi-addresses.zip --state Aguascalientes --text Independencia --limit 10
python3 scripts/mx_address_evidence.py inspect --archive /path/to/MX-inegi-addresses.zip --output /path/to/new-validation.json
```

分割書庫からの復元でも原典全体のバイト数とSHA-256が一致することを実ファイルで確認した。

## コスタリカの行政区更新

SNITの公式WFS `IGN_5_CO:limitedistrital_5k` は494件を公表しており、
今回全494件のコードと明示された親参照を取得した。7州・84カントンへの参照は一貫していた。
取得前後のWFS全件数も照合した。原典の境界形状はこの参照表に含めない。

[現在の公開参照](cr-current-districts.json)を、既存のCOD-AB 492地区と出典を分けて比較した。
追加のコードは50405（Pijije）と60310（Cabagra）。詳細は
[コード差分](cr-district-difference.json)に残した。名称からの推測による統合は行わない。
公開サービスの全行を取得したことと、全改編法令との独立照合の完了は区別する。

全国の網羅判定は、道路・番地の独立台帳、法的な行政改編、国境内の所属、未採番の扱いまで
照合してから行う。今回の追加で全国の実在地物を100%収録したとは扱わない。
