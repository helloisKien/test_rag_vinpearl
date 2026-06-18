"""DA10 — Phase 9: Evaluation Harness.

Chạy:
  python evaluation/run_eval.py --mode full_hybrid
  python evaluation/run_eval.py --mode bm25_only
  python evaluation/run_eval.py --smoke
  python evaluation/run_eval.py --mode full_hybrid --latency

Flags:
  --mode        full_hybrid | bm25_only | vector_only | hybrid_no_rerank
  --smoke       Dùng evaluation/smoke_queries_kien.json (5 query, không có GT)
  --top-k       Số kết quả retrieve (default: 10)
  --latency     Thêm latency benchmark (warmup 5, đo 30 lần p95)
  --api         API base URL (default: http://localhost:8000)
  --out         Output report path (default: evaluation/reports/evaluation_report.md)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))
from evaluation.metrics_ir import (
    compute_query_metrics, aggregate, p95,
    chunk_recall_at_k, citation_coverage,
)

ROOT = Path(__file__).parent.parent
GOLDEN_SET = ROOT / "golden_dataset" / "golden_set_v1.json"
SMOKE_SET = ROOT / "evaluation" / "smoke_queries_kien.json"
REPORTS_DIR = ROOT / "evaluation" / "reports"

DEFAULT_API = "http://localhost:8000"
TOP_K = 10
LATENCY_WARMUP = 5
LATENCY_RUNS = 30


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _group(query_id: str) -> str:
    """GS-DESC-001 → DESC, GS-FAQ-003 → FAQ …"""
    parts = query_id.split("-")
    return parts[1] if len(parts) >= 2 else "UNKNOWN"


def _build_filters(hard_filters: dict) -> dict:
    """Chuyển golden hard_filters → SearchRequest.filters shape."""
    f: dict = {}
    if not hard_filters:
        return f
    if "city" in hard_filters:
        f["city"] = hard_filters["city"]
    if "accommodation_type" in hard_filters:
        f["accommodation_type"] = hard_filters["accommodation_type"]
    if "amenities" in hard_filters:
        f["amenities"] = hard_filters["amenities"]
    if "suitable_for" in hard_filters:
        f["suitable_for"] = hard_filters["suitable_for"]
    if "star_rating" in hard_filters:
        f["star_rating"] = hard_filters["star_rating"]
    if "price" in hard_filters:
        f["price"] = hard_filters["price"]
    if "review_score" in hard_filters:
        f["review_score"] = hard_filters["review_score"]
    return f


def _call_search(client: httpx.Client, api: str, query: str, hard_filters: dict,
                 mode: str, top_k: int) -> tuple[list[int], float, dict]:
    """Gọi POST /search. Trả (hotel_ids, latency_ms, response_json)."""
    body: dict = {
        "query": query,
        "top_k": top_k,
        "search_mode": mode,
    }
    f = _build_filters(hard_filters)
    if f:
        body["filters"] = f

    t0 = time.perf_counter()
    resp = client.post(f"{api}/search", json=body, timeout=120)
    latency_ms = (time.perf_counter() - t0) * 1000

    if resp.status_code != 200:
        print(f"    [WARN] /search HTTP {resp.status_code} — {resp.text[:120]}")
        return [], latency_ms, {}

    data = resp.json()
    hotel_ids = [r["hotel_id"] for r in data.get("results", [])]
    return hotel_ids, latency_ms, data


def _call_context(client: httpx.Client, api: str, hotel_id: int,
                  query: str) -> tuple[list[str], list[str], float]:
    """Gọi POST /context. Trả (chunk_ids, citation_chunk_ids, latency_ms)."""
    body = {
        "hotel_id": hotel_id,
        "query": query,
        "options": {"include_chunks": True, "include_token_info": False},
    }
    t0 = time.perf_counter()
    resp = client.post(f"{api}/context", json=body, timeout=180)
    latency_ms = (time.perf_counter() - t0) * 1000

    if resp.status_code != 200:
        return [], [], latency_ms

    data = resp.json()
    chunk_ids = [c["chunk_id"] for c in data.get("chunks", [])]
    citation_ids = [c["chunk_id"] for c in data.get("citations", [])]
    return chunk_ids, citation_ids, latency_ms


# ─────────────────────────────────────────────────────────────────────────────
# Main eval loop
# ─────────────────────────────────────────────────────────────────────────────

def run_eval(mode: str, smoke: bool, top_k: int, api: str, run_latency: bool,
             out_path: Path) -> None:
    dataset_path = SMOKE_SET if smoke else GOLDEN_SET
    with open(dataset_path, encoding="utf-8") as f:
        dataset = json.load(f)

    queries = dataset["queries"]
    meta = dataset.get("metadata", {})
    print(f"\n{'='*60}")
    print(f"  DA10 Evaluation — mode={mode}  top_k={top_k}  queries={len(queries)}")
    print(f"  Dataset: {dataset_path.name}  smoke={smoke}")
    print(f"{'='*60}\n")

    if smoke:
        print("[SMOKE] Chỉ kiểm tra API hoạt động (không tính metrics — GT rỗng).")

    client = httpx.Client(timeout=180)
    per_query_results = []
    search_latencies: list[float] = []
    context_latencies: list[float] = []

    # ── Chỉ chạy query có GT (relevant_hotel_ids non-empty) để tính metrics ──
    eval_queries = queries if smoke else [q for q in queries if q.get("relevant_hotel_ids")]
    skipped = len(queries) - len(eval_queries)
    if not smoke and skipped:
        print(f"[INFO] Bỏ qua {skipped} query không có GT (relevant_hotel_ids rỗng).\n")

    for i, q in enumerate(eval_queries, 1):
        qid = q["query_id"]
        query_text = q["query"]
        relevant = q.get("relevant_hotel_ids", [])
        rel_chunks = q.get("relevant_chunk_ids", [])
        hard_filters = q.get("hard_filters", {})

        print(f"  [{i:2d}/{len(eval_queries)}] {qid}  \"{query_text[:50]}\"")

        # Search
        hotel_ids, lat_ms, resp_data = _call_search(
            client, api, query_text, hard_filters, mode, top_k)
        search_latencies.append(lat_ms)
        print(f"         /search → {len(hotel_ids)} results  {lat_ms:.0f}ms")

        if smoke:
            continue  # smoke: chỉ kiểm tra chạy được, không tính metrics

        # IR metrics
        metrics = compute_query_metrics(relevant, hotel_ids, k_primary=5, k_secondary=10)
        metrics["query_id"] = qid
        metrics["group"] = _group(qid)
        metrics["query"] = query_text
        metrics["retrieved_hotel_ids"] = hotel_ids
        metrics["search_latency_ms"] = lat_ms

        # Context (chỉ khi có ít nhất 1 kết quả)
        if hotel_ids:
            top_hotel = hotel_ids[0]
            chunk_ids, citation_ids, ctx_lat = _call_context(
                client, api, top_hotel, query_text)
            context_latencies.append(ctx_lat)
            print(f"         /context hotel={top_hotel} → {len(chunk_ids)} chunks  {ctx_lat:.0f}ms")

            if rel_chunks:
                metrics["chunk_recall@5"] = chunk_recall_at_k(rel_chunks, chunk_ids, 5)
                metrics["citation_coverage"] = citation_coverage(rel_chunks, citation_ids)
            else:
                metrics["chunk_recall@5"] = None
                metrics["citation_coverage"] = None
        else:
            metrics["chunk_recall@5"] = None
            metrics["citation_coverage"] = None

        per_query_results.append(metrics)

    client.close()

    if smoke:
        print("\n[SMOKE] Tất cả query chạy xong — API hoạt động bình thường.")
        return

    # ─────────────────────────────────────────────────────────────────────────
    # Latency benchmark (optional)
    # ─────────────────────────────────────────────────────────────────────────
    bench_search_p95 = None
    bench_context_p95 = None
    if run_latency and eval_queries:
        print(f"\n[LATENCY] Warmup {LATENCY_WARMUP} queries...")
        bench_client = httpx.Client(timeout=180)
        warmup_qs = (eval_queries * 10)[:LATENCY_WARMUP]
        for q in warmup_qs:
            _call_search(bench_client, api, q["query"], q.get("hard_filters", {}), mode, top_k)

        print(f"[LATENCY] Đo {LATENCY_RUNS} queries × 1 lần (p95)...")
        bench_lats: list[float] = []
        bench_ctx_lats: list[float] = []
        bench_qs = (eval_queries * 10)[:LATENCY_RUNS]
        for q in bench_qs:
            hids, lat, _ = _call_search(bench_client, api, q["query"],
                                         q.get("hard_filters", {}), mode, top_k)
            bench_lats.append(lat)
            if hids:
                _, _, ctx_lat = _call_context(bench_client, api, hids[0], q["query"])
                bench_ctx_lats.append(ctx_lat)
        bench_client.close()
        bench_search_p95 = p95(bench_lats)
        bench_context_p95 = p95(bench_ctx_lats) if bench_ctx_lats else None
        print(f"[LATENCY] /search p95={bench_search_p95:.0f}ms  "
              f"/context p95={bench_context_p95 or 0:.0f}ms")

    # ─────────────────────────────────────────────────────────────────────────
    # Aggregate
    # ─────────────────────────────────────────────────────────────────────────
    metric_keys = ["recall@5", "recall@10", "hit@5", "mrr@10", "ndcg@10", "zero_result"]

    overall = aggregate([
        {k: r[k] for k in metric_keys} for r in per_query_results
    ])

    by_group: dict[str, list] = defaultdict(list)
    for r in per_query_results:
        by_group[r["group"]].append({k: r[k] for k in metric_keys})
    group_agg = {g: aggregate(rows) for g, rows in by_group.items()}

    # p95 latency từ eval loop
    eval_search_p95 = p95(search_latencies)
    eval_context_p95 = p95(context_latencies) if context_latencies else None

    # ─────────────────────────────────────────────────────────────────────────
    # Report
    # ─────────────────────────────────────────────────────────────────────────
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    import subprocess
    try:
        git_commit = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(ROOT), stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        git_commit = "unknown"

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    report_lines = [
        f"# DA10 Evaluation Report",
        f"",
        f"## Header",
        f"",
        f"| Field | Value |",
        f"|-------|-------|",
        f"| generated_at | {now} |",
        f"| git_commit | `{git_commit}` |",
        f"| dataset | golden_set_v1.json ({len(eval_queries)} queries with GT) |",
        f"| mode | `{mode}` |",
        f"| top_k | {top_k} |",
        f"| embedding_model | BAAI/bge-m3 |",
        f"| reranker_model | BAAI/bge-reranker-v2-m3 |",
        f"| index_opensearch | hotel_chunks |",
        f"| index_qdrant | col_documents_v1.0 |",
        f"",
        f"---",
        f"",
        f"## §6.1 Hotel-level IR Metrics (Overall)",
        f"",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| **Recall@5** | **{overall.get('recall@5', 0):.4f}** |",
        f"| Recall@10 | {overall.get('recall@10', 0):.4f} |",
        f"| Hit@5 | {overall.get('hit@5', 0):.4f} |",
        f"| MRR@10 | {overall.get('mrr@10', 0):.4f} |",
        f"| NDCG@10 | {overall.get('ndcg@10', 0):.4f} |",
        f"| Zero-result rate | {overall.get('zero_result', 0):.4f} |",
        f"| Queries evaluated | {len(per_query_results)} |",
        f"",
        f"---",
        f"",
        f"## §6.1 Breakdown theo nhóm",
        f"",
        f"| Group | N | Recall@5 | Recall@10 | Hit@5 | MRR@10 | NDCG@10 | Zero% |",
        f"|-------|---|----------|-----------|-------|--------|---------|-------|",
    ]

    for g in ["DESC", "FAQ", "ACT", "POL", "AMEN"]:
        agg = group_agg.get(g, {})
        n = len(by_group.get(g, []))
        report_lines.append(
            f"| {g} | {n} "
            f"| {agg.get('recall@5', 0):.4f} "
            f"| {agg.get('recall@10', 0):.4f} "
            f"| {agg.get('hit@5', 0):.4f} "
            f"| {agg.get('mrr@10', 0):.4f} "
            f"| {agg.get('ndcg@10', 0):.4f} "
            f"| {agg.get('zero_result', 0):.4f} |"
        )

    # Chunk metrics
    chunk_rows = [r for r in per_query_results if r.get("chunk_recall@5") is not None]
    chunk_recall_mean = (
        sum(r["chunk_recall@5"] for r in chunk_rows) / len(chunk_rows)
        if chunk_rows else None
    )
    cit_rows = [r for r in per_query_results if r.get("citation_coverage") is not None]
    cit_cov_mean = (
        sum(r["citation_coverage"] for r in cit_rows) / len(cit_rows)
        if cit_rows else None
    )

    report_lines += [
        f"",
        f"---",
        f"",
        f"## §6.2 Chunk-level Metrics",
        f"",
    ]
    if chunk_rows:
        report_lines += [
            f"| Metric | Value | N |",
            f"|--------|-------|---|",
            f"| Chunk Recall@5 | {chunk_recall_mean:.4f} | {len(chunk_rows)} |",
            f"| Citation Coverage | {cit_cov_mean:.4f if cit_cov_mean is not None else 'N/A'} | {len(cit_rows)} |",
        ]
    else:
        report_lines.append(
            "_Chunk metrics N/A — `relevant_chunk_ids` chưa điền trong golden set._"
        )

    # Latency
    report_lines += [
        f"",
        f"---",
        f"",
        f"## §6.3 Latency",
        f"",
        f"| Endpoint | p95 (eval loop, {len(search_latencies)} calls) |",
        f"|----------|------|",
        f"| /search | {eval_search_p95:.0f} ms |",
        f"| /context | {f'{eval_context_p95:.0f}' if eval_context_p95 else 'N/A'} ms |",
    ]
    if bench_search_p95 is not None:
        report_lines += [
            f"",
            f"**Latency benchmark** ({LATENCY_RUNS} calls, warmup {LATENCY_WARMUP}):",
            f"",
            f"| Endpoint | p95 |",
            f"|----------|-----|",
            f"| /search | {bench_search_p95:.0f} ms |",
            f"| /context | {f'{bench_context_p95:.0f}' if bench_context_p95 else 'N/A'} ms |",
        ]

    # Per-query table
    report_lines += [
        f"",
        f"---",
        f"",
        f"## Appendix — Per-query Results",
        f"",
        f"| query_id | group | R@5 | R@10 | Hit@5 | MRR@10 | NDCG@10 | ZR | retrieved |",
        f"|----------|-------|-----|------|-------|--------|---------|----|-----------| ",
    ]
    for r in per_query_results:
        report_lines.append(
            f"| {r['query_id']} | {r['group']} "
            f"| {r['recall@5']:.3f} "
            f"| {r['recall@10']:.3f} "
            f"| {r['hit@5']:.3f} "
            f"| {r['mrr@10']:.3f} "
            f"| {r['ndcg@10']:.3f} "
            f"| {int(r['zero_result'])} "
            f"| {len(r.get('retrieved_hotel_ids', []))} |"
        )

    report_lines += [
        f"",
        f"---",
        f"",
        f"_Generated by `evaluation/run_eval.py` — DA10 Phase 9_",
    ]

    report_text = "\n".join(report_lines)
    out_path.write_text(report_text, encoding="utf-8")
    print(f"\n[DONE] Report saved → {out_path}")
    print(f"\n  Recall@5={overall.get('recall@5',0):.4f}  "
          f"Recall@10={overall.get('recall@10',0):.4f}  "
          f"MRR@10={overall.get('mrr@10',0):.4f}  "
          f"NDCG@10={overall.get('ndcg@10',0):.4f}  "
          f"Zero-result={overall.get('zero_result',0):.4f}")


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DA10 Evaluation Harness")
    parser.add_argument("--mode", default="full_hybrid",
                        choices=["full_hybrid", "bm25_only", "vector_only", "hybrid_no_rerank"])
    parser.add_argument("--smoke", action="store_true",
                        help="Chạy 5 smoke queries (không tính metrics)")
    parser.add_argument("--top-k", type=int, default=TOP_K)
    parser.add_argument("--latency", action="store_true",
                        help="Chạy latency benchmark sau eval")
    parser.add_argument("--api", default=DEFAULT_API)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    out_path = Path(args.out) if args.out else (
        REPORTS_DIR / f"evaluation_report_{args.mode}.md"
    )

    run_eval(
        mode=args.mode,
        smoke=args.smoke,
        top_k=args.top_k,
        api=args.api,
        run_latency=args.latency,
        out_path=out_path,
    )
