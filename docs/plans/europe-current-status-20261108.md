# 欧州Localities：全体整理・進捗台帳（2026-11-08）

> **単一の進捗入口。** この文書は原典データやソースコードの代わりではありません。すべての状態は2026年11月8日のGitHubで確認した**時点記録**であり、最新の国別原典の存在・ライセンス・配送可能性を自動で認定しません。国別57行の機械可読一覧は [europe-status-20261108.json](europe-status-20261108.json) に置きます。

## まず、何が完成していて、何が未完成か

| 区分 | 保存・実装の状態 | **検証済みの意味** | この段階で**証明されないこと** |
|---|---|---|---|
| 欧州の基礎地名台帳 | [57コード、GeoNames 1,161,589地物](../../registries/europe/README.md)、別出典のEurostat LAU 32か国104,687行 | 保存ファイル・コード・親参照などの整合性 | 住所実在、現行自治体名の全件一致、配達 |
| 西欧公式住所資料 | [AT/BE/CH/FR/LI/LU/NL計51,941,346原典観測行](../../releases/hierarchy/western-europe/README.md) | 過去に固定した原典の照合・再現 | 現行一意の住所数。旧版や無効レコードを含む |
| **チェコ RÚIAN** | **2026-10-31全国ZIPの全6,258自治体CSV、住所観測3,023,585件を実取込・索引検証**。[PR #30](https://github.com/veygrit-sys/world-localities/pull/30) | 公式ソースの全CSV行とSQLiteの同一性・一意ID | 現在有効な全国全住所率、運送会社の配達可否 |
| ルーマニア SIRUTA | [2026年の県・自治体・集落16,978行](../../registries/europe/priority-six/README.md) | 公式由来の行政・集落階層の固定版 | 道路・建物番地。郵便番号0の実在 |
| ポルトガル CAOP2025 | [本土3,049・アゾレス156・マデイラ54＝計3,259教区行](https://github.com/veygrit-sys/world-localities/pull/16) | 公式行政区画の固定版・照合 | 住宅住所や配達確認 |
| デンマーク・スウェーデン OSM | [全国PBFから索引観測4,867,793行](https://github.com/veygrit-sys/world-localities/pull/13) | ODbLに基づく出典別住所候補・道路・地名の取込 | 公式住所登録簿の完全性、現存・配達可否 |
| バルカン11か国 | [GeoNames 113,638行の全件監査と共通CLI](../../registries/europe/balkan-11/README.md) | 既存原典の構造検証・SQLite検索 | 11か国の全国住所の新規全量取込 |
| 東欧4か国 | [MD/UA/BY/RUのGeoNames 272,110行の全件監査](../../registries/europe/eastern-four/README.md) | 元原典の件数・ハッシュ・参照 | CUATM・KATOTTG・SOATO・GAR/FIAS公式全国原本の取得完了 |
| ミニ国家・属領 | [6小国](../../registries/europe/microstates/README.md)／[JE/GG/IM/GI](../../registries/europe/crown-four/README.md) | 公式名称とOSMの出典分離、所属未確定行の隔離 | 全住所の法的・郵便的な確定 |

**件数の加算禁止：** 上表はGeoNames、Eurostat、公式行政区画、公式住所点、OSM観測、旧版等が重複し得る別原典です。単純合計して「欧州全住所数」や「唯一の住所ID件数」を算出してはいけません。ロシアのGeoNamesには**アジア側を含むロシア全域**が入ります。グリーンランドはNordicsの管理対象ですが、欧州57コードの分母に含まれません。

## 進捗判定は5層に分ける

| 判定 | 確認事項 | 次の判定へ進む条件 |
|---|---|---|
| L0 国・地域コードの登録 | 57の収集コードを管理 | 実物を取得 |
| L1 地名・行政の保存元照合 | 原本のハッシュ・行数・ID・親関係検査 | 各国の正式な住所・行政原典を版固定 |
| L2 公式原典の実ファイル取込 | 配布元の元バイト・件数・版・識別子を全件再現 | 現行性、出典間の参照ID照合 |
| L3 現行住所・郵便の独立検証 | 道路、建物番号、郵便区域、廃止/将来日付の扱いを確認 | 独立した正解データで偽陽性などを評価 |
| L4 配送実証 | キャリア固有住所表記、ラベル/API受付、例外を確認 | 実際の対象サービスごとに配送可否を証明 |

**全国の郵便・配送住所についてL4を達成した国は、本台帳からは認定していません。** L1の全件監査成功とL2の公式原典取込成功は別物です。

## 直近のCZ・RS・ESの状態を一本化

| 国 | 現在の実装 | 実原典の状態 | 次にやること |
|---|---|---|---|
| **CZ（チェコ）** | [PR #30 merged](https://github.com/veygrit-sys/world-localities/pull/30)、公式RÚIAN全国取込成功 | 2026-10-31全国ZIPのSHA-256 \`56dc1392033cc6ab21e7f2bafc553c2837d49e62049a60a0f238a0ba83c27877\`。3,023,585件、6,258ファイル、S-JTSK座標を保持 | GitHub Actionsの一時アーティファクトを**期限切れ前に権利適合した永続保管先へ固定**。次に現行性・独立精度評価 |
| **RS（セルビア）** | 取込コード・合成テストあり、[PR #29 open](https://github.com/veygrit-sys/world-localities/pull/29) | RGZ全国の道路と番地の公式CSVをGitHub Actionsから取得する試みがタイムアウト。**全量未取得** | 認可された公式配布経路で道路・番地の両ファイルを入手、SHA-256を固定し実ヘッダー・共有道路IDを確認 |
| **ES（スペイン）** | CartoCiudad県別データ取込コードあり、[PR #29 open](https://github.com/veygrit-sys/world-localities/pull/29) | 52県・地域分のGeoPackage配布一覧は確認。ダウンロードのハンドシェークはHTTP 403。**全52ファイル未取得** | 公式サイトの正当な取得手段で県別原本を保存、\`portalpk_publi\`等の実スキーマを固定して52単位で再実行 |

該当の[RS/ES実アクセス検証ワークフロー](https://github.com/veygrit-sys/world-localities/actions/runs/42231016513)は**失敗**。コードの契約テストが成功したことを公式原典の取得成功と混同しません。認証・利用制限・CAPTCHAの回避を前提にした取得は採用しません。

### 残るオープンPR

| PR | 対象 | 現在の整理方針 |
|---|---|---|
| [#8](https://github.com/veygrit-sys/world-localities/pull/8) | LT・LV・SI・HR・AT・SE | **未統合**。旧版の出典登録・取込アダプター中心。後からマージされたスウェーデン・北欧・バルカン関連の同種機能と重複するため、変更をレビューしてからrebase・統合または分割 |
| [#29](https://github.com/veygrit-sys/world-localities/pull/29) | RS・ES | **未統合**。取得失敗の記録を保持。ダウンロード可能な正式配布元と利用条件の確認後に実取込を再実行 |

## 既存の配置は維持し、入口だけ統一

| 正本・入口 | 役割 |
|---|---|
| [registries/europe/countries/CC](../../registries/europe/countries) | 各国GeoNames分割CSV・メタデータ。新規公式住所台帳で上書きしない |
| [registries/europe/eurostat-lau/CC](../../registries/europe/eurostat-lau) | Eurostat LAU。正式な郵便住所台帳ではない |
| [releases/hierarchy/western-europe](../../releases/hierarchy/western-europe) | 既存西欧公式住所・道路原典の再現と記録 |
| [registries/europe/priority-six](../../registries/europe/priority-six) | イタリア等6か国の公式資料台帳／ROのSIRUTA |
| [registries/europe/es-pt-mt](../../registries/europe/es-pt-mt) | ES/PT/MT共通の出典別検索とPT行政原典 |
| [registries/europe/balkan-11](../../registries/europe/balkan-11) | 東南欧11か国の全件監査と出典方針 |
| [registries/europe/eastern-four](../../registries/europe/eastern-four) | MD/UA/BY/RUの地名監査・公式候補 |
| [registries/europe/microstates](../../registries/europe/microstates) / [crown-four](../../registries/europe/crown-four) | 小国・属領の別ルールとOSMの帰属隔離 |
| [scripts/europe_official_cz_rs_es.py](../../scripts/europe_official_cz_rs_es.py) | CZ全国取込、RS・ES配布確認。原典取込は使える国だけ実行 |
| [docs/plans/europe-status-20261108.json](europe-status-20261108.json) | 57国・地域の**時点別作業進捗**。実データの置換ではない |

既存コードの無理な一括移動・原典の上書き・新規の重複国別リポジトリは行わない。原典の単一の保管責任と、複数の検証入口は両立させる。新しい原典は国別の版・権利・領域を確定して追加する。

## 次の作業（優先順位）

1. **P0 / 入手不能な2国を解消：** RSの正式RGZ道路/番地CSV、ESの公式CartoCiudad 52 GPKGについて、合法的なダウンロード方法・契約・権利・発行年月・原ファイルハッシュを確定し、失敗状態のPR #29を更新する。入手できない国は無理に成功扱いしない。
2. **P0 / チェコの成果を永続化：** CZ公式原本・監査報告・SQLite索引のSHA/出典・版を権利適合の永続保管先に記録。GitHub Actionsは保存期限のある配布先であり、長期唯一の正本にしない。
3. **P1 / PR #8の重複整理：** LT/LV/HR/SI/AT/SEの未統合コードを、mainにある既存受入処理と比較し、必要な差分のみ残す。上書きや全件受入済みと誤認しない。
4. **P1 / その他の公式全国取込：** PLのRÚIAN/PRGに相当する別システム、ITのANNCSU、DE・GB・IEの未取得住所原典、北欧のFI/NO/IS公式住所、HR/SIの許諾済み住所点などを版固定して順次実取込する。国別の入手性と権利を先に調べる。
5. **P2 / 住所の正規化・参照整合：** 地方政府/郵便/住所点の発行IDを出典別に結合し、旧版・重複・行政階層変更・道路改称・座標系・言語を検証する。名前類似だけでは同一視しない。
6. **P3 / Veygritでの利用判定：** 実在住所と郵便番号の独立精度、配送業者別住所フォーマット、ラベル/API受付を別々に評価。住所トークン化や翻訳は原典の精度判定を超えて「配達可」を返さない。

## 保存された実物と一時アーティファクトの違い

- リポジトリ内の原典・派生CSV・メタデータ・コードはGitコミットで追跡する。
- **全国住所の巨大ZIPやSQLiteはGitHub Actionsアーティファクトとして配布されるものがある**。そのようなファイルは保持期限が切れた後に同じURLで再取得できる保証がない。保存版ごとの外部アーカイブ先・容量・署名/ハッシュ・配布権利と再取得手順を別途確保する。
- PRのCIが緑でも、実住所の現行性・配達可能性を証明しない。逆にRS/ESのアクセス失敗を記録していても、国のデータが存在しないと断定しない。

## 監査入口

リポジトリのルートから、データを上書きしない別出力パスで実行します。

\`\`\`bash
python registries/europe/build.py verify
python -m localities balkan audit --country all
python -m localities eastern audit --country all
python -m localities microstates audit --country all
python -m localities crown audit
python scripts/europe_priority_six.py audit-ro
python -m unittest discover -s tests -p 'test_europe_official_cz_rs_es.py' -v
\`\`\`

上記は保存済み原典や合成テストの検査です。CZ全国ファイルを再取得・解析するには [CZ専用GitHub Actions](../../.github/workflows/cz-ruian-national-index.yml) または明示的な新しい作業ディレクトリが必要です。公式CZの一度の成功を、RS・ESの公式ファイル全量取込成功に一般化しません。

更新時はこの台帳の**日付と証跡**を更新し、古い進捗記録は変更履歴として保持してください。
