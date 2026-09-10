"""集計（仕様書 §4.1 マイクロ平均主指標 / §5.3 条件別使い分け表 / §10 Summary・Breakdown）。

metrics（eval 済み）と results（レイテンシ）を読んで、エンジン別・条件タグ別の指標に
まとめる。**推論は行わない**（受け入れ基準: report は推論しない）。
micro CER = Σ(編集距離) / Σ(参照文字数)。
"""

from __future__ import annotations

import json
import sqlite3

import numpy as np


def _rows(conn, norm_profile, mode=None):
    sql = (
        "SELECT run.engine_id, run.mode, res.sample_id, res.region_id, res.latency_ms, "
        "       res.error, m.cer, m.wer, m.edit_ins, m.edit_del, m.edit_sub, "
        "       m.exact_match, m.proper_noun_acc, m.spurious_chars, m.det_recall, "
        "       m.det_precision, m.ref_chars, s.meta "
        "FROM metrics m JOIN results res ON res.id = m.result_id "
        "JOIN runs run ON run.id = res.run_id "
        "JOIN samples s ON s.id = res.sample_id "
        "WHERE m.norm_profile = ?"
    )
    params = [norm_profile]
    if mode:
        sql += " AND run.mode = ?"
        params.append(mode)
    return conn.execute(sql, params).fetchall()


def _summ(items: list[sqlite3.Row]) -> dict:
    """1 グループ（例: あるエンジン）の指標をまとめる。"""
    n = len(items)
    dist = sum((r["edit_ins"] or 0) + (r["edit_del"] or 0) + (r["edit_sub"] or 0) for r in items)
    ref = sum((r["ref_chars"] or 0) for r in items)
    ins = sum((r["edit_ins"] or 0) for r in items)
    micro_cer = (dist / ref) if ref else None
    ins_rate = (ins / ref) if ref else None
    macro_cer = float(np.mean([r["cer"] for r in items])) if n else None
    wer_mean = float(np.mean([r["wer"] for r in items])) if n else None
    exact = [r["exact_match"] for r in items if r["exact_match"] is not None]
    exact_rate = float(np.mean(exact)) if exact else None
    dets_r = [r["det_recall"] for r in items if r["det_recall"] is not None]
    dets_p = [r["det_precision"] for r in items if r["det_precision"] is not None]
    spur = [r["spurious_chars"] for r in items if r["spurious_chars"] is not None]
    pn = [r["proper_noun_acc"] for r in items if r["proper_noun_acc"] is not None]
    lat = [r["latency_ms"] for r in items if not r["error"] and r["latency_ms"]]
    return {
        "n": n,
        "micro_cer": micro_cer,
        "macro_cer": macro_cer,
        "wer": wer_mean,
        "exact_match_rate": exact_rate,
        "ins_rate": ins_rate,
        "proper_noun_acc": float(np.mean(pn)) if pn else None,
        "spurious_total": int(sum(spur)) if spur else None,
        "det_recall": float(np.mean(dets_r)) if dets_r else None,
        "det_precision": float(np.mean(dets_p)) if dets_p else None,
        "lat_p50": float(np.percentile(lat, 50)) if lat else None,
        "lat_p95": float(np.percentile(lat, 95)) if lat else None,
        "fps": (1000.0 / float(np.mean(lat))) if lat else None,
    }


def summary_by_engine(conn, norm_profile: str = "strict", mode: str | None = None) -> list[dict]:
    """エンジン別サマリ（§10 Summary）。micro CER 昇順。"""
    rows = _rows(conn, norm_profile, mode)
    by: dict[str, list] = {}
    for r in rows:
        by.setdefault(r["engine_id"], []).append(r)
    out = [{"engine_id": eid, **_summ(items)} for eid, items in by.items()]
    out.sort(key=lambda d: (d["micro_cer"] is None, d["micro_cer"] or 0))
    return out


def breakdown_by_tag(
    conn, tag: str, norm_profile: str = "strict", mode: str | None = None
) -> dict:
    """条件タグ × エンジンの micro CER 表（§10 Breakdown / §5.3 使い分け表の根拠）。

    戻り値: {"tag": tag, "engines": [...], "rows": [{"value": v, "cells": {engine: micro_cer}}]}
    """
    rows = _rows(conn, norm_profile, mode)
    engines = sorted({r["engine_id"] for r in rows})
    grouped: dict[str, dict[str, list]] = {}
    for r in rows:
        try:
            val = (json.loads(r["meta"] or "{}") or {}).get(tag)
        except Exception:
            val = None
        if val is None:
            continue
        grouped.setdefault(str(val), {}).setdefault(r["engine_id"], []).append(r)

    table = []
    for val in sorted(grouped):
        cells = {}
        for eid in engines:
            items = grouped[val].get(eid, [])
            cells[eid] = _summ(items)["micro_cer"] if items else None
        table.append({"value": val, "cells": cells})
    return {"tag": tag, "engines": engines, "rows": table}
