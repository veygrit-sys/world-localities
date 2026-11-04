# 国・地域別の更新と将来の分離

更新単位は国・地域コード、保管と原典固有処理の境界は `registries/` の各レイヤーです。国別に共通処理を複製せず、中央台帳から既存の処理を呼び出します。[実行方針と完了条件](implementation-strategy.md) に沿って更新します。

## 台帳の役割

| 台帳 | 管理すること |
|---|---|
| [catalog.json](../countries/catalog.json) | 250収集コードの保存先、物理ファイル参照、配布先、次の作業 |
| [modules.json](../countries/modules.json) | 国別の原典レイヤー、共有入力の抽出条件、NOTICE・原典・検査の対応 |
| [registry_catalog.json](../localities/registry_catalog.json) | 地域別領域と共有コードの構成 |

250コードは主権国家数や全国網羅済みの国数ではありません。バミューダ・グリーンランド・サンピエール島とミクロン島の行政名など、共有ファイル内の記録も国コードで選択します。住所形式しかない国、限定的な観測がある国、原典レイヤーがある国を区別します。

`catalog.paths` は物理ファイルの参照で、共有ファイル内の国の判定や単独配布の全依存を表しません。意味上の対応は `modules.layers` と `selector` を参照してください。`NA` はナミビアの文字列として保持します。

## 国別の確認・検証・復元

リポジトリのルートから実行します。

```bash
python -m localities country validate-catalog
python -m localities country inspect --country JP
python -m localities country verify --country JP
python -m localities country verify --country DE
python -m localities country verify --country BM
python -m localities country restore --country JP --output /tmp/JP-country-restored
```

`inspect` は原典レイヤー別に件数・記録された基準日・未解決・利用条件への参照を返します。観測行数を合算して一意住所数にしません。最新性・全国完全性・配達可能性の確認は別に表示します。

`verify` は許可済みのアダプターを使い、元の地域別検証・ハッシュ照合・国の選択を実行します。結果は台帳整合性、保存済み原典の同一性、行の再現性を区別します。レイヤーごとに検査範囲は異なり、未検査は `not_checked`、住所形式しかない国は全体を `unsupported` として返します。失敗・未対応は終了コードも失敗になります。

日本ではアジアの保存済みアーカイブ・変換行の再現と公式レイヤーの保存ハッシュ、ドイツでは欧州の保存ハッシュ・変換行の再現、バミューダでは限定的な行政名と原典参照を検査します。これらの成功は住所精度や配達可能性の証明ではありません。

`restore` は検査後に、明示した新しい出力先へ対象データと共有原典・NOTICEを展開します。元リポジトリや既存出力を上書きしません。出力は選択したデータで、サービス一式ではありません。

従来の `python scripts/country_modules.py validate` は保存パスの整合検査として維持します。国別一覧の同期は `python scripts/render_country_index.py --check` で確認できます。

## 更新と品質の管理

1. `inspect` で保存済みの版・不足・次の作業を確認する。
2. 原典の取得日、原典基準日、公開条件、ハッシュを固定する。
3. 別の作業ディレクトリで変換し、追加・削除・所属・改称の差分を照合する。
4. `verify` と通常PRのオフラインCIを実行する。共通コード変更では関連地域も確認する。
5. 原典・NOTICE・品質記録を更新し、再現できる版を配布する。

台帳の `quality` は台帳追加で品質を引き上げないための未検証値です。実際の件数・未解決・検査結果は国別のレイヤーレポートに記録します。ライブ原典との最新性の照合は通常CIと分離し、未確認は不明のまま保持します。

## 大容量データの配布

既存の圧縮・分割データとGit履歴は維持します。新しい大容量原本や生成索引は、原典の利用条件を確認してから通常Gitと分けて配布します。

日本の先行実証では、明示した2つの保存済み出典レイヤーについて梱包・ハッシュ照合・別ディレクトリへの復元を確認しました。[バンドルの作成・検証・復元](country-bundle.md) と [実行証跡](../releases/countries/JP/bundle-verification.json) を参照してください。

`release_manifests` は実在する公開先を確定してから登録します。現在の日本バンドルの証跡はローカル往復検証で、公開リリースではありません。

公開配布のJSONには `schema_version: 1`、`country`、`version`、`data_schema_version`、40桁の `source_commit`、`notice_path`、`quality_report`、`artifacts` を記録します。各artifactは安全な `path`、HTTPSの `url`、バイト単位の `size`、`sha256` を必須とします。

`python scripts/country_modules.py validate-release --country JP --manifest releases/countries/JP/実際の版.json` は管理情報の形を検査します。実配布ファイルのダウンロード・ハッシュ・NOTICE同梱も別途照合します。

## 国別リポジトリへ分離するとき

原典・共有依存・利用条件・品質記録を国単位で一覧化し、別環境で取得・変換・検証・復元できることを先に確認します。共通コードの版を固定してから公開先と実在する配布を台帳へ登録します。

`storage.kind: external` の参照は40桁コミットに固定し、元と移行先の件数・ハッシュ・検索結果・権利表記を比較します。外部コードの自動実行や最新版への無条件の追随は行いません。形式変更とデータ削除は分離し、戻せる版を残します。
