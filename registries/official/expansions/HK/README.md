# 香港 ALS 公式住所観測レイヤー

香港政府 Digital Policy Office の Address Lookup Service (ALS) から取得した原本 ZIP のうち、18地区の **2D 建物・住所観測182,254行**を収録する。CSU 建物識別子は159,427種類あり、8,211識別子に複数行がある。住所の総数や一意な配達先の総数には換算しない。

| ファイル | 内容 |
| --- | --- |
| `records.csv.gz` | 決定的 gzip CSV。原文の繁体字・英語、CSU、GeoAddress、元メンバー名と行番号、座標、完全な元 Feature を保持 |
| `coverage.json` | 件数・検索列・CSV のバイト数と SHA-256・品質上の限定 |
| `sources.json` | 公式 URL、取得日、更新日の意味、許諾、原本とメンバーごとの受領記録 |
| `sources/ALS-GeoJSON.zip` | 公式原本20,777,483 bytes。SHA-256 `4549e4f774224abdef062cb6ffaa7e75f0d8dc02187a64bc6c05434472b6f577` |
| `sources/als-geojson.schema.json` | 公式スキーマの取得時スナップショット |
| `sources/data-gov-hk-terms.html` | DATA.GOV.HK 利用条件の取得時スナップショット |
| `verification.json` | 保存済み原本から全18地区を再生した検証結果 |

原本に含まれる public-rental-housing 3D メンバーは ZIP 内にそのまま保存するが、読み込み・正規化・検索の対象に含めない。階・部屋の網羅性を示すレイヤーではない。

`observation_id` は元メンバー名と1始まりの行番号から導くスナップショット内の識別子である。次版で行が変われば同じ住所の識別子が変わり得る。公式の `CsuId` は建物の識別子であり、一意な住所・住戸・配達先の識別子ではない。`GeoAddress` と異なる場合もそれぞれの原文を保存する。

番地の `BuildingNoFrom` / `BuildingNoTo` は英字や範囲を含む元の文字列として `feature_json` に保持する。英語の道路名等が空の場合は空のままにする。中国語や他の項目を英語の道路名として補完しない。WGS84 座標は原本の経度・緯度を使用し、HK1980 座標も別列に保存する。座標が供給されない2行は欠損のまま残し、推定しない。

全国網羅性、全建物の現存、最新性、配送可否、住戸網羅性はいずれも未検証。カタログの更新日2026-10-23は個々の住所の有効日ではない。原本の再取得による追試には更新後のデータが返る可能性があるため、過去版の厳密な追試には同梱 ZIP を使う。

リポジトリのルートから検証する。

```sh
python scripts/import_hk_official.py verify --folder registries/official/expansions/HK
python -m unittest discover -s tests -p test_hk_official_expansion.py -v
```

原本から新しい出力先へ再構築する。既存の出力先は上書きしない。

```sh
python scripts/import_hk_official.py build \
  --source registries/official/expansions/HK/sources/ALS-GeoJSON.zip \
  --schema registries/official/expansions/HK/sources/als-geojson.schema.json \
  --terms registries/official/expansions/HK/sources/data-gov-hk-terms.html \
  --retrieved-at 2026-11-04 \
  --output /tmp/hk-als-rebuilt
```

`verify(folder, source_path=None)` は省略時に同梱 ZIP を使用し、全対象行を再正規化して一致を確認する。原本なしの受領記録・派生行のみの検証では `source_replay` を未実行として報告する。正規化データは31,194,958 bytes、SHA-256 `9fb279bbfa846866f57feb551816f739cb22bb1da96e7ffc9bb382027a733fd8`。

出典・利用条件は [NOTICE.md](NOTICE.md) を参照。
