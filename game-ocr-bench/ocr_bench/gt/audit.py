"""GT 監査（仕様書 §6 注意）。

3 エンジンが揃って誤読する可能性があるため、確定済み GT を抜き取り監査する。
監査率は既定 20%（§6）。font_style が fantasy / pixel のサンプルを優先する
（装飾・ピクセルフォントは 3 エンジンが同じ形で崩れやすいため）。
"""

from __future__ import annotations

import json
import random


def select_for_audit(
    conn,
    sample_rate: float = 0.2,
    priority_font_styles: tuple[str, ...] = ("fantasy", "pixel"),
    seed: int | None = 0,
) -> list:
    """確定済み領域から監査対象を選ぶ。優先フォントを先に、残りをランダム抽出。

    戻り値: regions 行のリスト（sample の meta も含む）。
    """
    rows = conn.execute(
        """SELECT r.id, r.sample_id, r.region_key, r.gt_text, s.meta, s.file_path
           FROM regions r JOIN samples s ON s.id = r.sample_id
           WHERE r.gt_status = 'confirmed'"""
    ).fetchall()
    if not rows:
        return []

    def font_of(meta_json):
        try:
            return (json.loads(meta_json or "{}") or {}).get("font_style")
        except Exception:
            return None

    priority = [r for r in rows if font_of(r["meta"]) in priority_font_styles]
    rest = [r for r in rows if font_of(r["meta"]) not in priority_font_styles]

    n_target = max(1, round(len(rows) * sample_rate))
    rng = random.Random(seed)
    rng.shuffle(rest)

    selected = priority[:n_target]
    if len(selected) < n_target:
        selected += rest[: n_target - len(selected)]
    return selected
