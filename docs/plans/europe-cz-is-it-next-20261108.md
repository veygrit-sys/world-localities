# 欧州の次段階：チェコ・アイスランド実原典とイタリアの取得状況（2026-11-08）

**判断の基準：** コードがある／合成テストに合格／実際の公式ファイルを取得／全件SQLite取込／住所と配達が検証された、という5つは異なります。今回は新規の本番実取込がアイスランドで成功しました。全57国・地域の配達可能性は引き続き未検証です。証跡の正本は [機械可読レシート](europe-cz-is-it-source-receipts-20261108.json)。

## アイスランド（IS）— 公式全国CSVを実取込・索引検証

公式HMS [Staðfangaskrá](https://hms.is/gogn-og-maelabord/grunngogntilnidurhals/stadfangaskra) のCSVを2026-11-08にGitHub Actionsで取得。公表側は毎週日曜日に更新すると説明しています。

| 実物検証 | 結果 |
|---|---:|
| 元ファイル | 38,151,464 bytes |
| SHA-256 | `561e8ea2be420a797e13cf50229619b87c00984ebdc4f931ab0b5a78bc25bff5` |
| ソース住所点ID（HNITNUM） | **139,795件、重複0** |
| ソース住所ID（HEINUM） | **137,624種類** |
| 住所点に郵便番号記載なし | 21件 |
| 住所点に番地記載なし | 24,310件 |
| 地名・道路名欄が空 | 3件 |
| WGS84座標欄が空 | 0件 |
| 座標の確認状態0（未確認） | **100,168件** |
| 確認状態1（確認済み） | **31,597件** |

HMSの **HNITNUMは座標点、HEINUMは住所識別子**。1住所に複数座標点が存在し得るので、139,795件を一意の住所数とは言わない。確認状態0の座標を確実な住所位置として扱わない。確認状態1でも配達可能性の保証はない。

[実際の全国取込・SQLite全件整合性検証](https://github.com/veygrit-sys/world-localities/actions/runs/42418793252) はPASS。スクリプト [hms_iceland_official.py](../../scripts/hms_iceland_official.py) はID・郵便・座標・品質区分を保持し、ソースのフリーテキスト `ATH` や作業員識別子 `NOTNR` をコピーしない。週次ZIP/CSV版を互いに上書きせず比較する `diff` に対応。

**保管上の制限：** コードとレシートのみGitに保存。原本とSQLiteはGitHub Actions実行時に取得・生成した実物で、元CSV・SQLite全体をGit本体や外部へ再配布していない。HMSデータの下流再配布条件と永続保存先の確定は今後の作業。アクション成果物には検証レポートのみ収録。

## チェコ（CZ）— 検証済み索引の回収を実行

2026-10-31のČÚZK RÚIAN全国CSV ZIP：6,258市町村ファイル、住所点3,023,585件、重複0。[既存PR #30](https://github.com/veygrit-sys/world-localities/pull/30)で公式全件取込成功。

元原本SHA-256：`56dc1392033cc6ab21e7f2bafc553c2837d49e62049a60a0f238a0ba83c27877`。

[既存の正式出力](https://github.com/veygrit-sys/world-localities/actions/runs/42229842630)のアーティファクトを実際に再取得し、圧縮SQLiteのSHA-256が同梱の`SHA256SUMS`と一致することを再確認。圧縮SQLiteのサイズ235,679,778 bytes、SHA-256：`3f6bf0588e45e9a2451b3c262f5e84e5391391c1b806aadd3ebff4a1b312714a`。

**長期保存は未完了。** GitHub Actionsの出力は2026-11-20までの保持期限で、別途回収したコピーがあっても外部の独立したバックアップ保管庫で長期保全を確認できるまでは完了扱いしない。CC BY 4.0の出典・対象日・チェックサムを必ず併記する。

## イタリア（IT）— 正規配布経路は判明、取得は未成功

Agenzia delle Entrate / ISTAT の [ANNCSU公開配布ページ](https://anncsu.gov.it/it/consultazione-dellarchivio/open-data/Accedi-ai-servizi-di-dowload-massivo-in-Open-data/)には、全国・地域別の道路名簿（Stradario）と番地名簿（Indirizzario）が存在する。CSVを月次ZIPで公開する旨が公表されている。

GitHub Actionsで公式のアブルッツォ州のダウンロードURLを直接確認した結果は **HTTP 406 Not Acceptable**。[アクセス調査実行](https://github.com/veygrit-sys/world-localities/actions/runs/42418793252)。**実ファイル取得0件**。アクセス制限・CAPTCHA・ログインの無断回避はしない。正規の提供方式・公式サポート・別の公式ミラーを調べ、実原典の列・道路IDと番地IDを確定してからロードする。

## 同時に残る制約

- **セルビア RS・スペイン ES：** [PR #29](https://github.com/veygrit-sys/world-localities/pull/29) は未統合。RGZ全国道路/番地CSVの通信タイムアウト、CartoCiudad県別GeoPackage配布のHTTP403。公式全国取込の成功とは呼ばない。
- **PR #8：** [LT/LV/SI/HR/AT/SE](https://github.com/veygrit-sys/world-localities/pull/8) の旧版アダプターは未統合。既存スウェーデン・バルカン共通コードと比較し、重複部分を除いた差分のみ統合。
- **配送利用：** 出典の品質区分、郵便、道路、番地、独立したサンプル検証、配送業者APIの順に合格範囲を分離。座標・地名の有無だけで配達可能と判断しない。

## 再現コマンド

公式HMS CSVを適法に入手したローカル作業ディレクトリで：

```bash
python scripts/hms_iceland_official.py ingest \
  --input /secure/Stadfangaskra.csv --output /secure/is-hms.sqlite \
  --receipt /secure/is-hms-source-receipt.json
python scripts/hms_iceland_official.py verify \
  --db /secure/is-hms.sqlite --receipt /secure/is-hms-source-receipt.json
python scripts/hms_iceland_official.py diff \
  --old /secure/is-hms-prior.sqlite --new /secure/is-hms.sqlite
```

ファイルを保存済み版のSHA-256で固定して再解析する場合は `ingest --expected-sha256 <sha256>` を使います。新しい週次スナップショットを同一の固定版と誤認しないよう、別の出力先を指定してください。
