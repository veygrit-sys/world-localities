# 西アジアの取得済み原本と検索

2026年11月8日に取得した23原本75,062行と、再利用したOpenSyria 7,953行を、出典ごとに検索できる形で保持しています。GeoNames 215,576行は既存の国別アーカイブから検証して読みます。重複する場所を含むため、合計は一意な住所件数ではありません。

18か国すべてに原本参照層があります。政府直接公開、政府由来の人道参照、第三者地理参照、郵便局、私書箱、統計単位は同じ品質・粒度ではありません。現行全国の公式地名・郵便番号・建物・配達可能性の完成は未証明です。

| 保存先 | 内容 |
|---|---|
| [manifest.json](manifest.json) | 原本URL、出典の役割、版、利用条件、ハッシュ、行数 |
| [originals/](originals/) | 取得バイトを保存した23原本。テキストは可逆gzip |
| [records/](records/) | 原典の行・シート・IDを残す出典別JSONL gzip |
| [evidence/](evidence/) | 出典目録・利用条件の取得時点の記録 |
| [country-status.json](country-status.json) | 18か国の実データ件数と未解決事項 |
| [acquisition.json](acquisition.json) | 取得成功・接続失敗・誤った資源の記録 |
| [reports/source-audit.json](reports/source-audit.json) | 原本再生、粒度、重複コード、親参照、名称候補の監査 |
| [NOTICE.md](NOTICE.md) | 帰属と出典ごとの利用条件 |

リポジトリのルートで実行します。Python 3.11以降の標準ライブラリのみを使用し、取得済みデータからオフラインで再現します。

    python -m localities western-asia verify
    python -m localities western-asia audit --output /tmp/western-asia-audit.json
    python -m localities western-asia build --output /tmp/western-asia.sqlite
    python -m localities western-asia verify-index --db /tmp/western-asia.sqlite
    python -m localities western-asia query --db /tmp/western-asia.sqlite --country CY --postcode 1010
    python -m localities western-asia query --db /tmp/western-asia.sqlite --country JO --postcode 11190
    python -m localities western-asia query --db /tmp/western-asia.sqlite --country QA --source-code QAT006

検索では地名、郵便番号、出典コードのどれか1つを選択します。別レイヤーの検索結果は同一住所として自動統合しません。住所形式の判定APIは従来どおり形式検証に限定し、今回のデータ取込で実在・配達可能性の判定へ引き上げていません。

アゼルバイジャンの公式IABT 6,697コードは原本取得・解析まで実施していますが、公開再配布条件の確認が残るため、公開層には監査集計だけを保存しています。全国公式原本取得済みと、公開可能な全件データとしての収録を区別してください。

詳しい国別の到達点は[進捗・残課題](../../../../docs/plans/western-asia-current-status-20261108.md)を参照してください。
