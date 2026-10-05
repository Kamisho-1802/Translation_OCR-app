"""OCREngine 抽象基底クラス（DESIGN.md 第7.1章）。"""

from __future__ import annotations

import io
from typing import Any, NamedTuple


class OcrError(RuntimeError):
    """OCR 実行に失敗したことを表す。"""


class OCREngine:
    """OCRエンジンの共通インターフェース。"""

    name: str = "base"

    def extract(
        self, image_bytes: bytes, lang_mode: str, block_mode: str
    ) -> list[str]:
        """block_mode='single' なら要素1個、'split' ならブロックごとの配列を返す。

        空文字・空白のみのブロックは含めない。1件も無ければ空配列。
        """
        raise NotImplementedError


def clean_blocks(blocks: list[str]) -> list[str]:
    """空文字・空白のみのブロックを除外する（DESIGN.md 第7.2章）。"""
    return [text.strip() for text in blocks if text.strip()]


# --- 検出結果を「行」にまとめる ---------------------------------------------
#
# OCRエンジンは文字のかたまりごとに結果を返すため、そのまま並べると
# 横に並んでいる文字（例: 「営業中」と「10:00-18:00」）まで改行で分かれてしまう。
# 外接矩形の縦位置が重なるものを同じ行とみなし、行が変わるときだけ改行する。

# 同じ行とみなす縦方向の重なり（小さい方の高さに対する比率）
_SAME_LINE_OVERLAP_RATIO = 0.4

# 語の間に空白を入れる横方向の間隔（行の高さに対する比率）
_WORD_GAP_RATIO = 0.25

# 「縦書きの列」とみなす縦横比（高さ ÷ 幅）
_VERTICAL_ASPECT = 1.3


class DetectedText(NamedTuple):
    """1つの検出結果。box は (x0, y0, x1, y1)。"""

    box: tuple[int, int, int, int]
    text: str


def _overlaps_vertically(a: tuple[int, int], b: tuple[int, int]) -> bool:
    """2つの縦範囲が、同じ行とみなせるだけ重なっているか。"""
    overlap = min(a[1], b[1]) - max(a[0], b[0])
    if overlap <= 0:
        return False
    shorter = min(a[1] - a[0], b[1] - b[0])
    if shorter <= 0:
        return False
    return overlap / shorter >= _SAME_LINE_OVERLAP_RATIO


def _join_line(items: list[DetectedText]) -> str:
    """1行分の検出結果を、横方向に並べて1つの文字列にする。"""
    heights = [item.box[3] - item.box[1] for item in items]
    widths = [item.box[2] - item.box[0] for item in items]
    line_height = max(heights) if heights else 0

    # 縦長の箱ばかりなら縦書きの列。日本語の縦書きは右の列から読む。
    is_vertical = all(
        h >= w * _VERTICAL_ASPECT for h, w in zip(heights, widths) if w > 0
    )
    ordered = sorted(items, key=lambda i: i.box[0], reverse=is_vertical)

    parts: list[str] = []
    previous_end: int | None = None
    for item in ordered:
        if previous_end is not None:
            gap = item.box[0] - previous_end
            # 離れているときだけ空白を入れる（隣接していれば直結する）
            if gap > line_height * _WORD_GAP_RATIO:
                parts.append(" ")
        parts.append(item.text)
        previous_end = max(previous_end or 0, item.box[2])
    return "".join(parts).strip()


def group_into_lines(items: list[DetectedText]) -> list[str]:
    """検出結果を行ごとにまとめ、行の文字列を上から順に返す。

    同じ行に並んでいるものは1つの文字列に連結し、行が変わるところで分ける。
    """
    valid = [item for item in items if item.text.strip()]
    if not valid:
        return []

    lines: list[list[DetectedText]] = []
    line_ranges: list[tuple[int, int]] = []
    for item in sorted(valid, key=lambda i: i.box[1]):
        span = (item.box[1], item.box[3])
        for index, existing in enumerate(line_ranges):
            if _overlaps_vertically(existing, span):
                lines[index].append(item)
                line_ranges[index] = (
                    min(existing[0], span[0]),
                    max(existing[1], span[1]),
                )
                break
        else:
            lines.append([item])
            line_ranges.append(span)

    # 行自体は上から下へ
    order = sorted(range(len(lines)), key=lambda i: line_ranges[i][0])
    return [text for text in (_join_line(lines[i]) for i in order) if text]


def load_image(image_bytes: bytes) -> Any:
    """画像バイト列を RGB の PIL Image にして返す（全エンジン共通の入口）。

    スマホ写真は「横向きに撮った画像を EXIF の向き情報で立てて表示している」ことが多く、
    PIL はその向きを自動適用しない。そのまま渡すと文字が90度倒れた状態でOCRにかかり、
    どのエンジンでもほぼ何も取れなくなるため、ここで必ず EXIF の向きを適用する。
    """
    from PIL import Image, ImageOps, UnidentifiedImageError

    try:
        image = Image.open(io.BytesIO(image_bytes))
        image = ImageOps.exif_transpose(image)
        return image.convert("RGB")
    except (UnidentifiedImageError, OSError) as exc:
        raise OcrError("画像を読み込めませんでした") from exc
