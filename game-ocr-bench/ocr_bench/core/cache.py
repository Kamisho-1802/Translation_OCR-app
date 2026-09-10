"""結果キャッシュ（仕様書 §8）。

キー: (image_sha256, engine, options_hash, preprocess_hash, mode, region_id)
同一条件の再実行で推論 0 回を保証するための照会。runs と results を結合して探す。
"""

from __future__ import annotations

import sqlite3


def find_cached_result(
    conn: sqlite3.Connection,
    *,
    image_sha256: str,
    engine_id: str,
    mode: str,
    options_hash: str,
    preprocess_hash: str,
    region_id: int | None,
) -> sqlite3.Row | None:
    """条件一致の既存 result 行を返す（無ければ None）。

    region_id は NULL 同士を一致とみなす必要があるため IS で比較する。
    """
    sql = """
        SELECT r.*
        FROM results r
        JOIN runs run ON run.id = r.run_id
        JOIN samples s ON s.id = r.sample_id
        WHERE s.image_sha256 = ?
          AND run.engine_id = ?
          AND run.mode = ?
          AND run.options_hash = ?
          AND run.preprocess_hash = ?
          AND r.region_id IS ?
          AND r.error IS NULL
        LIMIT 1
    """
    cur = conn.execute(
        sql,
        (image_sha256, engine_id, mode, options_hash, preprocess_hash, region_id),
    )
    return cur.fetchone()
