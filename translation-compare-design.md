# 翻訳API比較アプリ 設計書

Azure Translator と DeepL の翻訳品質を、同じ原文で並べて比較するための検証用アプリ。

---

## 1. 目的とスコープ

### 目的

- 同一の原文に対する Azure Translator と DeepL の訳文を**並べて目視比較**する
- 応答速度と消費文字数を実測し、本番採用時の判断材料にする
- バックエンドプロキシ経由でAPIを呼ぶ構成を、小さく試しておく

### スコープ内

- 英日 / 日英の双方向翻訳
- 2つのAPIを同時に呼び、結果を左右に並べて表示
- レイテンシと文字数の計測表示
- セッション内の累計使用文字数カウント（無料枠の消費管理用）

### スコープ外（今回はやらない）

- ユーザー認証、アカウント機能
- データベース、翻訳履歴の永続化
- 公開デプロイ、独自ドメイン
- 3言語以上への対応
- 翻訳結果の自動スコアリング（BLEU等）

---

## 2. 構成

```
[ブラウザ]
    │  POST /api/translate  { text, direction }
    ▼
[Next.js API Route]  ← APIキーはここだけが保持
    │
    ├──► Azure Translator API   ┐ Promise.all で並列
    └──► DeepL API              ┘
    │
    ▼  { azure: {...}, deepl: {...} }
[ブラウザ：2カラムで表示]
```

### 技術選定

| 項目 | 選定 | 理由 |
|---|---|---|
| フレームワーク | Next.js (App Router) | フロントとAPIプロキシが1プロジェクトで完結する |
| 言語 | TypeScript | |
| スタイル | Tailwind CSS | 検証用途なのでコンポーネントライブラリは入れない |
| 状態管理 | `useState` のみ | 画面が1つなので不要 |
| 実行環境 | ローカル (`npm run dev`) | 公開しない |

> より軽くしたい場合は Express + 静的HTML 1枚でも成立します。要は「APIキーを持つサーバー層が1つある」ことだけが必須条件です。

---

## 3. 画面設計

画面は1つだけ。上から下に積むシングルカラムレイアウト。

```
┌─────────────────────────────────────────────┐
│  翻訳API比較                    [EN→JA ▾]   │
├─────────────────────────────────────────────┤
│  ┌───────────────────────────────────────┐  │
│  │ 原文を入力…                           │  │
│  │                                       │  │
│  └───────────────────────────────────────┘  │
│  1,240 / 5,000 文字        [ 翻訳する ]     │
├─────────────────────────────────────────────┤
│  ┌──────────────────┐ ┌──────────────────┐  │
│  │ Azure    420ms   │ │ DeepL    680ms   │  │
│  ├──────────────────┤ ├──────────────────┤  │
│  │ 訳文…            │ │ 訳文…            │  │
│  │                  │ │                  │  │
│  │          [コピー]│ │          [コピー]│  │
│  └──────────────────┘ └──────────────────┘  │
├─────────────────────────────────────────────┤
│  このセッションの消費: Azure 3,200 / DeepL 3,200 │
└─────────────────────────────────────────────┘
```

### UI要素

| 要素 | 挙動 |
|---|---|
| 方向セレクタ | `EN→JA` / `JA→EN` の2択のみ |
| 原文テキストエリア | 5,000文字で `maxLength` 制限。残り文字数を表示 |
| 翻訳ボタン | 空文字・実行中は `disabled`。連打防止 |
| 結果カード ×2 | 見出しにサービス名と所要時間。ローディング中はスケルトン表示 |
| コピーボタン | `navigator.clipboard.writeText` |
| エラー表示 | 片方だけ失敗した場合、そのカードにのみエラーを出す（もう片方は成功として表示） |
| 累計カウンタ | ページリロードでリセットされてよい |

**レスポンシブ**: 画面幅768px未満では結果カードを縦積みに。

---

## 4. API設計

### `POST /api/translate`

リクエスト:

```json
{
  "text": "The quick brown fox jumps over the lazy dog.",
  "direction": "en-ja"
}
```

レスポンス:

```json
{
  "azure": { "ok": true, "text": "素早い茶色のキツネが…", "ms": 420 },
  "deepl": { "ok": true, "text": "素早い茶色のキツネが…", "ms": 680 },
  "chars": 44
}
```

失敗時は該当サービスのみ:

```json
{ "azure": { "ok": false, "error": "rate_limited" }, ... }
```

### 実装上のポイント

- **`Promise.allSettled` を使う**。片方が落ちてももう片方の結果を返すため
- 入力は `text.slice(0, 5000)` でサーバー側でも切り詰める（クライアントの `maxLength` は信用しない）
- `direction` はホワイトリスト検証。想定外の値は400を返す
- `ms` は `performance.now()` の差分。ネットワーク込みの実測値

### 各サービスの呼び出し仕様

**Azure Translator**

```
POST https://api.cognitive.microsofttranslator.com/translate
  ?api-version=3.0&from=en&to=ja

Headers:
  Ocp-Apim-Subscription-Key: <KEY>
  Ocp-Apim-Subscription-Region: <REGION>   ← 忘れがち。無いと401になる
  Content-Type: application/json

Body: [{ "Text": "..." }]
Response: [{ "translations": [{ "text": "...", "to": "ja" }] }]
```

**DeepL**

```
POST https://api-free.deepl.com/v2/translate   ← Free枠は api-free ドメイン
                                                  (Proは api.deepl.com)
Headers:
  Authorization: DeepL-Auth-Key <KEY>
  Content-Type: application/json

Body: { "text": ["..."], "source_lang": "EN", "target_lang": "JA" }
Response: { "translations": [{ "text": "...", "detected_source_language": "EN" }] }
```

> DeepLの無料枠のキーは末尾が `:fx` になっています。これが付いているのに `api.deepl.com` を叩くと認証エラーになるので注意。

---

## 5. ディレクトリ構成

```
translation-compare/
├── .env.local            ← Git管理外
├── .gitignore
├── app/
│   ├── page.tsx          ← 画面（クライアントコンポーネント）
│   ├── layout.tsx
│   ├── globals.css
│   └── api/
│       └── translate/
│           └── route.ts  ← プロキシ本体
├── lib/
│   ├── azure.ts          ← translateAzure(text, direction)
│   └── deepl.ts          ← translateDeepL(text, direction)
├── package.json
└── tsconfig.json
```

`lib/` の2ファイルは同じシグネチャに揃えておくと、後で3つ目のサービスを足すときに楽です。

### 環境変数（`.env.local`）

```
AZURE_TRANSLATOR_KEY=
AZURE_TRANSLATOR_REGION=japaneast
DEEPL_API_KEY=
```

`.gitignore` に `.env*.local` が入っていることを最初に確認すること。Next.js の初期テンプレートには含まれていますが、目視確認を推奨します。

**キーをクライアントに出さないための鉄則**: 環境変数名に `NEXT_PUBLIC_` を絶対に付けない。付けるとビルド時にJSへ埋め込まれます。

---

## 6. 実装手順

1. `npx create-next-app@latest` でプロジェクト作成（TypeScript / Tailwind / App Router を選択）
2. Azure ポータルで Translator リソースを作成 → キーとリージョンを取得（F0 無料プランを選択）
3. DeepL で API Free アカウント登録 → キー取得
4. `.env.local` を作成し、`.gitignore` を確認
5. `lib/azure.ts` を実装し、`curl` かテストスクリプトで単体で動くことを確認
6. `lib/deepl.ts` を同様に実装・確認
7. `app/api/translate/route.ts` で2つを `Promise.allSettled` で並列呼び出し
8. `app/page.tsx` でUI実装
9. レスポンシブ調整とエラー表示の作り込み

**手順5と6を先にやることが重要**です。UIから通しでデバッグすると、認証エラーなのかフロントのバグなのか切り分けに時間がかかります。

---

## 7. 品質比較の観点

せっかく作るので、以下のようなテストケースを用意しておくと差が見えやすくなります。

| カテゴリ | 例 | 見るポイント |
|---|---|---|
| 定型的なビジネス文 | メール文面 | どちらも問題ないはず。ベースライン |
| 口語・くだけた表現 | SNS投稿風 | DeepLが自然と言われる領域 |
| 専門用語 | 技術文書の一節 | 用語の訳し方の一貫性 |
| 長文の一貫性 | 5〜6文の段落 | 主語の補完、指示語の扱い |
| 固有名詞 | 製品名・人名を含む文 | 無理に訳していないか |
| 曖昧な主語 | 日本語→英語で主語省略 | 補完の妥当性。日英方向の差が出やすい |

これらをテキストファイルに用意しておき、貼り付けて実行するだけにしておくと比較が捗ります。

---

## 8. 注意事項

- **無料枠の消費に注意**: Azure F0 は月200万文字、DeepL API Free は月50万文字。DeepLのほうが先に尽きます。累計カウンタで消費量を把握してください
- **同じ原文を2回翻訳すると文字数も2回分**消費されます。今回はキャッシュを実装しないので、意図的にそうなります
- **個人情報や機密テキストは入力しない**。無料枠にはDPAがなく、データがサービス改善に使われる可能性があります
- **本番へ持っていく際の追加項目**: 認証、レート制限、キャッシュ層、リトライ処理（429対策の指数バックオフ）、課金アラート
