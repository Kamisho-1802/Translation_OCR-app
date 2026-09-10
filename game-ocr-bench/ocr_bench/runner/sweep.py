"""パラメータスイープ（仕様書 §5.2）。

条件タグでフィルタしたうえでエンジンパラメータを振り、値ごとの micro CER を出す。
例: ocr-bench sweep --engine easyocr --param mag_ratio --values 1.0,2.0 --filter font_style=hud

課金が無いので総当たりできる、という本アプリの利点（§5.1）を活かす中核機能。
"""

from __future__ import annotations

import json

from ..eval.evaluator import evaluate
from .runner import run_batch


def _parse_value(v: str):
    """'1.6' -> 1.6, '960' -> 960, それ以外は文字列。"""
    try:
        return int(v)
    except ValueError:
        pass
    try:
        return float(v)
    except ValueError:
        return v


def select_samples_by_tag(conn, tag_filter: str | None) -> list[int] | None:
    """'font_style=fantasy' 形式のフィルタで sample_id を絞る。None なら全件。"""
    if not tag_filter:
        return None
    key, _, val = tag_filter.partition("=")
    ids = []
    for r in conn.execute("SELECT id, meta FROM samples").fetchall():
        try:
            meta = json.loads(r["meta"] or "{}") or {}
        except Exception:
            meta = {}
        if str(meta.get(key)) == val:
            ids.append(r["id"])
    return ids


def _micro_cer_for_run(conn, run_id: int, norm_profile: str):
    row = conn.execute(
        """SELECT SUM(COALESCE(m.edit_ins,0)+COALESCE(m.edit_del,0)+COALESCE(m.edit_sub,0)) d,
                  SUM(COALESCE(m.ref_chars,0)) ref
           FROM metrics m JOIN results res ON res.id=m.result_id
           WHERE res.run_id=? AND m.norm_profile=?""",
        (run_id, norm_profile),
    ).fetchone()
    if not row or not row["ref"]:
        return None
    return row["d"] / row["ref"]


def sweep_param(
    conn,
    *,
    engine_id: str,
    param: str,
    values: list[str],
    tag_filter: str | None = None,
    mode: str = "fullscreen",
    preprocess: str = "raw",
    norm_profile: str = "strict",
    warmup_iters: int = 3,
) -> list[dict]:
    """param を values で振り、値ごとの micro CER と FPS を返す。"""
    sample_ids = select_samples_by_tag(conn, tag_filter)
    results = []
    for raw in values:
        val = _parse_value(raw)
        out = run_batch(conn, engine_ids=[engine_id], modes=[mode], presets=[preprocess],
                        sample_ids=sample_ids, warmup_iters=warmup_iters,
                        options={param: val})
        key = f"{engine_id}/{mode}/{preprocess}"
        run_id = out["stats"][key]["run_id"]
        fps = out["stats"][key]["fps"]
        evaluate(conn, run_ids=[run_id], norm_profile=norm_profile)
        micro = _micro_cer_for_run(conn, run_id, norm_profile)
        results.append({"param": param, "value": val, "run_id": run_id,
                        "micro_cer": micro, "fps": fps})
    return results
