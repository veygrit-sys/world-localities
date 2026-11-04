# 東アジア・東南アジア追加パッケージの検証・復元

## このコミットの範囲

このディレクトリには、2026-10-15版の追加パッケージを安全に検証・復元するための
SHA-256固定台帳と検証記録を収録しています。実装は `scripts/address_release.py`、
回帰テストは `tests/test_address_release.py` です。Python 3.11以降の標準ライブラリのみで動作します。

**住所・街路・番地データ本体、Code ZIP内の検索実装、国別取得アダプターは、このコミットではGitに追加していません。**
原本は別途配布済みの `Veygrit_EastAsia_20261015_Code.zip` と
`Veygrit_SoutheastAsia_20261015_Code.zip`、対応するData ZIPにあります。
この台帳の登録を、全データのGitHub公開、全住所の網羅、配達可能性の確認として扱わないでください。

Code ZIPは実ファイルを取得し、ZIP全体とマニフェスト内のoverlay全659項目を照合しました。
内訳は東アジア312項目、東南アジア347項目です。同じパスの更新を含むため、
659はユニークな最終ファイル数や住所件数ではありません。
Data ZIPの期待ハッシュは原本マニフェストから転記しましたが、今回の統合では再計算していません。
詳細は [20261015.json](20261015.json) と [verification-20261015.json](verification-20261015.json) を参照してください。

## コード・メタデータだけを検証

リポジトリのルートで実行します。ZIPのファイル名を変更しないでください。

```bash
python scripts/address_release.py verify --code /path/to/Veygrit_EastAsia_20261015_Code.zip
python scripts/address_release.py verify --code /path/to/Veygrit_SoutheastAsia_20261015_Code.zip
```

`VERIFIED_CODE_ONLY` はCode ZIP内の対象項目だけの検証成功を表します。
`unverified_data_payloads` が0でなければ、データ本体は未検証です。
このコマンドは復元先を書き換えません。ネットワーク取得やGitHub操作もしません。

## 全パッケージの検証と復元

東アジアのData ZIPは全5個、東南アジアは全4個を任意のpartsフォルダに置きます。
Code ZIP・Data ZIPを事前に手動展開する必要はありません。

```bash
python scripts/address_release.py verify --code /path/to/Veygrit_EastAsia_20261015_Code.zip --parts /path/to/parts
python scripts/address_release.py apply --code /path/to/Veygrit_EastAsia_20261015_Code.zip --parts /path/to/parts --target /path/to/world-localities
python scripts/address_release.py apply --code /path/to/Veygrit_SoutheastAsia_20261015_Code.zip --parts /path/to/parts --target /path/to/world-localities
```

適用順序は、従来のStreet Number版がある場合はそれを先に復元し、その後に**東アジア → 東南アジア**です。
空のディレクトリへの追加分のみの復元も可能ですが、従来の豪州・NZ・日本住居データ等まで
揃うという意味ではありません。検索に必要な外部ライブラリは、復元後のrequirementsを別途確認してください。

## 安全性と限界

SHA-256固定、ZIP・断片・復元ファイルのサイズとハッシュ照合、相対パス・重複・シンボリックリンクの拒否を行います。
許可する復元先は `address-points/`、`tests/`、既存パッケージに含まれる
`official-registry/JP/entities.csv.gz` に限定しています。

既存ファイルは、同一内容なら変更せず、原本マニフェストに記録された直前版と一致する場合だけ更新します。
未確認の編集がある場合は停止します。すべてのペイロードを一時領域へ検証してから各ファイルを反映します。
同じ復元先でのインポーター同士の同時実行はロックで拒否します。実行中は他の編集・同期処理も止めてください。

反映は**ファイル単位で原子的**であり、リリース全体のトランザクションではありません。
反映中のI/Oエラー等で部分適用になった場合は、原因を確認して同じパッケージを再実行できます。
全ペイロード分の一時ディスク容量が必要です。異なるファイルシステムをまたぐ復元先や、
ハードリンク非対応の保存先はこの実装の対象外です。

このハッシュ照合は、固定した配布物との一致確認です。データの正しさや再配布許諾を新たに保証しません。
原本内の出典・取得日・ライセンス・品質制約を維持し、再配布条件が不明な資料を追加しないでください。

## 回帰テスト

```bash
python -m unittest discover -s tests -p 'test_address_release.py' -v
```

オフラインの合成フィクスチャを使用し、実住所データ、外部サービス、認証情報を必要としません。
住所検索・国別取り込みの実データ検証とは別のテストです。
