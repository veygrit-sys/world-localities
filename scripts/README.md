# スクリプト一覧

コマンドはリポジトリのルートから実行します。最初に各スクリプトの `--help` と対象地域のREADMEを確認してください。取得・変換・出力を伴うコマンドは、入力版と出力先を決めてから実行します。

## 管理・検証の共通入口

| 目的 | 入口 |
|---|---|
| 国別の対象一覧・参照整合性 | [country_modules.py](country_modules.py) |
| 共有コードと地域台帳の構成検査 | `python -m localities layout` |
| 地域階層の操作入口 | [hierarchy_cli.py](hierarchy_cli.py) |
| 階層スナップショット | [hierarchy_snapshot.py](hierarchy_snapshot.py) |
| 分割データの復元 | [restore_data_parts.py](restore_data_parts.py) |
| 住所形式プロファイルの生成 | [compile_address_profiles.py](compile_address_profiles.py) |
| 住所データの公開単位 | [address_release.py](address_release.py) |
| アメリカのスナップショット検証 | [verify_americas_snapshots.py](verify_americas_snapshots.py) |

```bash
python scripts/country_modules.py list
python scripts/country_modules.py validate --country JP
python -m localities layout
```

`verify-migration` は移行直後の固定スナップショットを照合するコマンドです。整理・更新後の現在版を過去の移行元と同一だと検証する用途には使いません。[移行記録](../docs/migration/README.md) を参照してください。

## 出典・地域別の入口

| 対象 | スクリプト |
|---|---|
| 東アジア | [east_asia_sources.py](east_asia_sources.py)、[east_asia_query.py](east_asia_query.py)、[east_asia_fast.py](east_asia_fast.py)、[east_asia_projection.py](east_asia_projection.py) |
| 西欧 | [western_europe_sources.py](western_europe_sources.py) |
| オランダ | [netherlands_bag.py](netherlands_bag.py)、[netherlands_reference_review.py](netherlands_reference_review.py)、[netherlands_gap_review.py](netherlands_gap_review.py) |
| 台湾 | [tw_nlsc_reference.py](tw_nlsc_reference.py) |
| メキシコ | [mx_address_evidence.py](mx_address_evidence.py) |
| カリブ海 | [caribbean_official.py](caribbean_official.py)、[caribbean_osm.py](caribbean_osm.py) |
| OSM取得・照合 | [fetch_osm_evidence.py](fetch_osm_evidence.py)、[verify_osm_evidence.py](verify_osm_evidence.py) |
| OSMの内部処理 | [osm_evidence.py](osm_evidence.py)、[osm_stream.py](osm_stream.py)、[osm_pbf_lite.py](osm_pbf_lite.py) |

地域固有の `build.py`・`query.py` は各 `registries/<地域>/` にあります。[データと利用方法](../docs/guides/data-and-usage.md) から進んでください。

## 追加依存

通常の台帳・構成検査は標準ライブラリで実行できます。OSM処理と空間処理の追加依存は、使用する処理に合わせて導入します。

- OSM: [requirements-osm.txt](requirements-osm.txt)
- カリブ海のOSM・空間処理: [requirements-caribbean-osm.txt](../requirements-caribbean-osm.txt)
