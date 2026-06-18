"""DA10 — Phase 7 Acceptance test: POST /context endpoint.

Chạy trong terminal MỚI (server phải đang chạy):
    python tools/test_context_api.py
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
HOTEL_ID = 805030  # Vinpearl Resort & Spa Nha Trang Bay — có trong golden set


def sep(title):
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def check(label, condition, detail=""):
    mark = "PASS" if condition else "FAIL"
    print(f"  [{mark}] {label}" + (f" — {detail}" if detail else ""))
    return condition


# ── Test 1: POST /context cơ bản ─────────────────────────────────────────────
sep(f"Test 1 — POST /context hotel_id={HOTEL_ID} (cơ bản)")
payload1 = {
    "hotel_id": HOTEL_ID,
    "query": "hòn đảo riêng yên tĩnh",
    "options": {
        "max_context_tokens": 1500,
        "include_chunks": True,
        "include_token_info": True,
    },
}
try:
    r = httpx.post(f"{BASE}/context", json=payload1, timeout=120)
    print(f"  HTTP {r.status_code}")
    if r.status_code != 200:
        print(f"  ERROR: {r.text}")
    else:
        d = r.json()
        print(f"  hotel_name: {d.get('hotel_name')}")
        print(f"  query_id:   {d.get('query_id')}")
        print(f"  latency_ms: {d.get('latency_ms')}")
        print(f"  chunks:     {len(d.get('chunks', []))} chunks")
        print(f"  citations:  {len(d.get('citations', []))} citations")
        ct = d.get("context_text", "")
        print(f"  context_text ({len(ct)} chars): {ct[:120]}...")
        print(f"  token_info: {d.get('token_info')}")

        check("HTTP 200", r.status_code == 200)
        check("hotel_id correct", d.get("hotel_id") == HOTEL_ID)
        check("hotel_name non-empty", bool(d.get("hotel_name")))
        check("query_id present", bool(d.get("query_id")))
        check("chunks non-empty", len(d.get("chunks", [])) > 0)
        check("context_text non-empty", len(ct) > 0)
        check("context_text không có embed prefix",
              "— Mô tả." not in ct and "— Tiện nghi." not in ct,
              "kiểm tra text raw không có context_prefix")
        check("citations non-empty", len(d.get("citations", [])) > 0)
        check("token_info present", d.get("token_info") is not None)

        # Kiểm tra citation format
        if d.get("citations"):
            cit = d["citations"][0]
            check("citation có chunk_id", bool(cit.get("chunk_id")))
            check("citation chunk_id bắt đầu bằng chunk-",
                  str(cit.get("chunk_id", "")).startswith("chunk-"))
            check("citation có relevance_score", "relevance_score" in cit)
            check("citation có text_snippet", bool(cit.get("text_snippet")))

        # Kiểm tra metadata
        meta = d.get("metadata", {})
        check("metadata.hotel_id", meta.get("hotel_id") == HOTEL_ID)
        check("metadata.rooms non-empty", len(meta.get("rooms", [])) > 0)
        check("metadata.nearby_places non-empty", len(meta.get("nearby_places", [])) > 0)
        check("metadata.amenities non-empty", len(meta.get("amenities", [])) > 0)
        check("metadata.description non-empty", bool(meta.get("description")))

        # In sample chunks
        print("\n  --- Sample chunks (top 3) ---")
        for ch in d.get("chunks", [])[:3]:
            print(f"    {ch['chunk_id']}  score={ch['scores']['reranker_score']}  type={ch['source_type']}")
            print(f"    text[:100]: {ch['text'][:100]}")
except Exception as e:
    print(f"  ERROR: {e}")
    import traceback
    traceback.print_exc()


# ── Test 2: POST /context với query_id từ search ──────────────────────────────
sep("Test 2 — POST /context kèm query_id")
payload2 = {
    "hotel_id": HOTEL_ID,
    "query": "CLB trẻ em bể bơi ngoài trời",
    "query_id": "q-test-phase7-001",
    "options": {"include_chunks": False},
}
try:
    r = httpx.post(f"{BASE}/context", json=payload2, timeout=120)
    print(f"  HTTP {r.status_code}")
    if r.status_code == 200:
        d = r.json()
        check("query_id được echo lại", d.get("query_id") == "q-test-phase7-001")
        check("chunks rỗng khi include_chunks=False", d.get("chunks") == [])
        check("context_text vẫn có", len(d.get("context_text", "")) > 0)
        check("citations vẫn có", len(d.get("citations", [])) > 0)
    else:
        print(f"  ERROR: {r.text}")
except Exception as e:
    print(f"  ERROR: {e}")


# ── Test 3: POST /context hotel không tồn tại → 404 ──────────────────────────
sep("Test 3 — POST /context hotel_id=999999999 → 404")
payload3 = {"hotel_id": 999999999, "query": "test"}
try:
    r = httpx.post(f"{BASE}/context", json=payload3, timeout=30)
    print(f"  HTTP {r.status_code}  body={r.text[:200]}")
    check("HTTP 404", r.status_code == 404)
    check("error.code = HOTEL_NOT_FOUND",
          r.json().get("error", {}).get("code") == "HOTEL_NOT_FOUND")
except Exception as e:
    print(f"  ERROR: {e}")


print("\n" + "=" * 60)
print("  DONE")
print("=" * 60)
