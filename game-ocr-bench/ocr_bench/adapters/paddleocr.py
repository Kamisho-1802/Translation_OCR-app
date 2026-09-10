"""PaddleOCR アダプタ（仕様書 §3.1 / §3.2）。PP-OCRv4（en）。GPU 使用。

PaddleOCR は検出パラメータ（det_db_thresh 等）を**コンストラクタ**で受け取るため、
sweep でこれらを振るには内部の PaddleOCR インスタンスをパラメータ組ごとに作り直す
必要がある。認識のたびに毎回ロードすると遅いので、**det パラメータの組をキーに
インスタンスをキャッシュ**して使い回す（recognize(options) の共通インターフェースは維持）。

画像は BGR で渡す（PaddleOCR は cv2 前提）。2ch グレースケールは 3ch へ拡張する。
本アダプタは PaddleOCR 2.7〜2.8 系の古典 API（ocr.ocr(img, cls=...)）を前提とする。
"""

from __future__ import annotations

import cv2
import numpy as np

from ..core.registry import register
from ..core.types import Box, OcrResult, TextBlock
from ._gpu import measure_latency_ms

_ENGINE_ID = "paddleocr"

# PaddleOCR コンストラクタに渡す（インスタンスを分けるべき）検出系パラメータ。
_CTOR_DET_KEYS = (
    "det_db_thresh",
    "det_db_box_thresh",
    "det_db_unclip_ratio",
    "det_limit_side_len",
    "det_limit_type",
)


def _poly_to_box(poly) -> Box:
    xs = [int(p[0]) for p in poly]
    ys = [int(p[1]) for p in poly]
    x0, y0 = min(xs), min(ys)
    return Box(x0, y0, max(xs) - x0, max(ys) - y0)


class PaddleOcrEngine:
    id = _ENGINE_ID

    def __init__(self, base: dict) -> None:
        import paddleocr  # 遅延 import（登録時に未インストールでも落ちない）

        self._paddleocr = paddleocr
        self._base = dict(base)
        self._instances: dict[tuple, object] = {}

    def _instance_for(self, options: dict):
        det = {k: options[k] for k in _CTOR_DET_KEYS if k in options}
        key = tuple(sorted(det.items()))
        if key not in self._instances:
            kwargs = {
                "lang": self._base.get("lang", "en"),
                "use_angle_cls": bool(self._base.get("use_angle_cls", True)),
                "use_gpu": bool(self._base.get("use_gpu", True)),
                "show_log": False,
                **det,
            }
            self._instances[key] = self._paddleocr.PaddleOCR(**kwargs)
        return self._instances[key]

    def warmup(self) -> None:
        dummy = np.full((32, 96, 3), 255, dtype=np.uint8)
        try:
            self._instance_for(self._base).ocr(dummy, cls=True)
        except Exception:
            pass

    @staticmethod
    def _to_bgr3(image: np.ndarray) -> np.ndarray:
        if image.ndim == 2:
            return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        return image

    def recognize(self, image: np.ndarray, options: dict) -> OcrResult:
        mode = options.get("mode", "fullscreen")
        use_cls = bool(self._base.get("use_angle_cls", True))
        try:
            ocr = self._instance_for(options)
            img = self._to_bgr3(image)
            timing: dict = {}
            with measure_latency_ms(timing):
                result = ocr.ocr(img, cls=use_cls)

            blocks: list[TextBlock] = []
            texts: list[str] = []
            # result: [page] で page は [ [box, (text, conf)], ... ]。None のこともある。
            page = result[0] if result and result[0] is not None else []
            for line in page:
                poly, (text, conf) = line[0], line[1]
                texts.append(text)
                blocks.append(
                    TextBlock(text=text, box=_poly_to_box(poly), confidence=float(conf))
                )

            return OcrResult(
                engine_id=self.id,
                mode=mode,
                text=" ".join(texts),
                blocks=blocks,
                latency_ms=timing["latency_ms"],
                preprocess_ms=0,
                raw={"det": {k: options[k] for k in _CTOR_DET_KEYS if k in options}},
            )
        except Exception as exc:  # noqa: BLE001
            return OcrResult(
                engine_id=self.id, mode=mode, text="", blocks=[],
                latency_ms=0, preprocess_ms=0, raw={}, error=f"{type(exc).__name__}: {exc}",
            )


def _factory() -> PaddleOcrEngine:
    from ..core import config as cfg

    return PaddleOcrEngine(base=cfg.engine_base_options(_ENGINE_ID))


# PaddleOCR は現状保留（未導入）。import 可能になった時点で自動登録される。
import importlib.util as _ilu  # noqa: E402

if _ilu.find_spec("paddleocr") is not None:
    register(_ENGINE_ID, _factory)
