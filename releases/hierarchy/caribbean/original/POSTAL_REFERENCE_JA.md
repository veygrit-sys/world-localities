# 郵便番号・Address2の扱い

この版は郵便番号の原典・割当表を取得していません。28対象すべての `postcode_pattern` はnullです。GeoNamesのcountryInfoにある正規表現を、そのまま最新の郵便規則に採用していません。

`postcode` は入力を保持します。空欄は `missing`、文字列でない入力は `invalid_input_type`、その他は `review_required` です。これは番号の不存在・不正という断定ではありません。先頭ゼロは維持します。`display_candidate` は外側の空白・大文字小文字を整える候補で、原入力は `raw` に残ります。

```bash
python3 address-points/adapters/caribbean.py postcode --country PR --value 00901
python3 address-points/adapters/caribbean.py postal-records --country PR --value 00901
```

`postal-records` の空結果は割当データ未収録を意味します。`assignment_verified` と `delivery_verified` はfalseです。

Address2というフィールド名は国によって役割が違います。国・地域、州・県など、市町村、集落、街路、番地、建物・部屋を別の構成要素として管理してください。本版は出典で裏付けられた行政・集落の関係を提供します。街路・番地・建物・部屋の不足を推測で補完しません。
