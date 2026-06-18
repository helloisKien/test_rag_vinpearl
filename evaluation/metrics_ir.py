"""DA10 — Phase 9: IR metrics.

Tính Recall@K, MRR@K, NDCG@K, Hit@K, Zero-result cho từng query
rồi aggregate (mean) theo nhóm và toàn bộ.

Không dùng ranx để tránh dependency nặng; tự implement theo công thức chuẩn.
relevant_hotel_ids trong golden set đã SẮP XẾP THEO ĐỘ LIÊN QUAN GIẢM DẦN
→ dùng graded relevance: vị trí 0 = điểm cao nhất.
"""
from __future__ import annotations

import math
from typing import Dict, List


# ─────────────────────────────────────────────────────────────────────────────
# Per-query metrics
# ─────────────────────────────────────────────────────────────────────────────

def recall_at_k(relevant: List[int], retrieved: List[int], k: int) -> float:
    if not relevant:
        return 0.0
    hits = len(set(relevant) & set(retrieved[:k]))
    return hits / len(relevant)


def hit_at_k(relevant: List[int], retrieved: List[int], k: int) -> float:
    """Binary: 1 nếu có ít nhất 1 GT trong top-k."""
    if not relevant:
        return 0.0
    rel_set = set(relevant)
    return 1.0 if any(r in rel_set for r in retrieved[:k]) else 0.0


def mrr_at_k(relevant: List[int], retrieved: List[int], k: int) -> float:
    rel_set = set(relevant)
    for i, doc in enumerate(retrieved[:k], 1):
        if doc in rel_set:
            return 1.0 / i
    return 0.0


def ndcg_at_k(relevant: List[int], retrieved: List[int], k: int) -> float:
    """NDCG@K với graded relevance: vị trí 0 trong relevant[] = score cao nhất."""
    n = len(relevant)
    if n == 0:
        return 0.0
    # graded: vị trí i -> score = (n - i)
    rel_score = {hotel_id: (n - i) for i, hotel_id in enumerate(relevant)}

    dcg = sum(
        rel_score[doc] / math.log2(rank + 1)
        for rank, doc in enumerate(retrieved[:k], 1)
        if doc in rel_score
    )

    ideal_scores = sorted(rel_score.values(), reverse=True)[:k]
    idcg = sum(s / math.log2(rank + 1) for rank, s in enumerate(ideal_scores, 1))

    return dcg / idcg if idcg > 0 else 0.0


def compute_query_metrics(
    relevant: List[int],
    retrieved: List[int],
    k_primary: int = 5,
    k_secondary: int = 10,
) -> Dict[str, float]:
    """Trả full metric dict cho 1 query."""
    return {
        f"recall@{k_primary}": recall_at_k(relevant, retrieved, k_primary),
        f"recall@{k_secondary}": recall_at_k(relevant, retrieved, k_secondary),
        f"hit@{k_primary}": hit_at_k(relevant, retrieved, k_primary),
        f"mrr@{k_secondary}": mrr_at_k(relevant, retrieved, k_secondary),
        f"ndcg@{k_secondary}": ndcg_at_k(relevant, retrieved, k_secondary),
        "zero_result": 1.0 if not retrieved else 0.0,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Chunk-level metrics (chỉ khi relevant_chunk_ids đã điền)
# ─────────────────────────────────────────────────────────────────────────────

def chunk_recall_at_k(relevant_chunks: List[str], retrieved_chunks: List[str], k: int) -> float:
    if not relevant_chunks:
        return 0.0
    hits = len(set(relevant_chunks) & set(retrieved_chunks[:k]))
    return hits / len(relevant_chunks)


def citation_coverage(relevant_chunks: List[str], citations: List[str]) -> float:
    if not relevant_chunks:
        return 0.0
    hits = len(set(relevant_chunks) & set(citations))
    return hits / len(relevant_chunks)


# ─────────────────────────────────────────────────────────────────────────────
# Aggregation
# ─────────────────────────────────────────────────────────────────────────────

def aggregate(rows: List[Dict[str, float]]) -> Dict[str, float]:
    """Mean across queries. Bỏ qua key nếu tất cả None."""
    if not rows:
        return {}
    keys = rows[0].keys()
    result = {}
    for k in keys:
        vals = [r[k] for r in rows if r.get(k) is not None]
        result[k] = sum(vals) / len(vals) if vals else 0.0
    return result


def p95(values: List[float]) -> float:
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    idx = math.ceil(0.95 * len(sorted_vals)) - 1
    return sorted_vals[max(0, idx)]
