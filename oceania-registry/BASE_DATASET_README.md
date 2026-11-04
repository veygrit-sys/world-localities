# オセアニア自治体・地名データセット v0.1.0

作成日: 2026-09-27 JST。対象は国連M49の **Oceania / 009に含まれる29か国・地域**。
WorldAddressの住所入力・検索で参照できるように、国、行政区画、都市・集落、元の識別子と所属関係を保持したデータです。

## 収録内容

| データ層 | 件数 | 意味 |
| --- | ---: | --- |
| 国・地域 | 29 | M49の地域分類。主権国家の数ではありません |
| GeoNames行政区画 | 2,009 | ADM1〜ADM5・ADMD。自治体の法的地位は独立検証していません |
| GeoNames都市・集落 | 43,612 | 都市、町、村、居住地の一部など。自治体件数とは異なります |
| 過去の行政区画 | 229 | 歴史地理レコードとして保持 |
| 過去・廃止・破壊された居住地 | 726 | 通常の住所候補から除外する種別として保持 |
| その他の行政関連地物 | 18 | 学区、教区、領域など。元のfeature_codeを保持 |
| GeoNames行の合計 | 46,594 | 国ルート29行とは別 |
| ABS 2025の公式LGA台帳 | 567コード | 地方自治体542、未編入地域6、非地理的な特別コード19 |

ABS台帳とGeoNamesは別の出典層です。両者には同じ実体が含まれ得るため、合算して「自治体総数」にはしません。
全29地域の最新の公式自治体一覧が完成したという意味ではありません。

## ファイル

| パス | 用途 |
| --- | --- |
| `countries.csv` / `countries.json` | 国ルート、ISO alpha-2/3、M49、出典ごとの国名 |
| `summary.csv` / `summary.json` | 国別の行政区画・居住地の件数と階層品質 |
| `data/<subregion>/<CC>/places.csv` | UTF-8の国別全レコード |
| 同じディレクトリの `places.jsonl` | CSVと同じ内容。配列・nullを扱う用途に適した形式 |
| 同じディレクトリの `index.json` | 取得元、原典件数、採用範囲、未対応事項 |
| `official/AU/` | 既存WorldAddressで検証済みのABS台帳を固定コミットからそのまま収録 |
| `quality/parent_issues.csv` | 上位区画の情報欠落・階層を省略した接続などの確認対象816行 |
| `quality/validation.json` | 全件照合と構造検証の結果 |
| `schema.json` | 列とデータ型の説明 |
| `sources.json` / `sources/geonames/` | ダウンロード元・日時・SHA-256・オリジナルZIPと定義ファイル |
| `scope.csv` | 国連M49の対象範囲と4小地域 |
| `scripts/` | 再取得・再生成・検証・名称検索 |
| `manifest.json` / `SHA256SUMS` | 配布ファイルの内容ハッシュ |

小地域は `australia_new_zealand`、`melanesia`、`micronesia`、`polynesia` の4つです。

## 親子関係と利用上の区別

- 国ルートIDは `country:AU` の形式です。GeoNamesの各行は `geonames:2158177` のように出典IDで識別し、同名地を名前で統合しません。
- `parent_id` は原典の行政コードの組を完全一致させて選んだ、最も近い一意な行政上位レコードです。境界ポリゴンとの空間照合結果ではありません。
- `admin1_id`〜`admin4_id` と元の文字列コードも保存しています。コードの先頭ゼロを保持してください。GeoNamesの行政コードをISO 3166-2コードとして扱わないでください。
- `exact_source_code` は記載されたコードから親IDを特定できた意味です。直上の法定行政階層まで全件そろっていることや、公的検証の完了を意味しません。
- `nearest_known_ancestor` は8行です。より近い行政区画を特定できず、元のコードが一致する上位の行政区画につないでいます。欠けた区画名を補作していません。
- `country_only_no_lower_reference` は1,467行です。第一行政階層の正常な国接続も含みます。このうち居住地803行は、原典に有効な下位行政コードがありません。国所属だけを保持します。
- `unresolved_source_codes` は今回0行です。下位情報の欠落がない、という意味ではありません。親コードが不足する行政レコード3行と、自身の行政コードが不完全な5行も確認リストにあります。問題の種類は同じ行で重複する場合があります。
- `name_language=und` は原典の名称に言語タグがないことを示します。`ascii_name`を英訳とみなさず、別名にも日本語・現地語などのタグを推測で付けていません。
- `population=0` は人口不明を含みます。`source_modified_date`はGeoNamesの編集日であり、行政改編の施行日ではありません。
- 国境・行政境界、郵便番号、番地・建物、Address1、配達可否はこのリリースには含めていません。

HM（ハード島・マクドナルド諸島）は対象国・地域として保持し、選択条件に合う行政区画・居住地が原典で0行であることを記録しています。0行から行政組織や土地の不存在を推定していません。
ナウルは今回のM49の英語表記 `Naoero` と、GeoNames側の名称を別フィールドで保持します。

## 使い方

Python 3.11以降。外部Pythonライブラリは不要です。ZIPを展開し、このREADMEのあるフォルダで実行します。

```sh
# 名称・ASCII表記・別名から国を絞って検索
python scripts/query.py Wellington --country NZ --kind populated_place

# 同梱原典から再生成する。ネット接続不要
python scripts/build_dataset.py

# 全件の原典一致、CSV/JSONL一致、ID、親子関係、ハッシュを検証
python scripts/validate_dataset.py
python scripts/test_parent_resolution.py
```

更新する場合は別の空のキャッシュに取得し、既存版との変更を確認してください。
日次配布のURLは内容が変わるため、同梱の原典が本リリースを再現する固定入力です。

```sh
python scripts/download_sources.py --cache new-source-cache --workers 4
python scripts/build_dataset.py --cache new-source-cache
python scripts/validate_dataset.py --cache new-source-cache
```

更新後は原典ディレクトリ、リリースの件数説明、配布manifestも新しい版として更新する必要があります。
同梱のABS台帳は2025版をコピーした層で、GeoNames再生成スクリプトでは更新しません。

## WorldAddressへの組み込み

このパッケージは既存の住所形式YAMLを変更せずに参照できます。
`country:<CC>`を国の接続点として使い、GeoNamesのIDとABS/既存CSCのIDは独立した名前空間として扱ってください。
名称一致だけで既存IDへ変換していません。CSVは全列をまず文字列として読み、数値が必要な列のみ変換する方法が安全です。

ABS台帳の出所は `rei-k/world-address` のコミット
`b2b9ebc6bcfba9f3d98b7eed7075c10526a72a3b`、`address-foundation/official-registry/AU/`です。
インポート時に各ファイルのGit blob SHA-1を照合し、さらに元のSHA-256 manifestを検証しています。

## 出典と範囲

1. UN Statistics Division, [M49 geographic regions](https://unstats.un.org/unsd/methodology/m49/): 29地域の対象範囲。統計上のグループ化です。
2. [GeoNames Gazetteer](https://www.geonames.org/export/), [抽出仕様](https://download.geonames.org/export/dump/readme.txt): 各国の完全な国別ダンプから、Pクラスの全行と政治的実体PCL系を除くAクラスを抽出。掲載地物を網羅しても、現実の全自治体・全居住地を網羅したことにはなりません。
3. Australian Bureau of Statistics, [LGA 2025](https://www.abs.gov.au/statistics/standards/australian-statistical-geography-standard-asgs/edition-3-july-2021-june-2026/non-abs-structures/local-government-areas): 既存の公式原典台帳。ABSの統計的な近似区画であり法的境界ではありません。

原典の条件・帰属表示は [LICENSES.md](LICENSES.md) を参照してください。
検証成功はファイル内容・階層参照・原典一致の検証であり、現実世界での正しさを全件独立確認したという意味ではありません。

## 国別件数

国別の全件数は次の表の通りです。表の「その他」には歴史レコードなどを含みます。

| 国コード | 国・地域 | 行政区画 | 都市・集落 | その他 | 合計 |
| --- | --- | ---: | ---: | ---: | ---: |
| AU | Australia | 678 | 19,204 | 92 | 19,974 |
| CX | Christmas Island | 0 | 6 | 1 | 7 |
| CC | Cocos (Keeling) Islands | 0 | 2 | 0 | 2 |
| HM | Heard Island and McDonald Islands | 0 | 0 | 0 | 0 |
| NZ | New Zealand | 206 | 3,037 | 178 | 3,421 |
| NF | Norfolk Island | 0 | 4 | 0 | 4 |
| FJ | Fiji | 109 | 2,241 | 0 | 2,350 |
| NC | New Caledonia | 44 | 740 | 1 | 785 |
| PG | Papua New Guinea | 158 | 11,546 | 76 | 11,780 |
| SB | Solomon Islands | 193 | 2,549 | 530 | 3,272 |
| VU | Vanuatu | 8 | 1,907 | 15 | 1,930 |
| GU | Guam | 19 | 127 | 4 | 150 |
| KI | Kiribati | 40 | 192 | 15 | 247 |
| MH | Marshall Islands | 33 | 111 | 15 | 159 |
| FM | Micronesia (Federated States of) | 82 | 466 | 6 | 554 |
| NR | Naoero | 14 | 15 | 0 | 29 |
| MP | Northern Mariana Islands | 16 | 48 | 8 | 72 |
| PW | Palau | 17 | 84 | 2 | 103 |
| UM | United States Minor Outlying Islands | 9 | 7 | 4 | 20 |
| AS | American Samoa | 99 | 127 | 23 | 249 |
| CK | Cook Islands | 71 | 56 | 0 | 127 |
| PF | French Polynesia | 93 | 406 | 2 | 501 |
| NU | Niue | 0 | 49 | 0 | 49 |
| PN | Pitcairn | 0 | 1 | 0 | 1 |
| WS | Samoa | 38 | 408 | 0 | 446 |
| TK | Tokelau | 3 | 5 | 0 | 8 |
| TO | Tonga | 28 | 149 | 0 | 177 |
| TV | Tuvalu | 9 | 26 | 1 | 36 |
| WF | Wallis and Futuna Islands | 42 | 99 | 0 | 141 |
