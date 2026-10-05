"""OCR実装のファクトリ（文字列キー → 実装）。"""

from __future__ import annotations

from .base import OCREngine
from .easyocr_engine import EasyOcrEngine
from .mangaocr_engine import MangaOcrEngine
from .mock import MockOCR
from .tesseract import TesseractEngine

_ENGINES: dict[str, type[OCREngine]] = {
    "tesseract": TesseractEngine,
    "easyocr": EasyOcrEngine,
    "mangaocr": MangaOcrEngine,
    "mock": MockOCR,
}


def get_ocr_engine(name: str) -> OCREngine:
    """名前からOCR実装を返す。未知の名前は ValueError。"""
    engine_cls = _ENGINES.get(name)
    if engine_cls is None:
        raise ValueError(f"未対応のOCRエンジンです: {name}")
    return engine_cls()
