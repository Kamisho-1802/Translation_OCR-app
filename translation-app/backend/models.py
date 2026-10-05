"""Pydanticモデル（リクエスト/レスポンス）。

source_text / translated_text は DB 上では常にJSON配列文字列。
API 境界では配列（source_blocks / translated_blocks）として扱う。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Lang = Literal["ja", "en"]
TranslationApi = Literal["azure", "deepl"]
OcrEngine = Literal["tesseract", "easyocr", "mangaocr"]
BlockMode = Literal["single", "split"]
Origin = Literal["detection", "translate"]


class ConfigResponse(BaseModel):
    """GET /api/config"""

    enable_engine_toggle: bool
    default_translation_api: str
    default_ocr_engine: str


class OcrEngineResult(BaseModel):
    """1エンジン分のOCR結果。blocks は常に配列（ゼロ件なら空配列）。"""

    ocr_engine: str
    blocks: list[str]
    # そのエンジンだけが失敗したときのメッセージ。成功時は None。
    error: str | None = None


class OcrResponse(BaseModel):
    """POST /api/ocr のレスポンス。

    エンジンを選ばせるのではなく、実行したエンジンの結果を並べて返す。
    テスト時は Tesseract / easyOCR の2件、本番固定時は既定エンジンの1件。
    """

    results: list[OcrEngineResult]
    lang_mode: Lang
    block_mode: BlockMode


class TranslateRequest(BaseModel):
    """POST /api/translate のリクエスト。"""

    blocks: list[str]
    source_lang: Lang
    target_lang: Lang
    translation_api: TranslationApi
    origin: Origin
    # detection 由来のみ設定。translate 由来は null。
    ocr_engine: OcrEngine | None = None
    block_mode: BlockMode | None = None


class TranslateResponse(BaseModel):
    """POST /api/translate のレスポンス。"""

    id: int
    source_blocks: list[str]
    translated_blocks: list[str]
    source_lang: str
    target_lang: str
    translation_api: str
    created_at: str


class HistoryItem(BaseModel):
    """履歴1件。"""

    id: int
    source_blocks: list[str]
    translated_blocks: list[str]
    source_lang: str
    target_lang: str
    translation_api: str
    ocr_engine: str | None = None
    block_mode: str | None = None
    origin: str
    created_at: str


class HistoryListResponse(BaseModel):
    """GET /api/history"""

    items: list[HistoryItem] = Field(default_factory=list)
