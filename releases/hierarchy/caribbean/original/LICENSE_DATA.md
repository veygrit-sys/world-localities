# データの出典・利用条件

各原典の表示条件を維持してください。このパッケージは複数出典を含み、元データの権利や利用条件を単一のコードライセンスで置き換えません。

| 原典 | 表示・条件 | 対象 |
|---|---|---|
| GeoNames | GeoNames、CC BY 4.0、https://creativecommons.org/licenses/by/4.0/ | 全28国・地域と共通コード表 |
| HDX COD-AB | OCHA / HDXおよび各カタログの原提供元。公開カタログはCreative Commons Attribution for Intergovernmental Organisations（`cc-by-igo`） | 20国・地域のXLSXまたはSHP内DBF属性 |
| INSEE | INSEE, Code officiel géographique 2026。Licence Ouverte 2.0。https://www.insee.fr/fr/information/2008466 | GP / MQ / BL / MF |
| US Census Bureau | U.S. Census Bureau, 2026 Gazetteer Files。US government work | PR行のみ索引化 |

HDXの`license_title`、`license_url`、`dataset_source`は原カタログと登録情報をそのまま保存しています。GADM等を原提供元とするCOD-ABも含まれます。本版が公開カタログと異なる再許諾や政府による保証を追加することはありません。用途への適用時には各原典の表示・利用条件を確認してください。

原ファイルは変更せず同梱しています。ZIPがSHPを含む場合、実行コードが使用するのは指定DBFの属性だけです。境界図形からの位置包含判定は実装していません。Census・INSEE・GeoNamesの共通原ファイルには本版対象外の行もありますが、索引化する国・地域は明示的に限定しています。

原典への変更・加工：出典付きの行政・集落索引、検索用の正規化キー、元コードに基づく親子接続、別名の期間フィルター、要確認フラグ、原典別の集計を作成しました。元の氏名・住所の個人情報ファイルを収集したものではありません。

このパッケージのPythonコードは既存Veygrit中米版の実装を基礎に、カリブ海のコード・国別範囲・ADM5・INSEE・PRの取込を追加したものです。既存プロジェクトのライセンス条件がある場合はそれを維持してください。データ提供者の承認・住所の実在・配送可否は主張しません。
