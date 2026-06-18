"""DA10 — Phase 4: cross-encoder rerank (bge-reranker-v2-m3) trên GPU fp16.

ĐỔI (sau diag): FlagReranker (FlagEmbedding 1.4.0) dính cùng lỗi `dtype` với transformers 4.44.2.
Dùng **sentence-transformers CrossEncoder** GPU fp16 — diag xác nhận chạy OK, nhanh (vs ~15s CPU).
predict() trả điểm 0..1 (sigmoid) — khớp relevance_score API. Singleton lazy-load.
Fallback CPU: env RERANK_FORCE_CPU=1.
"""
from __future__ import annotations
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.settings import settings  # noqa: E402

_model = None


def _get():
    global _model
    if _model is None:
        import torch
        from sentence_transformers import CrossEncoder
        force_cpu = os.getenv("RERANK_FORCE_CPU", "0") == "1"
        dev = "cpu" if force_cpu else ("cuda" if torch.cuda.is_available() else "cpu")
        m = CrossEncoder(settings.rerank_model, device=dev, max_length=512)
        if dev == "cuda":
            try:
                m.model.half()  # fp16 ~1.1GB
            except Exception:
                pass
        _model = m
    return _model


def rerank(query, passages):
    """passages: list[str] -> list[float] điểm relevance (0..1)."""
    if not passages:
        return []
    scores = _get().predict([(query, p) for p in passages])
    return [float(s) for s in scores]
