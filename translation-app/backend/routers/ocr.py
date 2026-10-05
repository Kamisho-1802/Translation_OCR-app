"""OCRエンドポイント（DESIGN.md 第6.2章）。履歴保存はしない。

DESIGN.md からの変更: エンジンを1つ選んで実行するのではなく、
**Tesseract と easyOCR の両方を実行して結果を並べて返す**。
どちらの結果を使うかはユーザーが画面で選ぶ（選ばれたエンジン名は翻訳時に履歴へ残る）。
本番固定時（ENABLE_ENGINE_TOGGLE=false）は選択の余地が無いので既定エンジンのみ実行する。
"""

from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from config import settings
from models import OcrEngineResult, OcrResponse
from services.ocr.base import OcrError
from services.ocr.factory import get_ocr_engine
from services.ocr.mangaocr_engine import SUPPORTED_LANG_MODES as MANGAOCR_LANG_MODES

router = APIRouter(prefix="/api", tags=["ocr"])

_VALID_LANG_MODES = {"ja", "en"}
_VALID_BLOCK_MODES = {"single", "split"}

# 比較のために同時実行するエンジン（表示順）
_COMPARE_ENGINES = ["tesseract", "easyocr", "mangaocr"]


def engines_to_run(lang_mode: str) -> list[str]:
    """実行するエンジン名を返す。

    - ENABLE_ENGINE_TOGGLE=true : 全エンジンを実行してユーザーに選ばせる
    - false（本番固定）         : サーバー既定のエンジンのみ

    manga-ocr は日本語専用なので、英語画像のときは最初から候補に入れない
    （毎回「日本語専用です」というエラーカードが出るのを避ける）。
    """
    if not settings.enable_engine_toggle:
        return [settings.default_ocr_engine]

    return [
        name
        for name in _COMPARE_ENGINES
        if name != "mangaocr" or lang_mode in MANGAOCR_LANG_MODES
    ]


def _validate_image(upload: UploadFile, image_bytes: bytes) -> None:
    """形式・サイズを検証する。非対応は415、超過は413。"""
    content_type = (upload.content_type or "").split(";")[0].strip().lower()
    if content_type not in settings.allowed_image_types:
        raise HTTPException(
            status_code=415,
            detail=(
                f"対応していない形式です。{settings.max_image_size_mb}MBまでの"
                "PNG/JPEG画像にしてください"
            ),
        )
    if len(image_bytes) > settings.max_image_size_bytes:
        raise HTTPException(
            status_code=413,
            detail=(
                f"画像が大きすぎます。{settings.max_image_size_mb}MBまでの"
                "PNG/JPEG画像にしてください"
            ),
        )


def _run_engine(
    engine_name: str, image_bytes: bytes, lang_mode: str, block_mode: str
) -> OcrEngineResult:
    """1エンジン分のOCRを実行する。

    片方のエンジンが落ちても、もう片方の結果は使えるようにしたいので、
    失敗は例外にせず result.error に載せて返す。
    """
    name = "mock" if settings.use_mock_ocr else engine_name
    try:
        engine = get_ocr_engine(name)
    except ValueError as exc:
        return OcrEngineResult(ocr_engine=engine_name, blocks=[], error=str(exc))

    try:
        blocks = engine.extract(image_bytes, lang_mode, block_mode)
    except OcrError as exc:
        return OcrEngineResult(
            ocr_engine=engine_name, blocks=[], error=f"OCRに失敗しました: {exc}"
        )
    return OcrEngineResult(ocr_engine=engine_name, blocks=blocks, error=None)


@router.post("/ocr", response_model=OcrResponse)
def ocr(
    image: UploadFile = File(...),
    lang_mode: str = Form(...),
    block_mode: str = Form("single"),
) -> OcrResponse:
    """画像からテキストを抽出する。ゼロ件は空配列（エラーにしない）。"""
    if lang_mode not in _VALID_LANG_MODES:
        raise HTTPException(status_code=400, detail=f"不正な lang_mode です: {lang_mode}")
    if block_mode not in _VALID_BLOCK_MODES:
        raise HTTPException(status_code=400, detail=f"不正な block_mode です: {block_mode}")

    image_bytes = image.file.read()
    _validate_image(image, image_bytes)

    results = [
        _run_engine(name, image_bytes, lang_mode, block_mode)
        for name in engines_to_run(lang_mode)
    ]

    # 全エンジンが失敗したときだけエラーにする（片方でも結果があれば返す）
    if all(result.error is not None for result in results):
        detail = "; ".join(result.error or "" for result in results)
        raise HTTPException(status_code=500, detail=detail)

    return OcrResponse(
        results=results,
        lang_mode=lang_mode,  # type: ignore[arg-type]
        block_mode=block_mode,  # type: ignore[arg-type]
    )
