"""DA10 — Phase 4 smoke: chạy vài query golden (mỗi nhóm 1) qua retrieval.search()
để kiểm pipeline trả hotel + xem GT có lọt top_k không + xem stage latency.
KHÔNG phải eval chính thức (đó là Phase 9). Chỉ sanity-check end-to-end retrieval.

Chạy:  python core/smoke_search.py
"""
from __future__ import annotations
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.retrieval import search  # noqa: E402

GOLDEN = "golden_dataset/golden_set_v1.json"
TOP_K = 10
PICK_PREFIXES = ["GS-DESC", "GS-FAQ", "GS-ACT", "GS-POL", "GS-AMEN"]


def run():
    gs = json.load(open(GOLDEN, encoding="utf-8"))
    # mỗi nhóm lấy query đầu tiên
    picked = []
    for pre in PICK_PREFIXES:
        for q in gs["queries"]:
            if q["query_id"].startswith(pre):
                picked.append(q)
                break

    for q in picked:
        res = search(q["query"], filters=q.get("hard_filters"), top_k=TOP_K)
        top_ids = [h["hotel_id"] for h in res["hotels"]]
        gt = set(q["relevant_hotel_ids"])
        hit = [h for h in top_ids if h in gt]
        print("=" * 70)
        print(f"{q['query_id']}: {q['query']}")
        print(f"  hard_filters={q.get('hard_filters')}  whitelist={res['whitelist']}")
        print(f"  top{TOP_K} hotel_ids = {top_ids}")
        print(f"  GT({len(gt)}) = {sorted(gt)}")
        print(f"  HIT trong top{TOP_K}: {len(hit)}/{len(gt)} -> {hit}")
        print(f"  stages_ms = {res['stages_ms']}")
    print("=" * 70)
    print("Smoke xong. (Recall thấp ở đây là bình thường — chưa intent-parse/expansion; eval chính thức ở Phase 9.)")


if __name__ == "__main__":
    run()
