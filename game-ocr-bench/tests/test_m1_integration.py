"""M1 統合テスト: 合成画像を raw/tuned で認識し DB 保存 → 再実行でキャッシュ命中。

Tesseract バイナリが無い環境では skip する（コードは通るが認識結果は空/error）。
"""

from __future__ import annotations

import shutil

import numpy as np
import pytest

from ocr_bench.core.db import connect

pytest.importorskip("pytesseract")
import ocr_bench.adapters  # noqa: E402,F401  登録
from ocr_bench.runner.runner import run_single  # noqa: E402

_HAS_TESSERACT = shutil.which("tesseract") is not None


def _write_synth(path):
    import cv2

    img = np.full((120, 480, 3), 18, dtype=np.uint8)
    cv2.putText(img, "HP 120/200", (20, 75), cv2.FONT_HERSHEY_SIMPLEX, 1.6,
                (245, 245, 245), 3, cv2.LINE_AA)
    ok, buf = cv2.imencode(".png", img)
    buf.tofile(str(path))


@pytest.mark.skipif(not _HAS_TESSERACT, reason="tesseract バイナリ未インストール")
def test_run_stores_result_and_caches(tmp_path):
    img_path = tmp_path / "0001.png"
    _write_synth(img_path)
    conn = connect(tmp_path / "bench.sqlite")

    for preset in ["raw", "tuned"]:
        r = run_single(conn, engine_id="tesseract", image_path=img_path,
                       mode="fullscreen", preprocess=preset)
        assert r["cached"] is False
        assert r["result_id"] > 0

    # results が 2 行（raw / tuned）保存されている。
    n = conn.execute("SELECT COUNT(*) AS c FROM results").fetchone()["c"]
    assert n == 2

    # 同一条件の再実行はキャッシュ命中で推論しない（受け入れ基準）。
    r2 = run_single(conn, engine_id="tesseract", image_path=img_path,
                    mode="fullscreen", preprocess="raw")
    assert r2["cached"] is True
    n2 = conn.execute("SELECT COUNT(*) AS c FROM results").fetchone()["c"]
    assert n2 == 2  # 増えていない


@pytest.mark.skipif(not _HAS_TESSERACT, reason="tesseract バイナリ未インストール")
def test_tesseract_reads_synthetic_text(tmp_path):
    img_path = tmp_path / "0001.png"
    _write_synth(img_path)
    conn = connect(tmp_path / "bench.sqlite")
    r = run_single(conn, engine_id="tesseract", image_path=img_path,
                   mode="fullscreen", preprocess="tuned")
    assert r["error"] is None
    # 数字の一部が読めていれば OK（前処理・辞書オフの経路が生きている確認）。
    assert any(ch.isdigit() for ch in r["text"])
