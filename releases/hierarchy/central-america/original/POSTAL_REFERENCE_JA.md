# 郵便番号の扱い

本版には全国郵便番号の割当表を取り込んでいません。`postcode` は入力形式の参照に限定し、`assignment_verified` と `delivery_verified` は常にfalseです。`postal-records` の空結果は未収録を意味し、入力した番号が無効という意味ではありません。

| 国 | 本版の処理 | 参照と注意 |
|---|---|---|
| ベリーズ | 形式を断定せず、空欄をエラーにしない | UPU 2021年住所例は郵便番号を含まない |
| グアテマラ | 数字5桁を形式一致候補とする | UPU 2025年11月資料。先頭ゼロを保持 |
| エルサルバドル | 数字4桁。入力上の任意のCP接頭辞は一回のみ許容 | UPU 2019年資料は4桁。CPは入力許容であり番号の一部とは断定しない |
| ホンジュラス | 原入力を保持し、要確認 | UPU公開PDFは2004年の英字2字＋数字4桁、GeoNames国情報は数字6桁。現行全国ルールの根拠として採用しない |
| ニカラグア | 数字5桁を形式一致候補とする | Correos de Nicaraguaの現行説明。GeoNamesの7桁表記は採用しない |
| コスタリカ | 数字5桁を形式一致候補とする | UPU資料とCorreosの州・カントン・地区別検索を参照。行政P-codeを自動で郵便割当へ変換しない |
| パナマ | 原入力を保持し、要確認 | Correos Panamáが2026年5月に新制度を発表。旧4桁やGeoNamesの5桁表記を現行の全国ルールとして使わない |

数字を整数として渡すと先頭ゼロを復元できないため、`invalid_input_type` とします。全角などの非ASCII文字は勝手に半角変換せず要確認にします。前後の空白と英字大小の表示候補は返しますが、`raw` はそのまま残します。郵便番号だけで行政区分・番地・建物を補完しません。

参照:

- [UPU Belize](https://www.upu.int/UPU/media/upu/PostalEntitiesFiles/addressingUnit/blzEn.pdf)
- [UPU Guatemala](https://www.upu.int/UPU/media/upu/PostalEntitiesFiles/addressingUnit/gtmEn.pdf)
- [UPU El Salvador](https://www.upu.int/UPU/media/upu/PostalEntitiesFiles/addressingUnit/slvEn.pdf)
- [UPU Honduras（2004年資料）](https://www.upu.int/UPU/media/upu/PostalEntitiesFiles/addressingUnit/hndEn.pdf)
- [Correos de Nicaragua](https://www.correos.gob.ni/codigo-postal/)
- [UPU Costa Rica](https://www.upu.int/UPU/media/upu/PostalEntitiesFiles/addressingUnit/criEn.pdf)
- [Correos de Costa Ricaの郵便番号検索](https://sucursal.correos.go.cr/web/codigoPostal)
- [Correos Panamáの新制度発表](https://www.correospanama.gob.pa/panama-da-un-paso-firme-hacia-la-modernizacion-con-el-nuevo-sistema-de-codigos-postales/)
- [パナマの郵便番号公式サイト](https://www.codigospostalespanama.gob.pa/)

これらは住所形式の参照であり、PDFの住所例を実在住所台帳として索引に取り込んではいません。
