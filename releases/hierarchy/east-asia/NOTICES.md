# 出典・利用条件

- OpenStreetMap contributors; extracts by Geofabrik。OSMデータとnative PBF補助投影はODbL 1.0。https://www.openstreetmap.org/copyright / https://opendatacommons.org/licenses/odbl/1-0/ 。元データの全タグ、番号、版、参照を保持して対象種類を選択した派生資料。無タグの参照節点を全収録したものではない。
- 日本住居表示：デジタル庁「アドレス・ベース・レジストリ」（https://www.digital.go.jp/policies/base_registry_address）をもとにOpenAddressesが加工した公開資料を取り込み、world-localitiesで検証。公共データ利用規約PDL1.0（https://www.digital.go.jp/policies/base_registry_address_tos）。位置情報と結合できた住居表示に限る。生成説明はOpenAddressesの694e3dea10cc7465907c0ad5eb6ff1f62deef3b9版を固定。アップロードデータの生成時コミット自体は提供されていない。
- 日本町丁目：Geolonia 住所データ、株式会社Geolonia。https://github.com/geolonia/japanese-addresses 。データはCC BY 4.0（https://creativecommons.org/licenses/by/4.0/）。国土交通省の位置参照等を基礎とする町丁目位置参照であり、すべての地名を網羅するものではない。原典CSVを変更せず保持。
- 香港住所：Hong Kong Digital Policy Office / Address Lookup Service、OpenAddresses公開原典。https://data.gov.hk/en-data/dataset/hk-dpo-als_01-als / https://data.gov.hk/en/terms-and-conditions 。元の重複行、番号、名称、座標の欠損を保持。網羅性・最新性は保証されていない。
- 台湾道路名：內政部戶政司、115全國路名資料。https://data.gov.tw/dataset/35321 。政府資料開放授權條款第1版（OGDL-1.0、https://data.gov.tw/license）。元の道路名の行を保持。
- 台湾行政コード：內政部國土測繪中心。https://data.gov.tw/dataset/102011 / https://data.gov.tw/dataset/102017 / https://api.nlsc.gov.tw/ 。OGDL-1.0。API応答を保持し、リクエストの親対応を追加して照合。名称のない参照を別区分で保持。
- 中国統計区分：modood/Administrative-divisions-of-China、2023-06-30版、コミットc49d495b40ac73eb1a66f6eeae5f8fd10696f035。https://github.com/modood/Administrative-divisions-of-China 。リポジトリのWTFPL-2.0とLICENSEを同梱。統計区分の参照であり現行法定区分の保証ではない。

コードのライセンスと各原典データの条件は別に適用される。元の番号を展開・推測して増やさず、ソース間の同一性を名前だけで結合しない。配達可能性の判定は含めない。
