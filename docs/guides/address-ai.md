# 住所の照合・入力補助・表記変換・送り状用短縮

Veygrit のバックエンドから呼ぶ非公開 HTTP API と、同じ JSON を処理する Python/CLI。処理中に住所を外部の翻訳・地図・配送 API に送らない。学習モデルは候補の並べ替えに使用する。照合と表記変換は原典、短縮は配送サービスの項目制約で判断する。原本を上書きせず、住所欄を一つでも確定できなければ配送連携側で人の確認に回せる。

| 操作 | 入力 | 使い方 |
| --- | --- | --- |
| `suggest` | `country, postcode`、任意で `path, query, after, limit` | 国と完全な郵便番号を先に確定。選択した候補IDを `path` に追加して次の階層へ進む。番地を連番から作らない。候補が尽きたら手入力を残す。 |
| `validate` | `country, components` | `matched_scope` と `verified_fields` / `unverified_fields` を返す。`matched` でも郵便番号だけの場合がある。`not_observed` は未収録、`conflict` は入力と参照行の矛盾。 |
| `translate` | 上記＋`source_language, target_language` | 原文と項目別の表記、出典、要確認状態を返す。日本語ローマ字と翻訳は区別。未収録の固有名を推測しない。 |
| `fit_label` | `country, components, profile_id` | 指定した業者・製品の住所欄に収まるかを試す。収まる場合も所在地を確認したことにはならない。 |
| `prepare_label` | 同上。翻訳もする場合は言語を両方指定 | 郵便資料等の同一の住所点または同一事業所の完全な所在地に照合し、必要なら表記変換してから短縮する。`prepared` のみ配送連携の入力候補。要確認では `fields`・`carrier_fields` とも `null`。 |

全操作で共通の応答形式は `{"schema_version":1,"operation":"…","result":{…}}`。[OpenAPI 3.1](../api/address-ai.openapi.json) に各操作の要求・応答例がある。クラウドや契約を用意せずに試すにはリポジトリのルートで次を実行する。

```sh
python -m addressing.safe_suggest build --index /tmp/vey-postal.sqlite --country JP --country US --country CN --country FR --country NL --country LU
python -m addressing.address_ai --index /tmp/vey-postal.sqlite <<'JSON'
{"operation":"suggest","country":"JP","postcode":"150-0001"}
JSON
python -m addressing.address_ai <<'JSON'
{"operation":"translate","country":"JP","source_language":"ja","target_language":"en","components":{"postcode":"150-0001","state":"東京都","city":"渋谷区","town":"神宮前"}}
JSON
python -m addressing.address_ai <<'JSON'
{"operation":"prepare_label","country":"JP","profile_id":"yamato-jp-b2","components":{"organization":"外務省","state":"東京都","city":"千代田区","neighbourhood":"霞が関","house_number":"2丁目2-1","postcode":"100-8919"}}
JSON
```

標準コンテナには日本・米国・中国・フランス・オランダ・ルクセンブルクの索引を同梱する。全リポジトリを使う環境では、上の構築コマンドの `--country` をすべて省くと、利用可能な他の国・地域も索引化できる。候補数は精度や配達先件数ではない。

最後の公開例では日本郵便の事業所個別番号データの行 `4944` に一致し、B2「お届け先住所」は「東京都千代田区霞が関2丁目2-1」になる。未確認の部屋番号を足すと要確認に戻る。一般住宅について郵便番号・町名が一致するだけで、この経路を通すことはできない。

| 地域 | 現在の根拠と限界 |
| --- | --- |
| 日本 | 日本郵便とアドレス・ベース・レジストリで郵便番号、都道府県、市区町村、町域を照合。一部の大口事業所は事業所名と番地を同一行で照合できる。日本郵便または国土地理院に根拠がある表記はローマ字表示できる。一般住宅の部屋番号は対象外。 |
| 米国 | GeoNames の ZIP・地名候補。ワシントンD.C.に限り DC MAR 掲載の街路・番地・5桁ZIPの組み合わせまで照合。ZIP+4 や建物内の住戸に確認済みの印は付けない。 |
| 中国本土 | 香港政府が本土に置く16事務所の公開名・完全住所・郵便番号に限り、英語・繁体字の同一施設を特定できる。州省名や一部の市名の多言語表記は個別住所の存在を証明しない。全国の住宅の番地・部屋の照合、簡繁変換による任意の通り名生成には使わない。 |
| オランダ | ワッデン諸島の5自治体で25,225件。4自治体は取得完了、Texelは原典の先頭13,000行まで。例は `9161 BE → Hollum → Schoolstraat → 22`。郵便番号・通り・番地が同じ公開番号IDに載るかを照合する。対象外は従来どおり郵便番号候補まで。 |
| ルクセンブルク | ACTのBD-Adressesの全国配布から179,793住所点。例は `9755 → Hupperdange → Kaesfurterstrooss → 20`。`9755` と `L-9755` の両方を受け付け、所在地と自治体（例はClervaux）を区別する。 |
| フランスなど | La Poste・INSEE の収録地域では郵便番号・コミューンを照合できる。その他の地域は構築した索引と原典にある精度だけ。国コードや国名が表示できることは住所点までの対応を意味しない。 |

`ups-us-shipto` は米国内の対応範囲における UPS ShipTo、`yamato-jp-b2` はヤマト運輸B2クラウドの国内お届け先欄を生成する。両者とも住所断片のみ。宛名・電話・サービス・出荷元・課金先等がそろった完全な伝票ではない。未確認の部屋番号、桁あふれ、印字できない文字、未対応の宛先は自動送信しない。業者に送る前の承認、宛先本人の同意、業者側での受付・印字確認は別工程。契約別プロファイルはサーバー側の `ADDRESS_AI_PROFILES` から設定し、呼出側から制限を上書きできない。新しい契約で実際の住所欄へ割り付けるには業者別アダプターが必要。

## 非公開サービスで使う

```sh
docker build -f deploy/address-ai/Dockerfile -t vey-address-ai .
# ADDRESS_AI_TOKEN には呼出元のサーバーと共有するランダムな秘密値を事前に設定
docker run --rm -p 127.0.0.1:8080:8080 -e ADDRESS_AI_TOKEN vey-address-ai
```

`POST /v1/address` に UTF-8 の JSON と `Authorization: Bearer …` を渡す。アプリやブラウザーにサービス鍵を渡さず、呼出元でユーザー認証・住所利用権限・テナントごとのリクエスト上限を適用する。TLS とプライベート ingress の背後で運用し、プロキシや APM でも本文と認証ヘッダーを記録しない。`GET /healthz` はプロセスの生存のみ。認証エラーは401、入力形式エラーは422、索引を利用できない場合は503。要確認・未収録の住所は200で結果を返し、障害と区別する。索引は読み取り専用で使い、原典・モデル・索引・プロファイルを版ごとに展開し、同じ組み合わせへロールバックする。取得時の帰属・利用条件は候補の `source_details` から画面と再配布物に引き継ぐ。

[入力補助の出典と階層](../../addressing/SUGGESTIONS.md)・[モデルの再学習と評価](../../evaluation/address-ranking/README.md)・[受入試験と商用公開判定](../../evaluation/address-ai/README.md)。モデルの正解率は既知候補内の順位と、入力から実際に取得して上位に出た割合を区別する。本番国を拡大するときは、未学習の現地住所と誤りを含む住所で誤採用率・要確認率を測り、配送業者のテスト環境と実物ラベルで文字欠落・行切れを確認する。

## 住所点の出典と再現

[オランダのBAG](https://api.pdok.nl/kadaster/bag/ogc/v2/collections/adres)と[ルクセンブルクのBD-Adresses](https://data.public.lu/en/datasets/adresses-georeferencees-bd-adresses/)の保存版はCC0。地域・収録件数・原典URL・SHA-256は[NLの取得記録](../../localities/open_reference/benelux/NL/source.json)と[LUの取得記録](../../localities/open_reference/benelux/LU/source.json)に記載した。NLは番地・番字を連結し、追加符号の前にハイフンを置く。LUは原典にある `4-6` の表記を保持し、中間の番地を推定しない。住所点データは配達可否や住戸を保証しない。

取得時の原本を `inputs[].file` と同じ相対パスで保存しておくと、下記で派生CSVとハッシュを再現できる。公開APIが新版を返す場合は、取得記録の版とハッシュをそろえてから更新する。

```sh
python scripts/project_benelux_addresses.py --manifest localities/open_reference/benelux/LU/source.json --raw-dir /path/to/raw --output /path/to/new-lu
```
