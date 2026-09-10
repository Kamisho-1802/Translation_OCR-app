"""正規化プロファイル（仕様書 §4.5）。

strict: NFKC のみ + 連続空白の潰し。大文字小文字を区別する（ALL CAPS が意味を持つ）。
loose:  NFKC + 記号除去 + 小文字化 + 空白除去。

判読不能文字 "■" は評価対象外（§6.1）。GT/pred の両側から除去してから比較する。
プロファイル定義は config/norm_profiles.yaml から読む。
"""

from __future__ import annotations

import re
import unicodedata

from ..core import config as cfg

_ILLEGIBLE = "■"
_SYMBOL_CATEGORIES = ("P", "S")  # Punctuation / Symbol


def _remove_symbols(text: str) -> str:
    return "".join(
        ch for ch in text if unicodedata.category(ch)[0] not in _SYMBOL_CATEGORIES
    )


def normalize(text: str, profile: str | dict) -> str:
    """指定プロファイルで正規化した文字列を返す。

    profile はプロファイル名（"strict"/"loose"）または設定 dict。
    """
    if text is None:
        text = ""
    opts = cfg.norm_profiles()[profile] if isinstance(profile, str) else profile

    # 判読不能文字は常に除去（評価対象外）。
    text = text.replace(_ILLEGIBLE, "")

    if opts.get("nfkc", True):
        text = unicodedata.normalize("NFKC", text)
    if opts.get("remove_symbols", False):
        text = _remove_symbols(text)
    if opts.get("casefold", False):
        text = text.casefold()
    if opts.get("strip_whitespace", False):
        text = re.sub(r"\s+", "", text)
    elif opts.get("collapse_spaces", True):
        text = re.sub(r"\s+", " ", text).strip()
    return text
