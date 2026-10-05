"""翻訳実装のファクトリ（文字列キー → 実装）。"""

from __future__ import annotations

from .azure import AzureTranslator
from .base import Translator
from .deepl import DeepLTranslator
from .mock import MockTranslator

_TRANSLATORS: dict[str, type[Translator]] = {
    "deepl": DeepLTranslator,
    "azure": AzureTranslator,
    "mock": MockTranslator,
}


def get_translator(name: str) -> Translator:
    """名前から翻訳実装を返す。未知の名前は ValueError。"""
    translator_cls = _TRANSLATORS.get(name)
    if translator_cls is None:
        raise ValueError(f"未対応の翻訳APIです: {name}")
    return translator_cls()
