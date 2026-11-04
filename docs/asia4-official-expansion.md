# 香港・韓国・マレーシア・台湾の並行強化

作業の単位を国・地域とし、原典取得・変換・検証を並行して進めます。既存の基礎台帳と公式JP/TWレイヤーは保持し、追加分を `registries/official/expansions/<国コード>/` に収録します。

## 国ごとの到達範囲

| 対象 | 最初の強化 | 原典・派生の範囲 | 検証の限界 |
|---|---|---|---|
| 香港 | 中英住所・建物・街路の原文照合 | ALS ZIPの18地区の2Dファイル全行、182,254観測を保存・再生。CsuIdは159,427種類 | 観測行数は一意住所数・建物数ではない。公営住宅の3Dデータは今回の検索対象外 |
| 韓国 | 世宗市の道路名住所・郵便番号・建物番号 | 2026年9月の世宗市データ27,966観測を先行収録。1,139道路コード・153郵便番号を保持 | 韓国全国や全建物の完全性を主張しない。許諾を確定していない全国道路コード資料は公開対象にしない |
| マレーシア | 郵便番号と都市・州の対応 | 2026年6月基準の公式CSV、2,932観測・2,930郵便番号を原文のまま保持 | 道路・建物・番地の台帳ではない。年次更新の記録を現在有効と自動判定しない |
| 台湾 | 公式の路名と既存の郵便区域表記の接続 | 民国115年の保存CSVの全35,798観測。元の都市・行政区域・路名を保持 | 全物理道路・番地の実在台帳ではない。路名の英語訳は原典にないため生成しない。郵便関係は既存の3桁接頭辞の範囲 |

全国と名の付く原典でも、原典の全行を欠落なく取り込んだことと、現実世界の全国完全性を証明したことは区別します。

## 原典・派生・検証の関係

1. **原典を固定する。** 国ごとの `sources.json` にURL、提供者、取得時点、原典の版・基準時点、サイズ、SHA-256、利用条件を記録する。取得日を法的施行日や更新日に置き換えない。
2. **原文を保持して派生列を作る。** 郵便番号・建物番号・IDは文字列として保持する。比較用の空白整理・表記整理は原文と別の列にする。
3. **保存ハッシュを確認する。** 原典と派生ファイルが固定した記録に一致するか調べる。
4. **原典から全行を再生する。** 国ごとの変換処理で再現した結果と保存済みCSVを比較し、件数・識別子・欠損・複数対応を確認する。
5. **国別台帳と検索へ接続する。** 地域ごとのデータをコピーせず、国別モジュール台帳から追加レイヤーを参照する。

香港の同じ建物IDに複数住所があるケース、マレーシアの同じ郵便番号に複数都市があるケースを削除・強制統合しません。台湾の郵便区域の名称対応も、法的な行政区域の同一性と断定しません。

## 確認・検証・検索

以下はリポジトリのルートから実行します。

```bash
python -m localities country validate-catalog
python -m localities country inspect --country MY
python -m localities country verify --country MY
python -m localities official search --country MY --text 40160 --field postcode --exact --limit 5
python -m localities official search --country TW --text 忠孝東路 --field road --limit 3
```

マレーシアの `40160` はSungai BulohとShah Alamの2観測を返します。台湾の例は保存CSV内の8観測に一致し、`--limit 3` では3件だけを表示して `truncated: true` を返します。これらは動作・対応関係の確認であり、入力された完全な住所の配達可能性の判定ではありません。

検索は `--field` を省略すると許可された欄を横断し、通常はNFKC・大文字小文字を揃えた部分一致です。`--exact` はその比較表記での完全一致です。生の数値変換や、同名の別地域の統合は行いません。表示件数の上限を検索対象全体の件数と混同しないでください。

各国の元の検証入口は次のとおりです。

```bash
python scripts/import_hk_official.py verify --folder registries/official/expansions/HK
python scripts/import_kr_official.py verify --folder registries/official/expansions/KR
python scripts/import_my_official.py verify --folder registries/official/expansions/MY
python scripts/import_tw_official.py verify --folder registries/official/expansions/TW
```

個別の再構築引数や利用条件は [追加レイヤー一覧](../registries/official/expansions/README.md) から各国資料へ進んでください。

## 品質表示と後続の強化

保存・変換検証が成功しても、`national_completeness_verified` と `deliverability_verified` は引き上げません。ライブ原典と照合していない最新性は不明として表示します。原典ごとの件数は合算して世界の一意住所数にしません。

後続の作業は、原典の版を固定した差分更新、独立した実住所の評価例、住所・建物の変更や廃止の扱いです。韓国は世宗市での再現性を確認してから他の市道へ広げます。台湾の6桁郵便番号や番地、香港の階・部屋、マレーシアの道路・建物は、それぞれ確認できる別の原典を取得してから追加します。

既存の[国別更新方針](country-modules.md)・[住所評価契約](address-evaluation.md)に従い、学習用と評価用を原典・実体単位で分離します。今回の原典取込だけでは、モデル学習・独立精度評価・配達成功の実証を実施したとは扱いません。
