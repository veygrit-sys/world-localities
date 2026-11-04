# リポジトリ構成

このリポジトリは、データを地域別に保ちながら、地域に依存しない処理だけを
`localities/` に集約します。既存の利用者が参照している地域別パスは安定した公開入口です。

## ディレクトリの責務

| パス | 責務 |
|---|---|
| `localities/` | GeoNames変換、分割ファイル復元、構成検証などの共有コード |
| `*-registry/` | 地域・出典固有のデータ、規則、メタデータ、CLI、互換入口 |
| `official-registry/` | 国別の公式コード・公式名称・郵便対応を扱う追加レイヤー |
| `americas-registry/` | アメリカ4地域を横断する監査・品質サイクル |
| `tests/` | 複数地域またはリポジトリ全体にまたがる回帰テスト |
| `scripts/` | リリース検証などの運用コマンド |
| `docs/` | 横断設計、品質方針、更新計画 |

地域別ディレクトリの一覧と共有コードの利用関係は
[`localities/registry_catalog.json`](../localities/registry_catalog.json)を正とします。
次のコマンドで、登録済みディレクトリ、README、共有モジュール、重複コード規則を検証できます。

```bash
python -m localities layout
```

## 互換性方針

- 地域別の `query.py` と `build.py` は、地域を名前空間とする公開入口として維持します。
- 重複していた地域別 `materialize.py` と `geonames_core.py` は廃止し、`localities/` の単一実装を使います。
- データファイルの移動は、既存のマニフェスト、チェックサム、利用者の相対パスを壊すため、
  コード整理と同じ変更では実施しません。
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
python caribbean-registry/test_caribbean.py -v
python central-america-registry/test_central_registry.py -v
python south-america-registry/test_south_registry.py -v
```
