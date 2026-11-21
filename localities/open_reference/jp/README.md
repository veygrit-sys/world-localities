# 日本の公的地名の読みとローマ字

出典は国土地理院・海上保安庁海洋情報部の[地名集日本（2021年更新）英語版](https://www.gsi.go.jp/ENGLISH/pape_e300284.html)。国土地理院の[コンテンツ利用規約](https://www.gsi.go.jp/kikakuchousei/kikakuchousei40182.html)が示す公共データ利用規約（第1.0版）を参照。国土地理院・海上保安庁海洋情報部「地名集日本（2021年更新）」をもとに、行政・居住地名を抽出して作成した。原本PDFと訂正表は登録・APIキー不要で取得できる。

原典の基準は2021年3月。英語版の分類 `Municipality` の1,794行と `Populated area` の182行をすべて収録した。原典の地名番号・PDFページ・地域メッシュ、漢字・かな・掲載ローマ字で各行を識別できる。2026年3月24日の訂正表の5件は湖・海域・島に関するもので、選択した分類に該当するものはない。6行はPDFから漢字欄を文字として抽出できず空欄とし、かな・ローマ字を収録した。全国の現行自治体を確定する用途には時点付きの行政台帳を参照する。

初回検索時にCSVを原典台帳のSHA-256と照合し、異なる版は読み込まない。返却行の `attribution` と `terms_url` に出典表示と利用条件を格納する。名称・かな・掲載ローマ字を完全一致で検索する。海外向けの固有地名表記に使用できる。検索 `府中市` と `Fuchu Shi` はどちらも異なるメッシュの2件を返す。原典の地域メッシュは行政コードや郵便番号とは別であり、住所の番地・建物・配達可否は確認していない。

## 保存内容の再検証

原本と訂正表のSHA-256、正式名称、取得日は [source.json](source.json) に記録した。標準ライブラリとPopplerの `pdftotext`（検証時25.03.0）を使う。リポジトリのルートで以下を実行すると2原本を照合し、表を再抽出し、収録CSVとのバイト単位の一致を検査する。通常の地名検索にはPDFやPopplerは不要。

```sh
curl -fL https://www.gsi.go.jp/common/000238295.pdf -o /tmp/gsi-gazetteer-2021-en.pdf
curl -fL https://www.gsi.go.jp/common/000240221.pdf -o /tmp/gsi-gazetteer-errata.pdf
python -m localities.open_reference.jp.replay_gazetteer /tmp/gsi-gazetteer-2021-en.pdf /tmp/gsi-gazetteer-errata.pdf
```
