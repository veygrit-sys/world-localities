# データの出典・利用条件

原典ごとに利用条件を維持します。全データを単一の緩いライセンスへ変更するものではありません。

| 出典 | 収録対象 | 条件・帰属と参照 |
|---|---|---|
| GeoNames | 12か国・補足4地域の地名・別名、共通行政コード表 | CC BY 4.0。© GeoNames。[配布README](https://download.geonames.org/export/dump/readme.txt)、[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) |
| Servicio Georef | ARの州・departamento・municipio・localidad censal・localidad | CC BY 4.0。Servicio Georef – argentina.gob.ar/georef。[公式条件](https://www.argentina.gob.ar/georef/condiciones-de-uso-y-licencia) |
| IBGE | BRのUF・municipio・distrito・subdistrito | 公開政府データ。IBGEに帰属。[公式API説明](https://servicodados.ibge.gov.br/api/docs/localidades)、[公式データ公開方針](https://www.ibge.gov.br/acesso-informacao/dados-abertos.html)。取得応答は具体的なCCライセンス識別子を返さないため、CC BY等を独自に付与しない |
| DANE / Datos Abiertos Colombia | CO DIVIPOLA | **CC BY-SA 4.0**。APIのデータセットメタデータ `licenseId=CC_40_BY_SA` を保存。DANEに帰属。[データセット](https://www.datos.gov.co/Mapas-Nacionales/DIVIPOLA-C-digos-municipios/gdxc-w37w)、[CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) |
| MINSA公開 INEI UBIGEO参照表 | PEの行政コード・名称の参照表だけを取得 | Open Data Commons Attribution License（ODC-By）。INEI / MINSAに帰属。[実際の掲載データセット](https://www.datosabiertos.gob.pe/dataset/registros-de-nacidos-vivos-en-el-per%C3%BA-2015%E2%80%932025)、[行政参照表](https://www.datosabiertos.gob.pe/dataset/datos-de-registros-de-nacidos-vivos/resource/573f433b-0d44-46e2-932e-14abb9757860)。出生記録データ本体は取得・収録していない |
| INE Paraguay | PY departamento・distrito・barrio/localidadの属性表 | 各GeoNodeメタデータはPublic Domain。INE Paraguayに帰属。統計参照資料であり、資料の境界は法的な境界を示さない。本版の要求は属性のみで幾何形状を取得していない。対象ごとのメタデータURLを追加原典台帳に保存 |
| IDE / Correo Uruguayo | UYの2020年7月の街路・所属表記 | Licencia de Datos Abiertos Uruguay。[掲載資料](https://catalogodatos.gub.uy/dataset/ide-calles-por-localidad-y-departamento/resource/69571a02-32e8-4de8-b414-bc3439f9b1dc)。IDE（Correo Uruguayoの情報に基づく）に帰属 |
| INSEE | GFのCOG 2026地域・県・arrondissement・commune | Licence Ouverte / Open Licence 2.0。Source : Insee, COG au 1er janvier 2026。[利用条件](https://www.insee.fr/fr/information/2008466)、[COG 2026](https://www.insee.fr/fr/information/8740222) |
| Base Adresse Nationale | GF 973の住所観測と街路表記グループ | Licence Ouverte 2.0 / Etalab。Base Adresse Nationaleに帰属。[公式データセット](https://www.data.gouv.fr/datasets/base-adresse-nationale)、[ライセンス](https://www.etalab.gouv.fr/licence-ouverte-open-licence/) |

## 本パックによる加工

原典のバイト列・出典・取得日時・SHA256を保持し、別途検索用のキー、出典付きID、親子・上位関係、未解決状態を作成しています。集落・自治体・街路・住所の原文とコードは書き換えません。名称や近隣座標による出典間の自動統合は行いません。

PYの2件は空の合成親コードを上書きせず、同じ原典にあるdepartamentoとdistritoの明示コードの組み合わせを、地区台帳へ照合して関係だけを追加しています。UYとGFの街路は原典の明示項目をまとめたグループで、道路形状や郵便配達可能性の新しい証明ではありません。

DANE原典とDANEに由来する加工部分にはCC BY-SA 4.0の帰属・継承条件を維持します。他の原典と出典別に区別したコレクションとして扱い、全体をCC BYだけのデータと表示しないでください。各出典を再配布する際は、本書と当該出典の利用条件・版・加工した旨を添えてください。

UPU国別資料と国連M49は住所構文・統計上の収集区分の参照資料です。UPUの有料郵便番号データベースや資料PDF全文は収録していません。
