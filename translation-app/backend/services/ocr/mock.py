"""モックOCR（Tesseract/easyOCR 無しでフローを検証するため）。"""

from __future__ import annotations

from .base import OCREngine, clean_blocks

_DUMMY = {
    "ja": ["これはモックOCRの1ブロック目です。", "これは2ブロック目です。"],
    "en": ["This is the first mock OCR block.", "This is the second block."],
}


class MockOCR(OCREngine):
    """画像の内容に関係なく固定のダミーブロックを返す。"""

    name = "mock"

    def extract(
        self, image_bytes: bytes, lang_mode: str, block_mode: str
    ) -> list[str]:
        blocks = _DUMMY.get(lang_mode, _DUMMY["en"])
        if block_mode == "single":
            return clean_blocks(["\n".join(blocks)])
        return clean_blocks(list(blocks))
