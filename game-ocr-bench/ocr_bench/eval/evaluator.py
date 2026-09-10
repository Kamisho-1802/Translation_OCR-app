"""評価ランナー（仕様書 §8 実行と評価の分離）。

results（推論済み）を読み、GT と突き合わせて metrics を計算・保存する。
**推論は一切行わない**（受け入れ基準: eval / report は推論しない）。

GT の取り方:
  - roi モード（region_id あり）: regions.gt_text / regions.proper_nouns
  - fullscreen（region_id なし）: samples.gt_text（regions から自動生成された全画面 GT）
GT が未確定（NULL）の result はスキップする（M5 の GT 確定後に評価可能になる）。
"""

from __future__ import annotations

import json
import sqlite3

from . import detection as D
from . import metrics as M


def _sample_region_boxes(conn: sqlite3.Connection, sample_id: int):
    rows = conn.execute(
        "SELECT box_json FROM regions WHERE sample_id = ?", (sample_id,)
    ).fetchall()
    return [tuple(json.loads(r["box_json"])) for r in rows]


def _pred_blocks(blocks_json: str | None):
    """results.blocks_json を [(text, (x,y,w,h)|None), ...] へ。"""
    out = []
    for b in json.loads(blocks_json or "[]"):
        box = tuple(b["box"]) if b.get("box") else None
        out.append((b.get("text", ""), box))
    return out


def _iter_target_results(conn: sqlite3.Connection, run_ids: list[int] | None):
    sql = (
        "SELECT r.id AS result_id, r.sample_id, r.pred_text, r.region_id, r.error, "
        "       r.blocks_json, "
        "       s.gt_text AS sample_gt, "
        "       reg.gt_text AS region_gt, reg.proper_nouns AS region_pn "
        "FROM results r "
        "JOIN samples s ON s.id = r.sample_id "
        "LEFT JOIN regions reg ON reg.id = r.region_id "
    )
    params: list = []
    if run_ids:
        placeholders = ",".join("?" for _ in run_ids)
        sql += f"WHERE r.run_id IN ({placeholders}) "
        params = list(run_ids)
    return conn.execute(sql, params).fetchall()


def evaluate(
    conn: sqlite3.Connection,
    run_ids: list[int] | None = None,
    norm_profile: str = "strict",
) -> dict:
    """対象 result 群の指標を計算し metrics へ upsert。要約を返す（推論なし）。"""
    rows = _iter_target_results(conn, run_ids)
    evaluated = skipped = 0

    for row in rows:
        if row["error"]:
            skipped += 1
            continue
        gt = row["region_gt"] if row["region_id"] is not None else row["sample_gt"]
        if gt is None:
            skipped += 1  # GT 未確定
            continue

        pred = row["pred_text"] or ""
        cc = M.cer_counts(gt, pred, norm_profile)
        wc = M.wer_counts(gt, pred, norm_profile)
        cer = 0.0 if cc.ref_len == 0 else cc.distance / cc.ref_len
        wer = 0.0 if wc.ref_len == 0 else wc.distance / wc.ref_len
        exact = int(M.normalize(gt, norm_profile) == M.normalize(pred, norm_profile))

        proper_nouns = json.loads(row["region_pn"]) if row["region_pn"] else []
        pn_acc = M.proper_noun_accuracy(pred, proper_nouns, norm_profile)

        # 検出評価と誤検出テキスト量は fullscreen（region_id なし）のみ（§4.2/§4.3）。
        det_recall = det_precision = spurious = None
        if row["region_id"] is None:
            gt_boxes = _sample_region_boxes(conn, row["sample_id"])
            if gt_boxes:
                blocks = _pred_blocks(row["blocks_json"])
                word_boxes = [b for _t, b in blocks if b is not None]
                # 単語粒度のボックスを行に統合してから GT 領域と IoU 照合する。
                pred_boxes = D.merge_boxes_into_lines(word_boxes)
                ds = D.detection_scores(gt_boxes, pred_boxes)
                det_recall, det_precision = ds.recall, ds.precision
                spurious = D.spurious_char_count(gt_boxes, blocks)

        conn.execute(
            """INSERT INTO metrics
               (result_id, norm_profile, cer, wer, edit_ins, edit_del, edit_sub,
                exact_match, proper_noun_acc, spurious_chars,
                det_recall, det_precision, ref_chars)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(result_id, norm_profile) DO UPDATE SET
                 cer=excluded.cer, wer=excluded.wer,
                 edit_ins=excluded.edit_ins, edit_del=excluded.edit_del,
                 edit_sub=excluded.edit_sub, exact_match=excluded.exact_match,
                 proper_noun_acc=excluded.proper_noun_acc,
                 spurious_chars=excluded.spurious_chars,
                 det_recall=excluded.det_recall, det_precision=excluded.det_precision,
                 ref_chars=excluded.ref_chars""",
            (
                row["result_id"],
                norm_profile,
                cer,
                wer,
                cc.ins,
                cc.dele,
                cc.sub,
                exact,
                pn_acc,
                spurious,
                det_recall,
                det_precision,
                cc.ref_len,
            ),
        )
        evaluated += 1

    conn.commit()
    return {"evaluated": evaluated, "skipped": skipped, "norm_profile": norm_profile}
