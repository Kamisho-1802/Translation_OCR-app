import type { Direction, TranslateResult } from "./types";

// direction を DeepL の source_lang/target_lang へ変換
function langPair(direction: Direction): { source: string; target: string } {
  return direction === "en-ja"
    ? { source: "EN", target: "JA" }
    : { source: "JA", target: "EN" };
}

/**
 * DeepL API で翻訳する。
 * Free枠のキー(末尾 :fx)は api-free ドメイン、Proは api ドメインを叩く。
 * 失敗しても throw せず ok:false を返す。
 */
export async function translateDeepL(
  text: string,
  direction: Direction
): Promise<TranslateResult> {
  const start = performance.now();

  const key = process.env.DEEPL_API_KEY;
  if (!key) {
    return {
      ok: false,
      error: "missing_credentials",
      ms: Math.round(performance.now() - start),
    };
  }

  // Free枠のキーは末尾が :fx。ドメインを自動で振り分ける。
  const isFree = key.endsWith(":fx");
  const endpoint = isFree
    ? "https://api-free.deepl.com/v2/translate"
    : "https://api.deepl.com/v2/translate";

  const { source, target } = langPair(direction);

  try {
    const res = await fetch(endpoint, {
      method: "POST",
      headers: {
        Authorization: `DeepL-Auth-Key ${key}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        text: [text],
        source_lang: source,
        target_lang: target,
      }),
    });

    if (!res.ok) {
      return {
        ok: false,
        error: `http_${res.status}`,
        ms: Math.round(performance.now() - start),
      };
    }

    const data = (await res.json()) as {
      translations: Array<{ text: string; detected_source_language: string }>;
    };

    const translated = data?.translations?.[0]?.text;
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
