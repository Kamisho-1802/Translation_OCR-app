"""エンジンレジストリ（仕様書 §9）。

アダプタは自身を register() で登録する。runner はここから id で解決する。
新エンジン追加時に触るのは adapters/ とこの登録呼び出しのみ（受け入れ基準）。
エンジン本体は遅延生成（factory）にして、未インストールのエンジンを
import しただけで落ちないようにする。
"""

from __future__ import annotations

from typing import Callable

from .types import OcrEngine

# id -> factory（呼ぶと OcrEngine を返す）
_FACTORIES: dict[str, Callable[[], OcrEngine]] = {}


def register(engine_id: str, factory: Callable[[], OcrEngine]) -> None:
    _FACTORIES[engine_id] = factory


def available_ids() -> list[str]:
    return sorted(_FACTORIES.keys())


def create(engine_id: str) -> OcrEngine:
    if engine_id not in _FACTORIES:
        raise KeyError(
            f"未登録のエンジン: {engine_id!r}. 登録済み: {available_ids()}"
        )
    return _FACTORIES[engine_id]()


def resolve_ids(spec: str) -> list[str]:
    """'all' もしくはカンマ区切り指定を id リストへ。"""
    if spec.strip() == "all":
        return available_ids()
    ids = [s.strip() for s in spec.split(",") if s.strip()]
    unknown = [i for i in ids if i not in _FACTORIES]
    if unknown:
        raise KeyError(f"未登録のエンジン: {unknown}. 登録済み: {available_ids()}")
    return ids
