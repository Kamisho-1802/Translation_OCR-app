// 翻訳の方向。ホワイトリスト検証に使う。
export type Direction = "en-ja" | "ja-en";

export const DIRECTIONS: Direction[] = ["en-ja", "ja-en"];

export function isDirection(v: unknown): v is Direction {
  return typeof v === "string" && (DIRECTIONS as string[]).includes(v);
}

// 各サービスの翻訳結果。lib/azure.ts と lib/deepl.ts で共通のシグネチャに揃える。
export type TranslateOk = {
  ok: true;
  text: string;
  ms: number;
};

export type TranslateErr = {
  ok: false;
  error: string;
  ms: number;
};

export type TranslateResult = TranslateOk | TranslateErr;

// API レスポンス全体の型
export type TranslateResponse = {
  azure: TranslateResult;
  deepl: TranslateResult;
  chars: number;
};

export const MAX_CHARS = 5000;
