# 日本の公式コード・名称・郵便番号

次の取得・照合手順は[日本の完全網羅に向けた実行計画](../../docs/japan-complete-coverage-plan-ja.md)を参照してください。行政区・町字、住居表示、地番、道路・通り名の完了条件を定めています。

既存WorldAddress日本台帳とIDを共有します。都道府県は `admin:csc:`、市区町村・区は
`locality:jp:lg:<6桁LGコード>` です。チェックディジットを検査し、日本郵便の5桁コードと結合した後、
都道府県・市区町村名の整合を確認しています。

- 47都道府県と1,912市区町村・区を収録。後者には政令指定都市の親20件を含みます。
- 郵便番号と直接接続する1,892市区町村・区、124,526郵便行、120,720種類の7桁番号。
- 地域と番号の組合せ120,877件。134種類の番号は複数の地域に関係し、多対多を維持します。
- 名称11,553行。日本語 `ja`、カナ `ja-Kana`、原典ローマ字 `ja-Latn` を区別します。
- ローマ字は121,867行で一意照合、2,657行が未一致、2行が複数候補です。

## 原典と時点

[WorldAddress日本台帳](https://github.com/rei-k/world-address/tree/8e30ef141e40769fa932adeb2f901505023bfd1e/address-foundation/japan-registry)
のコード・階層・ABR原典行を再利用しています。ABR取得日2026-09-25、台帳基準日2026-09-26。
2026-10-01のABR ZIP新規取得はHTTP 403だったため保存済み版を使い、新しいABR版とは主張しません。
`sources/registry.json.gz` に抽出フィールドと元ファイルのGit blob SHA、`registry-manifest.json` に原典取得記録を保持しました。
元の1,918市区町村行のうち未解決6行を、住所階層へ追加していません。行政単位の不存在や帰属は推定しません。

日本郵便の [UTF-8データ](https://www.post.japanpost.jp/service/search/zipcode/download/utf-zip.html) は2026-09-30更新、
[ローマ字データ](https://www.post.japanpost.jp/service/search/zipcode/download/roman-zip.html) は2025-06-18更新（2025年6月現在）です。
取得日は2026-10-01。各郵便行の法的な有効期間を意味しません。元ZIPをそのまま保持しています。

## ファイルと照合

`entities.csv.gz` は地域ID・公式コード・親子関係、`names.csv.gz` は地域ID・言語・表記種別・出典、
`postal_rows.csv.gz` は地域ID・番号・住所要素・原典フラグとローマ字の省略保存方式です。
省略文字列は [共通アルゴリズム](../romanize.py) で復元し、例外表記を優先します。
詳細は [共通README](../README.md) を参照してください。

ローマ字は「番号＋都道府県＋市区町村＋完全な町域名」の一致で結びます。比較時の空白以外を削除せず、
CSV行順や町域の括弧・範囲を省略した類似照合を使いません。明石市「和坂」の異なる読みは未確定のまま残ります。
三宅村／三宅島三宅村、八丈町／八丈島八丈町、須恵町／須惠町の原典表記差は公式コード一致後にのみ適用します。
未解決2,659行は `unresolved_roman.csv` に保持しました。

原典ローマ字の文字数上限に達した可能性がある1,285行に `roman_truncation_possible=true` を付けています。
「以下に掲載がない場合」等は `town_is_postal_instruction` で識別し、町名とは扱いません。
`association_id` は郵便行のコード・日本語・カナから作る派生キーで、公式の町字IDではありません。
改称・読み変更・番号再割当ではキーが変わり、同一性の履歴照合が別途必要です。

`geonames_candidates.csv` はプロジェクト作成の照合候補で、政府提供のID対応ではありません。
名前・所属・コードの一致候補を公式正解として自動統合しません。
公式英訳の全面収録、大口事業所の個別番号、番地・建物・配達可能性の確認は含みません。

## 出典・利用条件

**「アドレス・ベース・レジストリ」（デジタル庁）を加工したWorldAddress台帳、および日本郵便「郵便番号データ」を加工してWorld Localities作成。**

派生台帳は [ODbL-1.0](ODbL-1.0.txt)。都道府県IDは [Countries States Cities Database](https://github.com/dr5hn/countries-states-cities-database)
（Darshan Gada and contributors、ODbL-1.0）由来です。ABR資源はカタログのCC BY 4.0、
[サイト規約](https://www.digital.go.jp/policies/base_registry_address_tos)は特記がない場合PDL 1.0です。
日本郵便の [UTF-8説明](https://www.post.japanpost.jp/service/search/zipcode/download/utf-readme.html)・
[ローマ字説明](https://www.post.japanpost.jp/service/search/zipcode/download/readme_ro.html) の再配布条件を保持します。
GeoNames候補：© [GeoNames](https://www.geonames.org/)、CC BY 4.0。
加工物が原典提供者に認証・推奨されたことを意味しません。
