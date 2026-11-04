# 出典付き地域階層と公式住所取込

各更新を検証してから個別に反映する。既存の地域台帳と住所表示レイヤーは保持する。
全行政区・全道路・全番地の完全網羅は未完了。配達可能性は対象外。

| 地域 | 対象範囲 | 実装・復元手順 |
| --- | ---: | --- |
| south-america | 16 | [south-america](../releases/hierarchy/south-america/README.md) |
| north-america | 6 | [north-america](../releases/hierarchy/north-america/README.md) |
| central-america | 7（MXは北米版参照） | [central-america](../releases/hierarchy/central-america/README.md) |
| caribbean | 28 | [caribbean](../releases/hierarchy/caribbean/README.md) |
| western-europe | 11（M49西欧9＋従来グループGB・IE） | [western-europe](../releases/hierarchy/western-europe/README.md) |

`releases/hierarchy/catalog.json` が反映済みの入口を示す。
地域の大容量原典・索引は別書庫から復元し、Gitコードの共通CLIへ `--data-root` を指定する。
欧州の全体版と部分版は同じ実装を使い、範囲設定を分ける。
原典ID・親参照・言語タグ・先頭ゼロを保持し、同名・座標一致だけで統合しない。
出典の異なる観測数、欧州とアジア、全欧州と部分版の件数を単純に合算しない。

```bash
python3 scripts/hierarchy_cli.py --region south-america -- --help
python3 -m unittest discover -s hierarchy-tests -p 'test_*.py'
```
