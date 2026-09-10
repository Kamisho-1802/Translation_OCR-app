"""実行ランナー（仕様書 §8 実行と評価の分離 / M1 骨組み）。

責務:
  - サンプルを DB へ登録（image_sha256 で冪等）
  - run 行を作成（engine/mode/options/preprocess のハッシュを記録）
  - 前処理を適用してアダプタを呼び、results へ保存
  - 同一条件はキャッシュ命中で推論 0 回（受け入れ基準）

M1 段階では fullscreen モード・単一エンジン・raw/tuned 前処理の最小経路のみを通す。
roi モードや検出評価は M4 で runner を拡張する。
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from ..core import cache, config as cfg
from ..core.db import connect
from ..core.hashing import stable_hash
from ..core.images import load_bgr, sha256_of_file
from ..core.registry import create
from ..core.types import Box, OcrResult, TextBlock
from ..preprocess.pipeline import apply_pipeline


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _git_commit() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).resolve().parents[2],
        )
        return out.stdout.strip() or None
    except Exception:
        return None


def register_sample(conn, image_path: str | Path, meta: dict | None = None) -> int:
    """samples に登録（image_sha256 で冪等）。既存なら id を返す。"""
    image_path = Path(image_path)
    sha = sha256_of_file(image_path)
    row = conn.execute(
        "SELECT id FROM samples WHERE image_sha256 = ?", (sha,)
    ).fetchone()
    if row is not None:
        return int(row["id"])
    cur = conn.execute(
        "INSERT INTO samples (file_path, image_sha256, gt_text, meta) VALUES (?, ?, ?, ?)",
        (str(image_path), sha, None, json.dumps(meta or {}, ensure_ascii=False)),
    )
    conn.commit()
    return int(cur.lastrowid)


def _rescale_boxes_to_input(result: OcrResult, input_shape, processed_shape) -> None:
    """予測ボックスを前処理後座標から前処理前（入力）座標へ写像する（インプレース）。

    upscale などの幾何変換で座標がずれるため、検出評価を入力画像座標で正しく行えるよう
    戻す。fullscreen では原画像座標、roi では切り出し座標に揃う。
    """
    ih, iw = input_shape[:2]
    ph, pw = processed_shape[:2]
    if pw == 0 or ph == 0 or (pw == iw and ph == ih):
        return
    sx, sy = iw / pw, ih / ph
    for b in result.blocks:
        if b.box is not None:
            b.box = Box(int(b.box.x * sx), int(b.box.y * sy),
                        int(b.box.w * sx), int(b.box.h * sy))


def _blocks_to_json(blocks: list[TextBlock]) -> str:
    payload = [
        {
            "text": b.text,
            "box": [b.box.x, b.box.y, b.box.w, b.box.h] if b.box else None,
            "confidence": b.confidence,
        }
        for b in blocks
    ]
    return json.dumps(payload, ensure_ascii=False)


def run_single(
    conn,
    *,
    engine_id: str,
    image_path: str | Path,
    mode: str = "fullscreen",
    preprocess: str | list = "raw",
    options: dict | None = None,
    device: str = "cpu",
    note: str = "",
) -> dict:
    """1 エンジン × 1 画像 × 1 前処理条件を実行し results に保存する。

    戻り値: {"result_id", "cached", "error", "text"} の要約 dict。
    """
    steps = cfg.resolve_preprocess(preprocess)
    base_opts = cfg.engine_base_options(engine_id)
    merged_opts = {**base_opts, **(options or {}), "mode": mode}

    options_hash = stable_hash(merged_opts)
    preprocess_hash = stable_hash(steps)

    sample_id = register_sample(conn, image_path)
    image = load_bgr(image_path)
    from ..core.images import sha256_of_file as _sha

    image_sha = _sha(image_path)

    # --- キャッシュ照会（fullscreen は region_id=None）---
    cached = cache.find_cached_result(
        conn,
        image_sha256=image_sha,
        engine_id=engine_id,
        mode=mode,
        options_hash=options_hash,
        preprocess_hash=preprocess_hash,
        region_id=None,
    )
    if cached is not None:
        return {
            "result_id": int(cached["id"]),
            "cached": True,
            "error": cached["error"],
            "text": cached["pred_text"],
        }

    # --- run 行を作成 ---
    cur = conn.execute(
        """INSERT INTO runs
           (started_at, engine_id, mode, options_json, options_hash,
            preprocess_json, preprocess_hash, git_commit, device, note)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            _now(),
            engine_id,
            mode,
            json.dumps(merged_opts, ensure_ascii=False),
            options_hash,
            json.dumps(steps, ensure_ascii=False),
            preprocess_hash,
            _git_commit(),
            device,
            note,
        ),
    )
    run_id = int(cur.lastrowid)

    # --- 前処理 → 推論 ---
    processed, preprocess_ms = apply_pipeline(image, steps)
    engine = create(engine_id)
    engine.warmup()  # M1 は都度ウォームアップ（M3 で計測規約を精緻化）
    result: OcrResult = engine.recognize(processed, merged_opts)
    _rescale_boxes_to_input(result, image.shape, processed.shape)

    conn.execute(
        """INSERT INTO results
           (run_id, sample_id, region_id, pred_text, blocks_json, raw_json,
            latency_ms, preprocess_ms, error)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            run_id,
            sample_id,
            None,
            result.text,
            _blocks_to_json(result.blocks),
            json.dumps({"note": "raw omitted in M1"}, ensure_ascii=False),
            result.latency_ms,
            preprocess_ms,
            result.error,
        ),
    )
    result_id = int(conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"])
    conn.execute("UPDATE runs SET finished_at = ? WHERE id = ?", (_now(), run_id))
    conn.commit()

    return {
        "result_id": result_id,
        "cached": False,
        "error": result.error,
        "text": result.text,
    }


# ---------------------------------------------------------------------------
# バッチ実行（M3 レイテンシ/FPS + M4 ROI モード）
# ---------------------------------------------------------------------------

def _create_run(conn, engine_id, mode, merged_opts, options_hash, steps,
                preprocess_hash, device, note) -> int:
    cur = conn.execute(
        """INSERT INTO runs
           (started_at, engine_id, mode, options_json, options_hash,
            preprocess_json, preprocess_hash, git_commit, device, note)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (_now(), engine_id, mode, json.dumps(merged_opts, ensure_ascii=False),
         options_hash, json.dumps(steps, ensure_ascii=False), preprocess_hash,
         _git_commit(), device, note),
    )
    return int(cur.lastrowid)


def _persist(conn, run_id, sample_id, region_id, result: OcrResult, preprocess_ms: int) -> int:
    conn.execute(
        """INSERT INTO results
           (run_id, sample_id, region_id, pred_text, blocks_json, raw_json,
            latency_ms, preprocess_ms, error)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (run_id, sample_id, region_id, result.text, _blocks_to_json(result.blocks),
         json.dumps({}, ensure_ascii=False), result.latency_ms, preprocess_ms,
         result.error),
    )
    return int(conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"])


def _load_regions(conn, sample_id: int) -> list:
    return conn.execute(
        "SELECT id, region_key, box_json FROM regions WHERE sample_id = ? ORDER BY order_index",
        (sample_id,),
    ).fetchall()


def _latency_stats(latencies: list[int]) -> dict:
    """p50/p95/mean と FPS（1000/mean）。ウォームアップは呼び出し側で除外済み。"""
    if not latencies:
        return {"n": 0, "p50": None, "p95": None, "mean": None, "fps": None}
    import numpy as np

    arr = np.array(latencies, dtype=float)
    mean = float(arr.mean())
    return {
        "n": len(latencies),
        "p50": float(np.percentile(arr, 50)),
        "p95": float(np.percentile(arr, 95)),
        "mean": mean,
        "fps": (1000.0 / mean) if mean > 0 else None,
    }


def _select_samples(conn, sample_ids, limit):
    if sample_ids:
        q = "SELECT id, file_path, image_sha256 FROM samples WHERE id IN (%s) ORDER BY id" % (
            ",".join("?" for _ in sample_ids)
        )
        rows = conn.execute(q, list(sample_ids)).fetchall()
    else:
        q = "SELECT id, file_path, image_sha256 FROM samples ORDER BY id"
        if limit:
            q += f" LIMIT {int(limit)}"
        rows = conn.execute(q).fetchall()
    return rows


def run_batch(
    conn,
    *,
    engine_ids: list[str],
    modes: list[str],
    presets: list[str],
    sample_ids: list[int] | None = None,
    limit: int | None = None,
    warmup_iters: int = 3,
    device: str = "cpu",
    options: dict | None = None,
    note: str = "",
) -> dict:
    """エンジンを使い回して データセット全体を実行する（§4.4 ウォームアップ規約）。

    - エンジンは (engine_id ごとに) 1 度だけ生成し、warmup_iters 回ダミー推論して破棄。
    - fullscreen: 画像全体を前処理して認識。
    - roi: regions を切り出し → 前処理 → 認識（region_id 付きで保存）。
    - キャッシュ命中は推論を行わず、レイテンシ統計にも含めない。
    戻り値: 条件ごとの latency/FPS 統計とカウンタ。
    """
    from ..core.images import crop

    samples = _select_samples(conn, sample_ids, limit)
    stats: dict[str, dict] = {}
    counters = {"inferences": 0, "cache_hits": 0, "errors": 0, "results": 0}

    for engine_id in engine_ids:
        base_opts = cfg.engine_base_options(engine_id)
        engine = create(engine_id)
        for _ in range(max(0, warmup_iters)):
            engine.warmup()

        for mode in modes:
            for preset in presets:
                steps = cfg.resolve_preprocess(preset)
                merged_opts = {**base_opts, **(options or {}), "mode": mode}
                options_hash = stable_hash(merged_opts)
                preprocess_hash = stable_hash(steps)
                run_id = _create_run(conn, engine_id, mode, merged_opts, options_hash,
                                     steps, preprocess_hash, device, note)
                latencies: list[int] = []

                for s in samples:
                    image = load_bgr(s["file_path"])

                    if mode == "fullscreen":
                        targets = [(None, image)]
                    else:  # roi: 各領域を切り出す
                        targets = []
                        for reg in _load_regions(conn, s["id"]):
                            box = json.loads(reg["box_json"])
                            targets.append((reg["id"], crop(image, box)))

                    for region_id, sub in targets:
                        hit = cache.find_cached_result(
                            conn, image_sha256=s["image_sha256"], engine_id=engine_id,
                            mode=mode, options_hash=options_hash,
                            preprocess_hash=preprocess_hash, region_id=region_id)
                        if hit is not None:
                            counters["cache_hits"] += 1
                            counters["results"] += 1
                            continue
                        processed, pp_ms = apply_pipeline(sub, steps)
                        result = engine.recognize(processed, merged_opts)
                        _rescale_boxes_to_input(result, sub.shape, processed.shape)
                        _persist(conn, run_id, s["id"], region_id, result, pp_ms)
                        counters["results"] += 1
                        if result.error:
                            counters["errors"] += 1
                        else:
                            counters["inferences"] += 1
                            latencies.append(result.latency_ms)

                conn.execute("UPDATE runs SET finished_at = ? WHERE id = ?", (_now(), run_id))
                conn.commit()
                stats[f"{engine_id}/{mode}/{preset}"] = {
                    "run_id": run_id, **_latency_stats(latencies)}

    return {"counters": counters, "stats": stats}
