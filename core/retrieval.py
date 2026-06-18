"""DA10 — Phase 4: Retrieval Core.

Luồng: SQL pre-filter (whitelist) -> BM25 (OpenSearch) ∥ Vector (Qdrant) [lọc whitelist]
       -> RRF fusion -> Cross-encoder rerank -> gom chunk->hotel (max score) -> top_k hotel.
Trả kèm stage_latencies (R13) cho monitoring. Sync + clients singleton (skeleton; API chạy
endpoint sync trong threadpool của FastAPI).
"""
from __future__ import annotations
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.settings import settings  # noqa: E402
from core.prefilter import sql_whitelist  # noqa: E402
from core.fusion import reciprocal_rank_fusion  # noqa: E402
from core.embedder import embed_query  # noqa: E402
from core.reranker import rerank  # noqa: E402

BM25_TOP = 50
VECTOR_TOP = 50
RRF_TOP = 15

_os = None
_qd = None


def _ms(t0):
    return round((time.perf_counter() - t0) * 1000, 1)


def os_client():
    global _os
    if _os is None:
        from opensearchpy import OpenSearch
        _os = OpenSearch([{"host": settings.os_host, "port": settings.os_port}], http_compress=True)
    return _os


def qd_client():
    global _qd
    if _qd is None:
        from qdrant_client import QdrantClient
        _qd = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)
    return _qd


def bm25_search(query, whitelist, size=BM25_TOP):
    must = [{"match": {"embed_text": query}}]
    bool_q = {"must": must}
    if whitelist is not None:
        bool_q["filter"] = [{"terms": {"hotel_id": list(whitelist)}}]
    res = os_client().search(index=settings.os_alias, body={"size": size, "query": {"bool": bool_q}})
    return [(h["_id"], h["_source"]) for h in res["hits"]["hits"]]


def vector_search(qvec, whitelist, limit=VECTOR_TOP):
    from qdrant_client.models import Filter, FieldCondition, MatchAny
    flt = None
    if whitelist is not None:
        flt = Filter(must=[FieldCondition(key="hotel_id", match=MatchAny(any=list(whitelist)))])
    res = qd_client().search(
        collection_name=settings.qdrant_collection,
        query_vector=qvec.tolist(), limit=limit, query_filter=flt, with_payload=True,
    )
    return [(p.payload["chunk_id"], p.payload) for p in res]


VALID_MODES = {"full_hybrid", "bm25_only", "vector_only", "hybrid_no_rerank"}


def search(query, filters=None, top_k=10, mode="full_hybrid"):
    """Trả dict: hotels[], chunks[], src{}, whitelist, stages_ms.

    mode:
      full_hybrid       — BM25 ∥ Vector → RRF → rerank  (default)
      bm25_only         — BM25 only → rerank
      vector_only       — Vector only → rerank
      hybrid_no_rerank  — BM25 ∥ Vector → RRF (score = RRF rank score, no rerank)
    """
    if mode not in VALID_MODES:
        mode = "full_hybrid"
    stages = {}

    t = time.perf_counter()
    wl = sql_whitelist(filters)
    stages["sql_filter"] = _ms(t)
    if wl is not None and len(wl) == 0:
        return {"hotels": [], "chunks": [], "src": {}, "whitelist": 0, "stages_ms": stages}

    # ── BM25 arm ──────────────────────────────────────────────────────────────
    bm: list = []
    if mode in ("full_hybrid", "bm25_only", "hybrid_no_rerank"):
        t = time.perf_counter()
        bm = bm25_search(query, wl)
        stages["os_bm25"] = _ms(t)
    else:
        stages["os_bm25"] = 0

    # ── Vector arm ────────────────────────────────────────────────────────────
    vec: list = []
    if mode in ("full_hybrid", "vector_only", "hybrid_no_rerank"):
        t = time.perf_counter()
        qvec = embed_query(query)
        stages["embed_query"] = _ms(t)
        t = time.perf_counter()
        vec = vector_search(qvec, wl)
        stages["qdrant_vector"] = _ms(t)
    else:
        stages["qdrant_vector"] = 0

    # ── Fusion ────────────────────────────────────────────────────────────────
    t = time.perf_counter()
    if mode == "bm25_only":
        top = [c for c, _ in bm[:RRF_TOP]]
    elif mode == "vector_only":
        top = [c for c, _ in vec[:RRF_TOP]]
    else:
        fused = reciprocal_rank_fusion([[c for c, _ in bm], [c for c, _ in vec]])
        top = list(fused)[:RRF_TOP]
    stages["rrf"] = _ms(t)

    # gom _source (text) cho top chunk: bm25 có sẵn; chunk chỉ-vector -> mget OpenSearch
    src = {c: s for c, s in bm}
    missing = [c for c in top if c not in src]
    if missing:
        docs = os_client().mget(index=settings.os_alias, body={"ids": missing})["docs"]
        for d in docs:
            if d.get("found"):
                src[d["_id"]] = d["_source"]

    valid = [c for c in top if c in src]

    # ── Rerank or score by position ───────────────────────────────────────────
    if mode == "hybrid_no_rerank":
        # RRF rank position as proxy score (higher = better)
        stages["rerank"] = 0
        reranked = [(c, float(len(valid) - i)) for i, c in enumerate(valid)]
    else:
        t = time.perf_counter()
        scores = rerank(query, [src[c]["text"] for c in valid])
        stages["rerank"] = _ms(t)
        reranked = sorted(zip(valid, scores), key=lambda x: -x[1])

    # gom chunk -> hotel (điểm = max score của chunk thuộc hotel)
    hotel_best = {}
    for cid, sc in reranked:
        hid = src[cid]["hotel_id"]
        if hid not in hotel_best or sc > hotel_best[hid]["score"]:
            hotel_best[hid] = {"score": float(sc), "chunk_id": cid, "source_type": src[cid]["source_type"]}
    hotels = [{"hotel_id": hid, **info} for hid, info in
              sorted(hotel_best.items(), key=lambda x: -x[1]["score"])[:top_k]]

    return {
        "hotels": hotels,
        "chunks": [{"chunk_id": c, "reranker_score": s} for c, s in reranked],
        "src": src,
        "whitelist": (len(wl) if wl is not None else None),
        "stages_ms": stages,
        "search_mode": mode,
    }
