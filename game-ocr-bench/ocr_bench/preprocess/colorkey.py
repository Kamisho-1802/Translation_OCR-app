"""色キーイング前処理（仕様書 §3.3・ゲーム特化）。

ゲーム UI の文字色は固定されがち（白本文・黄ハイライト・赤ダメージ）。
HSV で対象色域だけを抽出すると背景テクスチャを丸ごと排除できる。
汎用手法ではなく「効く場面が明確な特化手法」として扱い、text_color タグ別に
プリセット（config/colorkeys.yaml）を持たせる。
"""

from __future__ import annotations

import cv2
import numpy as np


def color_key(
    image: np.ndarray,
    ranges: list[dict] | None = None,
    invert: bool = True,
    **_: object,
) -> np.ndarray:
    """指定 HSV 色域を抽出して二値化する。

    ranges: [{"lo": [h,s,v], "hi": [h,s,v]}, ...]。複数域は OR で合成する。
            白のように色相全域に跨る場合は複数レンジで表現する。
    invert: True で「文字=黒・背景=白」に整える（多くの OCR の前提に合わせる）。
    ranges が None のときは無加工で返す（未定義色は落とさない安全側）。
    """
    if not ranges:
        return image

    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    mask = np.zeros(hsv.shape[:2], dtype=np.uint8)
    for rng in ranges:
        lo = np.array(rng["lo"], dtype=np.uint8)
        hi = np.array(rng["hi"], dtype=np.uint8)
        mask = cv2.bitwise_or(mask, cv2.inRange(hsv, lo, hi))

    # mask: 対象色=255（白）。invert で文字=黒・背景=白へ。
    return cv2.bitwise_not(mask) if invert else mask
