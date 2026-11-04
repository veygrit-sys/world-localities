# 住所評価の実行と独立評価データ

国別データの構造検証と、実際の問い合わせに対する精度評価を分けます。`scripts/evaluate_addresses.py` は、外部から用意した評価ケースと予測結果をオフラインで照合します。住所データや正解を生成する機能、モデル学習、配送会社への照会はありません。

**実際の住所を独立に確認した評価セットは、この更新には収録していません。** リポジトリのテストにある合成例は評価器の回帰テストであり、住所検証精度の実証には使用しません。

## 入力

JSONL形式で、1行に1つのオブジェクトを記録します。実行はリポジトリのルートから行います。

```bash
python scripts/evaluate_addresses.py --examples /path/to/evaluation.jsonl --predictions /path/to/predictions.jsonl --training-records /path/to/training-ids.jsonl
```

`--training-records` は任意です。省略時は学習データとの重複が確認済みとは扱いません。出力はJSONの標準出力です。実住所や個人情報を新たに公開する操作はありません。

| ケースの項目 | 内容 |
|---|---|
| `case_id` | 一意な評価問い合わせID |
| `country` | 大文字2文字の国・地域コード |
| `task` | `entity_resolution`、`component_validation`、`format_rendering` |
| `expected` | `verdict` と、そのタスクで確認済みの正解 |
| `split` | `evaluation` を必須とする |
| `used_for_training` | `false` を明示する |
| `evidence` | `source_id` と `reference` を必須とする。原典・確認記録へ追跡できる参照 |
| `provenance` | `kind`、`independently_reviewed`、独立確認済みの場合は `review_reference` |
| `equivalence_group` | 任意。同一実体、別名、同一問い合わせの派生を束ねる識別子 |

`verdict` は `matched`、`no_match`、`ambiguous` のいずれかです。`matched` の正解にはタスクに応じて `entity_id`、`components`（文字列の辞書）、`rendered`（文字列）を1種類だけ指定します。数値を含む住所要素も文字列で保持します。正解の `abstain` は認めません。

予測には同じ `case_id`、`country`、`task` と `verdict` を指定します。予測側は `abstain` も使用できます。`matched` は対応する対象を必須とし、他の判定で対象を併記することは認めません。任意の `latency_ms` は有限の0以上の数値です。

重複ID、予測の不足・余剰、国やタスクの不一致をエラーにします。`components` と `rendered` は明示された正解との完全一致を測ります。表記の正規化や寛容な採点を暗黙に追加しません。

## 独立性の扱い

`provenance.kind` は `synthetic`、`source_derived`、`external_reviewed` です。`independently_reviewed: true` は `external_reviewed` と確認記録の `review_reference` がある場合に限ります。合成例・同じ原典から作った例を独立評価に昇格させることはできません。

全ケースの結果は `diagnostic_metrics` に記録します。明示的に独立確認されたケースがある場合のみ、その部分集合を `independent_metrics` に別集計します。独立確認されたケースが0件なら、この項目を出力せず、`claim_status` を `diagnostic_only` にします。確認記録の真正性や確認作業そのものは、この評価器が監査するものではありません。

学習記録は `case_id` と任意の `equivalence_group` を持つJSONLです。学習と評価のIDまたは同値グループが重なれば採点を停止します。未申告の学習データや、同値グループが付いていない別名・同一実体の重複を自動証明する機能はありません。

## 出力指標

| 指標 | 定義 |
|---|---|
| `exact_output_accuracy` | 正解の判定・対象が完全一致した件数 ÷ 評価ケース数 |
| `country_macro_accuracy` | 国別の完全一致率を、ケース数で重み付けせず平均 |
| `false_accepts` | `matched` とした予測のうち、確認済みの判定・対象と一致しない件数 |
| `accepted_error_rate` | `false_accepts` ÷ `matched` とした予測数。受理が0件なら `null` |
| `acceptance_coverage` | `matched` とした予測数 ÷ 全ケース数 |
| `correct_acceptance_coverage` | 正解した `matched` 予測数 ÷ 全ケース数 |
| `abstention_rate` | `abstain` とした予測数 ÷ 全ケース数 |
| `latency` | 計測件数と比率、およびnearest-rank法によるP50・P95。未計測ならパーセンタイルは `null` |

タスク別・国別にも結果を表示します。`format_rendering` の成功は表示文字列の一致であり、住所の実在性・全国完全性・原典の最新性・配達可能性を示しません。誤受理と保留の割合は同じ評価セット・同じカバレッジ条件で比較し、すべて保留する方式も比較対象にします。

## 次の実データ評価

初期対象国ごとに、同名地名、旧住所、表記揺れ、欠損、郵便番号と行政区の多対多対応を含む独立確認済み問い合わせを用意します。原典の版・対象時点・権利・個人情報の扱いを記録し、実体と別名で学習／評価を先に分離します。件数・国別分布・独立確認の方法を確定してから精度を公表します。Hugging Face向け学習データや学習結果の公開は、これらの準備と別の作業です。
