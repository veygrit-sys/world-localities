# 公式住所APIの選択と照会

Veygritの住所入力で公的な原典の候補を提示するための、登録・APIキー不要の照会機能です。標準の住所登録やオフライン照合はローカルで完結します。アプリから利用する際は、利用者が対象国と照会先を選んだ時に `lookup_official` を呼びます。送信する項目はその原典が受け付ける住所、郵便番号、または識別子です。

## 利用例

```bash
python -m localities official-sources
python -m localities official-sources --country US
python -m localities official-lookup --country NL --source nl-pdok --query 'Dam 1, 1012JS Amsterdam'
python -m localities official-lookup --country HK --source hk-als --query '5 Edinburgh Place'
python -m localities official-lookup --country MC --source la-poste --query 98000
python -m localities official-lookup --country US --source dc-mar --query '1600 Pennsylvania Avenue NW'
python -m localities official-lookup --country AR --source ar-georef --query 'Balcarce 50' --province 02
```

```python
from localities.official_api import official_sources, lookup_official

sources = official_sources("NO")
result = lookup_official("NO", "Karl Johans gate 22 Oslo", source="no-kartverket", limit=3)
```

国はISO形式の2文字コード、件数は1〜10です。1回の照会で指定した原典にHTTPS GETを1回送ります。返却値には原典、発行機関、地理的範囲と候補が入ります。

| 項目 | アプリでの扱い |
|---|---|
| `status=candidates` | 候補の `scope` と `comparison` を見て、利用者に選択肢を示す。 |
| `status=no_candidates` | 取得した応答に対象国・条件に合う候補がなかった。別表記や手入力を受け付ける。 |
| `status=unavailable` | 通信失敗、HTTP制限、原典のエラーまたは応答形式の変更。CLI終了値は1。 |
| `comparison=exact_label` | 返却ラベルと入力が、大文字小文字・Unicode正規化・空白をそろえると一致。通りのラベルなら検証範囲も通りまで。 |
| `comparison=exact_postcode` / `exact_identifier` | 選んだ国・地域で郵便番号または入口IDが一致。 |
| `comparison=suggestion` | 住所候補。入力の自動上書きには使わない。 |

各APIの候補数には上限があり、一部は類似検索です。結果に建物があっても、個別の宛先への配達可否は未検査のため `deliverability_verified` は常に `false` です。原典ごとの帰属表示と利用条件は台帳の `publisher` と `documentation` から確認できます。

## 実装済みの照会先

| 国・地域 | 原典ID | 入力と照合範囲 |
|---|---|---|
| フランス本土・コルシカ | `fr-ban` | 住所の自由入力。IGNの結果に合わせて番地、通り、地域を区別。 |
| フランス、モナコ、仏領11地域 | `la-poste` | 5桁の郵便番号 → コミューン・配達地名。INSEE自治体コードを既存の公式対応表で照合。対象は FR、MC、BL、GF、GP、MF、MQ、NC、PF、PM、RE、WF、YT。 |
| オランダ | `nl-pdok` | 欧州オランダのBAG住所を入力。PDOKの複数索引から住所レコードを選択。 |
| ノルウェー | `no-kartverket` | 登記上の番地と郵便地名。スヴァールバル諸島・ヤンマイエンは対象外。 |
| ルクセンブルク | `lu-act` | 国土地籍当局の精度コードを、番地、施設、通り、地域、国に対応付け。 |
| スイス、リヒテンシュタイン | `ch-swisstopo` | 既知の公式入口ID（EGAID）で照会。例はベルンの `101002312`、ファドゥーツの `299012509`。返却された自治体番号で国を確認。 |
| 香港 | `hk-als` | 建物名または住所から、原典にある英語・繁体字の建物候補を取得。階・部屋の照合は対象外。 |
| 米国 | `us-census` | 50州・D.C.の住所を街路の番地範囲と照合。個別建物の実在確認には使わない。 |
| 米国・ワシントンD.C. | `dc-mar` | 正式な番地・通り名・方角の行を入力し、市の有効な番地ポイントを検索。 |
| イタリア・ボローニャ市 | `it-bologna` | 登録表記の通り・番地（例 `Piazza Maggiore 6`）で市の住居番号台帳を照会。 |
| カナダ・バンクーバー市 | `ca-vancouver` | 番地と市が使う通りの表記を入力（例 `453 W 12TH AV`）。物件住所まで。 |
| オーストラリア・クイーンズランド州 | `au-queensland` | 番地・通り・locality・QLDを含む登録表記（例 `2 George Street Brisbane City QLD`）で照会。 |
| アルゼンチン | `ar-georef` | 通り・番地を正規化。州を指定できる場合は `--province` に2桁のINDECコードを渡す。 |
| ウルグアイ | `uy-ide` | 住所からIDEの候補を取得。番地を伴う原典の正常な照合と近似候補を区別。 |
| 南アフリカ・ケープタウン市 | `za-cape-town` | 番地・通り・suburbを含む市の物件住所。例は市庁舎の `12 Hertzog Boulevard Foreshore`。 |

2026-11-24（日本時間）の導入確認では15原典・26国地域コードについて、公開施設の住所、公式入口IDまたは郵便番号を使い、各ルートから候補を取得しました。精度評価や稼働率の測定には、別途、地域別・住所種別の標本が必要です。

## 追加候補を組み込む順序

[機械可読な候補台帳](../../localities/official_api_sources.csv)には公開主体、国・地域、全国・自治体などの範囲、照合できる項目、公式資料を記録しています。`official-sources` の `candidate` は調査中、`implemented` は明示的に照会できる原典です。候補の掲載は商用利用条件やAPI提供の継続性の認定を意味しません。

| 台帳の `intake` | 原典数 | 採用判断と対象 |
|---|---:|---|
| `live_api` | 15 | 無認証の実照会で住所候補または郵便地域を取得。ケープタウンは市のカタログが案内するFeatureServerに更新し、suburbを含む番地を照合。 |
| `bundled_offline` | 1 | 台北市は公式CSVから12区の門牌索引を収録。全文はローカルで照合できる。[検索例・再現手順](../../localities/open_reference/taipei/) |
| `review_national_register` | 8 | 次の優先調査。アイスランド、エストニア、チェコ、スペイン、ポーランド、ラトビア、リトアニア、スロベニア。既存収録データとの重複、現役の番地ID、全国の取得方法を確認。 |
| `review_regional_register` | 8 | ウィーン、ヨーテボリ、ベルリン、タンペレ、フランダース、ボゴタ、ベロオリゾンテ、ウェリントン。市・州別に管轄と番地照合のテストを行う。 |
| `review_postcode_or_identifier` | 2 | 英国ONSは郵便番号・地域、ドバイ市はMakani入口番号。用途と入力型を限定して評価。 |

`status` はオンライン照会の実装状況、`next_check` は候補別の次の確認内容です。台北市は `official-lookup` ではなく [オフライン住所照合](../../localities/open_reference/taipei/) から使えます。この台帳で利用可能な範囲はオンライン26国・地域と台北市（TW）を合わせて27国・地域です。

### 欧州で取り込みを復旧した地図原典

Geofabrikの新しい地域別配布パスに対応し、公開元と選択した地域の一致を検査します。6小国と王室属領の地図は、道路・地名・OSMに記載された番地を補うために取り込みました。台帳の公式API件数には加算しません。

- アンドラ、リヒテンシュタイン、モナコ、サンマリノ、バチカン、マルタの6抽出を再取得し、索引63,870件を検査。バチカンは国が明示された番地候補1件に限定。[6か国の取得記録](../../registries/europe/microstates/intake-20261124.json)
- ガーンジー・ジャージーの共同抽出とマン島の抽出を再取得。ジブラルタルの既存資料を含む索引全体は27,104件。共同抽出内で所属を決められない番地候補2,653件を `UNRESOLVED` として保持。[王室属領の取得記録](../../registries/europe/crown-four/intake-20261124.json)

日本のデジタル庁アドレス・ベース・レジストリの自前運用や既存の国土地理院オフライン原典は別経路として利用できます。日本の公式ホストによる無認証APIは今回の実装件数に含めていません。
