"use client";

import { useState } from "react";
import {
  MAX_CHARS,
  type Direction,
  type TranslateResponse,
  type TranslateResult,
} from "@/lib/types";

// エラーコードを日本語の表示文言へ
function errorLabel(code: string): string {
  switch (code) {
    case "missing_credentials":
      return "APIキー未設定";
    case "network_error":
      return "ネットワークエラー";
    case "unexpected_response":
      return "予期しない応答";
    case "internal_error":
      return "内部エラー";
    default:
      if (code.startsWith("http_")) return `HTTPエラー (${code.slice(5)})`;
      return code;
  }
}

// 結果カード1枚
function ResultCard({
  name,
  color,
  loading,
  result,
}: {
  name: string;
  color: string;
  loading: boolean;
  result: TranslateResult | null;
}) {
  const [copied, setCopied] = useState(false);

  async function handleCopy(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
    } catch {
      // クリップボードが使えない環境では黙って無視
    }
  }

  const ms = result?.ms;

  return (
    <div className="flex flex-1 flex-col rounded-lg border border-slate-200 bg-white shadow-sm">
      {/* 見出し: サービス名 + 所要時間 */}
      <div className="flex items-center justify-between border-b border-slate-100 px-4 py-2.5">
        <span className={`text-sm font-semibold ${color}`}>{name}</span>
        {typeof ms === "number" && !loading ? (
          <span className="text-xs tabular-nums text-slate-500">{ms}ms</span>
        ) : null}
      </div>

      {/* 本文 */}
      <div className="flex flex-1 flex-col p-4">
        {loading ? (
          // ローディング中はスケルトン表示
          <div className="flex-1 animate-pulse space-y-2">
            <div className="h-3.5 w-full rounded bg-slate-200" />
            <div className="h-3.5 w-11/12 rounded bg-slate-200" />
            <div className="h-3.5 w-4/5 rounded bg-slate-200" />
          </div>
        ) : result == null ? (
          <p className="flex-1 text-sm text-slate-400">
            翻訳結果がここに表示されます
          </p>
        ) : result.ok ? (
          <>
            <p className="flex-1 whitespace-pre-wrap break-words text-sm leading-relaxed text-slate-800">
              {result.text}
            </p>
            <div className="mt-3 flex justify-end">
              <button
                type="button"
                onClick={() => handleCopy(result.text)}
                className="rounded border border-slate-200 px-2.5 py-1 text-xs text-slate-600 transition hover:bg-slate-50 active:bg-slate-100"
              >
                {copied ? "コピーしました" : "コピー"}
              </button>
            </div>
          </>
        ) : (
          // このカードだけ失敗した場合のエラー表示
          <div className="flex flex-1 items-start">
            <p className="rounded bg-red-50 px-3 py-2 text-sm text-red-600">
              {errorLabel(result.error)}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

export default function Home() {
  const [text, setText] = useState("");
  const [direction, setDirection] = useState<Direction>("en-ja");
  const [loading, setLoading] = useState(false);
  const [azure, setAzure] = useState<TranslateResult | null>(null);
  const [deepl, setDeepl] = useState<TranslateResult | null>(null);
  const [topError, setTopError] = useState<string | null>(null);

  // セッション累計の消費文字数（リロードでリセットされてよい）
  const [azureTotal, setAzureTotal] = useState(0);
  const [deeplTotal, setDeeplTotal] = useState(0);

  const remaining = MAX_CHARS - text.length;
  const canTranslate = text.trim().length > 0 && !loading;

  async function handleTranslate() {
    if (!canTranslate) return;

    setLoading(true);
    setTopError(null);
    setAzure(null);
    setDeepl(null);

    try {
      const res = await fetch("/api/translate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, direction }),
      });

      if (!res.ok) {
        setTopError("リクエストに失敗しました。入力を確認してください。");
        return;
      }

      const data = (await res.json()) as TranslateResponse;
      setAzure(data.azure);
      setDeepl(data.deepl);

      // 成功した側だけ消費文字数を累計に加算
      if (data.azure.ok) setAzureTotal((n) => n + data.chars);
      if (data.deepl.ok) setDeeplTotal((n) => n + data.chars);
    } catch {
      setTopError("通信エラーが発生しました。");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="mx-auto max-w-4xl px-4 py-8">
      {/* ヘッダー: タイトル + 方向セレクタ */}
      <header className="mb-6 flex items-center justify-between">
        <h1 className="text-xl font-bold text-slate-900">翻訳API比較</h1>
        <select
          value={direction}
          onChange={(e) => setDirection(e.target.value as Direction)}
          className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm text-slate-700 shadow-sm focus:border-slate-400 focus:outline-none"
        >
          <option value="en-ja">EN → JA</option>
          <option value="ja-en">JA → EN</option>
        </select>
      </header>

      {/* 入力エリア */}
      <section className="mb-6 rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          maxLength={MAX_CHARS}
          rows={6}
          placeholder="原文を入力…"
          className="w-full resize-y rounded-md border border-slate-200 p-3 text-sm leading-relaxed text-slate-800 placeholder:text-slate-400 focus:border-slate-400 focus:outline-none"
        />
        <div className="mt-3 flex items-center justify-between">
          <span
            className={`text-xs tabular-nums ${
              remaining < 0 ? "text-red-500" : "text-slate-500"
            }`}
          >
            {text.length.toLocaleString()} / {MAX_CHARS.toLocaleString()} 文字
          </span>
          <button
            type="button"
            onClick={handleTranslate}
            disabled={!canTranslate}
            className="rounded-md bg-slate-900 px-5 py-2 text-sm font-medium text-white transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:bg-slate-300"
          >
            {loading ? "翻訳中…" : "翻訳する"}
          </button>
        </div>
      </section>

      {topError ? (
        <p className="mb-4 rounded-md bg-red-50 px-4 py-2 text-sm text-red-600">
          {topError}
        </p>
      ) : null}

      {/* 結果カード ×2。768px未満では縦積み（flex-col → md:flex-row） */}
      <section className="mb-6 flex flex-col gap-4 md:flex-row">
        <ResultCard
          name="Azure"
          color="text-sky-600"
          loading={loading}
          result={azure}
        />
        <ResultCard
          name="DeepL"
          color="text-indigo-600"
          loading={loading}
          result={deepl}
        />
      </section>

      {/* セッション累計消費 */}
      <footer className="rounded-lg border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600 shadow-sm">
        <span className="font-medium text-slate-700">このセッションの消費: </span>
        <span className="tabular-nums">
          Azure {azureTotal.toLocaleString()} / DeepL {deeplTotal.toLocaleString()} 文字
        </span>
      </footer>
    </main>
  );
}
