# 南米12か国の住所・地名・階層対応パック

2026-10-17 / v0.2 / Python 3.10以上・標準ライブラリのみ

南米12か国を対象に、国→行政区画→市町村・集落の参照関係を再構成し、国別に検証を繰り返せるよう更新しました。取得できた公式資料については、地区・街路まで階層を追加しています。国別の実測結果は `COUNTRY_RESULTS_JA.md` にあります。

**12か国の処理完了と、全国全住所の完成は別です。** 本版は出典に記録された階層を照合する基盤です。全域の町名・街路・郵便番号割当や番地がそろった状態ではありません。

## 対象を12か国と補足4地域に分離

本体：アルゼンチン（AR）、ボリビア（BO）、ブラジル（BR）、チリ（CL）、コロンビア（CO）、エクアドル（EC）、ガイアナ（GY）、パラグアイ（PY）、ペルー（PE）、スリナム（SR）、ウルグアイ（UY）、ベネズエラ（VE）。

補足：仏領ギアナ（GF）、フォークランド諸島／マルビナス（FK）、南ジョージア・南サンドウィッチ諸島（GS）、ブーベ島（BV）。補足地域は国数に加えません。ブーベ島を含む従来の収集範囲は[国連M49の統計区分](https://unstats.un.org/unsd/methodology/m49/)に由来します。統計上の区分から帰属・国境を判断するものではありません。

`SOUTH_AMERICA_SCOPE.json` にこの区分を記録しています。階層点検の `loop` と再取得の既定対象は12か国です。

## v0.2で追加したこと

- 全12か国のGeoNames行政コードを、国コードと上位コードを含む組み合わせで照合。行政第3・第4階層も検索用の構造に取り込みました。
- 元の行政コード表と地名レコードを照合し、参照先不在、同じコードの別行政区への所属、親コード未記載を区別しました。
- 州・市などを選んで候補を絞る検索、親階層の取得、選択した階層の整合チェックを追加しました。
- 国・出典ごとにIDを分離。同名の市、似た行政コード、文字のアクセントを落とした検索結果を同一自治体に統合しません。
- 原典の親コードが空欄でも、別の明示コード項目の組み合わせが公式参照表の1件に一致する場合は、根拠を残して接続します。パラグアイの2件で適用し、元の空欄は変更していません。
- 検索結果に `hierarchy_status` と `source_issue_count` を表示。要確認の祖先も結果へ引き継ぎます。
- 原典の再取得は新規候補フォルダーに保存し、失敗・途中ページ・HTMLの誤取得を検出して確定版への昇格を止めます。

## 取得した追加参照資料

数値は今回保存した原典の件数です。現実世界の全件数や最新制度との一致を保証する数値ではありません。

| 国 | 公式資料から扱う階層 | 今回の件数・版 |
|---|---|---|
| AR | 州相当・departamento・municipio・localidad censal・localidad | 24 / 529 / 2,082 / 4,027 / 4,037。Georef v1応答を保存 |
| BR | UF・municipio・distrito・subdistrito | 27 / 5,571 / 10,751 / 646。IBGE API |
| CO | 第1行政階層・自治体等の単位 | 33 / 1,122。DANE DIVIPOLA、資料の基準日は2024-12-30 |
| PE | departamento・provincia・distrito | 25 / 196 / 1,892。MINSA公開のINEI UBIGEO参照表 |
| PY | departamento相当・distrito・barrio/localidad | 18 / 263 / 7,995。INEの統計参照資料。法的境界の証明には使わない |
| UY | 出典に記されたdepartamento・localidad・calle | 街路観測28,928行。局所IDごとの街路28,926件。資料は2020年7月 |

ウルグアイは文字列で示された所属グループです。これを新しい政府行政IDとは扱いません。地方名のグループは19の通常表記と `LIMITE CONTESTADO` の1表記があり、後者の2街路を要確認にしています。740のlocalidad表記グループも全国の自治体数ではありません。

ボリビア・チリ・エクアドル・ガイアナ・スリナム・ベネズエラには共通のコード照合と階層検索を適用しました。この6か国について、今回新たな全国公式行政台帳・街路台帳を取り込んだとはしていません。

補足の仏領ギアナはINSEE COG 2026の地域1・県1・arrondissement 3・commune 22を追加し、既存BAN住所の自治体コードと接続しました。BANから作る街路表記グループは3,640件です。

## 最初に実行すること

ZIPを解凍し、このREADMEのあるフォルダーで実行します。階層点検だけなら先に新しい階層索引を作れば使えます。索引は配布ZIPに含めません。

```bash
python3 address-points/adapters/southamerica_hierarchy.py build
python3 address-points/adapters/southamerica_hierarchy_validate.py --output hierarchy_validation.json

# 12か国を一巡して点検する（既定値）
python3 address-points/adapters/southamerica_hierarchy.py loop --output country_loop.json

# 補足4地域は別に集計
python3 address-points/adapters/southamerica_hierarchy.py loop --scope territories --output supplementary_loop.json
```

今回の階層索引は約0.7GBです。従来の地名・住所検索索引も生成すると約0.94GBが追加されます。両方を生成する場合は、解凍データ・一時ファイルを含めて3GB程度の空きを確保してください。初回生成後は通信やAPIキーなしで利用できます。

## 州・市を指定した検索と階層確認

```bash
# IBGEの市を検索
python3 address-points/adapters/southamerica_hierarchy.py search --country BR --text "Sao Paulo" --namespace br-ibge --kind municipality

# 選択した州の市を取得。続きは --offset と next_offset を使う
python3 address-points/adapters/southamerica_hierarchy.py children --parent br-ibge:state:35 --kind municipality

# 市から上の階層と、元データの未解決事項を確認
python3 address-points/adapters/southamerica_hierarchy.py hierarchy --id br-ibge:municipality:3550308

# 同名地でも上位自治体を指定して検索
python3 address-points/adapters/southamerica_hierarchy.py search --country BR --text "Sao" --parent br-ibge:state:35 --namespace br-ibge

# 選択済みの国→州→市が、出典の関係と矛盾しないか確認
python3 address-points/adapters/southamerica_hierarchy.py validate-path --country BR --input examples/br_path.json

# 国別の要確認レコードを出力
python3 address-points/adapters/southamerica_hierarchy.py issues --country PE --output pe_issues.jsonl
```

`children` は原典が明示した親・上位階層の関係を列挙します。必要に応じて `--namespace` と `--kind` を指定してください。全出典を混ぜた「直下の自治体一覧」ではありません。

IDの国・出典を一致させて利用してください。例えばGeoNamesの行政コードをIBGEのコード欄へそのまま渡すことはできません。アルゼンチンではmunicipioとdepartamentoを必ず一本道に並べられるとは仮定せず、原典にある複数の所属関係を保持します。

## 結果の読み方

| 状態・値 | 意味 |
|---|---|
| `source_relations_resolved` | 取得した出典の参照関係を接続できた。省略された階層の存在や全国網羅性は未検証 |
| `review_required` | 参照先不在、矛盾、親コード未記載などがある。無条件の自動確定に使わない |
| `source_path_consistent` | 指定したID列が出典の親子・上位関係と整合した |
| `not_supplied` | そのコードが原典に記載されていない。制度上不要なのかデータ不足なのかは別途確認が必要 |
| `resolved_from_explicit_components` | 別の明示コード項目を照合して一意の親を接続した。空欄の原文は保持 |
| `parent_tuple_conflict` | 下位コードは見つかるが、指定された上位コードとの組み合わせが一致しない |
| `address_verified: false` | 完全な住所の実在・配達可能性を認定していない |

前回検出した集落83件の第2行政階層の不整合は、原データに残っています。本版では全件を検出・記録し、祖先や検索結果に要確認を表示します。推測による州・市の差し替えで件数をゼロにしていません。

候補を表示して利用者に選択してもらうことと、未確認項目を自動で埋めることを区別してください。照合済みの所属項目だけを候補として返し、町名・街路・番地の不足を別の地名で補わない運用を想定しています。

## 従来の地名・住所機能

従来の地名・別名・住所原典も保持しています。12か国と補足4地域の合計でGeoNames地理地物708,766行、言語別別名738,944行、AR公式行政・地名4,061行、GF BAN住所観測60,905行です。出典間の重複を統合していないため、固有地点・住宅の件数には換算しません。

```bash
python3 address-points/adapters/southamerica.py verify-sources
python3 address-points/adapters/southamerica.py build
python3 address-points/adapters/southamerica_validate.py --output base_validation.json
python3 address-points/adapters/southamerica.py search --country PY --text "Asuncion"
python3 address-points/adapters/southamerica.py postcode --country PY --value "001218"
python3 address-points/adapters/southamerica.py render --country CO --input examples/synthetic_co_address.json
python3 address-points/adapters/southamerica.py reverse --country CO --layer place --lat 4.60971 --lon -74.08175 --radius-m 5000
```

`postcode` は構文チェックです。全国郵便番号割当表を収録した機能ではありません。`render` は明示入力された項目の整形で、自由文からの汎用住所解析ではありません。建物・部屋の生成は行いません。`reverse` は半径内の原典点を距離順に返し、その点が所属する行政区を境界ポリゴンで判定する機能ではありません。

原表記・ASCII表記・英語タグ付き別名を区別します。国内英語の `en-CC` は既存原典に0件です。ASCII表記を英訳へ昇格したり、欠けた英語名を創作して補ったりしません。

## 検証と原典の更新

`SOUTH_AMERICA_HIERARCHY_VALIDATION.json` が今回の階層検証結果です。全原典オブジェクトのハッシュ、取り込んだ原行の再照合、参照先・国・階層順序、全12か国と補足4地域の実データ検索を点検しています。原典にある欠落や現実世界の誤りまで解消したことを意味するPASSではありません。

```bash
python3 -m unittest discover -s tests -p 'test_southamerica*.py' -v

# 新規候補フォルダーへ再取得。既定では12か国と共通参照表を更新
python3 address-points/adapters/southamerica_fetch.py --output ../south_america_candidate

# 補足4地域も含めて再取得
python3 address-points/adapters/southamerica_fetch.py --output ../south_america_all_candidate --scope all
```

再取得後は両索引の生成・検証・国別点検を実行し、出典の日付・項目変更・利用条件と件数を確認してから公開してください。再取得コマンドは古い検証結果・索引・配布用MANIFESTを候補版から外します。候補READMEに残った説明は元版の説明です。

今回はGeorefの途中ページや異なるスキーマの応答を混ぜず、全行を取得できた行政・地名層だけを採用しました。履歴は `SOUTH_AMERICA_ACQUISITION_REVIEW.json` に残しています。

## 主なファイル

- `COUNTRY_RESULTS_JA.md`：12か国別の到達範囲と残課題、補足地域の結果。
- `address-points/SOUTH_AMERICA_SCOPE.json`：12か国と補足4地域の区分。
- `address-points/adapters/southamerica_hierarchy.py`：階層構築・検索・整合確認・国別ループ。
- `address-points/adapters/southamerica_hierarchy_validate.py`：原行再照合と実データ検証。
- `address-points/SOUTH_AMERICA_HIERARCHY_SOURCES.json`：追加原典19オブジェクトの取得記録。
- `address-points/reports/`：国別結果と要確認レコード。
- `LICENSE_DATA.md`：出典ごとの帰属・再利用条件。DANEのCC BY-SA条件も個別に保持。

この成果は既存パックの更新版です。GitHubのmainや公開サービスへの反映は含みません。
