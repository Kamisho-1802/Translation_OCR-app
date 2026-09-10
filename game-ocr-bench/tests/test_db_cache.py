"""DB スキーマ初期化とキャッシュ照会（外部エンジン不要）。"""

from __future__ import annotations

from ocr_bench.core.cache import find_cached_result
from ocr_bench.core.db import connect


def test_schema_creates_all_tables(tmp_path):
    conn = connect(tmp_path / "t.sqlite")
    names = {
        r["name"]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert {"samples", "regions", "runs", "results", "metrics"} <= names


def test_cache_hit_roundtrip(tmp_path):
    conn = connect(tmp_path / "t.sqlite")
    conn.execute(
        "INSERT INTO samples (file_path, image_sha256, gt_text, meta) VALUES (?, ?, ?, ?)",
        ("a.png", "SHA", "gt", "{}"),
    )
    sample_id = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
    conn.execute(
        """INSERT INTO runs (started_at, engine_id, mode, options_hash, preprocess_hash)
           VALUES (?, ?, ?, ?, ?)""",
        ("t", "tesseract", "fullscreen", "OPT", "PRE"),
    )
    run_id = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
    conn.execute(
        """INSERT INTO results (run_id, sample_id, region_id, pred_text, error)
           VALUES (?, ?, ?, ?, ?)""",
        (run_id, sample_id, None, "HELLO", None),
    )
    conn.commit()

    hit = find_cached_result(
        conn,
        image_sha256="SHA",
        engine_id="tesseract",
        mode="fullscreen",
        options_hash="OPT",
        preprocess_hash="PRE",
        region_id=None,
    )
    assert hit is not None and hit["pred_text"] == "HELLO"

    miss = find_cached_result(
        conn,
        image_sha256="SHA",
        engine_id="tesseract",
        mode="fullscreen",
        options_hash="OTHER",
        preprocess_hash="PRE",
        region_id=None,
    )
    assert miss is None
