# 郵便番号形式の参照

確認日：2026-10-17。正規表現は入力候補の構文チェックで、配達可能性や実際の割当の認証ではありません。原文を保持したまま大文字の候補表記を返します。

| 範囲 | 入力形式 | 参照 |
|---|---|---|
| US | 5桁、または5桁-4桁 | [USPS ZIP Code basics](https://faq.usps.com/articles/Knowledge/ZIP-Code-The-Basics) |
| CA | 英数字6文字、中央の空白を許容。使用できる文字を制限 | [Canada Post postal codes](https://www.canadapost-postescanada.ca/cpc/en/support/articles/addressing-guidelines/postal-codes.page)、同梱GeoNames countryInfo |
| MX | 5桁 | [メキシコ政府の住所技術基準](https://sidof.segob.gob.mx/notas/docFuente/5743561) |
| BM | 物理住所は英字2文字＋数字2桁、私書箱は英字4文字。中央空白を許容 | [Bermuda Post Office postal codes](https://www.bermudapost.bm/postal-codes/) |
| GL | 4桁 | 同梱GeoNames countryInfoの郵便番号形式。個別の町への割当は未検証 |
| PM | 97500 | 同梱GeoNames countryInfoおよびBANの原典属性 |

米国・PMの限定資料にある郵便番号は原典の属性として検索できます。カナダODA NTには郵便番号が記録されておらず、他の地図や地名から埋めていません。メキシコの全国郵便番号カタログは本パックに再配布していません。

返却する `matches_syntax_only`、`assignment_verified: false`、`delivery_verified: false` を区別してください。
