"""前処理パイプライン（仕様書 §3.3）。

複数 op を順に適用する。条件は組み合わせ可能（例: auto_invert + upscale_nearest + gray_otsu）。
前処理時間を計測して返す（レイテンシは前処理を含む/含まないの両方を記録する・§4.4）。

前処理条件の表現:
    ["auto_invert", "upscale_nearest"]            # op 名のみ
    [{"op": "upscale_nearest", "params": {"scale": 4}}]  # パラメータ付き
    "raw" / "tuned"                                # 名前付きプリセット（config で解決）
"""

from __future__ import annotations

import time
from typing import Any

import numpy as np

from .colorkey import color_key
from .ops import OPS


def _color_key_step(image, preset=None, ranges=None, invert=True, **_):
    """color_key の薄いラッパ。preset 名を colorkeys.yaml の HSV 色域へ解決する。

    使い方: {op: color_key, params: {preset: yellow}} または明示 ranges。
    """
    if preset and not ranges:
        from ..core import config as cfg

        ranges = cfg.colorkeys().get(preset)
    return color_key(image, ranges=ranges, invert=invert)


# 全 op 名 -> 関数
_ALL_OPS = {**OPS, "color_key": _color_key_step}


def available_ops() -> list[str]:
    return sorted(_ALL_OPS.keys())


def _normalize_steps(steps: Any) -> list[dict]:
    """多様な入力表現を [{"op": name, "params": {...}}, ...] に正規化する。"""
    if steps is None:
        return [{"op": "raw", "params": {}}]
    if isinstance(steps, str):
        steps = [steps]
    normalized: list[dict] = []
    for step in steps:
        if isinstance(step, str):
            normalized.append({"op": step, "params": {}})
        elif isinstance(step, dict):
            normalized.append({"op": step["op"], "params": step.get("params", {})})
        else:
            raise TypeError(f"未対応の前処理ステップ表現: {step!r}")
    return normalized


def apply_pipeline(image: np.ndarray, steps: Any) -> tuple[np.ndarray, int]:
    """steps を順に適用し、(結果画像, 前処理ミリ秒) を返す。"""
    normalized = _normalize_steps(steps)
    t0 = time.perf_counter()
    out = image
    for step in normalized:
        op_name = step["op"]
        if op_name not in _ALL_OPS:
            raise KeyError(
                f"未知の前処理 op: {op_name!r}. 利用可能: {available_ops()}"
            )
        out = _ALL_OPS[op_name](out, **step["params"])
    preprocess_ms = int((time.perf_counter() - t0) * 1000)
    return out, preprocess_ms
