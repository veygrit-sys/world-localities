# 西アジア18か国の地名・原典参照

現在の到達点は[実原本取込・国別残課題](../../../docs/plans/western-asia-current-status-20261108.md)を参照してください。2026年11月8日に18か国すべての原本参照層を更新しました。現行の公式地名・郵便番号・建物住所の全国照合完了は未証明です。

| 内容 | 現在の収録・実装 |
|---|---|
| GeoNamesの国別地名原典 | 18か国・215,576行、既存IDと国別分類を維持 |
| 今回取得した原本 | 23原本・75,062行。政府直接公開と人道・第三者参照を区別 |
| 既存OpenSyriaの共通検索接続 | 7,953行。今回新規取得した政府原本には数えない |
| 出典別に検索できる参照行 | 83,015行。別出典の重複場所を含み、一意な住所件数ではない |
| アゼルバイジャン公式IABT | 原本取得・6,697コードの解析と監査まで。公開再配布条件は未確認 |
| 国別の現地語／英語表示・形式検証 | 18か国対応。実在や配達の判定ではない |

## 現在のデータと操作

[imports/README.md](imports/README.md)に、原本、SHA-256、変換済み行、出典・権利、国別状態、原本再生の検証結果、検索方法を集約しています。生成SQLiteは原典から再構築できるためGitには含めません。

    python -m localities western-asia verify
    python -m localities western-asia audit --output /tmp/western-asia-audit.json
    python -m localities western-asia build --output /tmp/western-asia.sqlite
    python -m localities western-asia verify-index --db /tmp/western-asia.sqlite
    python -m localities western-asia query --db /tmp/western-asia.sqlite --country JO --postcode 11190

住所形式APIは addressing.validate_western_asia_country を使用します。国別形式と住所表示に限定し、今回のデータ取込で実在・配達可能性の判定へ変更していません。

## 既存の参照層

| 保存先 | 範囲と役割 |
|---|---|
| [rules.json](rules.json) | TR・CY・KW・AE・SA・BH・QA・OM・PSの国別形式と当初の出典調査 |
| [admin-crosswalk/](admin-crosswalk/README.md) | SA・BH・QA・OM・PSの手動公式名称参照・候補照合 |
| [postal-data/](postal-data/README.md) | OM・PS・SA・BHの85件の手動転記。全国原本ではない |
| [caucasus-levant/](caucasus-levant/README.md) | AM・GE・AZ・IL・JOの当初参照・取得アダプター |
| [remaining/](remaining/) | LB・IQ・SY・YEの国別形式と原典、既存OpenSyria投影 |
| [imports/](imports/README.md) | 取得済み原本を使う現在の共通検証・検索・国別残課題 |

旧参照層の「原本未取得」「取込0」は、それぞれの手動転記・調査スナップショットの状態です。現在の全体状況は imports/manifest.json と imports/country-status.json を使用してください。

## 粒度・版・権利の境界

郵便番号、郵便局番号、私書箱、統計コード、人道P-code、入口IDは独立した値として保存します。名称だけの一意候補を確認済み同一性へ昇格させず、原典の国境・所属分類を別出典へ上書きしません。

イラク旧18県、レバノンの重複・Conflictコード、カタールの目録と原本件数差は監査記録に残しています。AZ・KW・OM・SAのGADM由来人道参照は商用再利用条件の確認が残ります。[NOTICE](imports/NOTICE.md)と原本ごとの出典条件を確認してください。
