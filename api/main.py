"""DA10 — SearchAPI + ContextAPI + Observability.

Endpoints:
  POST /search       → SearchResponse
  POST /context      → ContextResponse
  GET  /health       → shallow liveness
  GET  /health/deep  → dependency ping + gauge update
  GET  /metrics      → Prometheus metrics

Chạy: python run_server.py
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import time
import uuid
from contextlib import asynccontextmanager

# Must be set BEFORE any torch / HuggingFace tokenizer import.
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("OMP_NUM_THREADS", "1")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
import psycopg2.extras
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Optional

from config.settings import settings
from core.intent import parse as intent_parse
from core.retrieval import search as retrieval_search
from core.context import build_context
from observability.metrics import (
    HTTP_REQUESTS, HTTP_DURATION, SEARCH_ZERO_RESULTS,
    CONTEXT_DURATION, STAGE_DURATION,
    DEP_UP, DEP_PROBE_DURATION,
)
from observability.logging_setup import get_logger

logger = get_logger()


def _git_commit() -> str:
    try:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=root, stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        return "unknown"


_GIT_COMMIT = _git_commit()


# ── Middleware ────────────────────────────────────────────────────────────────

class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        t = time.perf_counter()
        response = await call_next(request)
        dur = time.perf_counter() - t
        path = request.url.path
        HTTP_REQUESTS.labels(
            endpoint=path,
            method=request.method,
            status=str(response.status_code),
        ).inc()
        HTTP_DURATION.labels(endpoint=path).observe(dur)
        return response


# ── App ───────────────────────────────────────────────────────────────────────

def _warmup_models():
    from core.embedder import embed_query
    from core.reranker import rerank
    embed_query("warmup")
    rerank("warmup", ["warmup text"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("INFO:     [DA10] Warming up ML models...")
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _warmup_models)
        print("INFO:     [DA10] Models ready.")
    except Exception as e:
        print(f"WARNING:  [DA10] Model warmup failed: {e}")
    yield


app = FastAPI(title="DA10 Search API", version="1.0", lifespan=lifespan)
app.add_middleware(MetricsMiddleware)


# ── Request / Response models ─────────────────────────────────────────────────

class StarFilter(BaseModel):
    min: Optional[float] = None
    max: Optional[float] = None


class PriceFilter(BaseModel):
    min: Optional[float] = None
    max: Optional[float] = None


class ReviewFilter(BaseModel):
    min: Optional[float] = None


class SearchFilters(BaseModel):
    city: Optional[str] = None
    star_rating: Optional[StarFilter] = None
    price: Optional[PriceFilter] = None
    accommodation_type: Optional[list[str]] = None
    amenities: Optional[list[str]] = None
    suitable_for: Optional[list[str]] = None
    review_score: Optional[ReviewFilter] = None
    is_luxury: Optional[bool] = None


class SearchOptions(BaseModel):
    include_debug: bool = False


class SearchRequest(BaseModel):
    query: str
    top_k: int = Field(default=10, ge=1, le=50)
    page: int = Field(default=0, ge=0)
    filters: Optional[SearchFilters] = None
    options: Optional[SearchOptions] = None
    search_mode: str = Field(
        default="full_hybrid",
        pattern="^(full_hybrid|bm25_only|vector_only|hybrid_no_rerank)$",
    )


class ContextOptions(BaseModel):
    max_context_tokens: int = Field(default=1500, ge=100, le=8000)
    include_chunks: bool = True
    include_token_info: bool = False
    focus_aspects: Optional[list[str]] = None


class ContextRequest(BaseModel):
    hotel_id: int
    query: str
    query_id: Optional[str] = None
    options: Optional[ContextOptions] = None


# ── DB helpers ────────────────────────────────────────────────────────────────

def _pg_conn():
    return psycopg2.connect(settings.pg_dsn)


def _fetch_hotels(hotel_ids: list[int]) -> dict:
    if not hotel_ids:
        return {}
    conn = _pg_conn()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            """
            SELECT h.id, h.name, h.accommodation_type, h.address, h.city,
                   h.latitude, h.longitude, h.star_rating, h.review_score,
                   h.review_count, h.is_luxury, h.description,
                   h.suitable_for, h.amenities, h.images, h.source_url,
                   COALESCE(MIN(r.price), 0) AS price_from
            FROM hotels h
            LEFT JOIN rooms r ON r.hotel_id = h.id
            WHERE h.id = ANY(%s)
            GROUP BY h.id
            """,
            (hotel_ids,),
        )
        data: dict = {row["id"]: dict(row) for row in cur.fetchall()}
        cur.execute(
            """
            SELECT hotel_id, name, type, distance_km
            FROM (
                SELECT hotel_id, name, type, distance_km,
                       ROW_NUMBER() OVER (PARTITION BY hotel_id ORDER BY distance_km) AS rn
                FROM nearby_places WHERE hotel_id = ANY(%s)
            ) t WHERE rn <= 5
            """,
            (hotel_ids,),
        )
        for row in cur.fetchall():
            hid = row["hotel_id"]
            if hid in data:
                data[hid].setdefault("nearby_places", []).append({
                    "name": row["name"],
                    "type": row["type"],
                    "distance_km": float(row["distance_km"] or 0),
                })
        cur.close()
    finally:
        conn.close()
    return data


# ── Format helpers ────────────────────────────────────────────────────────────

def _fmt_intent(intent, query: str) -> dict:
    return {
        "original_query": query,
        "normalized_query": query,
        "hard_filters": intent.to_hard_filters(),
        "keyword_expansion": intent.keyword_expansion,
        "intent_type": "hotel_search",
        "confidence": intent.confidence,
        "parsed_by": intent.parsed_by,
    }


def _build_card(rank_idx: int, h: dict, d: dict) -> dict:
    amenities = d.get("amenities") or []
    images = d.get("images") or []
    desc = d.get("description") or ""
    return {
        "hotel_id": h["hotel_id"],
        "name": d.get("name") or "",
        "accommodation_type": d.get("accommodation_type") or "",
        "address": d.get("address") or "",
        "city": d.get("city") or "",
        "latitude": float(d.get("latitude") or 0),
        "longitude": float(d.get("longitude") or 0),
        "star_rating": float(d.get("star_rating") or 0),
        "review_score": float(d.get("review_score") or 0),
        "review_count": int(d.get("review_count") or 0),
        "is_luxury": bool(d.get("is_luxury")),
        "price_from": float(d.get("price_from") or 0),
        "description": desc[:200],
        "suitable_for": d.get("suitable_for") or [],
        "amenities_top": amenities[:8],
        "thumbnail_url": images[0] if images else "",
        "image_count": len(images),
        "ranking": {
            "final_score": round(h["score"], 4),
            "rank": rank_idx,
            "relevance_score": round(h["score"], 4),
        },
        "nearby_places": d.get("nearby_places") or [],
        "source_url": d.get("source_url") or "",
    }


# ── POST /search ──────────────────────────────────────────────────────────────

@app.post("/search")
def post_search(req: SearchRequest):
    t_start = time.perf_counter()
    query_id = f"q-{uuid.uuid4()}"

    # 1. Intent parse
    t0 = time.perf_counter()
    intent = intent_parse(req.query)
    intent_ms = round((time.perf_counter() - t0) * 1000, 1)

    # 2. Merge filters
    merged: dict = intent.to_hard_filters()
    if req.filters:
        f = req.filters
        if f.city is not None:
            merged["city"] = f.city
        if f.accommodation_type:
            merged["accommodation_type"] = f.accommodation_type
        if f.star_rating:
            merged["star_rating"] = f.star_rating.model_dump(exclude_none=True)
        if f.price:
            merged["price"] = f.price.model_dump(exclude_none=True)
        if f.amenities:
            merged["amenities"] = f.amenities
        if f.suitable_for:
            merged["suitable_for"] = f.suitable_for
        if f.review_score:
            merged["review_score"] = f.review_score.model_dump(exclude_none=True)
        if f.is_luxury is not None:
            merged["is_luxury"] = f.is_luxury

    # 3. Retrieval
    bm25_query = intent.expanded_query(req.query)
    result = retrieval_search(bm25_query, filters=merged, top_k=req.top_k, mode=req.search_mode)
    hotels_ranked = result["hotels"]
    stages_ms = result.get("stages_ms", {})

    # 4. Record stage metrics (convert ms → seconds)
    STAGE_DURATION.labels(stage="parse").observe(intent_ms / 1000)
    for stage, ms in stages_ms.items():
        STAGE_DURATION.labels(stage=stage).observe(ms / 1000)

    # 5. Zero-result path
    zero_results = not hotels_ranked
    if zero_results:
        SEARCH_ZERO_RESULTS.labels(search_mode=req.search_mode).inc()
        took_ms = round((time.perf_counter() - t_start) * 1000, 1)
        _log_search(query_id, req, intent_ms, stages_ms, 0, True, took_ms)
        return {
            "query_id": query_id,
            "query": req.query,
            "total_found": 0,
            "returned": 0,
            "page": req.page,
            "latency_ms": took_ms,
            "results": [],
            "parsed_intent": _fmt_intent(intent, req.query),
        }

    # 6. Fetch hotel details + build cards
    hotel_ids = [h["hotel_id"] for h in hotels_ranked]
    hotel_data = _fetch_hotels(hotel_ids)
    results = []
    for rank_idx, h in enumerate(hotels_ranked, 1):
        d = hotel_data.get(h["hotel_id"])
        if d:
            results.append(_build_card(rank_idx, h, d))

    took_ms = round((time.perf_counter() - t_start) * 1000, 1)
    _log_search(query_id, req, intent_ms, stages_ms, len(results), False, took_ms)

    response: dict = {
        "query_id": query_id,
        "query": req.query,
        "total_found": len(hotel_ids),
        "returned": len(results),
        "page": req.page,
        "latency_ms": took_ms,
        "results": results,
        "parsed_intent": _fmt_intent(intent, req.query),
    }

    if req.options and req.options.include_debug:
        response["debug_info"] = {
            "stage_latencies": {
                "intent_parsing_ms": intent_ms,
                "sql_prefilter_ms": stages_ms.get("sql_filter", 0),
                "parallel_retrieval_ms": stages_ms.get("os_bm25", 0),
                "rrf_fusion_ms": stages_ms.get("rrf", 0),
                "reranking_ms": stages_ms.get("rerank", 0),
            },
            "whitelist_hotel_count": result.get("whitelist") or 0,
            "bm25_candidates": len(result.get("chunks", [])),
            "vector_candidates": 0,
            "rrf_candidates": len(result.get("chunks", [])),
        }

    return response


def _log_search(query_id, req, intent_ms, stages_ms, results_count, zero_results, took_ms):
    logger.info("", extra={
        "event": "search_completed",
        "request_id": query_id,
        "endpoint": "/search",
        "query": req.query,
        "top_k": req.top_k,
        "search_mode": req.search_mode,
        "results_count": results_count,
        "zero_results": zero_results,
        "took_ms": took_ms,
        "stages_ms": {
            "parse": intent_ms,
            "sql_filter": stages_ms.get("sql_filter", 0),
            "os_bm25": stages_ms.get("os_bm25", 0),
            "qdrant_vector": stages_ms.get("qdrant_vector", 0),
            "rrf": stages_ms.get("rrf", 0),
            "rerank": stages_ms.get("rerank", 0),
        },
        "index_opensearch": settings.os_alias,
        "index_qdrant": settings.qdrant_collection,
        "git_commit": _GIT_COMMIT,
        "status": 200,
    })


# ── POST /context ─────────────────────────────────────────────────────────────

@app.post("/context")
def post_context(req: ContextRequest):
    t_start = time.perf_counter()
    opts = req.options or ContextOptions()
    request_id = req.query_id or f"q-{uuid.uuid4()}"

    ctx = build_context(
        hotel_id=req.hotel_id,
        query=req.query,
        max_context_tokens=opts.max_context_tokens,
        include_chunks=opts.include_chunks,
        include_token_info=opts.include_token_info,
        focus_aspects=opts.focus_aspects,
    )

    meta = ctx.get("metadata") or {}
    if not meta:
        return JSONResponse(
            status_code=404,
            content={"error": {"code": "HOTEL_NOT_FOUND", "message": f"hotel_id {req.hotel_id} not found"}},
        )

    took_ms = round((time.perf_counter() - t_start) * 1000, 1)
    CONTEXT_DURATION.observe(took_ms / 1000)

    ctx_stages = ctx.get("stages_ms", {})
    for stage_key, stage_map in [
        ("os_fetch_ms", "context_select"),
        ("rerank_ms", "context_aggregate"),
        ("pg_metadata_ms", "citation_build"),
    ]:
        if stage_key in ctx_stages:
            STAGE_DURATION.labels(stage=stage_map).observe(ctx_stages[stage_key] / 1000)

    token_count = (ctx.get("token_info") or {}).get("context_text_tokens", 0)
    logger.info("", extra={
        "event": "context_completed",
        "request_id": request_id,
        "endpoint": "/context",
        "hotel_id": req.hotel_id,
        "query": req.query,
        "chunk_count": len(ctx.get("chunks", [])),
        "citation_count": len(ctx.get("citations", [])),
        "token_count": token_count,
        "took_ms": took_ms,
        "stages_ms": {
            "context_select": ctx_stages.get("os_fetch_ms", 0),
            "context_aggregate": ctx_stages.get("rerank_ms", 0),
            "citation_build": ctx_stages.get("pg_metadata_ms", 0),
        },
        "status": 200,
    })

    response: dict = {
        "hotel_id": req.hotel_id,
        "hotel_name": meta.get("name", ""),
        "query_id": request_id,
        "context_text": ctx["context_text"],
        "chunks": ctx["chunks"],
        "citations": ctx["citations"],
        "metadata": meta,
        "latency_ms": took_ms,
    }
    if ctx.get("token_info"):
        response["token_info"] = ctx["token_info"]

    return response


# ── GET /health ───────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


# ── GET /health/deep ──────────────────────────────────────────────────────────

@app.get("/health/deep")
def health_deep():
    checks: dict = {}
    overall = "ok"

    # OpenSearch
    t = time.perf_counter()
    try:
        from core.retrieval import os_client
        os_client().ping()
        lat = round((time.perf_counter() - t) * 1000, 1)
        checks["opensearch"] = {"status": "ok", "latency_ms": lat}
        DEP_UP.labels(dependency="opensearch").set(1)
        DEP_PROBE_DURATION.labels(dependency="opensearch").observe(time.perf_counter() - t)
    except Exception as e:
        checks["opensearch"] = {"status": "error", "message": str(e)}
        DEP_UP.labels(dependency="opensearch").set(0)
        overall = "error"

    # Qdrant
    t = time.perf_counter()
    try:
        from core.retrieval import qd_client
        qd_client().get_collections()
        lat = round((time.perf_counter() - t) * 1000, 1)
        checks["qdrant"] = {"status": "ok", "latency_ms": lat}
        DEP_UP.labels(dependency="qdrant").set(1)
        DEP_PROBE_DURATION.labels(dependency="qdrant").observe(time.perf_counter() - t)
    except Exception as e:
        checks["qdrant"] = {"status": "error", "message": str(e)}
        DEP_UP.labels(dependency="qdrant").set(0)
        overall = "error"

    # Postgres
    t = time.perf_counter()
    try:
        conn = _pg_conn()
        conn.cursor().execute("SELECT 1")
        conn.close()
        lat = round((time.perf_counter() - t) * 1000, 1)
        checks["postgres"] = {"status": "ok", "latency_ms": lat}
        DEP_UP.labels(dependency="postgres").set(1)
        DEP_PROBE_DURATION.labels(dependency="postgres").observe(time.perf_counter() - t)
    except Exception as e:
        checks["postgres"] = {"status": "error", "message": str(e)}
        DEP_UP.labels(dependency="postgres").set(0)
        overall = "error"

    body = {
        "status": overall,
        "checks": checks,
        "index_opensearch": settings.os_alias,
        "index_qdrant": settings.qdrant_collection,
    }
    return JSONResponse(status_code=200 if overall == "ok" else 503, content=body)


# ── GET /metrics ──────────────────────────────────────────────────────────────

@app.get("/metrics")
def prometheus_metrics():
    from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
