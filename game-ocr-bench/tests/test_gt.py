"""M5: GT 多数決・ブートストラップ・レビュー・監査。"""

from __future__ import annotations

import json
import shutil

import numpy as np
import pytest

from ocr_bench.core.db import connect
from ocr_bench.gt.audit import select_for_audit
from ocr_bench.gt.review import accept_agreed, confirm_region, list_needs_review
from ocr_bench.gt.vote import majority_vote


# ---- 多数決 -------------------------------------------------------------
def test_vote_unanimous_two_engines():
    v = majority_vote({"a": "EXIT", "b": "EXIT"})
    assert v.agreed and v.winner == "EXIT" and v.top_votes == 2


def test_vote_split_two_engines_needs_review():
    v = majority_vote({"a": "EXIT", "b": "EXIY"})
    assert not v.agreed and v.winner is None


def test_vote_majority_three_engines():
    v = majority_vote({"a": "EXIT", "b": "EXIT", "c": "EXIY"})
    assert v.agreed and v.winner == "EXIT" and v.top_votes == 2


def test_vote_all_differ_three_engines():
    v = majority_vote({"a": "A", "b": "B", "c": "C"})
    assert not v.agreed and v.winner is None


def test_vote_uses_normalized_agreement():
    # strict では大小区別するので割れる。
    assert not majority_vote({"a": "EXIT", "b": "exit"}, "strict").agreed
    # loose では一致。
    assert majority_vote({"a": "EXIT", "b": "exit"}, "loose").agreed


# ---- レビュー（DB, エンジン不要） ---------------------------------------
def _seed_region(conn, sample_id, key, order, voted, status, drafts):
    conn.execute(
        """INSERT INTO regions (sample_id, region_key, box_json, order_index,
           voted_text, gt_status, draft_json) VALUES (?,?,?,?,?,?,?)""",
        (sample_id, key, "[0,0,10,10]", order, voted, status,
         json.dumps(drafts)),
    )


def test_accept_agreed_and_regenerate_full_gt(tmp_path):
    conn = connect(tmp_path / "b.sqlite")
    conn.execute("INSERT INTO samples (file_path, image_sha256) VALUES ('a.png','S')")
    sid = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
    _seed_region(conn, sid, "r1", 0, "HP 120/200", "agreed", {"a": "HP 120/200"})
    _seed_region(conn, sid, "r2", 1, "EXIT", "needs_review", {"a": "EXIT", "b": "EXIY"})
    conn.commit()

    n = accept_agreed(conn)
    assert n == 1  # agreed のみ確定
    # r2 はまだ needs_review。
    assert len(list_needs_review(conn)) == 1

    # 人手で r2 を確定 -> 全画面 GT が両領域から再生成される。
    r2_id = conn.execute("SELECT id FROM regions WHERE region_key='r2'").fetchone()["id"]
    confirm_region(conn, r2_id, "EXIT")
    gt = conn.execute("SELECT gt_text FROM samples WHERE id=?", (sid,)).fetchone()["gt_text"]
    assert gt == "HP 120/200\nEXIT"


def test_audit_prioritizes_fantasy_pixel(tmp_path):
    conn = connect(tmp_path / "b.sqlite")
    for i, fs in enumerate(["sans", "fantasy", "pixel", "serif", "sans"]):
        conn.execute(
            "INSERT INTO samples (file_path, image_sha256, meta) VALUES (?,?,?)",
            (f"{i}.png", f"S{i}", json.dumps({"font_style": fs})),
        )
        sid = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
        _seed_region(conn, sid, "r1", 0, "X", "confirmed", {"a": "X"})
    conn.commit()
    # rate 0.4 * 5 = 2 件、fantasy/pixel が優先される。
    sel = select_for_audit(conn, sample_rate=0.4)
    fonts = {json.loads(r["meta"])["font_style"] for r in sel}
    assert len(sel) == 2 and fonts <= {"fantasy", "pixel"}


# ---- ブートストラップ（Tesseract 必要） ---------------------------------
_HAS_TESSERACT = shutil.which("tesseract") is not None


@pytest.mark.skipif(not _HAS_TESSERACT, reason="tesseract 未インストール")
def test_bootstrap_agrees_on_clear_text(tmp_path):
    import cv2

    from ocr_bench.gt.bootstrap import bootstrap_gt
    from ocr_bench.runner.ingest import ingest_sample

    # 明瞭な 1 領域画像 + regions（box のみ、text 空）。
    img = np.full((80, 300, 3), 18, dtype=np.uint8)
    cv2.putText(img, "EXIT", (20, 55), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (240, 240, 240), 2)
    p = tmp_path / "x.png"
    ok, buf = cv2.imencode(".png", img)
    buf.tofile(str(p))
    (w, h), base = cv2.getTextSize("EXIT", cv2.FONT_HERSHEY_SIMPLEX, 1.2, 2)
    doc = {"image": "x.png", "reading_order": ["r1"],
           "regions": [{"id": "r1", "box": [20, 55 - h, w, h + base], "text": "",
                        "proper_nouns": []}]}
    rj = tmp_path / "x.json"
    rj.write_text(json.dumps(doc), encoding="utf-8")

    conn = connect(tmp_path / "b.sqlite")
    ingest_sample(conn, p, rj)
    summary = bootstrap_gt(conn, ["tesseract"], preprocess="tuned")
    assert summary["regions"] == 1
    row = conn.execute("SELECT voted_text, gt_status FROM regions").fetchone()
    # 単一エンジンでも threshold=(1//2)+1=1 で agreed、EXIT を読めている。
    assert row["gt_status"] == "agreed" and "EXIT" in (row["voted_text"] or "")
