# 台北市の門牌をオフラインで照合する

台北市政府民政局が2026年11月2日に更新した「臺北市門牌位置數值資料」を使用します。台湾の国コードは `TW`、収録範囲は台北市の12行政区です。区名と通り・巷・弄・号を連結した表記で検索します。原典に階などの情報がある場合は、その文字まで含めた表記も照合できます。

```bash
python -m addressing reference --country TW --source taipei-doorplates --query '臺北市信義區市府路1號'
```

「臺北市」「台北市」の市名は省略できます。区名は必須です。全角と半角の数字は一致に使い、結果には原典の表記を返します。行が見つかれば、原典での区コード・里・門牌表記まで確認できています。郵便番号、転居、個別の配達可否は判定対象外です。

| 2026年11月2日版 | 件数 |
|---|---:|
| 市のCSV原典行 | 1,158,179 |
| 門牌番号が空欄のため除外 | 1 |
| 照合に使った原典行 | 1,158,178 |
| 同一区・同一里・同じ門牌文字列をまとめた検索レコード | 1,157,317 |

市の公開APIでは、指定した通りに該当しない行が返ったため、全件CSVを採用しました。検索レコードには座標を収録せず、同じ表記に対応する元の行数を `source_rows` で返します。区別の圧縮ファイルは初回検索時にSHA-256を検査します。

## 同じ版を再現する

```bash
curl -fL 'https://data.taipei/api/frontstage/tpeod/dataset/resource.download?rid=ce76ca0c-7f94-4935-ab47-1d2a41ca2abb' -o taipei.csv
python -m localities.open_reference.taipei.project_doorplates --csv taipei.csv --output ./taipei-replay
```

出力先には新しいディレクトリを指定します。再現時は元CSVのSHA-256、原典行数、12区の生成物を検査します。公開元が月次版を差し替えた場合は新しい版として審査し、原典年月日・ハッシュ・集計を更新する必要があります。

出典：臺北市政府民政局「臺北市門牌位置數值資料」。政府資料開放授權條款第1版。world-localities が門牌文字索引に加工。[市の配布ページ](https://data.taipei/dataset/detail?id=b7c8e724-1e98-45ee-a0bd-f3840623ed97)・[利用条件](https://data.taipei/rule)・[取得情報と区別の照合値](source.json)
