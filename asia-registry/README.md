# アジア地域基礎データ

GeoNames の国別スナップショットから、行政区分・集落・関連する履歴地名を収録した基礎 Gazetteer です。
収録対象は52国・地域プロファイルです。保存済みの対象数と件数は `publication.json` と `manifest.json` を参照してください。
全国の公的自治体を網羅した台帳、公式対訳辞書、配達先住所台帳ではありません。

対象は `scope.json` の 51 アジア国・地域プロファイルと、追加対象のロシア全域です。
ロシアをアジア側だけに切り分けていません。原典の国コード・別国コードを保持し、境界や帰属を変更しません。
原典取得日時、原典の更新日と SHA-256 は `manifest.json` と各国の `metadata.json` に記録しています。
取得日は地域の法的現況の確認日を意味しません。

## 使い方

Python 3.11 以上、標準ライブラリのみで実行できます。国別 ZIP には圧縮 CSV、ADM1 表示用 CSV、
メタデータ、帰属表示が入ります。大きいZIPは8 MiB以下の連番ファイルへ分割しています。
`package.py unpack` が必要な分割ファイルを順に結合し、分割ファイル・ZIP全体・収録ファイルのハッシュを確認して展開します。
分割ファイル単体はZIPとして開けません。同じ国の全パートが必要です。
`archives.json` は保存済みZIPと分割ファイルの一覧です。取得の進行中は `publication.json` の状態が `partial` となります。

```bash
# リポジトリのルートから実行。全地域、または必要な地域だけを展開します。
python asia-registry/package.py unpack
python asia-registry/package.py unpack --country JP

# 全地域を展開した状態で、ID・所属・原典列からの再生成・全件ハッシュを検証します。
python asia-registry/build.py verify

# 原典を再取得して再構築。キャッシュがある場合はそのスナップショットを再利用します。
python asia-registry/build.py build --inputs /path/to/source-cache
python asia-registry/build.py verify
python asia-registry/package.py pack
```

`countries/JP/entities.csv.gz` 等を UTF-8 CSV として読みます。`admin1.csv` は同じレコードの表示用抜粋なので、
総件数に加算しません。再取得した原典は更新されるため、同じ件数の再現には記録済みハッシュの原典が必要です。

## ID と所属

- 地域 ID は `gn:<geonameid>`、国参照は `country:<CC>` です。GeoNames の名前空間であり、法的自治体 ID とは区別します。
- `parent_id` は原典の完全な行政コード階層で一意に対応できる場合だけ付与します。名前や近接座標で確定しません。
- 中間階層が欠ける場合、直接親は空欄にします。別に判明する第1行政区分は `state_id` へ保持します。
- `country_scope_only` は国への所属だけが判明した状態で、国が直近の行政親であるという意味ではありません。
- 履歴・廃止地名へ現在の行政親を断定しません。候補・未確定理由は JSON 列に残します。
- 原典の行政コードは文字列です。ISO 3166-2 と同じだとは仮定せず、先頭ゼロを保持します。

## 名前・郵便番号・住所表示

`name`、`asciiname`、`alternatenames` と原典の19列を保持します。
`asciiname` は英語名の保証ではなく、`alternatenames` は言語タグを持ちません。
したがって、このデータだけで「現地語・国内英語・国際英語」の公式対訳が揃ったとは扱いません。
郵便番号は原典の別資料であり、この Gazetteer への公式 ID 対応付けは未収録です。

拡充方針は [公式名称・郵便番号の追加設計](../docs/enrichment-plan-ja.md) を参照してください。
住所の表示処理は [world-address の presentation.py](https://github.com/rei-k/world-address/blob/8e30ef141e40769fa932adeb2f901505023bfd1e/address-foundation/addresskit/presentation.py) に分離しています。同じ地域 ID から必要な名前を選び、国・言語・用途別の
テンプレートで住所要素を並べます。名前辞書、公式自治体 ID 対応表、住所テンプレート、郵便番号関連は追加収録対象です。

座標は地点の代表値です。行政境界、配達区域、各住所の位置や配達可能性を表しません。
`address_candidate=1` にも集落の一部や集落群を含み、公的な市町村であることを意味しません。

## 検証と出典

`verification.json` は保存済みプロファイルに対する内部整合性検証の結果です。
`publication.json` が `complete`、`published_profiles` が52なら対象全件の保存が完了しています。
ハッシュ、ID の全体一意性、行政コードによる参照、階層の非循環性、原典19列からの派生列再生成、ADM1 抜粋の一致を確認しました。
原典の正確性、現在の行政制度との一致、公式名称、法的自治体の網羅性を独立検証したものではありません。

データ: GeoNames, CC BY 4.0。派生加工内容と帰属表示は [NOTICE.md](NOTICE.md)、列定義は [SCHEMA.md](SCHEMA.md) を参照してください。
コードは [LICENSE](LICENSE) に従います。データにはコードの MIT ライセンスを適用しません。

## 移行元と更新

このフォルダは `rei-k/world-address` のコミット
`8e30ef141e40769fa932adeb2f901505023bfd1e` にある `address-foundation/asia-registry/` を元にしています。
分割データ59ファイル、索引、検証結果、構築・展開コードは同じバイト列を保持します。
READMEの配置案内を更新し、ライセンスと移行記録を追加しています。
元リポジトリ専用の `publish.py` と `publish-request.json` は移行対象に含めません。

移行後の照合結果は [migration.json](migration.json) に記録します。
保存済みの地域IDは言語変更で付け替えません。公式コードとの対応は別表で追加します。
欧州台帳との重複対象（AM・AZ・CY・GE・RU・TR）は同じ `gn:` IDを使います。
両台帳の件数を単純に合計せず、取り込み時にIDで重複排除し、版の差異は出典・取得日時とともに管理してください。

更新時は作業ブランチで再構築・検証し、出典、件数、ハッシュ、未解決事項の差分を確認してから取り込みます。
基礎データの内部検証合格は、公式対訳・郵便番号対応の全面整備完了を意味しません。
