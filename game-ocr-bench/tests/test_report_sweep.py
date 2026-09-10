"""M6/M7: 集計・スイープ・HTML レポート・UI コンパイル。"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pytest

from ocr_bench.core.db import connect

_HAS_TESSERACT = shutil.which("tesseract") is not None


def test_ui_module_compiles():
    import py_compile

    path = Path(__file__).resolve().parents[1] / "ocr_bench" / "ui" / "app.py"
    py_compile.compile(str(path), doraise=True)  # 構文検証（Streamlit 不要）


def test_colorkey_preset_resolves():
    # color_key の preset が colorkeys.yaml から解決され、二値画像が返る。
    import cv2

    from ocr_bench.preprocess.pipeline import apply_pipeline

    img = np.zeros((20, 60, 3), dtype=np.uint8)
    img[:, :30] = (255, 255, 255)  # 白領域
    out, _ = apply_pipeline(img, [{"op": "color_key", "params": {"preset": "white"}}])
    assert out.ndim == 2  # 二値（単チャンネル）


def _build_dataset(tmp_path):
    import cv2

    from ocr_bench.runner.ingest import ingest_sample

    items = [("r1", "HP 120/200", "hud"), ("r2", "EASTMARCH KEEP", "map_label")]
    img = np.full((220, 480, 3), 18, dtype=np.uint8)
    orgs = [(20, 55), (20, 150)]
    regs = []
    for (rid, text, tt), org in zip(items, orgs):
        cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, 1.0, (240, 240, 240), 2)
        (w, h), base = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 1.0, 2)
        regs.append({"id": rid, "box": [org[0], org[1] - h, w, h + base],
                     "text": text, "text_type": tt, "proper_nouns": []})
    p = tmp_path / "0002.png"
    ok, buf = cv2.imencode(".png", img)
    buf.tofile(str(p))
    doc = {"image": "0002.png", "reading_order": ["r1", "r2"], "regions": regs}
    rj = tmp_path / "0002.json"
    rj.write_text(json.dumps(doc), encoding="utf-8")
    conn = connect(tmp_path / "b.sqlite")
    # meta に font_style を付けて breakdown を検証可能に。
    ingest_sample(conn, p, rj, meta={"font_style": "sans", "text_type": "hud"})
    return conn


@pytest.mark.skipif(not _HAS_TESSERACT, reason="tesseract 未インストール")
def test_summary_breakdown_and_report(tmp_path):
    from ocr_bench.eval.evaluator import evaluate
    from ocr_bench.report.aggregate import breakdown_by_tag, summary_by_engine
    from ocr_bench.report.export import write_report
    from ocr_bench.runner.runner import run_batch

    conn = _build_dataset(tmp_path)
    run_batch(conn, engine_ids=["tesseract"], modes=["fullscreen"], presets=["raw"], warmup_iters=1)
    evaluate(conn, norm_profile="strict")

    summ = summary_by_engine(conn, "strict")
    assert summ and summ[0]["engine_id"] == "tesseract"
    assert summ[0]["micro_cer"] == 0.0  # 完全一致
    assert summ[0]["fps"] and summ[0]["fps"] > 0

    bd = breakdown_by_tag(conn, "font_style", "strict")
    assert bd["rows"] and bd["rows"][0]["value"] == "sans"

    out = write_report(conn, tmp_path / "out" / "report.html", norm_profile="strict")
    html = out.read_text(encoding="utf-8")
    assert "Summary" in html and "tesseract" in html and "micro CER" in html


@pytest.mark.skipif(not _HAS_TESSERACT, reason="tesseract 未インストール")
def test_sweep_param_over_psm(tmp_path):
    from ocr_bench.runner.sweep import sweep_param

    conn = _build_dataset(tmp_path)
    rows = sweep_param(conn, engine_id="tesseract", param="psm",
                       values=["7", "11"], mode="fullscreen", preprocess="raw")
    assert len(rows) == 2
    assert all(r["param"] == "psm" for r in rows)
    # micro_cer が算出されている（数値 or None でなく数値であること）。
    assert all(isinstance(r["value"], int) for r in rows)
