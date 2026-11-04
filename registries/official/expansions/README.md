# アジア4国・地域の公式データ追加レイヤー

香港・韓国・マレーシア・台湾の原典を、国・地域コードごとの別レイヤーとしてまとめています。既存の `official/JP`・`official/TW` やGeoNames由来の基礎台帳は置換しません。

| 国・地域 | 原典と収録単位 | 保存済み観測数 | 入口 |
|---|---|---:|---|
| 香港 `HK` | ALSの18地区の2D中英・建物住所観測 | 182,254 | [説明](HK/README.md)・[収録範囲](HK/coverage.json)・[出典](HK/sources.json) |
| 韓国 `KR` | 2026年9月の世宗市道路名住所DB。郵便番号・道路名・建物番号 | 27,966 | [説明](KR/README.md)・[収録範囲](KR/coverage.json)・[出典](KR/sources.json) |
| マレーシア `MY` | 郵便番号・都市・州の対応 | 2,932 | [説明](MY/README.md)・[収録範囲](MY/coverage.json)・[出典](MY/sources.json) |
| 台湾 `TW` | 115年の公式全国路名CSV。既存の郵便区域表記へ候補対応 | 35,798 | [説明](TW/README.md)・[収録範囲](TW/coverage.json)・[出典](TW/sources.json) |

観測数の粒度は国ごとに異なります。同じ住所・建物・道路・郵便番号の総数として合算しません。全国完全性、現時点の有効性、配達可能性は検証していません。

## 共通の操作入口

リポジトリのルートから実行します。

```bash
python -m localities country inspect --country MY
python -m localities country verify --country MY
python -m localities official search --country MY --text 40160 --field postcode --exact --limit 5
python -m localities official search --country TW --text 忠孝東路 --field road --limit 3
```

公式検索は保存済みの派生データを検索します。ライブAPIへの問い合わせや住所の実在・配達確認ではありません。`matched_observations` は一致した観測数、`returned_observations` は表示数、`truncated` は表示上限による省略の有無です。

国単位の検証は、台帳で関連付けたレイヤーごとの結果を返します。原典の保存ハッシュと全行の変換再生を、住所内容そのものの正しさとは分けて扱います。検索対象・欠損欄・対象外の住所要素・利用条件は各国のREADMEとNOTICEを参照してください。

## 配置

各国フォルダの `sources.json` が取得URL・基準日・取得日・利用条件・保存ハッシュを記録し、`coverage.json` が観測数・列・派生ファイルのハッシュ・検索可能な欄・検証範囲を記録します。

`sources/` に保存する原典と `records.csv.gz` の派生データを区別します。原典にない表記・番地・英語名・座標を推測して追加しません。国ごとの変換処理は `scripts/import_<国コード>_official.py`、共通の検証・検索の入口は `localities/official_expansion.py` です。

大陸・エリア別のデータのコピーは作成しません。国別モジュール台帳からこの追加レイヤーを参照します。全体の進め方と制限は [アジア4地域の強化方針](../../../docs/asia4-official-expansion.md) を参照してください。
