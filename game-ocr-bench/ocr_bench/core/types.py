"""共通インターフェース（仕様書 §7）。

全エンジンアダプタはこのモジュールの型のみを介してやり取りする。
新エンジン追加時に adapters/ 以外を触らずに済むよう、ここを唯一の契約点とする。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

import numpy as np


@dataclass
class Box:
    """ピクセル座標の矩形。x, y は左上。"""

    x: int
    y: int
    w: int
    h: int

    def as_xyxy(self) -> tuple[int, int, int, int]:
        return (self.x, self.y, self.x + self.w, self.y + self.h)

    @classmethod
    def from_xywh(cls, box: list[int] | tuple[int, int, int, int]) -> "Box":
        x, y, w, h = box
        return cls(int(x), int(y), int(w), int(h))


@dataclass
class TextBlock:
    """検出された 1 テキスト領域。box/confidence はエンジンが返さない場合 None。"""

    text: str
    box: Box | None = None
    confidence: float | None = None


@dataclass
class OcrResult:
    """1 回の認識呼び出しの結果。例外もここに格納して返す（§7 規約）。"""

    engine_id: str
    mode: str  # 'fullscreen' | 'roi'
    text: str
    blocks: list[TextBlock] = field(default_factory=list)
    latency_ms: int = 0  # 推論のみ（前処理は含めない）
    preprocess_ms: int = 0
    raw: dict = field(default_factory=dict)
    error: str | None = None


@runtime_checkable
class OcrEngine(Protocol):
    """全エンジンが満たすプロトコル。

    - warmup: モデルロード + ダミー推論。レイテンシ統計から除外するために呼ぶ。
    - recognize: BGR の np.ndarray を受け取り OcrResult を返す。例外は捕捉して
      error に入れること（1 エンジンの失敗で全体を止めない）。
    """

    id: str

    def warmup(self) -> None: ...

    def recognize(self, image: np.ndarray, options: dict) -> OcrResult: ...
