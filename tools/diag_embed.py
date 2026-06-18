"""DA10 — DEBUG embedder/reranker (chạy 1 lần để xác định chính xác nguyên nhân + đường sửa).

Chạy:  python tools/diag_embed.py
Mục tiêu:
  [A] In phiên bản các lib liên quan.
  [B] Xác nhận transformers.from_pretrained có nhận 'dtype' không + dòng code FlagEmbedding gây lỗi.
  [C] Thử SentenceTransformer('BAAI/bge-m3') load + encode (đường thay thế, không qua FlagEmbedding).
  [D] ĐO ĐỘ NHẤT QUÁN: cos(ST.encode(chunk0.embed_text), embeddings.npy[0]) — nếu ~1.0 thì
      query-embed bằng SentenceTransformer khớp corpus -> KHÔNG cần re-embed.
  [E] Thử CrossEncoder('BAAI/bge-reranker-v2-m3') load trên GPU (đường rerank thay thế).
Mỗi mục bọc try/except để chạy hết, không dừng giữa chừng.
"""
from __future__ import annotations
import json
import sys
import traceback

import numpy as np


def section(t):
    print("\n" + "=" * 70 + f"\n[{t}]")


# ---------- A. versions ----------
section("A) Versions")
for mod in ["transformers", "FlagEmbedding", "sentence_transformers", "torch", "tokenizers", "huggingface_hub"]:
    try:
        m = __import__(mod)
        print(f"  {mod:22s} {getattr(m, '__version__', '?')}")
    except Exception as e:
        print(f"  {mod:22s} IMPORT-FAIL: {e}")

try:
    import torch
    print(f"  cuda available: {torch.cuda.is_available()} | device: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'cpu'}")
except Exception as e:
    print("  torch cuda check fail:", e)


# ---------- B. transformers from_pretrained 'dtype' support + FlagEmbedding dòng lỗi ----------
section("B) transformers 'dtype' support + FlagEmbedding runner")
try:
    import inspect
    from transformers import AutoModel
    src = inspect.getsource(AutoModel.from_pretrained)
    print("  AutoModel.from_pretrained nhắc tới 'dtype'?:", "'dtype'" in src or "dtype" in src.split("torch_dtype")[0][-200:])
    print("  (transformers cũ chỉ có 'torch_dtype'; FlagEmbedding 1.4 truyền 'dtype')")
except Exception:
    traceback.print_exc()
try:
    import FlagEmbedding, os
    runner = os.path.join(os.path.dirname(FlagEmbedding.__file__),
                          "finetune", "embedder", "encoder_only", "m3", "runner.py")
    print("  runner.py:", runner)
    if os.path.exists(runner):
        for i, line in enumerate(open(runner, encoding="utf-8"), 1):
            if "from_pretrained" in line or "dtype" in line:
                print(f"    L{i}: {line.rstrip()}")
except Exception:
    traceback.print_exc()


# ---------- C+D. SentenceTransformer bge-m3 + consistency ----------
section("C+D) SentenceTransformer('BAAI/bge-m3') load + consistency vs embeddings.npy")
try:
    import torch
    from sentence_transformers import SentenceTransformer
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    st = SentenceTransformer("BAAI/bge-m3", device=dev)
    line = open("chunks.jsonl", encoding="utf-8").readline()
    chunk0 = json.loads(line)
    v = st.encode([chunk0["embed_text"]], normalize_embeddings=True)[0]
    v = np.asarray(v, dtype=np.float32)
    print(f"  ST encode OK | dim={v.shape} | norm={float(np.linalg.norm(v)):.4f} | first3={v[:3]}")
    corpus = np.load("embeddings.npy")
    cos = float(np.dot(v, corpus[0]))
    print(f"  chunk0 = {chunk0['chunk_id']}")
    print(f"  >>> cos( ST(chunk0), embeddings.npy[0] ) = {cos:.4f}")
    print("  >>> cos ~ >0.98 => SentenceTransformer KHỚP corpus FlagEmbedding -> KHÔNG cần re-embed.")
    print("  >>> cos thấp => phải re-embed corpus bằng cùng phương pháp với query.")
    del st
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
except Exception:
    traceback.print_exc()


# ---------- E. CrossEncoder reranker trên GPU ----------
section("E) CrossEncoder('BAAI/bge-reranker-v2-m3') trên GPU (fp16)")
try:
    import torch
    from sentence_transformers import CrossEncoder
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    ce = CrossEncoder("BAAI/bge-reranker-v2-m3", device=dev, max_length=512)
    try:
        ce.model.half()  # fp16 để vừa GPU 4GB
        print("  ce.model.half() OK")
    except Exception as e:
        print("  half() fail (vẫn chạy fp32):", e)
    import time
    t = time.perf_counter()
    s = ce.predict([("khách sạn gần biển", "Khách sạn nằm ngay bãi biển riêng.")])
    print(f"  CrossEncoder predict OK | score={s} | thời gian={(time.perf_counter()-t)*1000:.0f}ms (1 cặp, gồm warmup)")
except Exception:
    traceback.print_exc()

print("\n" + "=" * 70)
print("XONG. Gửi toàn bộ output cho assistant để chốt cách sửa.")
