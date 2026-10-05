"""DeepL API 実装（DESIGN.md 第7.3章の言語コードマッピングに従う）。"""

from __future__ import annotations

from typing import Any

import requests

from config import settings

from .base import TranslationError, Translator, chunked

# 内部表現 'ja'/'en' → DeepL の言語コード
_SOURCE_LANG = {"ja": "JA", "en": "EN"}
# target で 'EN' は非推奨のため EN-US を使う
_TARGET_LANG = {"ja": "JA", "en": "EN-US"}

# DeepL の1リクエストあたりのテキスト上限は50
_MAX_TEXTS_PER_REQUEST = 50
_TIMEOUT_SEC = 30


class DeepLTranslator(Translator):
    """DeepL API v2。"""

    name = "deepl"

    def translate(
        self, blocks: list[str], source_lang: str, target_lang: str
    ) -> list[str]:
        key = settings.deepl_api_key
        if not key:
            raise TranslationError("DEEPL_API_KEY が設定されていません")

        source = _SOURCE_LANG.get(source_lang)
        target = _TARGET_LANG.get(target_lang)
        if source is None or target is None:
            raise TranslationError(
                f"DeepL が対応しない言語指定です: {source_lang} -> {target_lang}"
            )

        # Free枠のキーは末尾が :fx。設定値より実キーの種別を優先してドメインを決める。
        base_url = settings.deepl_api_url.rstrip("/")
        if key.endswith(":fx"):
            base_url = "https://api-free.deepl.com"
        url = f"{base_url}/v2/translate"

        results: list[str] = []
        for chunk in chunked(blocks, _MAX_TEXTS_PER_REQUEST):
            results.extend(self._request(url, key, chunk, source, target))
        return results

    def _request(
        self, url: str, key: str, texts: list[str], source: str, target: str
    ) -> list[str]:
        try:
            res = requests.post(
                url,
                headers={
                    "Authorization": f"DeepL-Auth-Key {key}",
                    "Content-Type": "application/json",
                },
                json={"text": texts, "source_lang": source, "target_lang": target},
                timeout=_TIMEOUT_SEC,
            )
        except requests.RequestException as exc:
            raise TranslationError(f"DeepL への接続に失敗しました: {exc}") from exc

        if res.status_code != 200:
            raise TranslationError(
                f"DeepL がエラーを返しました (HTTP {res.status_code}): {res.text[:200]}"
            )

        try:
            data: Any = res.json()
            translations = data["translations"]
        except (ValueError, KeyError, TypeError) as exc:
            raise TranslationError("DeepL のレスポンス形式が不正です") from exc

        if not isinstance(translations, list) or len(translations) != len(texts):
            raise TranslationError("DeepL の翻訳結果の個数が入力と一致しません")

        out: list[str] = []
        for item in translations:
            text = item.get("text") if isinstance(item, dict) else None
            if not isinstance(text, str):
                raise TranslationError("DeepL のレスポンス形式が不正です")
            out.append(text)
        return out
