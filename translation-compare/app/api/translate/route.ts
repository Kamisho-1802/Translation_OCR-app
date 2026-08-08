import { NextResponse } from "next/server";
import { translateAzure } from "@/lib/azure";
import { translateDeepL } from "@/lib/deepl";
import {
  isDirection,
  MAX_CHARS,
  type TranslateResult,
  type TranslateResponse,
} from "@/lib/types";

// allSettled の rejected は基本起きない（lib側でcatch済み）が、保険として変換する。
function settledToResult(
  r: PromiseSettledResult<TranslateResult>
): TranslateResult {
  if (r.status === "fulfilled") return r.value;
  return { ok: false, error: "internal_error", ms: 0 };
}

export async function POST(req: Request) {
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "invalid_json" }, { status: 400 });
  }

  const { text, direction } = (body ?? {}) as {
    text?: unknown;
    direction?: unknown;
  };

  // direction はホワイトリスト検証。想定外なら 400。
  if (!isDirection(direction)) {
    return NextResponse.json({ error: "invalid_direction" }, { status: 400 });
  }

  if (typeof text !== "string" || text.trim().length === 0) {
    return NextResponse.json({ error: "empty_text" }, { status: 400 });
  }

  // クライアントの maxLength は信用せず、サーバー側でも切り詰める。
  const trimmed = text.slice(0, MAX_CHARS);

  // 片方が落ちてももう片方を返すため allSettled を使う。
  const [azureSettled, deeplSettled] = await Promise.allSettled([
    translateAzure(trimmed, direction),
    translateDeepL(trimmed, direction),
  ]);

  const response: TranslateResponse = {
    azure: settledToResult(azureSettled),
    deepl: settledToResult(deeplSettled),
    chars: trimmed.length,
  };

  return NextResponse.json(response);
}
