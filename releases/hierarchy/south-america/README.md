# south-america: 出典付き階層パッケージ

収集範囲は16の国・地域。正確なコードは `archive.json` と設定ファイルを参照する。
この区分は保存済みパッケージの収集範囲であり、既存台帳のM49分類を変更しない。
原典のID・親参照・言語・先頭ゼロを保持し、同名や座標一致だけで地物を統合しない。
全行政区・道路・番地の完全網羅は未確認。配達可能性は今回の対象外。

## コードとデータ

取込・検索・階層・全対象巡回・検証のコードを address-points/adapters/ に収録した。
大容量の原典と索引はGitに含めない。原書庫のサイズ・SHA-256・項目数を固定し、
元の説明と検証記録を `original/` に残した。当時の検証結果と今回のテストは区別する。

```bash
python3 scripts/hierarchy_snapshot.py verify --region south-america --archives /path/to/archives
python3 scripts/hierarchy_snapshot.py restore --region south-america --archives /path/to/archives --target /path/to/new-south-america
python3 scripts/hierarchy_cli.py --region south-america --data-root /path/to/new-south-america/Veygrit_SouthAmerica_20261017/address-points search --country AR --text EXAMPLE
```

`EXAMPLE` は検索語の入力例であり、実在する地名や住所を生成したものではない。
復元先は未作成のフォルダを指定する。複数地域に現れる同じ出典IDや観測を単純合算しない。
欧州全体の圧縮索引は復元先で `python3 unpack_europe_index.py` を先に実行する。
新しい原典取得は確定版の外に候補を作り、全行照合が終わるまで未検証として扱う。
`verification.json` が今回実行した試験と実行していない検証を示す。
