"""GPU レイテンシ計測の共通ヘルパー（仕様書 §4.4）。

GPU 使用エンジンは非同期実行のため、計測前後で同期を取らないと不当に速く出る。
torch が無い/CPU のときは同期を no-op にする。
"""

from __future__ import annotations

import time
from contextlib import contextmanager


def _sync() -> None:
    # torch（EasyOCR）側の同期。
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.synchronize()
    except Exception:
        pass
    # paddle（PaddleOCR）側の同期。torch とは別の CUDA コンテキストを持つ。
    try:
        import paddle

        if paddle.device.is_compiled_with_cuda():
            paddle.device.cuda.synchronize()
    except Exception:
        pass


@contextmanager
def measure_latency_ms(sink: dict, key: str = "latency_ms"):
    """with ブロックの実測ミリ秒を sink[key] に格納する（前後で CUDA 同期）。"""
    _sync()
    t0 = time.perf_counter()
    try:
        yield
    finally:
        _sync()
        sink[key] = int((time.perf_counter() - t0) * 1000)
