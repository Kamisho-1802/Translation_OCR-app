"""オプション・前処理条件の安定ハッシュ（runs.options_hash 等・§8 キャッシュ）。

dict をキー順にソートした JSON にしてから SHA-256 を取ることで、
同一条件が常に同じハッシュになるようにする（キャッシュ命中の前提）。
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(obj: Any) -> str:
    """キー順ソート・空白なしの決定論的 JSON 文字列。"""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def stable_hash(obj: Any) -> str:
    """dict/list などの安定 SHA-256（先頭 16 桁を返す）。"""
    payload = canonical_json(obj).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]
