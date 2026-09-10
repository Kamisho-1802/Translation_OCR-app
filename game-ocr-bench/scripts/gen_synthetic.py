"""合成テスト画像を 1 枚生成する（実ゲーム画像が揃う前の M1 検証用）。

暗背景 + 明文字の HUD 風画像。auto_invert / 二値化前処理の動作確認に使える。
    python scripts/gen_synthetic.py data/game/images/0001.png
"""

from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np


def make_image(text: str = "HP 120/200") -> np.ndarray:
    img = np.full((120, 480, 3), 18, dtype=np.uint8)  # 暗背景
    cv2.putText(
        img, text, (20, 75), cv2.FONT_HERSHEY_SIMPLEX, 1.6, (245, 245, 245), 3, cv2.LINE_AA
    )
    return img


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/game/images/0001.png")
    text = sys.argv[2] if len(sys.argv) > 2 else "HP 120/200"
    out.parent.mkdir(parents=True, exist_ok=True)
    img = make_image(text)
    # PNG（ロスレス）で保存。日本語パス対策で imencode + tofile。
    ok, buf = cv2.imencode(".png", img)
    if not ok:
        print("PNG エンコードに失敗", file=sys.stderr)
        return 1
    buf.tofile(str(out))
    print(f"生成: {out}  text=\"{text}\"")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
