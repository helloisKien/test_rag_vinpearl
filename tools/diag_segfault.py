"""Diagnostic: tìm nguyên nhân segfault sentence-transformers trong uvicorn.

Chạy: python tools/diag_segfault.py
Ba test A/B/C giúp xác định context nào gây segfault.
"""
import os
import sys

os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["EMBED_FORCE_CPU"] = "1"
os.environ["RERANK_FORCE_CPU"] = "1"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio

print("=" * 60)
print("DA10 Segfault Diagnostic")
print("=" * 60)

print("\nStep 1: import torch...")
import torch
print(f"Step 2: torch {torch.__version__}  cuda={torch.cuda.is_available()}")

print("Step 3: import SentenceTransformer...")
from sentence_transformers import SentenceTransformer
print("Step 4: import OK")

MODEL = "BAAI/bge-m3"


# ── Test A: main thread, không asyncio (giống smoke_search.py) ────────────────
print("\n[Test A] Load in main thread (no event loop)...")
try:
    m = SentenceTransformer(MODEL, device="cpu")
    v = m.encode(["hello"], normalize_embeddings=True)
    print(f"[Test A] PASS  shape={v.shape}")
    del m
except Exception as e:
    print(f"[Test A] FAIL  {type(e).__name__}: {e}")


# ── Test B: thread pool via run_in_executor (giống FastAPI def endpoint) ──────
print("\n[Test B] Load in thread pool via run_in_executor...")


def _load_b():
    m2 = SentenceTransformer(MODEL, device="cpu")
    v2 = m2.encode(["hello"], normalize_embeddings=True)
    return v2.shape


async def run_b():
    loop = asyncio.get_event_loop()
    shape = await loop.run_in_executor(None, _load_b)
    print(f"[Test B] PASS  shape={shape}")


try:
    asyncio.run(run_b())
except Exception as e:
    print(f"[Test B] FAIL  {type(e).__name__}: {e}")


# ── Test C: trực tiếp trong async coroutine (event loop thread = lifespan) ────
print("\n[Test C] Load directly in async coroutine (event loop thread)...")


async def run_c():
    m3 = SentenceTransformer(MODEL, device="cpu")
    v3 = m3.encode(["hello"], normalize_embeddings=True)
    print(f"[Test C] PASS  shape={v3.shape}")


try:
    asyncio.run(run_c())
except Exception as e:
    print(f"[Test C] FAIL  {type(e).__name__}: {e}")


print("\n" + "=" * 60)
print("Kết quả:")
print("  A PASS, B PASS, C PASS → vấn đề specific to uvicorn setup")
print("  A PASS, B PASS, C FAIL → fix: dùng run_in_executor trong lifespan")
print("  A PASS, B FAIL         → fix: load model trước khi asyncio start")
print("  A FAIL                 → model bị hỏng / thiếu file")
print("=" * 60)
