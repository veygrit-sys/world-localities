# Veygrit 中米データパック

2026年10月17日版。ベリーズ、グアテマラ、エルサルバドル、ホンジュラス、ニカラグア、コスタリカ、パナマの7か国を処理します。

## 対象と完成範囲

- **上位の行政区分、集落・都市の参照検索、原典コードに基づく親子照合**を実装しました。
- 7か国すべてのGeoNames国別データ・言語付き別名、およびHDX COD-AB行政区分表を収録しています。
- メキシコは前回の `Veygrit_NorthAmerica_20261017.zip` に収録済みです。国連M49ではメキシコを含む中央アメリカ8か国ですが、本版のループと件数は重複を避けた7か国です。カリブ地域は含みません。
- **全国の街路・番地の実在検証は未対応です。** 建物名・部屋番号は自動入力しません。郵便番号の割当や配達可否も保証しません。
- パナマは現行行政区分との不足・階層差が残っています。検索できることを現行全国対応とは扱わず、機械可読な要確認状態を返します。

これはデータと実行コードをまとめた独立パックです。GitHubへの反映やVeygrit本番サービスへの接続・公開は行っていません。

## 実行

Python 3.10以降の標準ライブラリだけで動きます。ZIPを展開し、その直下で実行してください。初回にSQLite索引を構築します。生成される索引は約186 MiBです。元データ・コードの変更後は再構築が必要です。

```bash
python3 address-points/adapters/centralamerica.py build
python3 address-points/adapters/centralamerica.py loop
```

`loop` は BZ → GT → SV → HN → NI → CR → PA の順で一巡し、国別結果を返します。保存する場合:

```bash
python3 address-points/adapters/centralamerica.py loop --output address-points/CENTRAL_AMERICA_COUNTRIES_LOOP.json
```

原典のサイズ・SHA-256と必須ファイルの揃いを確認:

```bash
python3 address-points/adapters/centralamerica.py verify-sources
```

### 検索と階層

```bash
python3 address-points/adapters/centralamerica.py search --country CR --text "Puerto Jimenez" --namespace codab-cr-v01 --kind canton
python3 address-points/adapters/centralamerica.py children --parent codab-sv-v02:adm2:SV10001 --kind district
python3 address-points/adapters/centralamerica.py hierarchy --id codab-sv-v02:adm3:SV10001005
python3 address-points/adapters/centralamerica.py validate-path --country SV --input examples/sv_san_salvador_path.json
python3 address-points/adapters/centralamerica.py validate-path --country SV --input examples/sv_wrong_municipality_path.json
```

最後の例は、San Salvador地区をSan Salvador Este市町村へ誤って接続する入力です。`review_required` として拒否します。`source_path_consistent` は原典の親子関係と矛盾しないという意味で、住所の実在を証明しません。

`search` は国コードを必須とします。`--namespace`、`--kind`、`--parent` で絞り込めます。`children`、`search`、`names`、`observations` は `--limit` と `--offset` に対応し、`has_more` と `next_offset` を返します。

### 原行・別名・問題の確認

```bash
python3 address-points/adapters/centralamerica.py record --id codab-hn-v01:place:HN020831003:row:1569
python3 address-points/adapters/centralamerica.py observations --id codab-hn-v01:place:HN020831003:row:1571
python3 address-points/adapters/centralamerica.py names --id codab-cr-v01:adm2:CR613 --language es
python3 address-points/adapters/centralamerica.py issues --country HN --output honduras-issues.jsonl
python3 address-points/adapters/centralamerica.py postcode --country NI --value 12005
```

## 同一性と上位階層の扱い

1. GeoNamesとCOD-ABを別の名前空間に置きます。数字や地名が同じだけでは統合しません。例えばグアテマラのGeoNames行政コードと国別P-codeを見た目で結合しません。
2. 原典が示す親コードの組み合わせを照合します。参照先不明・組み合わせ矛盾・重複は問題として残します。上位ノードの問題も子の階層結果へ伝えます。
3. 湖・貯水池を行政区分表の行数からそのまま市町村に数えません。グアテマラの2行、エルサルバドルの市町村相当4行・地区相当4行を `cartographic_water_area` として保持します。`La Laguna` という正式な地区などを名前だけで除外しません。
4. ホンジュラスでは20の集落P-codeに重複があり、40行を別レコードとして保持します。曖昧なコードには `:row:行番号` を付け、`duplicate_source_pcode` を返します。この行番号は収録スナップショット内の位置であり、将来版に共通の恒久IDではありません。
5. 地名の原表記・アクセント・原コード・言語タグを保持します。検索用のアクセント除去は同一性判定や表示名の書換えに使いません。歴史名・将来開始名・リンク等を現行地名の別名に混ぜません。
6. 地図形状での包含判定は行いません。複数階層を飛ばした原典の明示参照は保持しますが、欠けた行政区分を自動生成しません。

## 検証

60件の機能テスト、32原典オブジェクトの整合確認、16系統・91,044原行の再照合、7か国の別名再照合を実施しています。17ワークシート・30,419行・545,448セルを別の読取実装でも照合しました。国ごとの実データ検索、誤った親の拒否、パナマの旧版判定、ホンジュラスの重複保持も確認しています。

```bash
python3 address-points/adapters/centralamerica_validate.py
```

機能テスト・整合検査の `PASS` と、データの完全性は別です。81件の原典・版・分類に関する確認事項は未解消のまま可視化しています。町名・集落名は原典別のレコードであり、出典間で重複排除した地理的な場所数ではありません。

任意の独立XLSX読取チェックは `tests/check_xlsx_readback.py` です。こちらだけ `tests/requirements-optional.txt` のopenpyxlが必要です。通常の構築・検索・検証には不要です。

## 次回の再取得

確定版を上書きせず、新しい候補ディレクトリへ取得します。

```bash
python3 address-points/adapters/centralamerica_fetch.py --output ../Veygrit_CentralAmerica_candidate
```

取得失敗、ライセンス表示変更、必須シート・版・行政件数の変更は確認が必要です。候補に移動して `build` と `centralamerica_validate.py` を実行してください。国別の件数、湖の例外コード、行政改編、郵便番号参照を確認してから採用します。再取得候補の古い説明文を新たな検証結果と読み替えないでください。今回、将来の一括再取得をネットワーク経由で完走させたという意味ではありません。

## 同梱物

- `COUNTRY_RESULTS_JA.md`: 国別の実測件数と不足。
- `POSTAL_REFERENCE_JA.md`: 郵便番号の形式確認と保留条件。
- `LICENSE_DATA.md`: 原典・配布元・利用条件の表示。
- `address-points/sources/CENTRALAMERICA/`: 原典ZIP、XLSX、参照表、カタログJSONと取得記録。
- `address-points/reports/countries/`: 各国の階層・問題一覧。
- `address-points/CENTRAL_AMERICA_VALIDATION.json`: 全件再照合結果。
- `tests/`: 機能テスト、実行ログ、CLI・別方式の表読取確認結果。
- `MANIFEST.json`: 配布ファイルのハッシュとサイズ。

生成SQLiteと一時ファイルはZIPに含めません。原典とコードから構築できます。
