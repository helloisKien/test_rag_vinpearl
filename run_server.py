"""DA10 — Server entry point: preload ML models in main thread before uvicorn starts.

Fix cho Windows segfault: uvicorn trên Windows đặt WindowsSelectorEventLoopPolicy
(khác ProactorEventLoop mà asyncio.run() dùng). Load model trong main thread TRƯỚC
khi event loop start → tránh race condition giữa PyTorch/tokenizer init và uvicorn.

Run: python run_server.py
"""
import os
import sys

# MUST set before any torch / HuggingFace tokenizer import
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["OMP_NUM_THREADS"] = "1"          # prevent OpenMP thread contention on Windows

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("=" * 55)
print("DA10 Server Startup")
print("=" * 55)

# --- CUDA sanity check ---
import torch
print(f"PyTorch {torch.__version__}  CUDA available: {torch.cuda.is_available()}")
if torch.cuda.is_available():
    try:
        free_vram, total_vram = torch.cuda.mem_get_info(0)
        print(f"VRAM: {free_vram/1024**3:.2f} GB free / {total_vram/1024**3:.2f} GB total")
        # Need ~2.2 GB for embedder + reranker in fp16; fallback CPU if not enough
        if free_vram < 2.4 * 1024**3:
            print("WARNING: VRAM < 2.4 GB — falling back to CPU mode")
            os.environ["EMBED_FORCE_CPU"] = "1"
            os.environ["RERANK_FORCE_CPU"] = "1"
    except Exception as e:
        print(f"WARNING: cuda.mem_get_info failed ({e}) — falling back to CPU mode")
        os.environ["EMBED_FORCE_CPU"] = "1"
        os.environ["RERANK_FORCE_CPU"] = "1"

# Preload ML models in main thread BEFORE uvicorn starts its event loop.
# Singletons in core/embedder.py + core/reranker.py cache the loaded model;
# FastAPI threadpool calls later just reuse the cached object.
print("Step 1: Loading embedder (bge-m3)...")
from core.embedder import embed_query
embed_query("warmup")
print("        Embedder OK.")

print("Step 2: Loading reranker (bge-reranker-v2-m3)...")
from core.reranker import rerank
rerank("warmup", ["warmup text"])
print("        Reranker OK.")

print("Step 3: Starting uvicorn on :8000 ...")
import uvicorn
uvicorn.run(
    "api.main:app",
    host="0.0.0.0",
    port=8000,
    workers=1,      # MUST be 1 — spawning workers forks process → PyTorch segfault on Windows
    reload=False,   # NO reload — watchfiles subprocess conflicts with PyTorch on Windows
    loop="asyncio", # explicit: force asyncio loop (consistent với diagnostic tests)
)
