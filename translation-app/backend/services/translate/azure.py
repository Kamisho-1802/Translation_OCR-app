"""Azure Translator 実装（DESIGN.md 第7.3章の言語コードマッピングに従う）。"""

from __future__ import annotations

from typing import Any

import requests

from config import settings

from .base import TranslationError, Translator, chunked

# 内部表現 'ja'/'en' → Azure の言語コード（同じ表記）
_LANG = {"ja": "ja", "en": "en"}

# Azure は1リクエスト100要素まで。余裕をみて25要素ずつ送る。
_MAX_TEXTS_PER_REQUEST = 25
_TIMEOUT_SEC = 30


class AzureTranslator(Translator):
    """Azure Translator Text API v3.0。"""

    name = "azure"

    def translate(
        self, blocks: list[str], source_lang: str, target_lang: str
    ) -> list[str]:
        key = settings.azure_translator_key
        region = settings.azure_translator_region
        if not key or not region:
            raise TranslationError(
                "AZURE_TRANSLATOR_KEY / AZURE_TRANSLATOR_REGION が設定されていません"
            )

        source = _LANG.get(source_lang)
        target = _LANG.get(target_lang)
        if source is None or target is None:
            raise TranslationError(
                f"Azure が対応しない言語指定です: {source_lang} -> {target_lang}"
            )

        url = (
            f"{settings.azure_translator_endpoint.rstrip('/')}/translate"
            f"?api-version=3.0&from={source}&to={target}"
        )

        results: list[str] = []
        for chunk in chunked(blocks, _MAX_TEXTS_PER_REQUEST):
            results.extend(self._request(url, key, region, chunk))
        return results

    def _request(
        self, url: str, key: str, region: str, texts: list[str]
    ) -> list[str]:
        try:
            res = requests.post(
                url,
                headers={
                    "Ocp-Apim-Subscription-Key": key,
                    # Region が無いと 401 になる。
                    "Ocp-Apim-Subscription-Region": region,
                    "Content-Type": "application/json",
                },
                json=[{"Text": text} for text in texts],
                timeout=_TIMEOUT_SEC,
            )
        except requests.RequestException as exc:
            raise TranslationError(f"Azure への接続に失敗しました: {exc}") from exc

        if res.status_code != 200:
            raise TranslationError(
                f"Azure がエラーを返しました (HTTP {res.status_code}): {res.text[:200]}"
            )

        try:
            data: Any = res.json()
        except ValueError as exc:
            raise TranslationError("Azure のレスポンス形式が不正です") from exc

        if not isinstance(data, list) or len(data) != len(texts):
            raise TranslationError("Azure の翻訳結果の個数が入力と一致しません")

        out: list[str] = []
        for entry in data:
            try:
                text = entry["translations"][0]["text"]
            except (KeyError, IndexError, TypeError) as exc:
                raise TranslationError("Azure のレスポンス形式が不正です") from exc
            if not isinstance(text, str):
                raise TranslationError("Azure のレスポンス形式が不正です")
            out.append(text)
        return out
