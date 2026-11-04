# アフリカの行政区画・都市・集落データ

2026-09-26取得の **GeoNames由来の基礎データ**です。国連M49のアフリカ分類に含まれる
**60か国・地域（54か国＋6地域）**を収録しています。各国の公式自治体名簿を全件確認した完成版ではありません。

| 収録・検証項目 | 件数 |
|---|---:|
| 国・地域 | 60 |
| 行政区画：原典のADM1〜ADM5 | 50,050 |
| 都市・集落等：原典のP分類、歴史的地名等を含む | 530,633 |
| 上記以外の行政・領域関係の地物 | 3,455 |
| 全収録レコード | 584,138 |
| 原典の種別に基づく住所候補 | 526,214 |
| 行政コードがあるものの、直接の親を解決できない行 | 5,193 |
| 行政所属がなく国の範囲だけを保持する地名 | 13,709 |
| ADM1参照を解決できない都市・集落等 | 14,769 |
| ファイル・国別の整合性検証 | 780項目、エラー0 |

未解決件数の各列は一部重複するため合計しません。親の未解決はデータの既知の欠落であり、
「エラー0」はそれらがすべて解消した意味ではありません。人口による足切りはしていません。
行政の階層は国ごとに意味が異なり、**50,050を自治体政府の数として扱いません**。

## ファイル

| パス | 内容 |
|---|---|
| `countries/CC/entities.csv.gz` | その国・地域の全収録行。UTF-8のCSVをgzip圧縮 |
| `countries/CC/admin1.csv` | ADM1の閲覧用一覧。全収録行からの重複投影 |
| `countries/CC/metadata.json` | 原典URL、原典ZIPのSHA-256、件数、出力ハッシュ、既知の課題 |
| [coverage.csv](coverage.csv) | 60か国・地域の収録件数と未解決件数 |
| [scope.json](scope.json) | 国・地域と国連M49の地域分類、国の参照ID |
| [manifest.json](manifest.json) | 集計と国別メタデータのハッシュ |
| [verification.json](verification.json) | 全件検証結果と国別の再構築結果 |
| [source_freshness.json](source_freshness.json) | 公式資料との行政改編差異を確認した箇所 |
| [schema.json](schema.json) | CSVの列・意味・欠損値の定義 |

国・地域コードは `scope.json` の一覧が正です。西サハラ、レユニオン、マヨット、
セントヘレナ、英領インド洋地域、フランス領南方地域を含みます。
IOとTFはGeoNamesの大陸欄と国連の統計的地域分類が異なるため、両方の分類を残しています。
EHの国・地域プロフィールは `status=disputed` です。帰属や国境を独自に変更していません。

## データの読み方

`id=gn:<geonameid>` は原典に由来するIDです。国の参照IDは `country:CC` で、
プロフィールは `scope.json` にあります。これらの参照用プロフィールは584,138行に加算していません。
原典の国そのものを表す地物行と国コードの参照プロフィールは、役割の異なるレコードです。

`kind` は `admin_subdivision` / `locality` / `other_admin_feature`。
`admin_level` は原典がADM1〜ADM5と分類した場合だけ設定します。
`parent_id` は完全に一致する国・行政区画コードで解決し、名称や座標の近さでは結び付けません。
中間階層が欠けた場合、州を直接の親に代入しません。確認できた `state_id` は別に残します。
`parent_relation=country_scope_only` は国の範囲が分かるという意味で、直轄自治体を意味しません。

`admin1_code` 等は **GeoNamesの原典コード**であり、ISO 3166-2や各国の公式自治体コードとは限りません。
数値のように見えても文字列として読み、先頭ゼロを保持してください。
`name` は原典表記、`asciiname` はASCII表記、`alternatenames` は言語タグのない別名列です。
現地表記を保持しますが、文字列だけから英語・現地語・公用語を推定しません。
国名の `name_en` だけは国連の英語表記です。言語付き別名表の追加は今後の拡張です。

緯度経度はWGS84の代表点です。境界ポリゴンや配達入口ではありません。
`modification_date` は原典レコードの変更日で、法的な行政改編日ではありません。
人口等も原典の文字列をそのまま残します。人口0を人口調査で確認した無人地域とは判断しません。
`address_candidate=1` は採用した地名種別という意味で、住所の正しさや配送可能性の認定ではありません。
歴史的・廃絶した集落等は原典の行を残し、既定の候補から除外しています。

## 確認済みの行政改編差異

- **ブルキナファソ**：今回のGeoNames ADM1は13行。大統領府の2025-07-02発表と国土地理機関は17地域・47州を示します。
- **ブルンジ**：今回のGeoNames ADM1は16行。公式法令は5州・42コミューンの構成を示します。

この2か国は現在の行政階層として利用する前に照合が必要です。原典のIDや所属を自動で付け替えていません。
出典URLは `source_freshness.json` にあります。他の国も行政改編を網羅的に点検済みではありません。

## 使い方

Python 3.11以上。追加パッケージやDBの構築は不要です。

```bash
cd address-foundation/africa-registry
python query.py --country KE --level 1
python query.py --country KE --state gn:184742 --limit 20
python query.py --country ZA --text Cape --limit 20
python query.py --country MG --kind admin_subdivision --level 2
python build.py verify
python -m unittest discover -s . -p 'test_africa.py' -v
```

一覧・検索は出典表記と別名の部分一致です。検索結果は自動確定しません。
`--offset` と `--limit` でページ分割できます。`--include-other` で既定候補外の行も検索できます。
種類や行政階層を明示した検索は、指定した種類の行を返します。

通常のCSVとしても読み込めます。

```python
import csv, gzip
with gzip.open('countries/NG/entities.csv.gz', 'rt', encoding='utf-8', newline='') as f:
    for row in csv.DictReader(f):
        if row['kind'] == 'admin_subdivision':
            print(row['id'], row['name'], row['parent_id'])
```

## 再取得・再現

`scope.json` の各CCに対応する `https://download.geonames.org/export/dump/CC.zip` と
`countryInfo.txt` を取得したディレクトリを指定します。

```bash
python build.py build --inputs /path/to/geonames-inputs --retrieved-on YYYY-MM-DD
python build.py summarize
python build.py verify
```

`--countries KE UG` のように国を限定して更新できます。国連の範囲は収録済みの `scope.json` を使用します。
各国ZIPは日次更新されるため、同じURLから将来取得したバイト列が同じとは限りません。
原典ZIP全体はGitに重複収録せず、SHA-256・原典行数・除外分類の件数を記録しています。
一方、採用した行は原典19列をすべて保持しているため、**配布CSVだけから派生列を再構築し、全件一致を検証**できます。
gzipは時刻とファイル名を固定して生成します。圧縮バイト列の完全一致にはPython/zlibの実行環境も関係します。

## 既存データとの関係

このフォルダは `world-address` の既存住所基盤ブランチへの追加です。
既存の公式国別台帳、CSCデータ、住所フォーマット、郵便番号、既定検索ソースを上書きしません。
本データを住所基盤DBへ自動マージする処理は追加していません。
既存のGeoNamesプレビューとIDは共有できますが、同名の都市と自治体を自動統合しないでください。
フォルダ全体を後から `world-localities` へ移しやすい構成です。

利用条件と帰属表示は [NOTICE.md](NOTICE.md) を参照してください。地名データは **CC BY 4.0** です。
