"""DA10 — Phase 3a: Embedding. chunks.jsonl -> embeddings.npy (bge-m3, 1024-dim, L2-norm).

Dùng GPU nếu có (Quadro T2000). Vector căn theo THỨ TỰ DÒNG của chunks.jsonl
(index.py đọc lại chunks.jsonl cùng thứ tự + zip với embeddings.npy).

Chạy:  python pipeline/embed.py
Output: embeddings.npy (N x 1024 float32), embed_meta.json (đếm + model)
"""
from __future__ import annotations
import json
import os
import sys

import datasets  # noqa: F401  — force pyarrow DLLs load before torch/CUDA (Windows DLL conflict)
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.settings import settings  # noqa: E402

CHUNKS = "chunks.jsonl"
OUT_VEC = "embeddings.npy"
OUT_META = "embed_meta.json"
BATCH = 16          # Quadro T2000 4GB -> batch nhỏ + fp16
MAX_LEN = 512


def run():
    if not os.path.exists(CHUNKS):
        sys.exit(f"Thiếu {CHUNKS} — chạy pipeline/chunking.py trước.")

    texts, ids = [], []
    with open(CHUNKS, encoding="utf-8") as fh:
        for line in fh:
            c = json.loads(line)
            texts.append(c["embed_text"])
            ids.append(c["chunk_id"])
    print(f"Đọc {len(texts)} chunk. Nạp model {settings.embed_model} ...")

    from FlagEmbedding import BGEM3FlagModel
    model = BGEM3FlagModel(settings.embed_model, use_fp16=True)  # tự dùng CUDA nếu có

    out = model.encode(texts, batch_size=BATCH, max_length=MAX_LEN)["dense_vecs"]
    vecs = np.asarray(out, dtype=np.float32)
    # L2-normalize (cosine)
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    vecs = vecs / norms

    if vecs.shape[1] != settings.embed_dim:
        sys.exit(f"Chiều vector {vecs.shape[1]} != EMBED_DIM {settings.embed_dim}")

    np.save(OUT_VEC, vecs)
    json.dump(
        {"count": len(ids), "dim": int(vecs.shape[1]), "model": settings.embed_model,
         "first_id": ids[0], "last_id": ids[-1]},
        open(OUT_META, "w", encoding="utf-8"), ensure_ascii=False, indent=2,
    )
    print(f"✓ Embedding xong: {vecs.shape[0]} x {vecs.shape[1]} -> {OUT_VEC}")


if __name__ == "__main__":
    run()
