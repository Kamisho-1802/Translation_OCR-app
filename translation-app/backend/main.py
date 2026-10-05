"""FastAPI エントリポイント。"""

from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import database
from config import settings
from models import ConfigResponse
from routers import history, ocr, translate


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """起動時にDB（ファイル・テーブル）を用意する。"""
    database.init_db()
    yield


app = FastAPI(title="OCR Translate App API", lifespan=lifespan)

# ローカル検証用。フロント（Vite dev server）からの呼び出しを許可する。
app.add_middleware(
    CORSMiddleware,
    # Vite が別ポートで起動することがある（5173 が埋まっていると 5174…）ので、
    # ローカルホストであればポートを問わず許可する。
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(history.router)
app.include_router(translate.router)
app.include_router(ocr.router)


@app.get("/")
def health() -> dict[str, str]:
    """ヘルスチェック。"""
    return {"status": "ok"}


@app.get("/api/config", response_model=ConfigResponse)
def get_config() -> ConfigResponse:
    """フロント初期化用。トグル表示可否と既定値を返す（DESIGN.md 第6.1章）。"""
    return ConfigResponse(
        enable_engine_toggle=settings.enable_engine_toggle,
        default_translation_api=settings.default_translation_api,
        default_ocr_engine=settings.default_ocr_engine,
    )
