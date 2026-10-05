"""モック翻訳（APIキー無しでフロー全体を検証するため）。"""

from __future__ import annotations

from .base import Translator


class MockTranslator(Translator):
    """各ブロックの先頭に [XX] を付けて返すだけの実装。"""

    name = "mock"

    def translate(
        self, blocks: list[str], source_lang: str, target_lang: str
    ) -> list[str]:
        return [f"[{target_lang.upper()}] {block}" for block in blocks]
