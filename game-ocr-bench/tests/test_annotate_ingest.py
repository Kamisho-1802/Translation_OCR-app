"""annotate ツール出力（meta 付き regions JSON）が ingest で正しく取り込まれること。"""

from __future__ import annotations

import json
from pathlib import Path

from ocr_bench.core.db import connect
from ocr_bench.runner.ingest import ingest_sample


def test_annotate_html_exists_and_has_key_controls():
    html = (Path(__file__).resolve().parents[1] / "tools" / "annotate.html").read_text(
        encoding="utf-8")
    for marker in ["buildDoc", "reading_order", "regions JSON", "text_type", "font_style"]:
        assert marker in html


def test_ingest_applies_meta_from_doc(tmp_path):
    import cv2
    import numpy as np

    img = np.full((60, 200, 3), 20, dtype=np.uint8)
    p = tmp_path / "0007.png"
    ok, buf = cv2.imencode(".png", img)
    buf.tofile(str(p))

    # annotate ツールが出力する形（meta 同梱）。
    doc = {
        "image": "0007.png",
        "reading_order": ["r1"],
        "regions": [{"id": "r1", "box": [10, 10, 80, 30], "text": "EXIT",
                     "text_type": "menu", "proper_nouns": []}],
        "meta": {"font_style": "fantasy", "text_color": "yellow"},
    }
    rj = tmp_path / "0007.json"
    rj.write_text(json.dumps(doc), encoding="utf-8")

    conn = connect(tmp_path / "b.sqlite")
    sid = ingest_sample(conn, p, rj)

    meta = json.loads(conn.execute("SELECT meta FROM samples WHERE id=?", (sid,)).fetchone()["meta"])
    assert meta["font_style"] == "fantasy" and meta["text_color"] == "yellow"
    reg = conn.execute("SELECT gt_text, text_type FROM regions WHERE sample_id=?", (sid,)).fetchone()
    assert reg["gt_text"] == "EXIT" and reg["text_type"] == "menu"
    # 全画面 GT も regions から生成されている。
    gt = conn.execute("SELECT gt_text FROM samples WHERE id=?", (sid,)).fetchone()["gt_text"]
    assert gt == "EXIT"
