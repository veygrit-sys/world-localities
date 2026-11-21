# La Posteの郵便番号と自治体

出典は La Poste – Service National de l’Adresse の「Base officielle des codes postaux」、2026年11月17日更新版です。登録・APIキーなしで11月21日に取得した原本CSVを、元バイトへ戻せるXZ形式で保存しています。フランス政府カタログは Licence Ouverte / Open Licence 2.0 を明示しています。二次配布時は提供元とデータ更新日を表示してください。[La Poste](https://data.laposte.fr/datasets/laposte-hexasmal)・[政府カタログ](https://www.data.gouv.fr/datasets/base-officielle-des-codes-postaux)・[利用条件](https://www.data.gouv.fr/pages/legal/licences/etalab-2-0)

原本39,192行のうち、13の国・地域コードで39,191行を検索できます。FRはフランス本土とコルシカの38,716行（6,051郵便番号、34,788の自治体・区のINSEEコード）です。ほかにグアドループ（GP）38行、マルティニーク（MQ）38行、フランス領ギアナ（GF）25行、レユニオン（RE）85行、サンピエール島・ミクロン島（PM）3行、マヨット（YT）23行、サン・バルテルミー（BL）1行、サン・マルタン（MF）1行、ウォリス・フツナ（WF）3行、仏領ポリネシア（PF）207行、ニューカレドニア（NC）50行、モナコ（MC）1行を収録しました。

国・地域の対応付けには、Inseeの2026年1月1日版Code officiel géographiqueを用いました。海外ではLa Posteの5文字のINSEEコードを、Inseeの自治体・海外区画とその親コードまたはモナコの国コードに照合します。郵便番号が共通の `971` で始まる場合も、`97139 LES ABYMES` はGP、`97133 ST BARTHELEMY` はBL、`97150 ST MARTIN` はMFの候補になります。`98901 ILE DE CLIPPERTON` の1行は、国・地域台帳にこの島の単独コードがないため原本に保存し、検索結果から除きました。[COG 2026](https://www.insee.fr/fr/information/8740222)・[Insee利用条件](https://www.insee.fr/fr/information/2008466)・[国連の地域名・国コード表](https://unstats.un.org/unsd/methodology/m49/overview/)

検索は郵便番号、自治体名、郵便上の宛先地名、補足地名、または明示したINSEEコードに対応します。文字列比較はNFC・大文字小文字・連続空白を正規化します。例として `75007` の原典行には自治体名 `PARIS 07` と郵便上の地名 `PARIS` の両方が載っています。`Ajaccio` は3行が該当し、`MEZZAVIA` はそのうち `20167` の行に載る補足地名です。数字のみの `13001` はマルセイユの郵便番号を、`insee:13001` はエクス＝アン＝プロヴァンスの自治体コードを検索します。全候補に原典の行番号（見出しが1行目）を返します。照合の根拠は郵便番号と地名の対応までです。番地や建物の実在、受託・配達の可否は未検証です。

住所検証用の `validate_place(country, postcode, locality)` は郵便番号欄をASCII数字5桁、地名欄を自治体名・宛先地名・補足地名として照合します。両方を満たす原典行が複数ある場合は `ambiguous` と全件数を返します。例えばPMの `97500 ST PIERRE ET MIQUELON` は3行で、表示上限を1にしても結果と件数は変わりません。対象外の国・番号未収録・番号と地名の不一致を区別します。

固定版を検証するコマンドです。オンライン再取得ではLa Poste原典とInseeの4原典を照合し、海外地域とモナコの対応表を再生成して収録した `territories.csv` との一致を確認します。新版は原典更新日・許諾・差分・検索範囲を確認したうえで取り込みます。固定原典のバイト数、SHA-256、帰属表示は [source.json](source.json) に記載しています。

```sh
python -m localities.open_reference.postal_eu.verify_laposte
python -m localities.open_reference.postal_eu.verify_laposte --refetch
```

La Poste – Service National de l’Adresse, Base officielle des codes postaux, mise à jour du 17 novembre 2026. Source : Insee, Code officiel géographique au 1er janvier 2026, publié le 24 février 2026.
