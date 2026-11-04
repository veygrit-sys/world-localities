# データ出典・利用条件

本パックは異なる出典を別の名前空間で保持します。パック全体へ一律のデータライセンスを付けるものではありません。原典を変換した階層索引は本プロジェクトの生成物であり、原典提供者が作成・推奨した製品ではありません。

## GeoNames

- 出典：GeoNames。各国・地域の地名と別名、admin1CodesASCII、admin2Codes、countryInfo、readme。
- [配布・スキーマ・利用条件](https://download.geonames.org/export/dump/readme.txt)、[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)。
- Attribution: GeoNames — https://www.geonames.org/
- 原典ZIPと取得ハッシュを保持。現行候補への絞り込み、参照関係の解決、検索用文字正規化は本プロジェクトが実施しました。提供者による配達保証ではありません。

## 米国 Census Gazetteer / TIGER

- Source: U.S. Census Bureau, 2026 Gazetteer Files; 2026 TIGER/Line address ranges and feature names, District of Columbia county-equivalent 11001.
- [Gazetteer配布](https://www.census.gov/geographies/reference-files/time-series/geo/gazetteer-files.html)、[TIGER技術文書](https://www.census.gov/programs-surveys/geography/technical-documentation/complete-technical-documentation/tiger-geo-line.html)、[引用方針](https://www.census.gov/about/policies/citation.html)。
- 米国政府が作成したデータとして原出典を表示します。商標・ロゴ・他者の著作物を同じ条件とみなさず、Censusによる推奨を表示しません。
- 属性参照を抽出し、コードで接続したものです。境界形状、実在家屋、USPSの住所認証を提供するものではありません。

## カナダ SGC 2021

- [Statistics Canada SGC 2021](https://www.statcan.gc.ca/en/subjects/standard/sgc/2021/index)、[Statistics Canada Open Licence](https://www.statcan.gc.ca/en/terms-conditions/open-licence)。
- Source: Statistics Canada, Standard Geographical Classification (SGC) 2021, 2021. Reproduced and distributed on an "as is" basis with the permission of Statistics Canada.
- Adapted from Statistics Canada, Standard Geographical Classification (SGC) 2021, 2021. This does not constitute an endorsement by Statistics Canada of this product.
- 英仏CSVを元コードで照合。文字コードをUnicodeへ変換した検索索引を生成しました。個人を特定する目的のデータ結合は行っていません。

## カナダ ODA v1 / Northwest Territories

- [Open Database of Addresses](https://www.statcan.gc.ca/en/lode/databases/oda)、[Open Government Licence – Canada](https://open.canada.ca/en/open-government-licence-canada)。
- Contains information licensed under the Open Government Licence – Canada.
- Source: Statistics Canada, Open Database of Addresses version 1.0, Northwest Territories, 2021; observed data provider City of Yellowknife.
- 原ZIP内の `Data_Sources.csv` と `ODA_v1_metadata.pdf` も保持しています。収録元ごとのライセンス・帰属表示はその一覧を参照してください。全国住所台帳として扱いません。

## メキシコ INEGI

- Fuente: INEGI, Catálogo Único de Claves de Áreas Geoestadísticas Estatales, Municipales y Localidades. Archivos distribuidos y adquiridos el 17 de octubre de 2026 (UTC).
- [配布カタログ](https://www.inegi.org.mx/app/ageeml/default.html)、[Términos de libre uso](https://www.inegi.org.mx/inegi/terminos.html)。
- 原データ・メタデータを保持して出典を明示し、本プロジェクトが行ったUTF-8 CSVの選択、索引化、階層構築を区別します。INEGIが本パックを推奨・認証しているとは表示しません。
- 取得日時、アーカイブ内の生成名、統計の基準年は別です。秘匿値や欠損値を推測で埋めません。

## サンピエール・ミクロン

- INSEE, Code officiel géographique 2026：[COG配布](https://www.insee.fr/fr/statistiques/8740222)、[再利用条件](https://www.insee.fr/fr/information/2008466)。
- Base Adresse Nationale, département 975：[CSV配布](https://adresse.data.gouv.fr/data/ban/adresses/latest/csv)、[BANについて](https://adresse.data.gouv.fr/decouvrir-la-BAN)。
- Licence Ouverte 2.0 / Etalab。出典と版を保持し、COGは975に属するcollectivité・communeだけを索引化します。BANの自治体認証フラグは原行に保持します。

## 限定資料の継承と未収録資料

US D.C.の番地範囲、CA ODA NT、PM BANは `Veygrit_world-localities_GitHub_20261016.zip` のversion 8から原典ハッシュを検査して継承しました。COG 2026は先行南米パックと同じ全国配布ZIPで、PMへの抽出条件を個別に検証しています。

バミューダとグリーンランドの公式住所台帳は、一括再配布の条件を今回確定していないため未収録です。各地域のGeoNamesデータは上記の別ライセンスで収録しています。

本書は収録元と条件の記録です。郵便事業者の非公開・有償住所台帳を取得または再配布したものではありません。
