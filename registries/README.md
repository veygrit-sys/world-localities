# 地域別データと検証処理

地域ごとにルートへ置いていた10フォルダを、この `registries/` に集約しています。国から探す場合は [国・地域一覧](../countries/README.md) を使用してください。

| フォルダ | 役割 |
|---|---|
| [africa](africa/README.md) | アフリカの地名・行政階層 |
| [asia](asia/README.md) | アジアと原典に記載された補足範囲 |
| [europe](europe/README.md) | 欧州の地名・行政階層 |
| [oceania](oceania/README.md) | オセアニアの地名・行政階層 |
| [north-america](north-america/README.md) | 北部アメリカ |
| [central-america](central-america/README.md) | 中央アメリカ |
| [caribbean](caribbean/README.md) | カリブ海 |
| [south-america](south-america/README.md) | 南アメリカ |
| [americas](americas/README.md) | 上記アメリカ4地域の品質管理・監査。別のデータ全集ではない |
| [official](official/README.md) | 原典固有の公式コード・名称・郵便対応の追加レイヤー |

## 新しい呼び出し方

リポジトリのルートから実行します。

```bash
python registries/europe/query.py --country AT --level 1
python registries/asia/package.py unpack --country JP
python -m localities materialize --registry central-america --country CR
python -m localities layout
```

旧 `<地域>-registry/` は `registries/<地域>/` に移動しました。旧パスを利用している外部スクリプトも更新してください。`localities/` の共有処理と、地域名を指定する共通CLIは維持しています。

各領域の国別ファイル・原典・NOTICE・個別ライセンスを保持し、別出典の行を一つの住所として強制統合していません。アジアと欧州の重複範囲や、地名と公式対応レイヤーの関係は各資料を参照してください。

過去の移行記録・原典に含まれる旧パスや元リポジトリURLは、その時点の証跡として保持します。保存済み米州公式スナップショットの照合では、旧配置を現在の配置に解決してから元のサイズ・SHA-256・Git blob SHAを検査します。
