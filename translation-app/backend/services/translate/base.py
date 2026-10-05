"""Translator 抽象基底クラス（DESIGN.md 第7.1章）。"""

from __future__ import annotations


class TranslationError(RuntimeError):
    """翻訳APIの呼び出しに失敗したことを表す。

    1ブロックでも失敗したら全体失敗とするため、例外で中断する（DESIGN.md 第6.3章）。
    """


class Translator:
    """翻訳APIの共通インターフェース。"""

    name: str = "base"

    def translate(
        self, blocks: list[str], source_lang: str, target_lang: str
    ) -> list[str]:
        """入力と同順・同数の訳配列を返す。"""
        raise NotImplementedError


def chunked(items: list[str], size: int) -> list[list[str]]:
    """APIの1リクエスト上限に合わせて分割する（順序は保たれる）。"""
    return [items[i : i + size] for i in range(0, len(items), size)]
