# 公式名称・郵便番号対応

公式資料の地域IDを中心に、名称と郵便番号を結び付ける追加データです。
表示言語を変えてもIDと郵便関連を維持します。アジア全域の全面対応は未完了です。

| プロファイル | 収録内容 | 対応範囲 |
|---|---|---|
| [JP](JP/README.md) | 日本語・カナ・原典ローマ字、郵便番号124,526行 | 47都道府県、郵便上の1,892市区町村・区、完全7桁番号120,720種類 |
| [TW](TW/README.md) | 郵便当局の中国語・英語371対と郵便関連371行 | 3桁接頭辞368種類。完全6桁番号は未収録 |

各国の `sources.json` に原典URL、更新日、取得日、利用条件、SHA-256を、
`coverage.json` に件数と出力ハッシュを保存しています。全52プロファイルの進捗は
[coverage.json](coverage.json)を参照してください。残る50プロファイルの公式対応は未着手です。
基礎Gazetteerの収録済み件数と、公式対応の完了件数を混同しません。

## 使い方

リポジトリのルートから実行します。Python 3.11以降の標準ライブラリだけを使います。

```bash
python official-registry/query.py --country JP --postal-code 0600000 --language ja-Latn
python official-registry/query.py --country TW --postal-code 300 --language en --include-prefix
python official-registry/build.py verify --country JP
python official-registry/build.py verify --country TW
python -m unittest discover -s tests -p 'test_*.py' -v
```

名称は `entity_id` と `language`、郵便関連は `entity_id` と `country + scheme + code` で接続します。
`source_ref` は国別 `sources.json` の `sources` 内の同名エントリーを参照します。
指定言語がない場合は `missing_requested_language` を返します。
JPのローマ字を英語に付け替えず、国内・国際英語の違いを原典なしに作りません。
TWで6桁を入力しても、明示指定した3桁接頭辞の範囲しか照合しません。
住所の番地・建物・部屋・配達可能性は検証しません。

## 共通アルゴリズムと例外

[romanize.py](romanize.py) の `jp-postal-kana-v1` がカナからローマ字を生成します。
日本郵便の [変換仕様](https://www.post.japanpost.jp/service/search/zipcode/download/roman_shiyou.pdf) を参考にした実装です。
漢字から読みを推測せず、郡・市・区などの境界が不明な複合名は保留します。

原典と完全一致する **295,029項目は文字列を省略**し、70,572項目を原文の例外として保持します。
未照合7,977項目は生成で埋めません。`roman_storage_modes` は都道府県・市区町村・町域の順に
`algorithm`、`literal`、`unavailable` を `|` でつなぎます。
`algorithm` の空欄は、同じ行のカナ・日本語名・役割と指定バージョンで復元します。
`query.py` の `expand_roman` はこの展開を行います。空欄を一律に未収録と扱わないでください。

照合済み121,867行の365,601要素が原典と完全一致することをテストします。
この省略保存は損失のない再現です。未知のカナへ `choose(..., allow_generated=True)` を適用した結果は
`generated_unreviewed` です。原典表記を渡した場合は原典を優先し、生成結果を公式名へ昇格させません。
変換のコードハッシュも記録し、実装変更後は再構築・原典照合を必要とします。

## 再構築

配布済み原典だけでオフライン再構築できます。原典がない場合の `sync.py` は固定ハッシュを検査し、
違う版を無断で取り込まず停止します。

```bash
python official-registry/sync.py
python asia-registry/package.py unpack --country JP
python official-registry/build.py build --country JP --geonames-jp asia-registry/countries/JP/entities.csv.gz
python official-registry/build.py build --country TW
```

JPのGeoNames入力を省略すると候補表は空になります。配布物の再現には上記入力を指定してください。
新しい原典への更新ではハッシュ・日付・未一致を確認してから固定値を更新します。

## 利用条件

JPの派生台帳はODbL-1.0。ABRのCC BY 4.0、日本郵便の郵便番号データ利用条件も保持します。
TWは政府資料開放授權條款第1版です。GeoNames由来の候補はCC BY 4.0の出典を保持します。
追加したプログラムは [MIT](../asia-registry/LICENSE)。第三者データの条件を置き換えません。
各国のREADME・出典メタデータ・利用条件を一緒に配布してください。
