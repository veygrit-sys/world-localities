# 住所検証の対応範囲と再検査

[フランス郵政の公式郵便番号と地名](../../localities/open_reference/postal_eu/)は
`validate-place --source la-poste` と `validate-places --source la-poste` で選択できる。
対象はフランス本土・海外11地域・モナコ。郵便番号と自治体名・郵便上の地名を照合する。

## 郵便番号と地名を同じ原典行で確認する

郵便番号・地名・州名・州コードを組み合わせて照合できる。比較する項目をすべて満たす原典行を探し、原文、行番号、固定原典のSHA-256を返す。採点後に表示件数を制限するので、先頭候補に一致しない地名も検索できる。

```sh
python scripts/world_postcodes.py validate-place --country US --code 02116 --locality Boston --region-code MA
python scripts/world_postcodes.py validate-place --country FR --code 75007 --locality Paris --limit 1
python scripts/world_postcodes.py validate-places --input evaluation/postal-places/public-examples.json
python scripts/check_postal_place_coverage.py
```

対象は固定版GeoNamesのうち、通常の掲載値または完全桁版の原典がある115国・地域。1回のバッチで必要な原典を各1回走査する。各要求には国・郵便番号と、地名 `locality`、第1行政区の名称 `region`、同コード `region_code` の少なくとも1項目を指定する。カナダ・英国・オランダの完全桁版では小文字と区切り空白の省略に対応する。地名のアクセント・句読点や番号の先頭ゼロは保持する。

| 結果 | 読み方 |
|---|---|
| `matched` | 入力された項目が同じ行にそろい、該当する地名・行政区の組み合わせが一つに絞れた |
| `ambiguous` | 該当する地名・行政区が複数あるか、項目不足で排除できない別の行がある |
| `insufficient_evidence` | 番号は掲載されているが、比較に必要な原典項目が空欄 |
| `no_match_in_source` | 番号は掲載されているが、指定した地名・行政区を同時に満たす行が見つからない |
| `postcode_not_observed` | その国の対象原典で、入力された番号が見つからない |
| `no_eligible_source` | この検索方式で使える原典行がない。地域別の原典や別の照合方法を参照する |

確認する範囲は固定原典における組み合わせ。GeoNamesの地名と郵便事業者の配送用地名が異なる場合がある。現行の番号割当や番地・建物・部屋への配達可否は未確認。接頭辞、集約値、経路専用値、履歴専用の原典はこの照合から除外する。原典の収録条件と帰属表示は [郵便番号原典の利用案内](../../postal/README.md) と [NOTICE](../../postal/NOTICE.md) を参照。

## 国・地域別の照合

| 対象 | 照合できる範囲 |
|---|---|
| 日本 | 日本郵便の2026-10-30版の通常・事業所等の原典を使う。政令指定都市の市・区と東京の特別区は、JISコード・表記が一致する住所ベース・レジストリの記録にも照合する。町域欄の番地案内、組織名が必要な事業所・私書箱を区別する。 |
| 台湾 | 中華郵政の中英371行から先頭3桁と郵便地名を照合する。368行は市・県と下位区分の分割照合にも対応する。6桁入力で照合するのは先頭3桁まで。 |
| 米国・カナダ・メキシコ・ブラジル | 保存済み原典の住所候補60,890件を対象に、地名・州・任意の原典コードを照合する。候補が別の州にあるときはその州を返す。米国原典の役割を示す `city` などの接尾辞は保持する。 |
| アルメニア・アゼルバイジャン・ジョージア・イスラエル・ヨルダン | 公式資料から採録した郵便番号・地名46件を参照し、同じレコードにある項目を示す。収録例以外は保留する。 |
| 共通の書式検査 | 9地域の130プロファイルで国選択・単一行の構文検査を強化。番号パターンあり89、なし41。アラビア文字の8プロファイルでは現地数字の入力を照合用に変換する。 |

```sh
python registries/official/query.py --country JP --postal-code 064-0941 --components-json '{"city":"札幌市","city_district":"中央区","town":"旭ケ丘"}'
python registries/official/query.py --country TW --postal-code 300001 --include-prefix --components-json '{"city":"新竹市","district":"北區"}'
python -m registries.americas.validate_locality --country CA --locality Toronto --region QC
```

```python
from addressing import validate_western_asia_country

result = validate_western_asia_country("AM", "0002", locality="Yerevan", admin_name="Yerevan")
print(result["postal_excerpt"])
```

## 確認に使った住所と結果

公式ページで所在地を確認した6件は、すべて郵便番号と地名が原典行で一致した。フランスの `75007` の先頭行は `Paris 07`、次の行は `Paris`。カナダ・英国・オランダの入力は小文字・空白なしに変えて同じ所在地を再確認した。

| 国 | 公表元 | 照合した組み合わせ | 固定原典の行番号 |
|---|---|---|---:|
| 米国 | [ボストン公共図書館](https://www.bpl.org/locations/central/) | 02116 · Boston · MA | 1,805,130 |
| カナダ | [トロント参考図書館](https://tpl.ca/locations/trl/) | M4W 2G8 · Toronto · ON | 535,156 |
| 英国 | [Science Museum Shop](https://shop.sciencemuseum.org.uk/pages/contact) | SW7 2DD · London | 1,433,786 |
| オランダ | [アムステルダム国立美術館・来館住所](https://www.rijksmuseum.nl/en/visit/practical-info/address-and-directions) | 1071 XX · Amsterdam | 232,364 |
| ドイツ | [連邦議会・来訪者窓口](https://www.bundestag.de/besuche/kontakt-besuch-251124) | 11011 · Berlin | 288,029 |
| フランス | [オルセー美術館](https://www.musee-orsay.fr/en/visit) | 75007 · Paris | 375,788 |

別に、115国・地域で各1件の掲載値と1件の誤った組み合わせを再生した。230件の確認で取りこぼし・誤受理はいずれも0件。誤った組み合わせのうち96件には同じ国の別の郵便番号に実在する地名を使用した。残り19件は抽出範囲内で代替名を確保できず、合成の地名を使った。この検査は原典の再生と判定処理を確認するもので、国別の実住所全体の精度を推定する評価ではない。
