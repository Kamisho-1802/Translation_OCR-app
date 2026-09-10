"""画像 I/O とハッシュ（仕様書 §7 規約・§12 PNG 必須化）。

画像は BGR の np.ndarray で受け渡す。ファイル I/O を繰り返さない方針のため、
読み込みは一度だけ行い ndarray を回す。
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import cv2
import numpy as np


def sha256_of_file(path: str | Path) -> str:
    """ファイル内容の SHA-256（samples.image_sha256 用）。"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_of_array(image: np.ndarray) -> str:
    """ndarray の内容ハッシュ（キャッシュキー用）。"""
    arr = np.ascontiguousarray(image)
    return hashlib.sha256(arr.tobytes()).hexdigest()


def is_png(path: str | Path) -> bool:
    """PNG シグネチャで判定（拡張子ではなく中身で検証・§12）。"""
    sig = b"\x89PNG\r\n\x1a\n"
    with open(path, "rb") as f:
        return f.read(len(sig)) == sig


def load_bgr(path: str | Path, require_png: bool = True) -> np.ndarray:
    """画像を BGR で読み込む。

    require_png=True のとき、PNG でなければ ValueError（JPEG 圧縮ノイズの混入防止）。
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    if require_png and not is_png(path):
        raise ValueError(
            f"{path} は PNG ではありません。収集規約により PNG（ロスレス）が必須です。"
        )
    # 日本語パス対策で imread ではなく imdecode を使う。
    data = np.fromfile(str(path), dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)  # 常に 3ch BGR
    if image is None:
        raise ValueError(f"{path} を画像としてデコードできませんでした。")
    return image


def crop(image: np.ndarray, box: list[int] | tuple[int, int, int, int]) -> np.ndarray:
    """[x, y, w, h] で切り出し。範囲は画像内にクリップする。"""
    x, y, w, h = (int(v) for v in box)
    ih, iw = image.shape[:2]
    x0 = max(0, min(x, iw))
    y0 = max(0, min(y, ih))
    x1 = max(0, min(x + w, iw))
    y1 = max(0, min(y + h, ih))
    return image[y0:y1, x0:x1]
