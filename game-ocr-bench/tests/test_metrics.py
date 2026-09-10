"""M2: 既知ペアで CER/WER・編集内訳・完全一致・固有名詞一致が手計算値と一致すること。"""

from __future__ import annotations

import pytest

from ocr_bench.eval.metrics import (
    cer,
    cer_counts,
    exact_match,
    macro_cer,
    micro_cer,
    proper_noun_accuracy,
    wer,
    wer_counts,
)
from ocr_bench.eval.normalize import normalize


# ---- 正規化 -------------------------------------------------------------
def test_normalize_strict_keeps_case_and_symbols():
    assert normalize("HP 120/200", "strict") == "HP 120/200"
    # 連続空白は潰す。
    assert normalize("HP   120", "strict") == "HP 120"


def test_normalize_loose_lowercases_and_strips_symbols_and_space():
    # "HP 120/200" -> 記号除去("/") + 小文字化 + 空白除去
    assert normalize("HP 120/200", "loose") == "hp120200"


def test_normalize_removes_illegible_marker():
    assert normalize("AB■C", "strict") == "ABC"


# ---- CER ----------------------------------------------------------------
def test_cer_single_substitution():
    # GT="EXIT"(4), pred="EXIY": 1 置換 / 4 = 0.25
    assert cer("EXIT", "EXIY", "strict") == pytest.approx(0.25)
    c = cer_counts("EXIT", "EXIY", "strict")
    assert (c.ins, c.dele, c.sub, c.ref_len) == (0, 0, 1, 4)


def test_cer_insertion_and_deletion():
    # GT="HP"(2) pred="HPX": 1 挿入 / 2 = 0.5
    assert cer("HP", "HPX", "strict") == pytest.approx(0.5)
    ci = cer_counts("HP", "HPX", "strict")
    assert (ci.ins, ci.dele, ci.sub) == (1, 0, 0)
    # GT="HPX"(3) pred="HP": 1 削除 / 3
    cd = cer_counts("HPX", "HP", "strict")
    assert (cd.ins, cd.dele, cd.sub) == (0, 1, 0)
    assert cer("HPX", "HP", "strict") == pytest.approx(1 / 3)


def test_cer_perfect_and_empty_gt():
    assert cer("EXIT", "EXIT", "strict") == 0.0
    assert cer("", "", "strict") == 0.0
    assert cer("", "junk", "strict") == 1.0  # GT 空・pred 非空 は 1.0


def test_cer_case_sensitive_strict_vs_loose():
    # strict は大小区別 → E,X,I,T の全4文字が置換 = 4/4 = 1.0
    assert cer("EXIT", "exit", "strict") == pytest.approx(1.0)
    # loose は小文字化で一致 → 0.0
    assert cer("EXIT", "exit", "loose") == 0.0


# ---- WER ----------------------------------------------------------------
def test_wer_word_level():
    # GT 3 語 / pred で 1 語置換 = 1/3
    gt = "raised her Sunstave"
    pred = "raised her Sunstaff"
    assert wer(gt, pred, "strict") == pytest.approx(1 / 3)
    w = wer_counts(gt, pred, "strict")
    assert (w.ins, w.dele, w.sub, w.ref_len) == (0, 0, 1, 3)


def test_wer_insertion():
    gt = "HP 120"
    pred = "HP 120 200"  # 1 語挿入
    assert wer(gt, pred, "strict") == pytest.approx(1 / 2)


# ---- 完全一致 / 固有名詞 -------------------------------------------------
def test_exact_match():
    assert exact_match("EXIT", "EXIT", "strict") == 1
    assert exact_match("EXIT", "EXIY", "strict") == 0
    assert exact_match("EXIT", "exit", "loose") == 1


def test_proper_noun_accuracy():
    pred = "Aelthyr raised her Sunstave"
    assert proper_noun_accuracy(pred, ["Aelthyr", "Sunstave"], "strict") == 1.0
    assert proper_noun_accuracy(pred, ["Aelthyr", "Moonstave"], "strict") == 0.5
    assert proper_noun_accuracy(pred, [], "strict") is None  # 固有名詞なしは集計除外


# ---- マイクロ / マクロ --------------------------------------------------
def test_micro_vs_macro_short_string_sensitivity():
    # 短文の事故がマクロを支配し、マイクロと乖離すること（§4.1 の根拠）。
    pairs = [
        ("HI", "XX"),            # dist 2 / len 2  -> per-sample CER 1.0
        ("A" * 100, "A" * 100),  # dist 0 / len 100 -> 0.0
    ]
    # micro = (2+0)/(2+100) = 2/102
    assert micro_cer(pairs, "strict") == pytest.approx(2 / 102)
    # macro = (1.0 + 0.0)/2 = 0.5  （短文事故が支配）
    assert macro_cer(pairs, "strict") == pytest.approx(0.5)
    assert macro_cer(pairs, "strict") > micro_cer(pairs, "strict")
