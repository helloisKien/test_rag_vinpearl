"""DA10 — Phase 7: Context builder.

Luồng:
  1. Lấy tất cả chunk của hotel từ OpenSearch (term hotel_id, size=100)
  2. Rerank chunk theo query (bge-reranker-v2-m3)
  3. Chọn top-K chunk cho đến max_context_tokens
  4. Build context_text (concat bằng "\\n---\\n"), citations[], chunks[]
  5. Fetch HotelMetadata từ Postgres (hotels + rooms + nearby + activities)
  6. Token info qua tiktoken cl100k_base (nếu include_token_info=True)
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import settings
from core.reranker import rerank as _rerank

_os_client = None


def _os():
    global _os_client
    if _os_client is None:
        from opensearchpy import OpenSearch
        _os_client = OpenSearch(
            [{"host": settings.os_host, "port": settings.os_port}],
            http_compress=True,
        )
    return _os_client


def _count_tokens(text: str) -> int:
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        return max(1, len(text) // 4)


def _fetch_hotel_chunks(hotel_id: int, size: int = 100) -> list[dict]:
    """Lấy tất cả chunk của hotel từ OpenSearch."""
    res = _os().search(
        index=settings.os_alias,
        body={
            "size": size,
            "query": {"term": {"hotel_id": hotel_id}},
            "_source": True,
        },
    )
    chunks = []
    for hit in res["hits"]["hits"]:
        src = hit["_source"]
        chunks.append({
            "chunk_id": hit["_id"],
            "text": src.get("text", ""),
            "source_type": src.get("source_type", ""),
            "source_table": src.get("source_table", ""),
            "source_column": src.get("source_column"),
            "record_id": src.get("record_id"),
            "hotel_id": src.get("hotel_id"),
            "lang": src.get("lang", "vi"),
        })
    return chunks


def fetch_hotel_metadata(hotel_id: int) -> dict | None:
    """Fetch full HotelMetadata từ Postgres. Trả None nếu hotel không tồn tại."""
    import psycopg2
    import psycopg2.extras

    conn = psycopg2.connect(settings.pg_dsn)
    meta: dict = {}
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cur.execute(
            """
            SELECT h.*, COALESCE(MIN(r.price), 0) AS price_from
            FROM hotels h
            LEFT JOIN rooms r ON r.hotel_id = h.id
            WHERE h.id = %s
            GROUP BY h.id
            """,
            (hotel_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        row = dict(row)

        useful_info = row.get("useful_info") or {}
        policy_raw = (
            useful_info.get("policyNotes")
            or useful_info.get("policy_notes")
            or useful_info.get("hotel_policy", {}).get("policyNotes")
            or []
        )
        if isinstance(policy_raw, str):
            policy_raw = [policy_raw]

        meta = {
            "hotel_id": int(row["id"]),
            "name": row.get("name") or "",
            "accommodation_type": row.get("accommodation_type") or "",
            "star_rating": float(row.get("star_rating") or 0),
            "is_luxury": bool(row.get("is_luxury")),
            "address": row.get("address") or "",
            "city": row.get("city") or "",
            "latitude": float(row.get("latitude") or 0),
            "longitude": float(row.get("longitude") or 0),
            "review_score": float(row.get("review_score") or 0),
            "review_count": int(row.get("review_count") or 0),
            "reviews_detail": row.get("reviews_detail") or {},
            "description": row.get("description") or "",
            "amenities": row.get("amenities") or [],
            "suitable_for": row.get("suitable_for") or [],
            "policy_notes": policy_raw,
            "useful_info": useful_info,
            "price_from": float(row.get("price_from") or 0),
            "images": row.get("images") or [],
            "source_url": row.get("source_url") or "",
        }

        cur.execute(
            """
            SELECT id, room_type_id, name, price, room_size, max_occupancy,
                   bed_type, room_view, room_amenities, images, review_score
            FROM rooms WHERE hotel_id = %s ORDER BY price
            """,
            (hotel_id,),
        )
        meta["rooms"] = [
            {
                "id": int(r["id"]),
                "room_type_id": int(r["room_type_id"] or 0),
                "name": r.get("name") or "",
                "price": float(r.get("price") or 0),
                "room_size": r.get("room_size") or "",
                "max_occupancy": int(r.get("max_occupancy") or 0),
                "bed_type": r.get("bed_type") or "",
                "room_view": r.get("room_view"),
                "room_amenities": r.get("room_amenities") or [],
                "images": r.get("images") or [],
                "review_score": float(r.get("review_score") or 0),
            }
            for r in cur.fetchall()
        ]

        cur.execute(
            "SELECT id, name, type, distance_km FROM nearby_places WHERE hotel_id = %s ORDER BY distance_km",
            (hotel_id,),
        )
        meta["nearby_places"] = [
            {
                "id": int(r["id"]),
                "name": r.get("name") or "",
                "type": r.get("type") or "",
                "distance_km": float(r.get("distance_km") or 0),
            }
            for r in cur.fetchall()
        ]

        cur.execute(
            "SELECT id, title, description, price_amount, review_score FROM activities WHERE hotel_id = %s",
            (hotel_id,),
        )
        meta["activities"] = [
            {
                "id": int(r["id"]),
                "title": r.get("title") or "",
                "description": r.get("description") or "",
                "price_amount": float(r.get("price_amount") or 0),
                "review_score": float(r.get("review_score") or 0),
            }
            for r in cur.fetchall()
        ]

        cur.close()
    finally:
        conn.close()
    return meta


def build_context(
    hotel_id: int,
    query: str,
    max_context_tokens: int = 1500,
    include_chunks: bool = True,
    include_token_info: bool = False,
    focus_aspects: list[str] | None = None,  # reserved — not used in skeleton
) -> dict:
    """Build context package (chunks, context_text, citations, metadata).

    Trả dict:
      chunks[], context_text, citations[], metadata{}, token_info?, stages_ms{}
    """
    stages: dict = {}

    # 1. Fetch chunks từ OpenSearch
    t = time.perf_counter()
    raw_chunks = _fetch_hotel_chunks(hotel_id)
    stages["os_fetch_ms"] = round((time.perf_counter() - t) * 1000, 1)

    if not raw_chunks:
        meta = fetch_hotel_metadata(hotel_id)
        return {
            "chunks": [],
            "context_text": "",
            "citations": [],
            "metadata": meta or {},
            "token_info": None,
            "stages_ms": stages,
        }

    # 2. Rerank chunks theo query
    t = time.perf_counter()
    passages = [c["text"] for c in raw_chunks]
    scores = _rerank(query, passages)
    stages["rerank_ms"] = round((time.perf_counter() - t) * 1000, 1)

    ranked = sorted(zip(raw_chunks, scores), key=lambda x: -x[1])

    # 3. Chọn top-K theo max_context_tokens (luôn lấy ít nhất 1)
    selected: list[tuple[dict, float]] = []
    total_tok = 0
    for chunk, score in ranked:
        tok = _count_tokens(chunk["text"])
        if total_tok + tok > max_context_tokens and selected:
            break
        selected.append((chunk, score))
        total_tok += tok

    # 4. context_text
    context_text = "\n---\n".join(c["text"] for c, _ in selected)

    # 5. RetrievedChunk list
    chunks_out: list[dict] = []
    if include_chunks:
        for chunk, score in selected:
            chunks_out.append({
                "chunk_id": chunk["chunk_id"],
                "text": chunk["text"],
                "source_type": chunk["source_type"],
                "scores": {
                    "rrf_score": 0.0,
                    "reranker_score": round(float(score), 4),
                },
                "payload": {
                    "hotel_id": chunk["hotel_id"],
                    "source_table": chunk["source_table"],
                    "source_column": chunk.get("source_column"),
                    "record_id": chunk.get("record_id"),
                    "lang": chunk.get("lang", "vi"),
                },
            })

    # 6. Citations
    citations = [
        {
            "citation_id": f"cit-{i + 1:03d}",
            "chunk_id": chunk["chunk_id"],
            "source_type": chunk["source_type"],
            "text_snippet": chunk["text"][:200],
            "relevance_score": round(float(score), 4),
            "metadata": {
                "source_table": chunk.get("source_table", ""),
                "source_column": chunk.get("source_column"),
                "record_id": chunk.get("record_id"),
            },
        }
        for i, (chunk, score) in enumerate(selected)
    ]

    # 7. Metadata từ Postgres
    t = time.perf_counter()
    meta = fetch_hotel_metadata(hotel_id) or {}
    stages["pg_metadata_ms"] = round((time.perf_counter() - t) * 1000, 1)

    # 8. Token info
    token_info = None
    if include_token_info:
        meta_text = str(meta)
        ctx_tok = _count_tokens(context_text)
        meta_tok = _count_tokens(meta_text)
        try:
            import tiktoken
            model_name = "cl100k_base"
        except ImportError:
            model_name = "char_estimate_div4"
        token_info = {
            "context_text_tokens": ctx_tok,
            "metadata_tokens": meta_tok,
            "total_tokens": ctx_tok + meta_tok,
            "model_used_for_count": model_name,
        }

    return {
        "chunks": chunks_out,
        "context_text": context_text,
        "citations": citations,
        "metadata": meta,
        "token_info": token_info,
        "stages_ms": stages,
    }
