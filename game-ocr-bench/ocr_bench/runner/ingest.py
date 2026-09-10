"""データセット取り込み（仕様書 §2.4 / §8）。

images/ の PNG を samples に登録し、regions/*.json があれば regions に取り込む。
**全画面 GT（samples.gt_text）は regions の reading_order から自動生成する**
（受け入れ基準: 手書きの二重管理を発生させない）。
"""

from __future__ import annotations

import json
from pathlib import Path

from ..core.images import sha256_of_file
from .runner import register_sample


def _full_gt_from_regions(regions_doc: dict) -> str:
    """reading_order に従って領域テキストを連結し、全画面 GT を作る。"""
    by_id = {r["id"]: r for r in regions_doc.get("regions", [])}
    order = regions_doc.get("reading_order") or [r["id"] for r in regions_doc.get("regions", [])]
    lines = [by_id[rid]["text"] for rid in order if rid in by_id]
    return "\n".join(lines)


def ingest_sample(
    conn,
    image_path: str | Path,
    regions_json_path: str | Path | None = None,
    meta: dict | None = None,
) -> int:
    """1 サンプルを取り込み、regions と全画面 GT を更新して sample_id を返す。"""
    image_path = Path(image_path)
    doc = None
    if regions_json_path and Path(regions_json_path).exists():
        doc = json.loads(Path(regions_json_path).read_text(encoding="utf-8"))
    # 条件タグ(meta)は引数優先、無ければ regions JSON の meta を使う（annotate ツール出力）。
    if meta is None and doc is not None:
        meta = doc.get("meta")

    sample_id = register_sample(conn, image_path, meta=meta)
    # 既存サンプルにも meta を反映（再取り込みでタグ更新できるように）。
    if meta:
        conn.execute("UPDATE samples SET meta = ? WHERE id = ?",
                     (json.dumps(meta, ensure_ascii=False), sample_id))

    if doc is not None:
        order = doc.get("reading_order") or [r["id"] for r in doc.get("regions", [])]
        order_index = {rid: i for i, rid in enumerate(order)}
        for r in doc.get("regions", []):
            conn.execute(
                """INSERT INTO regions
                   (sample_id, region_key, box_json, gt_text, text_type,
                    proper_nouns, order_index)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(sample_id, region_key) DO UPDATE SET
                     box_json=excluded.box_json, gt_text=excluded.gt_text,
                     text_type=excluded.text_type, proper_nouns=excluded.proper_nouns,
                     order_index=excluded.order_index""",
                (
                    sample_id,
                    r["id"],
                    json.dumps(r["box"]),
                    r.get("text", ""),
                    r.get("text_type"),
                    json.dumps(r.get("proper_nouns", []), ensure_ascii=False),
                    order_index.get(r["id"], 0),
                ),
            )
        # 全画面 GT を regions から自動生成。
        full_gt = _full_gt_from_regions(doc)
        conn.execute("UPDATE samples SET gt_text = ? WHERE id = ?", (full_gt, sample_id))

    conn.commit()
    return sample_id


def ingest_dataset(
    conn, images_dir: str | Path, regions_dir: str | Path | None = None
) -> list[int]:
    """images_dir の PNG を全取り込み。同名の regions/*.json があれば併せて取り込む。"""
    images_dir = Path(images_dir)
    regions_dir = Path(regions_dir) if regions_dir else None
    ids: list[int] = []
    for png in sorted(images_dir.glob("*.png")):
        rj = None
        if regions_dir:
            cand = regions_dir / (png.stem + ".json")
            rj = cand if cand.exists() else None
        ids.append(ingest_sample(conn, png, rj))
    return ids
