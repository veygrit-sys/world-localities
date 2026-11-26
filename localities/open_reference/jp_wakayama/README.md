# 和歌山市の住居表示・地番と県営住宅所在地

対象は和歌山市今福二丁目・三丁目、男野芝丁、八番丁の4町字。デジタル庁のABR試験公開データにある基礎番号651件と地番732件を、町字IDと原典の複合キーで照合する。番号は列挙されたものだけを採用する。全ての住居マスター収録行が基礎番号（basic_rsdt_div=0）、確認待ち（status_flg=0）である。基礎番号単独では街区までを確認し、住居番号は未照合にする。地番を lot として明示した入力は、同じ敷地に県営住宅がある場合も地番の照合に止める。

今福第一、今福第二、雄湊、城北の4団地は、県が公表する名称・所在地とABRの番号を突合した。同じ所在地を特定できたとき、最初の根拠は県の団地行、次の根拠はABRの区別付き番号である。県の資料で団地の敷地まで確認できる。戸別の住戸、入口、現住者、経緯度、配送可否を証明するデータは含まない。通常郵便番号を入力した場合は、固定した日本郵便の町域行（自治体・町名）を別途照合した結果を付ける。

## 出典と再現

- [デジタル庁 アドレス・ベース・レジストリ](https://www.digital.go.jp/policies/base_registry_address) の和歌山県住居表示‐住居マスターと和歌山市地番マスター（CC BY 4.0）を加工。市区町村コード302015で抽出し再圧縮したGeolonia公開キャッシュを使用した。元ZIPと抽出ZIPは別のファイルで、掲載ハッシュは後者のものである。版・原典URL・抽出ZIPのSHA-256は [sources.json](sources.json) に記載した。
- 出典：[和歌山県「令和8年度 県営住宅募集のご案内」](https://www.pref.wakayama.lg.jp/prefg/080800/kenei/annai_d/fil/R8goannai.pdf) 印刷版29頁をもとに町字・番地と団地名を抽出し加工した。[和歌山県ホームページ公開情報利用規約](https://www.pref.wakayama.lg.jp/prefg/000200/opendata/hpopendatakiyaku.html)
- 日本郵便株式会社「郵便番号データ」2026年10月30日版の通常町域行を使用。特殊な事業所郵便番号への割当てを確認するものではない。[日本郵便のデータ説明](https://www.post.japanpost.jp/service/search/zipcode/download/utf-readme.html)

再生成は sources.json の cache が示す固定コミットの files ディレクトリを用いる。Python 標準ライブラリのみで再現できる。

```sh
python localities/open_reference/jp_wakayama/project.py /path/to/processes_10_refresh_csv_ranges/files /tmp/numbers.csv.gz
python -m unittest discover -s tests -p 'test_jp_wakayama.py'
```
