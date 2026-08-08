# 翻訳API比較アプリ

Azure Translator と DeepL の訳文を、同じ原文で並べて比較する検証用アプリ。

## セットアップ

```bash
npm install
```

環境変数を用意します。`.env.local.example` をコピーして値を埋めてください。

```bash
cp .env.local.example .env.local
```

```
AZURE_TRANSLATOR_KEY=<Azureのキー>
AZURE_TRANSLATOR_REGION=japaneast
DEEPL_API_KEY=<DeepLのキー（Free枠は末尾が :fx）>
```

> **重要**: 環境変数名に `NEXT_PUBLIC_` を付けないこと。付けるとキーがクライアントJSに埋め込まれます。
> `.env.local` は `.gitignore` 済みなのでコミットされません。

## 起動

```bash
npm run dev
```

http://localhost:3000 を開きます。

## 構成

```
translation-compare/
├── app/
│   ├── page.tsx              画面（クライアントコンポーネント）
│   ├── layout.tsx
│   ├── globals.css
│   └── api/translate/route.ts  プロキシ本体（Promise.allSettled で並列呼び出し）
└── lib/
    ├── types.ts             共通型・direction 検証
    ├── azure.ts             translateAzure(text, direction)
    └── deepl.ts             translateDeepL(text, direction)
```

`lib/azure.ts` と `lib/deepl.ts` は同じシグネチャに揃えてあるので、3つ目のサービスを足すのも容易です。

## 注意

- **無料枠の消費に注意**: Azure F0 は月200万文字、DeepL API Free は月50万文字。DeepL のほうが先に尽きます。
- **同じ原文を2回翻訳すると文字数も2回分**消費されます（キャッシュ未実装）。
- **個人情報や機密テキストは入力しない**。無料枠は DPA がなく、データがサービス改善に使われる可能性があります。
