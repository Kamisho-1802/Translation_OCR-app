"""easyOCR 実装。

split は easyOCR の素の出力単位＝検出領域（行）単位をそのまま1ブロックとする
（DESIGN.md 第7.2章）。

GPU 運用（DESIGN.md 第7.4章）: モデルのロードと推論はこのモジュール内に閉じており、
OCR エンドポイントが呼ばれたときだけ GPU を使う。将来「OCR時のみGPUインスタンス起動」
へ移行する際は、この層だけを別プロセス／別ホストに切り出せばよい。
"""

from __future__ import annotations

from typing import Any

from .base import (
    DetectedText,
    OCREngine,
    OcrError,
    clean_blocks,
    group_into_lines,
    load_image,
)

# 内部表現 'ja'/'en' → easyOCR の言語リスト
_LANG = {"ja": ["ja", "en"], "en": ["en"]}

# Reader はモデルロードが重いので言語ごとに1度だけ生成して使い回す。
_readers: dict[str, Any] = {}

# これより小さい検出領域はノイズとして無視する（px）
_MIN_BOX_SIZE = 12


def _get_reader(lang_mode: str) -> Any:
    reader = _readers.get(lang_mode)
    if reader is not None:
        return reader

    try:
        import easyocr
    except ImportError as exc:  # pragma: no cover - 環境依存
        raise OcrError("easyocr がインストールされていません") from exc

    langs = _LANG.get(lang_mode)
    if langs is None:
        raise OcrError(f"未対応の言語モードです: {lang_mode}")

    try:
        import torch

        use_gpu = bool(torch.cuda.is_available())
    except ImportError:
        use_gpu = False

    try:
        reader = easyocr.Reader(langs, gpu=use_gpu)
    except Exception as exc:
        raise OcrError(f"easyOCR の初期化に失敗しました: {exc}") from exc

    _readers[lang_mode] = reader
    return reader


def release_readers() -> None:
    """ロード済みモデルを解放する（将来のGPU起動/解放運用のためのフック）。"""
    _readers.clear()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass


def _to_array(image_bytes: bytes) -> Any:
    """easyOCR が期待する RGB の numpy 配列へ変換する。"""
    import numpy as np

    return np.array(load_image(image_bytes))


def _poly_to_box(poly: Any) -> tuple[int, int, int, int]:
    """easyOCR が返す4点ポリゴンを外接矩形 (x0, y0, x1, y1) にする。"""
    xs = [int(point[0]) for point in poly]
    ys = [int(point[1]) for point in poly]
    return (min(xs), min(ys), max(xs), max(ys))


def detect_text_boxes(image: Any, lang_mode: str) -> list[tuple[int, int, int, int]]:
    """CRAFT による文字領域の検出だけを行い、(x0, y0, x1, y1) の列を返す。

    検出（CRAFT）は写真でも安定して当たるので、認識が弱いエンジン
    （manga-ocr は領域を渡す前提の認識器）から共用できるように切り出してある。
    """
    import numpy as np

    reader = _get_reader(lang_mode)
    try:
        horizontal, _free = reader.detect(
            np.asarray(image), text_threshold=0.5, low_text=0.3
        )
    except Exception as exc:
        raise OcrError(f"文字領域の検出に失敗しました: {exc}") from exc

    boxes: list[tuple[int, int, int, int]] = []
    for group in horizontal or []:
        for box in group:
            x0, x1, y0, y1 = (int(box[0]), int(box[1]), int(box[2]), int(box[3]))
            if x1 - x0 < _MIN_BOX_SIZE or y1 - y0 < _MIN_BOX_SIZE:
                continue  # ノイズ由来の極小領域は捨てる
            boxes.append((x0, y0, x1, y1))
    return boxes


class EasyOcrEngine(OCREngine):
    """easyOCR（CRAFT検出 + CRNN認識）。"""

    name = "easyocr"

    def extract(
        self, image_bytes: bytes, lang_mode: str, block_mode: str
    ) -> list[str]:
        reader = _get_reader(lang_mode)
        image = _to_array(image_bytes)

        try:
            detections = reader.readtext(image, detail=1)
        except Exception as exc:
            raise OcrError(f"easyOCR の実行に失敗しました: {exc}") from exc

        # detail=1 は (bbox, text, confidence) のタプル列。
        # 検出は文字のかたまり単位なので、横に並んでいるものは同じ行にまとめる。
        items = [
            DetectedText(_poly_to_box(det[0]), str(det[1]))
            for det in detections
            if len(det) > 1
        ]
        lines = group_into_lines(items)

        if block_mode == "single":
            return clean_blocks(["\n".join(lines)])
        return clean_blocks(lines)
