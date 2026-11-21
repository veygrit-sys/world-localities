# 国連の都市名・位置参照（2025年）

国連経済社会局人口部の [World Urbanization Prospects 2025](https://population.un.org/wup/downloads/?tab=Cities) は、人口の密度・規模・連続性などの統計基準に基づく都市を収録する。公式CSVの779,718データ行から、年が2025年の12,138都市をすべて抽出した。原典が割り当てた国・地域コードは191種類。中国本土2,082、日本137、米国348。香港・マカオ・台湾はそれぞれHK・MO・TWの原典行として照合する。

原典の都市コード、表記、国・地域コード、人口加重重心の緯度・経度、元CSVのレコード番号（見出し行を1として計数）を保存する。これは国連の統計上の都市と表記の参照。地方政府が定める行政市、同名の郵便用地名、街路・番地・配達先を自動認定しない。点は集住地域の重心であり、庁舎や市役所、宛先建物の位置に転用しない。訳名・別の文字体系は推定しない。

`lookup("Beijing", country="CN")` と `lookup("un-wup2025:9020", country="CN")` は同じUN都市コード9020を返す。単独の数字を都市コードとして消費しない。同じ国で複数都市に一致するときは全候補を返す。例えば中国の `Anping` には9266・9296の2件がある。NFC・大文字小文字・空白だけを検索用に揃え、アクセントや句読点は保持する。

## 原典との再照合

通常の検索はオフラインで行う。[source.json](source.json) に公式配布先、取得日、圧縮原典と抽出結果のSHA-256、国別収録数を記載。次のコマンドは未登録で取得できる公式CSV（圧縮約59 MB）から抽出を再実行し、同梱データと一文字ずつ比較する。元ファイルを保管している場合は `--source-file PATH` を付ける。

```sh
python -m localities.open_reference.un_cities.project
```

## 出典・利用条件

United Nations, Department of Economic and Social Affairs, Population Division (2025). *World Urbanization Prospects 2025, Online Data.* This projection selects 2025 city names, geographic identifiers and population-weighted centroids. Source spellings are preserved. © 2025 United Nations. The [UN FAQ](https://population.un.org/wup/assets/Publications/undesa_pd_2025_faq_wup25.pdf) specifies [CC BY 3.0 IGO](https://creativecommons.org/licenses/by/3.0/igo/) for the associated data.
