# アフリカ基礎地名データ：移行済み56か国・地域

GeoNamesの2026-09-26取得済みスナップショットを、既存データからバイト同一で移行した部分版です。新規収集はしていません。

- 収録：56か国・地域、388,038件
- 元データ：60か国・地域、584,138件
- 未移行：コンゴ民主共和国（CD）、モロッコ（MA）、マダガスカル（MG）、ナイジェリア（NG）
- 未移行理由：既存の圧縮ファイルが現在の接続経由で取得できるサイズを超えるため。元リポジトリには残っています
- 本フォルダのscope.json、coverage.csv、manifest.json、verification.jsonは56か国版に対応
- upstream/は元60か国版の説明・範囲・集計・検証結果。今回の収録完了を意味しません

## 利用

Python 3.11以上、標準ライブラリのみ。

    cd registries/africa
    python query.py --country KE --level 1
    python build.py verify
    python -m unittest discover -s . -p 'test_africa.py' -v

各国のcountries/CC/entities.csv.gzに全行、metadata.jsonに原典URL・SHA-256・件数・既知の課題、admin1.csvに重複投影を保持します。admin1行を全行数に加算しません。

GeoNamesのA/P分類の基礎台帳です。全自治体の公的確認、現在の法的行政階層、郵便配達可否を保証しません。未解決の所属はそのまま保存します。ブルキナファソ・ブルンジの行政改編差異はsource_freshness.jsonを参照してください。名称・ASCII表記・言語不明の別名を英訳とみなしません。Address1、境界ポリゴン、郵便番号割当は含みません。

地名データはCC BY 4.0（NOTICE.md）、コードはMIT（LICENSE）。元データの詳しい定義はupstream/README.md、列定義はschema.json、今回の照合結果はmigration.jsonを参照してください。

## 重点8か国の作業入口

第1陣（南アフリカ ZA、ナイジェリア NG、ケニア KE、ガーナ GH）→ 第2陣（ルワンダ RW、エジプト EG、モロッコ MA、アルジェリア DZ）の順序・現状・公式出典・受入条件・検証コマンドは [PRIORITY.md](PRIORITY.md) を参照してください。

`python registries/africa/priority_audit.py --wave 1 --check` で保存済み原典の整合性と未移行国を監査できます。これは公式の行政階層の照合完了を証明するものではありません。

## アフリカ8か国の公式・統計データ拡充（2026年11月）

南アフリカ・ナイジェリア・ケニア・ガーナ、およびルワンダ・エジプト・モロッコ・アルジェリアの別出典レイヤーは [アフリカ拡充監査](EXPANSION-2026-11.md) を参照してください。追加の地名・行政区画は保存された原典台帳のレコード数に加算せず、取得年・原典ID・ライセンスを分離します。ナイジェリアの旧GeoNames原本65,444件は依然として未移行であり、保存済みGeoNames基礎台帳の56か国・地域／388,038件を完成扱いに変更しません。

追加レイヤーの検査：`python registries/africa/verify_expansion.py --check`。
