# Veygrit カリブ海版 — 2026-10-17

独立国13か国と補足15地域、合計28対象の地名・行政階層を検索する実行用パッケージです。国別ループ、親子コードの照合、原行の参照、出典別の要確認情報を収録しています。Python 3.10以上の標準ライブラリだけで再構築できます。

この版は行政区分・集落の参照データです。全国の街路・番地、建物名、部屋番号、郵便番号の割当は未収録です。`Address2`を含む住所全体の実在・配達可否を検証するものではありません。

## 対象

- 独立国：AG / BS / BB / CU / DM / DO / GD / HT / JM / KN / LC / VC / TT
- 補足地域：AI / AW / BQ / VG / KY / CW / GP / MQ / MS / PR / BL / MF / SX / TC / VI
- `countries`は13か国、`territories`は15地域、`all`は28対象を順に処理します。

[国連M49のカリブ海（029）](https://unstats.un.org/unsd/methodology/m49/)を範囲の基準とし、独立国とその他の国・地域を分けて集計しました。Aruba・Curaçao・Sint Maartenはオランダ王国の構成国であり、本版の独立国13か国には含めません。BQは3島を持つ1対象です。仏領MFと蘭領SX、ドミニカ国DMとドミニカ共和国DOはそれぞれ別です。北米・中米・南米版との国の重複計上はありません。

## 実行

ZIPを展開し、このREADMEと同じフォルダーで実行してください。生成するSQLiteは配布ZIPに含めていません。

```bash
python3 address-points/adapters/caribbean.py verify-sources
python3 address-points/adapters/caribbean.py build
python3 address-points/adapters/caribbean.py loop --scope countries
python3 address-points/adapters/caribbean.py loop --scope territories
python3 address-points/adapters/caribbean.py loop --scope all --output address-points/all-loop.json
```

既存の国別結果は `address-points/reports/countries/` と `address-points/reports/supplementary/`、実行済みのループ結果は `CARIBBEAN_*_LOOP.json` にあります。すべての対象を一巡した結果を保存済みです。

```bash
python3 address-points/adapters/caribbean.py search --country MF --text Marigot
python3 address-points/adapters/caribbean.py search --country GP --text Basse-Terre --namespace insee-2026 --kind commune
python3 address-points/adapters/caribbean.py hierarchy --id insee-2026:GP:commune:97105
python3 address-points/adapters/caribbean.py record --id insee-2026:BL:collectivity:977
python3 address-points/adapters/caribbean.py observations --id insee-2026:BL:collectivity:977
python3 address-points/adapters/caribbean.py names --id insee-2026:GP:commune:97105 --language fr
python3 address-points/adapters/caribbean.py children --parent insee-2026:GP:department_code:971 --kind commune
python3 address-points/adapters/caribbean.py validate-path --country GP --input examples/gp_basse_terre_path.json
python3 address-points/adapters/caribbean.py validate-path --country GP --input examples/gp_wrong_arrondissement.json
python3 address-points/adapters/caribbean.py issues --country CW --output cw-issues.jsonl
```

検索・子要素・別名・原観測には `--limit` / `--offset` によるページ送りがあります。`has_more` と `next_offset` を使って残りを取得してください。`children` は原典が明示した親・上位要素への接続なので、国直下の結果に複数の階層が現れる場合があります。`--kind` と `--namespace` で絞れます。

## 上位階層の扱い

1. 原典コードを文字列で保持し、先頭ゼロ・ハイフン・言語情報を残します。
2. GeoNames、HDX COD-AB、INSEE、Censusは別の名前空間です。同名・同座標・似た番号だけでは統合しません。
3. GeoNamesの第1〜第5階層は国コードと上位コードの組を照合します。第5階層は追加の `adminCode5.zip` で接続します。
4. 下位区分の親が欠落・重複・矛盾している場合は `review_required` にします。推測した親を追加しません。
5. `hierarchy` は上位要素の問題も返し、検索結果にも要確認状態を表示します。
6. INSEEのMartiniqueには県コードと単一地方公共団体の枝があります。BLの977/97701、MFの978/97801は同じcollectivityの異なるコード表現として保持します。
7. PRのmunicipioとbarrio等はGEOIDで接続します。Census placeにはmunicipioの対応がないので、コードの類似だけでは接続しません。

`source_relations_resolved` / `source_path_consistent` は、収録した原典内の参照関係が解決できたという意味です。全行政階層の網羅・現行性・点の実際の包含関係や住所の正しさを保証する状態ではありません。未供給コードは `not_supplied` として残します。

## 収録量と検証

| 項目 | 件数・結果 |
|---|---:|
| 処理対象 | 13か国＋15地域＝28 |
| 原典ファイル | 106 |
| GeoNames集落・都市参照 | 47,719 |
| 全名前空間のノード | 70,789 |
| 明示した親・上位接続 | 247,459 |
| 原典との一致確認済み観測行 | 93,920 |
| 追加別名の照合行 | 61,392 |
| COD-AB選択行 | 3,211 |
| GeoNames ADM5ノード | 12,565 |
| 集落からADM5への接続 | 7,603 |
| 動作テスト | 63件 PASS |
| CLI確認 | 20件 PASS |
| XLSX独立読み戻し | 25シート・3,128行・79,207セル PASS |

ノード総数は複数の出典を足した件数であり、重複を除いた全国自治体・住所数ではありません。63件のテストに加え、56系統の原観測、28地域の追加別名、SQLiteの外部キー・同一対象内接続・循環不在を確認しました。XLSXはopenpyxlの独立読み取りと比較しました。

要確認情報は2,041件。直接問題を持つノード2,041件と、その上位関係から影響を受けるノードを含めた31,373件を区別しています。多くはGeoNamesに親コードがない集落や原典の版差です。処理のPASSは問題がゼロ・住所が完全という意味ではありません。

```bash
python3 address-points/adapters/caribbean_validate.py
python3 tests/check_cli.py
# XLSXの独立読み戻しを再実行する場合のみopenpyxlが必要
python3 -m pip install -r tests/requirements-optional.txt
python3 tests/check_xlsx_readback.py
```

## 注意する原典差

- ドミニカ共和国：COD-ABの155市町村に対してIGNの公表は158。第4・第5階層まで収録していても現行の全国完成版とは扱いません。
- ジャマイカ：Portmore教区化に関連する2026年の境界調整を反映済みとはしていません。
- ハイチ：COD-ABは県→コミューン→共同区、GeoNamesは郡を挟む別構成です。階層番号をそのまま対応させません。
- キュラソー：原典66行のうち65が参照区画、1行は `Homeless respondents` という地理区画でない集計カテゴリです。
- モントセラト：Plymouthの原典区分を保持しつつ、放棄された町・立入制限区域として個別に要確認表示します。
- 全対象：街路・番地・建物・部屋、郵便番号の割当データは取得していません。

詳細は `COUNTRY_RESULTS_JA.md`、外部資料は `REFERENCE_NOTES_JA.md`、利用条件は `LICENSE_DATA.md` を参照してください。

## 再取得

```bash
python3 address-points/adapters/caribbean_fetch.py --scope all --output ../caribbean-candidate --workers 4
```

新しい候補フォルダーを作り、全対象の原典を再取得します。`countries` / `territories` に限定した場合、その他の対象は元のスナップショットのまま残ります。共通コード表は毎回取得するため、その候補も全対象で再構築・検証してください。既存の確定フォルダーは上書きしません。取得失敗は記録し、失敗がある候補の構築を止めます。将来の取得についてはヘルプと入力形式を検証済みですが、将来版の取得・適合を保証しません。ソースの版・件数・列・ライセンスに変化があれば再確認が必要です。

取得日時、元URL、原ファイルのSHA-256、使用したシート・列・コード体系は `CARIBBEAN_SOURCES.json` と各receiptにあります。原ファイルを改変せず保持しています。ZIP内の `MANIFEST.json` は同梱ファイルのサイズ・ハッシュ一覧です。このパッケージの作成はGitHubや本番データベースへの反映を意味しません。
