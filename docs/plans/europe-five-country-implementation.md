# 欧州重点5か国の公式住所取込（2026-11-05）

対象: FR / NL / PL / CZ / DK。これは実装・検証の入口であり、全国住所が取り込まれたという報告ではない。

## 進捗と境界

| 国 | 既存の基盤 | この変更で追加するもの | 次の承認条件 |
|---|---|---|---|
| FR | BAN 96県の受入済み原典ピンと正規化・再実行処理 | 公式配布先・品質課題を5か国台帳へ登録 | 最新版再取得、県・自治体・道路参照の独立評価 |
| NL | 全国BAG履歴・CBS自治体名簿・参照ギャップ評価 | BAGを再取込せず、主副住所・建物参照の課題を台帳へ登録 | VBO/LIG/STAとの関係、時点照合、座標の出典確認 |
| PL | GeoNames地名・行政区画 | PRG GML入力のSHA固定・タグ別スキーマ調査コマンド | 2026-09-10以降の `prgad.xsd` で実ファイル構造を検証し、住所パーサーを別途追加 |
| CZ | GeoNames・Eurostat LAU | RÚIAN ZIP/CSVのWindows-1250住所点正規化・重複検出 | 固定した公式原典の全量テスト、外部サンプル検証 |
| DK | GeoNames・Eurostat LAU | DAR CSVのエンティティ別保持（ID・参照） | 認証済みの実スナップショットで列・時点・5エンティティ間の結合を検証 |

既存のFR・NLの記録は `releases/hierarchy/western-europe/README.md` と各 `official-sources.json` を参照。
公式原典の公開・取得・読込が可能でも、全番地の存在や配送可能性は認定しない。`current` や住所点の存在は、配送業者による受託可能性とは別。

## コマンド

```bash
python3 scripts/europe_priority_ingest.py inventory
python3 -m unittest discover -s tests -p 'test_europe_priority_ingest.py' -v

# 取得済みの公式RÚIANアーカイブ（取得版・基準日を別途記録）
python3 scripts/europe_priority_ingest.py normalize --country CZ \
  --input /path/to/cuzk-monthly-adr.zip --sha256 <official-file-sha256> \
  --source-date YYYY-MM-DD --output /new/path/CZ-ruian.jsonl

# PRGの現行GMLはスキーマ調査まで。住所出力はまだ許可しない。
python3 scripts/europe_priority_ingest.py survey-pl --country PL \
  --input /path/to/PRG-current.zip --sha256 <official-file-sha256> \
  --source-date YYYY-MM-DD --output /new/path/PL-gml-survey.json

# DAR公式ダウンロードのエンティティごとのCSVを確認してから登録
python3 scripts/europe_priority_ingest.py normalize --country DK --entity Adresse \
  --mode current --input /path/to/DAR-address.csv --sha256 <official-file-sha256> \
  --source-date YYYY-MM-DD --output /new/path/DK-adresse.jsonl
```

`--sha256` はローカルで取得した実バイト列のSHA-256であり、例の値を流用しない。
ソース入力は書き換えない。出力が既存なら停止し、重複ID・必須列変更・不正なZIP・入力改変も失敗する。
ただし新規3か国の全件実原典照合と現行配布への自動更新は、この変更では未実施。

## データ取扱の約束

- CZ: `Kód ADM`・自治体ID・番地・ゼロ付き郵便番号を文字列保持。街路が無い住所は勝手に生成しない。S-JTSKのX/Yを緯度経度として扱わない。全国月次CSVのZIPは自治体ごとのCSVを含み得る。
- DK: `Adresse` の `husnummer` は住所オブジェクトへの参照、`Husnummer` の `navngivenVej` と `postnummer` は別実体への参照。実行前に抽出版・同一時点の有効性を確認する。異なるエンティティや抽出時点を単純結合しない。秘密鍵をGitHubへ保存しない。
- PL: 2026-09-10からPRGのZIP/GML公開は新しい `prgad.xsd` のみに変更された。XMLのタグ名だけで住所行とみなさず、現行XSDとの一致を確認するまで正規化しない。
- FR/NL: 旧版の受入済み原典ハッシュや回帰検証コードは変更しない。最新性と元データに含まれる履歴の実在性を区別する。
- いずれも原典・加工物・ライセンス・出典・利用目的を分離する。モデル学習への許諾は個別審査。住所が存在しても配送可否・居住者情報・建物への入室権限は推測しない。

## 公式参照

- FR: [BANダウンロード](https://adresse.data.gouv.fr/outils/telechargements)
- NL: [BAG政府データ](https://data.overheid.nl/en/dataset/10491-bag)
- PL: [PRG](https://www.geoportal.gov.pl/pl/dane/panstwowy-rejestr-granic-prg/) / [2026年9月のスキーマ変更](https://www.geoportal.gov.pl/aktualnosci/zmiany-struktury-publikowanych-danych-adresowych-2/)
- CZ: [全国CSV](https://geoportal.gov.cz/php/micka/record/basic/CZ-00025712-CUZK_SERIES-MD_RUIAN-CSV-ADR-ST) / [仕様書](https://cuzk.gov.cz/Uvod/Produkty-a-sluzby/RUIAN/2-Poskytovani-udaju-RUIAN-ISUI-VDP/Dopady-zmeny-zakona-c-51-2020-Sb/Adresni-mista-CSV_atributy.aspx)
- DK: [DAR File Download](https://datafordeler.dk/dataoversigt/danmarks-adresseregister-dar/dar-fildownload/) / [DARエンティティ説明](https://confluence.kds.dk/pages/viewpage.action?pageId=148452334)

