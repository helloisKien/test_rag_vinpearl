"""DA10 — Phase 4: query embedding (bge-m3, GPU).

ĐỔI (sau diag): FlagEmbedding 1.4.0 lỗi `dtype` với transformers 4.44.2 → dùng
**sentence-transformers** SentenceTransformer('BAAI/bge-m3'). Diag xác nhận
cos(ST, corpus FlagEmbedding) = 1.0000 → KHỚP corpus, KHÔNG cần re-embed.
GPU fp16 (.half()) để vừa T2000 4GB cùng reranker. Singleton lazy-load.
"""
from __future__ import annotations
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.settings import settings  # noqa: E402

_model = None


def _get():
    global _model
    if _model is None:
        import torch
        from sentence_transformers import SentenceTransformer
        force_cpu = os.getenv("EMBED_FORCE_CPU", "0") == "1"
        dev = "cpu" if force_cpu else ("cuda" if torch.cuda.is_available() else "cpu")
        m = SentenceTransformer(settings.embed_model, device=dev)
        if dev == "cuda":
            try:
                m.half()  # fp16 ~1.1GB
            except Exception:
                pass
        _model = m
    return _model


def embed_query(text):
    v = _get().encode([text], normalize_embeddings=True)[0]
    return np.asarray(v, dtype=np.float32)
