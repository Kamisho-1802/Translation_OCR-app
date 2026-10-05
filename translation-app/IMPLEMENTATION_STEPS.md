# OCR翻訳アプリ 実装手順書（Claude Code 向け）

この手順書は `DESIGN.md`（設計書）とセットで使う。設計の**判断はDESIGN.mdが正**であり、
本書は**作る順番・各フェーズの完了条件（ここまで動けば次へ進む）**を定めるもの。

## この手順書の使い方（Claude Codeへ）
- **必ずフェーズ順に実装する**。各フェーズ末尾の「✅ 完了条件」を満たしてから次へ進む。
- 完了条件は「実際に動かして確認する」こと。コードを書いただけで次へ進まない。
- 各フェーズは独立して動作確認できるよう、**モック→本実装**の順で組む。
- 不明点が出たら DESIGN.md の該当章を参照する。DESIGN.md に無い判断は**勝手に決めず、
  TODOコメントを残して報告**する。
- 秘密情報（APIキー）は必ず `.env` から読む。ハードコード禁止。

---

## フェーズ 0: プロジェクト初期化

### やること
1. リポジトリ直下に `backend/` と `frontend/` を作成（DESIGN.md 第3章の構成に従う）。
2. `backend/`: Python仮想環境、`requirements.txt`、`.env.example`、`.gitignore` を用意。
3. `frontend/`: Vite + React + TypeScript プロジェクトを生成
   （`npm create vite@latest frontend -- --template react-ts`）。
4. `frontend/tsconfig.json` に DESIGN.md 第2章の厳格設定を適用
   （`strict`, `noUncheckedIndexedAccess` ほか）。
5. ESLint に `@typescript-eslint/no-explicit-any: "error"` を設定。
6. ルート `README.md` にセットアップ手順（DESIGN.md 第9章）を記載。

### ✅ 完了条件
- `backend/` で `uvicorn main:app` が起動し、`GET /` 等のヘルスチェックが200を返す
  （この時点では最小の FastAPI アプリでよい）。
- `frontend/` で `npm run dev` が起動し、初期画面がブラウザ表示される。
- `frontend/` で `npm run build`（= `tsc` 型チェック込み）がエラーなく通る。
- `.gitignore` に `.env` / `.venv` / `node_modules` / `data/` が含まれている。

---

## フェーズ 1: DB層と履歴の土台

### やること
1. `backend/database.py`: SQLite接続と、起動時のテーブル自動生成
   （DESIGN.md 第4章のDDL。`DATABASE_PATH` が無ければ生成）。
2. `backend/models.py`: Pydanticモデル（リクエスト/レスポンス）と、履歴レコードの
   read/write ヘルパ（`json.dumps` / `json.loads` で `source_text`/`translated_text` を
   配列⇄TEXT変換）。
3. `backend/routers/history.py`:
   - `GET /api/history?limit=N`（省略時全件・新しい順）
   - `DELETE /api/history/{id}`（204 / 存在しなければ404）
   - `DELETE /api/history`（全削除・204）
4. 動作確認用に、ダミー履歴を1件挿入する一時スクリプトかエンドポイントを用意（後で削除可）。

### 実装上の必須ルール（DESIGN.md準拠）
- `source_text` / `translated_text` は**常にJSON配列**として保存・取得する。
  一括・翻訳ページ由来も要素1個の配列。
- `GET` レスポンスでは `json.loads` 済みの `source_blocks` / `translated_blocks` を返す。

### ✅ 完了条件
- アプリ起動時に `data/history.db` が自動生成され、テーブルが存在する。
- ダミー履歴を入れた状態で `GET /api/history` が配列で返り、`source_blocks` が
  ちゃんと配列型になっている。
- `GET /api/history?limit=1` が1件だけ返す。
- `DELETE /api/history/{id}` で1件消え、`DELETE /api/history` で全件消える。

---

## フェーズ 2: 翻訳サービス（モック→本実装）

> OCRより先に翻訳を作る。翻訳は入出力が単純でテストしやすく、履歴保存フローを
> 先に固められるため。

### やること
1. `backend/services/translate/base.py`: `Translator` 抽象基底クラス
   （`translate(blocks, source_lang, target_lang) -> list[str]`、入出力同順同数）。
2. **まずモック実装**（`MockTranslator`）: 各ブロックに `[EN] ` 等を付けて返すだけ。
   これでAPIキー無しでもフロー全体を検証できる。
3. `azure.py` / `deepl.py` の本実装（DESIGN.md 第7.3章の言語コードマッピングに従う）。
4. `get_translator(name)` ファクトリ。
5. `backend/routers/translate.py`: `POST /api/translate`。処理は DESIGN.md 第6.3章の通り:
   - **空チェック**（空配列/空白のみ → 400、保存しない）
   - 各ブロック翻訳（順序保持）
   - **1つでも失敗したら全体失敗（5xx）・履歴に保存しない**
   - 全成功時のみ履歴保存
   - 本番固定時（`ENABLE_ENGINE_TOGGLE=false`）は API名をサーバー既定値で上書き

### ✅ 完了条件
- `MockTranslator` で `POST /api/translate` を叩くと翻訳結果が返り、履歴に1件増える。
- 入力 `blocks` と出力 `translated_blocks` の**個数・順序が一致**している。
- 空配列や空白のみを送ると400が返り、履歴が増えない。
- （キー設定後）`translation_api=deepl` と `azure` の両方で実際に翻訳が返る。
- わざと不正なキーにすると5xxが返り、履歴が増えないことを確認。

---

## フェーズ 3: OCRサービス（モック→本実装）

### やること
1. `backend/services/ocr/base.py`: `OCREngine` 抽象基底クラス
   （`extract(image_bytes, lang_mode, block_mode) -> list[str]`）。
2. **まずモック実装**（`MockOCR`）: 画像に関係なく固定のダミーブロック配列を返す。
   single なら要素1個、split なら複数要素。
3. `tesseract.py`: pytesseract 実装。
   - single: 全文を結合して要素1個
   - split: ブロック/段落単位（`image_to_data` 利用）
4. `easyocr_engine.py`: easyOCR 実装。
   - single: 全検出を結合して要素1個
   - split: 検出（行）単位で1要素ずつ
5. **共通**: 空文字・空白のみのブロックは除外。1件も無ければ空配列を返す。
6. `get_ocr_engine(name)` ファクトリ。
7. `backend/routers/ocr.py`: `POST /api/ocr`（multipart）。
   - 画像バリデーション: 10MB超→413、PNG/JPEG以外→415（DESIGN.md 第2章・6.2章）
   - **この段階では履歴保存しない**（保存は translate 側）
   - ゼロ件は空配列 `[]` を返す（エラーにしない）

### ✅ 完了条件
- `MockOCR` で `POST /api/ocr` が single/split それぞれ正しい形の配列を返す。
- 11MBの画像で413、GIF等で415が返る。
- Tesseract で日本語画像・英語画像から実際にテキストが取れる
  （`lang_mode` に応じて `jpn`/`eng` が使われる）。
- easyOCR で（GPU環境で）実際にテキストが取れる。
- split モードで、Tesseract と easyOCR の**粒度差**が観察できる
  （意図通り。DESIGN.md 第7.2章）。
- 文字の無い画像で空配列が返る。

---

## フェーズ 4: 設定エンドポイントとトグル制御

### やること
1. `backend/config.py`: `.env` を読み込み（`python-dotenv`）。
   `ENABLE_ENGINE_TOGGLE` / `DEFAULT_TRANSLATION_API` / `DEFAULT_OCR_ENGINE` ほか。
2. `GET /api/config`: フロント初期化用（DESIGN.md 第6.1章）。
3. `translate.py` / `ocr.py` に**サーバー側の固定ロジック**を適用:
   `ENABLE_ENGINE_TOGGLE=false` のとき、リクエストの `translation_api`/`ocr_engine` を
   無視して `DEFAULT_*` を使う（クライアント値を信用しない）。

### ✅ 完了条件
- `GET /api/config` がフラグと既定値を返す。
- `ENABLE_ENGINE_TOGGLE=false` にすると、リクエストで別エンジンを指定しても
  サーバーが既定エンジンで処理する（履歴の `translation_api`/`ocr_engine` が既定値になる）。
- `true` に戻すとリクエスト値が反映される。

---

## フェーズ 5: フロント共通土台（レイアウト・ルーティング・API接続）

### やること
1. `frontend/src/api/client.ts`: バックエンド全エンドポイントの型付きラッパ。
   - レスポンス/リクエストの TypeScript 型を定義（`source_blocks: string[]` 等）。
   - 接続先はenv（例 `VITE_API_BASE=http://localhost:8000`）で切替。
2. `frontend/src/components/Layout.tsx`: 上部バー＋「三」ハンバーガー＋ドロワー。
   ドロワーから ホーム/文字検出/翻訳履歴/翻訳ページ へ遷移（DESIGN.md 第8.1章）。
3. React Router で4ルート（`/`, `/detection`, `/history`, `/translate`）を設定。
4. `EngineToggles.tsx`: OCR/翻訳API/ブロックモードのトグル。
   起動時 `GET /api/config` を呼び、`enable_engine_toggle=false` なら非表示・既定値固定。

### ✅ 完了条件
- 4画面が空でも表示され、「三」→ドロワーで相互に遷移できる。
- `npm run build`（tsc込み）がエラーなく通る（`any` 不使用・厳格設定下）。
- config取得で、トグルの表示/非表示が環境に応じて切り替わる。

---

## フェーズ 6: 各画面の実装

> 依存の少ない順（翻訳ページ → 文字検出 → 履歴 → ホーム）で作る。

### 6-A. 翻訳ページ（`/translate`）
- 方向トグル（ja⇄en）＋入力欄＋翻訳ボタン＋結果表示。
- 実行時 `POST /api/translate`（`origin='translate'`, `blocks=["入力全文"]`,
  `ocr_engine=null`, `block_mode=null`）。結果は履歴保存。
- **✅**: 翻訳が表示され、履歴に `origin=translate` で1件残る。

### 6-B. 文字検出（`/detection`）
- トグル3種（OCR/画像モード/ブロックモード）を上部に配置。
- フロー（DESIGN.md 第8.3章）: 画像アップロード → OCR実行 → 抽出テキストを
  **編集可能**表示（single=1エリア / split=ブロックごと）→ 手直し → 翻訳する →
  同ページに結果表示（split は元/訳ペア）。
- 画像モードから翻訳方向を自動決定（ja画像→ja→en / en画像→en→ja）。
- **ゼロ件時**は「文字が検出されませんでした」表示＋翻訳ボタン無効化。
- 送信前バリデーション（10MB / PNG・JPEG）もフロントで行う。
- **✅**: 画像→OCR→編集→翻訳→結果表示が通しで動く。single/split 両方確認。
  履歴に `origin=detection` で残り、`ocr_engine`/`block_mode` が記録される。

### 6-C. 翻訳履歴（`/history`）
- 全件を新しい順に表示。各行に API/OCR/ブロックモードのバッジ。
- split レコードは元/訳をブロックペアで表示。
- 1件削除ボタン＋全削除ボタン（全削除は確認ダイアログ必須）。
- **✅**: 履歴が全件出る。1件削除・全削除が動く。バッジで条件が判別できる。

### 6-D. ホーム（`/`）
- `GET /api/history?limit=5` で最新5件をカード表示。
- split・複数ブロックは先頭ブロックを代表表示し「他N件」等で省略。
- **✅**: 最新5件が出る。翻訳を追加すると反映される。

---

## フェーズ 7: 結合確認と検証準備

### やること
1. **通し検証シナリオ**を手動実行:
   - 同じ画像で OCRエンジンを切り替えて2回 → 履歴で粒度・結果を見比べられる。
   - 同じテキストで 翻訳APIを切り替えて2回 → 履歴で訳を見比べられる。
   - single と split を切り替えて挙動差を確認。
2. 異常系の確認: 巨大画像・非対応形式・文字なし画像・翻訳API失敗（不正キー）。
3. `ENABLE_ENGINE_TOGGLE=false` で本番相当の固定動作を確認。
4. README に「検証手順」（トグルを変えて履歴で見比べる方法）を追記。

### ✅ 完了条件（プロジェクト完了）
- 4画面すべてが仕様通り動作する。
- 履歴に検証に必要な情報（API/OCR/ブロックモード/origin）が正しく残る。
- 異常系がすべて設計通り（413/415/400/5xx・保存されない）に振る舞う。
- `npm run build` が厳格設定下でエラーなく通る。

---

## 実装順の理由（まとめ）
- **DB→翻訳→OCR** の順は、テストのしやすさ順。翻訳は入出力が単純で履歴保存フローを
  先に固められる。OCRは環境依存（Tesseract本体・GPU）が大きいので後。
- 各サービスは**モックを先に**作ることで、APIキーやGPUが無い段階でも
  フロント含む全体フローを検証できる。
- フロントは共通土台→依存の少ない画面順。ホームは履歴に依存するため最後。

## 特に注意すべき落とし穴（再掲）
- `source_text`/`translated_text` は**常に配列**。プレーン文字列で保存しない。
- 翻訳の入出力は**同順・同数**。ペアがずれると履歴表示が壊れる。
- 本番固定は**サーバー側でも**強制（フロント非表示だけでは不十分）。
- `noUncheckedIndexedAccess` 下では `blocks[i]` が `string | undefined`。
  適切に存在チェックすること（このプロジェクトで最も型が効く箇所）。
