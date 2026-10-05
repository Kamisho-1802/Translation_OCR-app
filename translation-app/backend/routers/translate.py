"""翻訳エンドポイント（DESIGN.md 第6.3章）。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

import database
from config import settings
from models import TranslateRequest, TranslateResponse
from services.translate.base import TranslationError
from services.translate.factory import get_translator

router = APIRouter(prefix="/api", tags=["translate"])


def resolve_translation_api(requested: str) -> str:
    """本番固定時（ENABLE_ENGINE_TOGGLE=false）はサーバー既定値で上書きする。

    クライアントの値を信用しない（DESIGN.md 第5章・第10章）。
    """
    if settings.enable_engine_toggle:
        return requested
    return settings.default_translation_api


def resolve_ocr_engine(requested: str | None) -> str | None:
    """OCRエンジン名も同様に固定する。translate 由来（None）はそのまま。"""
    if requested is None:
        return None
    if settings.enable_engine_toggle:
        return requested
    return settings.default_ocr_engine


@router.post("/translate", response_model=TranslateResponse)
def translate(req: TranslateRequest) -> TranslateResponse:
    """テキストを翻訳し、成功時のみ履歴に保存して返す。"""
    # 1. 空チェック: 空白のみの要素は除外し、1件も残らなければ400（保存しない）
    source_blocks = [block for block in req.blocks if block.strip()]
    if not source_blocks:
        raise HTTPException(status_code=400, detail="翻訳するテキストがありません")

    api_name = resolve_translation_api(req.translation_api)
    if settings.use_mock_translator:
        translator = get_translator("mock")
    else:
        try:
            translator = get_translator(api_name)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    # 2〜3. 順序を保って翻訳。1ブロックでも失敗したら全体失敗（履歴に保存しない）
    try:
        translated_blocks = translator.translate(
            source_blocks, req.source_lang, req.target_lang
        )
    except TranslationError as exc:
        raise HTTPException(status_code=502, detail=f"翻訳に失敗しました: {exc}") from exc

    if len(translated_blocks) != len(source_blocks):
        raise HTTPException(
            status_code=502, detail="翻訳結果の個数が入力と一致しませんでした"
        )

    # 4. 全ブロック成功時のみ保存
    row = database.insert_history(
        source_blocks=source_blocks,
        translated_blocks=translated_blocks,
        source_lang=req.source_lang,
        target_lang=req.target_lang,
        translation_api=api_name,
        ocr_engine=resolve_ocr_engine(req.ocr_engine),
        block_mode=req.block_mode,
        origin=req.origin,
    )

    return TranslateResponse(
        id=row["id"],
        source_blocks=row["source_blocks"],
        translated_blocks=row["translated_blocks"],
        source_lang=row["source_lang"],
        target_lang=row["target_lang"],
        translation_api=row["translation_api"],
        created_at=row["created_at"],
    )
