"""外部エンジン不要の単体テスト（前処理・ハッシュ・DB・キャッシュ照会）。"""

from __future__ import annotations

import numpy as np

from ocr_bench.core.hashing import stable_hash
from ocr_bench.preprocess.pipeline import apply_pipeline, available_ops


def test_stable_hash_is_order_independent():
    a = {"psm": 7, "oem": 3, "mode": "fullscreen"}
    b = {"mode": "fullscreen", "oem": 3, "psm": 7}
    assert stable_hash(a) == stable_hash(b)


def test_stable_hash_changes_on_value():
    assert stable_hash({"psm": 7}) != stable_hash({"psm": 6})


def test_available_ops_includes_game_specific():
    ops = available_ops()
    for name in ["raw", "upscale_nearest", "auto_invert", "color_key", "gray_otsu"]:
        assert name in ops


def test_pipeline_raw_is_identity():
    img = np.full((20, 40, 3), 128, dtype=np.uint8)
    out, ms = apply_pipeline(img, ["raw"])
    assert np.array_equal(out, img)
    assert ms >= 0


def test_pipeline_auto_invert_on_dark_background():
    # 暗背景（平均輝度 < 127）は反転されて明るくなるはず。
    img = np.full((20, 40, 3), 10, dtype=np.uint8)
    out, _ = apply_pipeline(img, ["auto_invert"])
    assert float(out.mean()) > 127.0


def test_pipeline_upscale_nearest_scales():
    img = np.zeros((10, 10, 3), dtype=np.uint8)
    out, _ = apply_pipeline(img, [{"op": "upscale_nearest", "params": {"scale": 3}}])
    assert out.shape[0] == 30 and out.shape[1] == 30


def test_pipeline_chain_order():
    # auto_invert -> upscale_nearest -> gray_otsu が例外なく通り、単チャンネルになる。
    img = np.full((16, 32, 3), 20, dtype=np.uint8)
    out, _ = apply_pipeline(img, ["auto_invert", "upscale_nearest", "gray_otsu"])
    assert out.ndim == 2  # 二値化でグレー単チャンネル
