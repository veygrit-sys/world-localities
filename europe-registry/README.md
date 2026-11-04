# ヨーロッパの行政区画・地名台帳

国別・分割CSVで読める地名データです。国連M49のヨーロッパ51か国・地域と、
`world-address`の欧州範囲にあるAM・AZ・CY・GE、補足のTR・XKを対象とします。
正確な対象は [scope.json](scope.json) です。取得日: 2026-09-29。国別フォルダと分割CSVで収録しています。

## 収録データ

| 内容 | 件数 |
|---|---:|
| GeoNames対象国・地域 | 57 |
| 行政区画（ADM1〜ADM5） | 126,249 |
| 都市・集落等（P分類） | 1,026,412 |
| その他の採用行政地物 | 8,928 |
| GeoNames合計 | 1,161,589 |
| 直接の親が未解決 | 3,561 |
| 行政所属がなく国の範囲だけを保持 | 2,786 |
| Eurostat LAU対応表 | 32か国・104,687行 |
| 全件の構造検証 / 回帰テスト | 合格 / 13件合格 |

未解決の親子関係は解消済みとは扱いません。LAUとGeoNamesは重複する対象を含むため合算しません。
GeoNamesの詳細は[coverage.csv](coverage.csv)と[manifest.json](manifest.json)、
公式LAUの国別件数・原典検証状態は[eurostat-lau/manifest.json](eurostat-lau/manifest.json)にあります。


- `countries/CC/`: GeoNamesの行政区画と都市・集落。人口による足切りなし。
  各国の`metadata.json`がCSV分割一覧、出典、取得日時、SHA-256、件数、欠落を示します。
- `eurostat-lau/CC/`: Eurostat LAU 2025 / NUTS 2024対応表を別出典として収録。
  国別の原典検証状態・原典行番号を保持します。GeoNamesとは自動統合しません。
  セルビアの原典コア項目は未検証です。リヒテンシュタインの空シートは収録件数に含めません。
  原典の最終更新欄は2026-06-02、各データ行のPERIODは2024です。
  2025という配布版名とPERIODを別々に保持します。
- [world-addressの国別公式台帳](https://github.com/rei-k/world-address/tree/9071ff08548bbc6b449e6c30e8eae2adad025d46/address-foundation/official-registry)のFR・DE・IT・ES・GB:
  元リポジトリにある別の台帳です。この欧州データの構築・検索には不要です。
  2026年版の国別行政階層を必要とする場合は、各台帳の範囲・基準日を確認して使います。

GeoNamesの国別抽出は国全体を対象とし、大陸境界で切断しません。
AM/AZ/CY/GE/TRが他の地域台帳にも収録される場合は、共通の`gn:` IDで重複排除してください。
行政区画・都市・集落・LAUの件数を足して「自治体政府数」にしてはいけません。

## 親子関係と名前

`parent_id`は国コードと行政コードの完全一致でのみ決定します。
中間階層の欠落や重複コードは未解決として残し、確認できた州相当の参照は`state_id`に分けます。
`state_id`は原典のADM1であり、各国で同じ法的意味を持つ階層ではありません。
歴史的地名は保持しますが現行行政との親子関係は断定しません。

原典表記・ASCII表記・別名を保持します。ASCII表記やラテン文字表記を英語名とはみなしません。
この版は全公用語の翻訳を保証しません。郵便番号の対応、Address1、境界ポリゴンは未収録です。
国コードや`cc2`は原典のまま保持し、国境・帰属を独自に判定しません。
XKはGeoNamesの利用者割当コードで、正式なISO 3166-1割当コードとは区別します。

## 利用

読み込み・検索・GeoNames再構築はPython 3.11以降の標準ライブラリだけで動作します。

```bash
cd europe-registry
python query.py --country AT --level 1
python query.py --country PL --text Krak --limit 10
python build.py verify
python -m unittest discover -s . -p 'test_europe.py' -v
```

```python
from build import country_rows, ROOT
for row in country_rows(ROOT, 'AT'):
    print(row['id'], row['name'], row['parent_id'], row['state_id'])
```

## 再取得・検証

```bash
python build.py build --inputs /path/to/source-cache --countries AD AT
python build.py verify --countries AD AT
python build.py summarize
# 全対象を作る場合は --countries を省略
pip install -r requirements-build.txt
python eurostat.py build --inputs /path/to/source-cache
python eurostat.py verify
```

ソースキャッシュはハッシュ照合して再利用します。更新するときだけ対象ZIPとその
`.meta.json`をキャッシュから除きます。将来の同一URLは同一バイト列を保証しません。
配布CSVにGeoNamesの原典19列を残しているため、全派生列をオフラインで再構築して照合できます。
gzipのタイムスタンプとファイル名を固定し、国別CSVを最大20,000行に分割します。

`verification.json`の合格はID・参照・ハッシュ・再現性の検証です。
GeoNamesの地名や行政改編が全件最新であるという認定ではありません。
公式LAU対応表も、2026年の各国自治体名簿を一律に代替するものではありません。

詳しい列定義は[SCHEMA.md](SCHEMA.md)、利用条件は[NOTICE.md](NOTICE.md)を参照してください。

企業名簿・法人情報は収録していません。

このフォルダは、[world-addressの欧州データ](https://github.com/rei-k/world-address/tree/9071ff08548bbc6b449e6c30e8eae2adad025d46/address-foundation/europe-registry)
（コミット`9071ff08548bbc6b449e6c30e8eae2adad025d46`）を2026-09-30に移し、
配置場所の説明とリンクを更新したものです。データ・構築コード・検証結果は元の版と同一です。
このフォルダだけで読み込み・検索・検証できます。
