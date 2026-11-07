# 欧州の座標照合と公式原典の取得障害（2026-11-08）

## 重要な区別

公式の配布ページへのアクセス、全国原典の実取得、全行の住所ID検証、出典独立の位置検証、配達可能性の証明はすべて異なる工程です。今回、成功と失敗の実観測を分けて保存します。

## アイスランド：HMS住所点と別機関の道路地図を比較

HMSが公開するStaðfangaskráは2026-11-08実取得で139,795座標点、137,624住所IDでした。[実取得の元証跡](https://github.com/veygrit-sys/world-localities/actions/runs/42418793252)。

HMSのTEGHNITは座標種別（0要確認、1概算中心、2主出入口、3敷地車両入口、4敷地内、5概算建設区画）、YFIRFARIDはレビュー状態（0未確認、1確認済み、2要再確認、9住所識別子欠損）。これは原典による自己評価であり、独立検証ではありません。[HMSの公式カラム説明](https://hms.is/gogn-og-maelabord/grunngogntilnidurhals/stadfangaskra)。

別資料はNáttúrufræðistofnunが作成・管理するIS 50V（縮尺1:50,000、公式の道路中心線、元座標系はEPSG:3057、CC BY 4.0）。[行政資料](https://www.natt.is/en/resources/geospatial-data/base-map-data)と[公開元メタデータ](https://geoportal.gis.is/geonetwork/srv/api/records/41D3314D-55AF-4FE3-9A9F-B9CB18AC5CAA?language=eng)。

最初のArcGIS地図API（portal.land.is）はGitHub Actionsでタイムアウト。代わりに公開WFS（gis.lmi.is）からGetCapabilitiesと道路GeoJSONの実取得に成功しました。WFSは明示的にEPSG:3057のGeoJSONを要求すること。全住所点を投影変換し、確認区分ごとに最寄りの公式道路との距離を50/100/250/500/1000/2000mに集計する処理を別途整備します。

公開道路1:50,000は農村・山間・島嶼の通行経路を全て描くわけではありません。距離が大きいことを即座に「住所が偽」「座標が誤り」「配送できない」と判断しません。別機関の地図でも情報源が一部重複している可能性があります。

代替OSM道路照合も実装しますが、[過去にIceland OSMへHMS住所をインポートした記録](https://wiki.openstreetmap.org/wiki/Staðfangaskrá_Import)があるため、OSMの住所点をHMS住所の完全に独立した真値とはみなしません。

## イタリアANNCSU：正式配布リンクは確認、現時点で原本未取得

[ANNCSU公式大量配布ページ](https://www.anncsu.gov.it/it/consultazione-dellarchivio/open-data/Accedi-ai-servizi-di-dowload-massivo-in-Open-data/)には全国のStradario（道路名簿）/Indirizzario（番地名簿）と20地域それぞれのZIPへのリンクが掲載されています。[イタリア政府データ目録](https://www.dati.gov.it/node/view-dataset/dataset?id=0b846a28-76b1-469a-9445-5ea53f6903a0)は月次更新・CC BY 4.0を記載しています。

GitHub Actions（2026-11-08）から公式リンクをHEAD取得したところ全国道路GETDS、アブルッツォ州GETDS、カタログPHPがHTTP403。以前にアブルッツォ州のGETを試したところHTTP406。認証、CAPTCHA、IP制限の無断迂回はしません。行政提供窓口に正規のダウンロード手順と自動取得許可を問い合わせ、正式ZIPが得られるまで全国取込完了とは扱いません。

## セルビアRGZ：実ファイルの取得は未完了

[政府の住所登録簿](https://data.gov.rs/sr/datasets/adresni-registar/)（2026-10-22更新）は道路・家屋番号それぞれのCSV/GPKGを提供する旨を掲載しています。公式download.geosrbija.rsの2種類のCSVはGitHub Actionsからタイムアウト。[既存PR #29](https://github.com/veygrit-sys/world-localities/pull/29)に同じ障害があります。公共のデータが存在しないのではなく、取得経路に障害があるという結論です。

正式ファイルが取れた時点で道路ID/住所固有コード/地物の現行性と建設予定地の種別を別々に検査。国境・係争地の管轄を単なる住所コードで断定しません。

## スペインCartoCiudad：配布カタログは接続可能、全52県のデータ未取得

[CNIGのCartoCiudad配布センター](https://centrodedescargas.cnig.es/CentroDescargas/cartociudad)と一部詳細画面はHTTP200。しかし前回の県別GeoPackageのダウンロード・ハンドシェークはHTTP403のため、全52単位の実ZIP/GPKG未取得。正規ユーザー向けの提供方式、配布元によるプログラム取得許可と必要な受諾条件を確認します。

[CartoCiudad公式説明](https://www.cartociudad.es/web/portal/directorio-de-servicios/descarga)はOGC API FeaturesやWFSから一部を選択取得できるが、全量はCNIG配布センターへと明記。ページ送りだけで全て取得したとは扱いません。県別の原典版、portalpk_publiの識別子、ETRS89/REGCAN95と郵便の属性を実ファイルの段階で検証します。

## PR #8：実装の二重化を避ける

[未統合PR #8](https://github.com/veygrit-sys/world-localities/pull/8)の対象LT, LV, SI, HR, AT, SEについて、**公式ソースの取得候補・原典URL・条件**は [6か国レビュー台帳](europe-six-source-review-20261108.json)として新しいmainへ保存する方針です。

元PRの別汎用パーサは現行のCSV/GPKG/JSONLに関する取込アダプターと重複し、最新mainとのコンフリクトもあります。よって旧パーサを強制マージしません。残るGMLはクロアチアINSPIREの入れ子形式に合わせた単独のアダプターが必要で、元PRの平坦化パーサだけで全国住所取込成功とは認定できません。

**取得版・SHA・利用権・出典コードがない原典を見かけ上「完了」にしないこと**を全工程で徹底します。配送業者での実際の受付・ラベル生成は、その後の独立した工程です。
