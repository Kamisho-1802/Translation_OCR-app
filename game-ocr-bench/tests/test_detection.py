"""M4: 検出評価（IoU / Recall / Precision / 誤検出テキスト量）の単体テスト。"""

from __future__ import annotations

import pytest

from ocr_bench.eval.detection import (
    detection_scores,
    iou,
    merge_boxes_into_lines,
    spurious_char_count,
)


def test_merge_word_boxes_into_one_line():
    # 同じ行の 2 単語（縦が揃う）-> 1 行ボックスに統合。
    words = [(10, 10, 40, 20), (60, 12, 50, 18)]
    lines = merge_boxes_into_lines(words)
    assert len(lines) == 1
    assert lines[0] == (10, 10, 100, 20)  # x:10..110, y:10..30


def test_merge_keeps_separate_lines():
    words = [(10, 10, 40, 20), (10, 100, 40, 20)]  # 別の行
    assert len(merge_boxes_into_lines(words)) == 2


def test_merge_makes_wordlevel_match_region():
    # 単語ボックスを統合すると行レベル GT 領域と IoU>=0.5 で対応する。
    region = [(10, 10, 100, 22)]
    words = [(10, 10, 40, 20), (60, 12, 50, 18)]
    merged = merge_boxes_into_lines(words)
    s = detection_scores(region, merged)
    assert s.recall == 1.0 and s.precision == 1.0


def test_iou_identical_and_disjoint():
    assert iou((0, 0, 10, 10), (0, 0, 10, 10)) == pytest.approx(1.0)
    assert iou((0, 0, 10, 10), (100, 100, 10, 10)) == 0.0


def test_iou_half_overlap():
    # 10x10 と、x=5 ずらした 10x10 -> 交差 5x10=50, 和 200-50=150 -> 1/3
    assert iou((0, 0, 10, 10), (5, 0, 10, 10)) == pytest.approx(50 / 150)


def test_detection_perfect():
    gt = [(0, 0, 10, 10), (100, 0, 10, 10)]
    pred = [(0, 0, 10, 10), (100, 0, 10, 10)]
    s = detection_scores(gt, pred)
    assert s.recall == 1.0 and s.precision == 1.0 and s.matched == 2


def test_detection_missed_one():
    gt = [(0, 0, 10, 10), (100, 0, 10, 10)]
    pred = [(0, 0, 10, 10)]  # 2つ目を見落とし
    s = detection_scores(gt, pred)
    assert s.recall == pytest.approx(0.5)   # 1/2 GT
    assert s.precision == pytest.approx(1.0)  # 1/1 pred


def test_detection_false_positive():
    gt = [(0, 0, 10, 10)]
    pred = [(0, 0, 10, 10), (500, 500, 10, 10)]  # 余分な検出
    s = detection_scores(gt, pred)
    assert s.recall == pytest.approx(1.0)
    assert s.precision == pytest.approx(0.5)  # 1/2 pred が対応


def test_detection_below_threshold_not_matched():
    # IoU 1/3 < 0.5 -> 未対応
    gt = [(0, 0, 10, 10)]
    pred = [(5, 0, 10, 10)]
    s = detection_scores(gt, pred, iou_thresh=0.5)
    assert s.matched == 0 and s.recall == 0.0 and s.precision == 0.0


def test_detection_greedy_one_to_one():
    # 2 予測が同じ GT に被っても、対応は 1 つだけ（1:1）。
    gt = [(0, 0, 10, 10)]
    pred = [(0, 0, 10, 10), (1, 0, 10, 10)]
    s = detection_scores(gt, pred)
    assert s.matched == 1 and s.recall == 1.0 and s.precision == pytest.approx(0.5)


def test_spurious_chars_counts_outside_gt_only():
    gt = [(0, 0, 100, 20)]
    blocks = [
        ("HP 120/200", (0, 0, 100, 20)),   # GT 内 -> 数えない
        ("l1I", (500, 500, 30, 10)),        # GT 外 -> 3 文字
        ("noise", (600, 600, 40, 10)),      # GT 外 -> 5 文字
    ]
    # 空白除去後の文字数: 3 + 5 = 8
    assert spurious_char_count(gt, blocks) == 8


def test_spurious_chars_center_inside_is_not_spurious():
    gt = [(0, 0, 100, 100)]
    # IoU は小さいが中心が GT 内 -> 誤検出に数えない
    blocks = [("x", (40, 40, 5, 5))]
    assert spurious_char_count(gt, blocks) == 0
