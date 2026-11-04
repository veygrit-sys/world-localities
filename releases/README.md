# 版別の収録範囲と検証記録

| 領域 | 入口 |
|---|---|
| 日本のローカル配布・復元実証 | [countries/JP/bundle-verification.json](countries/JP/bundle-verification.json) |
| 保存済み配布記録とローカル実物の照合 | [artifact-audit-baseline.json](artifact-audit-baseline.json) |
| 世界全体の対象・不足 | [world-coverage](world-coverage/README.md) |
| 行政区・道路・番地の地域別スナップショット | [hierarchy/catalog.json](hierarchy/catalog.json) |
| 道路・番地の公開記録 | [address-points](address-points/README.md) |

過去の件数・検証結果は該当版の記録です。現在の全国完全性や配達可能性の保証とは扱いません。国別配布の新しい管理方法は [国別管理](../docs/country-modules.md) を参照してください。

`python scripts/artifact_audit.py` で保存済み配布記録とローカル実物の一致を再確認できます。`--artifact-root` で既存アーカイブの保管ディレクトリを指定できます。ローカルにないものは `referenced_not_local`、外部保管先の状態は `not_checked` とし、外部の不存在や紛失を推測しません。
