# 登録・APIキーなしで使える住所・地名の原典

住所の一部分、公開施設の住所、原典に載った外国語表記をオフラインで検索する。2026年11月21日に取得した固定版を使用し、通常の検索で入力住所を外部に送信しない。今回の原典のいずれかを検索できる範囲は196国・地域コード。国・地域によって確認できる項目と地理的な範囲が異なる。

| 原典と検索キー | 収録範囲 | 結果の読み方 |
|---|---|---|
| [国連 World Urbanization Prospects](un_cities/) · `un-urban-centres` | 2025年の191国・地域、12,138都市中心地。中国本土2,082、日本137、米国348 | 原典の都市名、ID、人口加重の中心座標。同名は複数候補。行政上の境界や建物位置は未確認 |
| [日本・国土地理院／海上保安庁](jp/) · `gsi` | 2021年3月版から行政地名1,794件・居住地名182件 | 地名の漢字・かな・原典ローマ字を参照可能。原文の外字を抽出できなかった6件はかな・ローマ字から検索可能 |
| [中国本土の香港政府事務所・連絡所](cn/) · `hk-mainland-offices` | 16施設の繁体字・英語住所と郵便番号。住所目録の基準日は2024年11月21日 | 政府の地図に載る住所全文とも一致する10件に座標を添付。残る6件は座標を保留 |
| [米国・D.C.政府 Master Address Repository](us/) · `dc-mar` | D.C.全域。公式CSVの有効な個別住所点141,189件、115種類のZIP | 番地と通り名、ZIP、市、州の組み合わせを住所点ごとに照合。市政府の別の照会で全IDを確認 |
| [OpenStreetMap・D.C.](osm/) · `osm-dc` | 2026年1月1日の図書館・博物館等の住所タグ付き76地図要素、うち16要素に言語別名称 | 地図要素の名称、番地と通り名、明示された住所タグを検索。各地物のID・版と帰属を保持 |
| [フランス郵政 La Poste／INSEE](postal_eu/) · `la-poste` | 2026年11月17日版。フランス本土、海外11地域、モナコの39,191郵便行 | 郵便番号と自治体名・郵便用地名を同じ行で照合。海外地域は自治体コードで分ける |
| [モーリシャス政府の郵便局名簿・位置資料](africa/) · `mu-post-offices` | 住所表105行、座標付きの表102行 | 同一局が両資料に登場する。名称・所在地・番号を出典ごとに返す |

## 検索例

```sh
python -m addressing reference-sources --country JP
python -m addressing reference --country CN --query Beijing --source un-urban-centres
python -m addressing reference --country JP --query 府中市 --also 'Fuchu Shi'
python -m addressing reference --country CN --query 駐深圳聯絡處 --also 518033
python -m addressing reference --country US --query '901 G St. NW' --also 20001 --source dc-mar
python -m addressing reference --country US --query 'National Museum of Women in the Arts' --also 20005 --source osm-dc
python -m addressing reference --country MU --query 'Beau Bassin Post Office' --also 71504
python scripts/world_postcodes.py validate-place --source la-poste --country BL --code 97133 --locality 'ST BARTHELEMY'
```

Pythonからは `from addressing import lookup_reference` として、
`lookup_reference("CN", "駐深圳聯絡處", "518033")` を呼び出せる。
返却する `records` は出典ごとの候補で、入力値をすべて同じ原典レコードで確認できたものに絞る。郵便番号と地名の役割を指定したいときは `validate-place` または一括版 `validate-places` を使う。住所帳の原文、番地、部屋番号は自動で書き換えない。

| 検索結果 | 意味 |
|---|---|
| `observed` | 1件以上の原典行に該当した。`matching_records` は全該当行の数で、`limit` は表示件数にだけ適用する |
| `no_common_record` | 各値はこの国のいずれかの原典にあるが、すべてを含む同一レコードが見つからなかった |
| `not_observed_in_snapshot` | 選択した原典に収録されていない入力値がある |
| `no_source_for_country` | この追加原典群で検索できるものがない |

各フォルダーに原典URL、取得日、利用条件・帰属、SHA-256、再現コマンドを収録した。外部に表示・再配布する際は該当する原典の帰属と条件を引き継ぐ。OpenStreetMapの抽出はODbL、モーリシャスの加工済みCSVはCC BY-SA 4.0で個別に配布する。いずれの照合結果も個別の配送可否は未確認。
