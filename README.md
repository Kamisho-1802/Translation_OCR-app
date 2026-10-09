# translation-app

翻訳 OSS・翻訳 API を使ったアプリ開発と、その検証用ツールを集めたリポジトリ。
現在は 2 つのサブプロジェクトで構成されています。

## プロジェクト一覧

### 🌐 translation-compare

Azure Translator と DeepL の訳文を、同じ原文で並べて比較する検証用 Web アプリ。
Next.js (App Router) + TypeScript + Tailwind CSS 製で、API キーはサーバー側のプロキシ
(`/api/translate`) だけが保持します。英日 / 日英の双方向翻訳・レイテンシ計測・累計文字数カウントに対応。

- [translation-compare/](translation-compare/) — アプリ本体
- [translation-compare/README.md](translation-compare/README.md) — セットアップと起動手順
- [translation-compare-design.md](translation-compare-design.md) — 設計書（目的・構成・API・画面設計）

### 🎮 game-ocr-bench

ゲーム画面のスクリーンショットに対し、無料で使える 3 つの OCR エンジン
（Tesseract / EasyOCR / PaddleOCR）を同一の正解データ・同一指標で比較するベンチマークツール。
ingest → run → eval → report → GT → sweep → UI までを CLI `ocr-bench` で通して実行できます。

- [game-ocr-bench/](game-ocr-bench/) — ツール本体
- [game-ocr-bench/README.md](game-ocr-bench/README.md) — セットアップ・使い方・実装フェーズの進捗
- [game-ocr-bench/RESULTS.md](game-ocr-bench/RESULTS.md) — 予備調査（5 枚）の比較結果

## ディレクトリ構成

```
translation-app/
├── translation-compare/        翻訳API比較アプリ（Next.js）
├── translation-compare-design.md  同アプリの設計書
└── game-ocr-bench/             ゲーム画面OCR精度比較ツール（Python）
```
