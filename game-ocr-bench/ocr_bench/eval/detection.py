"""検出評価（仕様書 §4.2 検出 Recall/Precision, §4.3 誤検出テキスト量）。

fullscreen モードで、GT 領域（regions[].box）と予測ボックス（blocks[].box）を
IoU で対応付けて検出性能を測る。認識性能（CER 等）とは独立に「見つけられたか」を
見るための指標。box は (x, y, w, h)。
"""

from __future__ import annotations

from dataclasses import dataclass


def iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    """2 矩形 (x,y,w,h) の IoU。"""
    ax0, ay0, aw, ah = a
    bx0, by0, bw, bh = b
    ax1, ay1 = ax0 + aw, ay0 + ah
    bx1, by1 = bx0 + bw, by0 + bh
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    iw, ih = max(0, ix1 - ix0), max(0, iy1 - iy0)
    inter = iw * ih
    if inter == 0:
        return 0.0
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


def _center_in(box: tuple[int, int, int, int], outer: tuple[int, int, int, int]) -> bool:
    x, y, w, h = box
    cx, cy = x + w / 2, y + h / 2
    ox, oy, ow, oh = outer
    return ox <= cx <= ox + ow and oy <= cy <= oy + oh


def merge_boxes_into_lines(
    boxes: list[tuple[int, int, int, int]], overlap_ratio: float = 0.5
) -> list[tuple[int, int, int, int]]:
    """単語レベルのボックスを行レベルに統合する（検出評価の粒度合わせ）。

    Tesseract は単語ごと、EasyOCR/PaddleOCR は行ごとにボックスを返すため、粒度が
    揃わないと IoU 比較が不当になる。縦方向の重なりが大きいボックス同士を同一行と見なし、
    外接矩形に統合する。既に行単位のエンジンでは概ね恒等変換になる。
    """
    if not boxes:
        return []
    remaining = sorted(boxes, key=lambda b: (b[1], b[0]))
    lines: list[list[int]] = []  # [x0,y0,x1,y1]
    for x, y, w, h in remaining:
        x1, y1 = x + w, y + h
        placed = False
        for ln in lines:
            ly0, ly1 = ln[1], ln[3]
            inter = min(y1, ly1) - max(y, ly0)
            smaller_h = min(y1 - y, ly1 - ly0)
            if smaller_h > 0 and inter / smaller_h >= overlap_ratio:
                ln[0], ln[1] = min(ln[0], x), min(ln[1], y)
                ln[2], ln[3] = max(ln[2], x1), max(ln[3], y1)
                placed = True
                break
        if not placed:
            lines.append([x, y, x1, y1])
    return [(l[0], l[1], l[2] - l[0], l[3] - l[1]) for l in lines]


@dataclass
class DetectionScore:
    recall: float
    precision: float
    matched: int
    n_gt: int
    n_pred: int


def detection_scores(
    gt_boxes: list[tuple[int, int, int, int]],
    pred_boxes: list[tuple[int, int, int, int]],
    iou_thresh: float = 0.5,
) -> DetectionScore:
    """IoU>=閾値 で GT と予測を貪欲に 1:1 対応付け、Recall/Precision を返す。

    Recall    = 対応が付いた GT 数 / GT 数
    Precision = 対応が付いた 予測数 / 予測数
    """
    n_gt, n_pred = len(gt_boxes), len(pred_boxes)
    if n_gt == 0 and n_pred == 0:
        return DetectionScore(1.0, 1.0, 0, 0, 0)

    # (iou, gt_idx, pred_idx) を大きい順に貪欲マッチ。
    pairs = []
    for gi, g in enumerate(gt_boxes):
        for pi, p in enumerate(pred_boxes):
            v = iou(g, p)
            if v >= iou_thresh:
                pairs.append((v, gi, pi))
    pairs.sort(reverse=True)

    used_gt: set[int] = set()
    used_pred: set[int] = set()
    for _v, gi, pi in pairs:
        if gi in used_gt or pi in used_pred:
            continue
        used_gt.add(gi)
        used_pred.add(pi)

    matched = len(used_gt)
    recall = matched / n_gt if n_gt else (1.0 if n_pred == 0 else 0.0)
    precision = matched / n_pred if n_pred else (1.0 if n_gt == 0 else 0.0)
    return DetectionScore(recall, precision, matched, n_gt, n_pred)


def spurious_char_count(
    gt_boxes: list[tuple[int, int, int, int]],
    pred_blocks: list[tuple[str, tuple[int, int, int, int] | None]],
    iou_thresh: float = 0.5,
) -> int:
    """GT 領域外から出力された文字数（誤検出テキスト量・§4.3）。

    予測ブロックが「どの GT 領域とも IoU>=閾値 で対応せず、中心も GT 領域内に無い」
    とき、そのブロックのテキスト（空白除く）の文字数を誤検出として数える。
    背景テクスチャを文字と誤認した量を、認識誤り（CER）とは別に測るための指標。
    """
    total = 0
    for text, box in pred_blocks:
        if box is None:
            continue
        matched = any(
            iou(g, box) >= iou_thresh or _center_in(box, g) for g in gt_boxes
        )
        if not matched:
            total += len("".join((text or "").split()))
    return total
