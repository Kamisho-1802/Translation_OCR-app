"""GT ブートストラップ（仕様書 §6）。

各サンプルの領域（regions[].box、人手で用意した矩形）に対し、利用可能な全エンジンを
ROI モードで走らせ、多数決で暫定 GT を作る。一致は 'agreed'、不一致は 'needs_review'
として regions に記録し、review CLI が不一致箇所だけを人手確定する。

前提: regions に box が入っていること（矩形は人手で用意する・§6.3）。
テキスト（gt_text）は空でよく、本処理が下書きを埋める。
"""

from __future__ import annotations

import json

from ..core import config as cfg
from ..core.images import crop, load_bgr
from ..core.registry import create
from ..preprocess.pipeline import apply_pipeline
from .vote import majority_vote


def bootstrap_gt(
    conn,
    engine_ids: list[str],
    sample_ids: list[int] | None = None,
    preprocess: str | list = "raw",
    norm_profile: str = "strict",
) -> dict:
    """全エンジンを ROI 実行し、多数決で voted_text / gt_status を埋める。

    戻り値: {"agreed": n, "needs_review": n, "regions": n, "engines": [...]}。
    """
    steps = cfg.resolve_preprocess(preprocess)

    # エンジンは 1 度だけ生成して使い回す。
    engines = {}
    for eid in engine_ids:
        eng = create(eid)
        eng.warmup()
        engines[eid] = eng

    # 対象サンプル。
    if sample_ids:
        q = "SELECT id, file_path FROM samples WHERE id IN (%s)" % ",".join(
            "?" for _ in sample_ids)
        samples = conn.execute(q, list(sample_ids)).fetchall()
    else:
        samples = conn.execute("SELECT id, file_path FROM samples").fetchall()

    agreed = needs_review = total = 0
    for s in samples:
        image = load_bgr(s["file_path"])
        regions = conn.execute(
            "SELECT id, region_key, box_json FROM regions WHERE sample_id = ? ORDER BY order_index",
            (s["id"],),
        ).fetchall()
        for reg in regions:
            total += 1
            box = json.loads(reg["box_json"])
            sub = crop(image, box)
            processed, _ = apply_pipeline(sub, steps)
            per_engine = {}
            for eid, eng in engines.items():
                r = eng.recognize(processed, {**cfg.engine_base_options(eid), "mode": "roi"})
                per_engine[eid] = "" if r.error else r.text
            vote = majority_vote(per_engine, norm_profile)
            status = "agreed" if vote.agreed else "needs_review"
            if vote.agreed:
                agreed += 1
            else:
                needs_review += 1
            conn.execute(
                """UPDATE regions SET voted_text = ?, gt_status = ?, draft_json = ?
                   WHERE id = ?""",
                (vote.winner, status,
                 json.dumps(per_engine, ensure_ascii=False), reg["id"]),
            )
    conn.commit()
    return {"agreed": agreed, "needs_review": needs_review, "regions": total,
            "engines": list(engines.keys())}
