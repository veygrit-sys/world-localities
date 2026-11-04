# オランダ：BAGの番地・公共空間・地名とCBS行政名簿

2026-10-08の全国BAG配布から、NUM（付番）、OPR（名称のある公共空間）、WPL（地名）、GWR（自治体との対応を補助する表）を取得。Not-BAG・非活性・調査中の補助書庫も原典のまま保持する。CBSの2026-01-01自治体・州名簿を別の参照元として使用する。配達可能性は対象外。

件数、原典別の全解析行ハッシュ、行政コードの比較結果は `validation.json`。原典9ファイルと配布の証拠3ファイルは `official-sources.json` にバイト数とSHA-256を固定する。全国BAG原典に含まれる履歴を読み込むことと、現実の全住所・全道路の完全性は別であり、全国完全性の認定は行わない。

## 保持する情報

- 16桁の付番・公共空間IDと4桁の地名・自治体コードを文字列で保持。番地、huisletter、huisnummertoevoeging、郵便番号、Verblijfsobject／Ligplaats／Standplaatsの種別を分離する。
- 版番号、有効期間、登録期間、非活性・Not-BAGの時刻、地名上書き参照、原典の状態・geconstateerd・根拠文書を保持。原典の誤記らしい表記も修正しない。
- OPRの `Weg` を道路名の観測とし、Water等の公共空間を `named_area` として別集計する。道路名の件数は無名道・私道等を含む物理道路の本数ではない。
- Not-BAG／非活性のNUMは主台帳の住所観測に加算しない。調査中の記録も別種別で保持。補助書庫内のVBO・PND・LIG・STAは原典を保持しCRC検査するが、今回の構造化読込の対象にはしない。
- WPLの元の面形状は原典XMLに保持し、EPSG:28992の参照を返す。地名の面を玄関座標に転用しない。主住所・副住所の役割と住所点座標の照合には、別途VBO／LIG／STA本台帳が必要。

`registry_open_at_snapshot` は、対象日の有効期間、発行・指定状態、登録終了・非活性・Not-BAG時刻の不在を確認する限定的な条件。現実の使用状態や配達可能性を認定しない。GWRは提供元自身が真正なBAG属性・公式BAG製品ではないと説明する補助表で、CBSの名簿とは分けて記録する。

住所検索の `reference_at_snapshot` は2026-10-08時点の参照名。過去の住所版に現在の道路名を無条件で書き込まず、過去名称の時間結合が未実施であることを明記する。未解決参照は監査表に残す。

住所のない公共空間名も含めた照合は `reference-validation.json`。対象条件に合うOPR 290,616件・WPL 2,503件から342自治体への参照に未解決はなかった。GWRの終了日なしの対応には、対象条件に合うWPLがない120コードも含まれるため、これを現行地名として追加しない。

NUM主台帳は13,377,160版、異なるIDは10,793,745。限定した登録・有効期間条件に合う観測は10,076,588行で、同一IDの複数該当は0。これを全現存住所数とは扱わない。全9原典の件数・正規化行ハッシュ・参照結果は独立した2回の全件読込で一致した。

同じ限定条件では、152行の番地が結合できるOPRを持たず、地名に結合できない番地は153行あった。`reference-gap-review.json` は152件すべてに対して有効期間上のOPR候補を特定し、将来の変更版と登録期間の違いを記録する。残る1行は、2015年に廃止されたWPLコードを明示参照する。元の参照IDを修正せず、候補と原典を分けて保持する。この候補照合は現実の住所・使用・配達の認定ではない。

## 復元と検索

分割ZIPは既存の復元コマンドで元のデータ書庫に戻せる。各部分と復元後の全体をSHA-256で検証し、既存出力を上書きしない。

```bash
python3 scripts/restore_data_parts.py --manifest releases/hierarchy/western-europe/netherlands/archive.json --parts-directory /path/to/parts --output /new/path/Veygrit_Western_Europe_NL_20261022.zip
python3 scripts/hierarchy_snapshot.py restore --manifest releases/hierarchy/western-europe/netherlands/archive.json --archives /new/path --target /new/restored
python3 scripts/hierarchy_cli.py --region western-europe --data-root /new/restored/western-europe-nl/raw -- search --country NL --kind address --number 7 --current-only --limit 5
python3 scripts/netherlands_bag.py replay --data-root /new/restored/western-europe-nl/raw --accepted releases/hierarchy/western-europe/netherlands/validation.json --work-dir /path/with/free/space
python3 scripts/netherlands_reference_review.py --data-root /new/restored/western-europe-nl/raw
python3 scripts/netherlands_gap_review.py --data-root /new/restored/western-europe-nl/raw --accepted releases/hierarchy/western-europe/netherlands/validation.json
```

検索の `--number` は元の番地文字列に完全一致する。接尾文字・番号付加は別フィールド。`--postcode` も原典文字列に一致させる。`--current-only` の意味は上記の限定条件で、住所の実在・配達判定ではない。監査時の一時SQLiteはIDの重複と件数確認に使用し、終了時に削除する。大きな原典を展開せず順に読む。

`python3 scripts/hierarchy_cli.py --region western-europe -- inventory` は従来の107原典とオランダの9原典を表示する。共通CLIの監査・再照合・取得は `--country` を指定する。従来の `scripts/western_europe_sources.py` とその受入済み検証記録は変更しない。

## 配布元との対応

配布元の外側ZIPは約3.64 GBで、今回保持するのは選択した内側書庫の元バイト列。外側ZIPの全体ハッシュを検証したとは扱わない。正確なHTTP範囲応答、ETag、中央ディレクトリ、外側メンバーのCRC・サイズ、保存後のSHA-256を照合する。固定した版と異なる応答やRange無視は停止する。

次の作業は、独立した付番総数との比較、主・副住所の役割、物理道路網、細分区画・境界の照合。カリブ海領域や王国内別国の収録完了は、この追加の対象ではない。
