# 中国本土の住所検証・翻訳

中国本土の構造化住所をオフラインで処理する。香港・マカオ・台湾にはそれぞれの住所プロファイルを使用する。

## 住所を検証する

```sh
python -m addressing validate-china --components-json '{"state":"湖北省","city":"武汉市","city_district":"武昌区","road":"八一路","house_number":"299","postcode":"430072"}'
```

`administrative` は、2023年6月30日時点の統計区分原典に対する名前・コードと親子関係の照合結果。省級31件、地級342件、県級2,978件を収録する。住所に使われる「市」は直轄市では省級に当たる。同名区は上位区分を指定するまで候補を残す。たとえば「朝阳区」には北京と長春の候補がある。`no_match` は指定した条件に一致する行がこの固定版にないことを示す。現在の法定区分は未確認。

`state_code` は原典の省級コード（例 `11`）と、固定版CLDRの省級識別子（例 `CN-BJ`）に対応する。省名とコードに共通する候補がなければ `no_match`、未対応のコードは `unsupported_state_code` を返す。

`postcode.status` はASCII数字6桁の書式検査。郵便番号と地域の割当、街路・番地・建物の実在、個別の配達可否は未検証。住所の原文は `input`、検査対象外の項目は `unchecked_fields` から参照できる。統計表の固定URL・版・ハッシュを [原典台帳](../../releases/hierarchy/east-asia/sources.json) に収録している。

## 省級地名を中英で表示する

```sh
python -m addressing render-bilingual --country CN --components-json '{"state":"陕西省","house_number":"001-2","postcode":"050024"}'
python -m addressing render-bilingual --country CN --components-json '{"state":{"en":"Shanxi"}}'
python -m addressing profile --country IN
```

Unicode CLDR 48 の中国本土31省級地名を使用する。「陕西省」は Shaanxi、「山西省」は Shanxi となる。英語表記を入力する場合は `en` を明示する。追加した表示名は `label_evidence` に言語・版・原典参照・審査状態を記録する。中国語データには暫定ラベルが含まれる。入力済みの中英省名や省コードが異なる省を指す場合は、原文を保持して警告を返す。街路や建物名は呼出元が言語別の表記を指定できる。既定の厳格モードは未翻訳項目を報告して停止する。`--allow-incomplete` は表示可能な項目と欠けた言語・項目の警告を返す。

`profile` の `standard_form_languages` は標準入力フォームの言語を優先順に返す。対象は中国本土の `zh-Hans` とインドの `en`。他の国・地域でこの項目が `null` の場合、フォーム方針は未設定。インドの既存ヒンディー語表示などの互換プロファイルは引き続き選択できる。

[CLDRの固定版](https://github.com/unicode-org/cldr/tree/acd6d88ae493633240e19a87a721076a8a75c310/common/subdivisions)の `zh.xml` と `en.xml` を用意した場合、次のコマンドで両ファイルのハッシュ・全31組の表記・審査状態を再照合できる。

```sh
python scripts/check_china_cldr.py --zh /path/to/zh.xml --en /path/to/en.xml
```

## 固定ケースで比較する

```sh
python scripts/compare_china_addresses.py
python scripts/compare_china_addresses.py --emit-local
python scripts/compare_china_addresses.py --compare-with /path/to/provider-predictions.jsonl
```

[requests.jsonl](requests.jsonl) は入力専用で、各行に国・原文の構造化要素・入出力言語・評価タスク・採点する項目を含む。[expected.jsonl](expected.jsonl) に正解と出典を分離した。同じ大学を使うケースは共通の `equivalence_group` を持つ。

| ケース | 採点する範囲 | 根拠 |
|---|---|---|
| 清華大学の北京の所在地 | 省と区の一致、省名の英訳 | [中国語](https://sem.tsinghua.edu.cn/xygk/lxwm.htm)・[英語](https://masters.sem.tsinghua.edu.cn/en/Contact_Us.htm) |
| 武漢大学の所在地 | 省・市・区の一致、省名の英訳 | [中国語](https://www.whu.edu.cn/)・[英語](https://en.whu.edu.cn/info/5531/52691.htm) |
| 河北師範大学の所在地 | 街路名の英訳。公開された英語表記と比較する | [国際交流部の中英連絡先](https://io.hebtu.edu.cn/en/a/Administration/Offices/index.html) |
| 朝阳区のみ、北京市と武昌区の組み合わせ | 同名の曖昧性、親子関係の矛盾 | 2023年統計区分に基づく合成2件 |

大学の公開ページは2026年11月18日に照合した。3大学からの5件は出典付きの診断例で、独立審査済みの代表サンプルは0件。各タスクの完全一致、誤受理、保留を集計する。街路名の英訳は正解が公開されていても、自作辞書に根拠がないため保留する。

### 外部サービスの予測を照合する

Alibaba Cloudなどの比較時は、同じ `requests.jsonl` を使ってサービスの実応答を採点形式に変換する。比較スクリプトはネットワーク接続や認証を必要としない。外部応答の取得と製品固有の変換は利用側で行う。

1. `--emit-local` と同じJSONL形式を使い、各入力行の `case_id`、`country`、`task`、`fields` を予測へ引き継ぐ。全件につき1行を返す。
2. 入力行全体を `json.dumps(request, ensure_ascii=False, sort_keys=True, separators=(",", ":"))` と同じ方法で表現し、UTF-8のSHA-256を `input_sha256` に入れる。原文・評価項目・言語の変更を検出できる。
3. `provider` に実際のサービス名、`data_version` に使用版を記録する。提供元がデータ版を開示していないときは `undisclosed` と記録する。
4. `verdict` は `matched`、`ambiguous`、`no_match`、`abstain` のいずれか。`matched` のときだけ `components` に採点対象の全項目を文字列で返す。街路や番地を含む入力でも、行政区の照合は指定された行政項目だけを採点する。

外部サービスの予測を指定した場合に限り、2つの実行結果が同じレポートに並ぶ。入力ハッシュやデータ版は比較の記録用で、外部サービスが実行されたことの証明には使えない。
