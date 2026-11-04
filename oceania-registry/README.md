# オセアニアの地名・多言語名・郵便番号対応

2026-09-27版の地名データと追加の言語付き名称を、国・地域単位のパッケージにまとめました。大きいパッケージはデータ本体を最大512 KiBに分割し、転送用のBase64ファイル（最大約683 KiB）として格納しています。変換処理は `addresskit/region_names.py`（このディレクトリ内） です。

| 収録対象 | 件数 |
| --- | ---: |
| UN M49のオセアニアの国・地域 | 29 |
| GeoNamesの行政区画・集落等のレコード | 46,594 |
| 上記とは別の国・地域のルートID | 29 |
| 言語付き名称レコード（旧称を含む） | 37,236 |
| 地域IDと直接対応する郵便番号レコード | 262 |
| 国別の個別住所書式 | 21 |
| 汎用書式を継承する国・地域 | 8 |
| 分割されたアーカイブファイル | 62 |

AUのABS 2025の公式コード567件も元データのまま同梱しています。GeoNamesとの重複排除・同一自治体判定は行っていません。統計分類は領有権や行政上の法的地位の判定ではありません。

## 固定IDによる表示切り替え

地域のIDと親IDは言語を切り替えても保持します。同じIDを使って名称を選び、住所の各要素を宛先国の書式へ配置します。文字列を逆順にしたり、地名だけで別の地域IDに置き換えたりする処理はありません。

| モード | 指定・選択方法 |
| --- | --- |
| `local` | `locale="mi"`、`locale="fr"`など現地言語を明示する |
| `international_english` | 用途に一致する英語名、または共通の `en` 名を選ぶ |
| `domestic_english` | `en-AU`、`en-NZ`等を優先し、未収録なら共通の `en` 名を使う |

国の言語数で一律に単一言語・多言語へ分類しません。地域や利用者によって現地言語を指定できます。`reported_local_languages` はGeoNamesの報告値であり、全ての母語や公用語を網羅する認定ではありません。

今回の資料では国内向け英語を固有に区別できる名称は未収録です。同じ英語名を使う場合も、`language_match`、`usage_match`、`fallback` で一致状況を返します。出典で言語が特定されていない元名称やASCII名を、英訳として扱うことはしません。対応する名称がなければ原名を保持し、`untranslated_fallback` として返します。機械翻訳・推測による名称追加は行っていません。

旧称、失効した名称、俗称は標準表示から除外します。同順位で異なる名称が残る場合は `ambiguous_label` と候補を返します。GeoNamesのpreferredフラグは国の公的確認そのものではなく、名称の状態は `source_attested` です。

## 郵便番号と並び順

郵便番号は文字列で保持し、先頭のゼロを維持します。同じ郵便番号と複数の地域IDを結べる多対多の構造です。GeoNames alternateNamesの `post` 行にある直接のID対応だけを採用し、同名や位置の近さによる自動結合はしていません。対応がない場合は `unverified`、検索で地域を絞り切れない場合は `ambiguous` を返します。

`render()` には `locality_id`、`administrative_area_id`、`dependent_locality_id` を役割ごとに渡します。行政上の親を自動的に郵便上の町名とみなすことはありません。Google Address Dataの `fmt` / `lfmt`、必須項目、大小文字指定を適用します。書式上不要な要素は表示だけから省略し、返却する `input` に元の値を残します。

このパックは地名照合と住所書式の基盤です。番地・建物・部屋の実在、住所全体の配送可否、郵便番号の完全な割当範囲は検証しません。`address_lines` は呼び出し側の値を保持します。欠けた必須項目と郵便番号の書式検査結果も返し、常に `delivery_validated: false` としています。

## 使い方

リポジトリの `oceania-registry` で実行します。Python 3.11以上、追加ライブラリ不要です。

```python
from addresskit.region_names import RegionCatalog

catalog = RegionCatalog.from_pack(".", country="NZ")
local = catalog.label("country:NZ", mode="local", locale="mi")
english = catalog.label("country:NZ", mode="international_english")
assert local["entity_id"] == english["entity_id"]

# 入力住所は説明用。実在・配送可能性を示す例ではありません。
result = catalog.render({
    "country_code": "NZ",
    "address_lines": ["1 Example Street"],
    "dependent_locality": "Example Suburb",
    "locality": "Example Town",
    "administrative_area": "Region retained in input",
    "postal_code": "0123"
}, mode="international_english", international=True)
```

```bash
python -m addresskit.region_names --pack . label country:NZ --mode local --locale mi
python -m addresskit.region_names --pack . postal AU 0812
python ./scripts/validate_split_pack.py
python -m unittest discover -s tests -p test_region_names.py
```

`country` を省略すると29国・地域を読み込みます。国ごとのCSV・JSONL・原典を展開するには次を実行します。

```bash
python ./scripts/extract_country.py --country NZ --output /tmp/oceania-nz
python ./scripts/extract_country.py --country shared --output /tmp/oceania-shared
```

各国の `countries/<CC>/index.json` にパーツ順序・SHA-256・ZIP内の全ファイルが記載されています。`pack_manifest.json` は全体の索引です。`.b64` ファイルは自動的に復号・結合し、保存ファイル・復号したパーツ・結合したZIPのチェックサムを確認してから読み込みます。異なる内容の既存ファイルへの上書きは拒否します。

## データと再生成

- `base/`：原版の地名、CSV/JSONL、公式AUデータ、GeoNames国別原典。
- `locale/`：言語付き名称、郵便番号対応、追加原典と取得記録。
- `shared/`：原版の共通資料・生成スクリプト・ライセンス・全体マニフェスト。
- `coverage.csv` / `coverage.json`：国別の収録状況。未収録は0として明示。
- `country_profiles.json`：言語の選択方針と国別の住所書式。
- `quality/`：元データの課題と分割後の検証結果。

原版の195ファイルを元マニフェストのサイズとSHA-256で確認しました。名称と郵便番号の追加は `scripts/build_locale_data.py`、国別分割は `scripts/split_country_packs.py` で再現できます。新しい資料を取得する処理は `scripts/download_locale_sources.py` に分離しています。取得日時は各原典の `.download.json` にあり、データの有効日と同一ではありません。

出典・ライセンスは [LICENSES.md](LICENSES.md)、原版の範囲と品質については [BASE_DATASET_README.md](BASE_DATASET_README.md) を参照してください。

## world-localitiesへの移行

[world-address PR #407](https://github.com/rei-k/world-address/pull/407)のコミット `538a91443823939451c66799604342c2724bc10a` から、取得済みの29国・地域パックを移しました。データ本体・原典・ライセンスは変更していません。読込モジュールと単体テストをこのディレクトリ内に同梱し、スクリプトの読込パスと利用例だけを調整しました。照合結果は [migration.json](migration.json) を参照してください。

Address1の番地・建物・部屋データは収録していません。書式例の住所行は架空の入力であり、収録済み住所ではありません。郵便番号対応はGeoNames原典の直接ID対応262行に限られ、郵便当局の完全な対応表や配送可能性の保証ではありません。既存の欧州・アジア台帳とIDの接頭辞が異なるため、横断利用時は出典IDを明示して扱ってください。
