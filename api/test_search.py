"""DA10 Phase 6 — HTTP smoke test cho POST /search.

Chạy khi server đang up: uvicorn api.main:app --reload --port 8000
Dùng: python api/test_search.py
"""
import json
import sys
import urllib.request
import urllib.error

BASE = "http://localhost:8000"

CASES = [
    {
        "name": "Resort Nha Trang có bể bơi (kết quả thường)",
        "body": {
            "query": "Tìm resort ở Nha Trang có bể bơi",
            "top_k": 3,
            "options": {"include_debug": True},
        },
    },
    {
        "name": "Zero-result (Tokyo — không có trong DB)",
        "body": {
            "query": "khách sạn ở Tokyo",
            "top_k": 5,
        },
    },
    {
        "name": "Health check",
        "body": None,  # GET /health
    },
]


def post(path: str, body: dict) -> dict:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        BASE + path,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get(path: str) -> dict:
    req = urllib.request.Request(BASE + path, method="GET")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def run():
    ok = 0
    for case in CASES:
        name = case["name"]
        print(f"\n{'='*60}")
        print(f"TEST: {name}")
        print("="*60)
        try:
            if case["body"] is None:
                resp = get("/health")
            else:
                resp = post("/search", case["body"])

            print(json.dumps(resp, ensure_ascii=False, indent=2))

            # Basic assertions
            if case["body"] is None:
                assert resp.get("status") == "ok", "health fail"
                print("[OK] /health")
            else:
                assert "query_id" in resp, "missing query_id"
                assert "results" in resp, "missing results"
                assert "parsed_intent" in resp, "missing parsed_intent"
                n = len(resp["results"])
                print(f"\n[OK] returned={n}, latency_ms={resp.get('latency_ms')}")
                if resp.get("debug_info"):
                    print(f"     stages={resp['debug_info']['stage_latencies']}")
            ok += 1
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            print(f"[FAIL] HTTP {e.code}: {body}")
        except Exception as e:
            print(f"[FAIL] {type(e).__name__}: {e}")

    print(f"\n{'='*60}")
    print(f"Result: {ok}/{len(CASES)} OK")
    sys.exit(0 if ok == len(CASES) else 1)


if __name__ == "__main__":
    run()
