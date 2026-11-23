# 住所入力補助

郵便番号の全桁と国コードを指定すると、同じ郵便番号に収録された候補を返す。利用者が選んだ `id` を順番に `path` に追加して次の候補に進む。存在しない番地や部屋番号は補わない。郵便番号の入力途中、未収録の地域、候補の末尾では、利用者が住所を手入力できる。

```sh
python -m addressing.safe_suggest build --index /var/lib/localities/address.sqlite --country JP --country US --country CN --country FR
python -m addressing.safe_suggest lookup --index /var/lib/localities/address.sqlite --country JP --postcode 039-1544
```

索引はローカルに保存された出典から一時ファイルに構築し、成功したときだけ置き換える。公開 API では索引のパスを運営者が設定する。国指定を省くと対象原典に収録された全地域を処理する。完了時に実際の国、出典、処理件数、指定したが対象データのなかった国を出力する。件数は出典から読んだパスの数であり、重複を除いた住所件数ではない。以前の郵便番号選択器の v1 索引を利用している場合は v2 索引に再構築する。

| 原典 | 索引が示すもの |
| --- | --- |
| 日本郵便 | 住所用郵便番号と都道府県・市区町村・町域。出典の範囲説明は番地候補に変換しない。別系統の事業所個別番号は、掲載事業所を選択した場合だけ、その行の住所を表示する。住居や私書箱の住所としては使わない。 |
| 米国 DC MAR | ワシントン DC 市内の公表住所に実在する通りと番地の組。一意に分割できない表記は全文のまま返す。 |
| 中国本土の香港政府事務所目録 | 掲載16施設の英語・繁体字での名称と同じ言語の住所。住宅や郵便番号全体の割当は対象外。 |
| La Poste・INSEE、モーリシャス公式データ | 原典に対応する地域・郵便用の補助情報。担当区域の説明は通りの名称と区別する。 |
| GeoNames | 対象行で報告された場所名と完全なコード。中国などの集約コード、欠けた桁を推定したコードは候補にしない。 |

`query` は幅・大文字小文字を正規化した候補先頭または語頭との前方一致。絞り込み後に取得したページ内でのみ、対象の国・原典・種別が学習条件を満たせば AI が順序を変更する（`ranking_scope: within_page`）。その他の候補は既定順（`source_order`）。前方一致が全件でゼロの場合だけ、同じ国・郵便番号・選択経路にある候補が100件以下で、種類と原典が評価対象の場合に限り、近い綴りの掲載名を提案する。数字・記号・番地・部屋番号を綴り補正の対象にしない。応答の `match_mode: similar_spelling` と `spelling_notice` を画面に反映し、候補は必ず利用者に選択してもらう。候補の順位や評価値は、配達可能率やページをまたぐ順位を示さない。郵便番号・国・path・query または索引のリリースを変えたら `after` を初期化する。

`unsupported_country` はこの索引に国のデータがない状態、`not_found` は郵便番号一致なし、`no_matching_options` は入力した接頭辞に一致する候補なし、`leaf` は選ばれた項目の先に原典の詳細がない状態。いずれも住所が無効であることを示さない。

候補には対応する `supporting_sources`、応答には原典ごとの `source_details`（帰属、収録された利用条件や原典 URL）を含む。利用・再配布条件は原典ごとに異なるため、公開画面やデータ再配布物に該当する帰属表示と利用条件を引き継ぐこと。[原典別の権利表示（GB は OS・Royal Mail・National Statistics の個別表示を含む）](../postal/NOTICE.md)、[郵便データの原典台帳](../postal/sources.json)、[DC MAR](../localities/open_reference/us/citywide/citywide.json)、[香港政府事務所目録](../localities/open_reference/cn/source.json)、[La Poste・INSEE](../localities/open_reference/postal_eu/source.json) に版と取得情報を記載している。
