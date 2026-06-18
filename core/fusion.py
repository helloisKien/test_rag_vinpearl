"""DA10 — Phase 4: Reciprocal Rank Fusion (RRF)."""
from __future__ import annotations
from collections import defaultdict


def reciprocal_rank_fusion(ranked_lists, k=60):
    """ranked_lists: list các list chunk_id (đã xếp hạng). Trả dict {chunk_id: rrf_score} giảm dần."""
    scores = defaultdict(float)
    for lst in ranked_lists:
        for rank, cid in enumerate(lst, 1):
            scores[cid] += 1.0 / (k + rank)
    return dict(sorted(scores.items(), key=lambda x: -x[1]))
