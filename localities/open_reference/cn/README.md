# 中国本土にある香港特別行政区政府の公表住所

[政制及内地事務局の公式目録](https://data.gov.hk/en-data/dataset/hk-cmab-cmabt7-hong-kong-offices-in-mainland-and-taiwan) の英語・繁体字中国語JSONを、2026-11-21に登録・APIキーなしで取得した。両原典の内部更新日は2024-11-21。中国本土の事務所5件と連絡所11件の名称・住所・郵便番号を同じ施設に結び付ける。目録内の台湾事務所は対象外。

名称・住所全文・郵便番号・レコードIDを完全一致で検索できる。英語の大文字小文字と連続空白を比較時に正規化する。局が公表した繁体字と英語をそのまま返す。原典には簡体字版がなく、中国語の字体、部屋番号、街路名の別表記を推定しない。郵便番号だけの検索結果はこの目録の掲載例。掲載日後の移転、第三者の住所、郵便番号全体の割当、投函・配達可否を確かめる原典ではない。

`lookup("518033")` と `lookup("駐深圳聯絡處")` はともに `hk-cmab:guangdong/shenzhen-liaison-unit` を返す。英語・繁体字の事務所を原典の `officeID` で、連絡所を同一事務所内の共通の官署メールアドレスと郵便番号で突き合わせる。原典の配列順は対応付けに使用しない。

同局が[CSDIの地理データ目録](https://portal.csdi.gov.hk/csdi-webpage/dataset/cmab_rcd_1632885529072_51988)で提供する16地点もGeoJSONで保存した。英語の住所全文が完全一致する10件に限り、`map_point` に原典オブジェクトID・経度・緯度・座標系を返す。6件は `null`。例えば済南の地図は26 Quancheng Road、事務所目録は102 Luoyuan Streetを掲載しており、同じ施設名でも座標を転記しない。位置は施設の参照点で、建物の入口や部屋の座標は公開していない。

## 版を照合する

保存したJSONはgzip + Base64から元バイト列に復元でき、読込時に長さとSHA-256を検査する。公式URL・原典ハッシュ・取得日・帰属は同梱の [source.json](source.json) を参照。公式サイトでの更新を検出するには以下をリポジトリのルートから実行する。

```sh
python -m localities.open_reference.cn.verify_cmab
```

## 帰属と利用条件

Source: Constitutional and Mainland Affairs Bureau, Government of the Hong Kong Special Administrative Region, via DATA.GOV.HK. Intellectual property rights in the source data belong to the Government and the relevant organisations. The [DATA.GOV.HK terms of use](https://data.gov.hk/en/terms-and-conditions) apply to the data and its copies. Keep the attribution with redistributed records.

Map point source: Constitutional and Mainland Affairs Bureau, Government of the Hong Kong Special Administrative Region, via the CSDI Portal. Intellectual property rights in the source data belong to the Government and the relevant organisations. The [CSDI Portal terms of use](https://static.csdi.gov.hk/csdi-webpage/doc/TNC) apply to the map data and its copies.
