"""前処理の個別オペレーション（仕様書 §3.3）。

各 op は BGR np.ndarray を受け取り、加工後の np.ndarray を返す純粋関数。
二値化系はグレー（単チャンネル）を返すことがあるが、アダプタ側で吸収する。
前処理は「エンジンの一部ではなく実験条件」として扱う（§3.3）。
"""

from __future__ import annotations

import cv2
import numpy as np


def _to_gray(image: np.ndarray) -> np.ndarray:
    if image.ndim == 2:
        return image
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def _to_bgr(image: np.ndarray) -> np.ndarray:
    if image.ndim == 2:
        return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    return image


def raw(image: np.ndarray, **_: object) -> np.ndarray:
    """無加工（ベースライン）。"""
    return image


def upscale_lanczos(image: np.ndarray, scale: float = 2.0, **_: object) -> np.ndarray:
    """Lanczos 拡大。一般フォント向け。"""
    return cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_LANCZOS4)


def upscale_nearest(image: np.ndarray, scale: float = 3.0, **_: object) -> np.ndarray:
    """最近傍拡大。ピクセルフォント専用（Lanczos だとドットが滲む）。"""
    return cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST)


def gray_otsu(image: np.ndarray, **_: object) -> np.ndarray:
    """グレースケール + Otsu 二値化。高コントラスト UI 向け。"""
    gray = _to_gray(image)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return binary


def gray_adaptive(
    image: np.ndarray, block_size: int = 31, c: int = 10, **_: object
) -> np.ndarray:
    """適応二値化。背景にグラデーションがある場合。"""
    gray = _to_gray(image)
    block_size = block_size if block_size % 2 == 1 else block_size + 1
    return cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        block_size,
        c,
    )


def auto_invert(image: np.ndarray, **_: object) -> np.ndarray:
    """平均輝度が暗ければ反転。暗背景・明文字 UI に必須。

    OCR は概ね「暗文字・明背景」を前提とするため、暗背景画像を反転して揃える。
    """
    gray = _to_gray(image)
    if float(gray.mean()) < 127.0:
        return cv2.bitwise_not(image)
    return image


def clahe(image: np.ndarray, clip: float = 2.0, grid: int = 8, **_: object) -> np.ndarray:
    """局所コントラスト強調。半透明パネル上の文字向け。"""
    gray = _to_gray(image)
    op = cv2.createCLAHE(clipLimit=clip, tileGridSize=(grid, grid))
    return op.apply(gray)


def morph_close(image: np.ndarray, ksize: int = 2, **_: object) -> np.ndarray:
    """モルフォロジー closing。縁取りで分断された字画の接続。"""
    kernel = np.ones((ksize, ksize), np.uint8)
    return cv2.morphologyEx(image, cv2.MORPH_CLOSE, kernel)


# pipeline から名前引きするための一覧（color_key は colorkey.py 側で登録）。
OPS = {
    "raw": raw,
    "upscale_lanczos": upscale_lanczos,
    "upscale_nearest": upscale_nearest,
    "gray_otsu": gray_otsu,
    "gray_adaptive": gray_adaptive,
    "auto_invert": auto_invert,
    "clahe": clahe,
    "morph_close": morph_close,
}
