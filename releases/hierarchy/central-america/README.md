# 中米：行政区・道路・割当番地の段階更新

中米7か国（BZ・GT・SV・HN・NI・CR・PA）の出典付き行政階層を反映した。
国連M49の中央アメリカはメキシコを含む8か国であり、MXは既存の
[北米パッケージ](../north-america/README.md)を参照する。今回の件数に重複計上しない。

目標は全行政区・住所用の通り・物理的な道路網・割当番地の完全網羅。
**今回の反映で完全網羅が完了したわけではない。配達可能性は対象外。**
国別・項目別の現在地と次の作業は [coverage.json](coverage.json) に記録する。

2026-10-22の[公開データ追加](enrichment-20261022/README.md)では、8か国分のOSM道路・
住所タグとメキシコのINEGI由来番号資料を別の出典で保持し、コスタリカの現在の地区参照も取得した。
以下の件数は2026-10-17の行政階層スナップショットとして残す。

## 今回のデータ

2026-10-17取得の固定スナップショットを使用する。取得日を各資料の地理的基準年とは扱わない。
HDX COD-AB行政区分表とGeoNames国別地名・言語付き別名を別の名前空間で保持する。

| 国 | COD-ABスナップショットの行政区分 | GeoNamesの集落・都市参照行 |
| --- | --- | ---: |
| BZ | 6地区。市・村の全行政区分は未照合 | 522 |
| GT | 22県・340市町村 | 16,979 |
| SV | 14県・44市町村・262地区 | 4,889 |
| HN | 18県・298市町村 | 12,965 |
| NI | 17県・自治地域・153市町村 | 2,629 |
| CR | 7州・84カントン・492地区 | 5,781 |
| PA | 13上位区分・76地区相当・594コレヒミエント。旧版 | 13,238 |

GeoNamesの集落・都市参照行は計57,003行。これは一意な自治体数や住所数ではない。
HNのCOD-AB集落参照27,969行は別系列で、GeoNamesと合算して場所数にはしない。
20の重複P-codeに対応する40原行は別々に保持する。GTとSVの湖・貯水池も行政区に数えない。
PAは旧版判定を子ノードまで伝播させ、現行全国行政区分として採用しない。

## 復元と実行

原書庫 `Veygrit_CentralAmerica_20261017.zip` のサイズ・SHA-256・99項目を
[archive.json](archive.json) に固定した。原典と生成SQLiteは通常のGitに重複格納しない。
原典の利用条件と取得記録は書庫および [original/LICENSE_DATA.md](original/LICENSE_DATA.md) を参照する。

```bash
python3 scripts/hierarchy_snapshot.py verify --region central-america --archives /path/to/archives
python3 scripts/hierarchy_snapshot.py restore --region central-america --archives /path/to/archives --target /path/to/new-central-america
python3 scripts/hierarchy_cli.py --region central-america --data-root /path/to/new-central-america/Veygrit_CentralAmerica_20261017/address-points build
python3 scripts/hierarchy_cli.py --region central-america --data-root /path/to/new-central-america/Veygrit_CentralAmerica_20261017/address-points loop
python3 scripts/hierarchy_cli.py --region central-america --data-root /path/to/new-central-america/Veygrit_CentralAmerica_20261017/address-points search --country CR --text 'Puerto Jimenez' --namespace codab-cr-v01 --kind canton
```

索引は約186 MiB。コード・原典・規則が変わった索引は利用時に拒否し、再構築を要求する。
原典ID、先頭ゼロ、表記、行位置、言語、明示された親参照を保持する。
同名や座標の一致だけで出典を越えた統合を行わない。

検証はGitに反映したコードで原典全行を再照合する。
新しい検証結果・国別レポートは指定した出力先に保存し、履歴を上書きしない。

```bash
WORLD_LOCALITIES_ADDRESS_ROOT=/path/to/new-central-america/Veygrit_CentralAmerica_20261017/address-points \
  python3 address-points/adapters/centralamerica_validate.py --output /path/to/run/validation.json
python3 -m unittest discover -s hierarchy-tests -p 'test_hierarchy_central_america_*.py'
```

新規原典の再取得は固定レシピから別ディレクトリへ行う。古い原典ファイルがない
Gitチェックアウトからも起動でき、中米以外の地域データやGit管理情報を候補にコピーしない。
再取得後は候補内で構築・原行再照合を行い、版・件数・利用条件を確認する。

```bash
python3 address-points/adapters/centralamerica_fetch.py --output /path/to/new-central-america-candidate
```

実行した確認と今回実行していない検証は [verification.json](verification.json) に区別する。
`original/` 内の説明・ログは元の2026-10-17版の記録であり、今回の実行結果ではない。

## 完全網羅に向けて残るもの

全8か国で現在の全行政階層を公式台帳と照合し、廃止・新設・改編と未接続コードを解消する。
PAの旧版更新、BZの下位行政区、HNの重複コードを独立した課題として残す。

道路は住所用の通りと無名道路を含む物理的な道路網を分け、国・自治体別の担当機関と
収録範囲を確定する。番地は割当元が公表する原番号・接尾辞・状態・街路参照を取得する。
未採番・記述式住所はその状態を保持し、道路沿いの推測や数値範囲の展開で番地を作らない。
全国道路・番地の原典は2026-10-17の原書庫に未収録。追加資料の取得状況は
[公開データ追加](enrichment-20261022/README.md)を参照する。分母不明の収録率を0%や100%にしない。
