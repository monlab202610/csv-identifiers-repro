# 商品コードを保持するCSV取り込み前チェック

日本語の商品マスターCSVで、先頭ゼロや文字列`NA`を保持する読込設定と、単一CSVの構造/ID検査を再現する小さな資料です。Codexが作成した架空データとコードを2026-10-04に実行検証しました。実際の業務体験や実際の仕入先データではありません。

`check_csv.py`は**Python 3.9以上・標準ライブラリのみ**。入力を外部送信/修復/上書きせず、利用時のモデル呼び出し・テレメトリもありません。pandasの設定比較は別スクリプトです。

## まず試す

展開したこのフォルダで実行します。

```bash
python3 generate_fixtures.py
python3 check_csv.py fixtures/numeric_cp932.csv --encoding cp932
python3 -m unittest discover -s tests -v
```

最初の検査はデータ2レコード、エラー0、警告2、終了0になります。警告は先頭ゼロを落とさないための注意で、取り込みを禁止するエラーではありません。

失敗例も試せます。

```bash
python3 check_csv.py fixtures/short_row.csv --encoding cp932
# 終了1、E_COLUMN_COUNT
python3 check_csv.py fixtures/invalid_bytes.csv --encoding cp932
# 終了2、E_ENCODING、incomplete
```

## 自分の入力を検査する

```bash
python3 check_csv.py INPUT.csv --encoding cp932 --id-column 商品コード
python3 check_csv.py INPUT.csv --encoding utf-8-sig --id-column 商品コード
```

`INPUT.csv`を手元のファイルに置き換えます。CSVはアップロードしません。`--encoding`は必須、`--id-column`の既定は`商品コード`。UTF-8はBOMあり・なしのどちらも`utf-8-sig`で扱います。文字コードは推定しません。元データの文字コードを確認してください。

入力契約は、カンマ区切り・ダブルクォート・最初の論理レコードがヘッダです。空/重複ヘッダ、ID列不在、列数のずれ、空/空白だけのID、完全一致の重複IDを拒否します。ヘッダやIDをtrim/数値化/欠損化しません。IDは大小文字・全半角も異なる値として扱います。

`0`は先頭ゼロ警告なし、`0000`は警告。`NA`/`N/A`/`NULL`の完全一致は警告ですが、`na`等を網羅していません。pandasが解釈する全ての欠損文字列を発見する製品ではありません。商品名や他列の業務内容も検査しません。

## JSONと終了コード

`status`はok/error/incomplete、`scan_complete`は全レコードを読めたか、`rows_checked`は検査したデータの論理レコード数です。ヘッダ違反で停止した場合はerrorでscan_complete=false、パーサー/資源上限で中断した場合はincompleteになります。空/ヘッダのみでもエラーです。

`findings`には固定コード、severity、record_number、physical_line_end、column_indexだけを含めます。レコード/列番号は1から、ヘッダはレコード1、データは2からです。改行を含むセルでは物理行末とレコード番号は一致しません。値・列名・パス・例外全文をJSONに入れません。

| 終了 | 意味 |
| ---: | --- |
| 0 | 全レコードを検査し、エラー0。警告はあり得る |
| 1 | 入力/契約違反。引用符不正などはincompleteの場合もある |
| 2 | 引数/読取/文字コード/資源上限の失敗。成功として扱わない |

上限は10 MiB / データ50,000レコード / フィールド65,536文字 / 指摘表示100件。上限の設定オプションはありません。指摘表示を切っても読み切れた時の総数は正確に数えます。incompleteの件数は途中までです。`findings_truncated`で表示の省略を確認できます。

固定コード：E_ARGUMENTS、E_READ、E_FILE_TYPE、E_SIZE_LIMIT、E_ENCODING、E_EMPTY_FILE、E_EMPTY_HEADER、E_DUPLICATE_HEADER、E_ID_COLUMN_MISSING、E_COLUMN_COUNT、E_EMPTY_ID、E_DUPLICATE_ID、E_NO_DATA、E_CSV_SYNTAX、E_FIELD_LIMIT、E_ROW_LIMIT。警告：W_LEADING_ZERO、W_NA_LITERAL、W_ID_WHITESPACE。

## pandasの比較を再現する

Python 3.10以上で仮想環境を作ります。依存の取得時だけネット接続が必要です。

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-repro.txt
.venv/bin/python reproduce.py > results-local.json
```

WindowsのPythonパスは`.venv\Scripts\python.exe`です。Windowsは今回未検証。検証環境はPython3.12.14、pandas2.2.3、NumPy2.3.5、macOS arm64。pandasを固定しても依存やOSまで同一になる保証はないので、結果JSONの環境も確認します。

22の合成CSVのうち11入力について、既定/コードdtype指定/さらにkeep_default_na=False/標準csvの4方式を比較します。数値だけの列とNA/英数字混在列は別の入力です。値repr・is_missing・入力ハッシュを出すため、型名だけで保持を判断しません。[確認済み結果](article-results.json)はこの環境の実行結果で、最新版一般を保証しません。

単一ファイル検査を通しても下流の読込は別です。必要に応じて、取り込みでもコードのdtypeとNA設定を指定します。空欄を保持できても、非空IDという契約ではエラーです。

## 境界と限界

テストは25メソッド（fixtureごとのsubTestを含む）、Python3.9.6/3.12.14で成功。10 MiB/50,000レコード/65,536文字のちょうど/超過、表示100件超、構造違反、値とパスの出力抑制、FIFO拒否を確認しています。大きい境界入力はテスト時の一時フォルダで生成し、配布物には入れません。

文字コードを誤指定しても構造が読めてしまう例があります。デコード成功は正しい文字コードの保証ではありません。strict=Trueでも全不正CSVを検出できる保証はありません。破損済みの先頭ゼロ・精度、業務全般、Excel数式としての安全性は保証しません。CSV書出し、バッチ、ルール保存、ブラウザツールは含めていません。

`generate_fixtures.py`はこのフォルダの名前が決まった合成fixtureとmanifestを上書きします。自分の入力をfixtures内の同じファイル名に置かないでください。検査対象は`check_csv.py`への入力に指定します。自分の入力に`reproduce.py`を使う経路はありません。

## 任意の報告

本資料の紹介記事のQiitaコメントに「サンプル/自分の入力」「完了/失敗」「元のコードを保持できた/不明」「繰り返す作業で不足する機能」を報告できます。入力内容や検査JSONを公開する必要はありません。実ファイル・セル値・取引先名・パス等は貼らないでください。

追加機能の検討項目は[feedback.md](feedback.md)に分けています。実装済み機能や購入受付ではありません。

## 出典・ライセンス

- [pandas 2.2 read_csv](https://pandas.pydata.org/pandas-docs/version/2.2/reference/api/pandas.read_csv.html)
- [Python 3.12 csv](https://docs.python.org/3.12/library/csv.html)、[codec一覧](https://docs.python.org/3.12/library/codecs.html#standard-encodings)
- [csvkitの無料の推論制御](https://csvkit.readthedocs.io/en/latest/common_arguments.html)、[csvclean](https://csvkit.readthedocs.io/en/latest/scripts/csvclean.html)

自作コード、合成CSV、README、実行結果と図は[MIT](LICENSE)。pandas等はそれぞれの配布元のライセンスに従います。本資料に依存パッケージ本体は同梱していません。
