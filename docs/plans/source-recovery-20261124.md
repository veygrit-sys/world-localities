# 取得失敗・保留原典の整理と復旧

確認日：2026-11-24（日本時間）。[機械可読台帳](source-recovery-20261124.json)は、郵便番号の第3・第4回に残った38件の保留判断、欧州の公式全国原典3件、OSMの2収集単位を管理する43行です。国数・全国対応数ではありません。今回再取得したものと、過去の判断を引き継いだものを区別しています。

## 今回の復旧

Geofabrikが `europe/andorra/andorra-261122.osm.pbf` のような地域名サブディレクトリへ移動したため、既存処理が正規の配布先を拒否していました。PR #44で先行していた最小修正を、API機能とは分けてmain向けに適用しています。選択した地域と同名のサブディレクトリだけを許可し、別地域・別ホスト・認証情報・ポート・クエリ付きURLの拒否は維持します。

8原本を実際に再取得し、全量索引を再構築・照合しました。原本・取得時刻・解決先URL・SHA-256と、復元可能な圧縮索引を今回の固定版に保存しています。動的な最新版への参照だけで済ませていません。

| 収集単位 | 再取得 | 再構築・照合した索引 | 証跡 |
|---|---:|---:|---|
| AD・LI・MC・SM・VA・MT | 6原本 | 63,870行 | [microstates-intake.json](../../releases/source-recovery/20261124/microstates-intake.json) |
| JE/GG共有原本・IM | 2原本 | 27,104行 | [crown-intake.json](../../releases/source-recovery/20261124/crown-intake.json) |

索引の行数には既存GeoNames・公式名称参照、OSMの道路・地名・番地候補が含まれます。後者にはGIの既存参照と所属未解決行も含まれます。一意住所数として合算しません。OSMは公式住所台帳と区別し、全国完全性・郵便番号の現行実在・配達可能性を認定しません。

ブータンの旧フォーム取得失敗は第4回の20地域検索・76観測で、タンザニアの旧計画PDFの404はTCRA本土26原本・3,921観測で代替取得済みでした。今回の新規追加件数には数えません。矛盾するブータン年次報告の地図、タンザニアの未取得ザンジバルを混ぜません。

## 次に取り込む優先順

郵便番号から地域を絞れること、公式の番地・道路情報が増えること、現行制度への移行が必要なことを重視します。優先度は取得・許諾・抽出の障害が解消したという意味ではありません。

| 優先 | 国・地域／原典 | 取り込む価値と次の作業 |
|---|---|---|
| P1 | ブルネイ BN | 公式Poskodディレクトリ。地区・集落から郵便番号の入力候補を増やせる。今回も503。PDFの取得後、2018年版の現行性を確認 |
| P1 | クウェート KW | 政府のブロック別・私書箱別表。用途を分けて保存。今回も503 |
| P1 | タジキスタン TJ | 公式の地域・都市・地区・集落別表。階層と空欄の意味を確認。検索には出るが元HTMLは今回も503 |
| P1 | キルギス KG、アフガニスタン AF | 新しい英数字方式／6桁方式を優先。旧方式で穴埋めしない。今回も503 |
| P1 | チュニジア TN | 公式郵便番号検索の原表を確認。過去503、今回は未再試行 |
| P1 | スペイン ES | CartoCiudad全52配布単位。県別GeoPackageの正式取得経路を解決。検索APIの応答を全国取込と数えない |
| P1 | セルビア RS | RGZの道路・番地の双方。今回カタログは200だが、全国CSV取得の成功とは別。実スキーマと共有道路IDを確認 |
| P1 | イタリア IT | ANNCSU全国道路・番地。全国道路エンドポイントは今回も403。正式配布手順を先に確認 |
| P1・抽出 | ネパール NP | 公式の画像PDF。OCR後の原表照合、全ページの行数・先頭ゼロの検査が必要 |
| P1・利用条件 | ベトナム VN | 2025年行政区再編後の34省市・94ページの公式番号表を確認。配布サイトの商用利用は事前の書面承諾条件があるため、原本・変換行は今回公開しない |
| P1・利用条件 | ナイジェリア NG | NDAPSの大量取得・編集条件を確認してから一括取込 |
| P2 | NI・KY・VG・CV・MV・BH・CU | 公式の現行配布先を確認する候補。古い失敗URLの無制限な再試行を避ける |
| P2 | GR・TT・LS・VE・SV | 明示的な公式番号割当表を探す。支店一覧・書式説明だけでは採用しない |
| P2・出典確認 | MM・TM・PG | 候補リポジトリ／ドメイン／旧ホストと公式郵便事業者の関係・版を確認 |
| P2・利用条件 | GE・OM | 現行版の提供・商用利用・再配布条件の確認を先行 |
| P2 | マダガスカル MG | 公式ページの取得は200に回復。ただし本文は読込表示で埋込先はuMap。番号割当行の取得成功とはしない |
| P3 | MZ・UG・ZM・ZW・ET | 構造だけ、試行段階、番号欄のない支店一覧等。実割当の公開を待つ |

不採用の候補は、ブータン年次報告の矛盾する地図、カーボベルデ法令の例示表、公式郵便当局ではないマダガスカルのログイン付き候補です。国全体を不採用にしたものではありません。新しい有料サードパーティは追加していません。

ベトナムの根拠：[省庁の決定2334/QĐ-BKHCN配布ページ](https://mst.gov.vn/van-ban-phap-luat/25175.htm)、[利用条件3項・5項đ](https://mst.gov.vn/dieu-khoan-su-dung-197132008.htm)。ダウンロード可能であることと商用利用条件を区別します。

今回の公開HTTP確認は[http-probes.json](../../releases/source-recovery/20261124/http-probes.json)に保存しました。取得環境の200・403・503はその時点の観測で、全国データの不存在や制度非採用の根拠にはしません。

## 実行・再利用

```bash
python scripts/source_recovery.py verify
python scripts/source_recovery.py list --priority P1
python scripts/source_recovery.py list --country VN
python scripts/source_recovery.py list --status retry_source
python scripts/source_recovery.py verify-snapshots
```

`verify` は過去38判断の参照漏れと証跡パスを検査します。`verify-snapshots` は8原本のサイズ・ハッシュ、2圧縮索引と展開後のサイズ・ハッシュ、索引全行のダイジェスト・件数を再照合します。

圧縮索引は `releases/source-recovery/20261124/{microstates,crown}.sqlite.xz`、元のPBFと取得証跡は `registries/europe/recovery-20261124/osm/` にあります。標準ライブラリの `lzma.open` または `xz -dk` で新しい場所へ展開した後、既存CLIで検索できます。

```bash
python scripts/europe_microstates.py search --db /new/microstates.sqlite --country AD --text Canillo
python scripts/crown_four_localities.py query --db /new/crown.sqlite --country IM --kind address_candidate
```

最新版を取り直す場合は空の別ディレクトリを用います。

```bash
python scripts/source_recovery.py download-europe --collection microstates --directory /new/raw --report /new/downloads.json
```

各原典を独立に取得し、失敗しても後続原典を試します。結果を毎回保存し、1件でも失敗したら非ゼロ終了します。途中失敗時もCIが証跡をアップロードします。取得成功を索引作成済みとは表示しません。通常のオフライン回帰検査は外部通信を行いません。

原本・索引の利用条件は[今回のNOTICE](../../registries/europe/recovery-20261124/NOTICE.md)を参照してください。既存の郵便番号台帳を無条件に置き換えず、出典レイヤーごとに再利用します。
