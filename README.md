# World Localities

世界の住所検証・住所翻訳・住所を使う通信基盤と、将来の学習用データに向けた原典付きデータ基盤です。

## 目的から探す

| 目的 | 入口 |
|---|---|
| 国・地域から探す | [250国・地域の一覧](countries/README.md) |
| 収録データと利用方法を調べる | [データと利用方法](docs/guides/data-and-usage.md) |
| 改善の順序を確認する | [実行方針](docs/implementation-strategy.md) |
| 国別に更新・配布する | [国別管理と分離手順](docs/country-modules.md) |
| 住所の入力・表記形式を扱う | [住所形式レイヤー](addressing/README.md) |
| 実行コマンドを探す | [スクリプト一覧](scripts/README.md) |
| 設計・計画資料を探す | [資料一覧](docs/README.md) |
| 出典と移行を確認する | [移行記録](docs/migration/README.md) |

## 最初の確認

リポジトリのルートから実行します。Python 3.11以降を使用します。

```bash
python -m localities country validate-catalog
python -m localities country inspect --country JP
python -m localities country verify --country JP
python -m localities layout
```

国別検証は保存済み原典・変換行・共有入力の対応を、レイヤーごとに区別して返します。未検査の最新性・全国完全性・配達可能性は引き上げません。

## ファイルの役割

| 領域 | 内容 |
|---|---|
| `countries/` | 国・地域の入口と機械可読の管理台帳 |
| `registries/` | 地域・原典固有のデータ、出典、検証・検索処理 |
| `localities/` | 共通処理と地域台帳の構成定義 |
| `addressing/` | 国・言語別の住所形式と互換処理 |
| `address-points/` | 道路・番地などの出典別アダプター |
| `scripts/` | 取得・変換・検索・検証の操作入口 |
| `tests/`、`hierarchy-tests/` | 共通回帰テストと地域階層テスト |
| `releases/` | 版ごとの収録範囲・品質・公開記録 |
| `docs/` | 利用ガイド、設計、計画、移行記録 |
| `training/` | 学習計画と設定 |

地域別の入口は [registries/](registries/README.md) に集約しています。旧 `<地域>-registry/` のコマンドは `registries/<地域>/` へ更新してください。詳細は [リポジトリ構成](docs/repository-layout.md) を参照してください。

## 収録範囲と利用条件

国別台帳の250コードは収集対象の管理単位で、主権国家数や全国網羅済みの国数ではありません。データの全国完全性・最新性・翻訳精度・配達可能性は別途評価します。モデル学習は未実施です。

原典ごとのNOTICE・ライセンス・取得時点を確認してください。全体へ新しい一律ライセンスは付与していません。元リポジトリと固定版は [移行記録](docs/migration/README.md) に記載しています。
