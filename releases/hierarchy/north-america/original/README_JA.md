# 北米の住所・地名・行政階層パック

2026-10-17 / v0.1 / Python 3.10以上・標準ライブラリのみ

米国・カナダ・メキシコを国別に一巡し、国→州相当→行政・統計区画→市町村・集落の参照関係を照合するパックです。限定範囲の街路・住所点・番地範囲も、出典のコードで上位階層へ接続しています。

**全3か国の処理を実行したことは、全住所・全街路の完成を意味しません。** 公式資料でも基準年や収録単位は異なります。原典の不整合を記録し、出典にない所属・番地・建物・部屋は補いません。

## 対象

| 区分 | 対象 |
|---|---|
| 本体3か国 | アメリカ合衆国（US）、カナダ（CA）、メキシコ（MX） |
| 補足3地域 | バミューダ（BM）、グリーンランド（GL）、サンピエール・ミクロン（PM） |

本版の「北米」はこの3か国をまとめた作業単位です。既存プロジェクトの国連M49分類では、メキシコは中央アメリカ、残り5コードはNorthern Americaです。元の分類は `NORTH_AMERICA_SCOPE.json` の `m49_mapping` に保持しています。中央アメリカの他の国・カリブ全域は本パックの対象に含みません。

米国の50州とワシントンD.C.を51の州相当区分として扱います。全国Gazetteer配布物に含まれるプエルトリコの原行は保存しますが、米国本体の索引には取り込みません。海外領域を親国の通常住所として統合しません。

## 主な収録内容

| 国・地域 | 公式資料から作る構造 | 今回の原典件数・範囲 |
|---|---|---|
| 米国 | 州相当→郡相当→county subdivision。placeは州に接続 | Census Gazetteer 2026：51 / 3,144 / 35,442、place 32,071 |
| 米国D.C. | 郡→街路→潜在的な番地範囲 | TIGER 2026：街路ID 3,641、番地範囲23,043。全国の街路ではない |
| カナダ | 地理地域→州・準州→census division→census subdivision | SGC 2021：6 / 13 / 293 / 5,161。英語・フランス語の資料をコードで照合 |
| カナダ一部 | CSDコード→街路表記→住所観測 | ODA v1：Yellowknife由来6,996行、街路表記200グループ。2021年の限定資料 |
| メキシコ | 州相当→municipio / demarcación→localidad | INEGI配布カタログ：32 / 2,478 / 296,649。コードの構成項目を照合 |
| PM | collectivité→commune→街路表記→住所観測 | INSEE COG 2026：1 / 2。BAN：街路表記211グループ、住所観測3,049行 |

全6範囲にはGeoNamesの現行扱いの集落・行政第1〜4階層と、対象ノードに対応する別名も収録します。原典に存在しない行政階層を設けるものではありません。バミューダ・グリーンランドの公式住所台帳の一括再利用条件は今回確定しておらず、公式住所全件を取り込んだとはしていません。

米国のplaceはincorporated placeやcensus-designated placeを含み、全件が自治体ではありません。county subdivisionも法的自治体と統計単位を含みます。市が複数の郡にまたがるため、市の名前やコードから1つの郡を推測して挿入しません。

カナダのcensus division・census subdivisionには統計上の同等単位を含みます。ODAのCSDコードとSGC 2021のコードの一致は確認しますが、資料の時点一致や住所点の境界内包含までは証明しません。

メキシコのZIPには複数形式が含まれ、UTF-8 CSVを1つ選んで取り込みます。州資料・自治体資料・地名資料のアーカイブ内の生成名はそれぞれ2025年12月、2026年8月、2026年10月を含みます。これを全項目の統計基準日とは扱いません。人口欄などの秘匿記号も原文のまま保持します。国の台帳をGeoNamesへ名前で統合しません。

## 実行

ZIPを解凍し、このREADMEのあるフォルダーで実行してください。初回の索引生成後は通信・APIキーなしで検索できます。生成したSQLite索引は配布ZIPには含めません。

```bash
# 原典のサイズ・SHA256を確認
python3 address-points/adapters/northamerica.py verify-sources

# 全対象の階層索引を生成
python3 address-points/adapters/northamerica.py build

# 原行再照合・実データ検索・機能テストをまとめて実行
python3 address-points/adapters/northamerica_validate.py

# 本体3か国をループする（既定）
python3 address-points/adapters/northamerica.py loop --output countries_loop.json

# 補足3地域は別にループする
python3 address-points/adapters/northamerica.py loop --scope territories --output supplementary_loop.json
```

原典オブジェクトは約257MB、生成索引は約2.05GBです。再構築中は旧索引と一時索引を同時に保持するため、6GB程度の空き容量を推奨します。索引は最後に検査してから置き換えます。コード・台帳・規則の変更後は再生成が必要です。

## 国・州・市を絞る

```bash
# 米国：選んだ州のplaceを列挙
python3 address-points/adapters/northamerica.py children --parent us-census-2026:state:36 --kind place

# カナダ：アクセントを省いた入力でも候補を検索
python3 address-points/adapters/northamerica.py search --country CA --text Montreal --namespace ca-sgc-2021 --kind census_subdivision

# メキシコ：同名地を選択済みの上位行政区で絞る
python3 address-points/adapters/northamerica.py search --country MX --text Aguascalientes --parent mx-inegi-catalogue:municipality:01001 --namespace mx-inegi-catalogue --kind locality

# 元の表記・コード・出典と上位階層を確認
python3 address-points/adapters/northamerica.py record --id mx-inegi-catalogue:locality:010010001

# 正しい州の選択／誤った州の選択を区別
python3 address-points/adapters/northamerica.py validate-path --country US --input examples/us_new_york_path.json
python3 address-points/adapters/northamerica.py validate-path --country US --input examples/us_wrong_state_path.json

# カナダ・メキシコの階層例
python3 address-points/adapters/northamerica.py validate-path --country CA --input examples/ca_montreal_path.json
python3 address-points/adapters/northamerica.py validate-path --country MX --input examples/mx_aguascalientes_path.json
```

`children` は出典が明示した親・上位関係を列挙します。GeoNamesは国・州・郡への複数リンクを持つため、単純な「直下の自治体一覧」と同じではありません。`--namespace`、`--kind`、`--limit`、`--offset` で対象を指定できます。`next_offset` がある場合は続きのページがあります。

## 地名の言語・原行・郵便番号

```bash
# フランス語の公表表記
python3 address-points/adapters/northamerica.py names --id ca-sgc-2021:province_territory:24 --language fr

# 同じIDに複数原行がある場合も、出典と行順を保持
python3 address-points/adapters/northamerica.py observations --id us-census-2026:place:3651000

# 郵便番号の形式のみを確認
python3 address-points/adapters/northamerica.py postcode --country CA --value "K1A 0B1"

# 収録済み住所観測に明記された郵便番号から検索
python3 address-points/adapters/northamerica.py postal-records --country PM --value 97500

# 国別の要確認事項
python3 address-points/adapters/northamerica.py issues --country US --output us_issues.jsonl
```

原表記、検索用にアクセント等を除いたキー、言語タグ付き別名は別物です。ASCII表記を英訳へ昇格させず、国内英語と国際英語の公称訳を創作しません。`--language` は原典のタグを厳密に指定します。カナダ公式分類の英仏表記は同一コードに接続し、GeoNamesの歴史名・終了日付き名称・未来の名称・空港コード・リンク等は現在の地名候補から除外します。

`postcode` は構文チェックです。`postal-records` は収録した限定範囲の原典属性の完全一致検索です。米国全国のZIP+4、カナダ全国の郵便番号、メキシコ全国のCP割当台帳ではありません。

## 判定の意味

| 値 | 意味 |
|---|---|
| `source_relations_resolved` | 収録資料に明記された参照関係を接続できた。未記載の階層や全国網羅は未検証 |
| `review_required` | 未解決コード、矛盾、親コード欠落などがある。祖先の問題も引き継ぐ |
| `source_path_consistent` | 選択したID列が、出典に記録された上位関係と整合する |
| `not_supplied` | 出典にそのコードがない。制度上不要かデータ不足かは別途確認が必要 |
| `matches_syntax_only` | 郵便番号の文字列形式に一致する。実割当・配達確認を意味しない |
| `address_verified: false` | 完全住所の実在認証を行っていない |

名前・近隣座標・同じ見た目のコードだけで出典を越えて同じ場所と断定しません。米国FIPS、GeoNames行政コード、カナダSGC、INEGIコードはそれぞれの名前空間に保持します。先頭ゼロは保持します。

本件の「Address2より上」は、番地へ進む前の地名・行政階層を主対象としています。一般的な住所フォームでAddress line 2を部屋番号に使う慣習とは分け、原典の番地とunitは別項目として扱います。D.C.の番地範囲は家屋番号へ展開しません。建物・部屋の自動入力もしません。`record` は監査用に原典の明示unitを返すことがあります。

## 原典を更新する

```bash
# 新規候補フォルダーへ、3か国と共通資料を再取得
python3 address-points/adapters/northamerica_fetch.py --output ../north_america_candidate

# 補足地域も含む
python3 address-points/adapters/northamerica_fetch.py --output ../north_america_all_candidate --scope all
```

再取得は既存パックを上書きしません。候補から古い索引・検証結果・国別レポート・配布用MANIFESTを外します。取得失敗があれば構築を止め、アーカイブのメンバー名やCSVの形式が変わった場合も見直しを要求します。固定年の資料URLを自動で最新年に変更する機能ではありません。候補版で索引生成・検証・国別ループを実行し、基準年・名称変更・件数・利用条件を確認してください。

## 同梱ファイルと範囲

- `COUNTRY_RESULTS_JA.md`：3か国と補足3地域の結果・残課題。
- `address-points/NORTH_AMERICA_SOURCES.json`：全30原典オブジェクトと取得記録。
- `address-points/NORTH_AMERICA_VALIDATION.json`：原行・別名・構造・実検索の検証結果。
- `address-points/reports/`：国・地域ごとの件数と要確認コード。
- `LICENSE_DATA.md`：出典・利用条件・帰属表示。
- `tests/`：同名地、誤った州、出典違い、英仏表記、先頭ゼロ、不正な取得内容等の回帰テスト。

国別の全住所・全街路、郵便番号の全国割当、現在の制度との完全一致、境界内包含、自由文住所解析、実配達確認は未完了です。このZIPは実行可能なデータパックで、GitHubのmainや公開サービスへの反映は含みません。
