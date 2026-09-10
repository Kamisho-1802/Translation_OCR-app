"""GT レビュー（仕様書 §6）。不一致スパンのみ人手確定する。

- accept_agreed: 多数決一致（agreed）の領域を voted_text で確定。
- 不一致（needs_review）は per-engine 下書きを提示し、人が正しいテキストを入力して確定。
- 確定後、全画面 GT（samples.gt_text）を regions から再生成する（二重管理を避ける）。
"""

from __future__ import annotations

import json


def regenerate_full_gt(conn, sample_id: int) -> None:
    """confirmed な領域の gt_text を order_index 順に連結して samples.gt_text を作る。"""
    rows = conn.execute(
        "SELECT gt_text FROM regions WHERE sample_id = ? ORDER BY order_index", (sample_id,)
    ).fetchall()
    full = "\n".join((r["gt_text"] or "") for r in rows)
    conn.execute("UPDATE samples SET gt_text = ? WHERE id = ?", (full, sample_id))
    conn.commit()


def accept_agreed(conn, sample_ids: list[int] | None = None) -> int:
    """多数決一致の領域を voted_text で確定する。確定件数を返す。"""
    where = "gt_status = 'agreed'"
    params: list = []
    if sample_ids:
        where += " AND sample_id IN (%s)" % ",".join("?" for _ in sample_ids)
        params = list(sample_ids)
    rows = conn.execute(f"SELECT id, sample_id FROM regions WHERE {where}", params).fetchall()
    for r in rows:
        conn.execute(
            "UPDATE regions SET gt_text = voted_text, gt_status = 'confirmed' WHERE id = ?",
            (r["id"],),
        )
    conn.commit()
    for sid in {r["sample_id"] for r in rows}:
        regenerate_full_gt(conn, sid)
    return len(rows)


def list_needs_review(conn, sample_ids: list[int] | None = None) -> list:
    q = ("SELECT r.id, r.sample_id, r.region_key, r.box_json, r.voted_text, r.draft_json, "
         "s.file_path FROM regions r JOIN samples s ON s.id = r.sample_id "
         "WHERE r.gt_status = 'needs_review'")
    params: list = []
    if sample_ids:
        q += " AND r.sample_id IN (%s)" % ",".join("?" for _ in sample_ids)
        params = list(sample_ids)
    q += " ORDER BY r.sample_id, r.order_index"
    return conn.execute(q, params).fetchall()


def confirm_region(conn, region_id: int, text: str) -> None:
    """1 領域の GT を人手確定し、全画面 GT を再生成する。"""
    row = conn.execute("SELECT sample_id FROM regions WHERE id = ?", (region_id,)).fetchone()
    conn.execute(
        "UPDATE regions SET gt_text = ?, gt_status = 'confirmed' WHERE id = ?",
        (text, region_id),
    )
    conn.commit()
    if row:
        regenerate_full_gt(conn, row["sample_id"])


def interactive_review(conn, input_fn=input, print_fn=print) -> int:
    """不一致領域を 1 件ずつ提示し、正しいテキストを入力して確定する。

    各行のエンジン別下書きを表示。Enter で voted_text を採用、テキスト入力で上書き、
    's' でスキップ。確定件数を返す。テスト用に input_fn/print_fn を差し替え可能。
    """
    rows = list_needs_review(conn)
    confirmed = 0
    for r in rows:
        drafts = json.loads(r["draft_json"] or "{}")
        print_fn(f"\n[sample {r['sample_id']} / {r['region_key']}] box={r['box_json']}")
        for eid, txt in drafts.items():
            print_fn(f"    {eid:12}: {txt!r}")
        print_fn(f"    (voted: {r['voted_text']!r})")
        ans = input_fn("  正しいテキスト [Enter=voted / 's'=skip]: ")
        if ans == "s":
            continue
        text = r["voted_text"] if ans == "" else ans
        confirm_region(conn, r["id"], text or "")
        confirmed += 1
    return confirmed
