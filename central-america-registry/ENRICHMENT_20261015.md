# 中央アメリカ強化：2026-10-15

## 更新範囲

従来の6か国版を上書きせず、コスタリカの取得原典と派生台帳を `enrichment/` に追加する。メキシコの既存INEGIレイヤーも含め、中央アメリカ（UN M49 013）の8か国を `query_enriched.py` と `quality.py` で参照する。

| 国 | 集落等のGeoNames Pレコード／別出典の自治体役割 | 読み込み先 |
|---|---:|---|
| BZ ベリーズ | 528 | 既存GeoNames |
| CR コスタリカ | 5,900 | 今回追加したGeoNames |
| GT グアテマラ | 16,981 | 既存GeoNames |
| HN ホンジュラス | 12,966 | 既存GeoNames |
| MX メキシコ | 2,478 | 別出典の既存INEGI自治体役割 |
| NI ニカラグア | 2,632 | 既存GeoNames |
| PA パナマ | 13,267 | 既存GeoNames |
| SV エルサルバドル | 4,889 | 既存GeoNames |

**8/8は国別の出典レイヤーが存在するという意味であり、すべての住所・自治体・街路・建物・部屋番号の網羅ではない。** メキシコの自治体とGeoNamesの集落を同種の地物と見なさない。旧 `scope.json`、`manifest.json`、`coverage.csv` は6か国の保存済み版の原本であり、移動・再作成しない。現行の統合集計は `americas-registry/audit.py` を使う。

## コスタリカの追加実データ

GeoNames原典の全A/Pレコード6,465件を保持する。内訳は集落等5,900件、行政区画564件、その他行政地物1件。行政区画は原典のADM1が7件、ADM2が82件、ADM3が474件、ADM4が1件である。廃集落等を除いた既定の候補は5,781件。検索候補というだけで配達可能性は保証しない。

言語タグ付き名称6,182件を追加した。英語タグの名称は45件、スペイン語タグの名称は5,234件であり、完全な英訳ではない。旧称・有効期間・原典の優先名フラグも保持する。出典の原名に言語を勝手に付けず、要求言語がなければフォールバックを明示する。

今回のCR別名原典から得られた直接IDの郵便番号リンクは**0件**である。行政コードから郵便番号を生成しない。未解決の原典親参照1件も推測で補わず残す。生成物と原典ZIP、国情報、ライセンス文書、取得日時・HTTPヘッダー・SHA-256を保存する。

## 82カントンと84カントンを混同しない

GeoNames原典にはADM2が82件しかない。一方、TSEの2025-11-13公表資料は2026年選挙の84カントンを示す。

- TSE: https://tse.go.cr/comunicado1103.html
- 保健省のカントンコード表: https://www.ministeriodesalud.go.cr/fhir/CodeSystem-cantones-cs.json.html

保健省が公開するCodeSystemは84件で、612=Monteverde、613=Puerto Jiménezを含む。これを `government-reference/CR/` に独立保存し、元の82件を上書きしたり、同名だけでGeoNames IDと結合したりしない。

**このCodeSystemは公開実装ガイドの1.1.0-ballot版、リソース日付2024-09-20、リソース状態activeである。** 国の現在の法的境界や最新の全国行政台帳を確認したという意味ではない。版・日付・原典の名前空間を保持する。政府公開コード表の条件はGeoNamesのCC BY 4.0と分けて記録する。英語名・座標・郵便番号・県への外部ID対応は生成しない。

## 実行

リポジトリのルートでPython 3.11以降を使う。追加の外部Pythonパッケージは不要。

```bash
# 8か国の実ペイロードを検査する
python central-america-registry/quality.py

# コスタリカの原典ZIPから全行照合する（ネットワークなし）
python central-america-registry/supplement.py verify

# 共通の国別検索：原典IDと表示言語を分離する
python central-america-registry/query_enriched.py --country CR --text 'San Jose' --language es
python central-america-registry/query_enriched.py --country GT --text Guatemala
python central-america-registry/query_enriched.py --country MX --text Oaxaca

# GeoNamesの82行政区画と、政府コード表の84項目を別々に照会する
python central-america-registry/query_enriched.py --country CR --level 2 --limit 100
python central-america-registry/query_enriched.py --country CR --layer government-cantons --limit 100
python central-america-registry/government_codes.py query --code 613

# 中米単位の繰り返し監査と状態保存
python americas-registry/quality_cycle.py --area central-america --rounds 2 --state-file /tmp/central-quality.json
python -m unittest discover -s tests -p 'test_americas_*.py' -v
```

旧 `query.py` は既存6か国の互換用として残す。新しい8か国共通入口は `query_enriched.py`。メキシコは原典スキーマが違うため、GeoNames専用のlevel/kind/parentフィルターを拒否し、region/textを使用する。

## 検査と今後の課題

CRでは原典ZIP→全19原典フィールド→派生階層→言語名・郵便番号候補を再計算して照合する。既存6か国では圧縮/展開後ハッシュ、全行の派生列再現、親IDの参照・循環、別名・郵便番号候補のID整合性まで調べる。既存6か国の原典ZIP・全別名原典の再取り込みとは区別する。メキシコは既存の公式スナップショット検査を維持する。

原典ハッシュを更新しても偽の名称・件数・重複IDが通らないかをテストする。実行による中間ファイルは原則一時領域に置き、原本や関連地域を変更しない。

残る重点は、CRの新旧行政コードの地理的対応、現行地区の公式台帳、既存国の行政改編の照合、正規の郵便番号データ、街路・番地・建物・部屋の収集である。今回の国別対応8/8を、これらの課題の完了と読み替えない。
