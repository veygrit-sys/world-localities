# マレーシアの公式郵便番号・都市・州対応

data.gov.my の **Postcode Dataset** を原典のバイトとともに収録しています。

| 項目 | 保存版 |
|---|---|
| 原典 | [Postcode Dataset](https://data.gov.my/data-catalogue/poskod) |
| 提供データの出所 | Malaysian Communications and Multimedia Commission |
| 原典の基準 | 2026年6月（カタログ記載、月単位） |
| カタログ最終更新 | 2026-08-02 12:00 +08:00 |
| 取得 | 2026-11-04、時刻・HTTP Last-Modifiedはsources.jsonに記録 |
| 原典CSV | 75,450バイト、2,932観測行 |
| 郵便番号 | 2,930種類 |
| 更新頻度 | 原典案内は年次。取得日だけで現時点の最新性を保証しない |
| ライセンス | CC BY 4.0。帰属・変更内容は [NOTICE.md](NOTICE.md) |

このデータが提供するのは郵便番号・都市・州の対応です。道路・番地・建物・部屋の全件台帳、実在住所や配達可能性の確認結果ではありません。原典のカタログには郵便サービス記録由来の全国郵便番号一覧とありますが、本収録は独立した全国完全性の照合を実施していません。

## 原文と比較用表記

`records.csv.gz` は次の列を持ちます。

| 列 | 意味 |
|---|---|
| `observation_id` | 原典ハッシュとデータ行番号に限定した内部観測ID |
| `association_id` | 原文の州・都市・郵便番号の組に基づく内部対応ID。政府の識別子ではない |
| `country` | `MY` |
| `postcode` | 先頭ゼロを含む5桁の文字列 |
| `city`、`state` | 原典の文字列をそのまま保持 |
| `city_normalized`、`state_normalized` | NFC化と空白整理だけを行う比較用の列 |
| `source_ref`、`source_row` | 原典の識別とデータ行番号（ヘッダーを含めない1始まり） |

郵便番号だけで行を統合しません。`40160` にはShah AlamとSungai Bulohの2つの都市対応があります。`71000` には州名末尾の空白が異なる原文があります。原文の州ラベルは17種類、空白整理後は16種類です。州・都市のいずれかに空白整理が生じる原典行は4行あり、すべて原文とともに残しています。

ラテン文字であることから英語の公式訳とは判定しません。国の識別、地名翻訳、他の地名台帳との同一性照合も別の処理です。

## 再現・検査

リポジトリのルートから実行します。

```bash
python scripts/import_my_official.py verify --folder registries/official/expansions/MY
python scripts/import_my_official.py build \
  --source registries/official/expansions/MY/sources/postcodes.csv \
  --output /tmp/MY-postcodes-rebuilt \
  --retrieved-at 2026-11-04T10:23:43+00:00 \
  --source-date 2026-06 \
  --source-last-modified 'Sun, 02 Aug 2026 02:44:59 GMT'
```

出力先は新しいディレクトリを指定します。原本・既存の生成先は上書きしません。検査はネットワークを使わず、保存済みCSVのSHA-256・サイズ、全行の変換再現、スキーマ、先頭ゼロ、件数・対応関係を照合します。ハッシュ照合は保存版の同一性を確認するもので、ライブ原典の最新性や利用者が入力した住所の実在性を検証しません。
