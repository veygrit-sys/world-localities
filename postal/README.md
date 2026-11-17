# 世界の郵便番号を段階的に保存する

250国・地域コードを収集対象とする、原典保存・検索・再検証のレイヤーです。国家数や全国網羅を達成した数とは区別します。

## 段階と完了条件

| 段階 | 保存・追加する内容 | 完了条件 |
|---|---|---|
| 1 基礎保存 | 世界全体の台帳、公開原本、既存日本・台湾の原典 | 原本ハッシュと全行を再検証し、未収集も記録 |
| 2 公式補強 | 日本・中国・台湾、CA/GB/NLの完全桁版を先行し、各国の郵便当局原典へ拡大 | 利用条件・対象範囲・取得版・原典との差分を確認 |
| 3 不足・特殊制度 | 未収録国、大口事業所、私書箱、郵便局、軍・外交、経路限定、制度非採用 | 完全番号・接頭辞・用途限定・制度なし・取得不可を根拠付きで区別 |
| 4 継続管理 | 新版、廃止・変更・統合、復元・差分 | 旧版を残して新しい固定版を追加し、国別の網羅率と最新性を再評価 |

**全世界の現行番号を網羅した状態にはまだ到達していません。** 非公開・利用制限があるデータを公開原本だけで補えない場合も、対象から外さず調査待ちに残します。書式から実在番号を総当たり生成しません。

## 第1段階の保存範囲（2026-11-18）

| 集計 | 値 | 意味 |
|---|---:|---|
| 収集対象 | 250国・地域 | 既存の国別台帳に合わせた管理単位 |
| 原典観測がある範囲 | 125国・地域 | 部分番号・特殊コードも含み、完全対応数ではない |
| 原典調査待ち | 125国・地域 | 制度なしとは判断しない |
| 原典のデータ行 | 1,961,648行 | 複数原典・地名との対応を残した観測行数 |
| 国＋原文の番号文字列 | 1,205,836組 | 異表記や接頭辞も含み、現行完全番号の一意件数ではない |

内訳はGeoNames公開原本124国・地域1,836,751行、日本郵便原本124,526行、台湾の既存接頭辞台帳371行です。[catalog.json](catalog.json) に全250コードを、[sources.json](sources.json) に固定原典・利用条件・制約を記録しています。

日本郵便は2026-09-30版で大口事業所番号を含みません。台湾は3桁接頭辞のみで、完全6桁番号を生成しません。既存データを上書きせず、出典別の原本と行番号を保持します。

## 番号の種類

| `code_kind` | 扱い |
|---|---|
| `official_full` | 郵便当局の固定原本の完全桁。全国完全性・現行性は別評価 |
| `source_reported` | 原典掲載値。独立した公式確認は未実施 |
| `prefix` | 接頭辞。CA/GB/NL/CL/IE/MTと台湾の今回の原典 |
| `aggregated` | 集約番号。中国の今回の原典 |
| `partial` | 一部収録。ブラジルの今回の原典 |
| `partial_or_legacy` | 部分・旧方式。アルゼンチンの今回の原典 |
| `routing_or_unreviewed` | 国内郵便番号と同一視しない特殊・未確認値。今回のAE/HK/MO |

通常のGeoNames原本はCA/GB/NLの完全桁版を含みません。CL/CN/IE/MT/AR/BRにも原典上の制約があります。HK/MOの999077/999078は中国本土発の経路に関する値で、国内郵便番号として使えると判断しません。AEの観測も意味を確認するまで保留します。

先頭ゼロ・空白・ハイフン・英字を原文どおり保持します。一つの番号に複数の地名があれば全候補を返し、原典間の異表記を暗黙に同一視しません。国別の制度状況は現在 `unreviewed` とし、未収録から「制度なし」を推定しません。

## コマンド

Python 3.11以降の標準ライブラリだけを使います。

```bash
python scripts/world_postcodes.py status
python scripts/world_postcodes.py verify
python scripts/world_postcodes.py lookup --country JP --code 0600000 --limit 5
python scripts/world_postcodes.py lookup --country CA --code T0A --include-partial
python scripts/world_postcodes.py build
python -m unittest discover -s tests -p 'test_world_postcodes.py' -v
python -m unittest discover -s tests -p 'test_postal_capture.py' -v
```

検索は原典の番号文字列との完全一致です。接頭辞は標準検索から除外し、`--include-partial` でも不足桁を補いません。原典掲載値の一致は、現行性・完全住所・配達可能性の検証ではありません。現在は原本走査で、常設API向け索引は後続工程です。

## 保存と更新

`postal/sources/geonames/20261118/allCountries.zip` に取得原本約20 MBを保存します。国別に同じ内容を重複保存せず、同じ原本から国別に読み出します。日本・台湾は既存の保存原本を参照します。

`capture` は固定URL・バイト数・SHA-256を満たす原本だけ保存します。配布元が新版へ変われば停止し、既存原本を上書きしません。新しい取得は保存先・ハッシュ・対象範囲をレビューして追加します。

GitHubの `codex/postal-*` 作業ブランチでは [原本保存](../.github/workflows/postal-capture.yml) が取得・全行検査後、原本と台帳だけを同じブランチへコミットします。mainへの直接書込み・定期実行は行いません。[PR品質検査](../.github/workflows/postal-quality.yml) は保存済み原本を再検証します。

## 出典

[NOTICE.md](NOTICE.md) と各原典の利用条件を一緒に保持してください。原本の同一性、国別網羅、現在の制度、配達可能性を分けて確認します。

- [GeoNames配布一覧](https://download.geonames.org/export/zip/)、[仕様・制約](https://download.geonames.org/export/zip/readme.txt)、[国別原典候補](https://www.geonames.org/postal-codes-sources.html)
- [UPU Addressing Knowledge Centre](https://www.upu.int/UPU/media/upu/documents/PostCode/General-Addressing-Issues.pdf)
- [Macao Post FAQ](https://www.ctt.gov.mo/MacauPost/Contents/faq.aspx?lang=en-us)
