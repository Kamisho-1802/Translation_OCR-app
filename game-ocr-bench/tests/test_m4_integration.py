"""M3/M4 統合: ingest→全画面GT自動生成→ROI/fullscreen実行→検出評価。

Tesseract バイナリが必要（無ければ skip）。
"""

from __future__ import annotations

import json
import shutil

import numpy as np
import pytest

pytest.importorskip("cv2")
import cv2  # noqa: E402

from ocr_bench.core.db import connect  # noqa: E402
from ocr_bench.eval.evaluator import evaluate  # noqa: E402
from ocr_bench.runner.ingest import ingest_sample  # noqa: E402
from ocr_bench.runner.runner import run_batch  # noqa: E402

_HAS_TESSERACT = shutil.which("tesseract") is not None
pytestmark = pytest.mark.skipif(not _HAS_TESSERACT, reason="tesseract 未インストール")

_FONT, _SCALE, _THICK = cv2.FONT_HERSHEY_SIMPLEX, 1.0, 2


def _text_box(text, org):
    (w, h), baseline = cv2.getTextSize(text, _FONT, _SCALE, _THICK)
    x, by = org
    return [x, by - h, w, h + baseline]


def _make_dataset(tmp_path):
    items = [("r1", "HP 120/200", "hud", [], (20, 55)),
             ("r2", "EASTMARCH KEEP", "map_label", ["EASTMARCH KEEP"], (20, 150))]
    img = np.full((220, 480, 3), 18, dtype=np.uint8)
    for _id, text, _tt, _pn, org in items:
        cv2.putText(img, text, org, _FONT, _SCALE, (240, 240, 240), _THICK, cv2.LINE_AA)
    img_path = tmp_path / "0002.png"
    ok, buf = cv2.imencode(".png", img)
    buf.tofile(str(img_path))
    doc = {"image": "0002.png", "reading_order": [i[0] for i in items],
           "regions": [{"id": i[0], "box": _text_box(i[1], i[4]), "text": i[1],
                        "text_type": i[2], "proper_nouns": i[3]} for i in items]}
    rj = tmp_path / "0002.json"
    rj.write_text(json.dumps(doc), encoding="utf-8")
    return img_path, rj


def test_ingest_autogenerates_full_gt(tmp_path):
    img_path, rj = _make_dataset(tmp_path)
    conn = connect(tmp_path / "b.sqlite")
    sid = ingest_sample(conn, img_path, rj)
    gt = conn.execute("SELECT gt_text FROM samples WHERE id=?", (sid,)).fetchone()["gt_text"]
    assert gt == "HP 120/200\nEASTMARCH KEEP"  # regions から自動生成
    assert conn.execute("SELECT COUNT(*) c FROM regions").fetchone()["c"] == 2


def test_roi_and_detection_flow(tmp_path):
    img_path, rj = _make_dataset(tmp_path)
    conn = connect(tmp_path / "b.sqlite")
    ingest_sample(conn, img_path, rj)

    run_batch(conn, engine_ids=["tesseract"], modes=["fullscreen", "roi"],
              presets=["raw", "tuned"], warmup_iters=1)
    # roi は 2 領域 × 2 前処理 = 4 件、fullscreen は 2 件。
    n_roi = conn.execute("SELECT COUNT(*) c FROM results WHERE region_id IS NOT NULL").fetchone()["c"]
    n_full = conn.execute("SELECT COUNT(*) c FROM results WHERE region_id IS NULL").fetchone()["c"]
    assert n_roi == 4 and n_full == 2

    evaluate(conn, norm_profile="strict")
    # fullscreen の検出は Recall/Precision=1.0、誤検出 0。
    rows = conn.execute(
        """SELECT m.det_recall, m.det_precision, m.spurious_chars
           FROM metrics m JOIN results r ON r.id=m.result_id
           WHERE r.region_id IS NULL""").fetchall()
    assert rows and all(r["det_recall"] == 1.0 and r["det_precision"] == 1.0
                        and r["spurious_chars"] == 0 for r in rows)

    # roi は認識のみ（検出指標は付かない）。
    roi_m = conn.execute(
        """SELECT m.det_recall FROM metrics m JOIN results r ON r.id=m.result_id
           WHERE r.region_id IS NOT NULL""").fetchall()
    assert roi_m and all(r["det_recall"] is None for r in roi_m)


def test_cache_zero_inference_on_rerun(tmp_path):
    img_path, rj = _make_dataset(tmp_path)
    conn = connect(tmp_path / "b.sqlite")
    ingest_sample(conn, img_path, rj)
    run_batch(conn, engine_ids=["tesseract"], modes=["fullscreen"], presets=["raw"], warmup_iters=1)
    out = run_batch(conn, engine_ids=["tesseract"], modes=["fullscreen"], presets=["raw"], warmup_iters=1)
    assert out["counters"]["inferences"] == 0 and out["counters"]["cache_hits"] >= 1
