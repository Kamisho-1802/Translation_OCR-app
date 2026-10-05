# OCR翻訳アプリ

画像からOCRで文字を抽出し、抽出テキストを日英・英日で翻訳するWebアプリ。
テスト段階ではOCRエンジン（Tesseract / easyOCR）と翻訳API（Azure / DeepL）を
UIトグルで切り替えて精度・使用感を比較できる。

- 設計: [DESIGN.md](DESIGN.md)
- 実装手順: [IMPLEMENTATION_STEPS.md](IMPLEMENTATION_STEPS.md)

## 構成

```
translation-app/
├── backend/    # FastAPI (Python 3.11)
└── frontend/   # React + TypeScript + Vite
```

## セットアップ

### バックエンド

本環境では OCR 依存（easyOCR / torch+CUDA / Tesseract 本体）を既存の conda 環境
`ocrbench` から引き継ぐため、venv を `--system-site-packages` 付きで作成している。

初回のみ（PowerShell。Windows PowerShell 5.1 では `&&` は使えないので `;` で区切る）:

```powershell
cd C:/Users/USER/Desktop/translation-app/translation-app/backend
# 既存の conda env(ocrbench) の Python から venv を作成（OCR系パッケージを再利用）
C:/Users/USER/anaconda3/envs/ocrbench/python.exe -m venv --system-site-packages .venv
./.venv/Scripts/python.exe -m pip install fastapi python-dotenv
Copy-Item .env.example .env    # 認証情報を記入
```

起動:

```powershell
cd C:/Users/USER/Desktop/translation-app/translation-app/backend; ./.venv/Scripts/python.exe -m uvicorn main:app --reload --port 8000
```

クリーンな環境で一から入れる場合は `pip install -r requirements.txt` と
Tesseract 本体のインストール（`TESSERACT_CMD` にパスを設定）が必要。

### フロントエンド

```powershell
cd C:/Users/USER/Desktop/translation-app/translation-app/frontend; npm install
cd C:/Users/USER/Desktop/translation-app/translation-app/frontend; npm run dev     # http://localhost:5173
cd C:/Users/USER/Desktop/translation-app/translation-app/frontend; npm run build   # tsc の型チェック込み
cd C:/Users/USER/Desktop/translation-app/translation-app/frontend; npm run lint    # oxlint（any は error）
```

> バックエンドとフロントエンドは別々のターミナルタブで起動したままにする。

API接続先は `frontend/.env` の `VITE_API_BASE`（既定 `http://localhost:8000`）で切替。

## 検証手順（テスト段階）

`.env` の `ENABLE_ENGINE_TOGGLE=true`（既定）でトグルを表示し、条件を変えて実行 →
翻訳履歴で見比べる、という流れで比較検証する。

1. **OCRエンジンの比較**: 文字検出ページで画像を1回OCRすると、Tesseract / easyOCR /
   manga-ocr の抽出結果が並んで出る（manga-ocr は日本語専用なので英語画像では出ない）。
   その場で読み比べ、使う方を選んで（必要なら手直しして）翻訳する。
   選んだエンジン名は履歴のバッジ（`tesseract` / `easyocr` / `mangaocr`）に残る。

   使い分けの目安:
   - **文書・スクリーンショット**: Tesseract / easyOCR
   - **看板・標識の写真、特に縦書き**: manga-ocr（他2つはほぼ読めない）
2. **翻訳APIの比較**: 同じテキストを DeepL / Azure で1回ずつ翻訳 → 履歴のバッジ
   （`deepl` / `azure`）で訳文を見比べる。
3. **ブロックモード**: 分割（split）は手直し・スクロールの手間が大きいため一時撤去中。
   常に一括（single）で動く。バックエンドと履歴表示は分割のまま残してあるので、
   戻すときは `frontend/src/pages/Detection.tsx` の `BLOCK_MODE` をトグルに戻せばよい。
4. 検証データが溜まったら、履歴ページの「全削除」でリセットできる。

### 本番相当の動作確認

`.env` の `ENABLE_ENGINE_TOGGLE=false` にして再起動すると、
OCRは既定エンジン1つだけを実行し（選択肢を出さない）、翻訳APIトグルは「既定値（固定）」表示に変わり、
バックエンドもリクエスト値を無視して `DEFAULT_*` を使う（クライアント値を信用しない）。

### APIキー無しで動かす（モック）

`.env` の `USE_MOCK_TRANSLATOR=true` で翻訳APIを、`USE_MOCK_OCR=true` でOCRを
ダミー実装に差し替えられる（フロー全体の確認用）。

### OCRがうまく取れないとき

`backend/tools/ocr_probe.py` で、1枚の画像に対して Tesseract（PSM 4種 × 前処理3種）と
easyOCR（設定4種）を総当たりし、それぞれ何文字取れたかを一覧できる。

```powershell
cd C:/Users/USER/Desktop/translation-app/translation-app/backend; ./.venv/Scripts/python.exe tools/ocr_probe.py "C:/path/to/photo.jpg" ja
```

写真でつまずく典型は次の2つ。どちらもアプリ本体では対策済み。

- **カラー写真のまま Tesseract に渡すと0文字**: 内部の白黒二値化が背景の草木や影に
  引きずられる。→ グレースケール+コントラスト強調した版も試し、良い方を採用している。
- **スマホ写真のEXIF向き**: 横向きに保存され、向き情報で立てて表示されている写真は、
  そのまま読むと文字が倒れた状態になる。→ 読み込み時に必ずEXIFの向きを適用している。
- **縦書き・デザイン書体の看板**: Tesseract / easyOCR はどちらも歯が立たない
  （easyOCR は縦書き非対応で、縦の列を横一行として読もうとする）。→ manga-ocr を追加。
  CRAFT（easyOCRの検出器）で文字領域を切り出し、その領域だけを manga-ocr に渡している。
  manga-ocr は検出器を持たず、画像全体を渡すと文章を捏造するため、切り出しが必須。

### 抽出テキストの改行

OCRエンジンは文字のかたまりごとに結果を返すため、そのまま並べると横に並んでいる文字まで
改行で分かれて読みにくくなる。そこで**外接矩形の縦位置が重なるものを同じ行とみなし、
行が変わるところにだけ改行を入れる**（`services/ocr/base.py` の `group_into_lines`）。

```
営業中     10:00-18:00        →   営業中 10:00-18:00
定休日     水曜日                  定休日 水曜日
```

- 同じ行の中では、離れているところにだけ空白を入れる（隣接していれば直結）。
- 日本語の縦書きの列が横に並ぶ場合は、右の列から読む。
- 3エンジンとも同じ規則で揃えてある。

### manga-ocr について

- 初回実行時に約450MBのモデルを取得し、`~/.cache/huggingface` に置く。2回目以降は数秒で起動。
- `transformers` は 4 系に固定している。モデルが `.bin` 形式のみで配布されており、
  transformers 5系 + torch 2.5 の組み合わせでは読み込みが拒否されるため。
- 日本語専用。英語画像のときはサーバー側で実行対象から外している。

### 異常系の確認

| 操作 | 期待 |
|---|---|
| 10MB超の画像 | 413／「画像が大きすぎます…」 |
| GIF等の非対応形式 | 415／「対応していない形式です…」（フロントは送信前に弾く） |
| 文字の無い画像 | 両エンジンとも空配列・「文字が検出されませんでした」・翻訳ボタン無効 |
| 空文字だけで翻訳 | 400・履歴に保存されない |
| 不正なAPIキー | 502・履歴に保存されない |
