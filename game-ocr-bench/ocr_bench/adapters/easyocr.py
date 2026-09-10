"""EasyOCR アダプタ（仕様書 §3.1 / §3.2）。CRAFT 検出 + CRNN 認識。GPU 使用。

アダプタは独自前処理を行わない（§7）。前処理済み画像を受け取る。
EasyOCR の内部モデルは RGB を前提とするため、3ch BGR は RGB へ変換して渡す
（2ch グレースケールはそのまま）。レイテンシは CUDA 同期込みで計測（§4.4）。

Reader はモデルロードが重いので **エンジンインスタンスごとに 1 度だけ生成して使い回す**。
sweep で認識パラメータ（text_threshold など）は readtext 呼び出し時に渡せるので、
Reader の再生成は不要。
"""

from __future__ import annotations

import cv2
import numpy as np

from ..core.registry import register
from ..core.types import Box, OcrResult, TextBlock
from ._gpu import measure_latency_ms

_ENGINE_ID = "easyocr"

# readtext に渡せる認識/検出パラメータ（§3.2 sweep 対象）。
_READTEXT_KEYS = (
    "text_threshold",
    "low_text",
    "link_threshold",
    "mag_ratio",
    "contrast_ths",
    "adjust_contrast",
    "canvas_size",
    "slope_ths",
    "ycenter_ths",
    "height_ths",
    "width_ths",
    "add_margin",
    "decoder",
    "beamWidth",
    "batch_size",
)


def _poly_to_box(poly) -> Box:
    xs = [int(p[0]) for p in poly]
    ys = [int(p[1]) for p in poly]
    x0, y0 = min(xs), min(ys)
    return Box(x0, y0, max(xs) - x0, max(ys) - y0)


class EasyOcrEngine:
    id = _ENGINE_ID

    def __init__(self, gpu: bool = True, lang: list[str] | None = None) -> None:
        import easyocr  # 遅延 import

        self._reader = easyocr.Reader(lang or ["en"], gpu=gpu)
        self._gpu = gpu

    def warmup(self) -> None:
        dummy = np.full((32, 96, 3), 255, dtype=np.uint8)
        try:
            self._reader.readtext(dummy, detail=1)
        except Exception:
            pass

    @staticmethod
    def _to_rgb(image: np.ndarray) -> np.ndarray:
        if image.ndim == 2:
            return image  # グレースケールはそのまま
        return cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

    def recognize(self, image: np.ndarray, options: dict) -> OcrResult:
        mode = options.get("mode", "fullscreen")
        paragraph = bool(options.get("paragraph", False))
        rt_kwargs = {k: options[k] for k in _READTEXT_KEYS if k in options}

        try:
            img = self._to_rgb(image)
            timing: dict = {}
            with measure_latency_ms(timing):
                detections = self._reader.readtext(
                    img, detail=1, paragraph=paragraph, **rt_kwargs
                )

            blocks: list[TextBlock] = []
            texts: list[str] = []
            for det in detections:
                # detail=1: paragraph=False -> (bbox, text, conf) / True -> (bbox, text)
                poly = det[0]
                text = det[1]
                conf = float(det[2]) if len(det) > 2 else None
                texts.append(text)
                blocks.append(TextBlock(text=text, box=_poly_to_box(poly), confidence=conf))

            return OcrResult(
                engine_id=self.id,
                mode=mode,
                text=" ".join(texts),
                blocks=blocks,
                latency_ms=timing["latency_ms"],
                preprocess_ms=0,
                raw={"paragraph": paragraph, "readtext_kwargs": rt_kwargs},
            )
        except Exception as exc:  # noqa: BLE001 — 1 エンジンの失敗で全体を止めない
            return OcrResult(
                engine_id=self.id, mode=mode, text="", blocks=[],
                latency_ms=0, preprocess_ms=0, raw={}, error=f"{type(exc).__name__}: {exc}",
            )


def _factory() -> EasyOcrEngine:
    from ..core import config as cfg

    base = cfg.engine_base_options(_ENGINE_ID)
    return EasyOcrEngine(gpu=bool(base.get("gpu", True)))


# ライブラリが実際に import 可能なときだけ登録する（未導入エンジンを all から除外）。
import importlib.util as _ilu  # noqa: E402

if _ilu.find_spec("easyocr") is not None:
    register(_ENGINE_ID, _factory)
