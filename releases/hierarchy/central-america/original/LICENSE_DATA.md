# 原典と利用条件

原典ごとの表示を保持します。GeoNamesとCOD-ABを統合した索引は本パックによる変換結果であり、原典機関による承認・認定を意味しません。

## GeoNames

GeoNames geographical database © GeoNames contributors. [Creative Commons Attribution 4.0](https://creativecommons.org/licenses/by/4.0/)。国別地名・別名・行政コード表を使用しています。検索用キーと親子リンクを本パックで生成しています。原表記、ID、別名の言語、原行は保持します。

[配布説明](https://download.geonames.org/export/dump/readme.txt)。GeoNamesは正確性・適時性・完全性を保証していません。

## HDX COD-AB gazetteers

OCHA Field Information Services / Humanitarian Data Exchange が公開した行政区分表。取得時の各カタログは [CC BY-IGO 3.0](https://creativecommons.org/licenses/by/3.0/igo/legalcode) を表示しています。配布元・上流出典・基準日をカタログ原典のまま収録しています。

| 国 | 公開カタログ | カタログに記載された上流出典 |
|---|---|---|
| BZ | [COD-AB BZ](https://data.humdata.org/dataset/cod-ab-blz) | www.gadm.org |
| CR | [COD-AB CR](https://data.humdata.org/dataset/cod-ab-cri) | Costa Rica National Statistics Office (NSO) |
| GT | [COD-AB GT](https://data.humdata.org/dataset/cod-ab-gtm) | Coordinadora Nacional Para La Reducción De Desastres |
| HN | [COD-AB HN](https://data.humdata.org/dataset/cod-ab-hnd) | Sistema Nacional de Información Territorial (SINIT), Secretaria Técnica de Planificación y Cooperación Externa (SEPLAN), 2010 |
| NI | [COD-AB NI](https://data.humdata.org/dataset/cod-ab-nic) | www.gadm.org |
| PA | [COD-AB PA](https://data.humdata.org/dataset/cod-ab-pan) | www.gadm.org |
| SV | [COD-AB SV](https://data.humdata.org/dataset/cod-ab-slv) | www.gadm.org |

本パックは公開XLSX表の原セルとP-code階層を使用し、GIS境界ポリゴンを同梱していません。上流にGADMと記載された系列も含むため、それらを各国政府から直接取得した公式住所台帳と表現しません。配布元が付した利用条件と上流出典の記録を併記します。

加工内容: 指定シートのセル抽出、P-codeによる原典内の上位参照、別名検索、地図用の水域行の分類、重複コードの警告、国別レポート。原典を改変したファイルへ置き換えてはいません。

パナマIGN由来のArcGISレイヤーで確認されたCC BY-NC-SAデータは取得・収録していません。行政改編の参照URLだけを資料に記載しています。

## 出典の追跡

`address-points/CENTRAL_AMERICA_SOURCES.json` にURL、取得時刻、サイズ、SHA-256、選択シート、基準日説明を記録しています。同じURLの内容は将来変わるため、バイト列のハッシュを収録版の識別子とします。共通のGeoNames参照4ファイルは同日作成した北米版から原典バイトと取得記録を継承しています。
