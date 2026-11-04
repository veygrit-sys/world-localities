# 西ヨーロッパ：行政区・道路・番地の取込管理（2026-10-22）

全行政区・全道路・全番地の完全網羅は未完了。配達可能性は対象外。従来の11か国を維持し、M49西欧9か国と北欧に属するGB・IEを区別する。既存2026-10-17版と最初の107原典を残し、オランダの全国BAG・CBS名簿を追加した。

## 収録済みの住所・道路名原典

| 国 | 公式住所の原典観測行 | 独立した道路名簿の観測行 |
|---|---:|---:|
| オーストリア | 2,529,222 | 138,112 |
| ベルギー | 7,178,121 | 157,906 |
| スイス | 3,306,620 | 224,629 |
| フランス | 25,288,623 | 住所内の道路名。独立名簿は未取込 |
| リヒテンシュタイン | 12,966 | 1,237 |
| ルクセンブルク | 248,634 | 9,963 |
| オランダ | 13,377,160 | 333,946 |

住所の原典観測は合計 **51,941,346行**。現存する一意の住所数ではない。BAGでは終了した版を含み、他国でも廃止・計画・暫定・公認外の記録を保持する。ベルギーは郵便番号によって同じ道路IDが繰り返される場合がある。道路名簿は物理道路の全本数ではない。

オランダは2026-10-08の全国NUMを全1,338 XML読み込み、**13,377,160版**を全件再照合。うち定義した「対象日の有効期間・発行状態・登録終了等なし」の条件に合う観測は **10,076,588行**。ID別集計は netherlands/validation.json に保存する。Not-BAG 43,021行・非活性 395行のNUMは、この主台帳の住所観測数に加えない。

CBSの342自治体・12州の参照名簿と比較し、上記の条件に合うNUMが参照する自治体は342。欠落・重複・未解決参照は検証記録に残す。GWRは提供元が真正なBAG属性・公式BAG製品ではないと説明する補助表として扱う。OPRには道路以外の公共空間名21,561版も別種別で保持する。詳細と復元手順は [オランダ版](netherlands/README.md)。 限定した参照条件で結合できない153行は、152行の将来日付の道路版への参照と、1行の廃止地名コードへの参照に整理した。候補と元データは netherlands/reference-gap-review.json に分けて保持する。

最初の107原典の検証と読込コードは維持。フランスはコルシカを含む96県のBANを全件再照合済み。スイスの番地なし・official=false、ベルギーのbox_number、LUの暫定・未定番地を保持する。LUの13件のcanton_referenceには特別・旧来のコードを含み、現行法定カントン総数とはしない。

補助MCのOSM抽出は周辺のバッファを含む。道路way 3,625、番地タグ観測474、行政境界タグ観測61を保持し、モナコ国内だけの総数としない。元PBFに版・時刻、投影にタグ・参照・点/way座標を保持し、関係の面形状は未組立。

既存GeoNames基盤は11か国344,143行、前回の構造検証でエラー0。これは最新の全行政区を保証しない。別の資料の自治体は名前だけで同一視しない。

## 残る不足

- DE・GB・IE：全国住所の追加取込が未完了。取得先・条件・次の作業は source-review.json / coverage.csv。
- NL：主住所・副住所の役割と座標に必要なVBO/LIG/STA、独立した付番総数、物理道路網、細分区画・境界の照合が残る。
- 全11か国：独立した現行の全階層名簿、無名道・私道・無番地道路を含む全物理道路、付番機関の独立した総台帳との比較が残る。
- CH・BE・FR等：他の原典との行政・道路IDの全件結合は未検証。AT内部・LU複合コード・NLの指定した参照の検証を、地域全体の完全性に拡大解釈しない。

住所が原典にあること、公認・現存・使用許可・配達可能性は同義ではない。全国完全性の分母が未確定のため、達成率は計算しない。

## 復元と検索

初回の8書庫は、同じ新しいフォルダへ展開すると `western-europe/raw/` に揃う。オランダ追加の6分割は別の書庫で、netherlands/README.md のコマンドにより `western-europe-nl/raw/` へ復元する。コードは検証記録と同じファイルハッシュの版を使う。

```bash
python3 scripts/hierarchy_cli.py --region western-europe -- inventory
python3 scripts/western_europe_sources.py search --data-root /path/to/western-europe/raw --country LI --kind address --number 9 --limit 5
python3 scripts/hierarchy_cli.py --region western-europe --data-root /path/to/western-europe-nl/raw -- search --country NL --kind address --number 7 --current-only --limit 5
python3 scripts/netherlands_bag.py replay --data-root /path/to/western-europe-nl/raw --accepted releases/hierarchy/western-europe/netherlands/validation.json --work-dir /path/with/free/space
```

共通CLIの監査・取得・再照合は国を指定する。従来の `scripts/western_europe_sources.py` の一括操作はそのまま維持する。NL検索の現在参照名は日付付きで返し、過去の住所版に現在名を混ぜない。

原典のSHA-256、全解析行の2回一致、ZIP CRC等を確認。今回の15契約テストと、既存分・配置・書庫安全性・分割復元を含む計44テストに合格。実原典の共通CLI検索、6分割からの全原典バイト復元も検証した。詳細は validation.json、netherlands/validation.json、各 official-sources.json / NOTICE.md / archive.json を参照。
