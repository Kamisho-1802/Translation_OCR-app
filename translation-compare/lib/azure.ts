import type { Direction, TranslateResult } from "./types";

// direction を Azure の from/to コードへ変換
function langPair(direction: Direction): { from: string; to: string } {
  return direction === "en-ja"
    ? { from: "en", to: "ja" }
    : { from: "ja", to: "en" };
}

const ENDPOINT = "https://api.cognitive.microsofttranslator.com/translate";

/**
 * Azure Translator で翻訳する。
 * ネットワーク込みの所要時間(ms)も返す。失敗しても throw せず ok:false を返す。
 */
export async function translateAzure(
  text: string,
  direction: Direction
): Promise<TranslateResult> {
  const start = performance.now();

  const key = process.env.AZURE_TRANSLATOR_KEY;
  const region = process.env.AZURE_TRANSLATOR_REGION;

  if (!key || !region) {
    return {
      ok: false,
      error: "missing_credentials",
      ms: Math.round(performance.now() - start),
    };
  }

  const { from, to } = langPair(direction);
  const url = `${ENDPOINT}?api-version=3.0&from=${from}&to=${to}`;

  try {
    const res = await fetch(url, {
      method: "POST",
      headers: {
        "Ocp-Apim-Subscription-Key": key,
        // Region が無いと 401 になる。忘れがち。
        "Ocp-Apim-Subscription-Region": region,
        "Content-Type": "application/json",
      },
      body: JSON.stringify([{ Text: text }]),
    });

    if (!res.ok) {
      return {
        ok: false,
        error: `http_${res.status}`,
        ms: Math.round(performance.now() - start),
      };
    }

    const data = (await res.json()) as Array<{
      translations: Array<{ text: string; to: string }>;
    }>;

    const translated = data?.[0]?.translations?.[0]?.text;
    if (typeof translated !== "string") {
      return {
        ok: false,
        error: "unexpected_response",
        ms: Math.round(performance.now() - start),
      };
    }

    return {
      ok: true,
      text: translated,
      ms: Math.round(performance.now() - start),
    };
  } catch {
    return {
      ok: false,
      error: "network_error",
      ms: Math.round(performance.now() - start),
    };
  }
}
