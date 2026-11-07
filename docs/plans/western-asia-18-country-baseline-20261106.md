# 西アジア18か国のLocalities基盤 — 2026年11月6日

現在の原本取得・検索索引・残課題は[2026年11月8日の国別状態](western-asia-current-status-20261108.md)を参照。本ページは形式基盤の到達点を記録した時点の資料です。

## 完成状態の定義

**第1段階：国別データ基盤・形式検証（18/18整備）**
- 国連M49の西アジア18か国・地域を対象に保存済みのGeoNamesの地名アーカイブがある。
- 18か国すべてに現地語／英語住所表示プロファイルがある。
- 9か国の住所・郵便ID形式ルール、5か国の個別郵便番号形式、今回の4か国の国別検証処理を共通APIに統合する。
- 出典別の行政ID、郵便番号、郵便局番号、人道支援P-codeとGeoNames IDを独立して保持する。
- 正式な同一性が証明できないリンクは「名称候補」に留める。

**第2段階：現行公式住所・配達可能性の全国検証（未完了）**
- 公的全国行政ID、郵便番号／配送区域、住居・建物入口を国別の法規と事業者情報で独立検証する。
- 全国の地名・郵便番号網羅率や住所実在率、配達成功率はこの段階では測定・証明できていない。
- 第1段階の達成を第2段階の完成とは表現しない。

## 今回追加した4か国

| 国 | 行政名の外部参照 | 郵便・住所検証 |
|---|---:|---|
| LB レバノン | 8県 | UPUの2018年住所方式に基づく建物・地区・私書箱。全国共通必須郵便番号は証明せず |
| IQ イラク | 現行19県 | 2025年のハラブジャ第19県を別版として保持。5桁郵便番号・郵便局掲載例9件 |
| SY シリア | 14県 | OpenSyriaの14県・62地区・272下位区画・7,605地名を実収録。人道P-codeは郵便番号ではない |
| YE イエメン | 22県・自治体相当区分 | 全国郵便番号を捏造せず、地区・私書箱・ランドマーク・原典コードを区別 |

### シリアのソースデータ

Open-Syria/data-geography のコミット
b4364ee892351671450f873c2e48901ae37a84be を固定して、14＋62＋272＋7,605＝7,953レコードを別レイヤーに収録。

7,605地名のうち英語・アラビア語が両方あるのは7,599件。
6件はアラビア語名が欠けており、翻訳を生成して公式名としない。
既存GeoNames IDとソースOCHA P-codeは独立列で保存。
出典のGit blob SHAとCC BY 4.0・OCHA等の原典帰属情報は
registries/official/western-asia/remaining/syria-reference/manifest.json に保存。
全国の郵便局や建物の配達可能性を示すデータではない。

### イラクのハラブジャ県

2025年5月のイラク法務省第19県新設を反映。
2005年UPUにある18県一覧を現行の19県と同一版にしない。
古いGeoNamesスナップショットにADM1がない場合、偽のgn:IDは作らない。

### レバノンとイエメン

レバノンAtlasには8県、26地区、1,627地籍区画が公開されるが、
原本全件ダウンロードと個別ライセンス照合は未完了。
イエメンのUN/LOCODE22区画コードとOCHAの335地区に関して、
いずれも郵便番号と混同しない。

## 検証と利用

関連ファイル：
- registries/official/western-asia/remaining/country-evidence.json
- registries/official/western-asia/remaining/syria-reference/
- scripts/western_asia_remaining_countries.py
- addressing/western_asia_country.py
- tests/test_western_asia_remaining_countries.py
- tests/test_western_asia_18_country_baseline.py

コマンド：

    python scripts/western_asia_remaining_countries.py report --country all
    python scripts/western_asia_remaining_countries.py syria-verify
    python scripts/western_asia_remaining_countries.py validate --country IQ --postcode 54001 --locality Najaf
    python -m unittest tests.test_western_asia_remaining_countries tests.test_western_asia_18_country_baseline -v

API：

    from addressing import validate_western_asia_country, western_asia_quality_inventory
    print(validate_western_asia_country("CY","2008",direction="inbound"))
    print(western_asia_quality_inventory()["countries_with_format_validators"])

format_only は入力文字列の形式適合のみを意味する。
official_postal_assignment_verified=false、carrier_deliverability_verified=false
は保留すべき事実であり、配送可能性を意味しない。

## 主な根拠・取得継続先

- レバノン政府IDAL8県：https://investinlebanon.gov.lb/en/lebanon_at_a_glance/invest_in_regions
- レバノンAtlas行政地理：https://services7.arcgis.com/OixUjmnC9qQkjog0/ArcGIS/rest/services/Lebanon_Atlas_%E2%80%93_National_and_Subnational_Administrative_Boundaries/FeatureServer
- イラク第19県：https://moj.gov.iq/view.9248/
- Iraqi Post公的郵便局コード例：https://post.iq/?page=15
- UPU Lebanon（2018）：https://www.upu.int/UPU/media/upu/PostalEntitiesFiles/addressingUnit/lbnEn.pdf
- UPU Iraq（2005年の旧版）：https://www.upu.int/UPU/media/upu/PostalEntitiesFiles/addressingUnit/irqEn.pdf
- OpenSyria（行政と地名）：https://github.com/Open-Syria/data-geography
- UNECEイエメン行政コード：https://unlocode.unece.org/directory/subdivisions/?country=YE
- OCHAイエメン：https://humanitarianatlas.org/yemen/
- UPU Yemen（2005）：https://www.upu.int/UPU/media/upu/PostalEntitiesFiles/addressingUnit/yemEn.pdf

第1段階の18か国基盤を整えてから東南アジアへ進むことは可能。
ただし西アジアの現行行政区画・全国郵便番号・住居や配達可能性の
公式原本照合は、第2段階の技術負債として残す。
