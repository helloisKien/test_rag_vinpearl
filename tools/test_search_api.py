"""DA10 — Phase 6 Acceptance test: POST /search endpoint.

Chạy trong terminal MỚI (server phải đang chạy ở terminal khác):
    python tools/test_search_api.py
"""
import json
import sys

try:
    import httpx
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "httpx"])
    import httpx

BASE = "http://localhost:8000"


def sep(title):
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def check(label, condition, detail=""):
    mark = "PASS" if condition else "FAIL"
    print(f"  [{mark}] {label}" + (f" — {detail}" if detail else ""))
    return condition


# ── Test 1: GET /health ───────────────────────────────────────────────────────
sep("Test 1 — GET /health")
try:
    r = httpx.get(f"{BASE}/health", timeout=5)
    print(f"  HTTP {r.status_code}  body={r.text}")
    check("status 200", r.status_code == 200)
    check("status=ok", r.json().get("status") == "ok")
except Exception as e:
    print(f"  ERROR: {e}")


# ── Test 2: POST /search — query có kết quả ──────────────────────────────────
sep("Test 2 — POST /search (query có kết quả)")
payload2 = {
    "query": "resort Nha Trang có hồ bơi",
    "top_k": 5,
    "options": {"include_debug": True},
}
try:
    r = httpx.post(f"{BASE}/search", json=payload2, timeout=60)
    print(f"  HTTP {r.status_code}")
    if r.status_code != 200:
        print(f"  ERROR body: {r.text}")
    else:
        d = r.json()
        print(json.dumps(d, ensure_ascii=False, indent=2))
        check("query_id có dạng q-<uuid>", str(d.get("query_id", "")).startswith("q-"))
        check("latency_ms là số", isinstance(d.get("latency_ms"), (int, float)))
        check("results là list", isinstance(d.get("results"), list))
        check("total_found >= returned",
              d.get("total_found", 0) >= d.get("returned", 0))
        check("parsed_intent present", "parsed_intent" in d)
        if d.get("results"):
            h = d["results"][0]
            for fld in ["hotel_id", "name", "city", "star_rating", "price_from", "ranking"]:
                check(f"  results[0].{fld} present", fld in h)
        if "debug_info" in d:
            check("debug_info.stage_latencies present",
                  "stage_latencies" in d.get("debug_info", {}))
except Exception as e:
    print(f"  ERROR: {e}")


# ── Test 3: POST /search — zero-result (Tokyo không có trong DB) ─────────────
sep("Test 3 — POST /search zero-result (city=Tokyo)")
payload3 = {
    "query": "khách sạn Tokyo",
    "top_k": 5,
    "filters": {"city": "Tokyo"},
}
try:
    r = httpx.post(f"{BASE}/search", json=payload3, timeout=30)
    print(f"  HTTP {r.status_code}")
    if r.status_code != 200:
        print(f"  ERROR body: {r.text}")
    else:
        d = r.json()
        print(json.dumps(d, ensure_ascii=False, indent=2))
        check("status 200 (không crash)", r.status_code == 200)
        check("results = []", d.get("results") == [])
        check("total_found = 0", d.get("total_found") == 0)
        check("returned = 0", d.get("returned") == 0)
except Exception as e:
    print(f"  ERROR: {e}")


# ── Test 4: POST /search — với filter star_rating ────────────────────────────
sep("Test 4 — POST /search với filter (star_rating min=4)")
payload4 = {
    "query": "khách sạn sang trọng Hà Nội",
    "top_k": 3,
    "filters": {"star_rating": {"min": 4}},
}
try:
    r = httpx.post(f"{BASE}/search", json=payload4, timeout=60)
    print(f"  HTTP {r.status_code}")
    if r.status_code != 200:
        print(f"  ERROR body: {r.text}")
    else:
        d = r.json()
        results = d.get("results", [])
        print(f"  returned={d.get('returned')}  total_found={d.get('total_found')}")
        for h in results:
            print(f"    hotel_id={h['hotel_id']}  name={h['name'][:40]}  star={h['star_rating']}  city={h['city']}")
        check("status 200", r.status_code == 200)
        all_4plus = all(h.get("star_rating", 0) >= 4 for h in results)
        check("mọi result có star_rating >= 4", all_4plus,
              "hoặc prefilter không lọc đúng" if not all_4plus else "")
except Exception as e:
    print(f"  ERROR: {e}")

print("\n" + "=" * 60)
print("  DONE")
print("=" * 60)
