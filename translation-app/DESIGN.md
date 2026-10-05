# OCR翻訳アプリ 設計書

OCRで画像から文字を抽出し、抽出したテキストを翻訳するWebアプリケーション。
テスト段階では、OCRエンジン（Tesseract / easyOCR）と翻訳API（Azure / DeepL）を
UIトグルで切り替えて精度・使用感を比較検証できるようにする。本番環境ではトグルを
非表示にし、既定のエンジン・APIに固定する。

---

## 1. 目的とスコープ

- 画像をOCRで読み取り、文字を抽出し、抽出テキストを日英・英日で翻訳する。
- テスト段階の主目的は、OCRエンジン2種と翻訳API2種の**精度・使用感の比較検証**。
- 比較のため、履歴に「どのエンジン・どのAPI・どのブロックモードで実行したか」を保存する。
- 本番ではエンジン/API選択UIを固定（環境変数で制御）。

### スコープ外（今回作らないもの）
- 日本語・英語以外の言語対応
- お気に入り機能／履歴件数制限
- OCR結果と翻訳結果のサイドバイサイド同時比較UI（履歴に条件を残すことで代替）
- 元画像そのものの保存（保存するのは抽出テキスト・翻訳結果・メタ情報のみ）

---

## 2. 技術スタック

| 層 | 採用技術 | 備考 |
|---|---|---|
| バックエンド | Python 3.11+ / FastAPI | OCRライブラリがPython前提のため |
| ASGIサーバー | Uvicorn | |
| DB | SQLite | ローカル検証用。将来PostgreSQLへ移行可能な書き方にする |
| OCR | Tesseract（pytesseract）/ easyOCR | トグルで切替 |
| 翻訳 | Azure Translator / DeepL API | トグルで切替 |
| フロントエンド | **TypeScript + React + Vite** | 厳格な型設定でハルシネーション・実装ミスを抑止 |

> **フロントエンド選定の理由**: 「ハルシネーションを減らし確実に動かす」ことを重視。
> TypeScript+Reactは生成精度が最も高く、かつ厳格な型設定で実行前にミスを弾ける。
> 型を最優先する案（PureScript / Haskell）は生成精度が低くデバッグ困難なため不採用。

### TypeScript 厳格設定（必須）
`frontend/tsconfig.json` に以下を設定すること。

```jsonc
{
  "compilerOptions": {
    "strict": true,                    // 主要な厳格チェックを一括ON
    "noUncheckedIndexedAccess": true,  // 配列アクセスにundefined可能性を付与（本設計で特に重要）
    "noImplicitReturns": true,
    "noFallthroughCasesInSwitch": true,
    "forceConsistentCasingInFileNames": true
  }
}
```

- **`noUncheckedIndexedAccess` が本設計の要**: 履歴は「常にJSON配列・同順同数ペア」で
  扱うため `blocks[i]` のアクセスが頻出する。この設定で `blocks[i]` が `string | undefined`
  となり、空配列・ペアのズレを型レベルで検出できる。
- **`any` は全面禁止**: ESLint `@typescript-eslint/no-explicit-any` を **error** に設定する
  （warningではなくerror）。暗黙のanyも `strict` で禁止される。
- ランタイム検証ライブラリ（zod等）は導入しない。型はコンパイル時チェックに留める。

### GPUに関する注意
- easyOCR は PyTorch 依存。ローカルではGPUを使用して検証する。
- 将来はクラウドサーバーを借り、**OCR実行時のみGPUを起動**する構成を想定。
  そのため、OCR処理層は「エンジンを起動→推論→解放」できるよう疎結合にしておく（第7章）。

### 画像入力の制約
- **上限サイズ: 10MB**。超過した画像は受け付けない。
- **対応形式: PNG / JPEG のみ**。それ以外（WebP / PDF / HEIC 等）は受け付けない。
- **超過・非対応時の挙動**: バックエンドが **HTTP 413（サイズ超過）** または
  **HTTP 415（非対応形式）** を返し、フロントは
  「10MBまでのPNG/JPEG画像にしてください」といったメッセージを表示する。
- **自動リサイズはしない**（弾く方式）。縮小するとOCR精度が変わり、
  Tesseract / easyOCR の公平な比較検証ができなくなるため。バリデーションは
  フロント（送信前）とバックエンド（受信時）の**両方**で行い、バックエンド側を最終防衛線とする。

---

## 3. プロジェクト構成

```
ocr-translate-app/
├── backend/
│   ├── main.py                  # FastAPIエントリポイント
│   ├── config.py                # 環境変数の読み込み・設定
│   ├── database.py              # SQLite接続・初期化
│   ├── models.py                # スキーマ定義／Pydanticモデル
│   ├── routers/
│   │   ├── ocr.py               # POST /api/ocr
│   │   ├── translate.py         # POST /api/translate
│   │   └── history.py           # GET /api/history
│   ├── services/
│   │   ├── ocr/
│   │   │   ├── base.py          # OCREngine 抽象基底クラス
│   │   │   ├── tesseract.py     # Tesseract実装
│   │   │   └── easyocr_engine.py# easyOCR実装
│   │   └── translate/
│   │       ├── base.py          # Translator 抽象基底クラス
│   │       ├── azure.py         # Azure実装
│   │       └── deepl.py         # DeepL実装
│   ├── requirements.txt
│   └── .env.example
├── frontend/                    # React + Vite（推奨）
│   ├── src/
│   │   ├── pages/
│   │   │   ├── Home.jsx
│   │   │   ├── Detection.jsx
│   │   │   ├── History.jsx
│   │   │   └── Translate.jsx
│   │   ├── components/
│   │   │   ├── Layout.jsx       # 上部バー＋ドロワー共通レイアウト
│   │   │   └── EngineToggles.jsx
│   │   ├── api/client.js        # バックエンドAPI呼び出し
│   │   └── App.jsx              # ルーティング
│   └── package.json
└── README.md
```

---

## 4. データベース設計（SQLite）

履歴は**全件保存**（件数制限なし）。分割モードは**1画像=1レコード**（グループ化）で保存する。
一括・分割・翻訳ページ由来のすべてを1スキーマで扱うため、`source_text` /
`translated_text` は**常にJSON配列文字列**として保存する。

```sql
CREATE TABLE translation_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_text     TEXT    NOT NULL,   -- JSON配列。例: ["文1","文2"]。一括/翻訳ページは要素1個
    translated_text TEXT    NOT NULL,   -- JSON配列。source_textと同順・同数のペア
    source_lang     TEXT    NOT NULL,   -- 'ja' または 'en'
    target_lang     TEXT    NOT NULL,   -- 'en' または 'ja'
    translation_api TEXT    NOT NULL,   -- 'azure' または 'deepl'
    ocr_engine      TEXT,               -- 'tesseract' / 'easyocr'。翻訳ページ由来は NULL
    block_mode      TEXT,               -- 'single' / 'split'。翻訳ページ由来は NULL
    origin          TEXT    NOT NULL,   -- 'detection'（文字検出画面） / 'translate'（翻訳ページ）
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_history_created_at ON translation_history (created_at DESC);
```

### データ表現ルール（重要）
- **常に配列**: 一括モード・翻訳ページ由来も要素1個の配列で保存する
  （例: `["元の全文"]`）。フロント・バックともに分岐を減らすため。
- **順序ペア対応**: `source_text[i]` と `translated_text[i]` は必ず同じ順序・同じ個数で対応する。
  分割モードで元3ブロックなら訳も3ブロック、`i` 番目同士が対応する。
- SQLiteはJSONをTEXTとして保存。アプリ側で `json.dumps` / `json.loads` する。
  必要に応じ `json_extract()` も利用可能。

### 言語連動ルール
- OCRの画像モードが「日本語」→ 翻訳方向は自動で **ja → en**
- OCRの画像モードが「英語」→ 翻訳方向は自動で **en → ja**
- 翻訳ページは独立した方向トグル（ja⇄en）を持つ。

---

## 5. 環境変数（トグル制御）

`.env` で制御する。テスト環境と本番環境の差はここだけで吸収する。

```bash
# .env.example
# --- トグル制御 ---
ENABLE_ENGINE_TOGGLE=true          # true: 切替UI表示（テスト） / false: 非表示・固定（本番）
DEFAULT_TRANSLATION_API=deepl      # 本番固定時／初期値
DEFAULT_OCR_ENGINE=easyocr         # 本番固定時／初期値

# --- 翻訳API認証 ---
AZURE_TRANSLATOR_KEY=
AZURE_TRANSLATOR_REGION=
AZURE_TRANSLATOR_ENDPOINT=https://api.cognitive.microsofttranslator.com
DEEPL_API_KEY=
DEEPL_API_URL=https://api-free.deepl.com   # Pro版は https://api.deepl.com

# --- OCR ---
TESSERACT_CMD=/usr/bin/tesseract   # Tesseract実行ファイルパス（環境依存）

# --- 画像入力制約 ---
MAX_IMAGE_SIZE_MB=10               # 上限サイズ(MB)。超過は413
ALLOWED_IMAGE_TYPES=image/png,image/jpeg  # 対応MIME。以外は415

# --- DB ---
DATABASE_PATH=./data/history.db
```

### 挙動
- `ENABLE_ENGINE_TOGGLE=false` のとき:
  - フロントは各トグルを**非表示**にし、`DEFAULT_*` の値で固定表示。
  - バックエンドはリクエストで送られた `translation_api` / `ocr_engine` を**無視**し、
    サーバー側で `DEFAULT_*` を使う（改ざん防止のためサーバー側でも固定する）。
- `ENABLE_ENGINE_TOGGLE=true` のとき:
  - フロントはトグルを表示し、リクエストに選択値を含める。
  - バックエンドはリクエスト値を採用する。
- フロントは起動時に `GET /api/config` でこのフラグと既定値を取得する（第6章）。

---

## 6. API仕様

OCRと翻訳は**別エンドポイント**にする（間にユーザーのテキスト手直しが入るため）。
OCR単体では履歴に保存せず、翻訳実行時に保存する。

### 6.1 `GET /api/config`
フロント初期化用。トグル表示可否と既定値を返す。

レスポンス:
```json
{
  "enable_engine_toggle": true,
  "default_translation_api": "deepl",
  "default_ocr_engine": "easyocr"
}
```

### 6.2 `POST /api/ocr`
画像からテキストを抽出する。**保存はしない。**

リクエスト（multipart/form-data）:
| フィールド | 型 | 内容 |
|---|---|---|
| image | file | 画像ファイル |
| ocr_engine | string | 'tesseract' / 'easyocr'（本番固定時はサーバーが無視） |
| lang_mode | string | 'ja'（日本語画像） / 'en'（英語画像） |
| block_mode | string | 'single'（一括） / 'split'（分割） |

レスポンス:
```json
{
  "blocks": ["抽出テキスト1", "抽出テキスト2"],
  "ocr_engine": "easyocr",
  "lang_mode": "ja",
  "block_mode": "split"
}
```
- `single` の場合も `blocks` は要素1個の配列で返す（`["全文"]`）。
- `split` の場合はブロックごとに配列要素を分ける。
- 抽出後、フロント側で各要素を編集可能にする。
- **ゼロ件（文字が検出できない）時**: `blocks` を**空配列 `[]`** で返す（エラーにはしない）。
  フロントは「文字が検出されませんでした」と表示し、**「翻訳する」ボタンを無効化**する。
  空データは翻訳・保存させない（C・下記translate側でも防御）。

バリデーション（受信時・第2章の制約に従う）:
- サイズが10MB超 → **413** を返す。
- 形式がPNG/JPEG以外 → **415** を返す。
- いずれもボディにエラーメッセージを含め、フロントで表示できるようにする。

### 6.3 `POST /api/translate`
テキストを翻訳し、**履歴に保存**して結果を返す。

リクエスト（application/json）:
```json
{
  "blocks": ["編集後テキスト1", "編集後テキスト2"],
  "source_lang": "ja",
  "target_lang": "en",
  "translation_api": "deepl",
  "origin": "detection",
  "ocr_engine": "easyocr",
  "block_mode": "split"
}
```
| フィールド | 必須 | 内容 |
|---|---|---|
| blocks | ✓ | 翻訳対象。常に配列。一括・翻訳ページは要素1個 |
| source_lang | ✓ | 'ja' / 'en' |
| target_lang | ✓ | 'en' / 'ja' |
| translation_api | ✓ | 'azure' / 'deepl'（本番固定時はサーバーが無視） |
| origin | ✓ | 'detection' / 'translate' |
| ocr_engine | － | detection由来のみ。translate由来は null |
| block_mode | － | detection由来のみ。translate由来は null |

処理:
1. **空チェック**: `blocks` が空配列、または全要素が空文字/空白のみなら **400** を返し、
   保存しない（空データを履歴に入れない）。有効な要素だけを対象とする。
2. `blocks` の各要素を順番に翻訳（順序・個数を保つ）。
3. **翻訳失敗時（案a: 全体失敗）**: いずれか1ブロックでも翻訳APIがエラーを返したら、
   **全体を失敗**とし **502**（またはAPIエラーに応じた5xx）を返す。**履歴には一切保存しない**。
   部分的な成功結果も保存しない。これにより履歴には完全に成功した翻訳のみが残り、
   検証データが汚れない。フロントはエラーメッセージを表示し、再実行を促す。
4. 全ブロック成功時のみ、`source_text = json.dumps(blocks)`、
   `translated_text = json.dumps(訳配列)` で保存する。
5. 本番固定時は `translation_api` / `ocr_engine` をサーバー既定値で上書き。

レスポンス:
```json
{
  "id": 42,
  "source_blocks": ["編集後テキスト1", "編集後テキスト2"],
  "translated_blocks": ["translated1", "translated2"],
  "source_lang": "ja",
  "target_lang": "en",
  "translation_api": "deepl",
  "created_at": "2026-01-01 12:00:00"
}
```

### 6.4 `GET /api/history`
履歴取得。`limit` 省略で全件（新しい順）。

クエリ: `?limit=5`（ホーム用）／なし（履歴画面用・全件）

レスポンス:
```json
{
  "items": [
    {
      "id": 42,
      "source_blocks": ["文1", "文2"],
      "translated_blocks": ["t1", "t2"],
      "source_lang": "ja",
      "target_lang": "en",
      "translation_api": "deepl",
      "ocr_engine": "easyocr",
      "block_mode": "split",
      "origin": "detection",
      "created_at": "2026-01-01 12:00:00"
    }
  ]
}
```
- サーバー側で `source_text` / `translated_text` を `json.loads` し、
  `source_blocks` / `translated_blocks` として返す（フロントの負担軽減）。

### 6.5 `DELETE /api/history/{id}`
履歴を1件削除する（検証中の不要データ整理用）。

- パスパラメータ `id` のレコードを削除。
- 存在しない `id` は **404**。成功時は **204**（No Content）。

### 6.6 `DELETE /api/history`
履歴を全件削除する（検証データのリセット用）。

- 全レコードを削除。成功時は **204**。
- 誤操作防止のため、フロント側で確認ダイアログを必須とする（第8.4章）。

---

## 7. OCR・翻訳サービスの実装方針

### 7.1 抽象化（切替の要）
OCR・翻訳ともに**抽象基底クラス＋実装クラス**にし、文字列キーで実装を選べるようにする。

```python
# services/ocr/base.py
class OCREngine:
    def extract(self, image_bytes: bytes, lang_mode: str, block_mode: str) -> list[str]:
        """block_mode='single'なら要素1個、'split'ならブロックごとの配列を返す"""
        raise NotImplementedError

# services/translate/base.py
class Translator:
    def translate(self, blocks: list[str], source_lang: str, target_lang: str) -> list[str]:
        """入力と同順・同数の訳配列を返す"""
        raise NotImplementedError
```

ファクトリで選択:
```python
def get_ocr_engine(name: str) -> OCREngine: ...      # 'tesseract'/'easyocr'
def get_translator(name: str) -> Translator: ...     # 'azure'/'deepl'
```

### 7.2 ブロックモードの実装
- **single（一括）**: OCR結果の全テキストを結合し、要素1個の配列で返す。
- **split（分割）**: 各エンジンの**素の出力単位**をそのまま1ブロックとする（案1採用）。
  - Tesseract: ブロック/段落単位（`image_to_data` のブロック情報を利用）
  - easyOCR: 検出領域（行）単位（`readtext` の各検出を1要素とする）
  - **注意**: エンジンによって分割の粒度が異なる（Tesseractは段落寄り、easyOCRは行寄り）。
    これは各エンジンの素の挙動を比較検証するための意図的な仕様。将来、行単位に揃える／
    座標で疑似ブロック化する等の発展余地があるが、初期実装は素の出力で行う。
- 2モードは検証目的で結果を見比べるためのもの。実装は同一エンジン内でモード分岐する。
- **空要素の除去**: 空文字・空白のみのブロックは結果配列から除外する。

### 7.3 言語コード対応
- 内部表現は 'ja' / 'en' に統一。
- Tesseract: `jpn` / `eng`、easyOCR: `['ja']` / `['en']`、
  DeepL: `JA` / `EN`、Azure: `ja` / `en` に各サービス層でマッピングする。

### 7.4 GPU運用（将来）
- easyOCR実装はモデルのロード/推論を関数内に閉じ、呼び出し時のみGPUを使う形にする。
- 将来クラウドで「OCR時のみGPUインスタンス起動」を実現しやすいよう、OCR層は
  翻訳層・DB層と疎結合を保つ（OCRエンドポイントが独立している点がこれを担保）。

---

## 8. 画面仕様

### 8.1 共通レイアウト
- 全画面上部に固定バーを表示。左端に「三」（ハンバーガー）アイコン。
- 「三」クリックでドロワー（左からスライド）を開き、以下へ遷移:
  **ホーム / 文字検出 / 翻訳履歴 / 翻訳ページ**

### 8.2 ホーム（`/`）
- 最新の翻訳履歴を**5件**カード表示（`GET /api/history?limit=5`）。
- 各カード: 元テキスト冒頭・翻訳結果冒頭・翻訳API名・OCRエンジン・時刻。
- 分割モードで複数ブロックある場合は先頭ブロックを代表表示し「他N件」等で省略。

### 8.3 文字検出（`/detection`）
トグル3つを画面上部に配置（`ENABLE_ENGINE_TOGGLE=true` のときのみ表示）:
1. OCRエンジン: Tesseract ⇄ easyOCR
2. 画像モード: 日本語 ⇄ 英語（→ 翻訳方向を自動決定）
3. ブロックモード: 一括 ⇄ 分割

フロー:
1. 画像アップロード → 「OCR実行」ボタン → `POST /api/ocr`
2. 抽出テキストを**編集可能な状態**で表示
   - 一括: 1つのテキストエリア
   - 分割: ブロックごとに編集エリアを並べる
3. ユーザーが手直し
4. 「翻訳する」ボタン → `POST /api/translate`（`origin='detection'`、
   方向は画像モードから自動決定、ocr_engine / block_mode も付与）
5. **同ページ内**に翻訳結果を表示（分割なら元/訳をブロック単位でペア表示）
6. 履歴に自動保存される

### 8.4 翻訳履歴（`/history`）
- 全履歴を新しい順にリスト表示（`GET /api/history`）。
- 各行に翻訳API名・OCRエンジン・ブロックモードの**バッジ**を付け、比較しやすくする。
- 分割モードのレコードは元/訳をブロック単位のペアで表示。
- **1件削除**: 各行に削除ボタン → `DELETE /api/history/{id}`。削除後リストを更新。
- **全削除**: 画面上部に「全削除」ボタン → 確認ダイアログ → `DELETE /api/history`。
  検証中のテストデータをまとめてリセットするための機能。

### 8.5 翻訳ページ（`/translate`）
- 純粋な翻訳のみ。
- 方向トグル（ja ⇄ en）＋入力欄＋「翻訳」ボタン＋結果表示。
- 翻訳API切替トグルもここに配置（`ENABLE_ENGINE_TOGGLE=true` のときのみ）。
- 実行時 `POST /api/translate`（`origin='translate'`、`blocks=["入力全文"]`、
  `ocr_engine=null`、`block_mode=null`）。結果は履歴に保存する。

---

## 9. セットアップ手順

### バックエンド
```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windowsは .venv\Scripts\activate
pip install -r requirements.txt
# Tesseract本体を別途インストール（例: apt install tesseract-ocr tesseract-ocr-jpn）
cp .env.example .env                                 # 認証情報を記入
uvicorn main:app --reload --port 8000
```

想定 `requirements.txt`（バージョンは実装時に確定）:
```
fastapi
uvicorn[standard]
python-multipart      # 画像アップロード用
pytesseract
easyocr
torch                 # easyOCR依存（GPU版は環境に合わせる）
requests              # Azure/DeepL呼び出し
python-dotenv
Pillow
```

### フロントエンド（React + Vite の場合）
```bash
cd frontend
npm install
npm run dev
```
- API接続先はデフォルト `http://localhost:8000`。環境変数で切替可能にする。

---

## 10. 実装時の注意点（Claude Codeへの指示）

- `source_text` / `translated_text` は**必ずJSON配列**として保存・読み出しすること。
  一括モードや翻訳ページ由来でも要素1個の配列にする（プレーン文字列で保存しない）。
- `blocks` の**順序と個数を翻訳前後で必ず一致**させること。ペアがずれると履歴表示が壊れる。
- `ENABLE_ENGINE_TOGGLE=false` のときは、**フロントの非表示だけでなくバックエンドでも**
  既定エンジン/APIに固定すること（クライアント値を信用しない）。
- OCR層・翻訳層は抽象基底クラス経由で呼び出し、エンジン追加が容易な構造を保つこと。
- 画像そのものはDBに保存しない。抽出テキスト・翻訳結果・メタ情報のみ保存する。
- SQLiteのDBファイルは `DATABASE_PATH` の場所に、なければ起動時に自動生成すること。
- APIキー等の秘密情報はコードにハードコードせず、必ず `.env` から読むこと。

---

## 付録: 確定仕様サマリ

| 項目 | 決定内容 |
|---|---|
| 形態 | Webアプリ（フロント: TypeScript+React+Vite / バック: FastAPI） |
| 型方針 | strict:true＋noUncheckedIndexedAccess等 / any全面禁止(error) / zod等は不使用 |
| 画像制約 | 上限10MB / PNG・JPEGのみ / 超過413・非対応415で弾く / 自動リサイズなし |
| DB | SQLite（将来Postgres移行可能な書き方） |
| 翻訳 | 英⇔日双方向 / Azure・DeepLをトグル切替（本番固定） |
| OCR | Tesseract・easyOCRをトグル切替 / GPUはローカル→将来クラウドでOCR時のみ起動 |
| 言語連動 | 日本語画像→ja→en、英語画像→en→ja（自動） |
| 履歴 | 全件保存・件数制限なし・お気に入りなし |
| 履歴保存項目 | 元テキスト / 翻訳結果 / 言語 / 翻訳API / OCRエンジン / ブロックモード / origin / 時刻 |
| ブロックモード | 一括（single）/ 分割（split）の2パターン・トグル切替 |
| 分割の単位 | 各エンジンの素の出力（Tesseract=ブロック / easyOCR=行）。粒度差は意図的 |
| OCRゼロ件 | 空配列を返す・翻訳ボタン無効化・空データは保存しない |
| 翻訳失敗時 | 1ブロックでも失敗なら全体失敗(5xx)・履歴に保存しない |
| 履歴削除 | 1件削除＋全削除(要確認ダイアログ)を提供 |
| 分割履歴粒度 | B案: 1画像=1レコード（グループ化）、JSON配列で保持 |
| データ表現 | source/translated は常にJSON配列・同順同数ペア |
| 画面 | ホーム（最新5件）/ 文字検出 / 翻訳履歴（全件）/ 翻訳ページ |
| ナビ | 上部バー＋「三」ドロワー |
