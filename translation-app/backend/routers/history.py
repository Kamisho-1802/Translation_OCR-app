"""履歴エンドポイント（DESIGN.md 第6.4〜6.6章）。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Response, status

import database
from models import HistoryItem, HistoryListResponse

router = APIRouter(prefix="/api", tags=["history"])


@router.get("/history", response_model=HistoryListResponse)
def get_history(limit: int | None = Query(default=None, ge=1)) -> HistoryListResponse:
    """履歴を新しい順に返す。limit 省略で全件。"""
    rows = database.list_history(limit)
    return HistoryListResponse(items=[HistoryItem(**row) for row in rows])


@router.delete("/history/{history_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_history_item(history_id: int) -> Response:
    """履歴を1件削除する。存在しなければ404。"""
    if not database.delete_history(history_id):
        raise HTTPException(status_code=404, detail="履歴が見つかりません")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/history", status_code=status.HTTP_204_NO_CONTENT)
def delete_all_history_items() -> Response:
    """履歴を全件削除する。"""
    database.delete_all_history()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
