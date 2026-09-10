"""GT 多数決（仕様書 §6）。

N エンジンの出力を正規化して集計し、過半数一致なら暫定確定、割れたら人手レビュー。
3 エンジン想定だが、2 エンジン（PaddleOCR 保留中）でも動くよう、閾値は (n//2)+1 とする
（n=2 で全一致、n=3 で 2 票）。
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from ..eval.normalize import normalize


@dataclass
class VoteResult:
    winner: str | None       # 暫定 GT（生テキスト）。割れたら None。
    agreed: bool             # 過半数一致したか
    top_votes: int
    n: int
    per_engine: dict[str, str]  # engine_id -> 生テキスト


def majority_vote(
    per_engine: dict[str, str], norm_profile: str = "strict"
) -> VoteResult:
    """エンジン別テキストを正規化キーで集計し、過半数一致を判定する。

    winner は多数派に属するエンジンのうち engine_id 昇順で最初の**生テキスト**。
    （casing など生の差異は残るため、監査・レビューで最終確認する。）
    """
    n = len(per_engine)
    if n == 0:
        return VoteResult(None, False, 0, 0, {})

    norm_of = {eid: normalize(txt, norm_profile) for eid, txt in per_engine.items()}
    counts = Counter(norm_of.values())
    top_key, top_votes = counts.most_common(1)[0]
    threshold = (n // 2) + 1
    agreed = top_votes >= threshold

    winner = None
    if agreed:
        for eid in sorted(per_engine):
            if norm_of[eid] == top_key:
                winner = per_engine[eid]
                break
    return VoteResult(winner=winner, agreed=agreed, top_votes=top_votes, n=n,
                      per_engine=dict(per_engine))
