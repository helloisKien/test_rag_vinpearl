"""DA10 — Phase 8 Acceptance test: Observability (metrics, logging, health/deep).

Chạy trong terminal MỚI (server phải đang chạy):
    python tools/test_observability.py
"""
import json
import sys
import time

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


# ── Bước 0: tạo traffic để có số trong metrics ───────────────────────────────
sep("Bước 0 — Tạo traffic (2 search + 1 context)")
try:
    r1 = httpx.post(f"{BASE}/search", json={"query": "resort Đà Nẵng có bãi biển", "top_k": 3}, timeout=60)
    print(f"  /search (1): HTTP {r1.status_code}")
    r2 = httpx.post(f"{BASE}/search", json={"query": "khách sạn Tokyo", "filters": {"city": "Tokyo"}}, timeout=10)
    print(f"  /search (2) zero-result: HTTP {r2.status_code}")
    r3 = httpx.post(f"{BASE}/context", json={"hotel_id": 805030, "query": "tiện nghi hồ bơi"}, timeout=120)
    print(f"  /context (1): HTTP {r3.status_code}")
except Exception as e:
    print(f"  ERROR tạo traffic: {e}")

time.sleep(1)  # cho metrics collector cập nhật


# ── Test 1: GET /metrics ──────────────────────────────────────────────────────
sep("Test 1 — GET /metrics")
try:
    r = httpx.get(f"{BASE}/metrics", timeout=5)
    print(f"  HTTP {r.status_code}  content_type={r.headers.get('content-type','')[:40]}")
    body = r.text
    check("HTTP 200", r.status_code == 200)
    check("Content-Type text/plain", "text/plain" in r.headers.get("content-type", ""))

    da10_metrics = [ln for ln in body.splitlines() if ln.startswith("da10_")]
    print(f"  da10_* metric lines: {len(da10_metrics)}")
    for name in [
        "da10_http_requests_total",
        "da10_http_request_duration_seconds",
        "da10_search_zero_results_total",
        "da10_context_build_duration_seconds",
        "da10_stage_duration_seconds",
    ]:
        present = any(name in ln for ln in body.splitlines())
        check(f"  {name} present", present)

    # In một số dòng metrics mẫu
    print("\n  Sample da10_* lines:")
    for ln in da10_metrics[:12]:
        print(f"    {ln}")
except Exception as e:
    print(f"  ERROR: {e}")


# ── Test 2: GET /health/deep ──────────────────────────────────────────────────
sep("Test 2 — GET /health/deep")
try:
    r = httpx.get(f"{BASE}/health/deep", timeout=10)
    print(f"  HTTP {r.status_code}")
    d = r.json()
    print(json.dumps(d, ensure_ascii=False, indent=2))
    check("HTTP 200 (tất cả deps up)", r.status_code == 200)
    check("status=ok", d.get("status") == "ok")
    checks = d.get("checks", {})
    for dep in ["opensearch", "qdrant", "postgres"]:
        dep_status = checks.get(dep, {}).get("status")
        check(f"  {dep} status=ok", dep_status == "ok",
              f"latency_ms={checks.get(dep, {}).get('latency_ms')}")
    check("index_opensearch present", bool(d.get("index_opensearch")))
    check("index_qdrant present", bool(d.get("index_qdrant")))
except Exception as e:
    print(f"  ERROR: {e}")


# ── Test 3: Kiểm tra da10_dependency_up trong metrics ───────────────────────
sep("Test 3 — da10_dependency_up trong /metrics sau /health/deep")
try:
    r = httpx.get(f"{BASE}/metrics", timeout=5)
    body = r.text
    dep_lines = [ln for ln in body.splitlines() if "da10_dependency_up" in ln and not ln.startswith("#")]
    print(f"  da10_dependency_up lines: {dep_lines}")
    check("da10_dependency_up{opensearch}", any("opensearch" in ln for ln in dep_lines))
    check("da10_dependency_up{qdrant}", any("qdrant" in ln for ln in dep_lines))
    check("da10_dependency_up{postgres}", any("postgres" in ln for ln in dep_lines))
    all_up = all('1.0' in ln or ln.endswith('1') for ln in dep_lines if dep_lines)
    check("tất cả dependency value=1.0", all_up)
except Exception as e:
    print(f"  ERROR: {e}")


# ── Test 4: Kiểm tra logs/da10.jsonl ─────────────────────────────────────────
sep("Test 4 — logs/da10.jsonl có search_completed + context_completed")
import os
log_path = "logs/da10.jsonl"
try:
    if not os.path.exists(log_path):
        print(f"  FAIL — file không tồn tại: {log_path}")
    else:
        lines = open(log_path, encoding="utf-8").readlines()
        print(f"  {log_path}: {len(lines)} dòng")
        events = []
        for ln in lines:
            try:
                obj = json.loads(ln.strip())
                events.append(obj.get("event"))
            except Exception:
                pass

        search_logs = [e for e in events if e == "search_completed"]
        context_logs = [e for e in events if e == "context_completed"]
        print(f"  search_completed: {len(search_logs)} dòng")
        print(f"  context_completed: {len(context_logs)} dòng")
        check("có search_completed log", len(search_logs) > 0)
        check("có context_completed log", len(context_logs) > 0)

        # In dòng search_completed cuối cùng
        for ln in reversed(lines):
            try:
                obj = json.loads(ln.strip())
                if obj.get("event") == "search_completed":
                    print("\n  Dòng search_completed cuối:")
                    print("  " + json.dumps(obj, ensure_ascii=False))
                    check("  có stages_ms", "stages_ms" in obj)
                    check("  có request_id", bool(obj.get("request_id")))
                    check("  có git_commit", bool(obj.get("git_commit")))
                    break
            except Exception:
                pass
except Exception as e:
    print(f"  ERROR: {e}")


print("\n" + "=" * 60)
print("  DONE")
print("=" * 60)
