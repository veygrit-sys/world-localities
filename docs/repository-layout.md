# リポジトリ構成

このリポジトリは、データを地域別に保ちながら、地域に依存しない処理だけを
`localities/` に集約します。地域別の配置は `registries/` 配下にまとめ、国別台帳と共有CLIから参照します。

## ディレクトリの責務

| パス | 責務 |
|---|---|
| `localities/` | GeoNames変換、分割ファイル復元、構成検証などの共有コード |
| `registries/<地域>/` | 地域・出典固有のデータ、規則、メタデータ、CLI、互換入口 |
| `registries/official/` | 国別の公式コード・公式名称・郵便対応を扱う追加レイヤー |
| `registries/americas/` | アメリカ4地域を横断する監査・品質サイクル |
| `tests/` | 複数地域またはリポジトリ全体にまたがる回帰テスト |
| `scripts/` | リリース検証などの運用コマンド |
| `docs/` | 横断設計、品質方針、更新計画 |

## 資料と操作の入口

ルートREADMEは目的別の案内に絞り、収録データ・地域別の詳細な利用説明は
[`docs/guides/data-and-usage.md`](guides/data-and-usage.md) にまとめています。

| パス | 内容 |
|---|---|
| [`countries/README.md`](../countries/README.md) | 250国・地域から既存データを探す一覧 |
| [`docs/README.md`](README.md) | 資料全体の目次 |
| [`docs/guides/`](guides/data-and-usage.md) | データ・利用方法の詳細 |
| [`docs/plans/`](plans/README.md) | 原典取得・国別拡充の計画 |
| [`docs/learning/`](learning/README.md) | 学習対象・評価方法の説明 |
| [`docs/migration/`](migration/README.md) | 固定した移行元と照合記録 |
| [`scripts/README.md`](../scripts/README.md) | 操作目的別のスクリプト一覧 |
| [`releases/README.md`](../releases/README.md) | 版別記録の入口 |
| [`training/README.md`](../training/README.md) | 学習設定の入口 |

移動した計画資料の旧パスには案内だけを残し、本文の二重管理を避けます。
`docs/migration/` の元資料・チェックサムは当時のスナップショットとして保持します。
地域別データとCLIは `registries/<地域>/` へ移動しています。内部の国別構成とファイル内容は保持し、呼び出しパスを更新します。

地域別ディレクトリの一覧と共有コードの利用関係は
[`localities/registry_catalog.json`](../localities/registry_catalog.json)を正とします。
次のコマンドで、登録済みディレクトリ、README、共有モジュール、重複コード規則を検証できます。

```bash
python -m localities layout
```

## 互換性方針

- 地域別の `query.py` と `build.py` は、地域を名前空間とする公開入口として維持します。
- 重複していた地域別 `materialize.py` と `geonames_core.py` は廃止し、`localities/` の単一実装を使います。
- 旧 `*-registry/` のCLIは `registries/<地域>/` から呼び出します。管理台帳・共有コード・CI・内部リンクも新しい配置に合わせます。
- 保存済み原典や過去の照合記録に含まれる旧パスは歴史資料として保持し、必要な検証処理では配置の対応を明示して解決します。
- 出典固有の意味や品質判定は、見た目が似ていても無理に共通化しません。

## 共有化の基準

共有コードへ移すのは、複数地域で同じ入出力契約と安全条件を持つ処理です。
現在は次の3種類を共有しています。

1. `localities.geonames`: GeoNamesのA/P行を、出典IDと親候補を保持した共通行へ変換する処理
2. `localities.materialize`: 分割済み大容量ファイルを、サイズとSHA-256を検証して原子的に復元する処理
3. `localities.query`: IDや表記を推測せずに行う共通フィルターとページング

## 同名ファイルの方針

国別の `metadata.json`、`entities.csv.gz`、`admin1.csv` は、それぞれの国ディレクトリが
名前空間なので重複ではありません。地域別の `build.py` と `query.py` も、出典・公開範囲・
CLI契約が異なるため意図した同名入口です。

一方、同じ役割のPython実装を複数地域へコピーすることは禁止します。
`python -m localities layout` は、許可されていない同名Pythonファイルと、内容が完全一致する
Pythonファイルを検出して失敗します。例外は `registry_catalog.json` の
`scoped_python_basenames` に理由付きで記録します。

国別公式データの照合、郵便番号の意味、言語選択、公開範囲は地域・出典ごとの差が大きいため、
各レジストリに残します。

## 変更時の確認

共有コードを変更した場合は、最低限、構成テストと3地域の回帰テストを実行します。

```bash
python -m unittest discover -s tests -p 'test_repository_layout.py' -v
python -m unittest discover -s tests -p 'test_split_materialization.py' -v
python registries/caribbean/test_caribbean.py -v
python registries/central-america/test_central_registry.py -v
python registries/south-america/test_south_registry.py -v
```
