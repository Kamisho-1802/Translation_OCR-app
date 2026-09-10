"""複数領域の合成画像 + regions JSON を生成（M4 ROI/検出評価の検証用）。

実ゲーム画像が揃う前に、ROI 切り出し・検出 Recall/Precision・誤検出量・全画面 GT の
自動生成までを通しで確認するためのダミーデータ。
    python scripts/gen_synthetic_multi.py 0002
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np

# (region_id, text, text_type, proper_nouns, draw_org(x, baseline_y))
_ITEMS = [
    ("r1", "HP 120/200", "hud", [], (20, 55)),
    ("r2", "EASTMARCH KEEP", "map_label", ["EASTMARCH KEEP"], (20, 150)),
]
_FONT = cv2.FONT_HERSHEY_SIMPLEX
_SCALE = 1.0
_THICK = 2


def _text_box(text: str, org: tuple[int, int]) -> tuple[int, int, int, int]:
    """描画テキストの外接矩形 (x,y,w,h) を getTextSize から算出（GT 箱を実描画に一致させる）。"""
    (w, h), baseline = cv2.getTextSize(text, _FONT, _SCALE, _THICK)
    x, by = org
    return (x, by - h, w, h + baseline)


_REGIONS = [(rid, txt, tt, pn, _text_box(txt, org)) for rid, txt, tt, pn, org in _ITEMS]


def main() -> int:
    stem = sys.argv[1] if len(sys.argv) > 1 else "0002"
    root = Path("data/game")
    img = np.full((220, 480, 3), 18, dtype=np.uint8)  # 暗背景
    for (rid, text, _tt, _pn, _box), (_, _, _, _, org) in zip(_REGIONS, _ITEMS):
        cv2.putText(img, text, org, _FONT, _SCALE, (240, 240, 240), _THICK, cv2.LINE_AA)

    (root / "images").mkdir(parents=True, exist_ok=True)
    (root / "regions").mkdir(parents=True, exist_ok=True)
    ok, buf = cv2.imencode(".png", img)
    buf.tofile(str(root / "images" / f"{stem}.png"))

    doc = {
        "image": f"{stem}.png",
        "reading_order": [r[0] for r in _REGIONS],
        "regions": [
            {"id": r[0], "box": list(r[4]), "text": r[1], "text_type": r[2], "proper_nouns": r[3]}
            for r in _REGIONS
        ],
    }
    (root / "regions" / f"{stem}.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"生成: images/{stem}.png, regions/{stem}.json（{len(_REGIONS)} 領域）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
