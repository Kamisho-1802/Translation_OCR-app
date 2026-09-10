"""M2: evaluate() が results を読んで metrics を保存し、推論を一切呼ばないこと。"""

from __future__ import annotations

import json

from ocr_bench.core.db import connect
from ocr_bench.eval.evaluator import evaluate


def _seed(conn, gt, pred, *, region=False, proper_nouns=None):
    conn.execute(
        "INSERT INTO samples (file_path, image_sha256, gt_text, meta) VALUES (?,?,?,?)",
        ("a.png", "SHA", None if region else gt, "{}"),
    )
    sid = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
    region_id = None
    if region:
        conn.execute(
            """INSERT INTO regions (sample_id, region_key, box_json, gt_text,
               text_type, proper_nouns, order_index) VALUES (?,?,?,?,?,?,?)""",
            (sid, "r1", "[0,0,10,10]", gt, "dialogue",
             json.dumps(proper_nouns or []), 0),
        )
        region_id = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
    conn.execute(
        "INSERT INTO runs (started_at, engine_id, mode, options_hash, preprocess_hash) "
        "VALUES (?,?,?,?,?)",
        ("t", "tesseract", "roi" if region else "fullscreen", "OPT", "PRE"),
    )
    run_id = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
    conn.execute(
        "INSERT INTO results (run_id, sample_id, region_id, pred_text, error) "
        "VALUES (?,?,?,?,?)",
        (run_id, sid, region_id, pred, None),
    )
    conn.commit()


def test_evaluate_fullscreen_stores_metrics(tmp_path):
    conn = connect(tmp_path / "b.sqlite")
    _seed(conn, gt="EXIT", pred="EXIY")
    summary = evaluate(conn, norm_profile="strict")
    assert summary["evaluated"] == 1 and summary["skipped"] == 0
    m = conn.execute("SELECT * FROM metrics").fetchone()
    assert m["cer"] == 0.25 and m["edit_sub"] == 1 and m["exact_match"] == 0


def test_evaluate_skips_when_gt_missing(tmp_path):
    conn = connect(tmp_path / "b.sqlite")
    # gt_text NULL の fullscreen result → GT 未確定でスキップ。
    conn.execute(
        "INSERT INTO samples (file_path, image_sha256, gt_text, meta) VALUES (?,?,?,?)",
        ("a.png", "SHA2", None, "{}"),
    )
    sid = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
    conn.execute(
        "INSERT INTO runs (started_at, engine_id, mode, options_hash, preprocess_hash) "
        "VALUES (?,?,?,?,?)", ("t", "tesseract", "fullscreen", "O", "P"))
    rid = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
    conn.execute(
        "INSERT INTO results (run_id, sample_id, region_id, pred_text, error) "
        "VALUES (?,?,?,?,?)", (rid, sid, None, "whatever", None))
    conn.commit()
    summary = evaluate(conn, norm_profile="strict")
    assert summary["evaluated"] == 0 and summary["skipped"] == 1


def test_evaluate_roi_proper_nouns(tmp_path):
    conn = connect(tmp_path / "b.sqlite")
    _seed(conn, gt="Aelthyr raised her Sunstave",
          pred="Aelthyr raised her Sunstave", region=True,
          proper_nouns=["Aelthyr", "Sunstave"])
    evaluate(conn, norm_profile="strict")
    m = conn.execute("SELECT * FROM metrics").fetchone()
    assert m["cer"] == 0.0 and m["exact_match"] == 1
    assert m["proper_noun_acc"] == 1.0


def test_evaluate_is_idempotent_upsert(tmp_path):
    conn = connect(tmp_path / "b.sqlite")
    _seed(conn, gt="EXIT", pred="EXIY")
    evaluate(conn, norm_profile="strict")
    evaluate(conn, norm_profile="strict")  # 2 回目でも重複行を作らない
    n = conn.execute("SELECT COUNT(*) AS c FROM metrics").fetchone()["c"]
    assert n == 1
