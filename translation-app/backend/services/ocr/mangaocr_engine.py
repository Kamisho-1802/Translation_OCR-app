"""manga-ocr 実装（日本語専用）。

manga-ocr は「1つの文字領域を読む」認識器で、検出器を持たない。画像全体を渡すと
文章を捏造する（ハルシネーション）ため、必ず文字領域を切り出してから渡す。
検出には easyOCR の CRAFT を流用する（写真でも領域検出は安定して当たるため）。

縦書きにネイティブ対応しており、看板やポスターのデザイン書体にも強い。
Tesseract / easyOCR が苦手な「縦書きの看板」を読むために追加したエンジン。
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
from .easyocr_engine import detect_text_boxes

# 日本語専用モデル。英語画像には使わない。
SUPPORTED_LANG_MODES = frozenset({"ja"})

# 切り出しのはみ出し量（短辺に対する比率）。
# 実写の看板で 0 / 0.02 / 0.04 / 0.08 / 0.12 を比べたところ、余白を取りすぎると
# 周囲の模様を拾って誤読が増えた（「キクチ美容室」→「キクチ美容里」）。
# 文字が縁で切れるのも困るので、ごく薄く付ける。
_CROP_PADDING_RATIO = 0.02

# モデルのロードは重いので1度だけ生成して使い回す。
_model: Any = None


def _get_model() -> Any:
    global _model
    if _model is not None:
        return _model

    try:
        from manga_ocr import MangaOcr
    except ImportError as exc:  # pragma: no cover - 環境依存
        raise OcrError(
            "manga-ocr がインストールされていません（pip install manga-ocr）"
        ) from exc

    try:
        _model = MangaOcr()
    except Exception as exc:
        raise OcrError(f"manga-ocr の初期化に失敗しました: {exc}") from exc
    return _model


def release_model() -> None:
    """ロード済みモデルを解放する（GPU運用のためのフック）。"""
    global _model
    _model = None
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass


def _reading_order(
    boxes: list[tuple[int, int, int, int]], line_tolerance: int
) -> list[tuple[int, int, int, int]]:
    """おおまかな読み順（上から下、同じ高さなら左から右）に並べ替える。

    line_tolerance は「同じ行とみなす縦方向のズレ」。
    """
    return sorted(boxes, key=lambda b: (b[1] // max(1, line_tolerance), b[0]))


class MangaOcrEngine(OCREngine):
    """manga-ocr（日本語特化・縦書き対応）。"""

    name = "mangaocr"

    def extract(
        self, image_bytes: bytes, lang_mode: str, block_mode: str
    ) -> list[str]:
        if lang_mode not in SUPPORTED_LANG_MODES:
            raise OcrError("manga-ocr は日本語専用です")

        image = load_image(image_bytes)
        boxes = detect_text_boxes(image, lang_mode)
        if not boxes:
            return []

        model = _get_model()
        line_tolerance = max(8, image.height // 40)

        items: list[DetectedText] = []
        for x0, y0, x1, y1 in _reading_order(boxes, line_tolerance):
            pad = int(min(x1 - x0, y1 - y0) * _CROP_PADDING_RATIO)
            crop = image.crop(
                (
                    max(0, x0 - pad),
                    max(0, y0 - pad),
                    min(image.width, x1 + pad),
                    min(image.height, y1 + pad),
                )
            )
            try:
                text = str(model(crop)).strip()
            except Exception as exc:
                raise OcrError(f"manga-ocr の実行に失敗しました: {exc}") from exc
            # 隣り合う領域で同じ文字列が出たら（領域の重なり）1つにまとめる
            if text and (not items or items[-1].text != text):
                items.append(DetectedText((x0, y0, x1, y1), text))

        # 横に並んでいる領域は同じ行にまとめ、行が変わるところだけ改行する
        lines = group_into_lines(items)

        if block_mode == "single":
            return clean_blocks(["\n".join(lines)])
        return clean_blocks(lines)
